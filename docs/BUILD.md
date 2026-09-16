# 构建说明

以下命令从项目根目录开始执行。验证结果见 [构建记录](BUILD_VALIDATION.md)。

## Reporter

使用 Python 3.11。Windows 在项目根目录执行：

```powershell
python -m venv reporter/.venv
reporter/.venv/Scripts/python.exe -m pip install -r reporter/requirements-build.txt
Push-Location reporter
.venv/Scripts/python.exe -m PyInstaller --noconfirm --distpath dist --workpath build SynaReporter.spec
Pop-Location
```

输出为 `reporter/dist/SynaReporter.exe`。源码运行入口为 `reporter/reporter.py`；Mac 构建入口为 `reporter/build_macos.command`。

## ESP-IDF 固件

1. 安装 Git、ESP-IDF **6.0.2** 和 ESP32-S3 工具链，激活官方 ESP-IDF 环境。
2. 将 `xiaozhi/upstream.lock` 指定的仓库检出到锁定提交，执行子模块初始化。Windows 源码与构建路径应使用无空格 ASCII 路径。
3. 在已激活环境安装 `xiaozhi/requirements-firmware.txt`。
4. 运行 `python <本项目>/xiaozhi/apply_ui_overlay.py <上游目录> --phase source`。
5. 在上游目录执行下列命令，解析组件后应用组件补丁，再编译：

```powershell
idf.py -DIDF_TARGET=esp32s3 '-DSDKCONFIG_DEFAULTS=sdkconfig.defaults;syna.sdkconfig.defaults' -DBOARD_NAME=esp32-s3-rlcd-4.2 reconfigure
python <本项目>/xiaozhi/apply_ui_overlay.py <上游目录> --phase components
python scripts/build.py waveshare/esp32-s3-rlcd-4.2 --name esp32-s3-rlcd-4.2 --language zh-CN
```

`<本项目>`、`<上游目录>` 为需要替换的路径。输出位于上游 `build` 目录。`build_windows.ps1` 是作者既有工具目录布局的便捷封装；通用环境优先使用上述手动入口。`build_macos.sh` 接受上游路径及 `SYNA_IDF_ROOT`。

## Windows 一体安装器

先完成 Reporter 和固件构建，再运行：

```powershell
reporter/.venv/Scripts/python.exe -m pip install esptool==5.4.0
reporter/.venv/Scripts/python.exe installer/windows/build_standalone.py --firmware-build C:/syna/xiaozhi/build --reporter-exe reporter/dist/SynaReporter.exe
```

将 `C:/syna/xiaozhi/build` 替换为固件输出目录。安装器输出位于 `installer/windows/dist`。

准备 Payload 后可在 `installer/windows` 目录运行 `python -m unittest -v test_installer.py`。测试使用 PySide6；固件主机测试另需 C++ 编译器，现有脚本的路径设置见脚本头部。

固件主机测试可设置 `SYNA_FIRMWARE_SOURCE` 指向已应用补丁的上游源码，设置 `SYNA_VCVARS` 指向 Visual Studio 的 `vcvars64.bat`。

## 模拟器

需要 CMake、SDL2 和 LVGL **9.5.0**。将该版本完整源码放到 `simulator/vendor/lvgl-9.5.0`，保留原许可证，使用 `simulator/CMakeLists.txt` 构建。字体源和许可证随源码保留；推荐 Python 字体生成器。PowerShell 模拟器脚本仍包含作者本地路径，使用前调整，或者直接通过 CMake 配置 SDL2 搜索路径。
