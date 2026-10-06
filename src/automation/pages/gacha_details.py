"""概率详情页

坐标格式统一为 (x, y, w, h)：x/y 为左上角，w 向右、h 向下。
"""

from src.config import config
from src.automation.button import Button

_ROOT = config.resource_root
_THRESHOLD = config.get("automation.image_recognition.template_threshold", 0.8)


# 页面识别
CHECK_GACHA_DETAILS = Button(
    area=(752, 65, 250, 61),
    button=(752, 65, 250, 61),
    file=str(_ROOT / "assets" / "templates" / "gacha" / "details" / "record.png"),
    similarity=_THRESHOLD,
    name="CHECK_DETAILS",
)

# 抽卡记录
BTN_GACHA_RECORD = Button(
    area=(752, 65, 250, 61),
    button=(752, 65, 250, 61),
    file=str(_ROOT / "assets" / "templates" / "gacha" / "details" / "record.png"),
    similarity=_THRESHOLD,
    name="RECORD",
)

# 返回上一级
BTN_BACK = Button(
    area=(522, 638, 247, 56),
    button=(522, 638, 247, 56),
    file=str(_ROOT / "assets" / "templates" / "gacha" / "details" / "back.png"),
    similarity=_THRESHOLD,
    name="BACK",
)
