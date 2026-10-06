"""召集记录页按钮

坐标格式统一为 (x, y, w, h)：x/y 为左上角，w 向右、h 向下。
"""

from src.config import config
from src.automation.button import Button

_ROOT = config.resource_root
_THRESHOLD = config.get("automation.image_recognition.template_threshold", 0.8)


# 页面识别
# 底部翻页栏横向居中、宽度随记录页数变化，上一页按钮会水平漂移
# （实测中心 x：>10页 466 / 5页 564 / 2页 637 / 1页 662，y 恒为 585~586）。
# 识别区域需覆盖整个漂移范围，否则页数少的布局会被判成"不在召集记录页"。
CHECK_GACHA_RECORD = Button(
    area=(395, 553, 695, 67),
    button=(395, 553, 695, 67),
    file=str(_ROOT / "assets" / "templates" / "gacha" / "details" / "record" / "page_up.png"),
    similarity=_THRESHOLD,
    name="CHECK_RECORD",
)

# 上一页
BTN_PAGE_UP = Button(
    area=(395, 553, 335, 67),
    button=(413, 561, 106, 50),
    file=str(_ROOT / "assets" / "templates" / "gacha" / "details" / "record" / "page_up.png"),
    similarity=_THRESHOLD,
    name="PAGE_UP",
)

# 下一页
BTN_PAGE_DOWN = Button(
    area=(750, 553, 340, 67),
    button=(962, 564, 108, 43),
    file=str(_ROOT / "assets" / "templates" / "gacha" / "details" / "record" / "page_down.png"),
    similarity=_THRESHOLD,
    name="PAGE_DOWN",
)

# 选择卡池
BTN_SELECT = Button(
    area=(1182, 131, 49, 45),
    button=(1182, 131, 49, 45),
    file=str(_ROOT / "assets" / "templates" / "gacha" / "details" / "record" / "select.png"),
    similarity=_THRESHOLD,
    name="SELECT",
)

# 切换卡池
BTN_CHANGE_POOLS = Button(
    area=(1051, 175, 177, 47),
    button=(1051, 175, 177, 47),
    file=str(_ROOT / "assets" / "templates" / "gacha" / "details" / "record" / "pool.png"),
    similarity=_THRESHOLD,
    name="CHANGE_POOLS",
)

# 返回
BTN_BACK = Button(
    area=(522, 638, 247, 56),
    button=(522, 638, 247, 56),
    file=str(_ROOT / "assets" / "templates" / "gacha" / "details" / "record" / "back.png"),
    similarity=_THRESHOLD,
    name="BACK",
)
