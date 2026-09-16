#include "environment_service.h"

#include <esp_log.h>
#include <esp_timer.h>
#include <freertos/FreeRTOS.h>
#include <freertos/task.h>

namespace {

constexpr char kTag[] = "PanelEnvironment";
constexpr uint16_t kAddress = 0x70;
constexpr int64_t kReadIntervalMs = 2000;
constexpr int64_t kReadingExpiryMs = 10000;

}  // namespace

EnvironmentService& EnvironmentService::GetInstance() {
    static EnvironmentService instance;
    return instance;
}

bool EnvironmentService::Initialize(i2c_master_bus_handle_t bus) {
    if (device_ != nullptr) return true;
    if (bus == nullptr || i2c_master_probe(bus, kAddress, 100) != ESP_OK) {
        ESP_LOGW(kTag, "SHTC3 not found at 0x70");
        return false;
    }

    i2c_device_config_t config = {};
    config.dev_addr_length = I2C_ADDR_BIT_LEN_7;
    config.device_address = kAddress;
    config.scl_speed_hz = 100000;
    if (i2c_master_bus_add_device(bus, &config, &device_) != ESP_OK) {
        device_ = nullptr;
        ESP_LOGE(kTag, "Failed to attach SHTC3 to shared I2C bus");
        return false;
    }
    ESP_LOGI(kTag, "SHTC3 detected at 0x70");
    return true;
}

bool EnvironmentService::CheckCrc(const uint8_t* bytes, uint8_t checksum) {
    uint8_t crc = 0xFF;
    for (int index = 0; index < 2; ++index) {
        crc ^= bytes[index];
        for (int bit = 0; bit < 8; ++bit) {
            crc = (crc & 0x80U) ? static_cast<uint8_t>((crc << 1) ^ 0x31U)
                                : static_cast<uint8_t>(crc << 1);
        }
    }
    return crc == checksum;
}

bool EnvironmentService::ReadSensor() {
    if (device_ == nullptr) return false;
    const uint8_t wake[] = {0x35, 0x17};
    const uint8_t measure_without_clock_stretching[] = {0x78, 0x66};
    const uint8_t sleep[] = {0xB0, 0x98};
    uint8_t response[6] = {};

    const int64_t now_ms = esp_timer_get_time() / 1000;
    const auto log_error = [this, now_ms](const char* step, esp_err_t error) {
        if (last_error_log_ms_ == 0 || now_ms - last_error_log_ms_ >= 10000) {
            ESP_LOGW(kTag, "SHTC3 %s failed: %s", step, esp_err_to_name(error));
            last_error_log_ms_ = now_ms;
        }
    };

    esp_err_t result = i2c_master_transmit(device_, wake, sizeof(wake), 100);
    if (result != ESP_OK) {
        log_error("wake", result);
        return false;
    }
    vTaskDelay(pdMS_TO_TICKS(10));
    result = i2c_master_transmit(device_, measure_without_clock_stretching,
                                 sizeof(measure_without_clock_stretching), 100);
    if (result != ESP_OK) {
        log_error("measure command", result);
        return false;
    }
    // Normal-power temperature-first conversion needs up to 12.1 ms. Use two
    // scheduler ticks (20 ms with the current 100 Hz tick) so it is never read early.
    vTaskDelay(pdMS_TO_TICKS(20));
    const esp_err_t receive_result =
        i2c_master_receive(device_, response, sizeof(response), 100);
    i2c_master_transmit(device_, sleep, sizeof(sleep), 100);
    if (receive_result != ESP_OK) {
        log_error("receive", receive_result);
        return false;
    }
    if (!CheckCrc(response, response[2]) || !CheckCrc(response + 3, response[5])) {
        log_error("CRC", ESP_ERR_INVALID_CRC);
        return false;
    }

    const uint16_t raw_temperature =
        (static_cast<uint16_t>(response[0]) << 8) | response[1];
    const uint16_t raw_humidity =
        (static_cast<uint16_t>(response[3]) << 8) | response[4];
    const float temperature = -45.0f + 175.0f * raw_temperature / 65535.0f;
    const float humidity = 100.0f * raw_humidity / 65535.0f;
    if (temperature < -40.0f || temperature > 125.0f ||
        humidity < 0.0f || humidity > 100.0f) {
        return false;
    }

    temperature_c_ = temperature;
    humidity_percent_ = humidity;
    last_success_ms_ = esp_timer_get_time() / 1000;
    if (last_log_ms_ == 0 || last_success_ms_ - last_log_ms_ >= 30000) {
        ESP_LOGI(kTag, "SHTC3 temperature=%.2fC humidity=%.1f%%",
                 temperature_c_, humidity_percent_);
        last_log_ms_ = last_success_ms_;
    }
    return true;
}

bool EnvironmentService::GetReadings(float& temperature_c,
                                     float& humidity_percent) {
    const int64_t now_ms = esp_timer_get_time() / 1000;
    if (last_attempt_ms_ == 0 || now_ms - last_attempt_ms_ >= kReadIntervalMs) {
        last_attempt_ms_ = now_ms;
        ReadSensor();
    }
    temperature_c = temperature_c_;
    humidity_percent = humidity_percent_;
    return last_success_ms_ != 0 && now_ms - last_success_ms_ <= kReadingExpiryMs;
}
