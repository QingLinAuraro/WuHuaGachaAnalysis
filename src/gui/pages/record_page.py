"""抽卡记录页"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTableWidget,
    QTableWidgetItem, QComboBox, QPushButton, QHeaderView,
    QFileDialog, QMessageBox,
)
from PyQt6.QtGui import QColor
from src.storage.database import db
from src.storage.exporter import export_to_json, import_from_json
from src.models.gacha_record import Rarity

RARITY_COLORS = {Rarity.SPECIAL: QColor("#c0392b"), Rarity.EXCELLENT: QColor("#d4a017"), Rarity.FINE: QColor("#3498db")}


class RecordPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        l = QVBoxLayout(self)
        l.setContentsMargins(16, 12, 16, 12)
        l.setSpacing(8)

        f = QHBoxLayout()
        self._banner = QComboBox()
        self._banner.addItem("全部卡池", "")
        self._banner.currentIndexChanged.connect(self._apply)
        f.addWidget(QLabel("卡池:"))
        f.addWidget(self._banner)
        self._rarity = QComboBox()
        self._rarity.addItem("全部", None)
        self._rarity.addItem("特出 5★", Rarity.SPECIAL.value)
        self._rarity.addItem("优异 4★", Rarity.EXCELLENT.value)
        self._rarity.addItem("新生 3★", Rarity.FINE.value)
        self._rarity.currentIndexChanged.connect(self._apply)
        f.addWidget(QLabel("稀有度:"))
        f.addWidget(self._rarity)
        f.addStretch()
        imp = QPushButton("导入 JSON")
        imp.clicked.connect(self._import)
        f.addWidget(imp)
        exp = QPushButton("导出 JSON")
        exp.clicked.connect(self._export)
        f.addWidget(exp)
        l.addLayout(f)

        self._cnt = QLabel("0 条记录")
        l.addWidget(self._cnt)

        self._table = QTableWidget()
        self._table.setColumnCount(5)
        self._table.setHorizontalHeaderLabels(["器者", "稀有度", "卡池", "时间", "序号"])
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        l.addWidget(self._table)

    def on_activated(self):
        self._banner.blockSignals(True)
        cur = self._banner.currentData()
        self._banner.clear()
        self._banner.addItem("全部卡池", "")
        for n in db.get_banner_names():
            self._banner.addItem(n, n)
        idx = self._banner.findData(cur)
        if idx >= 0:
            self._banner.setCurrentIndex(idx)
        self._banner.blockSignals(False)
        self.refresh()

    def refresh(self): self._apply()

    def _apply(self):
        bn = self._banner.currentData() or None
        rv = self._rarity.currentData()
        records = db.get_all_records(banner_name=bn, rarity=rv)
        self._table.setRowCount(len(records))
        for i, r in enumerate(records):
            n = QTableWidgetItem(r.character_name or "?")
            color = RARITY_COLORS.get(r.rarity)
            if color:
                n.setForeground(color)
            self._table.setItem(i, 0, n)
            s = QTableWidgetItem("★" * max(r.rarity.value, 1))
            self._table.setItem(i, 1, s)
            self._table.setItem(i, 2, QTableWidgetItem(r.banner_name or ""))
            try:
                t = r.pull_time.strftime("%Y-%m-%d %H:%M") if r.pull_time else ""
            except Exception:
                t = str(r.pull_time)
            self._table.setItem(i, 3, QTableWidgetItem(t))
            self._table.setItem(i, 4, QTableWidgetItem(str(r.pull_number)))
        self._cnt.setText(f"{len(records)} 条记录")

    def _export(self):
        p, _ = QFileDialog.getSaveFileName(self, "导出", "gacha_export.json", "JSON (*.json)")
        if p:
            export_to_json(output_path=p)
            QMessageBox.information(self, "完成", f"已导出到 {p}")

    def _import(self):
        p, _ = QFileDialog.getOpenFileName(self, "导入", "", "JSON (*.json)")
        if p:
            n = import_from_json(p)
            QMessageBox.information(self, "完成", f"导入了 {n} 条记录")
            self.refresh()
