"""
桌面GUI - 主窗口
ALAS风格：简洁紧凑，左侧导航 + 右侧内容 + 底部日志
"""
import sys
from typing import Optional

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QStackedWidget, QPushButton, QLabel, QStatusBar, QFrame,
    QTextEdit, QSplitter,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont

from src.config import config
from src.emulator.adb_client import ADBClient
from src.automation.gacha_scanner import GachaScanner
from src.gui.pages.home_page import HomePage
from src.gui.pages.record_page import RecordPage
from src.gui.pages.analysis_page import AnalysisPage
from src.gui.pages.settings_page import SettingsPage

STYLE = """
/* === 全局 === */
* {
    font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
    font-size: 13px;
}
QMainWindow {
    background-color: #1e1e1e;
}

/* === 输入控件 === */
QLineEdit {
    background-color: #2d2d2d;
    color: #d4d4d4;
    border: 1px solid #3c3c3c;
    border-radius: 4px;
    padding: 4px 8px;
    selection-background-color: #264f78;
}
QLineEdit:focus {
    border-color: #007acc;
}
QComboBox {
    background-color: #2d2d2d;
    color: #d4d4d4;
    border: 1px solid #3c3c3c;
    border-radius: 4px;
    padding: 4px 8px;
    min-width: 120px;
}
QComboBox:hover { border-color: #007acc; }
QComboBox::drop-down {
    border: none;
    padding-right: 8px;
}
QComboBox QAbstractItemView {
    background-color: #2d2d2d;
    color: #d4d4d4;
    border: 1px solid #3c3c3c;
    selection-background-color: #264f78;
    outline: none;
}
QSpinBox {
    background-color: #2d2d2d;
    color: #d4d4d4;
    border: 1px solid #3c3c3c;
    border-radius: 4px;
    padding: 4px 8px;
}
QSpinBox:focus { border-color: #007acc; }

/* === 按钮 === */
QPushButton {
    background-color: #3c3c3c;
    color: #d4d4d4;
    border: 1px solid #4a4a4a;
    border-radius: 4px;
    padding: 5px 14px;
}
QPushButton:hover {
    background-color: #4a4a4a;
    border-color: #5a5a5a;
}
QPushButton:pressed {
    background-color: #2d2d2d;
}
QPushButton:disabled {
    background-color: #2a2a2a;
    color: #666;
}
QPushButton[primary="true"] {
    background-color: #007acc;
    border-color: #007acc;
    color: white;
}
QPushButton[primary="true"]:hover {
    background-color: #1a8cd8;
}
QPushButton[danger="true"] {
    background-color: #c0392b;
    border-color: #c0392b;
    color: white;
}
QPushButton[danger="true"]:hover {
    background-color: #e74c3c;
}

/* === 标签 === */
QLabel {
    color: #d4d4d4;
}

/* === 分组框 === */
QGroupBox {
    color: #e0e0e0;
    border: 1px solid #3c3c3c;
    border-radius: 6px;
    margin-top: 14px;
    padding: 16px 12px 12px 12px;
    font-weight: bold;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
    color: #e0e0e0;
}

/* === 表格 === */
QTableWidget {
    background-color: #252526;
    color: #d4d4d4;
    border: 1px solid #3c3c3c;
    border-radius: 4px;
    gridline-color: #333;
}
QTableWidget::item { padding: 4px 8px; }
QTableWidget::item:selected {
    background-color: #264f78;
    color: white;
}
QHeaderView::section {
    background-color: #2d2d2d;
    color: #d4d4d4;
    border: none;
    border-bottom: 1px solid #3c3c3c;
    padding: 6px 8px;
    font-weight: bold;
}

/* === 滚动条 === */
QScrollBar:vertical {
    background: #1e1e1e;
    width: 8px;
    border-radius: 4px;
}
QScrollBar::handle:vertical {
    background: #555;
    border-radius: 4px;
    min-height: 30px;
}
QScrollBar::handle:vertical:hover { background: #777; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }

/* === 滚动区域 === */
QScrollArea { border: none; }

/* === 状态栏 === */
QStatusBar {
    background-color: #007acc;
    color: white;
    border: none;
    padding: 2px 8px;
    font-size: 12px;
}

/* === 日志输出 === */
QTextEdit {
    background-color: #1a1a1a;
    color: #a0a0a0;
    border: none;
    font-family: "Consolas", "Courier New", monospace;
    font-size: 12px;
}

/* === 标签页 === */
QTabWidget::pane { border: 1px solid #3c3c3c; background: #252526; }
QTabBar::tab {
    background: #2d2d2d;
    color: #999;
    padding: 6px 16px;
    border: none;
    border-bottom: 2px solid transparent;
}
QTabBar::tab:selected {
    color: #e0e0e0;
    border-bottom: 2px solid #007acc;
}
QTabBar::tab:hover { color: #d4d4d4; }

/* === 标题栏 === */
#titleBar {
    background-color: #007acc;
    border: none;
}
#titleLabel {
    color: white;
    font-size: 14px;
    font-weight: bold;
}
#deviceLabel {
    color: rgba(255,255,255,0.8);
    font-size: 12px;
}

/* === 侧边栏 === */
#sidebar {
    background-color: #252526;
    border-right: 1px solid #3c3c3c;
}
#navButton {
    background-color: transparent;
    color: #ccc;
    border: none;
    border-radius: 4px;
    text-align: left;
    padding: 8px 16px;
    font-size: 13px;
}
#navButton:hover {
    background-color: #2d2d2d;
    color: #e0e0e0;
}
#navButton:checked {
    background-color: #37373d;
    color: white;
    border-left: 3px solid #007acc;
}
"""


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self._adb: Optional[ADBClient] = None
        self._scanner: Optional[GachaScanner] = None
        self._setup_ui()
        self.setStyleSheet(STYLE)
        self._nav_buttons[0].setChecked(True)
        self._stack.setCurrentIndex(0)

    def _setup_ui(self) -> None:
        w, h = config.get("gui.window_width", 1100), config.get("gui.window_height", 680)
        self.setWindowTitle("WuHuaGachaAnalysis")
        self.setMinimumSize(800, 500)
        self.resize(w, h)

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── 顶栏 ──
        bar = QFrame()
        bar.setObjectName("titleBar")
        bar.setFixedHeight(40)
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(12, 0, 12, 0)
        t = QLabel("物华弥新 抽卡分析器")
        t.setObjectName("titleLabel")
        t.setFont(QFont("", 12, QFont.Weight.Bold))
        bl.addWidget(t)
        bl.addStretch()
        self._dev_lbl = QLabel("设备: --")
        self._dev_lbl.setObjectName("deviceLabel")
        bl.addWidget(self._dev_lbl)
        root.addWidget(bar)

        # ── 中部分割（左侧栏 + 右内容 + 底日志） ──
        splitter = QSplitter(Qt.Orientation.Vertical)
        top = QWidget()
        top_layout = QHBoxLayout(top)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(0)

        # 左侧栏
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(140)
        sl = QVBoxLayout(sidebar)
        sl.setContentsMargins(4, 8, 4, 8)
        sl.setSpacing(2)

        self._nav_buttons: list[QPushButton] = []
        for text in ["概览", "记录", "分析", "设置"]:
            b = QPushButton(text)
            b.setObjectName("navButton")
            b.setCheckable(True)
            b.setFixedHeight(36)
            b.clicked.connect(self._on_nav)
            sl.addWidget(b)
            self._nav_buttons.append(b)

        sl.addStretch()

        self._scan_btn = QPushButton("开始扫描")
        self._scan_btn.setObjectName("scanButton")
        self._scan_btn.setProperty("danger", True)
        self._scan_btn.setFixedHeight(38)
        self._scan_btn.clicked.connect(self._on_scan)
        sl.addWidget(self._scan_btn)

        top_layout.addWidget(sidebar)

        # 右侧内容区
        self._stack = QStackedWidget()
        self._pages = [
            HomePage(self),
            RecordPage(self),
            AnalysisPage(self),
            s := SettingsPage(self),
        ]
        s.on_adb_connected = self._on_adb_ready
        self._pages = [HomePage(self), RecordPage(self), AnalysisPage(self), s]
        for p in self._pages:
            self._stack.addWidget(p)
        top_layout.addWidget(self._stack)

        splitter.addWidget(top)

        # ── 底部日志 ──
        log_widget = QWidget()
        log_layout = QVBoxLayout(log_widget)
        log_layout.setContentsMargins(0, 0, 0, 0)
        log_bar = QFrame()
        log_bar.setFixedHeight(22)
        log_bar.setStyleSheet("background:#333; border:none; padding:2px 8px;")
        log_bl = QHBoxLayout(log_bar)
        log_bl.setContentsMargins(8, 0, 8, 0)
        log_bl.addWidget(QLabel("日志"))
        log_bl.addStretch()
        log_layout.addWidget(log_bar)

        self._log = QTextEdit()
        self._log.setReadOnly(True)
        self._log.document().setMaximumBlockCount(2000)
        log_layout.addWidget(self._log)
        splitter.addWidget(log_widget)
        splitter.setSizes([420, 140])

        root.addWidget(splitter)

        # ── 状态栏 ──
        self._status = QStatusBar()
        self._status.showMessage("就绪")
        self.setStatusBar(self._status)

    def log(self, msg: str) -> None:
        self._log.append(msg)

    def set_device_status(self, text: str) -> None:
        self._dev_lbl.setText(f"设备: {text}")

    def set_scan_enabled(self, enabled: bool) -> None:
        self._scan_btn.setEnabled(enabled)
        self._scan_btn.setText("开始扫描" if enabled else "扫描中...")

    def set_status(self, msg: str) -> None:
        self._status.showMessage(msg)

    def _on_nav(self) -> None:
        s = self.sender()
        for i, b in enumerate(self._nav_buttons):
            if b is s:
                b.setChecked(True)
                self._stack.setCurrentIndex(i)
                self._pages[i].on_activated()
            else:
                b.setChecked(False)

    def _on_adb_ready(self, adb: ADBClient) -> None:
        self._adb = adb
        self.set_device_status(f"{adb._serial}")
        self.log(f"[INFO] ADB 已连接: {adb._serial}")

    def _on_scan(self) -> None:
        if self._adb is None:
            self.log("[ERROR] 请先在设置页连接模拟器")
            self.set_status("请先连接模拟器")
            return

        self.set_scan_enabled(False)
        self.set_status("正在扫描...")
        self.log("[INFO] 开始扫描召集记录...")

        from src.automation.gacha_scanner import create_scanner
        from src.models.gacha_record import BannerType
        import threading

        self._scanner = create_scanner(self._adb)
        self._scanner.set_banner("活动招募", BannerType.EVENT)
        self._scanner.on_progress(lambda cur, total, info: self.log(f"[进度] {info}"))
        self._scanner.on_record_found(lambda r: self.log(f"[记录] {r.character_name} ★{r.rarity.value} {r.banner_name}"))

        def _run():
            try:
                records = self._scanner.scan_all()
                self.log(f"[完成] 共扫描 {len(records)} 条记录")
                self.set_status(f"扫描完成，共 {len(records)} 条")
                # 刷新所有页面
                self._pages[0].refresh()
                self._pages[1].refresh()
                self._pages[2].refresh()
            except Exception as e:
                self.log(f"[ERROR] {e}")
                self.set_status("扫描失败")
            finally:
                self.set_scan_enabled(True)

        threading.Thread(target=_run, daemon=True).start()

    @property
    def adb(self) -> Optional[ADBClient]:
        return self._adb

    @property
    def scanner(self) -> Optional[GachaScanner]:
        return self._scanner

    def refresh_all_pages(self) -> None:
        for p in self._pages:
            p.refresh()


def launch_gui() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("WuHuaGachaAnalysis")
    w = MainWindow()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    launch_gui()
