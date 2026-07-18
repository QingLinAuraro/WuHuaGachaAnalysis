"""首页 — 按卡池分组的时间线"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea, QFrame,
)
from pathlib import Path
from collections import OrderedDict
import yaml

from src.models.gacha_record import Rarity, BannerType
from src.storage.database import db


def _load_up_map():
    path = Path(__file__).parent.parent.parent.parent / "config" / "names.yaml"
    try:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f).get("banners", {})
    except Exception:
        return {}


def _pool_key(banner_type):
    if banner_type in (BannerType.LIMITED_TIME, BannerType.LIMITED):
        return banner_type
    return BannerType.UNKNOWN


def _build_timeline():
    up_map = _load_up_map()
    records = db.get_all_records()
    if not records:
        return [], 0, 0, 0, {}

    records.sort(key=lambda r: r.pull_number)
    banners = OrderedDict()
    pity = {}

    for r in records:
        pk = _pool_key(r.banner_type)
        pity[pk] = pity.get(pk, 0) + 1
        if r.rarity == Rarity.SPECIAL:
            bn = r.banner_name or "未知"
            up_char = up_map.get(bn, "")
            off = up_char and r.character_name != up_char
            if bn not in banners:
                banners[bn] = {"type": r.banner_type, "chars": []}
            banners[bn]["chars"].append({
                "name": r.character_name, "pull_number": r.pull_number,
                "off": off, "pity": pity[pk],
            })
            pity[pk] = 0

    total = len(records)
    total_5 = sum(len(v["chars"]) for v in banners.values())
    off_count = sum(1 for v in banners.values() for r in v["chars"] if r["off"])
    for bn in banners:
        banners[bn]["chars"].reverse()
    pool_pity = {k: v for k, v in pity.items() if v > 0}
    return banners, total, total_5, off_count, pool_pity


class HomePage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        l = QVBoxLayout(self)
        l.setContentsMargins(12, 8, 12, 8)
        l.setSpacing(4)

        self._stat = QLabel()
        self._stat.setStyleSheet("color:#888; font-size:13px; padding:4px 0;")
        l.addWidget(self._stat)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._list_w = QWidget()
        self._list = QVBoxLayout(self._list_w)
        self._list.setContentsMargins(0, 0, 0, 0)
        self._list.setSpacing(2)
        self._list.addStretch()
        self._scroll.setWidget(self._list_w)
        l.addWidget(self._scroll)

    def on_activated(self):
        self.refresh()

    def refresh(self):
        banners, total, total_5, off_count, pool_pity = _build_timeline()
        if not banners:
            self._stat.setText("暂无记录")
            return

        rate = ((total_5 - off_count) / total_5 * 100) if total_5 > 0 else 0
        self._stat.setText(
            f"总抽数: {total}  |  特出: {total_5}/{off_count}  |  不歪率: {rate:.1f}%"
        )

        # 清旧内容
        while self._list.count():
            w = self._list.takeAt(0).widget()
            if w:
                w.deleteLater()

        for bn, data in banners.items():
            # 卡池大区块
            block = QFrame()
            block.setStyleSheet("background:#1e1e1e; border:1px solid #3c3c3c;")
            bl = QVBoxLayout(block)
            bl.setContentsMargins(0, 0, 0, 6)
            bl.setSpacing(0)

            # 标题
            bl.addWidget(self._make_title(bn, data["type"]))
            # 垫抽
            pk = _pool_key(data["type"])
            if pk in pool_pity and pool_pity[pk] > 0:
                bl.addWidget(self._make_pity(pool_pity[pk]))
            # 特出
            for c in data["chars"]:
                bl.addWidget(self._make_pull(c["pity"], c["name"], c["off"]))

            self._list.addWidget(block)

        self._list.addStretch()

    def _make_title(self, banner_name, pool_type):
        type_label = {"限时": "限时", "限定": "限定"}.get(pool_type, "")
        ptype = f" [{type_label}]" if type_label else ""
        w = QFrame()
        w.setStyleSheet("background:#3c3c3c; padding:4px 10px;")
        w.setMinimumHeight(28)
        l = QHBoxLayout(w)
        l.setContentsMargins(10, 2, 10, 2)
        lb = QLabel(f"{banner_name}{ptype}")
        lb.setStyleSheet("color:#f39c12; font-size:14px; font-weight:bold; border:none; background:transparent;")
        l.addWidget(lb)
        l.addStretch()
        return w

    def _make_pity(self, count):
        w = QFrame()
        w.setStyleSheet("background:#2d2d2d; border-left:4px solid #888; padding:2px 0; margin:1px 0;")
        w.setFixedHeight(32)
        row = QHBoxLayout(w)
        row.setContentsMargins(8, 0, 8, 0)
        cnt = QLabel(f"{count}抽")
        cnt.setStyleSheet("color:#888; font-weight:bold; font-size:13px; border:none; background:transparent;")
        cnt.setFixedWidth(55)
        row.addWidget(cnt)
        lb = QLabel("垫")
        lb.setStyleSheet("color:#888; font-size:13px; font-weight:bold; border:none; background:transparent;")
        row.addWidget(lb)
        row.addStretch()
        return w

    def _make_pull(self, pull_count, name, off_banner):
        color = "#e74c3c" if off_banner else "#3498db"
        w = QFrame()
        w.setStyleSheet(f"background:#252526; border-left:4px solid {color}; padding:2px 0; margin:1px 0;")
        w.setFixedHeight(32)
        row = QHBoxLayout(w)
        row.setContentsMargins(8, 0, 8, 0)
        row.setSpacing(8)
        cnt = QLabel(f"{pull_count}抽")
        cnt.setStyleSheet(f"color:{color}; font-weight:bold; font-size:13px; border:none; background:transparent;")
        cnt.setFixedWidth(55)
        row.addWidget(cnt)
        nm = QLabel(name)
        nm.setStyleSheet("color:#e0e0e0; font-size:13px; font-weight:bold; border:none; background:transparent;")
        row.addWidget(nm)
        row.addStretch()
        mark = "歪" if off_banner else "UP"
        mk = QLabel(mark)
        mk.setStyleSheet(f"color:#fff; font-size:10px; font-weight:bold; background:{color}; border-radius:3px; padding:1px 5px;")
        row.addWidget(mk)
        return w
