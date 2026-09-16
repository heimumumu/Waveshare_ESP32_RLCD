#include "settings_portal_service.h"

#include <algorithm>
#include <cmath>
#include <cstring>
#include <string>
#include <vector>

#include <cJSON.h>
#include <esp_log.h>
#include <nvs.h>

#include "api_balance_service.h"
#include "reporter_service.h"
#include "settings.h"

namespace {

constexpr char kTag[] = "PanelSettings";
constexpr size_t kMaximumBodyBytes = 4096;

const char kSettingsPage[] = R"HTML(<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>召唤Syna-sama</title><style>
*{box-sizing:border-box}body{margin:0;background:#f1f1ef;color:#111;font-family:system-ui,"Microsoft YaHei",sans-serif}.card{max-width:620px;margin:20px auto;padding:24px;background:#fff;border:2px solid #111;border-radius:18px;box-shadow:6px 6px 0 #111}h1{font-size:25px;margin:0 0 7px}.sub,.tip{color:#555;line-height:1.55}.sub{margin:0 0 18px}.tip{font-size:13px;margin:7px 0 0}fieldset{margin:16px 0;padding:15px;border:2px solid #111;border-radius:12px}legend{padding:0 7px;font-weight:800}label{display:block;font-weight:700;margin:12px 0 6px}input,select,textarea{width:100%;padding:11px;border:2px solid #111;border-radius:8px;font-size:16px;background:#fff}textarea{min-height:76px;resize:vertical}button{width:100%;margin-top:15px;padding:13px;border:2px solid #111;border-radius:8px;background:#111;color:#fff;font-size:17px;font-weight:800}.notice{display:none;padding:11px;margin:0 0 14px;border:1px solid #111;border-radius:8px;background:#eee}.row{display:grid;grid-template-columns:1fr 1fr;gap:12px}@media(max-width:520px){.card{margin:0;border-radius:0;box-shadow:none}.row{grid-template-columns:1fr}}</style></head><body><main class="card"><h1>召唤Syna-sama</h1><p class="sub">网络、Reporter、API 余额、syna语音和电池校准统一设置。密码与令牌不会回显，留空即保持原值。</p><div id="notice" class="notice"></div><form id="form">
<fieldset><legend>网络与时间</legend><label>Wi-Fi / 手机热点名称</label><input name="ssid" list="networks" maxlength="32" autocomplete="off"><datalist id="networks"></datalist><label>Wi-Fi 密码</label><input name="password" type="password" maxlength="64" autocomplete="new-password" placeholder="留空保持已保存密码"><p class="tip">若不修改网络，两项都留空。设备会联网自动校时，时区固定为中国标准时间 UTC+8。</p></fieldset>
<fieldset><legend>电脑 Reporter</legend><label>配对令牌</label><input name="reporter_token" type="password" maxlength="96" autocomplete="off" placeholder="留空保持原令牌"><p class="tip">应与电脑 Reporter 中的令牌一致。</p></fieldset>
<fieldset><legend>API 余额</legend><label>提供商显示名称</label><input name="api_provider" maxlength="40" placeholder="DeepSeek / OpenRouter / 自建平台"><label>API 基础地址</label><input name="api_base" maxlength="200" placeholder="https://api.example.com"><label>API Key</label><input name="api_key" type="password" maxlength="160" autocomplete="off" placeholder="留空保持原 Key"><label>余额获取方式</label><select name="balance_adapter"><option value="disabled">不查询余额</option><option value="deepseek">DeepSeek 官方预设</option><option value="custom">自定义 HTTP 接口</option></select><section id="custom"><label>余额接口完整地址</label><input name="balance_url" maxlength="240"><div class="row"><div><label>请求方法</label><select name="balance_method"><option>GET</option><option>POST</option></select></div><div><label>鉴权方式</label><select name="balance_auth"><option value="bearer">Bearer</option><option value="header">自定义请求头</option><option value="query">URL 参数</option><option value="none">无鉴权</option></select></div></div><label>请求头名 / 参数名</label><input name="balance_auth_name" maxlength="64" placeholder="Authorization"><label>余额 JSON 路径</label><input name="balance_value_path" maxlength="160" placeholder="data.balance"><div class="row"><div><label>固定单位</label><input name="balance_unit" maxlength="16" placeholder="CNY"></div><div><label>数值倍率</label><input name="balance_scale" type="number" step="0.000001"></div></div><label>单位 JSON 路径（可选）</label><input name="balance_unit_path" maxlength="160"><label>POST JSON（可选）</label><textarea name="balance_body" maxlength="512" placeholder="留空保持原内容；可使用 {{API_KEY}}"></textarea></section></fieldset>
<fieldset><legend>syna语音</legend><p class="tip">当前小智云能力由设备激活信息管理，无需与余额 API 共用 Key。</p><label>OTA / 配置服务地址（高级，可选）</label><input name="ota_url" maxlength="240"><p class="tip">留空使用固件默认官方地址。填写错误会导致下次启动无法取得小智云配置。</p></fieldset>
<fieldset><legend>电池校准</legend><label>电压倍率</label><input name="battery_scale" type="number" min="2.5" max="3.5" step="0.001"><p class="tip">默认 3.000。新倍率 = 当前倍率 × 万用表实测电压 ÷ 屏幕显示电压。</p></fieldset><button type="submit">保存设置</button></form><p class="tip">以后先按住 BOOT，再同时长按 KEY 约 3 秒即可再次进入；已保存的 Wi-Fi 不会被删除。</p></main><script>
const f=document.getElementById('form'),n=document.getElementById('notice'),custom=document.getElementById('custom');const show=m=>{n.textContent=m;n.style.display='block';scrollTo(0,0)};const sync=()=>custom.style.display=f.balance_adapter.value==='custom'?'block':'none';f.balance_adapter.onchange=sync;
fetch('/panel/config').then(r=>r.json()).then(c=>{for(const[k,v]of Object.entries(c)){if(f.elements[k]&&v!==null)f.elements[k].value=v}sync()}).catch(()=>show('读取设置失败，请刷新页面'));
fetch('/scan').then(r=>r.json()).then(x=>{const d=document.getElementById('networks');for(const a of(x.aps||[])){const o=document.createElement('option');o.value=String(a.ssid);d.appendChild(o)}}).catch(()=>{});
f.onsubmit=async e=>{e.preventDefault();const o=Object.fromEntries(new FormData(f));show('正在保存…');try{let r=await fetch('/panel/save',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(o)}),j=await r.json();if(!j.success)throw Error(j.error||'保存失败');if(o.ssid){r=await fetch('/submit',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({ssid:o.ssid,password:o.password})});j=await r.json();if(!j.success)throw Error(j.error||'Wi-Fi 连接失败')}else{r=await fetch('/exit',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});j=await r.json();if(!j.success)throw Error(j.error||'退出设置模式失败')}show('设置已保存。设备正在恢复联网，Syna-0721 将自动关闭。')}catch(x){show(x.message)}};sync();
</script></body></html>)HTML";

void AddString(cJSON* root, const char* name, const std::string& value) {
    cJSON_AddStringToObject(root, name, value.c_str());
}

bool ReadFloat(const char* ns, const char* key, float& value) {
    nvs_handle_t handle = 0;
    if (nvs_open(ns, NVS_READONLY, &handle) != ESP_OK) return false;
    size_t size = sizeof(value);
    const esp_err_t result = nvs_get_blob(handle, key, &value, &size);
    nvs_close(handle);
    return result == ESP_OK;
}

void WriteFloat(const char* ns, const char* key, float value) {
    nvs_handle_t handle = 0;
    if (nvs_open(ns, NVS_READWRITE, &handle) != ESP_OK) return;
    if (nvs_set_blob(handle, key, &value, sizeof(value)) == ESP_OK) nvs_commit(handle);
    nvs_close(handle);
}

void SetIfPresent(Settings& settings, const cJSON* root, const char* json_name,
                  const char* key, bool allow_empty = true) {
    const cJSON* item = cJSON_GetObjectItemCaseSensitive(root, json_name);
    if (!cJSON_IsString(item) || item->valuestring == nullptr) return;
    if (allow_empty || item->valuestring[0] != '\0') settings.SetString(key, item->valuestring);
}

}  // namespace

SettingsPortalService& SettingsPortalService::GetInstance() {
    static SettingsPortalService instance;
    return instance;
}

esp_err_t SettingsPortalService::ServeRoot(httpd_req_t* request) {
    httpd_resp_set_type(request, "text/html; charset=utf-8");
    httpd_resp_set_hdr(request, "Cache-Control", "no-store");
    httpd_resp_set_hdr(request, "Connection", "close");
    return httpd_resp_send(request, kSettingsPage, HTTPD_RESP_USE_STRLEN);
}

void SettingsPortalService::RegisterHandlers(httpd_handle_t server) {
    const httpd_uri_t config = {
        .uri = "/panel/config", .method = HTTP_GET,
        .handler = HandleConfig, .user_ctx = this};
    const httpd_uri_t save = {
        .uri = "/panel/save", .method = HTTP_POST,
        .handler = HandleSave, .user_ctx = this};
    ESP_ERROR_CHECK(httpd_register_uri_handler(server, &config));
    ESP_ERROR_CHECK(httpd_register_uri_handler(server, &save));
}

float SettingsPortalService::GetBatteryScale() {
    const int cached = battery_scale_milli_.load();
    if (cached != 0) return cached / 1000.0f;
    float scale = 3.0f;
    if (!ReadFloat("wifi-config", "bat-scale", scale) || !std::isfinite(scale) ||
        scale < 2.5f || scale > 3.5f) scale = 3.0f;
    battery_scale_milli_.store(static_cast<int>(std::lround(scale * 1000.0f)));
    return scale;
}

esp_err_t SettingsPortalService::HandleConfig(httpd_req_t* request) {
    Settings panel("wifi-config");
    Settings wifi("wifi");
    cJSON* root = cJSON_CreateObject();
    AddString(root, "api_provider", panel.GetString("api-provider", "API"));
    AddString(root, "api_base", panel.GetString("api-base", ""));
    AddString(root, "balance_adapter", panel.GetString("bal-adapter", "disabled"));
    AddString(root, "balance_url", panel.GetString("bal-url", ""));
    AddString(root, "balance_method", panel.GetString("bal-method", "GET"));
    AddString(root, "balance_auth", panel.GetString("bal-auth", "bearer"));
    AddString(root, "balance_auth_name", panel.GetString("bal-hname", "Authorization"));
    AddString(root, "balance_value_path", panel.GetString("bal-path", "data.balance"));
    AddString(root, "balance_unit", panel.GetString("bal-unit", ""));
    AddString(root, "balance_unit_path", panel.GetString("bal-upath", ""));
    cJSON_AddNumberToObject(root, "balance_scale", [&]() { float v = 1.0f; ReadFloat("wifi-config", "bal-scale", v); return v; }());
    cJSON_AddNumberToObject(root, "battery_scale", SettingsPortalService::GetInstance().GetBatteryScale());
    AddString(root, "ota_url", wifi.GetString("ota_url", ""));
    char* json = cJSON_PrintUnformatted(root);
    cJSON_Delete(root);
    httpd_resp_set_type(request, "application/json");
    httpd_resp_set_hdr(request, "Cache-Control", "no-store");
    const esp_err_t result = httpd_resp_send(request, json, HTTPD_RESP_USE_STRLEN);
    cJSON_free(json);
    return result;
}

esp_err_t SettingsPortalService::HandleSave(httpd_req_t* request) {
    if (request->content_len == 0 || request->content_len > kMaximumBodyBytes) {
        httpd_resp_send_err(request, HTTPD_400_BAD_REQUEST, "Invalid payload size");
        return ESP_FAIL;
    }
    std::vector<char> body(request->content_len + 1);
    size_t received = 0;
    while (received < request->content_len) {
        const int count = httpd_req_recv(request, body.data() + received,
                                         request->content_len - received);
        if (count <= 0) {
            httpd_resp_send_err(request, HTTPD_400_BAD_REQUEST, "Failed to receive payload");
            return ESP_FAIL;
        }
        received += count;
    }
    body[received] = '\0';
    cJSON* root = cJSON_Parse(body.data());
    if (root == nullptr) {
        httpd_resp_send_err(request, HTTPD_400_BAD_REQUEST, "Invalid JSON");
        return ESP_FAIL;
    }
    {
        Settings panel("wifi-config", true);
        SetIfPresent(panel, root, "reporter_token", "reporter", false);
        SetIfPresent(panel, root, "api_provider", "api-provider");
        SetIfPresent(panel, root, "api_base", "api-base");
        SetIfPresent(panel, root, "api_key", "api-key", false);
        SetIfPresent(panel, root, "balance_adapter", "bal-adapter");
        SetIfPresent(panel, root, "balance_url", "bal-url");
        SetIfPresent(panel, root, "balance_method", "bal-method");
        SetIfPresent(panel, root, "balance_auth", "bal-auth");
        SetIfPresent(panel, root, "balance_auth_name", "bal-hname");
        SetIfPresent(panel, root, "balance_value_path", "bal-path");
        SetIfPresent(panel, root, "balance_unit", "bal-unit");
        SetIfPresent(panel, root, "balance_unit_path", "bal-upath");
        SetIfPresent(panel, root, "balance_body", "bal-body", false);
    }
    {
        Settings wifi("wifi", true);
        SetIfPresent(wifi, root, "ota_url", "ota_url");
    }
    const cJSON* balance_scale = cJSON_GetObjectItemCaseSensitive(root, "balance_scale");
    if (cJSON_IsString(balance_scale) && balance_scale->valuestring) {
        const float value = strtof(balance_scale->valuestring, nullptr);
        if (std::isfinite(value) && value != 0 && std::fabs(value) <= 1000000) {
            WriteFloat("wifi-config", "bal-scale", value);
        }
    }
    const cJSON* battery_scale = cJSON_GetObjectItemCaseSensitive(root, "battery_scale");
    if (cJSON_IsString(battery_scale) && battery_scale->valuestring) {
        const float value = strtof(battery_scale->valuestring, nullptr);
        if (std::isfinite(value) && value >= 2.5f && value <= 3.5f) {
            WriteFloat("wifi-config", "bat-scale", value);
            SettingsPortalService::GetInstance().battery_scale_milli_.store(
                static_cast<int>(std::lround(value * 1000.0f)));
        }
    }
    cJSON_Delete(root);
    ReporterService::GetInstance().RequestReload();
    ApiBalanceService::GetInstance().RequestRefresh();
    ESP_LOGI(kTag, "Settings saved; secret values were not echoed");
    httpd_resp_set_type(request, "application/json");
    return httpd_resp_sendstr(request, "{\"success\":true}");
}

extern "C" esp_err_t wifi_config_custom_root(httpd_req_t* request) {
    return SettingsPortalService::GetInstance().ServeRoot(request);
}

extern "C" void wifi_config_register_custom_handlers(httpd_handle_t server) {
    SettingsPortalService::GetInstance().RegisterHandlers(server);
}

extern "C" const char* wifi_config_custom_ssid() {
    return "Syna-0721";
}
