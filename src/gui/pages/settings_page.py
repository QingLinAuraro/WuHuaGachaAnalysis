"""设置页"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QComboBox, QGroupBox, QFormLayout, QSpinBox,
    QMessageBox,
)
from src.config import config
from src.emulator.adb_client import auto_detect_device, ADBClient


class SettingsPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._adb: ADBClient | None = None
        self.on_adb_connected = None  # 回调: (ADBClient) -> None
        self._setup_ui()

    def _setup_ui(self):
        l = QVBoxLayout(self)
        l.setContentsMargins(16, 12, 16, 12)
        l.setSpacing(10)

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

        g2 = QGroupBox("OCR 识别")
        g2l = QFormLayout(g2)
        g2l.setSpacing(8)
        self._ocr_eng = QComboBox()
        self._ocr_eng.addItems(["PaddleOCR"])
        g2l.addRow("引擎:", self._ocr_eng)
        self._ocr_gpu = QComboBox()
        self._ocr_gpu.addItems(["CPU", "GPU"])
        g2l.addRow("设备:", self._ocr_gpu)
        l.addWidget(g2)

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

    def on_activated(self): pass
    def refresh(self): pass

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
