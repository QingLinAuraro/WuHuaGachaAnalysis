"""
首页概览页
展示总览统计、保底计数、最近抽卡、快速操作
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QGridLayout, QScrollArea, QSizePolicy,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont

from src.analysis.stats import GachaStats
from src.models.gacha_record import Rarity


class StatCard(QFrame):
    """统计卡片组件"""

    def __init__(self, title: str, value: str, color: str = "#3498db") -> None:
        super().__init__()
        self.setObjectName("statCard")
        self.setStyleSheet(f"""
            #statCard {{
                background-color: white;
                border-radius: 10px;
                border-left: 4px solid {color};
                padding: 16px;
            }}
        """)
        self.setMinimumHeight(100)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)

        title_label = QLabel(title)
        title_label.setStyleSheet("color: #7f8c8d; font-size: 12px;")
        layout.addWidget(title_label)

        value_label = QLabel(str(value))
        value_label.setStyleSheet(f"color: {color}; font-size: 28px; font-weight: bold;")
        layout.addWidget(value_label)


class HomePage(QWidget):
    """首页 - 数据概览仪表板"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(16)

        # 页面标题
        title = QLabel("📊 数据概览")
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #2c3e50;")
        layout.addWidget(title)

        # 统计卡片行
        cards_layout = QGridLayout()
        cards_layout.setSpacing(12)

        self._total_card = StatCard("总抽数", "0", "#3498db")
        self._five_star_card = StatCard("特出 (5★)", "0", "#e74c3c")
        self._four_star_card = StatCard("优异 (4★)", "0", "#f39c12")
        self._pity_card = StatCard("当前保底计数", "0 抽", "#9b59b6")

        cards_layout.addWidget(self._total_card, 0, 0)
        cards_layout.addWidget(self._five_star_card, 0, 1)
        cards_layout.addWidget(self._four_star_card, 1, 0)
        cards_layout.addWidget(self._pity_card, 1, 1)

        layout.addLayout(cards_layout)

        # 最近抽卡标题
        recent_title = QLabel("🕐 最近抽卡记录")
        recent_title.setStyleSheet("font-size: 15px; font-weight: bold; color: #2c3e50; margin-top: 8px;")
        layout.addWidget(recent_title)

        # 最近记录列表
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        self._recent_list = QWidget()
        self._recent_layout = QVBoxLayout(self._recent_list)
        self._recent_layout.setContentsMargins(0, 0, 0, 0)
        self._recent_layout.setSpacing(4)
        self._recent_layout.addStretch()

        scroll.setWidget(self._recent_list)
        layout.addWidget(scroll)

    def on_activated(self) -> None:
        """页面被激活时刷新"""
        self.refresh()

    def refresh(self) -> None:
        """刷新统计数据"""
        # 更新卡片
        total = GachaStats.total_pulls()
        counts = GachaStats.rarity_counts()
        pity = GachaStats.pity_count()

        self._total_card.findChildren(QLabel)[1].setText(str(total))
        self._five_star_card.findChildren(QLabel)[1].setText(str(counts.get(Rarity.SPECIAL.value, 0)))
        self._four_star_card.findChildren(QLabel)[1].setText(str(counts.get(Rarity.EXCELLENT.value, 0)))
        self._pity_card.findChildren(QLabel)[1].setText(f"{pity} 抽")

        # 更新最近记录
        # 清除旧记录
        for i in reversed(range(self._recent_layout.count())):
            item = self._recent_layout.itemAt(i)
            if item and item.widget():
                item.widget().deleteLater()

        records = GachaStats.get_recent(20)
        rarity_colors = {
            Rarity.SPECIAL: "#e74c3c",
            Rarity.EXCELLENT: "#f39c12",
            Rarity.FINE: "#3498db",
        }

        for record in records:
            color = rarity_colors.get(record.rarity, "#95a5a6")
            card = QFrame()
            card.setStyleSheet(f"""
                QFrame {{
                    background-color: white;
                    border-radius: 6px;
                    border-left: 3px solid {color};
                    padding: 4px;
                }}
            """)
            card_layout = QHBoxLayout(card)
            card_layout.setContentsMargins(12, 6, 12, 6)

            name_label = QLabel(record.character_name)
            name_label.setStyleSheet(f"color: {color}; font-weight: bold; font-size: 13px;")
            card_layout.addWidget(name_label)

            rarity_label = QLabel(f"{'★' * record.rarity.value}")
            rarity_label.setStyleSheet(f"color: {color}; font-size: 12px;")
            card_layout.addWidget(rarity_label)

            card_layout.addStretch()

            time_label = QLabel(record.pull_time.strftime("%m-%d %H:%M"))
            time_label.setStyleSheet("color: #95a5a6; font-size: 11px;")
            card_layout.addWidget(time_label)

            banner_label = QLabel(record.banner_name)
            banner_label.setStyleSheet("color: #7f8c8d; font-size: 11px;")
            card_layout.addWidget(banner_label)

            self._recent_layout.addWidget(card)

        self._recent_layout.addStretch()
