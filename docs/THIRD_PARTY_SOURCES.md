# 第三方来源与重新构建

本项目使用 Qt/PySide6、esptool 及其他第三方软件。原创源码的 MIT 许可不改变第三方的许可；不得把整个安装器及所含依赖一概称为 MIT。

| 组件 | 验证版本 | 对应源码入口 |
| --- | --- | --- |
| Qt Core/Gui/Widgets/Network、平台插件 | 6.8.3 | https://github.com/qt/qtbase/tree/v6.8.3 |
| Qt SVG | 6.8.3 | https://github.com/qt/qtsvg/tree/v6.8.3 |
| Qt imageformats 插件 | 6.8.3 | https://download.qt.io/archive/qt/6.8/6.8.3/submodules/ |
| PySide6 / Shiboken6 | 6.8.3 | https://github.com/qt/pyside-setup/tree/v6.8.3 |
| esptool | 5.4.0 | https://github.com/espressif/esptool/tree/v5.4.0 |
| pyserial | 3.5 | https://github.com/pyserial/pyserial/tree/v3.5 |
| PyWinRT（runtime/Foundation/Collections/Media.Control） | 3.2.1 | https://github.com/pywinrt/pywinrt/tree/v3.2.1 |
| CPython | 3.11.0 | https://github.com/python/cpython/tree/v3.11.0 |
| PyInstaller | 6.21.0 | https://github.com/pyinstaller/pyinstaller/tree/v6.21.0 |
| ESP-IDF | 6.0.2 | https://github.com/espressif/esp-idf/tree/v6.0.2 |
| OpenSSL（CPython DLL） | 1.1.1q | https://github.com/openssl/openssl/tree/OpenSSL_1_1_1q |
| Mesa / LLVM（opengl32sw.dll） | 11.2.2 / 3.6.2 | https://archive.mesa3d.org/older-versions/11.x/11.2.2/ 与 https://releases.llvm.org/3.6.2/ |

更多依赖版本见 `release/build-info/windows-validation-20260916/`，发行元数据、许可证文件及来源 URL 见 `docs/THIRD_PARTY_AUDIT.json`。这些入口用于定位源码；仅给出链接不代表已经完成最终二进制的全部源码分发要求。

## 随候选包提供的源码

候选发布目录的 `third-party-sources/` 实际提供 Qt Base、SVG、imageformats、PySide/Shiboken、esptool、Mesa、LLVM、OpenSSL 版本化上游源码压缩包，不仅是下载链接。逐包 URL、大小与 SHA256 见 `SOURCE_ARCHIVES.json`；许可及 attribution 从这些压缩包原样提取到 `release/licenses/upstream-source-notices/`。本项目应用源码另放在 `Syna-source-1.0.0.zip`。

Qt 官方发布的模块源码包与 GitHub 标签源码用于保存对应版本。Mesa/LLVM 版本从实际 DLL 的内嵌版本字符串核对，不能据此声称已经复现该预编译 DLL 的全部构建选项或厂商补丁。

## Qt 与修改后的库

Qt/PySide6 使用开源许可，不依据随 wheel 出现的商业许可文本主张商业授权。LGPLv3 和其引用的 GPLv3 正文随附在 `release/licenses/windows-audit/supplemental/Qt-6.8.3/`。

项目不禁止用户为修改第三方库而调试、逆向分析、替换或重新构建程序。Syna 的 Python、安装后端及打包脚本以源码提供。

重新组合路线：在独立 Python 环境按锁定版本安装依赖，将自行构建的兼容 PySide6/Shiboken6/Qt 安装到该环境，再按 `docs/BUILD.md` 构建 Reporter 和安装器。PySide 构建参考 https://doc.qt.io/qtforpython-6.8/building_from_source/index.html 。不要通过修改一次性临时解压目录来假定已经验证库替换。

当前单文件产物尚未用修改后的 Qt 实测重构建；发布者仍需选择并落实相应源码及重新组合材料的交付方式。最终发布必须带有许可证，并保证对应源码及构建材料实际可取得。

发布本候选目录时应将应用源码包、上述第三方源码及构建说明一并提供，并保留可访问的下载位置。不要仅上传 EXE 后声称对应源码已经随附。尚未完成修改 Qt 后的实测重构建，相关限制必须保留。

## esptool

esptool 的 GPLv2-or-later 保持有效；其附带 stub 另有 Apache/MIT 文件，均保留。本项目后端在子进程中调用刷写功能，但后端程序本身也打包并导入 esptool，不能仅凭“使用子进程”声称没有 GPL 分发义务。发布时应随同提供对应 esptool 源码、本项目后端源码、依赖及构建说明，并核对最终发布组合的分发方式。

## 模型和字体

ESP-SR 2.4.7 的实际配置模型是 `mn7_cn` 与 `fst`。`THIRD_PARTY_AUDIT.json` 记录原模型文件哈希；模型不是本项目原创，许可包含乐鑫产品使用范围。字体来源和哈希见 `simulator/assets/fonts/SOURCE.md`，保留 OFL/原始 COPYING。

此说明是分发工程记录；未完成项见 THIRD_PARTY_AUDIT.md，不代表最终包已全部核准发布。
