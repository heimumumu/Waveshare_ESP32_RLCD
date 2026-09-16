#!/usr/bin/env python3
# Copyright (c) 2026 黑沐. MIT License; upstream notices retained.
"""Portable equivalent of apply-ui-overlay.ps1 for the pinned Xiaozhi tree."""
import argparse
import json
import re
import shutil
import subprocess
from pathlib import Path

HERE=Path(__file__).resolve().parent
COMMIT='5df5b7fb4da2b4d80e2b7f87285ec1f8a9ca565c'
BOARD=Path('main/boards/waveshare/esp32-s3-rlcd-4.2')

def patch(path, marker, old, new):
    text=path.read_text()
    if marker in text:return
    if old not in text:raise RuntimeError('Patch anchor missing: '+str(path))
    path.write_text(text.replace(old,new,1))

def configure(path, settings):
    if not path.exists():return
    text=path.read_text()
    for setting in settings:
        key=setting.split('=',1)[0]
        pattern=r'(?m)^(?:'+re.escape(key)+r'=.*|# '+re.escape(key)+r' is not set)$'
        if re.search(pattern,text):text=re.sub(pattern,lambda _:setting,text)
        else:text+='\n'+setting+'\n'
    path.write_text(text)

def single_turn(root):
    p = root/'main/application.cc'
    patch(root/'main/application.h', 'syna_reply_finished_',
          '    bool pending_listening_start_ = false;',
          '    bool syna_reply_finished_ = false;  // Return to idle after TTS drains\n    bool pending_listening_start_ = false;')
    patch(p, '// Syna single-turn: finish only after playback drains.',
          '        if (bits & MAIN_EVENT_PLAYBACK_DRAINED) {', '''        // Syna single-turn: finish only after playback drains.
        if ((bits & (MAIN_EVENT_PLAYBACK_DRAINED | MAIN_EVENT_CLOCK_TICK)) &&
            syna_reply_finished_ && GetDeviceState() == kDeviceStateSpeaking &&
            audio_service_.IsPlaybackIdle()) {
            syna_reply_finished_ = false;
            SetDeviceState(kDeviceStateIdle);
        }
        if (bits & MAIN_EVENT_PLAYBACK_DRAINED) {''')
    patch(p, '// Syna single-turn: server STOP may precede the last speaker samples.',
          '''                        if (listening_mode_ == kListeningModeManualStop) {
                            SetDeviceState(kDeviceStateIdle);
                        } else {
                            SetDeviceState(kDeviceStateListening);
                        }''', '''                        // Syna single-turn: server STOP may precede the last speaker samples.
                        syna_reply_finished_ = true;
                        if (audio_service_.IsPlaybackIdle()) {
                            syna_reply_finished_ = false;
                            SetDeviceState(kDeviceStateIdle);
                        }''')
    patch(p, '// Syna single-turn: reject queued wake detections during a conversation.',
          '    auto wake_word = audio_service_.GetLastWakeWord();', '''    // Syna single-turn: reject queued wake detections during a conversation.
    if (state == kDeviceStateSpeaking || state == kDeviceStateListening) {
        return;
    }
    auto wake_word = audio_service_.GetLastWakeWord();''')
    patch(p, '// Syna single-turn: never stream microphone audio during the reply.',
          '''            if (listening_mode_ != kListeningModeRealtime) {
                audio_service_.EnableVoiceProcessing(false);
                // Only AFE wake word can be detected in speaking mode
                audio_service_.EnableWakeWordDetection(audio_service_.IsAfeWakeWord());
            }''', '''            // Syna single-turn: never stream microphone audio during the reply.
            audio_service_.EnableVoiceProcessing(false);
            audio_service_.EnableWakeWordDetection(false);''')
    patch(p, '// Syna single-turn uses server end-of-utterance detection.',
          '    return aec_mode_ == kAecOff ? kListeningModeAutoStop : kListeningModeRealtime;',
          '    // Syna single-turn uses server end-of-utterance detection.\n    return kListeningModeAutoStop;')
    patch(p, '// Syna single-turn: listening does not accept another wake word.',
          'void Application::ConfigureWakeWordForListening() {', '''void Application::ConfigureWakeWordForListening() {
    // Syna single-turn: listening does not accept another wake word.
    audio_service_.EnableWakeWordDetection(false);
    return;''')
    patch(p, '// Syna single-turn: cancel deferred completion on state changes.',
          '    pending_listening_start_ = false;\n\n    auto& board',
          '''    pending_listening_start_ = false;
    // Syna single-turn: cancel deferred completion on state changes.
    if (new_state != kDeviceStateSpeaking) syna_reply_finished_ = false;

    auto& board''')

def source(root):
    single_turn(root)
    for p in (HERE/'overlay'/BOARD).iterdir():
        if p.is_file():shutil.copy2(p,root/BOARD/p.name)
    p=root/'main/CMakeLists.txt'
    patch(p,'                        esp_http_client\n','                    PRIV_REQUIRES\n','                    PRIV_REQUIRES\n                        esp_http_client\n')
    config=json.loads((HERE/'overlay'/BOARD/'config.json').read_text())
    config['builds'][0]['sdkconfig_append'] += [
        'CONFIG_LV_USE_CHART=y','CONFIG_LV_FONT_MONTSERRAT_38=y','CONFIG_LV_FONT_MONTSERRAT_42=y']
    (root/BOARD/'config.json').write_text(json.dumps(config,ensure_ascii=False,indent=2)+'\n')
    settings=config['builds'][0]['sdkconfig_append']+[
        'CONFIG_BOARD_TYPE_WAVESHARE_ESP32_S3_RLCD_4_2=y','CONFIG_LANGUAGE_ZH_CN=y']
    (root/'syna.sdkconfig.defaults').write_text('# Generated by Syna overlay\n'+'\n'.join(settings)+'\n')
    block='''config PANEL_FAR_FIELD_AGC
    bool "Enable panel far-field WebRTC AGC"
    default n
    depends on USE_AUDIO_PROCESSOR

config PANEL_FAR_FIELD_AGC_GAIN_DB
    int "Panel far-field AGC compression gain (dB)"
    default 9
    range 0 30
    depends on PANEL_FAR_FIELD_AGC

config PANEL_FAR_FIELD_AGC_TARGET_DBFS
    int "Panel far-field AGC target level (-dBFS)"
    default 3
    range 0 31
    depends on PANEL_FAR_FIELD_AGC

'''
    patch(root/'main/Kconfig.projbuild','config PANEL_FAR_FIELD_AGC\n','config USE_DEVICE_AEC',block+'config USE_DEVICE_AEC')
    patch(root/'main/audio/engines/afe_audio_engine.cc','CONFIG_PANEL_FAR_FIELD_AGC',
          '    afe_config->agc_init = false;', '''#if CONFIG_PANEL_FAR_FIELD_AGC
    afe_config->agc_init = true;
    afe_config->agc_mode = AFE_AGC_MODE_WEBRTC;
    afe_config->agc_compression_gain_db = CONFIG_PANEL_FAR_FIELD_AGC_GAIN_DB;
    afe_config->agc_target_level_dbfs = CONFIG_PANEL_FAR_FIELD_AGC_TARGET_DBFS;
    ESP_LOGI(TAG, "Far-field AGC enabled: gain=%d dB, target=-%d dBFS",
        CONFIG_PANEL_FAR_FIELD_AGC_GAIN_DB, CONFIG_PANEL_FAR_FIELD_AGC_TARGET_DBFS);
#else
    afe_config->agc_init = false;
#endif''')
    p=root/'CMakeLists.txt';text=p.read_text();text=re.sub(r'set\(PROJECT_VER "[^"]+"\)', 'set(PROJECT_VER "1.0.0")',text);p.write_text(text)

def components(root):
    managed=root/'managed_components/78__esp-wifi-connect'
    local=root/'local_components/esp-wifi-connect'
    if not local.exists():
        shutil.copytree(managed,local)
    manifest=root/'main/idf_component.yml'
    patch(manifest,'override_path: ../local_components/esp-wifi-connect',
          '  78/esp-wifi-connect: ~3.2.2',
          '  78/esp-wifi-connect:\n    version: ~3.2.2\n    override_path: ../local_components/esp-wifi-connect')
    p=local/'wifi_configuration_ap.cc'
    old='extern const char done_html_start[] asm("_binary_wifi_configuration_done_html_start");'
    patch(p,'wifi_config_custom_root',old,old+'''
extern "C" esp_err_t wifi_config_custom_root(httpd_req_t*) __attribute__((weak));
extern "C" void wifi_config_register_custom_handlers(httpd_handle_t) __attribute__((weak));
extern "C" const char* wifi_config_custom_ssid() __attribute__((weak));''')
    old='        .handler = [](httpd_req_t *req) -> esp_err_t {\n            httpd_resp_set_hdr(req, "Connection", "close");'
    patch(p,'if (wifi_config_custom_root != nullptr)',old,'''        .handler = [](httpd_req_t *req) -> esp_err_t {
            if (wifi_config_custom_root != nullptr) {
                return wifi_config_custom_root(req);
            }
            httpd_resp_set_hdr(req, "Connection", "close");''')
    old='    ESP_LOGI(TAG, "Web server started");'
    patch(p,'wifi_config_register_custom_handlers(server_)',old,'''    if (wifi_config_register_custom_handlers != nullptr) {
        wifi_config_register_custom_handlers(server_);
    }
'''+old)
    old='std::string WifiConfigurationAp::GetSsid()\n{'
    patch(p,'wifi_config_custom_ssid != nullptr',old,old+'''
    if (wifi_config_custom_ssid != nullptr) {
        const char* custom_ssid = wifi_config_custom_ssid();
        if (custom_ssid != nullptr && custom_ssid[0] != '\\0') {
            return std::string(custom_ssid);
        }
    }''')
    old=r'''            httpd_resp_send(req, "{\"success\":true}", HTTPD_RESP_USE_STRLEN);
            return ESP_OK;
        },
        .user_ctx = this
    };
    ESP_ERROR_CHECK(httpd_register_uri_handler(server_, &form_submit));'''
    new=r'''            httpd_resp_send(req, "{\"success\":true}", HTTPD_RESP_USE_STRLEN);
            ESP_LOGI(TAG, "WiFi credentials saved; exiting config mode...");
            xTaskCreate([](void *ctx) {
                vTaskDelay(pdMS_TO_TICKS(500));
                auto* self = static_cast<WifiConfigurationAp*>(ctx);
                if (self->on_exit_requested_) {
                    self->on_exit_requested_();
                }
                vTaskDelete(NULL);
            }, "submit_exit_task", 4096, this_, 5, NULL);
            return ESP_OK;
        },
        .user_ctx = this
    };
    ESP_ERROR_CHECK(httpd_register_uri_handler(server_, &form_submit));'''
    patch(p,'submit_exit_task',old,new)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('root',type=Path)
    parser.add_argument('--phase',choices=['source','components','all'],default='all')
    args=parser.parse_args();root=args.root.resolve()
    actual=subprocess.check_output(['git','-C',str(root),'rev-parse','HEAD'],text=True).strip()
    if actual!=COMMIT:raise SystemExit('Unsupported upstream commit: '+actual)
    if args.phase in ['source','all']:source(root)
    if args.phase in ['components','all']:components(root)
    print('Applied '+args.phase+' overlay to '+str(root))
