# Windows 状态窗口

Copyright (c) 2026 黑沐。原创代码采用 MIT。

`windows_ui.py` 使用 PySide6 Essentials，将 `native_ui.swift` 的 760 × 750
布局、卡片位置、配色、文案和作者信息移植到 Windows；Qt 按系统 DPI 缩放。
字体使用 Segoe UI，中文优先回退到 Microsoft YaHei UI / Microsoft YaHei。未更改 Mac 应用。
工作区较小时窗口自动缩小并提供滚动，保留原 760×750 内容布局，底部操作仍可到达。

## 使用

在 Windows 执行 `start.ps1`，或双击本次新构建的 `dist/SynaReporter.exe`。
无参数启动显示状态窗口，`--worker`、`--self-test`、`--no-supervisor` 等命令行行为保留。

- 状态每秒异步查询本机 HTTP；断开后清除旧数值。不支持的传感器显示 `—`。
- 可启动、停止本窗口创建的服务；外部进程提供服务时仅显示数据。
- 关闭窗口隐藏到系统托盘，点击托盘或再次打开程序显示窗口；托盘菜单可退出。
- 工作进程意外结束时退避重启；主动停止和退出不会重启。
- 登录启动使用当前用户 Run 注册表项，不要求窗口以管理员运行。
- 检测到旧版 HKLM 启动项时提示先运行新版安装程序，避免开关显示关闭但仍自动启动。
- 关于作者含黑沐、B站 UID 386856267、QQ 3091479711、版本和官方仓库/发布链接。

安装脚本已改为移除旧 HKLM 启动项并设置 HKCU；不同管理员账户提权安装的归属，
以及卸载其他用户启动项的问题，需在后续 Windows 一体安装器中验证和完善。

## 已验证与待验证

2026-09-13：在 Mac 的独立 Python 3.12 / PySide6 Essentials 6.8.3 环境中，
完成界面离屏渲染并人工检查；7 项测试通过，包含真实子进程启停、崩溃恢复、
外部进程保护、缺失指标、断线清理、注册表模拟测试。异步请求现有 Reporter
接口成功，未启动或停止现有 Mac 服务。

以上为 9 月 13 日的历史记录，Windows 进展见下方补充。

### 2026-09-14 Windows 本机验证

- 环境：Windows x64，Python 3.11.9，PySide6 Essentials 6.8.3；已新建 Windows 虚拟环境。
- 修改前备份：`备份_Windows实机验证前_20260914_102730/`，保留旧 EXE、安装包和原 Reporter。
- 修复高缩放时固定窗口超出工作区的问题，并明确中文回退字体；断开服务时同时清除旧电脑名称。
- Reporter 回归测试共 46 项：33 项通过，13 项 macOS 专用测试跳过；窗口测试为 8 项。
- 本机 1920×1080 屏幕正常显示；通过 `QT_SCALE_FACTOR=1/1.5/2` 验证三种缩放下窗口均在工作区内，并验证滚动后底部控件可达。这不等同于实际切换系统 DPI 或多显示器验收。
- 源码窗口实测真实 worker/HTTP、关闭到托盘、第二次启动唤回原窗口且不重复 worker、崩溃后恢复、停止后清空数据、重新启动以及正常退出无残留 worker。
- 实测 HKCU 自启动值开启/关闭并恢复测试前原值；作者弹窗内容和两个链接目标正确，未实际打开外部网站。
- 新 EXE 已构建并通过 `--self-test`；实测其窗口、真实后台 HTTP、托盘隐藏和重复启动唤回。
- CPU/GPU/内存/磁盘、CPU/GPU 温度在本机有数据，周额度有数据；短周期额度缺失时保持 `—`。
- 源码及新 EXE 均收到 1 台开发板的发现请求；这不能代替用户确认开发板已选择此电脑及屏幕显示正确。网易云播放联调尚未完成。

当前新程序：`dist/SynaReporter.exe`，41,895,786 字节（约 40 MiB）。
SHA-256：`eac0c514f55d1dd97b44914d445ca95dd512976f782b2c3e336c741119b9edd6`。

**`release/SynaReporter-Setup-1.0.0.exe` 仍为 9 月 5 日旧安装包，不含新窗口。**
本轮先交付本地可运行的新 EXE；安装脚本的跨管理员账户归属、卸载/升级以及 Qt 分发许可仍需处理，不能把旧安装包作为本轮产物。

待验收：实际系统 DPI 切换、多显示器、托盘鼠标交互、任务管理器禁用启动项、重新登录/重启、睡眠恢复、长时间运行、开发板屏幕及网易云播放、安装/升级/卸载。
本机临时测试脚本、JSON 结果、截图和构建日志位于 `.codex-tmp/`，不作为公开发行内容。

```powershell
python -m unittest discover -s reporter -p test_windows_ui.py -v
powershell -ExecutionPolicy Bypass -File reporter/build_release.ps1 -Version 1.0.0
```

Qt/PySide 保留独立许可证，参见根目录 THIRD_PARTY_NOTICES.md。
