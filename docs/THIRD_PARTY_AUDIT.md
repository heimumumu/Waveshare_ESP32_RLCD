# 第三方分发核对（2026-09-16）

## 已核对和补齐

- 从验证环境记录 39 个 Python 发行包。此数字是环境清单，不宣称每个包都进入了最终 EXE。
- 读取三份 PyInstaller Analysis 清单，分别记录 Reporter、安装器、后端的模块/二进制/数据文件；不是只列 requirements.txt。
- 实际 Qt 动态库包括 Core、Gui、Widgets、Network、Svg；还需考虑同包平台及图片插件。
- 发现 Qt wheel 元数据仅收录商业许可证，原打包器因此漏掉 LGPL/GPL 正文。已从 Qt 6.8.3 上游补齐 LGPLv3、GPLv3、GPLv2。
- 补齐 pyserial 3.5、PyWinRT 3.2.1 上游许可证及 CPython 运行时 LICENSE。
- 从 ESP-IDF 构建描述收集 177 个配置组件的许可证。配置组件不等于每个都贡献了最终链接代码，因此本清单是保守收集，尚非逐符号 SBOM。
- 从实际配置和构建日志确认 ESP-SR 2.4.7、mn7_cn/fst，记录 6 个模型文件哈希。
- Reporter spec 和安装器构建脚本已接入上述补充材料及源码获取说明，防止后续构建仅依赖 wheel 元数据。

机器可读记录：THIRD_PARTY_AUDIT.json；许可材料：`release/licenses/windows-audit/`；收集脚本：`release/audit_licenses.py`。文件均来自明确版本的上游或实际构建环境，不改写原许可。

## 后续材料补充

已取得版本化 Qt Base、SVG、imageformats、PySide/Shiboken、esptool、Mesa、LLVM、OpenSSL 等源码包，并解析 Qt attribution 及其引用的原许可证。材料与哈希记录在 THIRD_PARTY_SOURCE_ARCHIVES.json。源码包、项目源码 ZIP 和授权说明将随候选发布目录一起提供；最终产物及验证结果见 RELEASE_CANDIDATE.json。

Qt 各模块采用保守范围收集，包含未必进入当前二进制的示例/测试声明。不得据此声称所有列出的第三方均被当前程序使用。

## 正式分发仍需核对

1. 对照最终包确认对应源码、原许可与项目构建材料均一并提供，不要仅上传 EXE。
2. 修改后的 Qt 实测重构建仍未进行；现有脚本提供重构建路线，不宣称已验证任意兼容库替换。
3. Microsoft VC Runtime 的发布者适用许可需由作者核对；现有安装环境不能代替授权确认，见 RUNTIME_NOTICES.md。
4. Mesa/LLVM 版本已从实际 DLL 核对，但未独立复现其厂商补丁和构建选项；保留来源及限制。
5. 字体有来源记录；图片素材沿用作者此前确认，尚未逐文件重新做来源归档。

## 查阅依据

- Qt for Python 第三方说明：https://doc.qt.io/qtforpython-6.8/licenses.html
- Qt 6.8.3 LGPLv3 正文：https://raw.githubusercontent.com/qt/qtbase/v6.8.3/LICENSES/LGPL-3.0-only.txt
- esptool 5.4.0：https://github.com/espressif/esptool/blob/v5.4.0/LICENSE
- pyserial 3.5：https://raw.githubusercontent.com/pyserial/pyserial/v3.5/LICENSE.txt
- PyWinRT 3.2.1：https://raw.githubusercontent.com/pywinrt/pywinrt/v3.2.1/LICENSE

本次未修改开发目录、未安装、未刷机、未上传。结论是“发现并修补许可收集缺漏，仍有明确分发待办”，不是“所有第三方已审核通过”。
