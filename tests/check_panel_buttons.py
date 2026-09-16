"""Compile real board callbacks with fake buttons/LVGL, then exercise gestures.

Run in a Visual C++ developer prompt: python tests/check_panel_buttons.py
This is a host regression test, not an ESP-IDF build or hardware timing test.
"""
from pathlib import Path
import os
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
BOARD = ROOT / 'xiaozhi/overlay/main/boards/waveshare/esp32-s3-rlcd-4.2'


def method(path, signature):
    source = path.read_text(encoding='utf-8')
    start = source.index(signature)
    opening = source.index('{', start)
    depth = 1
    end = opening + 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end]


support = r'''
#include <cassert>
#include <functional>
#include <iostream>
#include <vector>
#include "panel_button_gestures.h"
#define CONFIG_USE_DEVICE_AEC 1
constexpr int BOOT_BUTTON_GPIO = 0, KEY_BUTTON_GPIO = 1;
bool pressed[2] = {};
int gpio_get_level(int pin) { return !pressed[pin]; }
enum { kDeviceStateStarting, kDeviceStateIdle, kAecOff, kAecOnDeviceSide };
bool picker = false;
int count = 3, selected = 0, pages = 0, last_request = -1;
int lock_depth = 0;
struct DisplayLockGuard {
    explicit DisplayLockGuard(void*) { ++lock_depth; }
    ~DisplayLockGuard() { --lock_depth; }
};
bool ui_is_computer_page() { assert(lock_depth); return picker; }
void ui_select_computer(int n) { assert(lock_depth); if (count) selected = (selected+n)%count; }
void ui_toggle_page() { assert(lock_depth); ++pages; }
void ui_show_dashboard() { assert(lock_depth); picker = false; }
void ui_show_computers() { assert(lock_depth); picker = true; }
int ui_confirm_computer() { assert(lock_depth); if (!count) return -1; picker = false; return selected; }
struct ReporterService {
    static ReporterService& GetInstance() { static ReporterService service; return service; }
    void RequestSelection(int n) { assert(!lock_depth); last_request = n; }
};
struct CustomLcdDisplay {
    bool panel_ui_ready_ = true;
    void HandlePanelKeyShortPress();
    void ToggleComputerPicker();
    bool ConfirmComputerPicker();
};
struct Application {
    std::vector<std::function<void()>> queued;
    int voice = 0, aec_changes = 0, state = kDeviceStateIdle;
    static Application& GetInstance() { static Application app; return app; }
    void Schedule(std::function<void()> f) { queued.push_back(f); }
    void Drain() { auto copy = queued; queued.clear(); for (auto& f : copy) f(); }
    int GetDeviceState() { return state; }
    void ToggleChatState() { ++voice; }
    int GetAecMode() { return kAecOff; }
    void SetAecMode(int) { ++aec_changes; }
};
struct Button {
    std::function<void()> down, up, click, long_press, double_click;
    void OnPressDown(std::function<void()> f) { down = f; }
    void OnPressUp(std::function<void()> f) { up = f; }
    void OnClick(std::function<void()> f) { click = f; }
    void OnLongPress(std::function<void()> f) { long_press = f; }
    void OnDoubleClick(std::function<void()> f) { double_click = f; }
};
struct CustomBoard {
    Button boot_button_, key_button_;
    CustomLcdDisplay display;
    CustomLcdDisplay* display_ = &display;
    PanelButtonGestures panel_buttons_;
    bool settings_combo_triggered_ = false;
    int settings = 0, cancelled = 0;
    void EnterWifiConfigMode() { ++settings; }
    void CancelFactoryResetCountdown() { ++cancelled; }
    void TryEnterSettingsPortal() {
        if (settings_combo_triggered_ || !pressed[0] || !pressed[1]) return;
        settings_combo_triggered_ = true;
        EnterWifiConfigMode();
    }
    void InitializeButtons();
    void Down(int pin) { pressed[pin] = true; (pin ? key_button_ : boot_button_).down(); }
    void Up(int pin) { pressed[pin] = false; (pin ? key_button_ : boot_button_).up(); }
};
'''

scenarios = r'''
void reset() {
    auto& app = Application::GetInstance();
    app = Application{};
    pressed[0] = pressed[1] = false;
    picker = false; count = 3; selected = pages = 0; last_request = -1;
}
int main() {
    auto& app = Application::GetInstance();
    reset();
    CustomBoard board; board.InitializeButtons();
    board.Down(1); assert(pages == 0);
    board.key_button_.long_press(); assert(!picker);
    app.Drain(); assert(picker && pages == 0);
    board.Up(1); app.Drain(); assert(selected == 0 && pages == 0);
    board.Down(1); board.Up(1); assert(selected == 0);
    app.Drain(); assert(selected == 1);
    board.Down(0); board.Up(0); board.boot_button_.click();
    assert(last_request == -1); app.Drain();
    assert(last_request == 1 && !picker && app.voice == 0);
    board.Down(0); board.Up(0); board.boot_button_.click(); app.Drain();
    assert(app.voice == 1);
    board.Down(1); board.Up(1); app.Drain(); assert(pages == 1);
    // Empty list consumes BOOT; holding KEY again gives a silent escape.
    picker = true; count = 0;
    board.Down(0); board.Up(0); board.boot_button_.click(); app.Drain();
    assert(app.voice == 1 && picker);
    board.Down(1); board.key_button_.long_press(); app.Drain();
    board.Up(1); app.Drain(); assert(!picker && pages == 1);
    // Double click confirms in picker; AEC double click remains elsewhere.
    picker = true; count = 3; selected = 2;
    board.Down(0); board.Up(0); board.boot_button_.double_click(); app.Drain();
    assert(last_request == 2 && app.aec_changes == 0 && app.voice == 1);
    board.Down(0); board.Up(0); board.boot_button_.double_click(); app.Drain();
    assert(app.aec_changes == 1);
    // Every chord press/release order, both short and long, suppresses all
    // picker/voice actions. A subsequent ordinary gesture must work again.
    for (int first = 0; first < 2; ++first) {
        for (int released = 0; released < 2; ++released) {
            for (int held = 0; held < 2; ++held) {
                reset(); CustomBoard combo; combo.InitializeButtons();
                combo.Down(first); combo.Down(1-first);
                if (held) { combo.key_button_.long_press(); combo.boot_button_.long_press(); }
                app.Drain(); assert(!picker && pages == 0 && app.voice == 0);
                assert(combo.settings == held);
                combo.Up(released); combo.Up(1-released);
                combo.boot_button_.click(); combo.boot_button_.double_click(); app.Drain();
                assert(pages == 0 && app.voice == 0 && app.aec_changes == 0);
                assert(combo.cancelled == 2);
                combo.Down(1); combo.Up(1); app.Drain(); assert(pages == 1);
                combo.Down(0); combo.Up(0); combo.boot_button_.click(); app.Drain();
                assert(app.voice == 1);
            }
        }
    }
    // Startup callbacks cannot dereference a display that is not ready yet.
    reset(); CustomBoard early; early.InitializeButtons(); early.display_ = nullptr;
    early.Down(1); early.Up(1); app.Drain();
    early.Down(1); early.key_button_.long_press(); early.Up(1); app.Drain();
    std::cout << "PASS: picker, empty list, voice/AEC isolation, deferred UI, 8 chord sequences, startup guards\n";
}
'''


def main():
    callbacks = method(BOARD / 'waveshare-s3-rlcd-4.2.cc', '    void InitializeButtons()')
    callbacks = callbacks.replace('void InitializeButtons()', 'void CustomBoard::InitializeButtons()', 1)
    display = BOARD / 'custom_lcd_display.cc'
    methods = '\n'.join(method(display, signature) for signature in (
        'void CustomLcdDisplay::HandlePanelKeyShortPress()',
        'void CustomLcdDisplay::ToggleComputerPicker()',
        'bool CustomLcdDisplay::ConfirmComputerPicker()',
    ))
    with tempfile.TemporaryDirectory(prefix='syna-buttons-', ignore_cleanup_errors=True) as tmp:
        directory = Path(tmp)
        source = directory / 'test.cpp'
        source.write_text(support + '\n' + methods + '\n' + callbacks + '\n' + scenarios, encoding='utf-8')
        exe = directory / 'test.exe'
        command = ['cl.exe', '/nologo', '/EHsc', '/std:c++17', '/utf-8', '/W4',
                   '/I' + str(BOARD), str(source), '/Fe:' + str(exe),
                   '/Fo:' + str(directory / 'test.obj')]
        if shutil.which('cl.exe'):
            subprocess.run(command, cwd=directory, check=True)
        else:
            vcvars = Path(os.environ.get('SYNA_VCVARS', r'D:\vs\VC\Auxiliary\Build\vcvars64.bat'))
            if not vcvars.is_file():
                raise SystemExit('Run in a Visual C++ developer prompt or set SYNA_VCVARS.')
            batch = directory / 'build.cmd'
            batch.write_text('@echo off\nchcp 65001 >nul\nset VSCMD_SKIP_SENDTELEMETRY=1\ncall "' + str(vcvars) + '" >nul\n' +
                             subprocess.list2cmdline(command) + '\nexit /b %errorlevel%\n', encoding='utf-8')
            # UTF-8 code page allows the project to keep its Chinese path.
            subprocess.run(['cmd.exe', '/d', '/c', str(batch)], cwd=ROOT, check=True)
        subprocess.run([str(exe)], check=True)


if __name__ == '__main__':
    main()
