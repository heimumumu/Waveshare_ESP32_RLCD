# Windows 附带运行时记录

本记录针对 2026-09-16 独立构建，不将构建机全部安装的软件视为程序依赖。

## 软件 OpenGL

PyInstaller 自动收集 PySide6 的 `opengl32sw.dll`。实际 DLL 含 Mesa 11.2.2 与 LLVM 3.6.2 字符串，Qt 文档确认该文件属于 llvmpipe 软件 OpenGL 实现。源码包及原许可证随候选包提供；这并不等于已经独立重建或核对厂商补丁。

来源：https://doc.qt.io/qt-6.8/windows-graphics.html 、https://wiki.qt.io/MesaLlvmpipe 。

## OpenSSL

CPython 3.11.0 环境报告 OpenSSL 1.1.1q，打包清单含 libssl-1_1.dll / libcrypto-1_1.dll；保留对应原始许可并提供上游 1.1.1q 源码包。cryptography 包另保留其自带许可，不能用 CPython 的 OpenSSL 版本代替所有静态链接依赖的版本。

## Microsoft VC Runtime

最终清单中存在 Microsoft VC Runtime DLL。它们不是 MIT/Qt 开源代码，不列入可任意重新授权的源码。微软将 VC Runtime 的再分发与适用的 Visual Studio/软件许可条款关联。

来源：https://learn.microsoft.com/en-us/cpp/windows/redistributing-visual-cpp-files?view=msvc-170 。

本次记录文件版本、来源路径类型和哈希用于追溯；并未自动确认发布者的 Visual Studio 授权状态。作者发布前需核对自身适用许可及允许分发文件清单。不能因构建机装有 Visual Studio 或 DLL 可下载就把该项标为已获授权。

## 保守收集

Qt 模块源码含测试、示例和平台实现，notice 收集采取保守范围。材料中出现某项许可并不意味着该组件必然链接进实际 EXE；以实际二进制清单及具体实现为准。
