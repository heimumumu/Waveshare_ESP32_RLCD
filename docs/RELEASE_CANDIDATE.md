# 1.0.0 本地候选发布包

本轮产物为发布前审核材料，未上传、未签名。2026-09-16 已完成本机 Reporter 安装与保留配置刷机及独立读回复核，用户确认正常亮屏、自动联网、电脑绑定保留及性能数据持续刷新，详见 HARDWARE_ACCEPTANCE.json。它不是已经正式发布的版本。

## 内容

- Windows 一体安装器及单独 Reporter，已重新构建并通过只读自检。
- 固件应用镜像（不是完整 Flash 镜像）。
- 项目源码 ZIP，含构建脚本、版本记录和文档。
- 42 个版本化上游源码发行包，约 165 MB，包含 Qt/PySide、esptool 及 Python 依赖。
- Qt 的 67 条 attribution 及其引用的许可证；所有引用均已定位。
- `LICENSES/`、第三方说明、逐文件 `SHA256SUMS.json`。

机器可读产物哈希与自检证据见 RELEASE_CANDIDATE.json。Reporter 与安装器均逐文件验证了嵌入的 444 份授权材料，内容与当前源码目录一致。

## 复现流程

1. 按 BUILD.md 构建程序；用验证环境执行 `release/collect_source_archives.py --python-sources --output <源码包目录>` 收集对应发行包。
2. 用验证环境执行 `release/verify_candidate.py --validation-root <验证目录>`，该过程不安装或刷机。
3. 执行 `release/assemble_candidate.py --validation-root <验证目录> --output <新的空目录>`。

源码收集脚本从 Qt 官方发布目录、项目上游和 PyPI 读取固定版本。PyPI 源码包还与其发布元数据 SHA256 比较。Qt/GitHub 等下载内容记录 SHA256 以便后续核对；未将下载记录冒称发布者数字签名。

## 发布前保留事项

新产物本机安装、保留配置升级及上述运行检查已通过，不能据此视为所有功能验收通过。单轮语音、首次清除安装和另一台 Windows 测试仍待进行。RELEASE_CANDIDATE.json 保留构建时只读自检记录，后续实机结果另见 HARDWARE_ACCEPTANCE.json。已有候选包内文档是打包时快照，正式发布前需重新汇总更新后的文档与哈希清单。

修改 Qt 后的重新组合实测尚未完成；Microsoft VC Runtime 的适用再分发许可由作者核对。Mesa/LLVM 仅核对版本和来源，未独立重建厂商 DLL。图片来源沿用作者既有确认。

正式发布时应一起提供程序、项目源码及第三方源码材料，不应只上传单个 EXE。SHA256 清单用于完整性验证，不代表来源签名或所有发布条件已满足。
