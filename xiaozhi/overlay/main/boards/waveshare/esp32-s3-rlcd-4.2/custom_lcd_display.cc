#include <vector>
#include <cstring>
#include <freertos/FreeRTOS.h>
#include <esp_lcd_panel_io.h>
#include <esp_log.h>
#include <esp_err.h>
#include <esp_wifi.h>
#include "custom_lcd_display.h"
#include "lcd_display.h"
#include "esp_lvgl_port.h"
#include "assets/lang_config.h"
#include "settings.h"
#include "config.h"
#include "board.h"
#include "application.h"
#include "reporter_service.h"
#include "todo_service.h"
#include "api_balance_service.h"
#include "environment_service.h"
#include "ui.h"

void CustomLcdDisplay::Lvgl_flush_cb(lv_display_t * disp, const lv_area_t * area, uint8_t * color_p)
{
    assert(disp != NULL);
    CustomLcdDisplay *Disp = (CustomLcdDisplay *)lv_display_get_user_data(disp);
    uint16_t *buffer = (uint16_t *)color_p;
  	for(int y = area->y1; y <= area->y2; y++)
  	{
  	 	for(int x = area->x1; x <= area->x2; x++) 
  	 	{
  	 	   	uint8_t color = (*buffer < 0x7fff) ? ColorBlack : ColorWhite;
  	 	   	Disp->RLCD_SetPixel(x,y,color);
  	 	   	buffer++;
  	 	}
	}
	Disp->RLCD_Display();
	// esp_lcd_panel_io_tx_color() is asynchronous.  The LVGL draw buffer and
	// the shared 1-bit panel buffer must not be reused until the SPI DMA
	// transaction really finishes.  on_color_trans_done below releases LVGL.
}

CustomLcdDisplay::CustomLcdDisplay(esp_lcd_panel_io_handle_t panel_io,
esp_lcd_panel_handle_t panel,
int width, 
int height, 
int offset_x, 
int offset_y,
bool mirror_x, 
bool mirror_y, 
bool swap_xy,
spi_display_config_t spiconfig,
spi_host_device_t spi_host) : LcdDisplay(panel_io, panel, width, height),
mosi_(spiconfig.mosi),
scl_(spiconfig.scl), 
dc_(spiconfig.dc), 
cs_(spiconfig.cs), 
rst_(spiconfig.rst), 
width_(width), 
height_(height)
{
	ESP_LOGI(TAG, "Initialize SPI");
	esp_err_t        ret;
    spi_bus_config_t buscfg   = {};
    int              transfer = width_ * height_;
    buscfg.miso_io_num                   = -1;
    buscfg.mosi_io_num                   = mosi_;
    buscfg.sclk_io_num                   = scl_;
    buscfg.quadwp_io_num                 = -1;
    buscfg.quadhd_io_num                 = -1;
    buscfg.max_transfer_sz               = transfer;
    ret                                  = spi_bus_initialize(spi_host, &buscfg, SPI_DMA_CH_AUTO);
    ESP_ERROR_CHECK(ret);
    esp_lcd_panel_io_spi_config_t io_config = {};
    io_config.dc_gpio_num = static_cast<gpio_num_t>(dc_);
    io_config.cs_gpio_num = static_cast<gpio_num_t>(cs_);
    io_config.pclk_hz = 40 * 1000 * 1000;
    io_config.lcd_cmd_bits = 8;
    io_config.lcd_param_bits = 8;
    io_config.spi_mode = 0;
    io_config.trans_queue_depth = 2;
    io_config.on_color_trans_done =
        [](esp_lcd_panel_io_handle_t,
           esp_lcd_panel_io_event_data_t *,
           void *user_ctx) -> bool {
            auto *self = static_cast<CustomLcdDisplay *>(user_ctx);
            if (self != nullptr && self->display_ != nullptr) {
                lv_display_flush_ready(self->display_);
            }
            return false;
        };
    io_config.user_ctx = this;
    ESP_ERROR_CHECK(esp_lcd_new_panel_io_spi((esp_lcd_spi_bus_handle_t)spi_host, &io_config, &io_handle));
    gpio_config_t gpio_conf = {};
    gpio_conf.intr_type     = GPIO_INTR_DISABLE;
    gpio_conf.mode          = GPIO_MODE_OUTPUT;
    gpio_conf.pin_bit_mask  = (0x1ULL << rst_);
    gpio_conf.pull_down_en  = GPIO_PULLDOWN_DISABLE;
    gpio_conf.pull_up_en    = GPIO_PULLUP_ENABLE;
    ESP_ERROR_CHECK_WITHOUT_ABORT(gpio_config(&gpio_conf));
    Set_ResetIOLevel(1);

    DisplayLen                = transfer >> 3; //(1byte 8ipex)
    DispBuffer                = (uint8_t *) heap_caps_malloc(DisplayLen, MALLOC_CAP_SPIRAM);
    assert(DispBuffer);
	PixelIndexLUT = (uint16_t (*)[300])heap_caps_malloc(transfer * sizeof(uint16_t), MALLOC_CAP_SPIRAM);
	PixelBitLUT   = (uint8_t (*)[300])heap_caps_malloc(transfer * sizeof(uint8_t), MALLOC_CAP_SPIRAM);
    assert(PixelIndexLUT);
    assert(PixelBitLUT);
    if(width_ == 400) {
        InitLandscapeLUT();
    } else {
        InitPortraitLUT();
    }

    ESP_LOGI(TAG, "Initialize LVGL library");
    lv_init();
    lvgl_port_cfg_t port_cfg = ESP_LVGL_PORT_INIT_CONFIG();
    port_cfg.task_priority   = 2;
    port_cfg.timer_period_ms = 50;
    lvgl_port_init(&port_cfg);
    lvgl_port_lock(0);

    display_ = lv_display_create(width, height); /* 以水平和垂直分辨率（像素）进行基本初始化 */
    lv_display_set_flush_cb(display_, Lvgl_flush_cb);
    lv_display_set_user_data(display_, this);
	size_t lvgl_buffer_size = LV_COLOR_FORMAT_GET_SIZE(LV_COLOR_FORMAT_RGB565) * transfer;
	uint8_t *lvgl_buffer1 = (uint8_t *) heap_caps_malloc(lvgl_buffer_size, MALLOC_CAP_SPIRAM);
    assert(lvgl_buffer1);
	lv_display_set_buffers(display_, lvgl_buffer1, NULL, lvgl_buffer_size, LV_DISPLAY_RENDER_MODE_PARTIAL);

    ESP_LOGI(TAG, "RLCD init");
    RLCD_Init();

    lvgl_port_unlock();
    if (display_ == nullptr) {
        ESP_LOGE(TAG, "Failed to add display");
        return;
    }

    // Note: SetupUI() should be called by Application::Initialize(), not in constructor
    // to ensure lvgl objects are created after the display is fully initialized.
}

CustomLcdDisplay::~CustomLcdDisplay() {
}

void CustomLcdDisplay::SetupUI() {
    /* This board owns the complete LVGL object tree.  Calling the stock LCD
     * implementation here would leave a second hidden tree whose font objects
     * become stale when the downloaded theme is refreshed after Wi-Fi joins. */
    Display::SetupUI();
    DisplayLockGuard lock(this);
    ui_init();
    ui_update_agent_state("OFFLINE");
    ui_update_api_balance("API", "--");
    ui_update_codex_quota(-1, -1, false, false);
    ui_update_media(false, "stopped", "", "", 0, 0, "");
    ui_update_performance(0, 0, 0, false, 0, 0, false, 0, false,
                          0, 0, 0, false);
    ui_update_pc_connected(false);
    ui_update_wifi_state(UI_WIFI_CONNECTING);
    panel_ui_ready_ = true;
}

void CustomLcdDisplay::SetTheme(Theme *theme) {
    /* Keep the official theme/resource state in sync without applying it to
     * the custom object tree.  Our fonts and styles have their own lifetime. */
    Display::SetTheme(theme);
}

void CustomLcdDisplay::NextPanelPage() {
    if (!panel_ui_ready_) return;
    DisplayLockGuard lock(this);
    ui_toggle_page();
}

bool CustomLcdDisplay::ShowPanelPage(const std::string& page) {
    if (!panel_ui_ready_) return false;
    DisplayLockGuard lock(this);
    if (page == "dashboard") ui_show_dashboard();
    else if (page == "performance") ui_show_performance();
    else if (page == "syna") ui_show_syna();
    else if (page == "computers") ui_show_computers();
    else return false;
    return true;
}

void CustomLcdDisplay::HandlePanelKeyShortPress() {
    if (!panel_ui_ready_) return;
    DisplayLockGuard lock(this);
    if (ui_is_computer_page()) ui_select_computer(1);
    else ui_toggle_page();
}

void CustomLcdDisplay::ToggleComputerPicker() {
    if (!panel_ui_ready_) return;
    DisplayLockGuard lock(this);
    if (ui_is_computer_page()) ui_show_dashboard();
    else ui_show_computers();
}

bool CustomLcdDisplay::ConfirmComputerPicker() {
    if (!panel_ui_ready_) return false;
    int selected = -1;
    {
        DisplayLockGuard lock(this);
        if (!ui_is_computer_page()) return false;
        selected = ui_confirm_computer();
    }
    if (selected >= 0) ReporterService::GetInstance().RequestSelection(selected);
    // Empty lists consume BOOT too: choosing a computer must remain silent.
    return true;
}

void CustomLcdDisplay::SetStatus(const char *status) {
    (void)status;
    if (!panel_ui_ready_) return;

    DisplayLockGuard lock(this);
    switch (Application::GetInstance().GetDeviceState()) {
        case kDeviceStateListening:
            ui_show_assistant_overlay("Syna-sama", "正在聆听…");
            break;
        case kDeviceStateSpeaking:
            ui_show_assistant_overlay("Syna-sama", "正在回答…");
            break;
        case kDeviceStateIdle:
            ui_hide_assistant_overlay();
            break;
        default:
            break;
    }
}

void CustomLcdDisplay::SetChatMessage(const char *role, const char *content) {
    if (!panel_ui_ready_ || role == nullptr || content == nullptr || content[0] == '\0') {
        return;
    }

    DisplayLockGuard lock(this);
    if (strcmp(role, "user") == 0) {
        ui_update_syna_conversation(content, nullptr);
        ui_show_assistant_overlay("你", content);
    } else if (strcmp(role, "assistant") == 0) {
        ui_update_syna_conversation(nullptr, content);
        ui_show_assistant_overlay("Syna-sama", content);
    }
}

void CustomLcdDisplay::UpdateStatusBar(bool update_all) {
    (void)update_all;
    if (!panel_ui_ready_) return;

    wifi_ap_record_t ap_info = {};
    ui_wifi_state_t wifi_state = UI_WIFI_CONNECTING;
    const auto device_state = Application::GetInstance().GetDeviceState();
    if (device_state == kDeviceStateWifiConfiguring) {
        wifi_state = UI_WIFI_PROVISIONING;
    } else if (esp_wifi_sta_get_ap_info(&ap_info) == ESP_OK) {
        wifi_state = UI_WIFI_CONNECTED;
    }

    float temperature_c = 0.0f;
    float humidity_percent = 0.0f;
    const bool environment_valid = EnvironmentService::GetInstance().GetReadings(
        temperature_c, humidity_percent);
    int battery_level = 0;
    bool charging = false;
    bool discharging = false;
    const bool battery_valid =
        Board::GetInstance().GetBatteryLevel(battery_level, charging, discharging);

    PanelReporterSnapshot reporter = {};
    const bool reporter_available =
        ReporterService::GetInstance().GetSnapshot(reporter);
    const bool reporter_changed = reporter_available &&
                                  reporter.generation != reporter_generation_;
    PanelTodoSnapshot todos = {};
    const bool todos_available = TodoService::GetInstance().GetSnapshot(todos);
    const bool todos_changed = todos_available &&
                               todos.generation != todo_generation_;
    PanelApiBalanceSnapshot api_balance = {};
    const bool api_balance_available =
        ApiBalanceService::GetInstance().GetSnapshot(api_balance);
    const bool api_balance_changed = api_balance_available &&
        api_balance.generation != api_balance_generation_;

    DisplayLockGuard lock(this);
    ui_update_clock();
    ui_update_wifi_state(wifi_state);
    ui_update_environment(temperature_c, humidity_percent, battery_level,
                          environment_valid, battery_valid);

    if (reporter_changed) {
        ui_computer_info_t computers[kPanelMaxReporters] = {};
        for (int index = 0; index < reporter.device_count; ++index) {
            snprintf(computers[index].name, sizeof(computers[index].name), "%s",
                     reporter.devices[index].computer_name);
            snprintf(computers[index].agent_state,
                     sizeof(computers[index].agent_state), "%s",
                     reporter.devices[index].agent_state);
            computers[index].online = reporter.devices[index].online;
        }
        ui_update_computer_list(computers, reporter.device_count,
                                reporter.current_index);

        const PanelReporterMetrics& metrics = reporter.metrics;
        ui_update_pc_connected(metrics.connected);
        ui_update_agent_state(metrics.connected ? metrics.agent_state : "OFFLINE");
        ui_update_codex_quota(metrics.codex_short_remaining,
                              metrics.codex_week_remaining,
                              metrics.connected, metrics.codex_quota_stale);
        ui_update_media(metrics.connected && metrics.media_available,
                        metrics.media_status, metrics.media_title,
                        metrics.media_artist,
                        static_cast<int>(metrics.media_position_seconds),
                        static_cast<int>(metrics.media_duration_seconds),
                        metrics.media_lyric);
        ui_update_performance(
            metrics.cpu_percent, metrics.memory_percent,
            metrics.gpu_percent, metrics.gpu_valid,
            metrics.disk_percent, metrics.cpu_temperature_c,
            metrics.cpu_temperature_valid, metrics.gpu_temperature_c,
            metrics.gpu_temperature_valid,
            static_cast<int>(metrics.latency_ms),
            metrics.upload_bytes_per_second / (1024.0f * 1024.0f),
            metrics.download_bytes_per_second / (1024.0f * 1024.0f),
            metrics.connected);
        reporter_generation_ = reporter.generation;
    }
    if (todos_changed) {
        ui_todo_item_t items[kPanelMaximumTodos] = {};
        for (size_t index = 0; index < todos.count; ++index) {
            items[index].id = todos.items[index].id;
            snprintf(items[index].text, sizeof(items[index].text), "%s",
                     todos.items[index].text);
            items[index].completed = todos.items[index].completed;
        }
        ui_update_todos(items, static_cast<int>(todos.count));
        todo_generation_ = todos.generation;
    }
    if (api_balance_changed) {
        ui_update_api_balance(api_balance.provider, api_balance.display);
        api_balance_generation_ = api_balance.generation;
    }
}

void CustomLcdDisplay::InitPortraitLUT() {
    uint16_t W4 = width_ >> 2;
    for (uint16_t y = 0; y < height_; y++)
    {
        uint16_t byte_y = y >> 1;
        uint8_t  local_y = y & 1;
        for (uint16_t x = 0; x < width_; x++)
        {
            uint16_t byte_x = x >> 2;
            uint8_t  local_x = x & 3;

            uint32_t index = byte_y * W4 + byte_x;
            uint8_t bit = 7 - ((local_x << 1) | local_y);

            PixelIndexLUT[x][y] = index;
            PixelBitLUT  [x][y] = (1 << bit);
        }
    }
}

void CustomLcdDisplay::InitLandscapeLUT() {
    uint16_t H4 = height_ >> 2;
    for (uint16_t y = 0; y < height_; y++)
    {
        uint16_t inv_y = height_ - 1 - y;
        uint16_t block_y = inv_y >> 2;
        uint8_t  local_y  = inv_y & 3;
        for (uint16_t x = 0; x < width_; x++)
        {
            uint16_t byte_x = x >> 1;
            uint8_t  local_x = x & 1;

            uint32_t index = byte_x * H4 + block_y;
            uint8_t bit = 7 - ((local_y << 1) | local_x);

            PixelIndexLUT[x][y] = index;
            PixelBitLUT  [x][y] = (1 << bit);
        }
    }
}

void CustomLcdDisplay::Set_ResetIOLevel(uint8_t level) {
    gpio_set_level((gpio_num_t) rst_, level ? 1 : 0);
}

void CustomLcdDisplay::RLCD_SendCommand(uint8_t Reg) {
    ESP_ERROR_CHECK(esp_lcd_panel_io_tx_param(io_handle, Reg, NULL, 0));
}

void CustomLcdDisplay::RLCD_SendData(uint8_t Data) {
    ESP_ERROR_CHECK(esp_lcd_panel_io_tx_param(io_handle, -1, &Data, 1));
}

void CustomLcdDisplay::RLCD_Sendbuffera(uint8_t *Data, int len) {
    ESP_ERROR_CHECK(esp_lcd_panel_io_tx_color(io_handle, -1, Data, len));
}

void CustomLcdDisplay::RLCD_Reset(void) {
    Set_ResetIOLevel(1);
    vTaskDelay(pdMS_TO_TICKS(50));
    Set_ResetIOLevel(0);
    vTaskDelay(pdMS_TO_TICKS(20));
    Set_ResetIOLevel(1);
    vTaskDelay(pdMS_TO_TICKS(50));
}

void CustomLcdDisplay::RLCD_ColorClear(uint8_t color) {
    memset(DispBuffer, color, DisplayLen);
}

void CustomLcdDisplay::RLCD_Init() {
    RLCD_Reset();

    RLCD_SendCommand(0xD6);  // NVM Load Control
	RLCD_SendData(0x17);
	RLCD_SendData(0x02);

	RLCD_SendCommand(0xD1); //Booster Enable
	RLCD_SendData(0x01);

	RLCD_SendCommand(0xC0); //Gate Voltage Control
	RLCD_SendData(0x11);   
	RLCD_SendData(0x04);   

	RLCD_SendCommand(0xC1); //VSHP Setting
	RLCD_SendData(0x69);
	RLCD_SendData(0x69);
	RLCD_SendData(0x69);
	RLCD_SendData(0x69);

	RLCD_SendCommand(0xC2);
	RLCD_SendData(0x19);
	RLCD_SendData(0x19);
	RLCD_SendData(0x19);
	RLCD_SendData(0x19);

	RLCD_SendCommand(0xC4);
	RLCD_SendData(0x4B);
	RLCD_SendData(0x4B);
	RLCD_SendData(0x4B);
	RLCD_SendData(0x4B);

	RLCD_SendCommand(0xC5);
	RLCD_SendData(0x19);
	RLCD_SendData(0x19);
	RLCD_SendData(0x19);
	RLCD_SendData(0x19);

	RLCD_SendCommand(0xD8);
	RLCD_SendData(0x80);
	RLCD_SendData(0xE9);

	RLCD_SendCommand(0xB2);
	RLCD_SendData(0x02);

	RLCD_SendCommand(0xB3);
	RLCD_SendData(0xE5);
	RLCD_SendData(0xF6);
	RLCD_SendData(0x05);
	RLCD_SendData(0x46);
	RLCD_SendData(0x77);
	RLCD_SendData(0x77);
	RLCD_SendData(0x77);
	RLCD_SendData(0x77);
	RLCD_SendData(0x76);
	RLCD_SendData(0x45);

	RLCD_SendCommand(0xB4);
	RLCD_SendData(0x05);
	RLCD_SendData(0x46);
	RLCD_SendData(0x77);
	RLCD_SendData(0x77);
	RLCD_SendData(0x77);
	RLCD_SendData(0x77);
	RLCD_SendData(0x76);
	RLCD_SendData(0x45);

	RLCD_SendCommand(0x62);
	RLCD_SendData(0x32);
	RLCD_SendData(0x03);
	RLCD_SendData(0x1F);

	RLCD_SendCommand(0xB7);
	RLCD_SendData(0x13);

	RLCD_SendCommand(0xB0);
	RLCD_SendData(0x64);

	RLCD_SendCommand(0x11); 
	vTaskDelay(pdMS_TO_TICKS(200));     
	RLCD_SendCommand(0xC9);
	RLCD_SendData(0x00);

	RLCD_SendCommand(0x36);
	RLCD_SendData(0x48); 

	RLCD_SendCommand(0x3A);
	RLCD_SendData(0x11); 

	RLCD_SendCommand(0xB9);
	RLCD_SendData(0x20);

	RLCD_SendCommand(0xB8);
	RLCD_SendData(0x29);

	RLCD_SendCommand(0x21);

	RLCD_SendCommand(0x2A); 
	RLCD_SendData(0x12);
	RLCD_SendData(0x2A);

	RLCD_SendCommand(0x2B); 
	RLCD_SendData(0x00);
	RLCD_SendData(0xC7);

	RLCD_SendCommand(0x35);
	RLCD_SendData(0x00);

	RLCD_SendCommand(0xD0);
	RLCD_SendData(0xFF);

	RLCD_SendCommand(0x38);
	RLCD_SendCommand(0x29);

    RLCD_ColorClear(ColorWhite);
}

void CustomLcdDisplay::RLCD_SetPixel(uint16_t x, uint16_t y, uint8_t color) {
    uint32_t idx = PixelIndexLUT[x][y];
    uint8_t  mask = PixelBitLUT[x][y];

    uint8_t *p = &DispBuffer[idx];

    if (color)
        *p |= mask;
    else
        *p &= ~mask;
}

void CustomLcdDisplay::RLCD_Display() {
    RLCD_SendCommand(0x2A);     // Column Address Set
  	RLCD_SendData(0x12);
  	RLCD_SendData(0x2A);

  	RLCD_SendCommand(0x2B);     // Page Address Set
  	RLCD_SendData(0x00);
  	RLCD_SendData(0xC7);

  	RLCD_SendCommand(0x2c);     // Page Address Set

	RLCD_Sendbuffera(DispBuffer,DisplayLen);
}
