#include <esp_lcd_panel_vendor.h>
#include <driver/i2c_master.h>
#include <driver/spi_common.h>
#include <esp_log.h>
#include <esp_system.h>
#include <esp_timer.h>
#include <nvs_flash.h>
#include <algorithm>
#include <cctype>
#include <string>
#include "custom_lcd_display.h"
#include "wifi_board.h"
#include "application.h"
#include "button.h"
#include "panel_button_gestures.h"
#include "config.h"
#include "codecs/box_audio_codec.h"
#include "wifi_station.h"
#include "mcp_server.h"
#include "reporter_service.h"
#include "todo_service.h"
#include "api_balance_service.h"
#include "settings_portal_service.h"
#include "environment_service.h"
#include "lvgl.h"
#include "custom_lcd_display.h"

#define TAG "waveshare_rlcd_4_2"

class CustomBoard : public WifiBoard {
private:
    i2c_master_bus_handle_t i2c_bus_;
    Button boot_button_;
    Button key_button_;
    CustomLcdDisplay *display_ = nullptr;
    PanelButtonGestures panel_buttons_;
    adc_oneshot_unit_handle_t adc1_handle;
    adc_cali_handle_t cali_handle;
    bool vbat_status = 0;
    bool settings_combo_triggered_ = false;
    esp_timer_handle_t factory_reset_timer_ = nullptr;

    static std::string LowerAscii(std::string value) {
        std::transform(value.begin(), value.end(), value.begin(), [](unsigned char ch) {
            return static_cast<char>(std::tolower(ch));
        });
        return value;
    }

    void TryEnterSettingsPortal() {
        if (settings_combo_triggered_ || gpio_get_level(BOOT_BUTTON_GPIO) != 0 ||
            gpio_get_level(KEY_BUTTON_GPIO) != 0) return;
        settings_combo_triggered_ = true;
        if (factory_reset_timer_ != nullptr) {
            esp_timer_stop(factory_reset_timer_);
            ESP_ERROR_CHECK(esp_timer_start_once(factory_reset_timer_, 7000000));
        }
        EnterWifiConfigMode();
    }

    static void FactoryResetTimerCallback(void* argument) {
        auto* board = static_cast<CustomBoard*>(argument);
        if (gpio_get_level(BOOT_BUTTON_GPIO) != 0 ||
            gpio_get_level(KEY_BUTTON_GPIO) != 0) return;
        xTaskCreate([](void*) {
            ESP_LOGW(TAG, "KEY+BOOT held 10 seconds: erasing all user settings");
            if (nvs_flash_erase() != ESP_OK) {
                ESP_LOGE(TAG, "Factory reset failed to erase NVS");
            }
            vTaskDelay(pdMS_TO_TICKS(300));
            esp_restart();
        }, "factory-reset", 3072, nullptr, 2, nullptr);
        (void)board;
    }

    void CancelFactoryResetCountdown() {
        if (factory_reset_timer_ != nullptr) esp_timer_stop(factory_reset_timer_);
    }

    void InitializeI2c() {
        i2c_master_bus_config_t i2c_bus_cfg = {};
        i2c_bus_cfg.i2c_port = ESP32_I2C_HOST;
        i2c_bus_cfg.sda_io_num = AUDIO_CODEC_I2C_SDA_PIN;
        i2c_bus_cfg.scl_io_num = AUDIO_CODEC_I2C_SCL_PIN;
        i2c_bus_cfg.clk_source = I2C_CLK_SRC_DEFAULT;
        i2c_bus_cfg.glitch_ignore_cnt = 7;
        i2c_bus_cfg.intr_priority = 0;
        i2c_bus_cfg.trans_queue_depth = 0;
        i2c_bus_cfg.flags.enable_internal_pullup = 1;
        ESP_ERROR_CHECK(i2c_new_master_bus(&i2c_bus_cfg, &i2c_bus_));
    }

    void InitializeButtons() { 
        boot_button_.OnPressDown([this]() {
            if (panel_buttons_.Idle()) settings_combo_triggered_ = false;
            panel_buttons_.BootDown();
        });
        boot_button_.OnClick([this]() {
            if (!panel_buttons_.BootClickAllowed() || settings_combo_triggered_) return;
            Application::GetInstance().Schedule([this]() {
                if (display_ != nullptr && display_->ConfirmComputerPicker()) return;
                auto& app = Application::GetInstance();
                if (app.GetDeviceState() == kDeviceStateStarting) {
                    EnterWifiConfigMode();
                    return;
                }
                app.ToggleChatState();
            });
        });

        // Decide short presses on release: holding KEY must not first flip a
        // page or move the selection. All LVGL work stays on the app task.
        key_button_.OnPressDown([this]() {
            if (panel_buttons_.Idle()) settings_combo_triggered_ = false;
            panel_buttons_.KeyDown();
        });

        boot_button_.OnLongPress([this]() { TryEnterSettingsPortal(); });
        key_button_.OnLongPress([this]() {
            const bool open_picker = panel_buttons_.KeyLongPress();
            if (gpio_get_level(BOOT_BUTTON_GPIO) == 0) {
                TryEnterSettingsPortal();
            } else if (open_picker && !settings_combo_triggered_) {
                Application::GetInstance().Schedule([this]() {
                    if (display_ != nullptr) display_->ToggleComputerPicker();
                });
            }
        });
        boot_button_.OnPressUp([this]() {
            panel_buttons_.BootUp();
            CancelFactoryResetCountdown();
        });
        key_button_.OnPressUp([this]() {
            const bool short_press = panel_buttons_.KeyUp();
            CancelFactoryResetCountdown();
            if (short_press) Application::GetInstance().Schedule([this]() {
                if (display_ != nullptr) display_->HandlePanelKeyShortPress();
            });
        });

#if CONFIG_USE_DEVICE_AEC
        boot_button_.OnDoubleClick([this]() {
            if (!panel_buttons_.BootClickAllowed() || settings_combo_triggered_) return;
            Application::GetInstance().Schedule([this]() {
                if (display_ != nullptr && display_->ConfirmComputerPicker()) return;
                auto& app = Application::GetInstance();
                if (app.GetDeviceState() == kDeviceStateIdle) {
                    app.SetAecMode(app.GetAecMode() == kAecOff ? kAecOnDeviceSide : kAecOff);
                }
            });
        });
#endif
    }

    void InitializeTools() {
        auto& mcp_server = McpServer::GetInstance();
        mcp_server.AddTool("self.disp.network", "重新配网", PropertyList(),
        [this](const PropertyList&) -> ReturnValue {
            EnterWifiConfigMode();
            return true;
        });
        mcp_server.AddTool(
            "self.panel.show_page",
            "切换状态屏页面。page 使用 dashboard（主页）、performance（电脑性能）、syna（Syna-sama 对话和待办）或 computers（电脑选择）。",
            PropertyList({Property("page", kPropertyTypeString)}),
            [this](const PropertyList& properties) -> ReturnValue {
                const std::string requested =
                    LowerAscii(properties["page"].value<std::string>());
                std::string page;
                if (requested == "dashboard" || requested == "home" ||
                    requested == "主页" || requested == "主页面") page = "dashboard";
                else if (requested == "performance" || requested == "性能" ||
                         requested == "性能页") page = "performance";
                else if (requested == "syna" || requested == "syna-sama" ||
                         requested == "对话" || requested == "待办") page = "syna";
                else if (requested == "computers" || requested == "computer" ||
                         requested == "电脑" || requested == "电脑列表") page = "computers";
                else throw std::runtime_error(
                    "Unknown page; use dashboard, performance, syna or computers");

                Application::GetInstance().Schedule([this, page]() {
                    display_->ShowPanelPage(page);
                });
                return std::string("已切换到 ") + page;
            });
        mcp_server.AddTool(
            "self.computer.list", "列出状态屏发现的电脑、在线状态和当前选择。",
            PropertyList(), [](const PropertyList&) -> ReturnValue {
                PanelReporterSnapshot snapshot = {};
                if (!ReporterService::GetInstance().GetSnapshot(snapshot) ||
                    snapshot.device_count == 0) {
                    return std::string("当前没有发现电脑");
                }
                std::string result = "已发现电脑：";
                for (int index = 0; index < snapshot.device_count; ++index) {
                    if (index != 0) result += "；";
                    result += snapshot.devices[index].computer_name;
                    result += snapshot.devices[index].online ? "（在线" : "（离线";
                    if (index == snapshot.current_index) result += "，当前";
                    result += "）";
                }
                return result;
            });
        mcp_server.AddTool(
            "self.computer.select",
            "按电脑名称切换状态屏的数据来源。先调用 self.computer.list，并把其中的完整名称传入 name。",
            PropertyList({Property("name", kPropertyTypeString)}),
            [this](const PropertyList& properties) -> ReturnValue {
                PanelReporterSnapshot snapshot = {};
                if (!ReporterService::GetInstance().GetSnapshot(snapshot)) {
                    throw std::runtime_error("Computer list is temporarily unavailable");
                }
                const std::string requested =
                    LowerAscii(properties["name"].value<std::string>());
                int selected = -1;
                for (int index = 0; index < snapshot.device_count; ++index) {
                    if (LowerAscii(snapshot.devices[index].computer_name) == requested) {
                        selected = index;
                        break;
                    }
                }
                if (selected < 0) {
                    throw std::runtime_error(
                        "Computer name not found; call self.computer.list first");
                }
                ReporterService::GetInstance().RequestSelection(selected);
                Application::GetInstance().Schedule([this]() {
                    display_->ShowPanelPage("dashboard");
                });
                return std::string("已选择电脑 ") +
                       snapshot.devices[selected].computer_name;
            });
        auto& todos = TodoService::GetInstance();
        if (!todos.Start()) {
            ESP_LOGE(TAG, "Failed to start local todo service");
        } else {
            todos.RegisterMcpTools();
        }
    }

    void InitializeLcdDisplay() {
        spi_display_config_t spi_config = {};
        spi_config.mosi = RLCD_MOSI_PIN;
        spi_config.scl = RLCD_SCK_PIN;
        spi_config.dc = RLCD_DC_PIN;
        spi_config.cs = RLCD_CS_PIN;
        spi_config.rst = RLCD_RST_PIN;
        display_ = new CustomLcdDisplay(NULL, NULL, RLCD_WIDTH,RLCD_HEIGHT,DISPLAY_OFFSET_X,DISPLAY_OFFSET_Y,DISPLAY_MIRROR_X,DISPLAY_MIRROR_Y,DISPLAY_SWAP_XY,spi_config);
    }

    uint16_t BatterygetVoltage(void) {
        static bool initialized = false;
        static adc_oneshot_unit_handle_t adc_handle;
        static adc_cali_handle_t cali_handle = NULL;
        if (!initialized) {
            adc_oneshot_unit_init_cfg_t init_config = {
                .unit_id = ADC_UNIT_1,
            };
            adc_oneshot_new_unit(&init_config, &adc_handle);
    
            adc_oneshot_chan_cfg_t ch_config = {
                .atten = ADC_ATTEN_DB_12,
                .bitwidth = ADC_BITWIDTH_12,
            };
            adc_oneshot_config_channel(adc_handle, ADC_CHANNEL_3, &ch_config);
    
            adc_cali_curve_fitting_config_t cali_config = {
                .unit_id = ADC_UNIT_1,
                .atten = ADC_ATTEN_DB_12,
                .bitwidth = ADC_BITWIDTH_12,
            };
            if (adc_cali_create_scheme_curve_fitting(&cali_config, &cali_handle) == ESP_OK) {
                initialized = true;
            }
        }

        if (initialized) {
            int raw_value = 0;
            int raw_voltage = 0;
            int voltage = 0; // mV
            adc_oneshot_read(adc_handle, ADC_CHANNEL_3, &raw_value);
            adc_cali_raw_to_voltage(cali_handle, raw_value, &raw_voltage);
            voltage = static_cast<int>(raw_voltage *
                SettingsPortalService::GetInstance().GetBatteryScale());
            // ESP_LOGI(TAG, "voltage: %dmV", voltage);
            return (uint16_t)voltage;
        }

        return 0;
    }

    uint8_t BatterygetPercent() {
        int voltage = 0;
        for (uint8_t i = 0; i < 10; i++) {
            voltage += BatterygetVoltage();
        }

        voltage /= 10;
        int percent = (-1 * voltage * voltage + 9016 * voltage - 19189000) / 10000;
        percent = (percent > 100) ? 100 : (percent < 0) ? 0 : percent;
        // ESP_LOGI(TAG, "voltage: %dmV, percentage: %d%%", voltage, percent);
        return (uint8_t)percent;
    }

public:
    CustomBoard() : boot_button_(BOOT_BUTTON_GPIO, false, 3000),
                    key_button_(KEY_BUTTON_GPIO, false, 3000) {
        const esp_timer_create_args_t timer_args = {
            .callback = FactoryResetTimerCallback,
            .arg = this,
            .dispatch_method = ESP_TIMER_TASK,
            .name = "factory-reset-hold",
            .skip_unhandled_events = true,
        };
        ESP_ERROR_CHECK(esp_timer_create(&timer_args, &factory_reset_timer_));
        InitializeI2c();  
        EnvironmentService::GetInstance().Initialize(i2c_bus_);
        InitializeButtons();     
        InitializeTools();
        InitializeLcdDisplay();
        if (!ReporterService::GetInstance().Start()) {
            ESP_LOGE(TAG, "Failed to start Reporter service");
        }
        if (!ApiBalanceService::GetInstance().Start()) {
            ESP_LOGE(TAG, "Failed to start API balance service");
        }
   }

    virtual AudioCodec* GetAudioCodec() override {
        ESP_LOGI(TAG, "ES7210 microphone gain: %.1f dB", (double)AUDIO_INPUT_GAIN_DB);
        static BoxAudioCodec audio_codec(
            i2c_bus_, 
            AUDIO_INPUT_SAMPLE_RATE, 
            AUDIO_OUTPUT_SAMPLE_RATE,
            AUDIO_I2S_GPIO_MCLK, 
            AUDIO_I2S_GPIO_BCLK, 
            AUDIO_I2S_GPIO_WS, 
            AUDIO_I2S_GPIO_DOUT, 
            AUDIO_I2S_GPIO_DIN,
            AUDIO_CODEC_PA_PIN, 
            AUDIO_CODEC_ES8311_ADDR, 
            AUDIO_CODEC_ES7210_ADDR, 
            AUDIO_INPUT_REFERENCE,
            AUDIO_INPUT_GAIN_DB);
        return &audio_codec;
    }

    virtual Display* GetDisplay() override {
        return display_;
    }

    virtual bool GetBatteryLevel(int &level, bool& charging, bool& discharging) override {
        charging = false;
        discharging = !charging;
        level = (int)BatterygetPercent();

        return true;
    }
};

DECLARE_BOARD(CustomBoard);
