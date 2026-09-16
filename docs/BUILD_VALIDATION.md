# 2026-09-16 独立源码重构建

验证目录：`D:/syna-release-validation-20260916`，与开发目录、开源整理目录分离。仅在开源整理目录修订文档及测试脚本参数，没有修改原开发源码，没有安装 Reporter 或刷写开发板。

## 隔离范围

- 从开源目录复制源码，全新创建 Python 3.11 虚拟环境并安装声明的依赖。
- 从本机 Git 对象库独立克隆锁定的小智提交，未复制开发工作树改动、旧 build 目录或旧固件。
- 通过开源目录覆盖脚本重新应用补丁，重新解析组件及编译。
- 使用本机现有 ESP-IDF 6.0.2 编译器、其 Python 环境和下载/编译缓存。因此这是源码与应用依赖环境隔离验证，不是全新操作系统测试，也不是字节级可复现构建证明。

## 已完成

- 全新 Python 环境 `pip check` 通过。
- Reporter：66 项测试，53 项通过、13 项跳过；退出码 0。
- Reporter EXE 重新打包成功，临时配置目录且 PATH 不含 Python 时自检退出 0。
- 固件从锁定提交完整编译成功，应用 3,762,016 字节，符合分区容量。
- 单轮对话与额度显示主机测试通过；测试使用新的固件源码路径。
- 安装器源码 11 项测试通过。
- 独立安装器重新打包成功；移除 Python/IDF 路径、强制非 UTF-8 环境后，文件清单、后端、esptool、Reporter 模式和中文完成协议自检全部通过，退出码 0。

固件 SHA256：`e649f596410ecca44c1fcf6716871c0447b7c7e9e3f5b78a848fbbc1bc5cfcc6`。

Reporter SHA256：`8254e77e946824342416750a66b8bba17df608f7dd620be01a784d636c89f0d2`。

最终安装包的自检与 SHA256 另见同目录完成记录 `BUILD_VALIDATION.json`。精确依赖清单在 `release/build-info/windows-validation-20260916/`，用于记录此次构建，不应将 Windows 依赖快照直接用于 Mac。

## 限制

这些是新构建产物，尚未安装、刷写或进行语音验收。不能以旧产物的实机验收替代本批次验收；另一台 Windows、首次安装清空流程及 Mac 最新版本仍待验证。

后续第三方核对发现原打包器遗漏部分许可证，打包脚本已修正。本记录中的哈希仍对应修正前的验证产物，正式发布必须重新构建并更新验证记录，见 THIRD_PARTY_AUDIT.md。

后续重新打包已经完成：新产物及内嵌授权文件验证见 RELEASE_CANDIDATE.json / RELEASE_CANDIDATE.md。本页及 BUILD_VALIDATION.json 保留初次重构建历史，不作为最新候选包的校验值。

PowerShell 5 把部分原生程序 stderr 的正常构建输出记录为 NativeCommandError，外层命令可能返回 1。本次固件以 ESP-IDF 的完整构建成功记录、无 FAILED 构建节点、实际生成的应用及分区检查为依据。后续自动化应使用 subprocess 或明确传播原生退出码，避免仅依赖外层 PowerShell 日志。
