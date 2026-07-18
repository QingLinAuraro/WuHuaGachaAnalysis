"""概率详情页"""

from pathlib import Path
from src.automation.button import Button

_ROOT = Path(__file__).resolve().parent.parent.parent.parent


# 页面识别
CHECK_GACHA_DETAILS = Button(
    area=(752, 65, 1002, 126),
    button=(752, 65, 1002, 126),
    file=str(_ROOT / "assets" / "templates" / "gacha" / "details" / "record.png"),
    name="CHECK_DETAILS",
)

# 抽卡记录
BTN_GACHA_RECORD = Button(
    area=(752, 65, 1002, 126),
    button=(752, 65, 1002, 126),
    file=str(_ROOT / "assets" / "templates" / "gacha" / "details" / "record.png"),
    name="RECORD",
)

# 返回上一级
BTN_BACK = Button(
    area=(522, 638, 769, 694),
    button=(522, 638, 769, 694),
    file=str(_ROOT / "assets" / "templates" / "gacha" / "details" / "back.png"),
    name="BACK",
)