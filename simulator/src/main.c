#define SDL_MAIN_HANDLED
#include <SDL2/SDL.h>

#include <stdint.h>
#include <stdlib.h>
#include <string.h>

#include "lvgl.h"
#include "src/drivers/sdl/lv_sdl_mouse.h"
#include "src/drivers/sdl/lv_sdl_window.h"
#include "ui/ui.h"

enum {
    COMMAND_TOGGLE_PAGE = 1U << 0,
    COMMAND_SHOW_COMPUTERS = 1U << 1,
    COMMAND_SELECT_NEXT = 1U << 2,
    COMMAND_SELECT_PREVIOUS = 1U << 3,
    COMMAND_CONFIRM = 1U << 4,
    COMMAND_DASHBOARD = 1U << 5,
    COMMAND_CYCLE_STATE = 1U << 6,
    COMMAND_PERFORMANCE = 1U << 7,
    COMMAND_SYNA = 1U << 8,
};

static volatile uint32_t pending_commands;

static int save_screenshot(lv_display_t *display, const char *path)
{
    SDL_Renderer *renderer = (SDL_Renderer *)lv_sdl_window_get_renderer(display);
    if(renderer == NULL || path == NULL || path[0] == '\0') return -1;

    int width = 0;
    int height = 0;
    if(SDL_GetRendererOutputSize(renderer, &width, &height) != 0) return -1;

    SDL_Surface *surface = SDL_CreateRGBSurfaceWithFormat(
        0, width, height, 32, SDL_PIXELFORMAT_ARGB8888);
    if(surface == NULL) return -1;

    int result = SDL_RenderReadPixels(
        renderer,
        NULL,
        SDL_PIXELFORMAT_ARGB8888,
        surface->pixels,
        surface->pitch);
    if(result == 0) result = SDL_SaveBMP(surface, path);

    SDL_FreeSurface(surface);
    return result;
}

static int watch_sdl_events(void *userdata, SDL_Event *event)
{
    (void)userdata;

    if(event->type != SDL_KEYDOWN || event->key.repeat != 0) return 1;

    switch(event->key.keysym.sym) {
        case SDLK_SPACE:
            pending_commands |= COMMAND_TOGGLE_PAGE;
            break;
        case SDLK_c:
            pending_commands |= COMMAND_SHOW_COMPUTERS;
            break;
        case SDLK_p:
            pending_commands |= COMMAND_PERFORMANCE;
            break;
        case SDLK_s:
            pending_commands |= COMMAND_SYNA;
            break;
        case SDLK_DOWN:
        case SDLK_TAB:
            pending_commands |= COMMAND_SELECT_NEXT;
            break;
        case SDLK_UP:
            pending_commands |= COMMAND_SELECT_PREVIOUS;
            break;
        case SDLK_RETURN:
        case SDLK_KP_ENTER:
            pending_commands |= COMMAND_CONFIRM;
            break;
        case SDLK_ESCAPE:
            pending_commands |= COMMAND_DASHBOARD;
            break;
        case SDLK_r:
            pending_commands |= COMMAND_CYCLE_STATE;
            break;
        default:
            break;
    }

    return 1;
}

static void process_pending_commands(void)
{
    uint32_t commands = pending_commands;
    pending_commands = 0;

    if(commands & COMMAND_SHOW_COMPUTERS) ui_show_computers();
    if(commands & COMMAND_PERFORMANCE) ui_show_performance();
    if(commands & COMMAND_SYNA) ui_show_syna();
    if(commands & COMMAND_TOGGLE_PAGE) ui_toggle_page();
    if(commands & COMMAND_SELECT_NEXT) ui_select_computer(1);
    if(commands & COMMAND_SELECT_PREVIOUS) ui_select_computer(-1);
    if(commands & COMMAND_CONFIRM) ui_confirm_computer();
    if(commands & COMMAND_DASHBOARD) ui_show_dashboard();
    if(commands & COMMAND_CYCLE_STATE) ui_cycle_mock_status();
}

int main(void)
{
    lv_init();

    lv_display_t *display = lv_sdl_window_create(400, 300);
    if(display == NULL) return 1;

    lv_sdl_window_set_title(display, "AI Agent Desktop Status - 400x300 RLCD Preview");
    lv_sdl_window_set_zoom(display, 2.0f);
    lv_sdl_window_set_resizeable(display, false);
    lv_sdl_mouse_create();
    SDL_AddEventWatch(watch_sdl_events, NULL);

    ui_init();
    ui_update_environment(26.0f, 58.0f, 87, true, true);
    ui_update_wifi_state(UI_WIFI_CONNECTED);
    ui_update_performance(38.0f, 67.0f, 42.0f, true, 15.0f,
                          64.0f, true, 57.0f, true, 12,
                          2.4f, 18.7f, true);
    ui_update_codex_quota(100, 91, true);
    ui_update_api_balance("DeepSeek", "CNY 86.42");
    ui_update_pc_connected(true);
    ui_update_syna_conversation("今天还有什么安排？",
                                "你有 2 项待办，最近一项是整理开发文档。");
    const ui_todo_item_t todo_demo[] = {
        {.id = 1, .text = "整理开发文档", .completed = true},
        {.id = 2, .text = "校验屏幕布局", .completed = true},
        {.id = 3, .text = "接入小智工具", .completed = false},
        {.id = 4, .text = "测试语音待办", .completed = false},
    };
    ui_update_todos(todo_demo, 4);
    const char *media_demo = getenv("AI_PANEL_MEDIA_DEMO");
    if(media_demo != NULL && strcmp(media_demo, "1") == 0) {
        ui_update_media(true, "playing", "Ring of Coins", "Lindsey Stirling",
                        114, 271, "纯音乐，请欣赏");
    }
    const char *start_page = getenv("AI_PANEL_START_PAGE");
    if(start_page != NULL && strcmp(start_page, "computers") == 0) ui_show_computers();
    else if(start_page != NULL && strcmp(start_page, "performance") == 0) {
        ui_show_performance();
        const float demo_traffic[][2] = {
            {0.0f, 0.2f}, {0.3f, 2.0f}, {0.1f, 0.7f}, {1.5f, 8.1f},
            {0.4f, 1.6f}, {2.0f, 13.0f}, {0.1f, 0.3f}, {0.8f, 4.0f},
            {3.1f, 20.0f}, {0.2f, 1.2f}, {1.1f, 6.5f}, {2.4f, 18.7f},
        };
        for(size_t index = 0;
            index < sizeof(demo_traffic) / sizeof(demo_traffic[0]); ++index) {
            ui_update_performance(38.0f, 67.0f, 42.0f, true, 15.0f,
                                  64.0f, true, 57.0f, true, 12,
                                  demo_traffic[index][0], demo_traffic[index][1], true);
        }
    }
    else if(start_page != NULL && strcmp(start_page, "syna") == 0) {
        ui_show_syna();
    }

    uint32_t last_clock_update = SDL_GetTicks();
    uint32_t started_at = last_clock_update;
    uint32_t auto_close_ms = 0;
    bool screenshot_saved = false;
    const char *auto_close_value = getenv("AI_PANEL_AUTOCLOSE_MS");
    const char *screenshot_path = getenv("AI_PANEL_SCREENSHOT_PATH");
    if(auto_close_value != NULL) auto_close_ms = (uint32_t)strtoul(auto_close_value, NULL, 10);

    while(true) {
        process_pending_commands();

        uint32_t now = SDL_GetTicks();
        if(now - last_clock_update >= 1000U) {
            ui_update_clock();
            last_clock_update = now;
        }

        uint32_t delay_ms = lv_timer_handler();

        if(!screenshot_saved && screenshot_path != NULL && now - started_at >= 200U) {
            lv_refr_now(display);
            if(save_screenshot(display, screenshot_path) != 0) {
                SDL_Log("Could not save simulator screenshot to %s: %s", screenshot_path, SDL_GetError());
            }
            screenshot_saved = true;
        }

        if(delay_ms < 5U) delay_ms = 5U;
        if(delay_ms > 20U) delay_ms = 20U;
        SDL_Delay(delay_ms);

        if(auto_close_ms > 0U && now - started_at >= auto_close_ms) break;
    }

    SDL_DelEventWatch(watch_sdl_events, NULL);
    lv_deinit();
    return 0;
}
