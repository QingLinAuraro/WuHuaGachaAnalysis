"""
图表生成模块
使用 pyecharts 生成 ECharts 图表，供 PyQt6 WebView 展示
"""

from typing import Optional

from pyecharts import options as opts
from pyecharts.charts import Pie, Bar, Line, Page as EPage

from src.analysis.stats import GachaStats
from src.models.gacha_record import Rarity


# 稀有度颜色映射
RARITY_COLORS = {
    Rarity.SPECIAL: "#e74c3c",   # 红
    Rarity.EXCELLENT: "#f39c12", # 黄
    Rarity.FINE: "#3498db",      # 蓝
}


RARITY_LABELS = {
    Rarity.SPECIAL: "特出(5★)",
    Rarity.EXCELLENT: "优异(4★)",
    Rarity.FINE: "精良(3★)",
}


def create_rarity_pie(banner_name: Optional[str] = None) -> Pie:
    """稀有度分布饼图"""
    counts = GachaStats.rarity_counts(banner_name=banner_name)

    data_pairs = []
    for rarity in [Rarity.SPECIAL, Rarity.EXCELLENT, Rarity.FINE]:
        count = counts.get(rarity.value, 0)
        if count > 0:
            data_pairs.append((RARITY_LABELS[rarity], count))

    pie = (
        Pie()
        .add(
            series_name="稀有度分布",
            data_pair=data_pairs,
            radius=["40%", "70%"],
            label_opts=opts.LabelOpts(formatter="{b}: {c} ({d}%)"),
        )
        .set_colors([RARITY_COLORS[r] for r in [Rarity.SPECIAL, Rarity.EXCELLENT, Rarity.FINE]])
        .set_global_opts(
            title_opts=opts.TitleOpts(title="稀有度分布"),
            legend_opts=opts.LegendOpts(orient="vertical", pos_right="5%", pos_top="middle"),
        )
    )
    return pie


def create_daily_chart(banner_name: Optional[str] = None, days: int = 30) -> Line:
    """每日抽卡趋势折线图"""
    daily = GachaStats.daily_stats(banner_name=banner_name, days=days)

    dates = [d["date"] for d in daily]
    totals = [d["total"] for d in daily]
    five_stars = [d["five_star"] for d in daily]

    line = (
        Line()
        .add_xaxis(dates)
        .add_yaxis(
            "总抽数",
            totals,
            is_smooth=True,
            linestyle_opts=opts.LineStyleOpts(width=2),
        )
        .add_yaxis(
            "特出",
            five_stars,
            is_smooth=True,
            linestyle_opts=opts.LineStyleOpts(width=2),
            areastyle_opts=opts.AreaStyleOpts(opacity=0.15),
        )
        .set_global_opts(
            title_opts=opts.TitleOpts(title="每日抽卡趋势"),
            xaxis_opts=opts.AxisOpts(axislabel_opts=opts.LabelOpts(rotate=45)),
            legend_opts=opts.LegendOpts(pos_top="5%"),
            datazoom_opts=[opts.DataZoomOpts(range_start=0, range_end=100)],
        )
    )
    return line


def create_pity_chart(banner_name: Optional[str] = None) -> Bar:
    """保底距离柱状图"""
    history = GachaStats.pity_history(banner_name=banner_name)

    if not history:
        return (
            Bar()
            .add_xaxis([])
            .add_yaxis("保底距离", [])
            .set_global_opts(title_opts=opts.TitleOpts(title="保底距离（暂无数据）"))
        )

    characters = [h["character_name"] for h in history]
    distances = [h["pity_count"] for h in history]

    bar = (
        Bar()
        .add_xaxis(characters)
        .add_yaxis(
            "距离上次5★的抽数",
            distances,
            itemstyle_opts=opts.ItemStyleOpts(color="#e74c3c"),
            markline_opts=opts.MarkLineOpts(
                data=[opts.MarkLineItem(y=70, name="硬保底线")],
                linestyle_opts=opts.LineStyleOpts(type_="dashed", color="#999"),
            ),
        )
        .set_global_opts(
            title_opts=opts.TitleOpts(title="保底距离"),
            xaxis_opts=opts.AxisOpts(axislabel_opts=opts.LabelOpts(rotate=45)),
            yaxis_opts=opts.AxisOpts(name="抽数"),
        )
    )
    return bar


def create_rate_chart(banner_name: Optional[str] = None) -> Bar:
    """出率对比柱状图（实际 vs 理论）"""
    actual = GachaStats.rate_5star(banner_name=banner_name)
    # 物华弥新理论概率约 1.6%（含软保底）
    theoretical = 0.016

    bar = (
        Bar()
        .add_xaxis(["实际出率", "理论出率"])
        .add_yaxis(
            "出率",
            [round(actual * 100, 2), round(theoretical * 100, 2)],
            itemstyle_opts=opts.ItemStyleOpts(
                color="#e74c3c" if actual >= theoretical else "#3498db"
            ),
        )
        .set_global_opts(
            title_opts=opts.TitleOpts(title="5★出率对比"),
            yaxis_opts=opts.AxisOpts(name="%", axislabel_opts=opts.LabelOpts(formatter="{value}%")),
        )
    )
    return bar


def generate_dashboard_html(banner_name: Optional[str] = None) -> str:
    """
    生成分析仪表板 HTML 字符串
    可直接在 PyQt6 WebView 中渲染
    """
    page = EPage(layout=Page.DraggablePageLayout)
    page.add(
        create_rarity_pie(banner_name),
        create_daily_chart(banner_name),
        create_pity_chart(banner_name),
        create_rate_chart(banner_name),
    )
    return page.render_embed()
