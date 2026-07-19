"""
桌面GUI - 主窗口
ALAS风格：简洁紧凑，左侧导航 + 右侧内容 + 底部日志
"""
import sys
from datetime import datetime
from typing import Optional

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QStackedWidget, QPushButton, QLabel, QStatusBar, QFrame,
    QTextEdit, QSplitter, QComboBox, QInputDialog, QMessageBox,
    QDialog, QDialogButtonBox,
)
from PyQt6.QtCore import Qt, pyqtSignal, QObject
from PyQt6.QtGui import QFont

from src.config import config
from src.storage.database import db
from src.emulator.adb_client import ADBClient
from src.automation.gacha_scanner import GachaScanner
from src.gui.pages.home_page import HomePage
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
#accountCombo {
    background-color: rgba(255,255,255,0.15);
    color: white;
    border: 1px solid rgba(255,255,255,0.3);
    border-radius: 4px;
    padding: 2px 8px;
    min-width: 90px;
    max-width: 130px;
    font-size: 12px;
}
#accountCombo:hover { background-color: rgba(255,255,255,0.25); }
#accountCombo::drop-down { border: none; padding-right: 4px; }
#accountCombo QAbstractItemView {
    background-color: #2d2d2d;
    color: #d4d4d4;
    border: 1px solid #3c3c3c;
    selection-background-color: #264f78;
    font-size: 12px;
}
#manageAccountBtn {
    background-color: rgba(255,255,255,0.15);
    color: white;
    border: 1px solid rgba(255,255,255,0.3);
    border-radius: 4px;
    padding: 2px 6px;
    font-size: 11px;
    max-height: 22px;
}
#manageAccountBtn:hover { background-color: rgba(255,255,255,0.25); }

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


class ScannerSignals(QObject):
    """信号桥 — 后台线程 → 主线程 UI 更新"""
    log_msg = pyqtSignal(str)
    status_msg = pyqtSignal(str)
    scan_done = pyqtSignal(int)
    scan_error = pyqtSignal(str)


class AccountDialog(QDialog):
    """账户管理对话框"""
    def __init__(self, parent=None, current_account_id: int = 0):
        super().__init__(parent)
        self.setWindowTitle("管理账户")
        self.setFixedSize(350, 280)
        self._current_id = current_account_id
        self._setup()

    def _setup(self):
        from PyQt6.QtWidgets import QListWidget, QListWidgetItem
        root = QVBoxLayout(self)
        root.setSpacing(8)

        self._list = QListWidget()
        self._list.setStyleSheet("background:#252526; color:#d4d4d4; border:1px solid #3c3c3c;")
        root.addWidget(self._list)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)

        b_new = QPushButton("新建")
        b_new.clicked.connect(self._on_new)
        btn_row.addWidget(b_new)

        b_rename = QPushButton("重命名")
        b_rename.clicked.connect(self._on_rename)
        btn_row.addWidget(b_rename)

        b_del = QPushButton("删除")
        b_del.setProperty("danger", True)
        b_del.clicked.connect(self._on_delete)
        btn_row.addWidget(b_del)

        root.addLayout(btn_row)

        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        bb.accepted.connect(self.accept)
        root.addWidget(bb)

        self._refresh_list()

    def _refresh_list(self):
        from PyQt6.QtWidgets import QListWidgetItem
        self._list.clear()
        accounts = db.list_accounts()
        for acc in accounts:
            item = QListWidgetItem(acc.name)
            item.setData(Qt.ItemDataRole.UserRole, acc.id)
            if acc.id == self._current_id:
                item.setForeground(Qt.GlobalColor.cyan)
                font = item.font()
                font.setBold(True)
                item.setFont(font)
            self._list.addItem(item)

    def _selected_id(self) -> Optional[int]:
        item = self._list.currentItem()
        if item:
            return item.data(Qt.ItemDataRole.UserRole)
        return None

    def _on_new(self):
        name, ok = QInputDialog.getText(self, "新建账户", "账户名称:")
        if ok and name.strip():
            acc = db.create_account(name.strip())
            if acc is None:
                QMessageBox.warning(self, "错误", "账户名已存在或无效")
            else:
                self._refresh_list()

    def _on_rename(self):
        aid = self._selected_id()
        if aid is None:
            return
        acc = db.get_account(aid)
        if acc is None:
            return
        name, ok = QInputDialog.getText(self, "重命名", "新名称:", text=acc.name)
        if ok and name.strip() and name.strip() != acc.name:
            if not db.rename_account(aid, name.strip()):
                QMessageBox.warning(self, "错误", "重命名失败（名称重复或无效）")

    def _on_delete(self):
        aid = self._selected_id()
        if aid is None:
            return
        acc = db.get_account(aid)
        if acc is None or acc.name == db.DEFAULT_ACCOUNT_NAME:
            QMessageBox.warning(self, "提示", "不能删除默认账户")
            return
        reply = QMessageBox.question(
            self, "确认删除",
            f"确定删除账户「{acc.name}」及其所有抽卡记录？\n此操作不可撤销！",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            db.delete_account(aid)
            self._refresh_list()


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self._adb: Optional[ADBClient] = None
        self._scanner: Optional[GachaScanner] = None
        self._signals = ScannerSignals()
        self._current_account_id: int = 0
        self._accounts: list = []
        self._setup_ui()
        self._connect_signals()
        self._load_accounts()
        self.setStyleSheet(STYLE)
        self._nav_buttons[0].setChecked(True)
        self._stack.setCurrentIndex(0)

    @property
    def current_account_id(self) -> int:
        return self._current_account_id

    def _connect_signals(self) -> None:
        self._signals.log_msg.connect(self._on_log)
        self._signals.status_msg.connect(self.set_status)
        self._signals.scan_done.connect(self._on_scan_done)
        self._signals.scan_error.connect(self._on_scan_error)

    def _on_log(self, msg: str) -> None:
        now = datetime.now()
        self._log.append(msg)
        # 每50条清理一次超过10分钟的旧日志
        if not hasattr(self, '_log_trim_counter'):
            self._log_trim_counter = 0
        self._log_trim_counter += 1
        if self._log_trim_counter % 50 == 0:
            self._trim_old_logs()

    def _trim_old_logs(self) -> None:
        """移除超过10分钟的日志行"""
        from datetime import timedelta
        cutoff = datetime.now() - timedelta(minutes=10)
        doc = self._log.document()
        blocks_to_remove = []
        for i in range(doc.blockCount()):
            block = doc.findBlockByNumber(i)
            text = block.text()
            # 日志格式: "HH:MM:SS | LEVEL | message"
            if len(text) >= 8 and text[2] == ':':
                try:
                    h, m, s = int(text[0:2]), int(text[3:5]), int(text[6:8])
                    log_time = datetime.now().replace(hour=h, minute=m, second=s, microsecond=0)
                    if log_time < cutoff:
                        blocks_to_remove.append(i)
                except (ValueError, IndexError):
                    pass
        # 从后往前删避免索引错乱
        for i in reversed(blocks_to_remove):
            cursor = self._log.textCursor()
            cursor.movePosition(cursor.MoveOperation.Start)
            for _ in range(i):
                cursor.movePosition(cursor.MoveOperation.Down)
            cursor.movePosition(cursor.MoveOperation.StartOfLine, cursor.MoveMode.MoveAnchor)
            cursor.movePosition(cursor.MoveOperation.Down, cursor.MoveMode.KeepAnchor)
            cursor.movePosition(cursor.MoveOperation.EndOfLine, cursor.MoveMode.KeepAnchor)
            cursor.removeSelectedText()
            cursor.deleteChar()  # 删除换行符

    def _on_scan_done(self, count: int) -> None:
        self.log_msg(f"[完成] 共扫描 {count} 条记录")
        self.set_status(f"扫描完成，共 {count} 条")
        for p in self._pages:
            p.refresh()
        self.set_scan_enabled(True)

    def _on_scan_error(self, msg: str) -> None:
        self.log_msg(f"[ERROR] {msg}")
        self.set_status("扫描失败")
        self.set_scan_enabled(True)

    def log_msg(self, msg: str) -> None:
        """线程安全的日志方法"""
        self._signals.log_msg.emit(msg)

    # ── 账户管理 ──────────────────────────────────────

    def _load_accounts(self) -> None:
        """从数据库加载账户列表到下拉框"""
        self._account_combo.blockSignals(True)
        self._account_combo.clear()
        self._accounts = db.list_accounts()
        for acc in self._accounts:
            self._account_combo.addItem(acc.name, acc.id)

        # 恢复上次选中的账户
        last_id = config.get("gui.last_account_id", 0)
        found = False
        for i, acc in enumerate(self._accounts):
            if acc.id == last_id:
                self._account_combo.setCurrentIndex(i)
                self._current_account_id = acc.id
                found = True
                break
        if not found and self._accounts:
            self._account_combo.setCurrentIndex(0)
            self._current_account_id = self._accounts[0].id
        self._account_combo.blockSignals(False)
        self.refresh_all_pages()

    def _on_account_changed(self, idx: int) -> None:
        if idx < 0:
            return
        self._current_account_id = self._account_combo.currentData()
        config.set("gui.last_account_id", self._current_account_id)
        self.log_msg(f"[INFO] 切换到账户: {self._account_combo.currentText()} (ID={self._current_account_id})")
        self.refresh_all_pages()

    def _on_manage_accounts(self) -> None:
        dlg = AccountDialog(self, self._current_account_id)
        dlg.exec()
        self._load_accounts()
        self.refresh_all_pages()

    # ── UI 构建 ──────────────────────────────────────

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

        # 账户选择
        self._account_combo = QComboBox()
        self._account_combo.setObjectName("accountCombo")
        self._account_combo.setFixedHeight(24)
        self._account_combo.currentIndexChanged.connect(self._on_account_changed)
        bl.addWidget(self._account_combo)

        btn_mgr = QPushButton("⚙")
        btn_mgr.setObjectName("manageAccountBtn")
        btn_mgr.setFixedSize(26, 22)
        btn_mgr.setToolTip("管理账户")
        btn_mgr.clicked.connect(self._on_manage_accounts)
        bl.addWidget(btn_mgr)

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
        for text in ["概览", "设置"]:
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
            SettingsPage(self),
        ]
        s = self._pages[1]
        s.on_adb_connected = self._on_adb_ready
        s.main_window = self
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

    def set_device_status(self, text: str) -> None:
        self._dev_lbl.setText(f"设备: {text}")

    def set_scan_enabled(self, enabled: bool) -> None:
        """切换扫描按钮状态：True=可开始扫描, False=扫描中可停止"""
        self._scan_btn.setEnabled(True)  # 始终可点击
        if enabled:
            self._scan_btn.setText("开始扫描")
            self._scan_btn.setProperty("danger", True)
        else:
            self._scan_btn.setText("⏹ 停止扫描")
            self._scan_btn.setProperty("danger", False)
        self._scan_btn.style().unpolish(self._scan_btn)
        self._scan_btn.style().polish(self._scan_btn)

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
        self.log_msg(f"[INFO] ADB 已连接: {adb._serial}")

    def _on_scan(self) -> None:
        # 如果正在扫描 → 停止
        if self._scanner is not None and self._scanner._is_running:
            self.log_msg("[INFO] 正在停止扫描（当前页完成后停止）...")
            self._scanner.stop()
            self.set_status("正在停止...")
            return

        if self._adb is None:
            self.log_msg("[ERROR] 请先在设置页连接模拟器")
            self.set_status("请先连接模拟器")
            return

        self.set_scan_enabled(False)
        self.set_status("正在扫描...")
        self.log_msg("[INFO] 开始扫描召集记录...")

        from src.automation.gacha_scanner import create_scanner
        from src.models.gacha_record import BannerType
        import threading

        self._scanner = create_scanner(self._adb)
        self._scanner.set_account(self._current_account_id)
        self._scanner.set_banner("活动招募", BannerType.EVENT)

        sig = self._signals
        self._scanner.on_progress(lambda cur, total, info: sig.log_msg.emit(f"[进度] {info}"))
        self._scanner.on_record_found(lambda r: sig.log_msg.emit(f"[记录] {r.character_name} ★{r.rarity.value} {r.banner_name}"))

        def _run():
            try:
                records = self._scanner.scan_all()
                sig.scan_done.emit(len(records))
            except Exception as e:
                sig.scan_error.emit(str(e))

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
