"""统计分析页"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QTabWidget,
)
from PyQt6.QtCore import Qt
from src.analysis.charts import (
    create_rarity_pie, create_daily_chart, create_pity_chart, create_rate_chart,
)
from src.storage.database import db


class AnalysisPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        l = QVBoxLayout(self)
        l.setContentsMargins(16, 12, 16, 12)
        l.setSpacing(8)

        f = QHBoxLayout()
        f.addWidget(QLabel("卡池:"))
        self._sel = QComboBox()
        self._sel.addItem("全部", "")
        self._sel.currentIndexChanged.connect(self._refresh)
        f.addWidget(self._sel)
        f.addStretch()
        l.addLayout(f)

        self._tabs = QTabWidget()
        for title in ["稀有度分布", "每日趋势", "保底分析", "出率对比"]:
            w = QWidget()
            wl = QVBoxLayout(w)
            lb = QLabel("加载中...")
            lb.setAlignment(Qt.AlignmentFlag.AlignCenter)
            wl.addWidget(lb)
            self._tabs.addTab(w, title)
        l.addWidget(self._tabs)

    def on_activated(self):
        cur = self._sel.currentData()
        self._sel.blockSignals(True)
        self._sel.clear()
        self._sel.addItem("全部", "")
        for n in db.get_banner_names():
            self._sel.addItem(n, n)
        idx = self._sel.findData(cur)
        if idx >= 0:
            self._sel.setCurrentIndex(idx)
        self._sel.blockSignals(False)
        self._refresh()

    def refresh(self): self._refresh()

    def _refresh(self):
        bn = self._sel.currentData() or None
        charts = [create_rarity_pie, create_daily_chart, create_pity_chart, create_rate_chart]
        for i, fn in enumerate(charts):
            try:
                fn(bn)
                self._tabs.widget(i).findChild(QLabel).setText("图表已就绪")
            except Exception as e:
                self._tabs.widget(i).findChild(QLabel).setText(f"生成失败: {e}")
