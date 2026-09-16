#pragma once

#include <atomic>

#include <esp_http_server.h>

class SettingsPortalService {
public:
    static SettingsPortalService& GetInstance();

    esp_err_t ServeRoot(httpd_req_t* request);
    void RegisterHandlers(httpd_handle_t server);
    float GetBatteryScale();

private:
    SettingsPortalService() = default;
    static esp_err_t HandleConfig(httpd_req_t* request);
    static esp_err_t HandleSave(httpd_req_t* request);
    std::atomic<int> battery_scale_milli_{0};
};
