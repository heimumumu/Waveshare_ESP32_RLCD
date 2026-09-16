# ESP-IDF 固件

当前实现通过 `apply_ui_overlay.py` 将板级源码及单轮对话补丁应用到 `upstream.lock` 锁定的小智上游。

统一构建步骤见 [构建说明](../docs/BUILD.md)。Windows 与 Mac 均使用 Python 覆盖脚本；旧 PowerShell 覆盖脚本未包含在此次整理目录中，避免两份补丁不同步。

`build_windows.ps1` 和 `enter-idf.ps1` 保留作者工具目录布局的默认值，可通过参数调整；若已有官方 ESP-IDF 6.0.2 环境，使用构建说明中的手动命令，不必复用作者目录。

板型：waveshare/esp32-s3-rlcd-4.2，16 MB Flash、8 MB PSRAM。升级前必须备份及核对分区。

单轮对话：默认自动断句，回答期间关闭语音处理与唤醒词检测，TTS 结束且本地播放完成后回待机。按键主动停止仍保留，麦克风增益未因本轮改动而调整。已编译刷入，语音实测仍待进行。
