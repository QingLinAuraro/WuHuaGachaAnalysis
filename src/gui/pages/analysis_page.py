"""
统计分析页
展示图表（使用 PyQt6 WebEngine 渲染 ECharts）
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QTabWidget, QScrollArea,
)
from PyQt6.QtCore import QUrl, Qt

from src.analysis.charts import (
    create_rarity_pie, create_daily_chart, create_pity_chart,
    create_rate_chart,
)
from src.storage.database import db


class AnalysisPage(QWidget):
    """统计分析页"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._chart_widgets: list = []
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        # 标题
        title = QLabel("📊 统计分析")
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #2c3e50;")
        layout.addWidget(title)

        # 卡池选择
        filter_layout = QHBoxLayout()
        filter_layout.addWidget(QLabel("选择卡池:"))
        self._banner_selector = QComboBox()
        self._banner_selector.addItem("全部卡池", "")
        self._banner_selector.currentIndexChanged.connect(self._refresh_charts)
        filter_layout.addWidget(self._banner_selector)
        filter_layout.addStretch()
        layout.addLayout(filter_layout)

        # 图表区域（使用 Tab 方式展示多个图表）
        self._tabs = QTabWidget()
        self._tabs.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid #e0e0e0;
                border-radius: 6px;
                background-color: white;
            }
            QTabBar::tab {
                padding: 8px 20px;
                font-size: 13px;
            }
            QTabBar::tab:selected {
                color: #3498db;
                border-bottom: 2px solid #3498db;
            }
        """)

        # 稀有度分布
        self._pie_tab = QWidget()
        pie_layout = QVBoxLayout(self._pie_tab)
        self._pie_label = QLabel("加载中...")
        self._pie_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pie_layout.addWidget(self._pie_label)
        self._tabs.addTab(self._pie_tab, "稀有度分布")

        # 抽卡趋势
        self._daily_tab = QWidget()
        daily_layout = QVBoxLayout(self._daily_tab)
        self._daily_label = QLabel("加载中...")
        self._daily_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        daily_layout.addWidget(self._daily_label)
        self._tabs.addTab(self._daily_tab, "每日趋势")

        # 保底距离
        self._pity_tab = QWidget()
        pity_layout = QVBoxLayout(self._pity_tab)
        self._pity_label = QLabel("加载中...")
        self._pity_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pity_layout.addWidget(self._pity_label)
        self._tabs.addTab(self._pity_tab, "保底分析")

        # 出率对比
        self._rate_tab = QWidget()
        rate_layout = QVBoxLayout(self._rate_tab)
        self._rate_label = QLabel("加载中...")
        self._rate_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        rate_layout.addWidget(self._rate_label)
        self._tabs.addTab(self._rate_tab, "出率对比")

        layout.addWidget(self._tabs)

    def on_activated(self) -> None:
        """页面激活时刷新"""
        self._refresh_banner_list()
        self._refresh_charts()

    def refresh(self) -> None:
        self._refresh_charts()

    def _refresh_banner_list(self) -> None:
        """刷新卡池下拉列表"""
        current = self._banner_selector.currentData()
        self._banner_selector.blockSignals(True)
        self._banner_selector.clear()
        self._banner_selector.addItem("全部卡池", "")
        for name in db.get_banner_names():
            self._banner_selector.addItem(name, name)
        idx = self._banner_selector.findData(current)
        if idx >= 0:
            self._banner_selector.setCurrentIndex(idx)
        self._banner_selector.blockSignals(False)

    def _refresh_charts(self) -> None:
        """刷新所有图表"""
        banner = self._banner_selector.currentData()
        banner_name = banner if banner else None

        # 由于 PyQt6 WebEngine 可能较大，这里使用 pyecharts 的 render_embed
        # 实际 WebView 渲染可在后续加入。当前用 HTML 文本摘要展示
        try:
            pie = create_rarity_pie(banner_name)
            pie_html = pie.render_embed()
            self._pie_label.setText(f"稀有度分布图表已生成\n数据点数: {len(pie.options.get('series', [{}])[0].get('data', [])) if pie.options.get('series') else 0}")
        except Exception as e:
            self._pie_label.setText(f"图表生成失败: {e}")

        try:
            daily = create_daily_chart(banner_name)
            self._daily_label.setText(f"每日趋势图表已生成\n数据范围: 最近30天")
        except Exception as e:
            self._daily_label.setText(f"图表生成失败: {e}")

        try:
            pity = create_pity_chart(banner_name)
            self._pity_label.setText(f"保底分析图表已生成")
        except Exception as e:
            self._pity_label.setText(f"图表生成失败: {e}")

        try:
            rate = create_rate_chart(banner_name)
            self._rate_label.setText(f"出率对比图表已生成")
        except Exception as e:
            self._rate_label.setText(f"图表生成失败: {e}")
