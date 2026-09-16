// Copyright (c) 2026 黑沐. Licensed under the MIT License.
import Cocoa
import Foundation
import ServiceManagement

final class Canvas: NSView {
    override var isFlipped: Bool { true }
}

final class ReporterApp: NSObject, NSApplicationDelegate {
    var window: NSWindow!
    var backend: Process?
    var timer: Timer?
    var polling = false
    var initialCheck = true
    var stopping = false
    var quitting = false
    var lastSuccess: Date?
    var launchedAt: Date?
    let port = 8765
    let ink = NSColor(calibratedRed: 0.13, green: 0.20, blue: 0.23, alpha: 1)
    let muted = NSColor(calibratedRed: 0.43, green: 0.49, blue: 0.50, alpha: 1)
    let green = NSColor(calibratedRed: 0.12, green: 0.46, blue: 0.36, alpha: 1)
    var statusLabel: NSTextField!
    var detailLabel: NSTextField!
    var hostLabel: NSTextField!
    var cpu: NSTextField!
    var gpu: NSTextField!
    var cpuTemperature: NSTextField!
    var gpuTemperature: NSTextField!
    var memory: NSTextField!
    var disk: NSTextField!
    var upload: NSTextField!
    var download: NSTextField!
    var agent: NSTextField!
    var quota: NSTextField!
    var device: NSTextField!
    var musicTitle: NSTextField!
    var musicDetail: NSTextField!
    var updated: NSTextField!
    var toggle: NSButton!
    var diagnostic: NSButton!
    var loginSwitch: NSSwitch!
    var loginStatus: NSTextField!
    var loginSettings: NSButton!
    let session: URLSession = {
        let config = URLSessionConfiguration.ephemeral
        config.timeoutIntervalForRequest = 2
        config.timeoutIntervalForResource = 3
        config.connectionProxyDictionary = [:]
        config.requestCachePolicy = .reloadIgnoringLocalCacheData
        return URLSession(configuration: config)
    }()

    var dataDirectory: URL {
        if let override = ProcessInfo.processInfo.environment["SYNA_REPORTER_DATA_DIR"] {
            return URL(fileURLWithPath: override)
        }
        return FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent("Library/Application Support/SynaReporter", isDirectory: true)
    }

    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.setActivationPolicy(.regular)
        if CommandLine.arguments.contains("--installer-enable-login") {
            if #available(macOS 13.0, *) {
                do {
                    // Installation may move the app from a development folder
                    // or an older location. Refresh the registered path.
                    if SMAppService.mainApp.status == .enabled { try SMAppService.mainApp.unregister() }
                    try SMAppService.mainApp.register()
                }
                catch { NSLog("Installer login registration: %@", error.localizedDescription) }
            }
        }
        buildMenu()
        buildWindow()
        showWindow()
        refresh()
        timer = Timer.scheduledTimer(withTimeInterval: 1, repeats: true) { [weak self] _ in self?.refresh() }
    }

    func buildMenu() {
        let menu = NSMenu()
        let appItem = NSMenuItem()
        let submenu = NSMenu()
        submenu.addItem(withTitle: "显示状态窗口", action: #selector(showWindow), keyEquivalent: "0").target = self
        submenu.addItem(NSMenuItem.separator())
        submenu.addItem(withTitle: "退出 Syna Reporter", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
        appItem.submenu = submenu
        menu.addItem(appItem)
        NSApp.mainMenu = menu
    }

    @discardableResult
    func text(_ parent: NSView, _ value: String, _ x: CGFloat, _ y: CGFloat,
              _ width: CGFloat, _ height: CGFloat, _ size: CGFloat = 14,
              _ weight: NSFont.Weight = .regular, _ color: NSColor? = nil) -> NSTextField {
        let label = NSTextField(labelWithString: value)
        label.frame = NSRect(x: x, y: y, width: width, height: height)
        label.font = .systemFont(ofSize: size, weight: weight)
        label.textColor = color ?? ink
        label.lineBreakMode = .byTruncatingTail
        label.isSelectable = true
        parent.addSubview(label)
        return label
    }

    func card(_ parent: NSView, _ rect: NSRect, _ tint: NSColor = .white) -> Canvas {
        let view = Canvas(frame: rect)
        view.wantsLayer = true
        view.layer?.backgroundColor = tint.cgColor
        view.layer?.cornerRadius = 16
        parent.addSubview(view)
        return view
    }

    func metric(_ parent: NSView, _ name: String, _ x: CGFloat) -> NSTextField {
        let view = card(parent, NSRect(x: x, y: 210, width: 166, height: 108))
        text(view, name, 20, 16, 126, 22, 12, .medium, muted)
        return text(view, "—", 20, 40, 126, 42, 28, .semibold)
    }

    func buildWindow() {
        window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 760, height: 750),
                          styleMask: [.titled, .closable, .miniaturizable], backing: .buffered, defer: false)
        window.title = "Syna Reporter"
        window.isReleasedWhenClosed = false
        window.titlebarAppearsTransparent = true
        window.backgroundColor = NSColor(calibratedRed: 0.95, green: 0.96, blue: 0.95, alpha: 1)
        window.appearance = NSAppearance(named: .aqua)
        let page = Canvas(frame: NSRect(x: 0, y: 0, width: 760, height: 750))
        window.contentView = page
        text(page, "Syna Reporter", 28, 24, 470, 38, 29, .semibold)
        text(page, "你的电脑与 Syna，现在一目了然。", 29, 64, 650, 23, 13, .regular, muted)
        text(page, "MAC 状态中心", 576, 34, 156, 23, 11, .semibold, muted).alignment = .right

        let banner = card(page, NSRect(x: 28, y: 100, width: 704, height: 96),
                          NSColor(calibratedRed: 0.88, green: 0.94, blue: 0.91, alpha: 1))
        statusLabel = text(banner, "正在检查服务…", 22, 17, 440, 33, 24, .semibold, green)
        detailLabel = text(banner, "连接本机 Reporter", 23, 58, 658, 24, 12, .regular, muted)
        hostLabel = text(banner, "", 415, 22, 266, 25, 12, .medium, muted)
        hostLabel.alignment = .right

        cpu = metric(page, "CPU 使用率", 28)
        gpu = metric(page, "GPU 使用率", 207)
        memory = metric(page, "内存使用率", 386)
        disk = metric(page, "磁盘空间占用", 565)
        cpuTemperature = text(cpu.superview!, "温度 —", 20, 86, 126, 18, 11, .regular, muted)
        gpuTemperature = text(gpu.superview!, "温度 —", 20, 86, 126, 18, 11, .regular, muted)
        cpuTemperature.toolTip = "CPU 温度传感器平均值，每 5 秒更新"
        gpuTemperature.toolTip = "GPU 温度传感器平均值，每 5 秒更新"

        let network = card(page, NSRect(x: 28, y: 332, width: 704, height: 76))
        text(network, "实时网络", 20, 14, 160, 22, 12, .medium, muted)
        upload = text(network, "↑  —", 20, 38, 320, 29, 19, .medium)
        download = text(network, "↓  —", 363, 38, 320, 29, 19, .medium)

        let codex = card(page, NSRect(x: 28, y: 422, width: 346, height: 102))
        text(codex, "CODEX", 20, 15, 160, 21, 11, .semibold, muted)
        agent = text(codex, "等待数据", 20, 39, 306, 27, 20, .semibold)
        quota = text(codex, "短周期剩余 —    ·    周额度剩余 —", 20, 73, 306, 23, 12, .regular, muted)

        let music = card(page, NSRect(x: 388, y: 422, width: 344, height: 102))
        text(music, "网易云音乐", 20, 15, 304, 21, 11, .semibold, muted)
        musicTitle = text(music, "等待播放", 20, 39, 304, 27, 16, .semibold)
        musicDetail = text(music, "打开网易云并播放歌曲", 20, 73, 304, 23, 11, .regular, muted)

        let board = card(page, NSRect(x: 28, y: 538, width: 704, height: 72))
        text(board, "开发板通信", 20, 12, 180, 22, 12, .medium, muted)
        device = text(board, "等待开发板请求", 20, 37, 660, 24, 14, .medium)

        toggle = NSButton(title: "正在检查…", target: self, action: #selector(toggleService))
        toggle.bezelStyle = .rounded
        toggle.controlSize = .large
        toggle.frame = NSRect(x: 24, y: 626, width: 133, height: 34)
        toggle.isEnabled = false
        page.addSubview(toggle)
        diagnostic = NSButton(title: "查看诊断", target: self, action: #selector(openDiagnostic))
        diagnostic.bezelStyle = .rounded
        diagnostic.frame = NSRect(x: 169, y: 626, width: 108, height: 34)
        page.addSubview(diagnostic)
        let logs = NSButton(title: "打开日志", target: self, action: #selector(openLogs))
        logs.bezelStyle = .rounded
        logs.frame = NSRect(x: 288, y: 626, width: 108, height: 34)
        page.addSubview(logs)
        let author = NSButton(title: "关于作者", target: self, action: #selector(aboutAuthor))
        author.bezelStyle = .rounded
        author.frame = NSRect(x: 407, y: 626, width: 108, height: 34)
        page.addSubview(author)
        updated = text(page, "等待首次更新", 526, 635, 206, 22, 11, .regular, muted)
        updated.alignment = .right
        loginSwitch = NSSwitch(frame: NSRect(x: 28, y: 674, width: 40, height: 24))
        loginSwitch.target = self
        loginSwitch.action = #selector(toggleLogin)
        loginSwitch.setAccessibilityLabel("登录时自动启动")
        page.addSubview(loginSwitch)
        text(page, "登录时自动启动", 78, 676, 160, 22, 13, .medium)
        loginStatus = text(page, "", 246, 678, 350, 22, 11, .regular, muted)
        loginSettings = NSButton(title: "系统登录项", target: self, action: #selector(openLoginSettings))
        loginSettings.bezelStyle = .rounded
        loginSettings.frame = NSRect(x: 618, y: 671, width: 118, height: 32)
        page.addSubview(loginSettings)
        refreshLoginStatus()
        text(page, "关闭窗口后继续运行 · 退出应用时停止服务", 29, 718, 700, 20, 11, .regular, muted)
        window.center()
    }

    @objc func showWindow() {
        window.deminiaturize(nil)
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
    }

    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool {
        showWindow()
        return false
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { false }

    func refresh() {
        refreshLoginStatus()
        guard !polling && !quitting else { return }
        polling = true
        let url = URL(string: "http://127.0.0.1:\(port)/api/v1/status")!
        session.dataTask(with: url) { [weak self] data, response, error in
            let json = data.flatMap { try? JSONSerialization.jsonObject(with: $0) } as? [String: Any]
            DispatchQueue.main.async {
                guard let self = self else { return }
                self.polling = false
                if let body = json, (response as? HTTPURLResponse)?.statusCode == 200,
                   body["reporter_id"] is String, body["online"] as? Bool == true {
                    self.initialCheck = false
                    self.lastSuccess = Date()
                    self.render(body)
                } else {
                    self.offline()
                    if self.initialCheck {
                        self.initialCheck = false
                        self.startService()
                    }
                }
            }
        }.resume()
    }

    func percent(_ value: Any?) -> String {
        guard let number = value as? NSNumber else { return "—" }
        return String(format: "%.1f%%", number.doubleValue)
    }

    func rate(_ value: Any?) -> String {
        guard let number = value as? NSNumber else { return "—" }
        let speed = max(0, number.doubleValue)
        return speed >= 1048576 ? String(format: "%.2f MB/s", speed / 1048576)
            : String(format: "%.1f KB/s", speed / 1024)
    }

    func render(_ body: [String: Any]) {
        statusLabel.stringValue = stopping ? "正在停止…" : "●  运行中"
        statusLabel.textColor = green
        hostLabel.stringValue = body["computer_name"] as? String ?? "这台 Mac"
        detailLabel.stringValue = backend == nil ? "服务由其他进程运行；当前窗口用于查看状态。" : "正在采集电脑状态，并向同一网络中的开发板提供数据。"
        let performance = body["performance"] as? [String: Any] ?? [:]
        cpu.stringValue = percent(performance["cpu_percent"])
        gpu.stringValue = percent(performance["gpu_percent"])
        func temperature(_ value: Any?) -> String {
            guard let number = value as? NSNumber else { return "温度 —" }
            return String(format: "温度 %.1f°C", number.doubleValue)
        }
        cpuTemperature.stringValue = temperature(performance["cpu_temp_c"])
        gpuTemperature.stringValue = temperature(performance["gpu_temp_c"])
        memory.stringValue = percent(performance["memory_percent"])
        disk.stringValue = percent(performance["disk_percent"])
        upload.stringValue = "↑  " + rate(performance["upload_bytes_per_sec"])
        download.stringValue = "↓  " + rate(performance["download_bytes_per_sec"])
        let state = body["agent"] as? [String: Any] ?? [:]
        let code = state["state"] as? String ?? "offline"
        let names = ["working": "工作中", "done": "已完成", "idle": "空闲", "offline": "未运行", "login_required": "请登录 Codex", "waiting": "等待输入"]
        let count = (state["active_count"] as? NSNumber)?.intValue ?? 0
        agent.stringValue = (names[code] ?? "状态不可用") + (code == "working" ? "  ·  \(count) 个任务" : "")
        let limits = body["codex_quota"] as? [String: Any] ?? [:]
        quota.stringValue = "短周期剩余 \(percent(limits["short_remaining_percent"]))    ·    周额度剩余 \(percent(limits["week_remaining_percent"]))"
        let media = body["media"] as? [String: Any] ?? [:]
        if media["available"] as? Bool == true {
            musicTitle.stringValue = media["title"] as? String ?? ""
            musicTitle.toolTip = musicTitle.stringValue
            let singer = media["artist"] as? String ?? ""
            let status = media["playback_status"] as? String == "playing" ? "播放中" : "已暂停"
            func clock(_ value: Any?) -> String {
                let seconds = max(0, (value as? NSNumber)?.intValue ?? 0)
                return String(format: "%d:%02d", seconds / 60, seconds % 60)
            }
            musicDetail.stringValue = "\(status) · \(clock(media["position_seconds"]))/\(clock(media["duration_seconds"])) · \(singer)"
            musicDetail.toolTip = musicDetail.stringValue
        } else {
            musicTitle.stringValue = "未获取到歌曲"
            musicTitle.toolTip = nil
            musicDetail.stringValue = "请在网易云播放歌曲"
            musicDetail.toolTip = nil
        }
        let peers = body["devices"] as? [[String: Any]] ?? []
        let ips = peers.compactMap { $0["ip"] as? String }.joined(separator: "、")
        device.stringValue = peers.isEmpty ? "尚未收到请求，请确认开发板与 Mac 连接同一 Wi-Fi。"
            : "已收到 \(peers.count) 台开发板请求  ·  \(ips)"
        device.toolTip = "表示最近 15 秒收到发现请求，不代表开发板已选中本机。"
        let formatter = DateFormatter()
        formatter.dateFormat = "HH:mm:ss"
        updated.stringValue = "最近更新  " + formatter.string(from: Date())
        toggle.title = backend == nil ? "由其他进程运行" : "停止服务"
        toggle.isEnabled = backend != nil && !stopping
        diagnostic.isEnabled = true
    }

    func offline() {
        let starting = backend?.isRunning == true && launchedAt.map { Date().timeIntervalSince($0) < 8 } == true
        statusLabel.stringValue = stopping ? "正在停止…" : (starting ? "正在启动…" : "○  服务未运行")
        statusLabel.textColor = starting ? green : .systemOrange
        detailLabel.stringValue = starting ? "正在初始化采集与网络服务。" : "暂无实时数据。点击启动服务，或打开日志查看原因。"
        for label in [cpu, gpu, memory, disk] { label?.stringValue = "—" }
        cpuTemperature.stringValue = "温度 —"
        gpuTemperature.stringValue = "温度 —"
        upload.stringValue = "↑  —"
        download.stringValue = "↓  —"
        agent.stringValue = "等待服务启动"
        musicTitle.stringValue = "等待服务启动"
        musicDetail.stringValue = "—"
        musicTitle.toolTip = nil
        musicDetail.toolTip = nil
        quota.stringValue = "短周期剩余 —    ·    周额度剩余 —"
        device.stringValue = "服务停止时，不向开发板发送数据。"
        updated.stringValue = lastSuccess == nil ? "尚未连接服务" : "连接中断，已清除旧数据"
        toggle.title = backend?.isRunning == true ? "停止服务" : "启动服务"
        toggle.isEnabled = !stopping && !initialCheck
        diagnostic.isEnabled = false
    }

    func startService() {
        guard backend?.isRunning != true else { return }
        let executable = Bundle.main.bundleURL.appendingPathComponent("Contents/MacOS/ReporterBackend")
        let process = Process()
        process.executableURL = executable
        process.arguments = ["--port", String(port)]
        process.standardOutput = FileHandle.nullDevice
        process.standardError = FileHandle.nullDevice
        process.terminationHandler = { [weak self] finished in
            DispatchQueue.main.async {
                guard let self = self, self.backend === finished else { return }
                self.backend = nil
                self.stopping = false
                self.refresh()
            }
        }
        do {
            try process.run()
            backend = process
            launchedAt = Date()
            offline()
        } catch {
            backend = nil
            offline()
            detailLabel.stringValue = "启动失败：\(error.localizedDescription)"
        }
    }

    @objc func toggleService() {
        if let process = backend, process.isRunning {
            stopping = true
            toggle.isEnabled = false
            process.terminate()
            offline()
        } else {
            startService()
        }
    }

    func applicationDidBecomeActive(_ notification: Notification) {
        if loginSwitch != nil { refreshLoginStatus() }
    }

    func refreshLoginStatus() {
        guard #available(macOS 13.0, *) else {
            loginSwitch.isEnabled = false
            loginSettings.isEnabled = false
            loginStatus.stringValue = "此功能需要 macOS 13 或更新版本"
            return
        }
        switch SMAppService.mainApp.status {
        case .enabled:
            loginSwitch.state = .on
            loginStatus.stringValue = "已开启，下次登录自动启动窗口与服务"
        case .requiresApproval:
            loginSwitch.state = .on
            loginStatus.stringValue = "等待系统允许，请前往系统登录项开启"
        case .notRegistered:
            loginSwitch.state = .off
            loginStatus.stringValue = "已关闭，登录后需手动打开程序"
        case .notFound:
            loginSwitch.state = .off
            loginStatus.stringValue = "系统未找到应用，请重新打开完整应用"
        @unknown default:
            loginSwitch.state = .off
            loginStatus.stringValue = "状态未知，请检查系统登录项"
        }
    }

    @objc func toggleLogin() {
        guard #available(macOS 13.0, *) else { return }
        do {
            if loginSwitch.state == .on {
                try SMAppService.mainApp.register()
            } else {
                try SMAppService.mainApp.unregister()
            }
        } catch {
            let alert = NSAlert()
            alert.messageText = "无法更改自启动设置"
            alert.informativeText = error.localizedDescription
            alert.addButton(withTitle: "好")
            alert.beginSheetModal(for: window)
        }
        refreshLoginStatus()
    }

    @objc func openLoginSettings() {
        if #available(macOS 13.0, *) { SMAppService.openSystemSettingsLoginItems() }
    }

    @objc func openDiagnostic() {
        NSWorkspace.shared.open(URL(string: "http://127.0.0.1:\(port)/api/v1/status")!)
    }

    @objc func openLogs() {
        try? FileManager.default.createDirectory(at: dataDirectory, withIntermediateDirectories: true)
        NSWorkspace.shared.open(dataDirectory)
    }

    @objc func aboutAuthor() {
        let alert = NSAlert()
        alert.messageText = "关于作者"
        alert.informativeText = "希娜 Syna · v1.0.0\n作者：黑沐\n\nB 站 UID：386856267\nQQ：3091479711\n\n官方仓库：github.com/heimumumu/Waveshare_ESP32_RLCD\n发布下载：仓库 Releases 页面\n\nCopyright © 2026 黑沐\n原创部分采用 MIT；第三方组件保留各自授权。"
        alert.addButton(withTitle: "关闭")
        alert.addButton(withTitle: "官方仓库")
        alert.addButton(withTitle: "发布下载")
        alert.beginSheetModal(for: window) { response in
            if response == .alertSecondButtonReturn {
                NSWorkspace.shared.open(URL(string: "https://github.com/heimumumu/Waveshare_ESP32_RLCD")!)
            } else if response == .alertThirdButtonReturn {
                NSWorkspace.shared.open(URL(string: "https://github.com/heimumumu/Waveshare_ESP32_RLCD/releases")!)
            }
        }
    }

    func applicationShouldTerminate(_ sender: NSApplication) -> NSApplication.TerminateReply {
        quitting = true
        timer?.invalidate()
        guard let process = backend, process.isRunning else { return .terminateNow }
        process.terminate()
        DispatchQueue.global().async {
            process.waitUntilExit()
            DispatchQueue.main.async { NSApp.reply(toApplicationShouldTerminate: true) }
        }
        return .terminateLater
    }
}

// Preserve command-line and worker behavior for existing launchers and tests.
if !CommandLine.arguments.contains("--installer-enable-login") && CommandLine.arguments.dropFirst().contains(where: { $0.hasPrefix("--") }) {
    let executable = URL(fileURLWithPath: CommandLine.arguments[0]).deletingLastPathComponent().appendingPathComponent("ReporterBackend").path
    let arguments = [executable] + Array(CommandLine.arguments.dropFirst())
    let pointers = arguments.map { strdup($0) } + [nil]
    execv(executable, pointers)
    exit(1)
}
let application = NSApplication.shared
let delegate = ReporterApp()
application.delegate = delegate
application.run()
