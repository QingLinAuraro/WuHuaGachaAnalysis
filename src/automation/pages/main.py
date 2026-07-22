"""主界面按钮"""

from src.config import config
from src.automation.button import Button

_ROOT = config.resource_root
_THRESHOLD = config.get("automation.image_recognition.template_threshold", 0.8)


# 页面识别
CHECK_MAIN = Button(
    area=(902, 344, 1073, 547),
    button=(902, 344, 1073, 547),
    file=str(_ROOT / "assets" / "templates" / "main" / "gacha.png"),
    similarity=_THRESHOLD,
    name="CHECK_MAIN",
)

# 主界面 → 招集页
BTN_GACHA = Button(
    area=(902, 344, 1073, 547),
    button=(902, 344, 1073, 547),
    file=str(_ROOT / "assets" / "templates" / "main" / "gacha.png"),
    similarity=_THRESHOLD,
    name="GACHA",
)
