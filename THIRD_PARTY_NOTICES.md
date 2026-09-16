# 第三方版权与授权

本项目是基于第三方组件的集成及定制项目。根目录 MIT 仅覆盖黑沐有权授权的原创代码及改动，
不覆盖第三方代码和素材的原有权利。修改第三方文件时不得删除原版权声明。

2026-09-16 实际构建核对见 [分发核对记录](docs/THIRD_PARTY_AUDIT.md)，
对应源码及重新构建路线见 [第三方源码说明](docs/THIRD_PARTY_SOURCES.md)。补充许可已归档在
`release/licenses/windows-audit/` 和 `release/licenses/upstream-source-notices/`。
更新的打包脚本将这些材料随包携带；请以最新候选包及其校验清单为准，不要使用补充材料之前的旧 EXE。

| 组件 | 来源与许可证 |
| --- | --- |
| 小智 ESP32 底座 | 78/xiaozhi-esp32，版本见 xiaozhi/upstream.lock；MIT，Copyright 2025 Shenzhen Xinzhi Future Technology Co., Ltd. / Project Contributors |
| LVGL | 开发者取得 9.5.0 上游源码；许可证副本 release/licenses/lvgl-9.5.0-LICENCE.txt；MIT |
| esp_codec_dev | ESP-IDF 构建时解析的组件，保留该组件实际版本的 Apache-2.0 许可证；旧 Arduino lib 目录不在此次源码导出中 |
| 其他库及运行时 | 保留目录内原许可证；Reporter 分发还包含 Python、PyInstaller 及 requirements.txt 中依赖的授权 |
| Syna UI 位图字体 | 数字/西文来自 Arimo，中文点阵来自 GNU Unifont 16.0.04，开机大字来自 Noto Sans CJK SC；统一按 SIL OFL 1.1 使用；见 simulator/assets/fonts/SOURCE.md 及对应许可证；不适用根目录 MIT |
| 图标与背景 | 黑沐于 2026-09-13 确认自行制作；其原创部分按本项目 MIT 授权 |
| 自定义唤醒词 | 配置词 ni hao xi na；底层为乐鑫 ESP-SR MultiNet7，模型不是黑沐原创；见 release/licenses/esp-sr-2.4.7-LICENSE.txt |

小智许可证副本见 release/licenses/xiaozhi-MIT.txt。源码中原有授权头、许可证和 NOTICE 均保留。
公开完整固件和素材包前，仍需完成资源来源及 ESP-IDF/语音模型依赖的逐项分发核查。
不得将第三方组件宣称为黑沐独立原创，也不得把未核验资源直接标为 MIT。

## 字体核查与替换

原生成脚本使用 Windows Arial / SimSun，现使用随项目提供的 Arimo、GNU Unifont 和 Noto Sans CJK SC。
小字号中文采用 Unifont 原生 16 像素点阵，西文和数字单独使用 Arimo；28 像素开机署名保留 Noto。
Unifont 上游字体为双许可，本项目选择 SIL OFL 1.1，原始 COPYING 完整保留。
新位图字体称为 Syna UI，生成器为 MIT，字库数据仍为 OFL，附原作者信息与许可证。
旧字库仅保留在本地备份中，不应上传或用于正式发布。新的 Python 生成器不依赖 Windows 字体。

## 唤醒词来源

固定小智上游声明依赖 espressif/esp-sr ~2.4.7；当前板级配置使用
CONFIG_SR_MN_CN_MULTINET7_QUANT=y，识别命令为 ni hao xi na。
这属于用乐鑫 MultiNet7 配置识别词，没有发现单独训练的“你好希娜”模型。
ESP-SR 2.4.7 的 ESPRESSIF MIT 许可限定用于乐鑫产品，允许相应使用和销售，须保留许可。
它不是无硬件限制的标准 MIT，禁止将其改标为本项目 MIT。
来源：https://components.espressif.com/components/espressif/esp-sr/versions/2.4.7/license
正式构建时须保存实际解析出的组件版本、模型文件及各自许可；本源码目录不包含开发机的构建缓存或设备模型镜像。
# Windows 状态窗口新增依赖

Windows UI 使用 PySide6 Essentials 6.8.3、Shiboken6 和随附 Qt Core/Gui/Widgets/Network，
来源：https://download.qt.io/official_releases/QtForPython/ 。项目原创窗口代码采用 MIT，
这些依赖保持各自 LGPL/GPL/第三方许可，不被项目 MIT 重新授权。
官方说明：https://doc.qt.io/qtforpython-6.8/licenses.html 。
构建配置收集 Python 包元数据和许可。当前 Windows 界面及安装已在作者电脑验收，
但公开分发前仍须针对最终成品复核 Qt 许可证、对应源码取得方式与动态库替换/
重新构建说明。运行测试通过不表示第三方分发材料的核对已经完成。
