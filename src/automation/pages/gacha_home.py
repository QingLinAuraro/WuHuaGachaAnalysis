"""招集主页按钮

坐标格式统一为 (x, y, w, h)：x/y 为左上角，w 向右、h 向下。
"""

from src.config import config
from src.automation.button import Button

_ROOT = config.resource_root
_THRESHOLD = config.get("automation.image_recognition.template_threshold", 0.8)


# 页面识别
CHECK_GACHA_HOME = Button(
    area=(945, 77, 149, 51),
    button=(945, 77, 149, 51),
    file=str(_ROOT / "assets" / "templates" / "gacha" / "details.png"),
    similarity=_THRESHOLD,
    name="CHECK_GACHA_HOME",
)

# 招集页 → 召集记录
BTN_DETAILS = Button(
    area=(945, 77, 149, 51),
    button=(945, 77, 149, 51),
    file=str(_ROOT / "assets" / "templates" / "gacha" / "details.png"),
    similarity=_THRESHOLD,
    name="DETAILS",
)

# 返回主界面
BTN_BACK1 = Button(
    area=(5, 4, 199, 56),
    button=(5, 4, 199, 56),
    file=str(_ROOT / "assets" / "templates" / "gacha" / "back1.png"),
    similarity=_THRESHOLD,
    name="BACK1_TO_MAIN",
)
