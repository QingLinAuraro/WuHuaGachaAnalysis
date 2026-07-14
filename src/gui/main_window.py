"""
桌面GUI - 主窗口
基于 PyQt6 的单窗口多页面布局
"""

import sys
from typing import Optional

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QStackedWidget, QPushButton, QLabel, QStatusBar, QFrame,
)
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QIcon, QFont

from src.config import config
from src.storage.database import db
from src.emulator.adb_client import ADBClient, auto_detect_device
from src.automation.gacha_scanner import create_scanner, GachaScanner
from src.gui.pages.home_page import HomePage
from src.gui.pages.record_page import RecordPage
from src.gui.pages.analysis_page import AnalysisPage
from src.gui.pages.settings_page import SettingsPage


class MainWindow(QMainWindow):
    """主窗口"""

    def __init__(self) -> None:
        super().__init__()

        self._adb: Optional[ADBClient] = None
        self._scanner: Optional[GachaScanner] = None

        self._setup_ui()
        self._apply_theme()

        # 默认显示首页
        self._nav_buttons[0].setChecked(True)
        self._stack.setCurrentIndex(0)

    def _setup_ui(self) -> None:
        """初始化UI"""
        width = config.get("gui.window_width", 1200)
        height = config.get("gui.window_height", 800)
        self.setWindowTitle("物华弥新抽卡分析器")
        self.setMinimumSize(900, 600)
        self.resize(width, height)

        # ── 中心控件 ──────────────────────────────

        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ── 顶部标题栏 ────────────────────────────

        title_bar = QFrame()
        title_bar.setObjectName("titleBar")
        title_bar.setFixedHeight(52)
        title_layout = QHBoxLayout(title_bar)
        title_layout.setContentsMargins(16, 0, 16, 0)

        title_label = QLabel("🎴 物华弥新 抽卡分析器")
        title_label.setObjectName("titleLabel")
        title_font = QFont()
        title_font.setPointSize(14)
        title_font.setBold(True)
        title_label.setFont(title_font)
        title_layout.addWidget(title_label)

        title_layout.addStretch()

        # 设备状态
        self._device_label = QLabel("🔌 设备未连接")
        self._device_label.setObjectName("deviceLabel")
        title_layout.addWidget(self._device_label)

        main_layout.addWidget(title_bar)

        # ── 内容区（侧栏 + 页面） ──────────────────

        content_layout = QHBoxLayout()
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        # 侧边导航栏
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(180)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(8, 12, 8, 12)
        sidebar_layout.setSpacing(4)

        self._nav_buttons: list[QPushButton] = []
        nav_items = [
            ("🏠", "首页概览"),
            ("📋", "抽卡记录"),
            ("📊", "统计分析"),
            ("⚙️", "设置"),
        ]

        for icon, text in nav_items:
            btn = QPushButton(f"  {icon}  {text}")
            btn.setObjectName("navButton")
            btn.setCheckable(True)
            btn.setFixedHeight(40)
            btn.clicked.connect(self._on_nav_click)
            sidebar_layout.addWidget(btn)
            self._nav_buttons.append(btn)

        sidebar_layout.addStretch()

        # 一键扫描按钮
        self._scan_btn = QPushButton("  🔍 开始扫描")
        self._scan_btn.setObjectName("scanButton")
        self._scan_btn.setFixedHeight(44)
        self._scan_btn.clicked.connect(self._on_scan_click)
        sidebar_layout.addWidget(self._scan_btn)

        content_layout.addWidget(sidebar)

        # 页面栈
        self._stack = QStackedWidget()
        self._pages = [
            HomePage(self),
            RecordPage(self),
            AnalysisPage(self),
            SettingsPage(self),
        ]
        for page in self._pages:
            self._stack.addWidget(page)

        content_layout.addWidget(self._stack)
        main_layout.addLayout(content_layout)

        # ── 状态栏 ──────────────────────────────────

        self._status_bar = QStatusBar()
        self._status_bar.showMessage("就绪 — 物华弥新抽卡分析器 v1.0")
        self.setStatusBar(self._status_bar)

    def _on_nav_click(self) -> None:
        """导航按钮点击"""
        sender = self.sender()
        for i, btn in enumerate(self._nav_buttons):
            if btn is sender:
                btn.setChecked(True)
                self._stack.setCurrentIndex(i)
                self._pages[i].on_activated()
            else:
                btn.setChecked(False)

    def _on_scan_click(self) -> None:
        """开始扫描按钮点击"""
        self._scan_btn.setEnabled(False)
        self._scan_btn.setText("  ⏳ 扫描中...")
        self._status_bar.showMessage("正在连接模拟器并扫描...")

        # 切换到首页显示进度
        self._nav_buttons[0].setChecked(True)
        self._stack.setCurrentIndex(1)

    # ── 公共接口 ───────────────────────────────────

    @property
    def adb(self) -> Optional[ADBClient]:
        return self._adb

    @property
    def scanner(self) -> Optional[GachaScanner]:
        return self._scanner

    def set_status(self, message: str) -> None:
        self._status_bar.showMessage(message)

    def refresh_all_pages(self) -> None:
        """刷新所有页面数据"""
        for page in self._pages:
            page.refresh()

    def _apply_theme(self) -> None:
        """应用样式主题"""
        theme = config.get("gui.theme", "light")

        if theme == "light":
            self.setStyleSheet("""
                QMainWindow {
                    background-color: #f5f6fa;
                }
                #titleBar {
                    background-color: #ffffff;
                    border-bottom: 1px solid #e0e0e0;
                }
                #titleLabel {
                    color: #2c3e50;
                }
                #deviceLabel {
                    color: #7f8c8d;
                    font-size: 12px;
                }
                #sidebar {
                    background-color: #ffffff;
                    border-right: 1px solid #e0e0e0;
                }
                #navButton {
                    background-color: transparent;
                    border: none;
                    border-radius: 6px;
                    text-align: left;
                    padding-left: 12px;
                    color: #2c3e50;
                    font-size: 13px;
                }
                #navButton:hover {
                    background-color: #ecf0f1;
                }
                #navButton:checked {
                    background-color: #3498db;
                    color: white;
                    font-weight: bold;
                }
                #scanButton {
                    background-color: #e74c3c;
                    color: white;
                    border: none;
                    border-radius: 8px;
                    font-size: 14px;
                    font-weight: bold;
                }
                #scanButton:hover {
                    background-color: #c0392b;
                }
                #scanButton:disabled {
                    background-color: #bdc3c7;
                }
                QStatusBar {
                    background-color: #ffffff;
                    border-top: 1px solid #e0e0e0;
                    color: #7f8c8d;
                }
            """)
        else:
            self.setStyleSheet("""
                QMainWindow {
                    background-color: #1a1a2e;
                }
                #titleBar {
                    background-color: #16213e;
                    border-bottom: 1px solid #0f3460;
                }
                #titleLabel {
                    color: #e0e0e0;
                }
                #deviceLabel {
                    color: #a0a0a0;
                    font-size: 12px;
                }
                #sidebar {
                    background-color: #16213e;
                    border-right: 1px solid #0f3460;
                }
                #navButton {
                    background-color: transparent;
                    border: none;
                    border-radius: 6px;
                    text-align: left;
                    padding-left: 12px;
                    color: #c0c0c0;
                    font-size: 13px;
                }
                #navButton:hover {
                    background-color: #0f3460;
                }
                #navButton:checked {
                    background-color: #e94560;
                    color: white;
                    font-weight: bold;
                }
                #scanButton {
                    background-color: #e94560;
                    color: white;
                    border: none;
                    border-radius: 8px;
                    font-size: 14px;
                    font-weight: bold;
                }
                #scanButton:hover {
                    background-color: #c23152;
                }
                #scanButton:disabled {
                    background-color: #555;
                }
                QStatusBar {
                    background-color: #16213e;
                    border-top: 1px solid #0f3460;
                    color: #a0a0a0;
                }
            """)


def launch_gui() -> None:
    """启动 GUI 应用"""
    app = QApplication(sys.argv)
    app.setApplicationName("WuHuaGachaAnalysis")

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    launch_gui()
