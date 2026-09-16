#ifndef AI_PANEL_ENVIRONMENT_SERVICE_H
#define AI_PANEL_ENVIRONMENT_SERVICE_H

#include <cstdint>

#include <driver/i2c_master.h>

class EnvironmentService {
public:
    static EnvironmentService& GetInstance();

    bool Initialize(i2c_master_bus_handle_t bus);
    bool GetReadings(float& temperature_c, float& humidity_percent);

private:
    EnvironmentService() = default;
    EnvironmentService(const EnvironmentService&) = delete;
    EnvironmentService& operator=(const EnvironmentService&) = delete;

    static bool CheckCrc(const uint8_t* bytes, uint8_t checksum);
    bool ReadSensor();

    i2c_master_dev_handle_t device_ = nullptr;
    float temperature_c_ = 0.0f;
    float humidity_percent_ = 0.0f;
    int64_t last_attempt_ms_ = 0;
    int64_t last_success_ms_ = 0;
    int64_t last_log_ms_ = 0;
    int64_t last_error_log_ms_ = 0;
};

#endif
