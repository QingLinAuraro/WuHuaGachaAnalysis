"""招集主页按钮"""

from pathlib import Path
from src.automation.button import Button

_ROOT = Path(__file__).resolve().parent.parent.parent.parent


# 页面识别
CHECK_GACHA_HOME = Button(
    area=(939, 71, 1094, 129),
    button=(939, 71, 1094, 129),
    file=str(_ROOT / "assets" / "templates" / "gacha" / "details.png"),
    name="CHECK_GACHA_HOME",
)

# 招集页 → 召集记录
BTN_DETAILS = Button(
    area=(939, 71, 1094, 129),
    button=(939, 71, 1094, 129),
    file=str(_ROOT / "assets" / "templates" / "gacha" / "details.png"),
    name="DETAILS",
)

# 返回主界面
BTN_BACK1 = Button(
    area=(5, 4, 204, 60),
    button=(5, 4, 204, 60),
    file=str(_ROOT / "assets" / "templates" / "gacha" / "back1.png"),
    name="BACK1_TO_MAIN",
)
