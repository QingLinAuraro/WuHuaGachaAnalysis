"""召集记录页 —— 渠道（卡池）切换面板

记录页右上角的渠道选择器展开后，会列出当前账号可查看的全部渠道。
每个渠道对应一份独立的抽卡记录，逐一切换即可把全部记录扫完。

坐标格式统一为 (x, y, w, h)：x/y 为左上角，w 向右、h 向下。

⚠️ 条目模板（xianshi/xianding/...）截的是条目的【未选中态】。
   面板展开时，当前渠道处于选中态（浅色高亮底 + 绿勾），与模板差异较大，
   此时用它自己的模板去匹配会失配（实测「限时渠道」选中时，xianshi.png
   反而在「限定渠道」那一行拿到 0.891 分）。因为待切换的目标渠道必然是
   **未选中态**，本模块只用于「按目标类型匹配并点击」，不会踩到这个坑。

   由此推出一条有用规律：
     · 面板里**能匹配到**模板的条目 = 未选中态 = 可切换的目标
     · 面板里**匹配不到**模板的条目 = 选中态 = 当前正在看的渠道
   所以"当前是哪个渠道"可以用排除法算出来（见 channel_by_elimination），
   但主力仍是 OCR（记录内容里带类型，见 GachaScanner._detect_channel），
   排除法只作为 OCR 失败时的兜底。
"""

from typing import Iterable

import numpy as np

from src.config import config
from src.automation.button import Button
from src.models.gacha_record import BannerType

_ROOT = config.resource_root
_THRESHOLD = config.get("automation.image_recognition.template_threshold", 0.8)
_TEMPLATE_DIR = _ROOT / "assets" / "templates" / "gacha" / "details" / "record"

# 面板内相邻条目的间距约 45px。两个匹配结果中心 y 相差不超过这个值，
# 就认为它们落在同一条目上（用于剔除"张冠李戴"的重复命中）。
_ROW_MERGE_TOLERANCE = 20

# 展开后的渠道列表区域。
# 条目数量与位置会随账号拥有的渠道不同而变化，所以这里给的是一个
# "全部展开时"的整块区域，再在其中用模板匹配定位具体条目。
CHANNEL_PANEL_AREA = (1048, 175, 185, 235)

# 面板内条目自上而下的顺序（与界面一致）
CHANNEL_ORDER = (
    BannerType.LIMITED_TIME,   # 限时渠道
    BannerType.LIMITED,        # 限定渠道
    BannerType.SUMMON,         # 招集渠道
    BannerType.COLLECT,        # 征集渠道
    BannerType.SEASON,         # 赛季渠道
)

# 渠道类型 → 条目模板文件名
CHANNEL_TEMPLATE_FILES = {
    BannerType.LIMITED_TIME: "xianshi.png",
    BannerType.LIMITED: "xianding.png",
    BannerType.SUMMON: "zhaoji.png",
    BannerType.COLLECT: "zhengji.png",
    BannerType.SEASON: "saiji.png",
}

# 渠道类型 → 可在面板中定位并点击的 Button
# area / button 都用面板整块区域，match() 会在其中搜索条目模板
CHANNEL_BUTTONS = {
    banner_type: Button(
        area=CHANNEL_PANEL_AREA,
        button=CHANNEL_PANEL_AREA,
        file=str(_TEMPLATE_DIR / filename),
        similarity=_THRESHOLD,
        name=f"CHANNEL_{banner_type}",
    )
    for banner_type, filename in CHANNEL_TEMPLATE_FILES.items()
}


def get_channel_button(banner_type: str) -> Button | None:
    """取某个渠道类型对应的面板条目按钮；未定义该类型时返回 None"""
    return CHANNEL_BUTTONS.get(banner_type)


def find_visible_channels(image: np.ndarray) -> list[str]:
    """列出【已展开】面板里"未选中态"的渠道条目，按界面自上而下排序

    返回值里的每一项都能在面板上定位到，可直接点击切换。

    ⚠️ 返回结果**不含当前选中的那个渠道**：它是浅色高亮底 + 绿勾，与未选中态
       模板差异大，匹配不上。所以面板上的实际条目总数 = len(本函数结果) + 1
       （除非当前渠道碰巧也匹配上了，那时 +1 会重复，调用方用集合去重即可）。
       换渠道时不用管这一个 —— 待切换的目标必然是未选中态。

    去重说明：同一个"张冠李戴"命中会让两个模板指向同一条目
    （实测「限时」选中时，xianshi.png 在「限定」那一行得 0.891）。
    这里按得分从高到低逐个收录，中心 y 相近的视为同一条目，只留高分那个，
    否则条目总数会被算多，导致"全部扫完"的判定永远达不到。
    """
    hits: list[tuple[float, int, str]] = []      # (得分, 条目中心 y, 渠道类型)
    for banner_type in CHANNEL_ORDER:
        btn = CHANNEL_BUTTONS.get(banner_type)
        if btn is None:
            continue
        match = btn.match(image)
        if match is None:
            continue
        _x, y, _w, h, score = match
        hits.append((score, y + h // 2, banner_type))

    hits.sort(key=lambda item: -item[0])         # 得分高的先收录
    kept: list[tuple[float, int, str]] = []
    for score, center_y, banner_type in hits:
        if any(abs(center_y - kept_y) <= _ROW_MERGE_TOLERANCE for _, kept_y, _ in kept):
            continue
        kept.append((score, center_y, banner_type))

    kept.sort(key=lambda item: item[1])          # 按位置自上而下
    return [banner_type for _, _, banner_type in kept]


def channel_by_elimination(visible: Iterable[str]) -> str:
    """用排除法推断"当前选中的是哪个渠道"

    依据：面板里匹配不到模板的那个条目就是选中态（见模块 docstring）。
    但只有在 CHANNEL_ORDER 里**恰好剩一个**时才敢下结论 —— 剩下的多于一个，
    说明本账号根本没开通那么多渠道类型（面板里本来就没有），无法判断。

    Args:
        visible: find_visible_channels() 的结果

    Returns:
        BannerType 常量；判断不出来时返回 BannerType.UNKNOWN
    """
    visible = set(visible)
    remaining = [t for t in CHANNEL_ORDER if t not in visible]
    return remaining[0] if len(remaining) == 1 else BannerType.UNKNOWN
