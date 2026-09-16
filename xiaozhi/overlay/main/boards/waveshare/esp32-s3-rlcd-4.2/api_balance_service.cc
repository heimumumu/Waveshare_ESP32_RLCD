#include "api_balance_service.h"

#include <algorithm>
#include <cctype>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>

#include <cJSON.h>
#include <esp_crt_bundle.h>
#include <esp_http_client.h>
#include <esp_log.h>
#include <esp_netif.h>
#include <esp_wifi.h>
#include <nvs.h>

#include "settings.h"

namespace {

constexpr char kTag[] = "ApiBalance";
constexpr size_t kMaximumResponseBytes = 4096;
constexpr uint32_t kRefreshMs = 5U * 60U * 1000U;
constexpr uint32_t kRetryMs = 30U * 1000U;

struct ResponseContext {
    std::string* response;
};

esp_err_t CollectResponse(esp_http_client_event_t* event) {
    if (event->event_id != HTTP_EVENT_ON_DATA || event->data == nullptr ||
        event->data_len <= 0 || event->user_data == nullptr) return ESP_OK;
    auto* context = static_cast<ResponseContext*>(event->user_data);
    const size_t available = context->response->size() < kMaximumResponseBytes
        ? kMaximumResponseBytes - context->response->size() : 0;
    if (available > 0) {
        context->response->append(static_cast<const char*>(event->data),
                                  std::min<size_t>(event->data_len, available));
    }
    return ESP_OK;
}

std::string Trim(std::string value) {
    auto visible = [](unsigned char character) { return !std::isspace(character); };
    value.erase(value.begin(), std::find_if(value.begin(), value.end(), visible));
    value.erase(std::find_if(value.rbegin(), value.rend(), visible).base(), value.end());
    return value;
}

std::string Lower(std::string value) {
    for (char& character : value) {
        character = static_cast<char>(std::tolower(static_cast<unsigned char>(character)));
    }
    return value;
}

std::string Upper(std::string value) {
    for (char& character : value) {
        character = static_cast<char>(std::toupper(static_cast<unsigned char>(character)));
    }
    return value;
}

std::string NormalizedBase(std::string value) {
    value = Trim(value);
    while (!value.empty() && value.back() == '/') value.pop_back();
    return value;
}

void Copy(char* destination, size_t size, const std::string& source) {
    if (size == 0) return;
    snprintf(destination, size, "%s", source.c_str());
}

std::string UrlEncode(const std::string& value) {
    static constexpr char hex[] = "0123456789ABCDEF";
    std::string encoded;
    encoded.reserve(value.size() * 3);
    for (unsigned char character : value) {
        if (std::isalnum(character) || character == '-' || character == '_' ||
            character == '.' || character == '~') {
            encoded.push_back(static_cast<char>(character));
        } else {
            encoded.push_back('%');
            encoded.push_back(hex[character >> 4]);
            encoded.push_back(hex[character & 0x0F]);
        }
    }
    return encoded;
}

std::string ReplaceAll(std::string value, const std::string& needle,
                       const std::string& replacement) {
    size_t position = 0;
    while ((position = value.find(needle, position)) != std::string::npos) {
        value.replace(position, needle.size(), replacement);
        position += replacement.size();
    }
    return value;
}

bool ReadFloat(const char* name_space, const char* key, float& value) {
    nvs_handle_t handle = 0;
    if (nvs_open(name_space, NVS_READONLY, &handle) != ESP_OK) return false;
    size_t length = sizeof(value);
    const esp_err_t error = nvs_get_blob(handle, key, &value, &length);
    nvs_close(handle);
    return error == ESP_OK && length == sizeof(value);
}

std::string FormatNumber(const std::string& source, float scale) {
    char* end = nullptr;
    const double parsed = strtod(source.c_str(), &end);
    if (end == source.c_str() || *end != '\0') return {};
    char buffer[48];
    snprintf(buffer, sizeof(buffer), "%.6f", parsed * scale);
    std::string formatted = buffer;
    while (!formatted.empty() && formatted.back() == '0') formatted.pop_back();
    if (!formatted.empty() && formatted.back() == '.') formatted.pop_back();
    return formatted;
}

}  // namespace

ApiBalanceService& ApiBalanceService::GetInstance() {
    static ApiBalanceService instance;
    return instance;
}

bool ApiBalanceService::Start() {
    if (task_ != nullptr) return true;
    mutex_ = xSemaphoreCreateMutex();
    if (mutex_ == nullptr) return false;
    snapshot_ = PanelApiBalanceSnapshot{};
    const Config config = LoadConfig();
    Copy(snapshot_.provider, sizeof(snapshot_.provider), config.provider);
    ++snapshot_.generation;
    return xTaskCreatePinnedToCore(TaskEntry, "api-balance", 10240, this, 1,
                                   &task_, 0) == pdPASS;
}

void ApiBalanceService::TaskEntry(void* context) {
    static_cast<ApiBalanceService*>(context)->Run();
}

void ApiBalanceService::Run() {
    while (true) {
        if (!WifiReady()) {
            ulTaskNotifyTake(pdTRUE, pdMS_TO_TICKS(1000));
            continue;
        }
        const Config config = LoadConfig();
        PanelApiBalanceSnapshot result;
        Copy(result.provider, sizeof(result.provider), config.provider);
        const bool success = Fetch(config, result);
        if (!success) Copy(result.display, sizeof(result.display), "ERR");
        Publish(result);
        ulTaskNotifyTake(pdTRUE, pdMS_TO_TICKS(success ? kRefreshMs : kRetryMs));
    }
}

void ApiBalanceService::RequestRefresh() {
    if (task_ != nullptr) xTaskNotifyGive(task_);
}

bool ApiBalanceService::GetSnapshot(PanelApiBalanceSnapshot& snapshot) {
    if (mutex_ == nullptr || xSemaphoreTake(mutex_, pdMS_TO_TICKS(20)) != pdTRUE) {
        return false;
    }
    snapshot = snapshot_;
    xSemaphoreGive(mutex_);
    return true;
}

void ApiBalanceService::Publish(PanelApiBalanceSnapshot result) {
    if (xSemaphoreTake(mutex_, pdMS_TO_TICKS(100)) != pdTRUE) return;
    result.generation = snapshot_.generation + 1;
    snapshot_ = result;
    xSemaphoreGive(mutex_);
}

ApiBalanceService::Config ApiBalanceService::LoadConfig() {
    Settings settings("wifi-config");
    Config config;
    config.provider = Trim(settings.GetString("api-provider", "API"));
    if (config.provider.empty()) config.provider = "API";
    config.adapter = Lower(Trim(settings.GetString("bal-adapter", "disabled")));
    config.api_base_url = NormalizedBase(settings.GetString("api-base", ""));
    config.api_key = settings.GetString("api-key", settings.GetString("deepseek", ""));
    config.request_url = Trim(settings.GetString("bal-url", ""));
    config.method = Upper(Trim(settings.GetString("bal-method", "GET")));
    config.auth_mode = Lower(Trim(settings.GetString("bal-auth", "bearer")));
    config.auth_name = Trim(settings.GetString("bal-hname", "Authorization"));
    config.value_path = Trim(settings.GetString("bal-path", "data.balance"));
    config.unit = Trim(settings.GetString("bal-unit", ""));
    config.unit_path = Trim(settings.GetString("bal-upath", ""));
    config.request_body = settings.GetString("bal-body", "");
    float scale = 1.0f;
    if (ReadFloat("wifi-config", "bal-scale", scale) && std::isfinite(scale) &&
        scale != 0.0f && scale >= -1000000.0f && scale <= 1000000.0f) {
        config.scale = scale;
    }
    return config;
}

bool ApiBalanceService::Fetch(const Config& config,
                              PanelApiBalanceSnapshot& result) {
    Copy(result.display, sizeof(result.display), "--");
    result.available = false;
    if (config.adapter == "disabled" || config.adapter.empty()) return true;
    if (config.adapter == "deepseek") {
        if (config.api_key.empty()) return true;
        return FetchDeepSeek(config, result);
    }
    if (config.adapter == "custom") return FetchCustom(config, result);
    Copy(result.display, sizeof(result.display), "N/A");
    return true;
}

bool ApiBalanceService::FetchDeepSeek(const Config& config,
                                      PanelApiBalanceSnapshot& result) {
    std::string base = config.api_base_url.empty() ? "https://api.deepseek.com"
                                                   : config.api_base_url;
    if (base.size() >= 3 && base.compare(base.size() - 3, 3, "/v1") == 0) {
        base.resize(base.size() - 3);
    }
    std::string response;
    if (!PerformRequest(config, base + "/user/balance", "GET", "bearer",
                        "Authorization", "", response)) return false;
    std::string currency;
    std::string total;
    if (!ExtractJsonPath(response, "balance_infos[0].currency", currency) ||
        !ExtractJsonPath(response, "balance_infos[0].total_balance", total) ||
        currency.empty() || total.empty()) return false;
    Copy(result.display, sizeof(result.display), currency + " " + total);
    result.available = true;
    return true;
}

bool ApiBalanceService::FetchCustom(const Config& config,
                                    PanelApiBalanceSnapshot& result) {
    if (config.request_url.empty() || config.value_path.empty()) {
        Copy(result.display, sizeof(result.display), "N/A");
        return true;
    }
    std::string response;
    if (!PerformRequest(config, config.request_url, config.method, config.auth_mode,
                        config.auth_name, config.request_body, response)) return false;
    std::string raw_value;
    if (!ExtractJsonPath(response, config.value_path, raw_value)) return false;
    std::string value = FormatNumber(raw_value, config.scale);
    if (value.empty()) value = raw_value;
    std::string unit = config.unit;
    if (!config.unit_path.empty()) {
        std::string dynamic_unit;
        if (ExtractJsonPath(response, config.unit_path, dynamic_unit)) unit = dynamic_unit;
    }
    Copy(result.display, sizeof(result.display), unit.empty() ? value : unit + " " + value);
    result.available = true;
    return true;
}

bool ApiBalanceService::PerformRequest(const Config& config,
                                       const std::string& source_url,
                                       const std::string& method,
                                       const std::string& auth_mode,
                                       const std::string& auth_name,
                                       const std::string& source_body,
                                       std::string& response) {
    std::string url = source_url;
    std::string body = ReplaceAll(source_body, "{{API_KEY}}", config.api_key);
    const bool sends_key = !config.api_key.empty() &&
        (auth_mode != "none" || source_body.find("{{API_KEY}}") != std::string::npos);
    if (sends_key && url.rfind("https://", 0) != 0) return false;
    if (auth_mode == "query" && !config.api_key.empty()) {
        const std::string name = auth_name.empty() ? "key" : auth_name;
        url += url.find('?') == std::string::npos ? '?' : '&';
        url += UrlEncode(name) + "=" + UrlEncode(config.api_key);
    }
    const bool https = url.rfind("https://", 0) == 0;
    if (!https && url.rfind("http://", 0) != 0) return false;

    response.clear();
    response.reserve(768);
    ResponseContext context{&response};
    esp_http_client_config_t http_config = {};
    http_config.url = url.c_str();
    http_config.event_handler = CollectResponse;
    http_config.user_data = &context;
    http_config.timeout_ms = 10000;
    http_config.buffer_size = 1024;
    http_config.buffer_size_tx = 1024;
    if (https) http_config.crt_bundle_attach = esp_crt_bundle_attach;
    esp_http_client_handle_t client = esp_http_client_init(&http_config);
    if (client == nullptr) return false;

    esp_http_client_set_header(client, "Accept", "application/json");
    if (!config.api_key.empty()) {
        if (auth_mode == "bearer") {
            const std::string authorization = "Bearer " + config.api_key;
            esp_http_client_set_header(client, "Authorization", authorization.c_str());
        } else if (auth_mode == "header") {
            const std::string name = auth_name.empty() ? "X-API-Key" : auth_name;
            esp_http_client_set_header(client, name.c_str(), config.api_key.c_str());
        }
    }
    if (method == "POST") {
        esp_http_client_set_method(client, HTTP_METHOD_POST);
        esp_http_client_set_header(client, "Content-Type", "application/json");
        esp_http_client_set_post_field(client, body.c_str(), body.size());
    } else {
        esp_http_client_set_method(client, HTTP_METHOD_GET);
    }
    const esp_err_t error = esp_http_client_perform(client);
    const int status = esp_http_client_get_status_code(client);
    esp_http_client_cleanup(client);
    return error == ESP_OK && status >= 200 && status < 300;
}

bool ApiBalanceService::ExtractJsonPath(const std::string& json,
                                        const std::string& source_path,
                                        std::string& value) {
    cJSON* root = cJSON_ParseWithLength(json.c_str(), json.size());
    if (root == nullptr) return false;
    cJSON* current = root;
    std::string path = Trim(source_path);
    if (path.rfind("$.", 0) == 0) path.erase(0, 2);
    else if (path == "$") path.clear();
    bool valid = true;
    size_t start = 0;
    while (valid && start < path.size()) {
        size_t dot = path.find('.', start);
        if (dot == std::string::npos) dot = path.size();
        const std::string segment = path.substr(start, dot - start);
        size_t bracket = segment.find('[');
        const std::string key = segment.substr(0, bracket);
        if (!key.empty()) current = cJSON_GetObjectItemCaseSensitive(current, key.c_str());
        while (current != nullptr && bracket != std::string::npos) {
            const size_t closing = segment.find(']', bracket + 1);
            if (closing == std::string::npos) { valid = false; break; }
            char* end = nullptr;
            const long index = strtol(segment.c_str() + bracket + 1, &end, 10);
            if (end != segment.c_str() + closing || index < 0 || !cJSON_IsArray(current)) {
                valid = false;
                break;
            }
            current = cJSON_GetArrayItem(current, static_cast<int>(index));
            bracket = segment.find('[', closing + 1);
        }
        if (current == nullptr) valid = false;
        start = dot + 1;
    }
    if (valid && cJSON_IsString(current) && current->valuestring != nullptr) {
        value = current->valuestring;
    } else if (valid && cJSON_IsNumber(current)) {
        char buffer[48];
        snprintf(buffer, sizeof(buffer), "%.6f", current->valuedouble);
        value = buffer;
        while (!value.empty() && value.back() == '0') value.pop_back();
        if (!value.empty() && value.back() == '.') value.pop_back();
    } else if (valid && cJSON_IsBool(current)) {
        value = cJSON_IsTrue(current) ? "true" : "false";
    } else {
        valid = false;
    }
    cJSON_Delete(root);
    return valid;
}

bool ApiBalanceService::WifiReady() {
    wifi_ap_record_t ap = {};
    if (esp_wifi_sta_get_ap_info(&ap) != ESP_OK) return false;
    esp_netif_t* netif = esp_netif_get_handle_from_ifkey("WIFI_STA_DEF");
    esp_netif_ip_info_t ip = {};
    return netif != nullptr && esp_netif_get_ip_info(netif, &ip) == ESP_OK &&
           ip.ip.addr != 0;
}
