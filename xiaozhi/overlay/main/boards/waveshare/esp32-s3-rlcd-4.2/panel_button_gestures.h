#pragma once

// Event state only. Called from the button timer task, never from the UI task.
// Remember a chord through both releases so it cannot become a short press.
class PanelButtonGestures {
public:
    bool Idle() const { return !key_down_ && !boot_down_; }
    void KeyDown() {
        BeginPress();
        key_down_ = true;
        key_long_ = false;
        chord_ = chord_ || boot_down_;
    }
    void BootDown() {
        BeginPress();
        boot_down_ = true;
        chord_ = chord_ || key_down_;
    }
    bool KeyLongPress() {
        key_long_ = true;
        return key_down_ && !chord_;
    }
    bool KeyUp() {
        const bool short_press = key_down_ && !key_long_ && !chord_;
        key_down_ = false;
        return short_press;
    }
    void BootUp() { boot_down_ = false; }
    bool BootClickAllowed() const { return !chord_; }

private:
    void BeginPress() {
        if (Idle()) chord_ = false;
    }
    bool key_down_ = false;
    bool boot_down_ = false;
    bool key_long_ = false;
    bool chord_ = false;
};
