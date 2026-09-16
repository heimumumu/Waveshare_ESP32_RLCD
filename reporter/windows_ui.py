# Copyright (c) 2026 黑沐. SPDX-License-Identifier: MIT
"""Windows status window, ported from native_ui.swift without changing its layout.

Qt coordinates are device-independent pixels. The backend stays in a separate
worker process; UI polling never blocks the event loop or stops an external worker.
"""
from __future__ import annotations
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time

from PySide6.QtCore import Qt, QTimer, QProcess, QUrl, QLockFile
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap, QAction
from PySide6.QtNetwork import QLocalServer, QLocalSocket, QNetworkAccessManager, QNetworkRequest, QNetworkProxy, QNetworkReply
from PySide6.QtWidgets import QApplication, QWidget, QLabel, QPushButton, QCheckBox, QMessageBox, QSystemTrayIcon, QMenu, QScrollArea, QVBoxLayout, QStyle
from PySide6.QtGui import QDesktopServices
from platform_support import application_data_dir

REPOSITORY = 'https://github.com/heimumumu/Waveshare_ESP32_RLCD'
RUN_KEY = r'Software\Microsoft\Windows\CurrentVersion\Run'


def launch_command():
    if getattr(sys, 'frozen', False):
        return [sys.executable]
    executable = Path(sys.executable)
    if os.name == 'nt' and executable.with_name('pythonw.exe').exists():
        executable = executable.with_name('pythonw.exe')
    return [str(executable), str(Path(__file__).with_name('reporter.py'))]


def login_enabled():
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            value, _ = winreg.QueryValueEx(key, 'SynaReporter')
        return value == subprocess.list2cmdline(launch_command())
    except FileNotFoundError:
        return False


def set_login(enabled):
    import winreg
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
        if enabled:
            winreg.SetValueEx(key, 'SynaReporter', 0, winreg.REG_SZ, subprocess.list2cmdline(launch_command()))
        else:
            try:
                winreg.DeleteValue(key, 'SynaReporter')
            except FileNotFoundError:
                pass


def number(value, suffix=''):
    return f'{value:.1f}{suffix}' if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) else '—'


def rate(value):
    if number(value) == '—':
        return '—'
    value = max(0, value)
    return f'{value / 1048576:.2f} MB/s' if value >= 1048576 else f'{value / 1024:.1f} KB/s'


class ElidedLabel(QLabel):
    """Preserve full accessible text and tooltip while clipping long song names."""
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setPen(self.palette().windowText().color())
        painter.setFont(self.font())
        painter.drawText(self.rect(), int(self.alignment()), self.fontMetrics().elidedText(self.text(), Qt.ElideRight, self.width()))


class ReporterWindow(QWidget):
    def __init__(self, *, preview=False):
        super().__init__()
        self.preview = preview
        self.worker = None
        self.wanted = True
        self.quitting = False
        self.first_poll = True
        self.polling = False
        self.restart_delay = 1000
        self.labels = {}
        self.setWindowTitle('Syna Reporter')
        self.setStyleSheet('QWidget {background:#f2f5f2;color:#21333b;} QPushButton {background:white;border:1px solid #d7dfd9;border-radius:7px;padding:5px;} QPushButton:hover {background:#e0eee6;} QPushButton:disabled {color:#89958f;} QCheckBox {spacing:10px;}')
        font = QFont()
        font.setFamilies(['Segoe UI', 'Microsoft YaHei UI', 'Microsoft YaHei'])
        self.setFont(font)
        # Keep the original design dimensions; scroll on smaller work areas so
        # high DPI never leaves service or startup controls below the screen.
        self.content = QWidget()
        self.content.setFixedSize(760, 750)
        self.scroll = QScrollArea(self)
        self.scroll.setFrameShape(QScrollArea.NoFrame)
        self.scroll.setWidget(self.content)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.scroll)
        self.setMinimumSize(320, 240)
        self.fit_to_screen()
        self.build_window()
        self.network = QNetworkAccessManager(self)
        self.network.setProxy(QNetworkProxy(QNetworkProxy.NoProxy))
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.tray = QSystemTrayIcon(self.make_icon(), self)
        self.tray.setToolTip('Syna Reporter · 双击显示状态窗口')
        menu = QMenu(self)
        menu.addAction('显示状态窗口', self.reveal)
        menu.addAction('关于作者', self.about)
        menu.addSeparator()
        menu.addAction('退出 Syna Reporter', self.quit)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(lambda reason: self.reveal() if reason in (QSystemTrayIcon.DoubleClick, QSystemTrayIcon.Trigger) else None)
        self.setWindowIcon(self.make_icon())
        if not preview:
            self.tray.show()
            self.refresh_login()
            self.timer.start(1000)
            self.refresh()

    @staticmethod
    def make_icon():
        pix = QPixmap(32, 32)
        pix.fill(Qt.transparent)
        p = QPainter(pix)
        p.setRenderHint(QPainter.Antialiasing)
        p.setBrush(QColor('#1f755c'))
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(0, 0, 32, 32, 8, 8)
        p.setPen(Qt.white)
        p.setFont(QFont('Segoe UI', 19, QFont.Bold))
        p.drawText(pix.rect(), Qt.AlignCenter, 'S')
        p.end()
        return QIcon(pix)

    def fit_to_screen(self):
        area = self.screen().availableGeometry()
        height = min(750, max(240, area.height() - 64))
        width = 760 + (self.style().pixelMetric(QStyle.PM_ScrollBarExtent) if height < 750 else 0)
        self.resize(min(width, max(320, area.width() - 32)), height)

    def text(self, parent, value, x, y, w, h, size=14, bold=False, muted=False, key=None):
        label = ElidedLabel(value, self.content if parent is self else parent)
        label.setGeometry(x, y, w, h)
        font = QFont('Segoe UI')
        font.setFamilies(['Segoe UI', 'Microsoft YaHei UI', 'Microsoft YaHei'])
        font.setPixelSize(size)
        font.setWeight(QFont.DemiBold if bold else QFont.Normal)
        label.setFont(font)
        label.setStyleSheet('background:transparent;color:' + ('#6e7d80' if muted else '#21333b') + ';')
        label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        if key:
            self.labels[key] = label
        return label

    def card(self, x, y, w, h, tint='white'):
        card = QWidget(self.content)
        card.setGeometry(x, y, w, h)
        card.setStyleSheet(f'background:{tint};border-radius:16px;')
        return card

    def button(self, title, x, w, action, y=626):
        button = QPushButton(title, self.content)
        button.setGeometry(x, y, w, 34)
        button.clicked.connect(action)
        return button

    def build_window(self):
        self.text(self, 'Syna Reporter', 28, 24, 470, 38, 29, True)
        self.text(self, '你的电脑与 Syna，现在一目了然。', 29, 64, 650, 23, 13, muted=True)
        self.text(self, 'WINDOWS 状态中心', 570, 34, 162, 23, 11, True, True).setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        banner = self.card(28, 100, 704, 96, '#e0f0e8')
        self.text(banner, '正在检查服务…', 22, 17, 395, 33, 24, True, key='status')
        self.text(banner, '连接本机 Reporter', 23, 58, 658, 24, 12, muted=True, key='detail')
        self.text(banner, '', 415, 22, 266, 25, 12, muted=True, key='host').setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        for key, title, x in [('cpu','CPU 使用率',28), ('gpu','GPU 使用率',207), ('memory','内存使用率',386), ('disk','磁盘空间占用',565)]:
            card = self.card(x, 210, 166, 108)
            self.text(card, title, 20, 16, 126, 22, 12, muted=True)
            self.text(card, '—', 20, 40, 126, 42, 28, True, key=key)
            if key in ('cpu','gpu'):
                self.text(card, '温度 —', 20, 86, 126, 18, 11, muted=True, key=key+'_temp')
        card = self.card(28, 332, 704, 76)
        self.text(card, '实时网络', 20, 14, 160, 22, 12, muted=True)
        self.text(card, '↑  —', 20, 38, 320, 29, 19, key='upload')
        self.text(card, '↓  —', 363, 38, 320, 29, 19, key='download')
        card = self.card(28, 422, 346, 102)
        self.text(card, 'CODEX', 20, 15, 306, 21, 11, True, True, key='quota_status')
        self.text(card, '等待数据', 20, 39, 306, 27, 20, True, key='agent')
        self.text(card, '短周期剩余 —    ·    周额度剩余 —', 20, 73, 306, 23, 12, muted=True, key='quota')
        card = self.card(388, 422, 344, 102)
        self.text(card, '网易云音乐', 20, 15, 304, 21, 11, True, True)
        self.text(card, '等待播放', 20, 39, 304, 27, 16, True, key='music')
        self.text(card, '打开网易云并播放歌曲', 20, 73, 304, 23, 11, muted=True, key='music_detail')
        card = self.card(28, 538, 704, 72)
        self.text(card, '开发板通信', 20, 12, 180, 22, 12, muted=True)
        self.text(card, '等待开发板请求', 20, 37, 660, 24, 14, key='device')
        self.labels['device'].setToolTip('表示最近 15 秒收到发现请求，不代表开发板已选中本机。')
        self.toggle = self.button('正在检查…', 28, 129, self.toggle_service)
        self.toggle.setEnabled(False)
        self.diagnostic = self.button('查看诊断', 169, 108, lambda: QDesktopServices.openUrl(QUrl('http://127.0.0.1:8765/api/v1/status')))
        self.button('打开日志', 288, 108, self.open_logs)
        self.button('关于作者', 407, 108, self.about)
        self.text(self, '等待首次更新', 526, 635, 206, 22, 11, muted=True, key='updated').setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.login = QCheckBox('登录时自动启动', self.content)
        self.login.setGeometry(28, 674, 210, 26)
        self.login.clicked.connect(self.toggle_login)
        self.text(self, '', 246, 678, 360, 22, 11, muted=True, key='login')
        self.button('系统启动项', 618, 114, lambda: QDesktopServices.openUrl(QUrl('ms-settings:startupapps')), y=671)
        self.text(self, '关闭窗口后继续运行 · 托盘菜单退出应用时停止服务', 29, 718, 700, 20, 11, muted=True)

    def put(self, key, value):
        self.labels[key].setText(value)
        if key in ('music','music_detail','host'):
            self.labels[key].setToolTip(value)

    def render(self, body):
        self.put('status', '●  运行中')
        self.put('detail', '正在采集电脑状态，并向同一网络中的开发板提供数据。' if self.worker else '服务由其他进程运行；当前窗口用于查看状态。')
        self.put('host', body.get('computer_name', '这台电脑'))
        perf = body.get('performance', {})
        for key in ('cpu','gpu','memory','disk'):
            self.put(key, number(perf.get(key+'_percent'), '%'))
        for key in ('cpu','gpu'):
            self.put(key+'_temp', '温度 ' + number(perf.get(key+'_temp_c'), '°C'))
        for key, arrow in [('upload','↑'),('download','↓')]:
            self.put(key, arrow+'  '+rate(perf.get(key+'_bytes_per_sec')))
        agent = body.get('agent', {})
        state = agent.get('state', 'offline')
        names = {'working':'工作中','done':'已完成','idle':'空闲','offline':'未运行','login_required':'请登录 Codex','waiting':'等待输入'}
        self.put('agent', names.get(state, '状态不可用') + (f"  ·  {agent.get('active_count',0)} 个任务" if state == 'working' else ''))
        quota = body.get('codex_quota', {})
        self.put('quota_status', 'CODEX · 更新失败，显示上次数据' if quota.get('stale') else
                 'CODEX · 额度暂不可用' if quota.get('source') == 'unavailable' else 'CODEX')
        self.put('quota', '短周期剩余 '+number(quota.get('short_remaining_percent'),'%')+'    ·    周额度剩余 '+number(quota.get('week_remaining_percent'),'%'))
        media = body.get('media', {})
        def clock(value):
            seconds = max(0,int(value or 0))
            return f'{seconds//60}:{seconds%60:02d}'
        if media.get('available'):
            self.put('music', media.get('title', ''))
            self.put('music_detail', ('播放中' if media.get('playback_status') == 'playing' else '已暂停')+f" · {clock(media.get('position_seconds'))}/{clock(media.get('duration_seconds'))} · {media.get('artist','')}")
        else:
            self.put('music', '未获取到歌曲')
            self.put('music_detail', '请在网易云播放歌曲')
        devices = body.get('devices', [])
        self.put('device', f"已收到 {len(devices)} 台开发板请求  ·  "+'、'.join(p.get('ip','') for p in devices) if devices else '尚未收到请求，请确认开发板与电脑连接同一 Wi-Fi。')
        self.put('updated', '最近更新  '+time.strftime('%H:%M:%S'))
        self.toggle.setText('停止服务' if self.worker else '由其他进程运行')
        self.toggle.setEnabled(self.worker is not None)
        self.diagnostic.setEnabled(True)
        self.restart_delay = 1000

    def offline(self):
        self.put('host', '')
        self.put('status', '正在启动…' if self.wanted and self.worker else '○  服务未运行')
        self.put('detail', '暂无实时数据。点击启动服务，或打开日志查看原因。')
        for key in ('cpu','gpu','memory','disk'):
            self.put(key, '—')
        for key in ('cpu','gpu'):
            self.put(key+'_temp', '温度 —')
        self.put('upload', '↑  —')
        self.put('download', '↓  —')
        self.put('agent', '等待服务启动')
        self.put('quota', '短周期剩余 —    ·    周额度剩余 —')
        self.put('quota_status', 'CODEX')
        self.put('music', '等待服务启动')
        self.put('music_detail', '—')
        self.put('device', '服务停止时，不向开发板发送数据。')
        self.put('updated', '尚未连接服务 / 已清除旧数据')
        self.toggle.setText('停止服务' if self.worker else '启动服务')
        self.toggle.setEnabled(True)
        self.diagnostic.setEnabled(False)

    def refresh(self):
        if self.polling or self.quitting:
            return
        self.polling = True
        request = QNetworkRequest(QUrl('http://127.0.0.1:8765/api/v1/status'))
        request.setTransferTimeout(2000)
        reply = self.network.get(request)
        def finished():
            self.polling = False
            try:
                if reply.error() != QNetworkReply.NoError:
                    raise ValueError('service unavailable')
                body = json.loads(bytes(reply.readAll()))
                if not isinstance(body.get('performance'), dict):
                    raise ValueError('not a Reporter response')
                self.render(body)
            except (ValueError, TypeError, AttributeError):
                self.offline()
                if self.first_poll and self.wanted:
                    self.start_service()
            finally:
                self.first_poll = False
                reply.deleteLater()
        reply.finished.connect(finished)

    def start_service(self):
        if self.worker or self.quitting:
            return
        self.wanted = True
        process = QProcess(self)
        self.worker = process
        command = launch_command()
        process.setProgram(command[0])
        process.setArguments(command[1:]+['--worker'])
        process.setStandardOutputFile(QProcess.nullDevice())
        process.setStandardErrorFile(QProcess.nullDevice())
        process.finished.connect(lambda *_: self.worker_finished(process))
        process.errorOccurred.connect(lambda error: self.worker_finished(process) if error == QProcess.FailedToStart else None)
        process.start()
        self.offline()

    def worker_finished(self, process):
        if self.worker is not process:
            return
        self.worker = None
        process.deleteLater()
        if self.wanted and not self.quitting:
            delay = self.restart_delay
            self.restart_delay = min(30000, delay*2)
            QTimer.singleShot(delay, lambda: self.start_service() if self.wanted else None)
        self.offline()

    def toggle_service(self):
        if self.worker:
            self.wanted = False
            # Only kill our direct worker, never an unrelated Reporter process.
            self.worker.kill()
        else:
            self.start_service()

    def refresh_login(self):
        try:
            import winreg
            try:
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, RUN_KEY) as key:
                    winreg.QueryValueEx(key, 'SynaReporter')
                self.login.setChecked(True)
                self.login.setEnabled(False)
                self.put('login', '旧版系统启动项仍在，请先运行新版安装程序')
                return
            except FileNotFoundError:
                pass
            self.login.setEnabled(True)
            enabled = login_enabled()
            self.login.setChecked(enabled)
            self.put('login', '已开启，下次登录自动启动窗口与服务' if enabled else '已关闭，登录后需手动打开程序')
            if enabled:
                try:
                    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run') as key:
                        approval, _ = winreg.QueryValueEx(key, 'SynaReporter')
                    if isinstance(approval, bytes) and approval and approval[0] in (3, 7):
                        self.put('login', '已被系统禁用，请在系统启动项中允许')
                except FileNotFoundError:
                    pass
        except OSError as exc:
            self.put('login', '无法读取启动项：'+str(exc))

    def toggle_login(self, enabled):
        try:
            set_login(enabled)
        except OSError as exc:
            QMessageBox.warning(self, '无法更改自启动设置', str(exc))
        self.refresh_login()

    def open_logs(self):
        directory = application_data_dir()
        directory.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(directory)))

    def about(self):
        box = QMessageBox(self)
        box.setWindowTitle('关于作者')
        box.setText('希娜 Syna · v1.0.0\n作者：黑沐')
        box.setInformativeText('B 站 UID：386856267\nQQ：3091479711\n\n官方仓库：github.com/heimumumu/Waveshare_ESP32_RLCD\n发布下载：仓库 Releases 页面\n\nCopyright © 2026 黑沐\n原创部分采用 MIT；第三方组件保留各自授权。')
        repo = box.addButton('官方仓库', QMessageBox.ActionRole)
        releases = box.addButton('发布下载', QMessageBox.ActionRole)
        box.addButton('关闭', QMessageBox.RejectRole)
        box.exec()
        if box.clickedButton() in (repo, releases):
            QDesktopServices.openUrl(QUrl(REPOSITORY+('/releases' if box.clickedButton() is releases else '')))

    def reveal(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()
        if not self.preview:
            self.refresh_login()

    def closeEvent(self, event):
        if self.quitting:
            event.accept()
        elif self.tray.isSystemTrayAvailable():
            self.hide()
            event.ignore()
        else:
            event.ignore()
            QMessageBox.information(self, '系统托盘不可用', '请使用任务栏最小化窗口；需要停止程序时，按 Alt+F4 后选择退出。')
            if QMessageBox.question(self, '退出程序', '是否退出 Syna Reporter 并停止服务？') == QMessageBox.Yes:
                self.quit()

    def quit(self):
        self.quitting = True
        self.wanted = False
        self.timer.stop()
        if self.worker:
            self.worker.kill()
            self.worker.waitForFinished(3000)
        self.tray.hide()
        QApplication.instance().quit()


def run():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setStyle('Fusion')
    root = application_data_dir()
    root.mkdir(parents=True, exist_ok=True)
    name = 'syna-reporter-ui-'+hashlib.sha256(str(root.resolve()).encode()).hexdigest()[:20]
    lock = QLockFile(str(root/'windows-ui.lock'))
    if not lock.tryLock(0):
        socket = QLocalSocket()
        socket.connectToServer(name)
        if socket.waitForConnected(2000):
            socket.write(b'show')
            socket.waitForBytesWritten(1000)
        return 0
    QLocalServer.removeServer(name)
    server = QLocalServer()
    server.setSocketOptions(QLocalServer.UserAccessOption)
    if not server.listen(name):
        raise RuntimeError('无法创建窗口通信通道：'+server.errorString())
    window = ReporterWindow()
    def connected():
        peer = server.nextPendingConnection()
        window.reveal()
        peer.disconnectFromServer()
        peer.deleteLater()
    server.newConnection.connect(connected)
    app.aboutToQuit.connect(lambda: window.quit() if not window.quitting else None)
    window.show()
    return app.exec()
