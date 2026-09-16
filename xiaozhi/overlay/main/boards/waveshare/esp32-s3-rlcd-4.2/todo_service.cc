#include "todo_service.h"

#include <cstddef>
#include <cstdio>
#include <cstring>
#include <stdexcept>
#include <string>

#include <cJSON.h>
#include <esp_log.h>

#include "application.h"
#include "board.h"
#include "display.h"
#include "mcp_server.h"

namespace {

constexpr char kTag[] = "PanelTodos";

void CopyUtf8(char* destination, size_t destination_size, const char* source) {
    if (destination_size == 0) return;
    destination[0] = '\0';
    if (source == nullptr) return;

    size_t input = 0;
    size_t output = 0;
    while (source[input] != '\0' && output + 1 < destination_size) {
        const unsigned char lead = static_cast<unsigned char>(source[input]);
        size_t width = 1;
        if ((lead & 0xE0) == 0xC0) width = 2;
        else if ((lead & 0xF0) == 0xE0) width = 3;
        else if ((lead & 0xF8) == 0xF0) width = 4;
        if (output + width >= destination_size) break;
        bool complete = true;
        for (size_t offset = 1; offset < width; ++offset) {
            if (source[input + offset] == '\0' ||
                (static_cast<unsigned char>(source[input + offset]) & 0xC0) != 0x80) {
                complete = false;
                break;
            }
        }
        if (!complete) width = 1;
        memcpy(destination + output, source + input, width);
        input += width;
        output += width;
    }
    destination[output] = '\0';
}

std::string TrimAsciiWhitespace(const char* text) {
    if (text == nullptr) return {};
    const char* begin = text;
    while (*begin == ' ' || *begin == '\t' || *begin == '\r' || *begin == '\n') ++begin;
    const char* end = begin + strlen(begin);
    while (end > begin &&
           (end[-1] == ' ' || end[-1] == '\t' || end[-1] == '\r' || end[-1] == '\n')) {
        --end;
    }
    return std::string(begin, end);
}

void ScheduleTodoUiRefresh() {
    Application::GetInstance().Schedule([]() {
        auto* display = Board::GetInstance().GetDisplay();
        if (display != nullptr) display->UpdateStatusBar(true);
    });
}

std::string MutationResultJson(const char* operation, size_t changed, size_t remaining,
                               uint32_t id = 0) {
    cJSON* root = cJSON_CreateObject();
    cJSON_AddBoolToObject(root, "ok", true);
    cJSON_AddStringToObject(root, "operation", operation);
    cJSON_AddNumberToObject(root, "changed", changed);
    cJSON_AddNumberToObject(root, "remaining", remaining);
    if (id != 0) cJSON_AddNumberToObject(root, "id", id);
    char* encoded = cJSON_PrintUnformatted(root);
    std::string result = encoded == nullptr ? "{\"ok\":false}" : encoded;
    if (encoded != nullptr) cJSON_free(encoded);
    cJSON_Delete(root);
    return result;
}

}  // namespace

TodoService& TodoService::GetInstance() {
    static TodoService instance;
    return instance;
}

uint32_t TodoService::Checksum(const StoredSnapshot& snapshot) {
    const uint8_t* bytes = reinterpret_cast<const uint8_t*>(&snapshot);
    const size_t length = offsetof(StoredSnapshot, checksum);
    uint32_t value = 2166136261U;
    for (size_t index = 0; index < length; ++index) {
        value ^= bytes[index];
        value *= 16777619U;
    }
    return value;
}

bool TodoService::IsValid(const StoredSnapshot& snapshot) {
    return snapshot.magic == kMagic && snapshot.version == kVersion &&
           snapshot.count <= kPanelMaximumTodos && snapshot.next_id != 0 &&
           snapshot.checksum == Checksum(snapshot);
}

bool TodoService::HasVisibleText(const char* text) {
    if (text == nullptr) return false;
    while (*text != '\0') {
        if (*text != ' ' && *text != '\t' && *text != '\r' && *text != '\n') {
            return true;
        }
        ++text;
    }
    return false;
}

bool TodoService::Start() {
    if (ready_) return true;
    mutex_ = xSemaphoreCreateMutex();
    if (mutex_ == nullptr) return false;
    if (nvs_open("syna-todos", NVS_READWRITE, &nvs_handle_) != ESP_OK) return false;

    StoredSnapshot slots[2] = {};
    bool valid[2] = {};
    const char* keys[2] = {"slot0", "slot1"};
    for (int index = 0; index < 2; ++index) {
        size_t length = sizeof(StoredSnapshot);
        if (nvs_get_blob(nvs_handle_, keys[index], &slots[index], &length) == ESP_OK &&
            length == sizeof(StoredSnapshot)) {
            valid[index] = IsValid(slots[index]);
        }
    }
    if (valid[0] || valid[1]) {
        const int selected = !valid[0] ? 1 : (!valid[1] ? 0 :
            (static_cast<int32_t>(slots[1].generation - slots[0].generation) > 0 ? 1 : 0));
        stored_ = slots[selected];
    } else {
        stored_ = StoredSnapshot{};
    }
    ++ui_generation_;
    ready_ = true;
    ESP_LOGI(kTag, "Loaded %u local todo(s)", stored_.count);
    return true;
}

bool TodoService::SaveLocked() {
    StoredSnapshot pending = stored_;
    ++pending.generation;
    pending.checksum = Checksum(pending);
    const char* key = (pending.generation & 1U) == 0 ? "slot0" : "slot1";
    if (nvs_set_blob(nvs_handle_, key, &pending, sizeof(pending)) != ESP_OK ||
        nvs_commit(nvs_handle_) != ESP_OK) {
        return false;
    }
    stored_ = pending;
    ++ui_generation_;
    return true;
}

bool TodoService::GetSnapshot(PanelTodoSnapshot& snapshot) {
    if (!ready_ || xSemaphoreTake(mutex_, pdMS_TO_TICKS(20)) != pdTRUE) return false;
    snapshot = PanelTodoSnapshot{};
    snapshot.generation = ui_generation_;
    snapshot.count = stored_.count;
    for (size_t index = 0; index < stored_.count; ++index) {
        snapshot.items[index] = stored_.items[index];
    }
    xSemaphoreGive(mutex_);
    return true;
}

bool TodoService::Create(const char* text, uint32_t* created_id) {
    if (!ready_ || !HasVisibleText(text) ||
        xSemaphoreTake(mutex_, pdMS_TO_TICKS(100)) != pdTRUE) return false;
    if (stored_.count >= kPanelMaximumTodos) {
        xSemaphoreGive(mutex_);
        return false;
    }
    const StoredSnapshot previous = stored_;
    PanelTodoItem& item = stored_.items[stored_.count++];
    item = PanelTodoItem{};
    item.id = stored_.next_id++;
    if (stored_.next_id == 0) stored_.next_id = 1;
    CopyUtf8(item.text, sizeof(item.text), text);
    const uint32_t id = item.id;
    const bool saved = SaveLocked();
    if (!saved) stored_ = previous;
    const size_t remaining = stored_.count;
    xSemaphoreGive(mutex_);
    if (saved) {
        if (created_id != nullptr) *created_id = id;
        ESP_LOGI(kTag, "Created todo id=%lu; remaining=%u",
                 static_cast<unsigned long>(id), static_cast<unsigned>(remaining));
        ScheduleTodoUiRefresh();
    }
    return saved;
}

bool TodoService::SetCompleted(uint32_t id, bool completed, bool* changed) {
    if (!ready_ || id == 0 || xSemaphoreTake(mutex_, pdMS_TO_TICKS(100)) != pdTRUE) {
        return false;
    }
    for (size_t index = 0; index < stored_.count; ++index) {
        if (stored_.items[index].id != id) continue;
        if (stored_.items[index].completed == completed) {
            xSemaphoreGive(mutex_);
            if (changed != nullptr) *changed = false;
            ScheduleTodoUiRefresh();
            return true;
        }
        const StoredSnapshot previous = stored_;
        stored_.items[index].completed = completed;
        const bool saved = SaveLocked();
        if (!saved) stored_ = previous;
        xSemaphoreGive(mutex_);
        if (saved) {
            if (changed != nullptr) *changed = true;
            ESP_LOGI(kTag, "Set todo id=%lu completed=%d",
                     static_cast<unsigned long>(id), completed);
            ScheduleTodoUiRefresh();
        }
        return saved;
    }
    xSemaphoreGive(mutex_);
    return false;
}

bool TodoService::SetCompletedByText(const char* text, bool completed, uint32_t* matched_id,
                                     bool* changed) {
    const std::string target = TrimAsciiWhitespace(text);
    if (!ready_ || target.empty() || xSemaphoreTake(mutex_, pdMS_TO_TICKS(100)) != pdTRUE) {
        return false;
    }

    uint32_t id = 0;
    size_t exact_matches = 0;
    for (size_t index = 0; index < stored_.count; ++index) {
        if (TrimAsciiWhitespace(stored_.items[index].text) == target) {
            id = stored_.items[index].id;
            ++exact_matches;
        }
    }

    if (exact_matches == 0) {
        size_t partial_matches = 0;
        for (size_t index = 0; index < stored_.count; ++index) {
            const std::string candidate = TrimAsciiWhitespace(stored_.items[index].text);
            if (candidate.find(target) != std::string::npos ||
                target.find(candidate) != std::string::npos) {
                id = stored_.items[index].id;
                ++partial_matches;
            }
        }
        exact_matches = partial_matches;
    }
    xSemaphoreGive(mutex_);

    if (exact_matches != 1 || !SetCompleted(id, completed, changed)) return false;
    if (matched_id != nullptr) *matched_id = id;
    return true;
}

bool TodoService::Remove(uint32_t id) {
    if (!ready_ || id == 0 || xSemaphoreTake(mutex_, pdMS_TO_TICKS(100)) != pdTRUE) {
        return false;
    }
    for (size_t index = 0; index < stored_.count; ++index) {
        if (stored_.items[index].id != id) continue;
        const StoredSnapshot previous = stored_;
        for (size_t move = index + 1; move < stored_.count; ++move) {
            stored_.items[move - 1] = stored_.items[move];
        }
        stored_.items[--stored_.count] = PanelTodoItem{};
        const bool saved = SaveLocked();
        if (!saved) stored_ = previous;
        const size_t remaining = stored_.count;
        xSemaphoreGive(mutex_);
        if (saved) {
            ESP_LOGI(kTag, "Deleted todo id=%lu; remaining=%u",
                     static_cast<unsigned long>(id), static_cast<unsigned>(remaining));
            ScheduleTodoUiRefresh();
        }
        return saved;
    }
    xSemaphoreGive(mutex_);
    return false;
}

bool TodoService::RemoveByText(const char* text, uint32_t* removed_id) {
    const std::string target = TrimAsciiWhitespace(text);
    if (!ready_ || target.empty() || xSemaphoreTake(mutex_, pdMS_TO_TICKS(100)) != pdTRUE) {
        return false;
    }

    uint32_t id = 0;
    size_t exact_matches = 0;
    for (size_t index = 0; index < stored_.count; ++index) {
        if (TrimAsciiWhitespace(stored_.items[index].text) == target) {
            id = stored_.items[index].id;
            ++exact_matches;
        }
    }
    if (exact_matches == 0) {
        size_t partial_matches = 0;
        for (size_t index = 0; index < stored_.count; ++index) {
            const std::string candidate = TrimAsciiWhitespace(stored_.items[index].text);
            if (candidate.find(target) != std::string::npos ||
                target.find(candidate) != std::string::npos) {
                id = stored_.items[index].id;
                ++partial_matches;
            }
        }
        exact_matches = partial_matches;
    }
    xSemaphoreGive(mutex_);

    if (exact_matches != 1 || !Remove(id)) return false;
    if (removed_id != nullptr) *removed_id = id;
    return true;
}

bool TodoService::ClearCompleted(size_t* removed_count) {
    if (!ready_ || xSemaphoreTake(mutex_, pdMS_TO_TICKS(100)) != pdTRUE) return false;
    const StoredSnapshot previous = stored_;
    const size_t before = stored_.count;
    size_t write = 0;
    for (size_t read = 0; read < stored_.count; ++read) {
        if (!stored_.items[read].completed) stored_.items[write++] = stored_.items[read];
    }
    if (write == stored_.count) {
        xSemaphoreGive(mutex_);
        if (removed_count != nullptr) *removed_count = 0;
        ScheduleTodoUiRefresh();
        return true;
    }
    while (stored_.count > write) stored_.items[--stored_.count] = PanelTodoItem{};
    const bool saved = SaveLocked();
    if (!saved) stored_ = previous;
    const size_t removed = saved ? before - stored_.count : 0;
    xSemaphoreGive(mutex_);
    if (saved) {
        if (removed_count != nullptr) *removed_count = removed;
        ESP_LOGI(kTag, "Cleared %u completed todo(s); remaining=%u",
                 static_cast<unsigned>(removed), static_cast<unsigned>(write));
        ScheduleTodoUiRefresh();
    }
    return saved;
}

bool TodoService::ClearAll(size_t* removed_count) {
    if (!ready_ || xSemaphoreTake(mutex_, pdMS_TO_TICKS(100)) != pdTRUE) return false;
    const size_t removed = stored_.count;
    if (removed == 0) {
        xSemaphoreGive(mutex_);
        if (removed_count != nullptr) *removed_count = 0;
        ScheduleTodoUiRefresh();
        return true;
    }

    const StoredSnapshot previous = stored_;
    stored_.count = 0;
    for (auto& item : stored_.items) item = PanelTodoItem{};
    const bool saved = SaveLocked();
    if (!saved) stored_ = previous;
    xSemaphoreGive(mutex_);
    if (saved) {
        if (removed_count != nullptr) *removed_count = removed;
        ESP_LOGI(kTag, "Cleared all %u todo(s)", static_cast<unsigned>(removed));
        ScheduleTodoUiRefresh();
    }
    return saved;
}

std::string TodoService::ListJson() {
    PanelTodoSnapshot snapshot;
    if (!GetSnapshot(snapshot)) throw std::runtime_error("Todo storage unavailable");
    cJSON* root = cJSON_CreateObject();
    cJSON* items = cJSON_AddArrayToObject(root, "items");
    for (size_t index = 0; index < snapshot.count; ++index) {
        cJSON* item = cJSON_CreateObject();
        cJSON_AddNumberToObject(item, "id", snapshot.items[index].id);
        cJSON_AddStringToObject(item, "text", snapshot.items[index].text);
        cJSON_AddBoolToObject(item, "completed", snapshot.items[index].completed);
        cJSON_AddItemToArray(items, item);
    }
    char* encoded = cJSON_PrintUnformatted(root);
    std::string result = encoded == nullptr ? "{\"items\":[]}" : encoded;
    if (encoded != nullptr) cJSON_free(encoded);
    cJSON_Delete(root);
    return result;
}

void TodoService::RegisterMcpTools() {
    if (tools_registered_) return;
    tools_registered_ = true;
    auto& mcp = McpServer::GetInstance();

    mcp.AddTool("self.todo.list",
        "列出设备本地待办及其 ID。必须以这个工具的实际返回为准；没有收到变更工具的成功结果时，不得声称待办已经创建、完成或删除。",
        PropertyList(), [this](const PropertyList&) -> ReturnValue { return ListJson(); });
    mcp.AddTool("self.todo.create",
        "在设备本地创建待办。最多四项，不要把多个事项合并成一项。",
        PropertyList({Property("text", kPropertyTypeString)}),
        [this](const PropertyList& properties) -> ReturnValue {
            uint32_t id = 0;
            if (!Create(properties["text"].value<std::string>().c_str(), &id)) {
                throw std::runtime_error("Unable to create todo: list full or invalid text");
            }
            PanelTodoSnapshot snapshot;
            if (!GetSnapshot(snapshot)) throw std::runtime_error("Todo storage unavailable");
            return MutationResultJson("create", 1, snapshot.count, id);
        });
    mcp.AddTool("self.todo.complete", "按 ID 完成一项本地待办。",
        PropertyList({Property("id", kPropertyTypeInteger, 1, INT32_MAX)}),
        [this](const PropertyList& properties) -> ReturnValue {
            bool changed = false;
            if (!SetCompleted(properties["id"].value<int>(), true, &changed)) {
                throw std::runtime_error("Todo id not found");
            }
            PanelTodoSnapshot snapshot;
            if (!GetSnapshot(snapshot)) throw std::runtime_error("Todo storage unavailable");
            return MutationResultJson("complete", changed ? 1 : 0, snapshot.count,
                                      properties["id"].value<int>());
        });
    mcp.AddTool("self.todo.complete_by_text",
        "按待办标题完成一项本地待办。用户说出待办内容但没有 ID 时直接调用，text 只填用户提到的标题；成功结果中的 changed 必须大于零才能声称完成。",
        PropertyList({Property("text", kPropertyTypeString)}),
        [this](const PropertyList& properties) -> ReturnValue {
            uint32_t id = 0;
            bool changed = false;
            if (!SetCompletedByText(properties["text"].value<std::string>().c_str(), true,
                                    &id, &changed)) {
                throw std::runtime_error("Todo title not found or matches more than one item; list todos and use ID");
            }
            PanelTodoSnapshot snapshot;
            if (!GetSnapshot(snapshot)) throw std::runtime_error("Todo storage unavailable");
            return MutationResultJson("complete_by_text", changed ? 1 : 0, snapshot.count, id);
        });
    mcp.AddTool("self.todo.reopen", "按 ID 将已完成的本地待办恢复为未完成。",
        PropertyList({Property("id", kPropertyTypeInteger, 1, INT32_MAX)}),
        [this](const PropertyList& properties) -> ReturnValue {
            bool changed = false;
            if (!SetCompleted(properties["id"].value<int>(), false, &changed)) {
                throw std::runtime_error("Todo id not found");
            }
            PanelTodoSnapshot snapshot;
            if (!GetSnapshot(snapshot)) throw std::runtime_error("Todo storage unavailable");
            return MutationResultJson("reopen", changed ? 1 : 0, snapshot.count,
                                      properties["id"].value<int>());
        });
    mcp.AddTool("self.todo.reopen_by_text",
        "按待办标题把已完成项恢复为未完成。用户说出待办内容但没有 ID 时直接调用。",
        PropertyList({Property("text", kPropertyTypeString)}),
        [this](const PropertyList& properties) -> ReturnValue {
            uint32_t id = 0;
            bool changed = false;
            if (!SetCompletedByText(properties["text"].value<std::string>().c_str(), false,
                                    &id, &changed)) {
                throw std::runtime_error("Todo title not found or matches more than one item; list todos and use ID");
            }
            PanelTodoSnapshot snapshot;
            if (!GetSnapshot(snapshot)) throw std::runtime_error("Todo storage unavailable");
            return MutationResultJson("reopen_by_text", changed ? 1 : 0, snapshot.count, id);
        });
    mcp.AddTool("self.todo.delete", "按 ID 删除一项本地待办。",
        PropertyList({Property("id", kPropertyTypeInteger, 1, INT32_MAX)}),
        [this](const PropertyList& properties) -> ReturnValue {
            if (!Remove(properties["id"].value<int>())) {
                throw std::runtime_error("Todo id not found");
            }
            PanelTodoSnapshot snapshot;
            if (!GetSnapshot(snapshot)) throw std::runtime_error("Todo storage unavailable");
            return MutationResultJson("delete", 1, snapshot.count,
                                      properties["id"].value<int>());
        });
    mcp.AddTool("self.todo.delete_by_text",
        "按待办标题删除一项本地待办。用户说出待办内容但没有 ID 时直接调用；成功结果中的 changed 必须大于零才能声称删除。",
        PropertyList({Property("text", kPropertyTypeString)}),
        [this](const PropertyList& properties) -> ReturnValue {
            uint32_t id = 0;
            if (!RemoveByText(properties["text"].value<std::string>().c_str(), &id)) {
                throw std::runtime_error("Todo title not found or matches more than one item; list todos and use ID");
            }
            PanelTodoSnapshot snapshot;
            if (!GetSnapshot(snapshot)) throw std::runtime_error("Todo storage unavailable");
            return MutationResultJson("delete_by_text", 1, snapshot.count, id);
        });
    mcp.AddTool("self.todo.clear_completed",
        "删除设备本地所有已完成待办。只有用户明确确认清理后才可把 confirm 设为 true。",
        PropertyList({Property("confirm", kPropertyTypeBoolean)}),
        [this](const PropertyList& properties) -> ReturnValue {
            if (!properties["confirm"].value<bool>()) {
                throw std::runtime_error("Explicit confirmation is required");
            }
            size_t removed = 0;
            if (!ClearCompleted(&removed)) throw std::runtime_error("Todo storage unavailable");
            PanelTodoSnapshot snapshot;
            if (!GetSnapshot(snapshot)) throw std::runtime_error("Todo storage unavailable");
            return MutationResultJson("clear_completed", removed, snapshot.count);
        });
    mcp.AddTool("self.todo.clear_all",
        "删除设备本地全部待办，包括未完成和已完成项。仅当用户明确要求删除全部待办时才把 confirm 设为 true；必须依据返回的 changed 数量回答，禁止未调用工具便声称成功。",
        PropertyList({Property("confirm", kPropertyTypeBoolean)}),
        [this](const PropertyList& properties) -> ReturnValue {
            if (!properties["confirm"].value<bool>()) {
                throw std::runtime_error("Explicit confirmation is required");
            }
            size_t removed = 0;
            if (!ClearAll(&removed)) throw std::runtime_error("Todo storage unavailable");
            PanelTodoSnapshot snapshot;
            if (!GetSnapshot(snapshot)) throw std::runtime_error("Todo storage unavailable");
            return MutationResultJson("clear_all", removed, snapshot.count);
        });
}
