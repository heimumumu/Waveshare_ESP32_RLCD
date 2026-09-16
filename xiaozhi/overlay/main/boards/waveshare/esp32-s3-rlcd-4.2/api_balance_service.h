#pragma once

#include <cstdint>
#include <string>

#include <freertos/FreeRTOS.h>
#include <freertos/semphr.h>
#include <freertos/task.h>

struct PanelApiBalanceSnapshot {
    uint32_t generation = 0;
    char provider[32] = "API";
    char display[48] = "--";
    bool available = false;
};

class ApiBalanceService {
public:
    static ApiBalanceService& GetInstance();

    bool Start();
    bool GetSnapshot(PanelApiBalanceSnapshot& snapshot);
    void RequestRefresh();

private:
    struct Config {
        std::string provider;
        std::string adapter;
        std::string api_base_url;
        std::string api_key;
        std::string request_url;
        std::string method;
        std::string auth_mode;
        std::string auth_name;
        std::string value_path;
        std::string unit;
        std::string unit_path;
        std::string request_body;
        float scale = 1.0f;
    };

    ApiBalanceService() = default;
    ApiBalanceService(const ApiBalanceService&) = delete;
    ApiBalanceService& operator=(const ApiBalanceService&) = delete;

    static void TaskEntry(void* context);
    void Run();
    Config LoadConfig();
    bool Fetch(const Config& config, PanelApiBalanceSnapshot& result);
    bool FetchDeepSeek(const Config& config, PanelApiBalanceSnapshot& result);
    bool FetchCustom(const Config& config, PanelApiBalanceSnapshot& result);
    bool PerformRequest(const Config& config, const std::string& source_url,
                        const std::string& method, const std::string& auth_mode,
                        const std::string& auth_name, const std::string& source_body,
                        std::string& response);
    static bool ExtractJsonPath(const std::string& json, const std::string& path,
                                std::string& value);
    static bool WifiReady();
    void Publish(PanelApiBalanceSnapshot result);

    SemaphoreHandle_t mutex_ = nullptr;
    TaskHandle_t task_ = nullptr;
    PanelApiBalanceSnapshot snapshot_ = {};
};
