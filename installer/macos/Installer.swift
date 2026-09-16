// Copyright (c) 2026 黑沐. MIT License.
import Cocoa

final class Installer: NSObject, NSApplicationDelegate, NSWindowDelegate {
    var window: NSWindow!
    let mode = NSPopUpButton()
    let ports = NSPopUpButton()
    let refresh = NSButton(title: "刷新设备", target: nil, action: nil)
    let start = NSButton(title: "一键安装", target: nil, action: nil)
    let login = NSButton(checkboxWithTitle: "安装后开启 Reporter 登录自启动", target: nil, action: nil)
    let reset = NSButton(checkboxWithTitle: "我已知悉首次安装会清除开发板原有数据", target: nil, action: nil)
    let hint = NSTextField(wrappingLabelWithString: "")
    let status = NSTextField(wrappingLabelWithString: "连接开发板，选择设备后开始。")
    let progress = NSProgressIndicator()
    let log = NSTextView()
    let backups = NSButton(title: "查看备份与日志", target: nil, action: nil)
    let launch = NSButton(title: "打开 Reporter", target: nil, action: nil)
    var portPaths: [String] = []
    var backupURL: URL?
    var installedURL: URL?
    var busy = false
    var process: Process?
    var pending = ""
    let resources = Bundle.main.resourceURL!

    func label(_ text: String, _ size: CGFloat = 13, _ weight: NSFont.Weight = .regular) -> NSTextField {
        let l = NSTextField(wrappingLabelWithString: text)
        l.font = .systemFont(ofSize: size, weight: weight)
        return l
    }
    func row(_ items: [NSView]) -> NSStackView {
        let s = NSStackView(views: items); s.orientation = .horizontal; s.spacing = 12
        return s
    }
    func applicationDidFinishLaunching(_ note: Notification) {
        NSApp.setActivationPolicy(.regular)
        let menu = NSMenu(); let item = NSMenuItem(); menu.addItem(item)
        let submenu = NSMenu(); submenu.addItem(withTitle: "退出安装器", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
        item.submenu = submenu; NSApp.mainMenu = menu
        window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 720, height: 740),
                          styleMask: [.titled, .closable, .miniaturizable], backing: .buffered, defer: false)
        window.title = "希娜 Syna 安装器"; window.delegate = self
        let stack = NSStackView(); stack.orientation = .vertical; stack.alignment = .leading; stack.spacing = 14
        stack.translatesAutoresizingMaskIntoConstraints = false
        window.contentView!.addSubview(stack)
        NSLayoutConstraint.activate([stack.leadingAnchor.constraint(equalTo: window.contentView!.leadingAnchor, constant: 28),
                                     stack.trailingAnchor.constraint(equalTo: window.contentView!.trailingAnchor, constant: -28),
                                     stack.topAnchor.constraint(equalTo: window.contentView!.topAnchor, constant: 26)])
        stack.addArrangedSubview(label("希娜 Syna", 30, .semibold))
        stack.addArrangedSubview(label("固件与 Reporter 一次安装 · v1.0.0 · Apple 芯片 Mac", 14))
        mode.addItems(withTitles: ["保留配置升级（推荐）", "首次安装 / 替换其他固件", "仅安装 Reporter"])
        mode.target = self; mode.action = #selector(modeChanged)
        mode.widthAnchor.constraint(equalToConstant: 300).isActive = true
        stack.addArrangedSubview(row([label("安装方式", 13, .medium), mode]))
        ports.widthAnchor.constraint(equalToConstant: 380).isActive = true
        refresh.target = self; refresh.action = #selector(refreshPorts)
        stack.addArrangedSubview(row([label("开发板", 13, .medium), ports, refresh]))
        hint.textColor = .secondaryLabelColor; stack.addArrangedSubview(hint)
        hint.widthAnchor.constraint(equalTo: stack.widthAnchor).isActive = true
        reset.target = self; reset.action = #selector(updateStart)
        stack.addArrangedSubview(reset)
        login.state = .on; stack.addArrangedSubview(login)
        start.bezelStyle = .rounded; start.keyEquivalent = "\r"; start.target = self; start.action = #selector(install)
        stack.addArrangedSubview(start)
        progress.minValue = 0; progress.maxValue = 100; progress.isIndeterminate = false
        progress.style = .bar; stack.addArrangedSubview(progress)
        progress.widthAnchor.constraint(equalTo: stack.widthAnchor).isActive = true
        stack.addArrangedSubview(status); status.widthAnchor.constraint(equalTo: stack.widthAnchor).isActive = true
        let scroll = NSScrollView(); scroll.hasVerticalScroller = true; scroll.borderType = .bezelBorder
        log.isEditable = false; log.isSelectable = true; log.font = .monospacedSystemFont(ofSize: 11, weight: .regular)
        log.autoresizingMask = [.width]; log.textContainer?.widthTracksTextView = true
        scroll.documentView = log; stack.addArrangedSubview(scroll)
        scroll.widthAnchor.constraint(equalTo: stack.widthAnchor).isActive = true
        scroll.heightAnchor.constraint(equalToConstant: 125).isActive = true
        backups.target = self; backups.action = #selector(openBackups)
        launch.target = self; launch.action = #selector(openReporter); launch.isEnabled = false
        stack.addArrangedSubview(row([backups, launch]))
        let author = label("黑沐 · B站 UID 386856267 · QQ 3091479711", 11)
        author.textColor = .secondaryLabelColor; stack.addArrangedSubview(author)
        modeChanged(); refreshPorts(); window.center(); window.makeKeyAndOrderFront(nil); NSApp.activate(ignoringOtherApps: true)
    }
    @objc func modeChanged() {
        reset.isHidden = mode.indexOfSelectedItem != 1
        ports.isEnabled = !busy && mode.indexOfSelectedItem != 2
        hint.stringValue = mode.indexOfSelectedItem == 2
            ? "Reporter 安装到 ~/Applications，保留已有设置。无需连接开发板。"
            : (mode.indexOfSelectedItem == 1
               ? "仅适用于微雪 ESP32-S3-RLCD-4.2（16 MB）。先校验完整备份，再清除并安装。"
               : "仅适用于微雪 ESP32-S3-RLCD-4.2（16 MB）。自动备份；保留 Wi-Fi、激活与待办。")
        updateStart()
    }
    @objc func updateStart() {
        start.isEnabled = !busy && (mode.indexOfSelectedItem == 2 || !portPaths.isEmpty)
            && (mode.indexOfSelectedItem != 1 || reset.state == .on)
    }
    func append(_ message: String) {
        guard !message.isEmpty else { return }
        log.string += message + "\n"
        if log.string.count > 24000 { log.string = String(log.string.suffix(18000)) }
        log.scrollToEndOfDocument(nil)
    }
    func receive(_ text: String) {
        pending += text
        while let end = pending.firstIndex(of: "\n") {
            let line = String(pending[..<end]); pending.removeSubrange(...end)
            guard let data = line.data(using: .utf8), let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else { append(line); continue }
            let event = obj["event"] as? String ?? ""
            if event == "ports" {
                let list = obj["ports"] as? [[String: String]] ?? []
                ports.removeAllItems(); portPaths = list.compactMap { $0["path"] }
                ports.addItems(withTitles: portPaths.isEmpty ? ["未检测到 USB 开发板"] : portPaths)
                updateStart()
            }
            if let path = obj["path"] as? String, event == "backup" { backupURL = URL(fileURLWithPath: path) }
            if let app = obj["app"] as? String { installedURL = URL(fileURLWithPath: app) }
            if let value = obj["progress"] as? Double { progress.doubleValue = value }
            if let message = obj["message"] as? String, !message.isEmpty {
                append(message)
                if event == "progress" || event == "error" { status.stringValue = message }
            }
        }
    }
    func worker(_ args: [String], completion: @escaping (Int32) -> Void) {
        let p = Process(); let pipe = Pipe()
        p.executableURL = Bundle.main.bundleURL.appendingPathComponent("Contents/Helpers/InstallerWorker.app/Contents/MacOS/InstallerWorker")
        p.arguments = args; p.standardOutput = pipe; p.standardError = pipe; pending = ""; process = p
        do { try p.run() } catch { append(error.localizedDescription); completion(1); return }
        DispatchQueue.global().async {
            while true {
                let data = pipe.fileHandleForReading.availableData
                if data.isEmpty { break }
                let text = String(decoding: data, as: UTF8.self)
                DispatchQueue.main.async { self.receive(text) }
            }
            p.waitUntilExit()
            DispatchQueue.main.async { self.process = nil; completion(p.terminationStatus) }
        }
    }
    @objc func refreshPorts() {
        guard process == nil && !busy else { return }
        refresh.isEnabled = false
        worker(["ports"]) { _ in self.refresh.isEnabled = true }
    }
    func finished(_ code: Int32) {
        busy = false; mode.isEnabled = true; refresh.isEnabled = true; login.isEnabled = true; modeChanged()
        if code == 0, installedURL != nil {
            progress.doubleValue = 100; launch.isEnabled = true
            status.stringValue = "安装完成。Reporter 已打开。开发板若未启动，请短按 PWR；首次安装请按屏幕提示配网。"
            openReporter()
        } else {
            status.stringValue = "安装未完成，请查看日志后重试。无法连接时按住 BOOT 重新插入 USB，再松开 BOOT。"
        }
    }
    @objc func install() {
        guard !busy && process == nil else { return }
        let selection = mode.indexOfSelectedItem
        let port = portPaths.indices.contains(ports.indexOfSelectedItem) ? portPaths[ports.indexOfSelectedItem] : ""
        busy = true; installedURL = nil; launch.isEnabled = false; mode.isEnabled = false
        refresh.isEnabled = false; ports.isEnabled = false; start.isEnabled = false; login.isEnabled = false
        progress.doubleValue = 0; status.stringValue = "校验官方安装文件…"
        worker(["verify", "--resources", resources.path]) { code in
            guard code == 0 else { self.finished(code); return }
            let apps = NSRunningApplication.runningApplications(withBundleIdentifier: "local.syna.reporter")
            apps.forEach { _ = $0.terminate() }
            DispatchQueue.global().async {
                let deadline = Date().addingTimeInterval(12)
                while apps.contains(where: { !$0.isTerminated }) && Date() < deadline { Thread.sleep(forTimeInterval: 0.2) }
                let stopped = !apps.contains(where: { !$0.isTerminated })
                DispatchQueue.main.async {
                    guard stopped else { self.append("请退出正在运行的 Reporter 后重试。"); self.finished(1); return }
                    var args = ["install", "--resources", self.resources.path, "--mode", ["upgrade", "fresh", "reporter"][selection]]
                    if selection != 2 { args += ["--port", port] }
                    if selection == 1 { args += ["--confirm-reset"] }
                    self.worker(args) { self.finished($0) }
                }
            }
        }
    }
    @objc func openBackups() {
        let url = backupURL ?? FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Library/Application Support/SynaInstaller")
        try? FileManager.default.createDirectory(at: url, withIntermediateDirectories: true)
        NSWorkspace.shared.open(url)
    }
    @objc func openReporter() {
        guard let url = installedURL else { return }
        let config = NSWorkspace.OpenConfiguration()
        if login.state == .on { config.arguments = ["--installer-enable-login"] }
        NSWorkspace.shared.openApplication(at: url, configuration: config) { _, error in
            if let error = error { DispatchQueue.main.async { self.append("Reporter 启动失败：" + error.localizedDescription) } }
        }
    }
    func windowShouldClose(_ sender: NSWindow) -> Bool { !busy }
    func applicationShouldTerminate(_ sender: NSApplication) -> NSApplication.TerminateReply {
        if busy { append("安装正在进行，请勿退出或拔线。"); return .terminateCancel }
        return .terminateNow
    }
    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { true }
}
let app = NSApplication.shared
let delegate = Installer(); app.delegate = delegate; app.run()
