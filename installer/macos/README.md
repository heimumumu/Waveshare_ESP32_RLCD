# Mac 一键安装器

Copyright (c) 2026 黑沐。安装器原创代码使用项目 MIT 许可。

`Installer.swift` 提供原生 AppKit 窗口；`worker.py` 负责发布文件校验、设备备份、
分区判断、刷写及 Reporter 原子替换。PyInstaller 将 Python 和 esptool 一并打包，
安装过程无需下载依赖。

## 构建

在 Apple 芯片 Mac 上准备 Python 3.12、Xcode Command Line Tools、已验证的
Reporter `.app` 和 ESP-IDF 固件构建目录。构建不会自动刷写设备。

```bash
python3.12 -m venv .codex-tmp/installer-venv
.codex-tmp/installer-venv/bin/pip install -r installer/macos/requirements-build.txt
.codex-tmp/installer-venv/bin/python installer/macos/build.py \
  --worker-python .codex-tmp/installer-venv/bin/python \
  --firmware-build /path/to/xiaozhi/build \
  --reporter-app reporter/dist-macos/SynaReporter.app
```

默认工具链及固件路径采用本项目本机约定。构建还会读取对应 ESP-IDF LICENSE、
固件依赖目录、Reporter `.venv-macos` 中的许可证；缺失时需先完成项目环境准备。
Python 运行时许可证、依赖许可证及字体署名均收集到 Payload/Legal。

发布私钥位于 `~/Library/Application Support/SynaReleaseSigning/private.pem`，
不会放入安装包。公钥使用 `release/keys/syna-release-public.pem`，其 SHA-256
固定在 worker 内。更换签名身份时必须同步公钥指纹并通过官方渠道通知用户。

输出：`release/artifacts/v1.0.0-macos-installer/`，包含 DMG、使用说明和签名清单。
安装器暂未使用 Developer ID 签名或苹果公证；不要将项目发布签名描述为苹果认证。

## 验证

```bash
python3.12 -m unittest discover -s installer/macos -p 'test_*.py' -v
python3 release/sign_release.py verify release/artifacts/v1.0.0-macos-installer
```

测试覆盖 OTA 双分区选择、损坏分区/OTA 记录、错误板型、链接越界、安装文件
变更、备份校验失败禁止写入、首次安装的备份顺序及拒绝覆盖无关应用。
实际安装检查记录见 `VERIFICATION.md`。用户操作见 [使用说明](使用说明.md)。
