/* Project-specific additions Copyright (c) 2026 黑沐. MIT; upstream notices retained. */
#include "ui.h"

#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <time.h>

#include "lvgl.h"
#include "assets.h"
#include "ui_fonts.h"

typedef enum {
    PAGE_DASHBOARD,
    PAGE_PERFORMANCE,
    PAGE_SYNA,
    PAGE_COMPUTERS,
    PAGE_ABOUT,
} page_t;

typedef struct {
    const char *name;
    const char *connection;
    const char *agent_state;
    const char *task;
    const char *elapsed;
    const char *deepseek_balance;
    int codex_short_percent;
    int codex_week_percent;
} computer_t;

typedef struct {
    float cpu_percent;
    float memory_percent;
    float gpu_percent;
    float disk_percent;
    float cpu_temperature_c;
    float gpu_temperature_c;
    float upload_mb_per_second;
    float download_mb_per_second;
    int latency_ms;
    bool gpu_valid;
    bool cpu_temperature_valid;
    bool gpu_temperature_valid;
    bool connected;
} performance_state_t;

static computer_t computers[] = {
    {
        .name = "--",
        .connection = "OFFLINE",
        .agent_state = "OFFLINE",
        .task = "--",
        .elapsed = "--:--:--",
        .deepseek_balance = "--",
        .codex_short_percent = -1,
        .codex_week_percent = -1,
    },
};

#define MOCK_COMPUTER_COUNT ((int)(sizeof(computers) / sizeof(computers[0])))
#define COMPUTER_ROWS_VISIBLE 3

#define COLOR_BLACK lv_color_black()
#define COLOR_WHITE lv_color_white()

static page_t current_page = PAGE_DASHBOARD;
static int current_computer = 0;
static int current_list_computer = 0;
static int selected_computer = 0;
static int computer_list_count = 0;
static int computer_list_offset = 0;
static ui_computer_info_t computer_list[UI_MAX_COMPUTERS];

static lv_obj_t *clock_label;
static lv_obj_t *dashboard_clock_label;
static lv_obj_t *performance_clock_label;
static lv_obj_t *dashboard_temperature_label;
static lv_obj_t *dashboard_humidity_label;
static lv_obj_t *dashboard_battery_label;
static lv_obj_t *performance_battery_label;
static lv_obj_t *syna_battery_label;
static lv_obj_t *dashboard_wifi_status_image;
static lv_obj_t *performance_wifi_status_image;
static lv_obj_t *syna_wifi_status_image;
static lv_obj_t *dashboard_pc_status_image;
static lv_obj_t *performance_pc_status_image;
static lv_obj_t *syna_pc_status_image;
static lv_obj_t *dashboard_agent_status_image;
static lv_obj_t *dashboard_agent_login_label;
static lv_obj_t *dashboard_short_quota_label;
static lv_obj_t *dashboard_week_quota_label;
static lv_obj_t *dashboard_short_quota_fill;
static lv_obj_t *dashboard_week_quota_fill;
static lv_obj_t *dashboard_media_status_label;
static lv_obj_t *dashboard_media_title_label;
static lv_obj_t *dashboard_media_artist_label;
static lv_obj_t *dashboard_media_position_label;
static lv_obj_t *dashboard_media_duration_label;
static lv_obj_t *dashboard_media_lyric_label;
static lv_obj_t *dashboard_media_progress_knob;
static lv_timer_t *agent_done_blink_timer;
static lv_obj_t *performance_temperature_labels[2];
static lv_obj_t *performance_usage_labels[4];
static lv_obj_t *performance_usage_fills[4];
static lv_obj_t *performance_latency_label;
static lv_obj_t *performance_upload_label;
static lv_obj_t *performance_download_label;
static lv_obj_t *performance_network_chart;
static lv_chart_series_t *performance_network_series;
static lv_obj_t *dashboard_screen;
static lv_obj_t *performance_screen;
static lv_obj_t *syna_screen;
static lv_obj_t *syna_clock_label;
static lv_obj_t *syna_api_provider_label;
static lv_obj_t *syna_api_balance_label;
static lv_obj_t *syna_user_label;
static lv_obj_t *syna_assistant_label;
static lv_obj_t *syna_todo_count_label;
static lv_obj_t *syna_todo_images[UI_MAX_TODOS];
static lv_obj_t *syna_todo_labels[UI_MAX_TODOS];
static lv_obj_t *computers_screen;
static lv_obj_t *computer_rows[COMPUTER_ROWS_VISIBLE];
static lv_obj_t *computer_name_labels[COMPUTER_ROWS_VISIBLE];
static lv_obj_t *computer_state_labels[COMPUTER_ROWS_VISIBLE];
static lv_obj_t *computer_current_labels[COMPUTER_ROWS_VISIBLE];
static lv_obj_t *computer_found_label;
static lv_obj_t *assistant_overlay;
static lv_obj_t *assistant_overlay_label;
static bool assistant_active = false;
static char assistant_state[32] = "Syna-sama";
static char assistant_text[192] = "正在聆听…";
static char current_syna_user[160] = "";
static char current_syna_assistant[192] = "";
static char current_api_provider[32] = "API";
static char current_api_balance[48] = "--";
static ui_todo_item_t current_todos[UI_MAX_TODOS];
static int current_todo_count = 0;
static ui_wifi_state_t current_wifi_state = UI_WIFI_UNCONFIGURED;
static bool current_pc_connected = false;
static int current_battery_percent = -1;
static bool current_battery_valid = false;
static char current_agent_state[16] = "OFFLINE";
static performance_state_t current_performance_state;

static void style_screen(lv_obj_t *screen);
static lv_obj_t *make_label(lv_obj_t *parent, const char *text, const lv_font_t *font,
                            int32_t x, int32_t y);
static lv_obj_t *make_value_label(lv_obj_t *parent, const lv_font_t *font,
                                  int32_t x, int32_t y, int32_t width,
                                  int32_t height);
static lv_obj_t *make_panel(lv_obj_t *parent, int32_t x, int32_t y,
                            int32_t width, int32_t height);
static lv_obj_t *make_progress_fill(lv_obj_t *parent, int32_t y, int percent);
static lv_obj_t *make_performance_fill(lv_obj_t *parent, int32_t y, int percent);
static const lv_image_dsc_t *status_asset_for(const char *state);
static const lv_image_dsc_t *wifi_asset_for(ui_wifi_state_t state);
static const lv_image_dsc_t *pc_asset_for(bool connected);
static void agent_done_blink_cb(lv_timer_t *timer);
static void update_computer_rows(void);
static void computer_row_clicked(lv_event_t *event);
static void sync_assistant_visibility(void);
static void refresh_syna_conversation(void);
static void refresh_syna_todos(void);

static void update_battery_labels(void)
{
    char value[8];
    if(current_battery_valid) {
        int percent = current_battery_percent;
        if(percent < 0) percent = 0;
        if(percent > 100) percent = 100;
        snprintf(value, sizeof(value), "%d%%", percent);
    }
    else {
        snprintf(value, sizeof(value), "--");
    }

    lv_obj_t *labels[] = {dashboard_battery_label, performance_battery_label,
                          syna_battery_label};
    for(size_t index = 0; index < sizeof(labels) / sizeof(labels[0]); ++index) {
        if(labels[index] != NULL && lv_obj_is_valid(labels[index]) &&
           strcmp(lv_label_get_text(labels[index]), value) != 0) {
            lv_label_set_text(labels[index], value);
        }
    }
}

static int network_chart_value(float upload_mb_per_second,
                               float download_mb_per_second)
{
    float kb_per_second = (upload_mb_per_second + download_mb_per_second) * 1024.0f;
    int value;
    if(kb_per_second < 1.0f) value = 0;
    else if(kb_per_second < 10.0f) value = 8 + (int)(kb_per_second * 2.0f);
    else if(kb_per_second < 100.0f) value = 28 + (int)(kb_per_second / 5.0f);
    else if(kb_per_second < 1000.0f) value = 48 + (int)(kb_per_second / 30.0f);
    else value = 78 + (int)(kb_per_second / 500.0f);
    if(value > 100) value = 100;
    return value;
}

static void ensure_assistant_overlay(void)
{
    if(assistant_overlay != NULL && lv_obj_is_valid(assistant_overlay)) return;
    assistant_overlay = make_panel(lv_layer_top(), 10, 237, 380, 54);
    lv_obj_set_style_border_width(assistant_overlay, 2, 0);
    lv_obj_set_style_radius(assistant_overlay, 10, 0);
    assistant_overlay_label = make_label(
        assistant_overlay, "小智  正在聆听…", &ui_font_14_cjk, 12, 16);
    lv_obj_set_size(assistant_overlay_label, 354, 22);
    lv_label_set_long_mode(assistant_overlay_label, LV_LABEL_LONG_CLIP);
    lv_obj_add_flag(assistant_overlay, LV_OBJ_FLAG_HIDDEN);
}

void ui_show_assistant_overlay(const char *state, const char *text)
{
    ensure_assistant_overlay();
    assistant_active = true;
    char line[256];
    const char *prefix = (state != NULL && state[0] != '\0') ? state : "Syna-sama";
    const char *message = (text != NULL && text[0] != '\0') ? text : "正在聆听…";
    snprintf(assistant_state, sizeof(assistant_state), "%s", prefix);
    snprintf(assistant_text, sizeof(assistant_text), "%s", message);
    snprintf(line, sizeof(line), "%s  %s", prefix, message);
    lv_label_set_text(assistant_overlay_label, line);
    if(current_page == PAGE_SYNA) {
        snprintf(current_syna_assistant, sizeof(current_syna_assistant), "%s", message);
        refresh_syna_conversation();
    }
    sync_assistant_visibility();
}

void ui_hide_assistant_overlay(void)
{
    assistant_active = false;
    if(assistant_overlay != NULL && lv_obj_is_valid(assistant_overlay)) {
        lv_obj_add_flag(assistant_overlay, LV_OBJ_FLAG_HIDDEN);
    }
}

static void sync_assistant_visibility(void)
{
    if(assistant_overlay == NULL || !lv_obj_is_valid(assistant_overlay)) return;
    if(assistant_active && current_page != PAGE_SYNA) {
        lv_obj_remove_flag(assistant_overlay, LV_OBJ_FLAG_HIDDEN);
        lv_obj_move_foreground(assistant_overlay);
    }
    else {
        lv_obj_add_flag(assistant_overlay, LV_OBJ_FLAG_HIDDEN);
    }
}

static void style_screen(lv_obj_t *screen)
{
    lv_obj_remove_flag(screen, LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_set_style_bg_color(screen, COLOR_WHITE, 0);
    lv_obj_set_style_bg_opa(screen, LV_OPA_COVER, 0);
    lv_obj_set_style_text_color(screen, COLOR_BLACK, 0);
    lv_obj_set_style_pad_all(screen, 0, 0);
    lv_obj_set_style_border_width(screen, 0, 0);
}

static lv_obj_t *make_label(lv_obj_t *parent, const char *text, const lv_font_t *font,
                            int32_t x, int32_t y)
{
    lv_obj_t *label = lv_label_create(parent);
    lv_label_set_text(label, text);
    lv_obj_set_style_text_font(label, font, 0);
    lv_obj_set_style_text_color(label, COLOR_BLACK, 0);
    lv_obj_set_pos(label, x, y);
    return label;
}

static lv_obj_t *make_value_label(lv_obj_t *parent, const lv_font_t *font,
                                  int32_t x, int32_t y, int32_t width,
                                  int32_t height)
{
    lv_obj_t *label = make_label(parent, "--", font, x, y);
    lv_obj_set_size(label, width, height);
    lv_obj_set_style_bg_color(label, COLOR_WHITE, 0);
    lv_obj_set_style_bg_opa(label, LV_OPA_COVER, 0);
    lv_obj_set_style_pad_all(label, 0, 0);
    lv_obj_set_style_text_align(label, LV_TEXT_ALIGN_CENTER, 0);
    return label;
}

static lv_obj_t *make_panel(lv_obj_t *parent, int32_t x, int32_t y,
                            int32_t width, int32_t height)
{
    lv_obj_t *panel = lv_obj_create(parent);
    lv_obj_remove_flag(panel, LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_set_pos(panel, x, y);
    lv_obj_set_size(panel, width, height);
    lv_obj_set_style_radius(panel, 8, 0);
    lv_obj_set_style_bg_color(panel, COLOR_WHITE, 0);
    lv_obj_set_style_bg_opa(panel, LV_OPA_COVER, 0);
    lv_obj_set_style_border_color(panel, COLOR_BLACK, 0);
    lv_obj_set_style_border_width(panel, 1, 0);
    lv_obj_set_style_pad_all(panel, 0, 0);
    return panel;
}

static lv_obj_t *make_progress_fill(lv_obj_t *parent, int32_t y, int percent)
{
    if(percent < 0) percent = 0;
    if(percent > 100) percent = 100;

    lv_obj_t *fill = lv_obj_create(parent);
    lv_obj_remove_flag(fill, LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_set_pos(fill, 19, y);
    lv_obj_set_size(fill, (142 * percent) / 100, 11);
    lv_obj_set_style_radius(fill, 3, 0);
    lv_obj_set_style_border_width(fill, 0, 0);
    lv_obj_set_style_pad_all(fill, 0, 0);
    lv_obj_set_style_bg_color(fill, COLOR_BLACK, 0);
    lv_obj_set_style_bg_opa(fill, LV_OPA_COVER, 0);
    if(percent <= 0) lv_obj_add_flag(fill, LV_OBJ_FLAG_HIDDEN);
    return fill;
}

static lv_obj_t *make_performance_fill(lv_obj_t *parent, int32_t y, int percent)
{
    if(percent < 0) percent = 0;
    if(percent > 100) percent = 100;

    lv_obj_t *fill = lv_obj_create(parent);
    lv_obj_remove_flag(fill, LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_set_pos(fill, 18, y);
    lv_obj_set_size(fill, (150 * percent) / 100, 9);
    lv_obj_set_style_radius(fill, 0, 0);
    lv_obj_set_style_border_width(fill, 0, 0);
    lv_obj_set_style_pad_all(fill, 0, 0);
    lv_obj_set_style_bg_color(fill, COLOR_BLACK, 0);
    lv_obj_set_style_bg_opa(fill, LV_OPA_COVER, 0);
    return fill;
}

static const lv_image_dsc_t *status_asset_for(const char *state)
{
    if(strcmp(state, "WAITING") == 0) return &ui_status_waiting;
    if(strcmp(state, "DONE") == 0) return &ui_status_done;
    if(strcmp(state, "IDLE") == 0) return &ui_status_idle;
    if(strcmp(state, "OFFLINE") == 0) return &ui_status_offline;
    return &ui_status_working;
}

static void agent_done_blink_cb(lv_timer_t *timer)
{
    (void)timer;
    if(strcmp(current_agent_state, "DONE") != 0 ||
       dashboard_agent_status_image == NULL ||
       !lv_obj_is_valid(dashboard_agent_status_image)) return;

    if(lv_obj_has_flag(dashboard_agent_status_image, LV_OBJ_FLAG_HIDDEN)) {
        lv_obj_remove_flag(dashboard_agent_status_image, LV_OBJ_FLAG_HIDDEN);
    }
    else {
        lv_obj_add_flag(dashboard_agent_status_image, LV_OBJ_FLAG_HIDDEN);
    }
}

static const lv_image_dsc_t *wifi_asset_for(ui_wifi_state_t state)
{
    switch(state) {
        case UI_WIFI_CONNECTED: return &ui_wifi_connected;
        case UI_WIFI_CONNECTING: return &ui_wifi_connecting;
        case UI_WIFI_PROVISIONING: return &ui_wifi_provisioning;
        default: return &ui_wifi_unconfigured;
    }
}

static const lv_image_dsc_t *pc_asset_for(bool connected)
{
    return connected ? &ui_pc_connected : &ui_pc_disconnected;
}

static lv_obj_t *make_white_mask(lv_obj_t *parent, int x, int y, int width, int height)
{
    lv_obj_t *mask = lv_obj_create(parent);
    lv_obj_remove_flag(mask, LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_set_pos(mask, x, y);
    lv_obj_set_size(mask, width, height);
    lv_obj_set_style_radius(mask, 0, 0);
    lv_obj_set_style_border_width(mask, 0, 0);
    lv_obj_set_style_pad_all(mask, 0, 0);
    lv_obj_set_style_bg_color(mask, COLOR_WHITE, 0);
    lv_obj_set_style_bg_opa(mask, LV_OPA_COVER, 0);
    return mask;
}

void ui_show_dashboard(void)
{
    current_page = PAGE_DASHBOARD;
    sync_assistant_visibility();
    if(dashboard_screen != NULL) {
        clock_label = dashboard_clock_label;
        lv_screen_load(dashboard_screen);
        ui_update_clock();
        return;
    }

    lv_obj_t *screen = lv_obj_create(NULL);
    dashboard_screen = screen;
    style_screen(screen);
    const computer_t *computer = &computers[current_computer];

    lv_obj_t *base = lv_image_create(screen);
    lv_image_set_src(base, &ui_screen_base);
    lv_obj_set_pos(base, 0, 0);

    clock_label = make_label(screen, "--:--", &lv_font_montserrat_42, 40, 9);
    dashboard_clock_label = clock_label;
    lv_obj_set_width(clock_label, 129);
    lv_obj_set_style_text_align(clock_label, LV_TEXT_ALIGN_CENTER, 0);
    ui_update_clock();

    dashboard_temperature_label = make_value_label(screen, &ui_font_18_regular,
                                                    229, 31, 58, 22);
    dashboard_humidity_label = make_value_label(screen, &ui_font_18_regular,
                                                 330, 31, 56, 22);
    dashboard_battery_label = make_value_label(screen, &ui_font_11_regular,
                                                354, 268, 36, 18);
    lv_obj_set_style_text_align(dashboard_temperature_label, LV_TEXT_ALIGN_LEFT, 0);
    lv_obj_set_style_text_align(dashboard_humidity_label, LV_TEXT_ALIGN_LEFT, 0);

    dashboard_wifi_status_image = lv_image_create(screen);
    lv_image_set_src(dashboard_wifi_status_image, wifi_asset_for(current_wifi_state));
    lv_obj_set_pos(dashboard_wifi_status_image, 46, 270);
    dashboard_pc_status_image = lv_image_create(screen);
    lv_image_set_src(dashboard_pc_status_image, pc_asset_for(current_pc_connected));
    lv_obj_set_pos(dashboard_pc_status_image, 236, 270);

    /* The reference background contains the original WORKING block. Keep an
     * opaque white layer below the dynamic status image so a hidden DONE image
     * flashes to white instead of revealing that baked-in block. */
    lv_obj_t *agent_status_mask = lv_obj_create(screen);
    lv_obj_remove_flag(agent_status_mask, LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_set_pos(agent_status_mask, 46, 108);
    lv_obj_set_size(agent_status_mask, 88, 29);
    lv_obj_set_style_radius(agent_status_mask, 0, 0);
    lv_obj_set_style_border_width(agent_status_mask, 0, 0);
    lv_obj_set_style_pad_all(agent_status_mask, 0, 0);
    lv_obj_set_style_bg_color(agent_status_mask, COLOR_WHITE, 0);
    lv_obj_set_style_bg_opa(agent_status_mask, LV_OPA_COVER, 0);

    dashboard_agent_status_image = lv_image_create(screen);
    lv_image_set_src(dashboard_agent_status_image,
                     status_asset_for(current_agent_state));
    lv_obj_set_pos(dashboard_agent_status_image, 46, 108);
    dashboard_agent_login_label = make_label(
        screen, "请登录", &ui_font_14_cjk, 46, 113);
    lv_obj_set_size(dashboard_agent_login_label, 88, 20);
    lv_obj_set_style_text_align(dashboard_agent_login_label, LV_TEXT_ALIGN_CENTER, 0);
    if(strcmp(current_agent_state, "LOGIN_REQUIRED") == 0) {
        lv_obj_add_flag(dashboard_agent_status_image, LV_OBJ_FLAG_HIDDEN);
    }
    else {
        lv_obj_add_flag(dashboard_agent_login_label, LV_OBJ_FLAG_HIDDEN);
    }

    make_white_mask(screen, 221, 81, 78, 20);
    make_white_mask(screen, 255, 115, 127, 23);
    make_white_mask(screen, 276, 140, 106, 20);
    make_white_mask(screen, 268, 176, 9, 10);
    make_white_mask(screen, 192, 188, 43, 17);
    make_white_mask(screen, 347, 188, 37, 17);
    make_white_mask(screen, 190, 212, 192, 34);

    dashboard_media_status_label = make_label(
        screen, "未播放", &ui_font_14_cjk, 222, 82);
    lv_obj_set_size(dashboard_media_status_label, 77, 18);
    dashboard_media_title_label = make_label(
        screen, "网易云音乐", &ui_font_14_cjk, 257, 116);
    lv_label_set_long_mode(dashboard_media_title_label, LV_LABEL_LONG_CLIP);
    lv_obj_set_size(dashboard_media_title_label, 124, 18);
    dashboard_media_artist_label = make_label(
        screen, "--", &ui_font_14_cjk, 277, 141);
    lv_label_set_long_mode(dashboard_media_artist_label, LV_LABEL_LONG_CLIP);
    lv_obj_set_size(dashboard_media_artist_label, 104, 18);
    dashboard_media_position_label = make_label(
        screen, "--:--", &ui_font_11_regular, 193, 189);
    dashboard_media_duration_label = make_label(
        screen, "--:--", &ui_font_11_regular, 349, 189);
    lv_obj_set_width(dashboard_media_duration_label, 34);
    lv_obj_set_style_text_align(dashboard_media_duration_label, LV_TEXT_ALIGN_RIGHT, 0);
    dashboard_media_lyric_label = make_label(
        screen, "暂无歌词", &ui_font_14_cjk, 191, 216);
    lv_label_set_long_mode(dashboard_media_lyric_label, LV_LABEL_LONG_CLIP);
    lv_obj_set_size(dashboard_media_lyric_label, 190, 20);
    lv_obj_set_style_text_align(dashboard_media_lyric_label, LV_TEXT_ALIGN_CENTER, 0);

    for(int dot = 0; dot < 3; ++dot) {
        lv_obj_t *progress_patch = lv_obj_create(screen);
        lv_obj_remove_flag(progress_patch, LV_OBJ_FLAG_SCROLLABLE);
        lv_obj_set_pos(progress_patch, 269 + dot * 3, 180);
        lv_obj_set_size(progress_patch, 2, 1);
        lv_obj_set_style_radius(progress_patch, 0, 0);
        lv_obj_set_style_border_width(progress_patch, 0, 0);
        lv_obj_set_style_pad_all(progress_patch, 0, 0);
        lv_obj_set_style_bg_color(progress_patch, COLOR_BLACK, 0);
        lv_obj_set_style_bg_opa(progress_patch, LV_OPA_COVER, 0);
    }
    dashboard_media_progress_knob = lv_obj_create(screen);
    lv_obj_remove_flag(dashboard_media_progress_knob, LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_set_pos(dashboard_media_progress_knob, 191, 178);
    lv_obj_set_size(dashboard_media_progress_knob, 5, 5);
    lv_obj_set_style_radius(dashboard_media_progress_knob, LV_RADIUS_CIRCLE, 0);
    lv_obj_set_style_border_width(dashboard_media_progress_knob, 0, 0);
    lv_obj_set_style_pad_all(dashboard_media_progress_knob, 0, 0);
    lv_obj_set_style_bg_color(dashboard_media_progress_knob, COLOR_BLACK, 0);
    lv_obj_set_style_bg_opa(dashboard_media_progress_knob, LV_OPA_COVER, 0);

    char short_quota[16];
    char week_quota[16];
    if(computer->codex_short_percent >= 0) {
        snprintf(short_quota, sizeof(short_quota), "%d%%", computer->codex_short_percent);
        snprintf(week_quota, sizeof(week_quota), "%d%%", computer->codex_week_percent);
    }
    else {
        snprintf(short_quota, sizeof(short_quota), "--");
        snprintf(week_quota, sizeof(week_quota), "--");
    }

    dashboard_short_quota_fill = make_progress_fill(
        screen, 179, computer->codex_short_percent);
    dashboard_week_quota_fill = make_progress_fill(
        screen, 222, computer->codex_week_percent);
    dashboard_short_quota_label = make_label(
        screen, short_quota, &ui_font_18_regular, 106, 156);
    lv_obj_set_size(dashboard_short_quota_label, 57, 22);
    lv_label_set_long_mode(dashboard_short_quota_label, LV_LABEL_LONG_CLIP);
    lv_obj_set_style_text_align(dashboard_short_quota_label, LV_TEXT_ALIGN_RIGHT, 0);

    dashboard_week_quota_label = make_label(
        screen, week_quota, &ui_font_18_regular, 106, 199);
    lv_obj_set_size(dashboard_week_quota_label, 57, 22);
    lv_label_set_long_mode(dashboard_week_quota_label, LV_LABEL_LONG_CLIP);
    lv_obj_set_style_text_align(dashboard_week_quota_label, LV_TEXT_ALIGN_RIGHT, 0);
    lv_screen_load(screen);
}

void ui_show_performance(void)
{
    current_page = PAGE_PERFORMANCE;
    sync_assistant_visibility();
    if(performance_screen != NULL) {
        clock_label = performance_clock_label;
        lv_screen_load(performance_screen);
        ui_update_clock();
        return;
    }

    lv_obj_t *screen = lv_obj_create(NULL);
    performance_screen = screen;
    style_screen(screen);
    lv_obj_t *base = lv_image_create(screen);
    lv_image_set_src(base, &ui_performance_base);
    lv_obj_set_pos(base, 0, 0);

    clock_label = make_label(screen, "--:--", &lv_font_montserrat_38, 47, 8);
    performance_clock_label = clock_label;
    lv_label_set_long_mode(clock_label, LV_LABEL_LONG_CLIP);
    lv_obj_set_size(clock_label, 108, 44);
    lv_obj_set_style_text_align(clock_label, LV_TEXT_ALIGN_CENTER, 0);
    ui_update_clock();

    performance_temperature_labels[0] =
        make_value_label(screen, &ui_font_18_regular, 200, 31, 59, 22);
    performance_temperature_labels[1] =
        make_value_label(screen, &ui_font_18_regular, 318, 31, 60, 22);
    lv_obj_set_style_text_align(performance_temperature_labels[0], LV_TEXT_ALIGN_LEFT, 0);
    lv_obj_set_style_text_align(performance_temperature_labels[1], LV_TEXT_ALIGN_LEFT, 0);

    const int usage[] = {0, 0, 0, 0};
    const int bar_y[] = {119, 158, 198, 237};
    const int label_y[] = {94, 134, 173, 213};
    // The metric names are baked into the base image. Move only their ink
    // rectangles, preserving the original glyphs and stationary bar outlines.
    const int name_y[] = {106, 146, 185, 224};
    const int name_height[] = {8, 9, 8, 9};
    for(int i = 0; i < 4; ++i) {
        lv_obj_t *mask = make_white_mask(screen, 17, name_y[i] - 2,
                                         68, name_height[i] + 2);
        lv_obj_t *clip = make_white_mask(mask, 0, 0, 68, name_height[i]);
        lv_obj_t *name = lv_image_create(clip);
        lv_image_set_src(name, &ui_performance_base);
        lv_obj_set_pos(name, -17, -name_y[i]);
    }
    for(int i = 0; i < 4; ++i) {
        char percent[8];
        snprintf(percent, sizeof(percent), "%d%%", usage[i]);
        lv_obj_t *value = make_label(screen, percent, &ui_font_18_regular,
                                     116, label_y[i]);
        performance_usage_labels[i] = value;
        lv_obj_set_size(value, 52, 22);
        lv_label_set_long_mode(value, LV_LABEL_LONG_CLIP);
        lv_obj_set_style_text_align(value, LV_TEXT_ALIGN_RIGHT, 0);
        performance_usage_fills[i] = make_performance_fill(screen, bar_y[i], usage[i]);
    }

    lv_obj_t *latency = make_label(screen, "12 ms", &ui_font_11_regular, 334, 124);
    performance_latency_label = latency;
    lv_obj_set_width(latency, 47);
    lv_obj_set_style_text_align(latency, LV_TEXT_ALIGN_RIGHT, 0);
    lv_obj_t *upload = make_label(screen, "2.4 MB/s", &ui_font_11_regular, 321, 146);
    performance_upload_label = upload;
    lv_obj_set_width(upload, 60);
    lv_obj_set_style_text_align(upload, LV_TEXT_ALIGN_RIGHT, 0);
    lv_obj_t *download = make_label(screen, "18.7 MB/s", &ui_font_11_regular, 314, 168);
    performance_download_label = download;
    lv_obj_set_width(download, 67);
    lv_obj_set_style_text_align(download, LV_TEXT_ALIGN_RIGHT, 0);

    performance_network_chart = lv_chart_create(screen);
    lv_obj_set_pos(performance_network_chart, 200, 191);
    lv_obj_set_size(performance_network_chart, 182, 48);
    lv_obj_set_style_bg_color(performance_network_chart, COLOR_WHITE, 0);
    lv_obj_set_style_bg_opa(performance_network_chart, LV_OPA_COVER, 0);
    lv_obj_set_style_border_width(performance_network_chart, 0, 0);
    lv_obj_set_style_radius(performance_network_chart, 0, 0);
    lv_obj_set_style_pad_all(performance_network_chart, 0, 0);
    lv_obj_set_style_line_width(performance_network_chart, 1, LV_PART_ITEMS);
    lv_obj_set_style_size(performance_network_chart, 0, 0, LV_PART_INDICATOR);
    lv_chart_set_type(performance_network_chart, LV_CHART_TYPE_LINE);
    lv_chart_set_div_line_count(performance_network_chart, 0, 0);
    lv_chart_set_point_count(performance_network_chart, 32);
    lv_chart_set_range(performance_network_chart, LV_CHART_AXIS_PRIMARY_Y, 0, 100);
    performance_network_series = lv_chart_add_series(
        performance_network_chart, COLOR_BLACK, LV_CHART_AXIS_PRIMARY_Y);
    for(int i = 0; i < 32; ++i) {
        lv_chart_set_next_value(performance_network_chart,
                                performance_network_series, 0);
    }

    make_white_mask(screen, 354, 268, 36, 18);
    performance_battery_label = make_value_label(
        screen, &ui_font_11_regular, 354, 268, 36, 18);
    update_battery_labels();
    performance_wifi_status_image = lv_image_create(screen);
    lv_image_set_src(performance_wifi_status_image, wifi_asset_for(current_wifi_state));
    lv_obj_set_pos(performance_wifi_status_image, 46, 270);
    performance_pc_status_image = lv_image_create(screen);
    lv_image_set_src(performance_pc_status_image, pc_asset_for(current_pc_connected));
    lv_obj_set_pos(performance_pc_status_image, 236, 270);
    ui_update_performance(
        current_performance_state.cpu_percent,
        current_performance_state.memory_percent,
        current_performance_state.gpu_percent,
        current_performance_state.gpu_valid,
        current_performance_state.disk_percent,
        current_performance_state.cpu_temperature_c,
        current_performance_state.cpu_temperature_valid,
        current_performance_state.gpu_temperature_c,
        current_performance_state.gpu_temperature_valid,
        current_performance_state.latency_ms,
        current_performance_state.upload_mb_per_second,
        current_performance_state.download_mb_per_second,
        current_performance_state.connected);
    lv_screen_load(screen);
}

static void refresh_syna_conversation(void)
{
    if(syna_user_label != NULL && lv_obj_is_valid(syna_user_label)) {
        char text[192];
        snprintf(text, sizeof(text), "你\n%s", current_syna_user[0] ? current_syna_user : "…");
        lv_label_set_text(syna_user_label, text);
    }
    if(syna_assistant_label != NULL && lv_obj_is_valid(syna_assistant_label)) {
        char text[224];
        snprintf(text, sizeof(text), "Syna\n%s",
                 current_syna_assistant[0] ? current_syna_assistant : "…");
        lv_label_set_text(syna_assistant_label, text);
    }
}

static void refresh_syna_todos(void)
{
    int completed = 0;
    for(int index = 0; index < current_todo_count; ++index) {
        if(current_todos[index].completed) ++completed;
    }
    if(syna_todo_count_label != NULL && lv_obj_is_valid(syna_todo_count_label)) {
        char count[24];
        snprintf(count, sizeof(count), "%d/%d", completed, current_todo_count);
        lv_label_set_text(syna_todo_count_label, count);
    }
    for(int index = 0; index < UI_MAX_TODOS; ++index) {
        if(syna_todo_images[index] == NULL || syna_todo_labels[index] == NULL) continue;
        if(index < current_todo_count) {
            lv_image_set_src(syna_todo_images[index], current_todos[index].completed
                                 ? &ui_syna_todo_checked
                                 : &ui_syna_todo_unchecked);
            lv_label_set_text(syna_todo_labels[index], current_todos[index].text);
            lv_obj_remove_flag(syna_todo_images[index], LV_OBJ_FLAG_HIDDEN);
            lv_obj_remove_flag(syna_todo_labels[index], LV_OBJ_FLAG_HIDDEN);
        }
        else {
            lv_obj_add_flag(syna_todo_images[index], LV_OBJ_FLAG_HIDDEN);
            lv_obj_add_flag(syna_todo_labels[index], LV_OBJ_FLAG_HIDDEN);
        }
    }
}

void ui_show_syna(void)
{
    current_page = PAGE_SYNA;
    sync_assistant_visibility();
    if(syna_screen != NULL) {
        clock_label = syna_clock_label;
        refresh_syna_conversation();
        refresh_syna_todos();
        lv_screen_load(syna_screen);
        ui_update_clock();
        return;
    }

    lv_obj_t *screen = lv_obj_create(NULL);
    syna_screen = screen;
    style_screen(screen);
    lv_obj_t *base = lv_image_create(screen);
    lv_image_set_src(base, &ui_syna_base);
    lv_obj_set_pos(base, 0, 0);

    clock_label = make_label(screen, "--:--", &lv_font_montserrat_42, 40, 9);
    syna_clock_label = clock_label;
    lv_obj_set_width(clock_label, 129);
    lv_obj_set_style_text_align(clock_label, LV_TEXT_ALIGN_CENTER, 0);

    lv_obj_t *wallet = lv_image_create(screen);
    lv_image_set_src(wallet, &ui_syna_wallet);
    lv_obj_set_pos(wallet, 207, 28);
    syna_api_provider_label = make_label(screen, current_api_provider,
                                         &ui_font_11_regular, 243, 33);
    lv_obj_set_size(syna_api_provider_label, 63, 17);
    lv_label_set_long_mode(syna_api_provider_label, LV_LABEL_LONG_CLIP);
    syna_api_balance_label = make_label(screen, current_api_balance,
                                        &ui_font_11_regular, 306, 33);
    lv_obj_set_size(syna_api_balance_label, 77, 17);
    lv_label_set_long_mode(syna_api_balance_label, LV_LABEL_LONG_CLIP);
    lv_obj_set_style_text_align(syna_api_balance_label, LV_TEXT_ALIGN_RIGHT, 0);

    lv_obj_t *speech = lv_image_create(screen);
    lv_image_set_src(speech, &ui_syna_speech);
    lv_obj_set_pos(speech, 17, 79);
    lv_obj_t *todo_header = lv_image_create(screen);
    lv_image_set_src(todo_header, &ui_syna_todo_checked);
    lv_obj_set_pos(todo_header, 220, 80);
    syna_todo_count_label = make_label(screen, "0/0", &ui_font_11_regular, 350, 81);
    lv_obj_set_size(syna_todo_count_label, 32, 17);
    lv_obj_set_style_text_align(syna_todo_count_label, LV_TEXT_ALIGN_RIGHT, 0);

    lv_obj_t *user_bubble = make_panel(screen, 43, 111, 150, 48);
    lv_obj_set_style_radius(user_bubble, 7, 0);
    syna_user_label = make_label(user_bubble, "", &ui_font_14_cjk, 7, 3);
    lv_obj_set_size(syna_user_label, 136, 42);
    lv_label_set_long_mode(syna_user_label, LV_LABEL_LONG_WRAP);
    lv_obj_set_style_text_line_space(syna_user_label, 0, 0);

    lv_obj_t *assistant_bubble = make_panel(screen, 17, 167, 166, 70);
    lv_obj_set_style_radius(assistant_bubble, 7, 0);
    syna_assistant_label = make_label(assistant_bubble, "", &ui_font_14_cjk, 7, 3);
    lv_obj_set_size(syna_assistant_label, 152, 62);
    lv_label_set_long_mode(syna_assistant_label, LV_LABEL_LONG_WRAP);
    lv_obj_set_style_text_line_space(syna_assistant_label, 0, 0);

    for(int index = 0; index < UI_MAX_TODOS; ++index) {
        const int y = 114 + index * 31;
        syna_todo_images[index] = lv_image_create(screen);
        lv_image_set_src(syna_todo_images[index], &ui_syna_todo_unchecked);
        lv_obj_set_pos(syna_todo_images[index], 221, y);
        syna_todo_labels[index] = make_label(screen, "", &ui_font_14_cjk, 243, y - 2);
        lv_obj_set_size(syna_todo_labels[index], 138, 22);
        lv_label_set_long_mode(syna_todo_labels[index], LV_LABEL_LONG_CLIP);
    }

    make_white_mask(screen, 354, 268, 36, 18);
    syna_battery_label = make_value_label(screen, &ui_font_11_regular,
                                          354, 268, 36, 18);
    syna_wifi_status_image = lv_image_create(screen);
    lv_image_set_src(syna_wifi_status_image, wifi_asset_for(current_wifi_state));
    lv_obj_set_pos(syna_wifi_status_image, 46, 270);
    syna_pc_status_image = lv_image_create(screen);
    lv_image_set_src(syna_pc_status_image, pc_asset_for(current_pc_connected));
    lv_obj_set_pos(syna_pc_status_image, 236, 270);

    refresh_syna_conversation();
    refresh_syna_todos();
    update_battery_labels();
    ui_update_clock();
    lv_screen_load(screen);
}

void ui_show_computers(void)
{
    current_page = PAGE_COMPUTERS;
    sync_assistant_visibility();
    selected_computer = current_list_computer >= 0 ? current_list_computer : 0;
    clock_label = NULL;
    if(computers_screen != NULL) {
        update_computer_rows();
        lv_screen_load(computers_screen);
        return;
    }

    lv_obj_t *screen = lv_obj_create(NULL);
    computers_screen = screen;
    style_screen(screen);

    lv_obj_t *frame = make_panel(screen, 0, 0, 400, 300);
    lv_obj_set_style_radius(frame, 0, 0);

    lv_obj_t *header = make_panel(screen, 6, 7, 388, 44);
    make_label(header, "SELECT COMPUTER", &ui_font_18_regular, 14, 9);
    computer_found_label = make_label(header, "0 FOUND", &ui_font_11_regular,
                                      306, 15);
    lv_obj_set_width(computer_found_label, 68);
    lv_obj_set_style_text_align(computer_found_label, LV_TEXT_ALIGN_RIGHT, 0);

    for(int i = 0; i < COMPUTER_ROWS_VISIBLE; ++i) {
        int32_t row_y = 57 + i * 59;
        lv_obj_t *row = make_panel(screen, 6, row_y, 388, 53);
        lv_obj_add_flag(row, LV_OBJ_FLAG_CLICKABLE);
        lv_obj_add_event_cb(row, computer_row_clicked, LV_EVENT_CLICKED,
                            (void *)(uintptr_t)i);

        computer_rows[i] = row;
        /* Keep Latin at 18 px; use the existing native CJK glyphs for names. */
        static lv_font_t computer_name_font;
        computer_name_font = ui_font_18_regular;
        computer_name_font.fallback = &ui_font_14_cjk;
        computer_name_labels[i] = make_label(row, "",
                                             &computer_name_font, 14, 5);
        computer_state_labels[i] = make_label(row, "", &ui_font_11_regular, 14, 32);

        computer_current_labels[i] = make_label(row, "",
                                                &ui_font_11_regular, 314, 12);
    }

    lv_obj_t *detail_panel = make_panel(screen, 6, 234, 388, 60);
    make_label(detail_panel, "KEY  NEXT", &ui_font_11_regular, 14, 10);
    make_label(detail_panel, "BOOT CONNECT", &ui_font_11_regular, 145, 10);
    make_label(detail_panel, "HOLD KEY BACK", &ui_font_11_regular, 270, 10);

    lv_obj_t *remembered_label = make_label(
        detail_panel, "PAIRED PCS ARE REMEMBERED BY REPORTER ID",
        &ui_font_11_regular, 0, 38);
    lv_obj_set_width(remembered_label, 388);
    lv_obj_set_style_text_align(remembered_label, LV_TEXT_ALIGN_CENTER, 0);
    update_computer_rows();
    lv_screen_load(screen);
}

/* This page is cached like the other primary pages. */
static lv_obj_t *about_screen;
static void ui_show_about(void)
{
    current_page = PAGE_ABOUT;
    if(about_screen == NULL) {
        about_screen = lv_obj_create(NULL);
        style_screen(about_screen);
        make_label(about_screen, "希娜 Syna  v1.0.0", &ui_font_14_cjk, 18, 18);
        make_label(about_screen, "关于作者：黑沐", &ui_font_14_cjk, 18, 54);
        make_label(about_screen, "B站 UID: 386856267", &ui_font_14_cjk, 18, 85);
        make_label(about_screen, "QQ: 3091479711", &ui_font_14_cjk, 18, 112);
        make_label(about_screen, "github.com/heimumumu/", &ui_font_14_cjk, 18, 147);
        make_label(about_screen, "Waveshare_ESP32_RLCD", &ui_font_14_cjk, 18, 171);
        make_label(about_screen, "发布版本：仓库 Releases 页面", &ui_font_14_cjk, 18, 201);
        make_label(about_screen, "原创部分 MIT - 保留版权声明", &ui_font_14_cjk, 18, 233);
        make_label(about_screen, "感谢小智、LVGL及第三方贡献者", &ui_font_14_cjk, 18, 264);
    }
    lv_screen_load(about_screen);
}

static void dismiss_signature(lv_timer_t *timer)
{
    lv_obj_t *panel = lv_timer_get_user_data(timer);
    lv_obj_delete(panel);
    lv_timer_delete(timer);
}

static void show_startup_signature(void)
{
    lv_obj_t *panel = lv_obj_create(lv_layer_top());
    lv_obj_set_size(panel, 400, 300);
    lv_obj_set_pos(panel, 0, 0);
    style_screen(panel);
    lv_obj_t *title = make_label(panel, "希娜 Syna · 黑沐", &ui_font_28_brand, 0, 106);
    lv_obj_set_width(title, 400);
    lv_obj_set_style_text_align(title, LV_TEXT_ALIGN_CENTER, 0);
    lv_obj_t *version = make_label(panel, "v1.0.0", &ui_font_18_regular, 0, 157);
    lv_obj_set_width(version, 400);
    lv_obj_set_style_text_align(version, LV_TEXT_ALIGN_CENTER, 0);
    lv_timer_create(dismiss_signature, 2000, panel);
}

void ui_toggle_page(void)
{
    if(current_page == PAGE_DASHBOARD) ui_show_performance();
    else if(current_page == PAGE_PERFORMANCE) ui_show_syna();
    else if(current_page == PAGE_SYNA) ui_show_about();
    else ui_show_dashboard();
}

void ui_select_computer(int direction)
{
    if(current_page != PAGE_COMPUTERS) {
        ui_show_computers();
        return;
    }

    if(computer_list_count <= 0) return;
    selected_computer =
        (selected_computer + direction + computer_list_count) % computer_list_count;
    if(selected_computer < computer_list_offset) computer_list_offset = selected_computer;
    if(selected_computer >= computer_list_offset + COMPUTER_ROWS_VISIBLE) {
        computer_list_offset = selected_computer - COMPUTER_ROWS_VISIBLE + 1;
    }
    update_computer_rows();
}

int ui_confirm_computer(void)
{
    if(current_page != PAGE_COMPUTERS || computer_list_count <= 0) return -1;

    current_list_computer = selected_computer;
    if(selected_computer < MOCK_COMPUTER_COUNT) current_computer = selected_computer;
    /* Dashboard values depend on the selected computer. Recreate this one
     * screen only when that selection actually changes. */
    lv_obj_t *old_dashboard = dashboard_screen;
    dashboard_screen = NULL;
    dashboard_clock_label = NULL;
    ui_show_dashboard();
    if(old_dashboard != NULL && old_dashboard != lv_screen_active()) {
        lv_obj_delete(old_dashboard);
    }
    return current_list_computer;
}

void ui_update_computer_list(const ui_computer_info_t *items, int count,
                             int current_index)
{
    if(count < 0) count = 0;
    if(count > UI_MAX_COMPUTERS) count = UI_MAX_COMPUTERS;
    computer_list_count = count;
    for(int i = 0; i < count; ++i) computer_list[i] = items[i];

    if(current_index >= 0 && current_index < count) current_list_computer = current_index;
    else if(count == 0) current_list_computer = -1;
    if(selected_computer < 0 || selected_computer >= count) {
        selected_computer = current_list_computer >= 0 ? current_list_computer : 0;
    }
    if(selected_computer < computer_list_offset) computer_list_offset = selected_computer;
    if(selected_computer >= computer_list_offset + COMPUTER_ROWS_VISIBLE) {
        computer_list_offset = selected_computer - COMPUTER_ROWS_VISIBLE + 1;
    }
    if(computer_list_count <= COMPUTER_ROWS_VISIBLE) computer_list_offset = 0;
    if(computers_screen != NULL) update_computer_rows();
}

void ui_update_clock(void)
{
    if(clock_label == NULL || !lv_obj_is_valid(clock_label)) return;

    time_t now = time(NULL);
    struct tm *local = localtime(&now);
    if(local == NULL) return;

    char time_text[8];
    strftime(time_text, sizeof(time_text), "%H:%M", local);
    /* The screen only shows hours and minutes. Avoid invalidating a full-screen
     * monochrome render once per second when the visible text did not change. */
    if(strcmp(lv_label_get_text(clock_label), time_text) != 0) {
        lv_label_set_text(clock_label, time_text);
    }
}

void ui_update_environment(float temperature_c, float humidity_percent,
                           int battery_percent, bool environment_valid,
                           bool battery_valid)
{
    current_battery_percent = battery_percent;
    current_battery_valid = battery_valid;
    if(dashboard_temperature_label != NULL &&
       lv_obj_is_valid(dashboard_temperature_label)) {
        char value[12];
        if(environment_valid) snprintf(value, sizeof(value), "%.0f\xC2\xB0" "C", temperature_c);
        else snprintf(value, sizeof(value), "--");
        if(strcmp(lv_label_get_text(dashboard_temperature_label), value) != 0) {
            lv_label_set_text(dashboard_temperature_label, value);
        }
    }

    if(dashboard_humidity_label != NULL && lv_obj_is_valid(dashboard_humidity_label)) {
        char value[8];
        if(environment_valid) snprintf(value, sizeof(value), "%.0f%%", humidity_percent);
        else snprintf(value, sizeof(value), "--");
        if(strcmp(lv_label_get_text(dashboard_humidity_label), value) != 0) {
            lv_label_set_text(dashboard_humidity_label, value);
        }
    }

    update_battery_labels();
}

void ui_update_wifi_state(ui_wifi_state_t state)
{
    /* UpdateStatusBar runs once per second. Reassigning the same image source
     * invalidates all three page trees even when nothing changed. On the RLCD
     * this eventually leaves the main task spending long enough in
     * lv_inv_area to trip the watchdog, freezing the clock and buttons first.
     * Page constructors already use current_wifi_state, so unchanged states
     * require no LVGL work here. */
    if(current_wifi_state == state) return;
    current_wifi_state = state;
    const lv_image_dsc_t *asset = wifi_asset_for(state);
    if(dashboard_wifi_status_image != NULL &&
       lv_obj_is_valid(dashboard_wifi_status_image)) {
        lv_image_set_src(dashboard_wifi_status_image, asset);
    }
    if(performance_wifi_status_image != NULL &&
       lv_obj_is_valid(performance_wifi_status_image)) {
        lv_image_set_src(performance_wifi_status_image, asset);
    }
    if(syna_wifi_status_image != NULL && lv_obj_is_valid(syna_wifi_status_image)) {
        lv_image_set_src(syna_wifi_status_image, asset);
    }
}

void ui_update_pc_connected(bool connected)
{
    /* Reporter snapshots arrive continuously. Reassigning the same source to
     * three page trees invalidates them all and can eventually wedge LVGL. */
    if(current_pc_connected == connected) return;
    current_pc_connected = connected;
    const lv_image_dsc_t *asset = pc_asset_for(connected);
    if(dashboard_pc_status_image != NULL && lv_obj_is_valid(dashboard_pc_status_image)) {
        lv_image_set_src(dashboard_pc_status_image, asset);
    }
    if(performance_pc_status_image != NULL && lv_obj_is_valid(performance_pc_status_image)) {
        lv_image_set_src(performance_pc_status_image, asset);
    }
    if(syna_pc_status_image != NULL && lv_obj_is_valid(syna_pc_status_image)) {
        lv_image_set_src(syna_pc_status_image, asset);
    }
}

void ui_update_syna_conversation(const char *user_text,
                                 const char *assistant_reply)
{
    if(user_text != NULL) {
        snprintf(current_syna_user, sizeof(current_syna_user), "%s", user_text);
    }
    if(assistant_reply != NULL) {
        snprintf(current_syna_assistant, sizeof(current_syna_assistant), "%s",
                 assistant_reply);
    }
    refresh_syna_conversation();
}

void ui_update_api_balance(const char *provider, const char *balance)
{
    snprintf(current_api_provider, sizeof(current_api_provider), "%s",
             provider != NULL && provider[0] ? provider : "API");
    snprintf(current_api_balance, sizeof(current_api_balance), "%s",
             balance != NULL && balance[0] ? balance : "--");
    if(syna_api_provider_label != NULL && lv_obj_is_valid(syna_api_provider_label)) {
        lv_label_set_text(syna_api_provider_label, current_api_provider);
    }
    if(syna_api_balance_label != NULL && lv_obj_is_valid(syna_api_balance_label)) {
        lv_label_set_text(syna_api_balance_label, current_api_balance);
    }
}

void ui_update_todos(const ui_todo_item_t *items, int count)
{
    if(count < 0) count = 0;
    if(count > UI_MAX_TODOS) count = UI_MAX_TODOS;
    if(items == NULL && count > 0) return;
    current_todo_count = count;
    for(int index = 0; index < count; ++index) {
        current_todos[index] = items[index];
        current_todos[index].text[sizeof(current_todos[index].text) - 1] = '\0';
    }
    refresh_syna_todos();
}

void ui_update_agent_state(const char *state)
{
    if(state == NULL || state[0] == '\0') state = "OFFLINE";
    const bool state_changed = strcmp(current_agent_state, state) != 0;
    if(!state_changed) return;
    snprintf(current_agent_state, sizeof(current_agent_state), "%s", state);
    if(dashboard_agent_status_image != NULL &&
       lv_obj_is_valid(dashboard_agent_status_image)) {
        lv_image_set_src(dashboard_agent_status_image,
                         status_asset_for(current_agent_state));
        if(strcmp(current_agent_state, "LOGIN_REQUIRED") == 0) {
            lv_obj_add_flag(dashboard_agent_status_image, LV_OBJ_FLAG_HIDDEN);
        }
        else if(state_changed) {
            lv_obj_remove_flag(dashboard_agent_status_image, LV_OBJ_FLAG_HIDDEN);
        }
    }
    if(dashboard_agent_login_label != NULL &&
       lv_obj_is_valid(dashboard_agent_login_label)) {
        if(strcmp(current_agent_state, "LOGIN_REQUIRED") == 0) {
            lv_obj_remove_flag(dashboard_agent_login_label, LV_OBJ_FLAG_HIDDEN);
        }
        else {
            lv_obj_add_flag(dashboard_agent_login_label, LV_OBJ_FLAG_HIDDEN);
        }
    }
    if(agent_done_blink_timer != NULL && state_changed) {
        if(strcmp(current_agent_state, "DONE") == 0) {
            lv_timer_reset(agent_done_blink_timer);
            lv_timer_resume(agent_done_blink_timer);
        }
        else {
            lv_timer_pause(agent_done_blink_timer);
        }
    }
}

void ui_update_codex_quota(int short_remaining_percent,
                           int week_remaining_percent, bool connected, bool stale)
{
    const int values[2] = {short_remaining_percent, week_remaining_percent};
    lv_obj_t *labels[2] = {dashboard_short_quota_label,
                           dashboard_week_quota_label};
    lv_obj_t *fills[2] = {dashboard_short_quota_fill,
                          dashboard_week_quota_fill};
    for(int index = 0; index < 2; ++index) {
        const bool valid = connected && values[index] >= 0 && values[index] <= 100;
        char text[8];
        if(valid) snprintf(text, sizeof(text), "%s%d%%", stale ? "~" : "", values[index]);
        else snprintf(text, sizeof(text), "--");
        if(labels[index] != NULL && lv_obj_is_valid(labels[index])) {
            lv_label_set_text(labels[index], text);
        }
        if(fills[index] != NULL && lv_obj_is_valid(fills[index])) {
            if(valid && values[index] > 0) {
                lv_obj_set_width(fills[index], (142 * values[index]) / 100);
                lv_obj_remove_flag(fills[index], LV_OBJ_FLAG_HIDDEN);
            }
            else {
                lv_obj_add_flag(fills[index], LV_OBJ_FLAG_HIDDEN);
            }
        }
    }
}

static void format_media_time(char *buffer, size_t size, int seconds, bool valid)
{
    if(!valid || seconds < 0) {
        snprintf(buffer, size, "--:--");
        return;
    }
    snprintf(buffer, size, "%02d:%02d", seconds / 60, seconds % 60);
}

void ui_update_media(bool available, const char *status, const char *title,
                     const char *artist, int position_seconds,
                     int duration_seconds, const char *lyric)
{
    const bool playing = available && status != NULL && strcmp(status, "playing") == 0;
    const bool paused = available && status != NULL && strcmp(status, "paused") == 0;
    if(dashboard_media_status_label != NULL) {
        lv_label_set_text(dashboard_media_status_label,
                          playing ? "正在播放" : (paused ? "已暂停" : "未播放"));
    }
    if(dashboard_media_title_label != NULL) {
        lv_label_set_text(dashboard_media_title_label,
                          available && title != NULL && title[0] ? title : "网易云音乐");
    }
    if(dashboard_media_artist_label != NULL) {
        lv_label_set_text(dashboard_media_artist_label,
                          available && artist != NULL && artist[0] ? artist : "--");
    }
    if(dashboard_media_lyric_label != NULL) {
        lv_label_set_text(dashboard_media_lyric_label,
                          available && lyric != NULL && lyric[0] ? lyric : "暂无歌词");
    }
    char position_text[12];
    char duration_text[12];
    const bool timeline_valid = available && duration_seconds > 0;
    format_media_time(position_text, sizeof(position_text), position_seconds, timeline_valid);
    format_media_time(duration_text, sizeof(duration_text), duration_seconds, timeline_valid);
    if(dashboard_media_position_label != NULL) {
        lv_label_set_text(dashboard_media_position_label, position_text);
    }
    if(dashboard_media_duration_label != NULL) {
        lv_label_set_text(dashboard_media_duration_label, duration_text);
    }
    if(dashboard_media_progress_knob != NULL) {
        int progress = timeline_valid ? (position_seconds * 182) / duration_seconds : 0;
        if(progress < 0) progress = 0;
        if(progress > 182) progress = 182;
        lv_obj_set_x(dashboard_media_progress_knob, 191 + progress);
    }
}

void ui_update_performance(float cpu_percent, float memory_percent,
                           float gpu_percent, bool gpu_valid,
                           float disk_percent, float cpu_temperature_c,
                           bool cpu_temperature_valid,
                           float gpu_temperature_c,
                           bool gpu_temperature_valid,
                           int latency_ms, float upload_mb_per_second,
                           float download_mb_per_second, bool connected)
{
    current_performance_state.cpu_percent = cpu_percent;
    current_performance_state.memory_percent = memory_percent;
    current_performance_state.gpu_percent = gpu_percent;
    current_performance_state.gpu_valid = gpu_valid;
    current_performance_state.disk_percent = disk_percent;
    current_performance_state.cpu_temperature_c = cpu_temperature_c;
    current_performance_state.cpu_temperature_valid = cpu_temperature_valid;
    current_performance_state.gpu_temperature_c = gpu_temperature_c;
    current_performance_state.gpu_temperature_valid = gpu_temperature_valid;
    current_performance_state.latency_ms = latency_ms;
    current_performance_state.upload_mb_per_second = upload_mb_per_second;
    current_performance_state.download_mb_per_second = download_mb_per_second;
    current_performance_state.connected = connected;
    if(performance_screen == NULL || !lv_obj_is_valid(performance_screen)) return;

    const float values[4] = {cpu_percent, memory_percent, gpu_percent, disk_percent};
    for(int index = 0; index < 4; ++index) {
        bool valid = connected && (index != 2 || gpu_valid);
        int percent = valid ? (int)(values[index] + 0.5f) : 0;
        if(percent < 0) percent = 0;
        if(percent > 100) percent = 100;
        char text[8];
        if(valid) snprintf(text, sizeof(text), "%d%%", percent);
        else snprintf(text, sizeof(text), "--");
        lv_label_set_text(performance_usage_labels[index], text);
        lv_obj_set_width(performance_usage_fills[index], (150 * percent) / 100);
    }

    char text[20];
    if(connected && cpu_temperature_valid)
        snprintf(text, sizeof(text), "%.0f\xC2\xB0" "C", cpu_temperature_c);
    else snprintf(text, sizeof(text), "--");
    lv_label_set_text(performance_temperature_labels[0], text);

    if(connected && gpu_temperature_valid)
        snprintf(text, sizeof(text), "%.0f\xC2\xB0" "C", gpu_temperature_c);
    else snprintf(text, sizeof(text), "--");
    lv_label_set_text(performance_temperature_labels[1], text);

    if(connected) snprintf(text, sizeof(text), "%d ms", latency_ms);
    else snprintf(text, sizeof(text), "--");
    lv_label_set_text(performance_latency_label, text);

    if(connected) snprintf(text, sizeof(text), "%.1f MB/s", upload_mb_per_second);
    else snprintf(text, sizeof(text), "--");
    lv_label_set_text(performance_upload_label, text);

    if(connected) snprintf(text, sizeof(text), "%.1f MB/s", download_mb_per_second);
    else snprintf(text, sizeof(text), "--");
    lv_label_set_text(performance_download_label, text);

    if(performance_network_chart != NULL && performance_network_series != NULL &&
       lv_obj_is_valid(performance_network_chart)) {
        lv_chart_set_next_value(
            performance_network_chart,
            performance_network_series,
            connected ? network_chart_value(upload_mb_per_second,
                                              download_mb_per_second) : 0);
    }
    ui_update_pc_connected(connected);
}

bool ui_is_computer_page(void)
{
    return current_page == PAGE_COMPUTERS;
}

bool ui_is_syna_page(void)
{
    return current_page == PAGE_SYNA;
}

void ui_init(void)
{
    ui_show_dashboard();
    show_startup_signature();
    agent_done_blink_timer = lv_timer_create(agent_done_blink_cb, 500, NULL);
    lv_timer_pause(agent_done_blink_timer);
}

static void update_computer_rows(void)
{
    if(computer_found_label != NULL) {
        char found[20];
        snprintf(found, sizeof(found), "%d FOUND", computer_list_count);
        lv_label_set_text(computer_found_label, found);
    }
    for(int i = 0; i < COMPUTER_ROWS_VISIBLE; ++i) {
        const int item_index = computer_list_offset + i;
        const bool visible = item_index < computer_list_count;
        if(!visible) {
            lv_obj_add_flag(computer_rows[i], LV_OBJ_FLAG_HIDDEN);
            continue;
        }
        lv_obj_remove_flag(computer_rows[i], LV_OBJ_FLAG_HIDDEN);
        const bool selected = item_index == selected_computer;
        const ui_computer_info_t *item = &computer_list[item_index];
        char state[48];
        snprintf(state, sizeof(state), "%s  AGENT %s",
                 item->online ? "ONLINE" : "OFFLINE", item->agent_state);
        lv_label_set_text(computer_name_labels[i], item->name);
        lv_label_set_text(computer_state_labels[i], state);
        lv_label_set_text(computer_current_labels[i],
                          item_index == current_list_computer ? "CURRENT" : "");

        /* White-on-black antialiased glyphs lose strokes after 1-bit
         * quantization. Keep the same rounded-card language as the dashboard,
         * and show selection with a bold black outline instead. */
        lv_obj_set_style_bg_color(computer_rows[i], COLOR_WHITE, 0);
        lv_obj_set_style_border_width(computer_rows[i], selected ? 3 : 1, 0);
        lv_obj_set_style_text_color(computer_rows[i], COLOR_BLACK, 0);
        lv_obj_set_style_text_color(computer_name_labels[i], COLOR_BLACK, 0);
        lv_obj_set_style_text_color(computer_state_labels[i], COLOR_BLACK, 0);
        lv_obj_set_style_text_color(computer_current_labels[i], COLOR_BLACK, 0);
    }
}

static void computer_row_clicked(lv_event_t *event)
{
    selected_computer = computer_list_offset +
                        (int)(uintptr_t)lv_event_get_user_data(event);
    update_computer_rows();
}
