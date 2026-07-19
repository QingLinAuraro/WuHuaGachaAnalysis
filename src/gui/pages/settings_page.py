"""设置页"""
from typing import Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QComboBox, QGroupBox, QFormLayout, QSpinBox,
    QMessageBox, QScrollArea,
)
from src.config import config
from src.emulator.adb_client import auto_detect_device, ADBClient


class SettingsPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._adb: Optional[ADBClient] = None
        self.on_adb_connected = None
        self.main_window = None
        self._setup_ui()

    def _setup_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea{border:none;}")

        content = QWidget()
        l = QVBoxLayout(content)
        l.setContentsMargins(16, 12, 16, 12)
        l.setSpacing(10)

        # ── 模拟器连接 ──
        g = QGroupBox("模拟器连接")
        gl = QFormLayout(g)
        gl.setSpacing(8)

        self._adb_path = QLineEdit(config.get("adb.path", "adb"))
        self._adb_path.setPlaceholderText("auto (自动搜索)")
        gl.addRow("ADB 路径:", self._adb_path)

        row = QHBoxLayout()
        self._addr = QLineEdit("127.0.0.1:16384")
        self._addr.setPlaceholderText("127.0.0.1:16384")
        row.addWidget(self._addr)
        b = QPushButton("检测")
        b.clicked.connect(self._detect)
        row.addWidget(b)
        b2 = QPushButton("连接")
        b2.setProperty("primary", True)
        b2.clicked.connect(self._connect)
        row.addWidget(b2)
        gl.addRow("设备地址:", row)

        self._emu = QComboBox()
        self._emu.addItems(["auto", "MuMu", "雷电", "蓝叠"])
        gl.addRow("模拟器:", self._emu)

        self._st = QLabel("未连接")
        gl.addRow("状态:", self._st)
        l.addWidget(g)

        # ── 账户管理（入口按钮） ──
        g4 = QGroupBox("账户管理")
        g4l = QHBoxLayout(g4)
        g4l.setContentsMargins(12, 8, 12, 8)
        g4l.addWidget(QLabel("点击下方按钮管理账户（新建、重命名、删除）"))
        g4l.addStretch()
        btn_mgr = QPushButton("管理账户")
        btn_mgr.setProperty("primary", True)
        btn_mgr.clicked.connect(self._open_account_dialog)
        g4l.addWidget(btn_mgr)
        l.addWidget(g4)

        # ── 扫描 ──
        g3 = QGroupBox("扫描设置")
        g3l = QFormLayout(g3)
        g3l.setSpacing(8)
        self._delay = QSpinBox()
        self._delay.setRange(1, 30)
        self._delay.setValue(5)
        self._delay.setSuffix(" ×0.1秒")
        g3l.addRow("翻页延迟:", self._delay)
        l.addWidget(g3)
        l.addStretch()

        scroll.setWidget(content)
        outer.addWidget(scroll)

    def on_activated(self):
        pass

    def refresh(self):
        pass

    def _open_account_dialog(self):
        """打开账户管理弹窗"""
        from src.gui.main_window import AccountDialog
        current_id = 0
        if self.main_window is not None:
            current_id = self.main_window.current_account_id
        dlg = AccountDialog(self, current_id)
        dlg.exec()
        if self.main_window is not None:
            self.main_window._load_accounts()
            self.main_window.refresh_all_pages()

    # ── ADB ──

    def _detect(self):
        d = auto_detect_device()
        if d:
            self._addr.setText(d)
            self._st.setText("已检测到")
        else:
            self._st.setText("未找到设备")

    def _connect(self):
        addr = self._addr.text().strip()
        if not addr:
            QMessageBox.warning(self, "错误", "请输入设备地址")
            return
        self._adb = ADBClient(serial=addr)
        if self._adb.connect(addr):
            self._adb._serial = addr
            self._st.setText("已连接")
            if self.on_adb_connected:
                self.on_adb_connected(self._adb)
        else:
            self._st.setText("连接失败")
