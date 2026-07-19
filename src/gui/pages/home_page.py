"""首页 — 按卡池分组的时间线（带头像占位和日期）"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea, QFrame,
)
from PyQt6.QtCore import Qt
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


def _build_timeline(account_id: int = 0):
    """构建指定账户的卡池时间线"""
    up_map = _load_up_map()
    if account_id > 0:
        records = db.get_all_records(account_id=account_id)
    else:
        records = db.get_all_records()  # 无账户筛选（兼容）
    if not records:
        return [], 0, 0, 0, {}, ""

    records.sort(key=lambda r: r.pull_number)
    banners = OrderedDict()
    pity = {}
    pool_banner = {}  # pool_type → (banner_name, banner_type)

    for r in records:
        pk = _pool_key(r.banner_type)
        pity[pk] = pity.get(pk, 0) + 1
        if r.banner_name:
            pool_banner[pk] = (r.banner_name, r.banner_type)
        if r.rarity == Rarity.SPECIAL:
            bn = r.banner_name or "未知"
            up_char = up_map.get(bn, "")
            off = up_char and r.character_name != up_char
            if bn not in banners:
                banners[bn] = {"type": r.banner_type, "chars": []}
            banners[bn]["chars"].append({
                "name": r.character_name,
                "pull_number": r.pull_number,
                "pull_date": r.pull_date,
                "off": off,
                "pity": pity[pk],
            })
            pity[pk] = 0

    # 没有抽出特出的池子也显示垫抽
    for pk, remaining in pity.items():
        if remaining > 0 and pk in pool_banner:
            bn, bt = pool_banner[pk]
            if bn and bn not in banners:
                banners[bn] = {"type": bt, "chars": []}

    total = len(records)
    total_5 = sum(len(v["chars"]) for v in banners.values())
    off_count = sum(1 for v in banners.values() for r in v["chars"] if r["off"])
    for bn in banners:
        banners[bn]["chars"].reverse()
    pool_pity = {k: v for k, v in pity.items() if v > 0}

    # 获取账户名称
    account_name = ""
    if account_id:
        acc = db.get_account(account_id)
        if acc:
            account_name = acc.name

    return banners, total, total_5, off_count, pool_pity, account_name


class HomePage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._main_window = parent
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
        account_id = self._main_window.current_account_id if self._main_window else 0
        banners, total, total_5, off_count, pool_pity, account_name = _build_timeline(account_id)

        # 先清旧内容（无论是否有数据）
        while self._list.count():
            w = self._list.takeAt(0).widget()
            if w:
                w.deleteLater()

        if not banners:
            self._stat.setText("暂无记录")
            self._list.addStretch()
            return

        rate = ((total_5 - off_count) / total_5 * 100) if total_5 > 0 else 0
        header = f"总抽数: {total}  |  特出: {total_5}/{off_count}  |  不歪率: {rate:.1f}%"
        if account_name:
            header = f"[{account_name}]  " + header
        self._stat.setText(header)

        for bn, data in banners.items():
            block = QFrame()
            block.setStyleSheet("background:#1e1e1e; border:1px solid #3c3c3c;")
            bl = QVBoxLayout(block)
            bl.setContentsMargins(0, 0, 0, 6)
            bl.setSpacing(1)

            # 标题
            bl.addWidget(self._make_title(bn, data["type"]))
            # 垫抽
            pk = _pool_key(data["type"])
            if pk in pool_pity and pool_pity[pk] > 0:
                bl.addWidget(self._make_pity(pool_pity[pk]))
            # 特出
            for c in data["chars"]:
                bl.addWidget(self._make_pull(
                    c["pity"], c["name"], c["pull_date"], c["off"]
                ))

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
        w.setFixedHeight(36)
        row = QHBoxLayout(w)
        row.setContentsMargins(8, 0, 8, 0)
        # 空白头像占位
        avatar = QLabel()
        avatar.setFixedSize(32, 32)
        avatar.setStyleSheet("background:#3a3a3a; border-radius:4px; border:none;")
        row.addWidget(avatar)
        cnt = QLabel(f"{count}抽")
        cnt.setStyleSheet("color:#888; font-weight:bold; font-size:13px; border:none; background:transparent;")
        cnt.setFixedWidth(55)
        row.addWidget(cnt)
        lb = QLabel("垫")
        lb.setStyleSheet("color:#888; font-size:13px; font-weight:bold; border:none; background:transparent;")
        row.addWidget(lb)
        row.addStretch()
        return w

    def _make_pull(self, pull_count, name, pull_date, off_banner):
        color = "#e74c3c" if off_banner else "#3498db"
        w = QFrame()
        w.setStyleSheet(f"background:#252526; border-left:4px solid {color}; padding:2px 0; margin:1px 0;")
        w.setFixedHeight(44)
        row = QHBoxLayout(w)
        row.setContentsMargins(8, 3, 8, 3)
        row.setSpacing(8)

        # 头像占位 — 40×40 圆角色块，显示首字
        avatar_bg = "#3498db" if not off_banner else "#e74c3c"
        avatar = QFrame()
        avatar.setFixedSize(36, 36)
        avatar.setStyleSheet(
            f"background:{avatar_bg}; border-radius:6px; border:none;"
        )
        avatar_layout = QVBoxLayout(avatar)
        avatar_layout.setContentsMargins(0, 0, 0, 0)
        avatar_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        first_char = name[0] if name else "?"
        char_label = QLabel(first_char)
        char_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        char_label.setStyleSheet("color:white; font-size:16px; font-weight:bold; border:none; background:transparent;")
        avatar_layout.addWidget(char_label)
        row.addWidget(avatar)

        # 第N抽
        cnt = QLabel(f"{pull_count}抽")
        cnt.setStyleSheet(f"color:{color}; font-weight:bold; font-size:13px; border:none; background:transparent;")
        cnt.setFixedWidth(55)
        row.addWidget(cnt)

        # 角色名
        nm = QLabel(name)
        nm.setStyleSheet("color:#e0e0e0; font-size:13px; font-weight:bold; border:none; background:transparent;")
        row.addWidget(nm)

        # 出货日期 (月-日)
        if pull_date:
            date_lbl = QLabel(pull_date)
            date_lbl.setStyleSheet("color:#888; font-size:11px; border:none; background:transparent;")
            row.addWidget(date_lbl)

        row.addStretch()

        # UP/歪 标签
        mark = "歪" if off_banner else "UP"
        mk = QLabel(mark)
        mk.setStyleSheet(f"color:#fff; font-size:10px; font-weight:bold; background:{color}; border-radius:3px; padding:1px 5px;")
        row.addWidget(mk)
        return w
