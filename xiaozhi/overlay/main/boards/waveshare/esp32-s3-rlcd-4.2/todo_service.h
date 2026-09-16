#pragma once

#include <cstddef>
#include <cstdint>
#include <string>

#include <freertos/FreeRTOS.h>
#include <freertos/semphr.h>
#include <nvs.h>

constexpr size_t kPanelMaximumTodos = 4;
constexpr size_t kPanelTodoTextCapacity = 64;

struct PanelTodoItem {
    uint32_t id = 0;
    char text[kPanelTodoTextCapacity] = {};
    bool completed = false;
};

struct PanelTodoSnapshot {
    uint32_t generation = 0;
    size_t count = 0;
    PanelTodoItem items[kPanelMaximumTodos] = {};
};

class TodoService {
public:
    static TodoService& GetInstance();

    bool Start();
    bool GetSnapshot(PanelTodoSnapshot& snapshot);
    void RegisterMcpTools();

    bool Create(const char* text, uint32_t* created_id = nullptr);
    bool SetCompleted(uint32_t id, bool completed, bool* changed = nullptr);
    bool SetCompletedByText(const char* text, bool completed, uint32_t* matched_id = nullptr,
                            bool* changed = nullptr);
    bool Remove(uint32_t id);
    bool RemoveByText(const char* text, uint32_t* removed_id = nullptr);
    bool ClearCompleted(size_t* removed_count = nullptr);
    bool ClearAll(size_t* removed_count = nullptr);

private:
    static constexpr uint32_t kMagic = 0x53594E41U;
    static constexpr uint16_t kVersion = 1;

    struct StoredSnapshot {
        uint32_t magic = kMagic;
        uint16_t version = kVersion;
        uint16_t count = 0;
        uint32_t generation = 0;
        uint32_t next_id = 1;
        PanelTodoItem items[kPanelMaximumTodos] = {};
        uint32_t checksum = 0;
    };

    TodoService() = default;
    TodoService(const TodoService&) = delete;
    TodoService& operator=(const TodoService&) = delete;

    static uint32_t Checksum(const StoredSnapshot& snapshot);
    static bool IsValid(const StoredSnapshot& snapshot);
    static bool HasVisibleText(const char* text);
    bool SaveLocked();
    std::string ListJson();

    SemaphoreHandle_t mutex_ = nullptr;
    nvs_handle_t nvs_handle_ = 0;
    StoredSnapshot stored_ = {};
    uint32_t ui_generation_ = 0;
    bool ready_ = false;
    bool tools_registered_ = false;
};
