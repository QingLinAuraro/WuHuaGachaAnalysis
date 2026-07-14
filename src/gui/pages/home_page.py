"""首页 — 仅展示特出(5★)记录，类似原神/鸣潮抽卡记录"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QGridLayout, QScrollArea,
)
from src.analysis.stats import GachaStats
from src.models.gacha_record import Rarity


class StatCard(QFrame):
    def __init__(self, title: str, value: str, accent: str = "#c0392b"):
        super().__init__()
        self.setStyleSheet(f"""
            QFrame {{
                background:#252526; border:1px solid #3c3c3c;
                border-radius:6px; border-left:3px solid {accent};
                padding:10px 14px;
            }}
        """)
        l = QVBoxLayout(self)
        l.setContentsMargins(10, 8, 10, 8)
        t = QLabel(title)
        t.setStyleSheet("color:#888; font-size:11px; background:transparent; border:none;")
        l.addWidget(t)
        self._val = QLabel(str(value))
        self._val.setStyleSheet(f"color:{accent}; font-size:22px; font-weight:bold; background:transparent; border:none;")
        l.addWidget(self._val)

    def set_value(self, v): self._val.setText(str(v))


class HomePage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        l = QVBoxLayout(self)
        l.setContentsMargins(16, 12, 16, 12)
        l.setSpacing(8)

        g = QGridLayout()
        g.setSpacing(8)
        self._total_card = StatCard("总抽数", "0", "#007acc")
        self._five_card = StatCard("特出 (5★)", "0", "#c0392b")
        self._rate_card = StatCard("出货率", "0%", "#d4a017")
        g.addWidget(self._total_card, 0, 0)
        g.addWidget(self._five_card, 0, 1)
        g.addWidget(self._rate_card, 0, 2)
        l.addLayout(g)

        l.addWidget(QLabel("特出记录"))
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self._list_w = QWidget()
        self._list = QVBoxLayout(self._list_w)
        self._list.setContentsMargins(0, 0, 0, 0)
        self._list.addStretch()
        scroll.setWidget(self._list_w)
        l.addWidget(scroll)

    def on_activated(self): self.refresh()

    def refresh(self):
        total = GachaStats.total_pulls()
        counts = GachaStats.rarity_counts()
        five = counts.get(Rarity.SPECIAL, 0)
        rate = f"{five/total*100:.1f}%" if total > 0 else "0%"
        self._total_card.set_value(total)
        self._five_card.set_value(five)
        self._rate_card.set_value(rate)

        # 清列表
        while self._list.count():
            w = self._list.takeAt(0).widget()
            if w: w.deleteLater()

        # 只显示特出记录
        from src.storage.database import db
        records = db.get_all_records(rarity=Rarity.SPECIAL)
        for r in records:
            row = QHBoxLayout()
            n = QLabel(r.character_name)
            n.setStyleSheet("color:#c0392b; font-weight:bold;")
            row.addWidget(n)
            row.addWidget(QLabel(r.banner_name))
            row.addStretch()
            row.addWidget(QLabel(f"第{r.pull_number}抽"))
            row.addWidget(QLabel(r.pull_time.strftime("%m-%d %H:%M")))
            rw = QWidget()
            rw.setLayout(row)
            self._list.addWidget(rw)
        self._list.addStretch()
