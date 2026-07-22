"""概率详情页"""

from src.config import config
from src.automation.button import Button

_ROOT = config.resource_root
_THRESHOLD = config.get("automation.image_recognition.template_threshold", 0.8)


# 页面识别
CHECK_GACHA_DETAILS = Button(
    area=(752, 65, 1002, 126),
    button=(752, 65, 1002, 126),
    file=str(_ROOT / "assets" / "templates" / "gacha" / "details" / "record.png"),
    similarity=_THRESHOLD,
    name="CHECK_DETAILS",
)

# 抽卡记录
BTN_GACHA_RECORD = Button(
    area=(752, 65, 1002, 126),
    button=(752, 65, 1002, 126),
    file=str(_ROOT / "assets" / "templates" / "gacha" / "details" / "record.png"),
    similarity=_THRESHOLD,
    name="RECORD",
)

# 返回上一级
BTN_BACK = Button(
    area=(522, 638, 769, 694),
    button=(522, 638, 769, 694),
    file=str(_ROOT / "assets" / "templates" / "gacha" / "details" / "back.png"),
    similarity=_THRESHOLD,
    name="BACK",
)