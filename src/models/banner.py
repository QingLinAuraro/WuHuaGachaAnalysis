"""
卡池信息管理
"""

from .gacha_record import GachaBanner, BannerType


# 物华弥新已知卡池列表
KNOWN_BANNERS: list[GachaBanner] = [
    GachaBanner(
        name="新人招募",
        banner_type=BannerType.NEWBIE,
        pity_count=30,  # 新人30抽必出特出
    ),
    GachaBanner(
        name="常规招募",
        banner_type=BannerType.STANDARD,
        pity_count=70,
    ),
    GachaBanner(
        name="器者征集",
        banner_type=BannerType.COLLECTION,
        pity_count=70,
    ),
]


def get_banner_by_name(name: str) -> GachaBanner | None:
    """根据卡池名称查找已知卡池"""
    for banner in KNOWN_BANNERS:
        if banner.name == name:
            return banner
    return None
