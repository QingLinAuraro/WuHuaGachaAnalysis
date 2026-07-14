"""
抽卡记录页
表格展示所有记录，支持筛选和导出
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTableWidget,
    QTableWidgetItem, QComboBox, QPushButton, QHeaderView,
    QFileDialog, QMessageBox,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor

from src.storage.database import db
from src.storage.exporter import export_to_json, import_from_json
from src.models.gacha_record import GachaRecord, Rarity
from src.analysis.stats import GachaStats


RARITY_COLORS = {
    Rarity.SPECIAL: QColor("#e74c3c"),
    Rarity.EXCELLENT: QColor("#f39c12"),
    Rarity.FINE: QColor("#3498db"),
}


class RecordPage(QWidget):
    """抽卡记录列表页"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        # 标题
        title = QLabel("📋 抽卡记录")
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #2c3e50;")
        layout.addWidget(title)

        # 筛选栏
        filter_layout = QHBoxLayout()
        filter_layout.setSpacing(8)

        filter_layout.addWidget(QLabel("卡池:"))
        self._banner_filter = QComboBox()
        self._banner_filter.addItem("全部卡池", "")
        self._banner_filter.currentIndexChanged.connect(self._apply_filter)
        filter_layout.addWidget(self._banner_filter)

        filter_layout.addWidget(QLabel("稀有度:"))
        self._rarity_filter = QComboBox()
        self._rarity_filter.addItem("全部", None)
        self._rarity_filter.addItem("特出 (5★)", Rarity.SPECIAL.value)
        self._rarity_filter.addItem("优异 (4★)", Rarity.EXCELLENT.value)
        self._rarity_filter.addItem("精良 (3★)", Rarity.FINE.value)
        self._rarity_filter.currentIndexChanged.connect(self._apply_filter)
        filter_layout.addWidget(self._rarity_filter)

        filter_layout.addStretch()

        # 导入/导出按钮
        import_btn = QPushButton("📥 导入JSON")
        import_btn.clicked.connect(self._import_json)
        filter_layout.addWidget(import_btn)

        export_btn = QPushButton("📤 导出JSON")
        export_btn.clicked.connect(self._export_json)
        filter_layout.addWidget(export_btn)

        layout.addLayout(filter_layout)

        # 记录统计
        self._count_label = QLabel("共 0 条记录")
        self._count_label.setStyleSheet("color: #7f8c8d; font-size: 12px;")
        layout.addWidget(self._count_label)

        # 记录表格
        self._table = QTableWidget()
        self._table.setColumnCount(6)
        self._table.setHorizontalHeaderLabels(["器者名称", "稀有度", "卡池", "抽取时间", "序号", "ID"])
        self._table.setAlternatingRowColors(True)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self._table.setColumnHidden(5, True)  # 隐藏ID列
        self._table.setStyleSheet("""
            QTableWidget {
                background-color: white;
                border: 1px solid #e0e0e0;
                border-radius: 6px;
                gridline-color: #f0f0f0;
            }
            QTableWidget::item {
                padding: 6px;
            }
            QHeaderView::section {
                background-color: #fafafa;
                border: none;
                border-bottom: 2px solid #e0e0e0;
                padding: 8px;
                font-weight: bold;
            }
        """)

        layout.addWidget(self._table)

    def on_activated(self) -> None:
        """页面激活时刷新"""
        self._refresh_banner_list()
        self.refresh()

    def refresh(self) -> None:
        self._apply_filter()

    def _refresh_banner_list(self) -> None:
        """刷新卡池下拉列表"""
        current = self._banner_filter.currentData()
        self._banner_filter.blockSignals(True)
        self._banner_filter.clear()
        self._banner_filter.addItem("全部卡池", "")
        for name in db.get_banner_names():
            self._banner_filter.addItem(name, name)
        # 恢复选择
        idx = self._banner_filter.findData(current)
        if idx >= 0:
            self._banner_filter.setCurrentIndex(idx)
        self._banner_filter.blockSignals(False)

    def _apply_filter(self) -> None:
        """应用筛选条件加载数据"""
        banner = self._banner_filter.currentData()
        rarity = self._rarity_filter.currentData()

        records = db.get_all_records(
            banner_name=banner if banner else None,
            rarity=rarity,
        )

        self._populate_table(records)
        self._count_label.setText(f"共 {len(records)} 条记录")

    def _populate_table(self, records: list[GachaRecord]) -> None:
        """填充表格数据"""
        self._table.setRowCount(len(records))

        for row, record in enumerate(records):
            # 器者名称
            name_item = QTableWidgetItem(record.character_name)
            name_item.setForeground(RARITY_COLORS.get(record.rarity, QColor("#333")))
            self._table.setItem(row, 0, name_item)

            # 稀有度
            rarity_item = QTableWidgetItem(f"{'★' * record.rarity.value}")
            rarity_item.setForeground(RARITY_COLORS.get(record.rarity, QColor("#333")))
            self._table.setItem(row, 1, rarity_item)

            # 卡池
            self._table.setItem(row, 2, QTableWidgetItem(record.banner_name))

            # 时间
            time_item = QTableWidgetItem(record.pull_time.strftime("%Y-%m-%d %H:%M:%S"))
            self._table.setItem(row, 3, time_item)

            # 序号
            self._table.setItem(row, 4, QTableWidgetItem(str(record.pull_number)))

            # ID (隐藏)
            self._table.setItem(row, 5, QTableWidgetItem(record.record_id))

    def _export_json(self) -> None:
        """导出JSON文件"""
        path, _ = QFileDialog.getSaveFileName(
            self, "导出抽卡记录", "gacha_export.json", "JSON Files (*.json)"
        )
        if path:
            try:
                output = export_to_json(output_path=path)
                QMessageBox.information(self, "导出成功", f"已导出到:\n{output}")
            except Exception as e:
                QMessageBox.critical(self, "导出失败", str(e))

    def _import_json(self) -> None:
        """导入JSON文件"""
        path, _ = QFileDialog.getOpenFileName(
            self, "导入抽卡记录", "", "JSON Files (*.json)"
        )
        if path:
            try:
                count = import_from_json(path)
                QMessageBox.information(self, "导入成功", f"成功导入 {count} 条新记录")
                self.refresh()
            except Exception as e:
                QMessageBox.critical(self, "导入失败", str(e))
