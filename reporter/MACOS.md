# macOS Reporter 使用说明

本轮完成的是电脑端 Reporter 的 macOS 基础适配，沿用现有开发板的 V1 UDP 协议。
不需要为接入 Mac 更换开发板固件。实际屏幕显示和跨设备发现仍需开发板联调。

## 启动

推荐双击 `dist-macos/SynaReporter.app`，直接打开 Mac 原生状态窗口。
也可以双击本目录 `start.command`：检测到已构建应用时会打开同一个窗口。
窗口每秒显示服务状态、CPU／内存／磁盘、网络速度、Codex 状态与额度，以及最近收到的开发板请求。
“停止服务／启动服务”控制本窗口启动的后台程序；“查看诊断”打开只读接口，“打开日志”定位日志目录。
关闭窗口后继续后台运行，点击 Dock 图标或按 Command+0 可再次显示；Command+Q 退出并停止所管理的服务。
如果服务原本由其他进程启动，窗口只查看它的状态，不会擅自结束该进程。
也可在终端执行：

```bash
cd "/你的项目路径/reporter"
./start.command
```

已构建的 `.app` 自带运行环境，无需另装 Python。若未构建应用，启动脚本会使用 Python 3.9+
在本目录创建 `.venv-macos` 并安装依赖，以终端方式运行。
本机已创建并验证 `.venv-macos`。源码运行时，如果其他 Mac 没有 Python，需要先安装 Python 3.9+；
可通过 `SYNA_PYTHON=/绝对路径/python3 ./start.command` 指定解释器。

运行后可打开 `http://127.0.0.1:8765/api/v1/status` 查看数据，
`http://127.0.0.1:8765/api/v1/health` 查看服务状态。
电脑和开发板需连接同一可互访的 Wi-Fi；系统询问本地网络访问时允许 Reporter 使用。
不要把诊断接口或 UDP 端口映射到互联网。

## 当前支持范围

| 功能 | macOS 基础版 |
| --- | --- |
| UDP 8766 发现、稳定电脑身份、绑定指纹 | 已实现，本机协议测试通过；待开发板联调 |
| CPU、内存、磁盘、上传／下载速度 | 已在 Apple 芯片 Mac 实测 |
| 磁盘使用率 | 优先读取 APFS 数据卷 `/System/Volumes/Data`，避免只统计只读系统卷 |
| Codex 进程和本地状态 | 支持 Mac 进程名称；数据库只查询原有状态字段和工作区路径 |
| Codex 登录与额度 | 通过 app-server 查询；兼容由 Codex 自己管理的钥匙串登录 |
| 网易云音乐 | 已接入普通启动的 Mac 客户端：歌曲、歌手、播放／暂停、真实进度、总时长及歌词 |
| 音乐数据来源 | Mac 读取系统 Now Playing；Windows 原有 CDP／本地读取路线保留 |
| GPU 使用率、CPU／GPU 温度 | Apple M5 实测可用，无需管理员权限；不可用时返回 `null` |
| 后台恢复、单实例、日志 | 已实现；另提供可选的用户级 launchd 管理脚本 |

没有可靠音乐数据时返回 `media.available=false`，设备按现有逻辑显示“未播放”。
这表示没有取得可用数据，不能据此判断 Mac 网易云是否实际上正在播放。
不会把 Windows 本地缓存路径用于 Mac，也不会虚构播放进度。

Codex 状态现优先读取 `logs_2.sqlite` 中固定格式的 `turn/started`／`turn/completed` 生命周期标记，
并结合进程 PID 和创建时间排除已退出的客户端及 PID 重用。支持多个客户端和同一客户端的并行任务；
全部任务结束后显示“已完成”约 120 秒，再回到“空闲”。生命周期记录不包含可可靠关联的工作区名称，
因此这一数据源显示通用的 `Codex` 名称。
SQL 仅返回时间戳、进程标识和固定事件类型，不返回日志正文、提示词、回复或工具参数。
读取失败或客户端不提供这些标记时，回退到原有历史表／进程判断。此日志格式属于版本相关实现，
并非承诺稳定的外部 API；客户端更新或日志被清理后可能需要同步适配。
本次实际账户只返回周额度窗口，短周期保持 `--`，不推算缺失额度。

## Mac 网易云音乐

普通打开网易云并播放歌曲即可，无需调试端口。Reporter 窗口显示歌曲、歌手、
播放／暂停与进度；开发板沿用原有 `media_*` 字段显示音乐和当前歌词，无需更新固件。
读取频率约每秒一次，以系统计算进度为准；暂停、拖动进度及切歌都会重新校正。

实现通过 macOS 自带 `osascript` 运行只读 Foundation/AppKit/MediaRemote 查询，
不操作播放器界面，不使用 System Events，不读取 Cookie、账号或播放历史，
也不修改网易云客户端。仅接受 bundle ID 为 `com.netease.163music` 的当前系统播放器。
若系统当前媒体切换成浏览器或其他播放器，返回不可用；重新在网易云播放即可。
网易云未启动、系统未提供曲目或接口失败时清空旧歌曲。

MediaRemote 属于私有接口，已在本机 macOS 26.6.2、网易云 3.1.8 验证，
不承诺所有 macOS／网易云版本兼容，系统升级后需复验。
API 调用参考：[MRNowPlayingRequest 示例](https://gist.github.com/SKaplanOfficial/f9f5bdd6455436203d0d318c078358de)。

歌词沿用现有网易云搜索与 LRC 查询：将当前歌名、歌手发送到网易云接口匹配歌曲，
不发送账户凭证。查询在后台执行，不阻塞实时播放状态；没有网络、无法匹配或无歌词时
显示“暂无歌词”。当前不提供封面或远程播放控制。

## Apple Silicon GPU 和温度

GPU 使用率读取 IORegistry 的 `AGXAccelerator / PerformanceStatistics / Device Utilization %`，
每秒更新；不叠加 Renderer 和 Tiler 计数，避免重复统计。
CPU 温度取有效 `Tp*`、`Te*` 传感器的平均值，GPU 温度取 `Tg*` 的平均值，
每 5 秒更新。它们是传感器组平均值，不代表最热点或机壳温度。
SMC 探针仅包含读取操作，不写入 SMC，不更改风扇、电源或温控设置。
无需 sudo、管理员密码或额外隐私权限。

本机 Apple M5 / macOS 26.6.2 实测成功。传感器名称与 ABI 非 Apple 稳定公开协议，
参考 [mactop SMC 实现](https://github.com/metaspartan/mactop/blob/main/internal/app/smc.c)。
其他芯片和系统版本需单独验证；无匹配传感器、超时或无效数据时显示 `--`，不沿用过期温度。
应用已包含 `MacThermalProbe`，源代码运行若缺少它，仅温度不可用，可先编译：

```bash
mkdir -p .macos-tools
clang -O2 -Wall -Wextra -framework IOKit macos_thermal.c -o .macos-tools/MacThermalProbe
```

## 打包程序

已生成 Apple 芯片版本：`dist-macos/SynaReporter.app`。
它包含 Swift / AppKit 原生状态窗口，以及 Python Reporter 后台。
双击后自动打开窗口并启动服务；若已有服务运行，则直接显示它的实时状态。
页面明确显示运行／停止／连接中断；中断时清除旧数值，避免把缓存误认为实时数据。
开发板通信栏仅表示最近 15 秒收到发现请求，不表示开发板已经选中本机。
本机包使用临时签名，尚未做 Developer ID 签名、公证；不是已完成公开发行的安装包。

源码启动和 `.app` 二选一。窗口内点击“停止服务”可停止采集并保留窗口；
退出应用则同时停止由它启动的后台。强制终止 worker 会触发后台监督进程恢复。

重新构建：

```bash
./build_macos.command
```

输出采用构建机器的架构；Intel Mac 需要在相应环境重新构建并验证，当前没有声称兼容所有 Mac。

## 登录后自动运行

在应用窗口底部打开“登录时自动启动”（需要 macOS 13+）。开关读取系统真实状态，
开启后下次登录当前 Mac 账户会打开应用窗口并启动 Reporter；关闭不影响当前服务。
若显示“等待系统允许”，点击“系统登录项”前往系统设置允许；在系统设置中更改后，窗口会自动同步。
关闭窗口仍继续运行，Command+Q 只退出本次运行，不取消下次登录自启动。
请将应用放在固定位置；移动或替换应用后重新检查开关。实际注销／登录效果需在方便时验收。
实现使用 Apple 的 [SMAppService](https://developer.apple.com/documentation/servicemanagement/smappservice)。

### 进阶：仅运行后台的旧版脚本

此脚本与窗口开关是两套独立机制，不要同时启用。如果曾安装此脚本，请先执行
`macos_service.py uninstall` 再使用窗口开关。只需要无窗口后台的用户可以先停止手动启动的 Reporter，然后执行：

```bash
.venv-macos/bin/python macos_service.py install
.venv-macos/bin/python macos_service.py status
```

这会在当前用户的 `~/Library/LaunchAgents/local.syna.reporter.plist` 注册服务，
由 launchd 启动并恢复 worker，无需管理员权限。
服务使用当前项目与虚拟环境的绝对路径，安装后不要移动项目；移动后重新执行 install。
桌面目录的访问权限由 macOS 管理，若后台启动被系统拒绝，检查服务日志和系统隐私设置。

```bash
.venv-macos/bin/python macos_service.py stop       # 停止本次运行，下次登录仍启动
.venv-macos/bin/python macos_service.py start      # 再次启动
.venv-macos/bin/python macos_service.py uninstall  # 停止并移除登录启动，保留配置与日志
```

launchd 的 plist 参数已测试；用户登录、自启动、系统权限弹窗和休眠唤醒还需要实际环境验收。

## 配置、日志与 Codex 路径

默认目录：`~/Library/Application Support/SynaReporter/`。
其中 `reporter.json` 保存稳定电脑身份与绑定信息，`reporter.log` 是轮转日志。
不要删除配置文件，否则设备会把它识别成新的 Reporter。
launchd 标准输出另记录为 `launchd.stdout.log`、`launchd.stderr.log`。

- `SYNA_REPORTER_DATA_DIR`：覆盖数据目录，适合隔离测试。
- `SYNA_CODEX_EXECUTABLE`：指定 Codex 可执行文件绝对路径。
- `CODEX_HOME`：沿用 Codex 的数据目录设置。

程序依次查找 PATH、常见 Codex.app／CLI 位置和 VS Code 扩展内的 Mac 可执行文件。
当前 Mac 的 VS Code 扩展路径已验证。Codex 更新后路径变化，重新安装后台服务可刷新其固定路径。
Mac 登录状态由 `account/read` 决定，不直接读取认证文件或钥匙串内容；额度通过 `account/rateLimits/read` 获取。

## 验证

```bash
.venv-macos/bin/python -m unittest discover -v
SYNA_TEST_APP="$PWD/dist-macos/SynaReporter.app/Contents/MacOS/SynaReporter" \
  .venv-macos/bin/python -m unittest test_macos.MacProtocolTests -v
```

测试使用临时配置，检查真实子进程的 HTTP、UDP、两次启动后的身份一致性、
正常退出及端口释放。若 UDP 8766 已被 Reporter 占用，协议测试会跳过，需先停止已有程序再运行。

接板验收：发现 Mac → 选择 Mac → 核对性能数据 → 核对 Codex 状态和额度 →
停止／重启 Reporter → 断开／恢复 Wi-Fi → Mac 休眠／唤醒。

## 工程边界

本轮没有改动或烧录 `src/`、`xiaozhi/overlay/` 中的固件，也没有迁移全部开发工具。
`platformio.ini` 的 Windows 构建目录、`xiaozhi/apply-ui-overlay.ps1`、模拟器的 Windows 构建脚本，
以及基于 System.Drawing 的字体／图片生成脚本仍保留原样。
它们不影响本轮 Mac Reporter 使用已有固件；如果需要在 Mac 上重建整个固件和资源，需另做工具链迁移与验证。

适配前备份：项目根目录 `备份_适配mac前_20260909_130845/`，复制后按 SHA-256 校验了 9,803 个文件。

参考：[psutil 支持范围](https://psutil.readthedocs.io/stable/index.html)、
[PyInstaller 打包说明](https://pyinstaller.org/en/stable/usage.html)、
[Apple launchd 说明](https://developer.apple.com/library/archive/documentation/MacOSX/Conceptual/BPSystemStartup/Chapters/CreatingLaunchdJobs.html)。
