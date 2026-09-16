# Windows 一体安装器

源码入口 installer_ui.py，后台协议 worker.py，独立后端入口 backend_entry.py。发布目录不携带 Payload、生成清单或 EXE。

构建见 [统一说明](../../docs/BUILD.md)。build_standalone.py 必须提供 --firmware-build 和 --reporter-exe；prepare_payload.py 同样接受这两个参数，可单独准备测试文件。

生成后运行 dist/SynaInstaller-1.0.0.exe。只读自检命令：SynaInstaller-1.0.0.exe --self-test <绝对报告路径.json>，不安装或刷写。

三种模式为仅安装 Reporter、保留配置升级、首次安装。仅安装不访问串口；升级先备份和核对分区，只写应用；首次安装须确认清除，完整备份校验后才擦除。结束时读回校验并复位。失败不自动回滚，请保留备份。

后端采用 ASCII JSON 转义传递中文消息，避免 Windows 代码页造成错误；最终成功需要完成事件和正常退出两者同时满足。

当前作者本机独立版 Reporter 安装和保留配置刷写均验收成功；新目录的重新构建、另一台电脑、首次安装及语音实测仍需验证。备份在 %LOCALAPPDATA%/SynaInstaller/Backups，含私人数据，请勿提交源码仓库。
