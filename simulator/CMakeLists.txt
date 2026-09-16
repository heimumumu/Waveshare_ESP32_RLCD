cmake_minimum_required(VERSION 3.20)

project(ai_panel_simulator LANGUAGES C CXX)

set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)
set(CMAKE_RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/bin")

find_package(SDL2 CONFIG REQUIRED)

set(LV_BUILD_CONF_PATH "${CMAKE_CURRENT_SOURCE_DIR}/lv_conf.h" CACHE PATH "" FORCE)
set(CONFIG_LV_BUILD_DEMOS OFF CACHE BOOL "" FORCE)
set(CONFIG_LV_BUILD_EXAMPLES OFF CACHE BOOL "" FORCE)
set(CONFIG_LV_USE_THORVG_INTERNAL OFF CACHE BOOL "" FORCE)

add_subdirectory(vendor/lvgl-9.5.0 lvgl-build EXCLUDE_FROM_ALL)
target_link_libraries(lvgl PUBLIC SDL2::SDL2)

add_executable(ai_panel_simulator
    src/main.c
    src/ui/ui.c
    src/assets/ui_screen_base.c
    src/assets/ui_performance_base.c
    src/assets/ui_syna_base.c
    src/assets/ui_syna_wallet.c
    src/assets/ui_syna_speech.c
    src/assets/ui_syna_todo_checked.c
    src/assets/ui_syna_todo_unchecked.c
    src/assets/ui_status_working.c
    src/assets/ui_status_waiting.c
    src/assets/ui_status_done.c
    src/assets/ui_status_idle.c
    src/assets/ui_status_offline.c
    src/assets/ui_wifi_unconfigured.c
    src/assets/ui_wifi_connecting.c
    src/assets/ui_wifi_provisioning.c
    src/assets/ui_wifi_connected.c
    src/assets/ui_pc_disconnected.c
    src/assets/ui_pc_connected.c
    src/assets/ui_font_18_regular.c
    src/assets/ui_font_11_regular.c
    src/assets/ui_font_14_regular.c
    src/assets/ui_font_14_cjk.c
)

target_include_directories(ai_panel_simulator PRIVATE src)
target_compile_definitions(ai_panel_simulator PRIVATE _CRT_SECURE_NO_WARNINGS)
target_link_libraries(ai_panel_simulator PRIVATE lvgl SDL2::SDL2)

if(MINGW)
    target_link_options(ai_panel_simulator PRIVATE -static-libgcc -static-libstdc++)
endif()

add_custom_command(TARGET ai_panel_simulator POST_BUILD
    COMMAND ${CMAKE_COMMAND} -E copy_if_different
            $<TARGET_FILE:SDL2::SDL2>
            $<TARGET_FILE_DIR:ai_panel_simulator>
)
