"""
设置页
模拟器连接配置、ADB设置、OCR设置等
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QComboBox, QGroupBox, QFormLayout, QSpinBox,
    QMessageBox, QFrame,
)
from PyQt6.QtCore import Qt

from src.config import config
from src.emulator.adb_client import list_devices, auto_detect_device, ADBClient


class SettingsPage(QWidget):
    """设置页面"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._adb: ADBClient | None = None
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(16)

        # 标题
        title = QLabel("⚙️ 设置")
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #2c3e50;")
        layout.addWidget(title)

        # ── 模拟器连接 ──────────────────────────

        emu_group = QGroupBox("模拟器连接")
        emu_group.setStyleSheet("""
            QGroupBox {
                font-size: 14px;
                font-weight: bold;
                color: #2c3e50;
                border: 1px solid #e0e0e0;
                border-radius: 8px;
                margin-top: 12px;
                padding-top: 16px;
                background-color: white;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 12px;
                padding: 0 8px;
            }
        """)
        emu_layout = QFormLayout(emu_group)
        emu_layout.setSpacing(10)

        # ADB路径
        adb_layout = QHBoxLayout()
        self._adb_path = QLineEdit(config.get("adb.path", "adb"))
        adb_layout.addWidget(self._adb_path)
        self._adb_path.setPlaceholderText("ADB可执行文件路径，默认 'adb' 使用系统PATH")
        emu_layout.addRow("ADB路径:", adb_layout)

        # 设备地址
        device_layout = QHBoxLayout()
        self._device_addr = QLineEdit("127.0.0.1:7555")
        device_layout.addWidget(self._device_addr)

        detect_btn = QPushButton("自动检测")
        detect_btn.clicked.connect(self._auto_detect)
        device_layout.addWidget(detect_btn)

        connect_btn = QPushButton("连接")
        connect_btn.setStyleSheet("""
            QPushButton {
                background-color: #27ae60;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 6px 16px;
            }
            QPushButton:hover {
                background-color: #219a52;
            }
        """)
        connect_btn.clicked.connect(self._connect_device)
        device_layout.addWidget(connect_btn)

        emu_layout.addRow("设备地址:", device_layout)

        # 模拟器类型
        self._emu_type = QComboBox()
        self._emu_type.addItems(["自动检测", "MuMu模拟器", "雷电模拟器", "蓝叠模拟器"])
        emu_layout.addRow("模拟器类型:", self._emu_type)

        # 连接状态
        self._conn_status = QLabel("⚪ 未连接")
        self._conn_status.setStyleSheet("font-size: 13px;")
        emu_layout.addRow("连接状态:", self._conn_status)

        layout.addWidget(emu_group)

        # ── OCR设置 ─────────────────────────────

        ocr_group = QGroupBox("OCR识别")
        ocr_group.setStyleSheet(emu_group.styleSheet())
        ocr_layout = QFormLayout(ocr_group)
        ocr_layout.setSpacing(10)

        self._ocr_engine = QComboBox()
        self._ocr_engine.addItems(["PaddleOCR", "Tesseract"])
        ocr_layout.addRow("OCR引擎:", self._ocr_engine)

        self._ocr_gpu = QComboBox()
        self._ocr_gpu.addItems(["关闭", "开启"])
        ocr_layout.addRow("GPU加速:", self._ocr_gpu)

        layout.addWidget(ocr_group)

        # ── 扫描设置 ───────────────────────────

        scan_group = QGroupBox("扫描设置")
        scan_group.setStyleSheet(emu_group.styleSheet())
        scan_layout = QFormLayout(scan_group)
        scan_layout.setSpacing(10)

        self._page_delay = QSpinBox()
        self._page_delay.setRange(1, 30)
        self._page_delay.setValue(5)
        self._page_delay.setSuffix(" (×0.1秒)")
        scan_layout.addRow("翻页延迟:", self._page_delay)

        layout.addWidget(scan_group)

        layout.addStretch()

        # ── 操作按钮 ───────────────────────────

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        save_btn = QPushButton("  💾 保存设置")
        save_btn.setStyleSheet("""
            QPushButton {
                background-color: #3498db;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 10px 24px;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #2980b9;
            }
        """)
        save_btn.clicked.connect(self._save_settings)
        btn_layout.addWidget(save_btn)

        layout.addLayout(btn_layout)

    def on_activated(self) -> None:
        """页面激活时刷新"""
        pass

    def refresh(self) -> None:
        pass

    def _auto_detect(self) -> None:
        """自动检测设备"""
        device = auto_detect_device()
        if device:
            self._device_addr.setText(device)
            self._conn_status.setText("🟡 已检测到设备")
        else:
            self._conn_status.setText("🔴 未检测到设备")

    def _connect_device(self) -> None:
        """连接设备"""
        address = self._device_addr.text().strip()
        if not address:
            QMessageBox.warning(self, "提示", "请输入设备地址")
            return

        self._adb = ADBClient(serial=address)
        self._conn_status.setText("🟡 正在连接...")

        if not address.startswith("127.0.0.1") and not address.startswith("localhost"):
            # 可能是直接序列号，检查连接状态
            if self._adb.is_connected():
                self._conn_status.setText("🟢 已连接")
            else:
                self._conn_status.setText("🔴 连接失败")
        else:
            # 网络地址，先connect
            if self._adb.connect(address):
                self._adb._serial = address
                self._conn_status.setText("🟢 已连接")
            else:
                self._conn_status.setText("🔴 连接失败")

    def _save_settings(self) -> None:
        """保存设置"""
        QMessageBox.information(self, "保存", "设置已保存（当前为内存配置，重启后恢复默认）")
