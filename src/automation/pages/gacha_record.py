"""召集记录页按钮"""

from pathlib import Path
from src.automation.button import Button

_ROOT = Path(__file__).resolve().parent.parent.parent.parent


# 页面识别
CHECK_GACHA_RECORD = Button(
    area=(413, 561, 519, 611),
    button=(413, 561, 519, 611),
    file=str(_ROOT / "assets" / "templates" / "gacha" / "details" / "record" / "page_up.png"),
    name="CHECK_RECORD",
)

# 末尾页
BTN_FINAL_PAGE = Button(
    area=(913, 565, 961, 609),
    button=(913, 565, 961, 609),
    file=str(_ROOT / "assets" / "templates" / "gacha" / "details" / "record" / "final_page.png"),
    name="FINAL_PAGE",
)

# 上一页
BTN_PAGE_UP = Button(
    area=(413, 561, 519, 611),
    button=(413, 561, 519, 611),
    file=str(_ROOT / "assets" / "templates" / "gacha" / "details" / "record" / "page_up.png"),
    name="PAGE_UP",
)

# 下一页
BTN_PAGE_DOWN = Button(
    area=(962, 564, 1070, 607),
    button=(962, 564, 1070, 607),
    file=str(_ROOT / "assets" / "templates" / "gacha" / "details" / "record" / "page_down.png"),
    name="PAGE_DOWN",
)

# 选择卡池
BTN_SELECT = Button(
    area=(1182, 131, 1231, 176),
    button=(1182, 131, 1231, 176),
    file=str(_ROOT / "assets" / "templates" / "gacha" / "details" / "record" / "select.png"),
    name="SELECT",
)

# 切换卡池
BTN_CHANGE_POOLS = Button(
    area=(1051, 175, 1228, 222),
    button=(1051, 175, 1228, 222),
    file=str(_ROOT / "assets" / "templates" / "gacha" / "details" / "record" / "pool.png"),
    name="CHANGE_POOLS",
)

# 返回
BTN_BACK = Button(
    area=(522, 638, 769, 694),
    button=(522, 638, 769, 694),
    file=str(_ROOT / "assets" / "templates" / "gacha" / "details" / "record" / "back.png"),
    name="BACK",
)