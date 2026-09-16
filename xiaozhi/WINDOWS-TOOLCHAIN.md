# Windows 工具链说明

需要 ESP-IDF 6.0.2、ESP32-S3 编译器和 Git。优先采用 [通用构建步骤](../docs/BUILD.md)，在官方 ESP-IDF 已激活的 PowerShell 环境中执行。

作者便捷脚本默认使用 D:/syna-toolchains，且尝试从作者 Visual Studio 目录寻找 Git；这些是示例布局，不代表你的电脑已安装。把 Git 加入 PATH，并通过 SourceRoot / ToolchainRoot 参数指向自己的 ASCII 路径。不要复制他人的 Python 虚拟环境。

本开源快照未包含工具链、上游源码、私有配置及历史日志。正式发布前仍需在干净 Windows 环境完成整个构建链验收。
