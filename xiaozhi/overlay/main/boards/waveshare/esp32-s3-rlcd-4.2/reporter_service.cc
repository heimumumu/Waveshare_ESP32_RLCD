#include "reporter_service.h"

#include <algorithm>
#include <cctype>
#include <cerrno>
#include <cstdio>
#include <cstring>

#include <cJSON.h>
#include <esp_log.h>
#include <esp_mac.h>
#include <esp_netif.h>
#include <esp_timer.h>
#include <esp_wifi.h>
#include <sha/sha_core.h>

#include "settings.h"

namespace {

constexpr char kTag[] = "PanelReporter";
constexpr uint16_t kLocalPort = 42100;
constexpr uint16_t kDiscoveryPort = 8766;
constexpr int64_t kDiscoveryIntervalMs = 1000;
constexpr int64_t kReporterExpiryMs = 5000;
constexpr char kDiscoveryRequest[] = "AI_PANEL_DISCOVER_V1";
constexpr char kDiscoveryType[] = "AI_PANEL_REPORTER_V1";

int64_t NowMs() {
    return esp_timer_get_time() / 1000;
}

void CopyUtf8(char* destination, size_t destination_size, const char* source) {
    if (destination_size == 0) return;
    destination[0] = '\0';
    if (source == nullptr) return;

    size_t in = 0;
    size_t out = 0;
    while (source[in] != '\0' && out + 1 < destination_size) {
        const unsigned char lead = static_cast<unsigned char>(source[in]);
        size_t width = 1;
        if ((lead & 0xE0) == 0xC0) width = 2;
        else if ((lead & 0xF0) == 0xE0) width = 3;
        else if ((lead & 0xF8) == 0xF0) width = 4;
        if (out + width >= destination_size) break;
        bool complete = true;
        for (size_t offset = 1; offset < width; ++offset) {
            if (source[in + offset] == '\0' ||
                (static_cast<unsigned char>(source[in + offset]) & 0xC0) != 0x80) {
                complete = false;
                break;
            }
        }
        if (!complete) width = 1;
        memcpy(destination + out, source + in, width);
        in += width;
        out += width;
    }
    destination[out] = '\0';
}

const cJSON* JsonItem(const cJSON* object, const char* name) {
    return object == nullptr ? nullptr :
        cJSON_GetObjectItemCaseSensitive(const_cast<cJSON*>(object), name);
}

bool JsonString(const cJSON* object, const char* name,
                char* destination, size_t destination_size) {
    const cJSON* item = JsonItem(object, name);
    if (!cJSON_IsString(item) || item->valuestring == nullptr) return false;
    CopyUtf8(destination, destination_size, item->valuestring);
    return true;
}

bool JsonFloat(const cJSON* object, const char* name, float& value) {
    const cJSON* item = JsonItem(object, name);
    if (!cJSON_IsNumber(item)) return false;
    value = static_cast<float>(item->valuedouble);
    return true;
}

int16_t JsonPercent(const cJSON* object, const char* name) {
    float value = -1;
    if (!JsonFloat(object, name, value) || value < 0 || value > 100) return -1;
    return static_cast<int16_t>(value);
}

uint32_t NonNegativeSeconds(float value) {
    return static_cast<uint32_t>(std::max(0.0f, value));
}

}  // namespace

ReporterService& ReporterService::GetInstance() {
    static ReporterService instance;
    return instance;
}

ReporterService::ReporterService() {
    mutex_ = xSemaphoreCreateMutex();
    uint8_t mac[6] = {};
    if (esp_read_mac(mac, ESP_MAC_WIFI_STA) == ESP_OK) {
        snprintf(board_id_, sizeof(board_id_), "%02X%02X%02X%02X%02X%02X",
                 mac[0], mac[1], mac[2], mac[3], mac[4], mac[5]);
    }
}

bool ReporterService::Start() {
    if (task_ != nullptr) return true;
    if (mutex_ == nullptr) return false;
    LoadSettings();
    return xTaskCreatePinnedToCore(TaskEntry, "panel-reporter", 8192, this, 1,
                                   &task_, 0) == pdPASS;
}

bool ReporterService::GetSnapshot(PanelReporterSnapshot& snapshot) {
    if (mutex_ == nullptr || xSemaphoreTake(mutex_, pdMS_TO_TICKS(20)) != pdTRUE) {
        return false;
    }
    snapshot = snapshot_;
    xSemaphoreGive(mutex_);
    return true;
}

void ReporterService::RequestSelection(int index) {
    if (mutex_ == nullptr || xSemaphoreTake(mutex_, pdMS_TO_TICKS(20)) != pdTRUE) {
        return;
    }
    requested_index_ = index;
    xSemaphoreGive(mutex_);
}

void ReporterService::RequestReload() {
    if (mutex_ == nullptr || xSemaphoreTake(mutex_, pdMS_TO_TICKS(20)) != pdTRUE) {
        return;
    }
    reload_requested_ = true;
    xSemaphoreGive(mutex_);
}

void ReporterService::TaskEntry(void* argument) {
    static_cast<ReporterService*>(argument)->Run();
}

void ReporterService::Run() {
    while (true) {
        bool reload = false;
        if (xSemaphoreTake(mutex_, pdMS_TO_TICKS(20)) == pdTRUE) {
            reload = reload_requested_;
            reload_requested_ = false;
            xSemaphoreGive(mutex_);
        }
        if (reload) {
            CloseSocket();
            endpoint_count_ = 0;
            selected_index_ = -1;
            memset(expected_pairing_hash_, 0, sizeof(expected_pairing_hash_));
            ClearSelectedMetrics();
            LoadSettings();
        }
        if (!WifiReady()) {
            if (socket_ >= 0) {
                CloseSocket();
                for (int index = 0; index < endpoint_count_; ++index) {
                    endpoints_[index].online = false;
                }
                ClearSelectedMetrics();
                PublishSnapshot();
            }
            vTaskDelay(pdMS_TO_TICKS(250));
            continue;
        }

        if (!OpenSocket()) {
            vTaskDelay(pdMS_TO_TICKS(1000));
            continue;
        }

        int requested = -1;
        if (xSemaphoreTake(mutex_, pdMS_TO_TICKS(20)) == pdTRUE) {
            requested = requested_index_;
            requested_index_ = -1;
            xSemaphoreGive(mutex_);
        }
        if (requested >= 0) SelectEndpoint(requested, true);

        const int64_t now = NowMs();
        if (last_discovery_ms_ == 0 ||
            now - last_discovery_ms_ >= kDiscoveryIntervalMs) {
            SendDiscovery(now);
        }
        ReceiveOne();
        ExpireEndpoints(NowMs());
        vTaskDelay(pdMS_TO_TICKS(20));
    }
}

bool ReporterService::WifiReady() const {
    wifi_ap_record_t ap = {};
    if (esp_wifi_sta_get_ap_info(&ap) != ESP_OK) return false;
    esp_netif_t* netif = esp_netif_get_handle_from_ifkey("WIFI_STA_DEF");
    esp_netif_ip_info_t ip = {};
    return netif != nullptr && esp_netif_get_ip_info(netif, &ip) == ESP_OK &&
           ip.ip.addr != 0;
}

bool ReporterService::OpenSocket() {
    if (socket_ >= 0) return true;
    socket_ = socket(AF_INET, SOCK_DGRAM, IPPROTO_IP);
    if (socket_ < 0) {
        ESP_LOGW(kTag, "socket failed: errno=%d", errno);
        return false;
    }

    int enabled = 1;
    setsockopt(socket_, SOL_SOCKET, SO_REUSEADDR, &enabled, sizeof(enabled));
    setsockopt(socket_, SOL_SOCKET, SO_BROADCAST, &enabled, sizeof(enabled));
    timeval timeout = {.tv_sec = 0, .tv_usec = 100000};
    setsockopt(socket_, SOL_SOCKET, SO_RCVTIMEO, &timeout, sizeof(timeout));

    sockaddr_in local = {};
    local.sin_family = AF_INET;
    local.sin_port = htons(kLocalPort);
    local.sin_addr.s_addr = htonl(INADDR_ANY);
    if (bind(socket_, reinterpret_cast<sockaddr*>(&local), sizeof(local)) != 0) {
        ESP_LOGW(kTag, "bind UDP %u failed: errno=%d", kLocalPort, errno);
        CloseSocket();
        return false;
    }
    ESP_LOGI(kTag, "Reporter discovery listening on UDP %u", kLocalPort);
    return true;
}

void ReporterService::CloseSocket() {
    if (socket_ >= 0) {
        shutdown(socket_, SHUT_RDWR);
        close(socket_);
        socket_ = -1;
    }
    last_discovery_ms_ = 0;
}

void ReporterService::SendDiscovery(int64_t now_ms) {
    sockaddr_in destination = {};
    destination.sin_family = AF_INET;
    destination.sin_port = htons(kDiscoveryPort);
    destination.sin_addr.s_addr = htonl(INADDR_BROADCAST);
    char request[128];
    const int request_length = snprintf(
        request, sizeof(request),
        "{\"type\":\"%s\",\"board_id\":\"%s\"}",
        kDiscoveryRequest, board_id_);
    const int result = sendto(socket_, request, request_length, 0,
                              reinterpret_cast<sockaddr*>(&destination),
                              sizeof(destination));
    if (result < 0) ESP_LOGD(kTag, "discovery send failed: errno=%d", errno);
    last_discovery_ms_ = now_ms;
}

void ReporterService::ReceiveOne() {
    char payload[4096];
    sockaddr_in source = {};
    socklen_t source_length = sizeof(source);
    const int received = recvfrom(socket_, payload, sizeof(payload) - 1, 0,
                                  reinterpret_cast<sockaddr*>(&source),
                                  &source_length);
    if (received <= 0) return;
    payload[received] = '\0';
    ParseDiscovery(payload, static_cast<size_t>(received), source);
}

void ReporterService::ParseDiscovery(const char* payload, size_t length,
                                     const sockaddr_in& source) {
    cJSON* root = cJSON_ParseWithLength(payload, length);
    if (root == nullptr) return;

    char type[32] = {};
    char id[40] = {};
    char pairing_hash[65] = {};
    float port_value = 0;
    if (!JsonString(root, "type", type, sizeof(type)) ||
        strcmp(type, kDiscoveryType) != 0 ||
        !JsonString(root, "reporter_id", id, sizeof(id)) ||
        !JsonFloat(root, "http_port", port_value)) {
        cJSON_Delete(root);
        return;
    }
    JsonString(root, "pairing_hash", pairing_hash, sizeof(pairing_hash));

    int index = FindEndpoint(id);
    const bool is_new = index < 0;
    if (is_new) {
        if (endpoint_count_ >= kPanelMaxReporters) {
            cJSON_Delete(root);
            return;
        }
        index = endpoint_count_++;
    }

    Endpoint& endpoint = endpoints_[index];
    endpoint.online = true;
    endpoint.address = source;
    endpoint.http_port = static_cast<uint16_t>(port_value);
    endpoint.last_seen_ms = NowMs();
    CopyUtf8(endpoint.reporter_id, sizeof(endpoint.reporter_id), id);
    CopyUtf8(endpoint.pairing_hash, sizeof(endpoint.pairing_hash), pairing_hash);
    if (!JsonString(root, "computer_name", endpoint.computer_name,
                    sizeof(endpoint.computer_name))) {
        CopyUtf8(endpoint.computer_name, sizeof(endpoint.computer_name), "UNKNOWN-PC");
    }
    if (!JsonString(root, "agent_state", endpoint.agent_state,
                    sizeof(endpoint.agent_state))) {
        CopyUtf8(endpoint.agent_state, sizeof(endpoint.agent_state), "IDLE");
    }
    for (char* cursor = endpoint.agent_state; *cursor != '\0'; ++cursor) {
        *cursor = static_cast<char>(std::toupper(static_cast<unsigned char>(*cursor)));
    }
    if (cJSON_IsTrue(JsonItem(root, "codex_login_required"))) {
        CopyUtf8(endpoint.agent_state, sizeof(endpoint.agent_state), "LOGIN_REQUIRED");
    }
    endpoint.codex_short_remaining = JsonPercent(root, "codex_short_remaining");
    endpoint.codex_week_remaining = JsonPercent(root, "codex_week_remaining");
    endpoint.codex_quota_stale = cJSON_IsTrue(JsonItem(root, "codex_quota_stale"));

    if (selected_id_[0] != '\0' && strcmp(selected_id_, id) == 0) {
        // Existing installations are upgraded on first sight. Afterwards both
        // the stable PC id and its secret-derived hash must match.
        if (expected_pairing_hash_[0] == '\0' ||
            strcmp(expected_pairing_hash_, pairing_hash) == 0) {
            selected_index_ = index;
            if (expected_pairing_hash_[0] == '\0' && pairing_hash[0] != '\0') {
                CopyUtf8(expected_pairing_hash_, sizeof(expected_pairing_hash_), pairing_hash);
                Settings settings("reporter", true);
                settings.SetString("pair_hash", expected_pairing_hash_);
            }
        }
    } else if (selected_id_[0] == '\0') {
        SelectEndpoint(index, true);
    }

    if (index == selected_index_) {
        PanelReporterMetrics metrics;
        metrics.connected = true;
        metrics.latency_ms = static_cast<uint32_t>(
            std::max<int64_t>(0, NowMs() - last_discovery_ms_));
        CopyUtf8(metrics.reporter_id, sizeof(metrics.reporter_id), endpoint.reporter_id);
        CopyUtf8(metrics.computer_name, sizeof(metrics.computer_name),
                 endpoint.computer_name);
        CopyUtf8(metrics.agent_state, sizeof(metrics.agent_state), endpoint.agent_state);
        metrics.codex_short_remaining = endpoint.codex_short_remaining;
        metrics.codex_week_remaining = endpoint.codex_week_remaining;
        metrics.codex_quota_stale = endpoint.codex_quota_stale;

        const cJSON* performance = JsonItem(root, "performance");
        const bool base_metrics =
            JsonFloat(performance, "cpu_percent", metrics.cpu_percent) &&
            JsonFloat(performance, "memory_percent", metrics.memory_percent) &&
            JsonFloat(performance, "disk_percent", metrics.disk_percent) &&
            JsonFloat(performance, "upload_bytes_per_sec",
                      metrics.upload_bytes_per_second) &&
            JsonFloat(performance, "download_bytes_per_sec",
                      metrics.download_bytes_per_second);
        metrics.gpu_valid = JsonFloat(performance, "gpu_percent", metrics.gpu_percent);
        metrics.cpu_temperature_valid =
            JsonFloat(performance, "cpu_temp_c", metrics.cpu_temperature_c);
        metrics.gpu_temperature_valid =
            JsonFloat(performance, "gpu_temp_c", metrics.gpu_temperature_c);

        JsonString(root, "media_status", metrics.media_status,
                   sizeof(metrics.media_status));
        JsonString(root, "media_title", metrics.media_title,
                   sizeof(metrics.media_title));
        JsonString(root, "media_artist", metrics.media_artist,
                   sizeof(metrics.media_artist));
        JsonString(root, "media_lyric", metrics.media_lyric,
                   sizeof(metrics.media_lyric));
        float media_position = 0;
        float media_duration = 0;
        JsonFloat(root, "media_position", media_position);
        JsonFloat(root, "media_duration", media_duration);
        metrics.media_position_seconds = NonNegativeSeconds(media_position);
        metrics.media_duration_seconds = NonNegativeSeconds(media_duration);
        const cJSON* media_available = JsonItem(root, "media_available");
        metrics.media_available = cJSON_IsTrue(media_available) ||
                                  metrics.media_title[0] != '\0';

        if (base_metrics) metrics_ = metrics;
        else ClearSelectedMetrics();
    }

    PublishSnapshot();
    if (is_new) {
        ESP_LOGI(kTag, "Reporter discovered: %s", endpoint.computer_name);
    }
    cJSON_Delete(root);
}

void ReporterService::ExpireEndpoints(int64_t now_ms) {
    bool changed = false;
    for (int index = 0; index < endpoint_count_; ++index) {
        Endpoint& endpoint = endpoints_[index];
        if (endpoint.online && now_ms - endpoint.last_seen_ms > kReporterExpiryMs) {
            endpoint.online = false;
            changed = true;
            if (index == selected_index_) ClearSelectedMetrics();
        }
    }
    if (changed) PublishSnapshot();
}

int ReporterService::FindEndpoint(const char* reporter_id) const {
    for (int index = 0; index < endpoint_count_; ++index) {
        if (strcmp(endpoints_[index].reporter_id, reporter_id) == 0) return index;
    }
    return -1;
}

void ReporterService::SelectEndpoint(int index, bool persist) {
    if (index < 0 || index >= endpoint_count_) return;
    selected_index_ = static_cast<int8_t>(index);
    CopyUtf8(selected_id_, sizeof(selected_id_), endpoints_[index].reporter_id);
    CopyUtf8(expected_pairing_hash_, sizeof(expected_pairing_hash_),
             endpoints_[index].pairing_hash);
    ClearSelectedMetrics();
    if (persist) {
        Settings settings("reporter", true);
        settings.SetString("current_id", selected_id_);
        settings.SetString("current_name", endpoints_[index].computer_name);
        settings.SetString("pair_hash", expected_pairing_hash_);
    }
    PublishSnapshot();
}

void ReporterService::PublishSnapshot() {
    if (mutex_ == nullptr || xSemaphoreTake(mutex_, pdMS_TO_TICKS(20)) != pdTRUE) {
        return;
    }
    snapshot_.device_count = endpoint_count_;
    snapshot_.current_index = selected_index_;
    snapshot_.metrics = metrics_;
    for (int index = 0; index < endpoint_count_; ++index) {
        snapshot_.devices[index].online = endpoints_[index].online;
        CopyUtf8(snapshot_.devices[index].reporter_id,
                 sizeof(snapshot_.devices[index].reporter_id),
                 endpoints_[index].reporter_id);
        CopyUtf8(snapshot_.devices[index].computer_name,
                 sizeof(snapshot_.devices[index].computer_name),
                 endpoints_[index].computer_name);
        CopyUtf8(snapshot_.devices[index].agent_state,
                 sizeof(snapshot_.devices[index].agent_state),
                 endpoints_[index].agent_state);
    }
    ++snapshot_.generation;
    xSemaphoreGive(mutex_);
}

void ReporterService::ClearSelectedMetrics() {
    PanelReporterMetrics cleared;
    if (selected_index_ >= 0 && selected_index_ < endpoint_count_) {
        CopyUtf8(cleared.reporter_id, sizeof(cleared.reporter_id),
                 endpoints_[selected_index_].reporter_id);
        CopyUtf8(cleared.computer_name, sizeof(cleared.computer_name),
                 endpoints_[selected_index_].computer_name);
    }
    metrics_ = cleared;
}

void ReporterService::LoadSettings() {
    Settings reporter_settings("reporter");
    const std::string selected = reporter_settings.GetString("current_id", "");
    CopyUtf8(selected_id_, sizeof(selected_id_), selected.c_str());
    const std::string bound_hash = reporter_settings.GetString("pair_hash", "");
    CopyUtf8(expected_pairing_hash_, sizeof(expected_pairing_hash_),
             bound_hash.c_str());

    Settings panel_settings("wifi-config");
    const std::string token = panel_settings.GetString("reporter", "");
    if (!token.empty()) {
        unsigned char digest[32] = {};
        esp_sha(SHA2_256,
                reinterpret_cast<const unsigned char*>(token.data()),
                token.size(), digest);
        for (int index = 0; index < 32; ++index) {
            snprintf(expected_pairing_hash_ + index * 2, 3, "%02x", digest[index]);
        }
        ESP_LOGI(kTag, "Reporter pairing filter enabled");
    } else if (expected_pairing_hash_[0] != '\0') {
        ESP_LOGI(kTag, "Using automatically bound Reporter identity");
    } else {
        ESP_LOGI(kTag, "No Reporter bound; first discovered Reporter will be trusted");
    }
    PublishSnapshot();
}
