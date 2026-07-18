"""主界面按钮"""

from pathlib import Path
from src.automation.button import Button

_ROOT = Path(__file__).resolve().parent.parent.parent.parent


# 页面识别
CHECK_MAIN = Button(
    area=(902, 344, 1073, 547),
    button=(902, 344, 1073, 547),
    file=str(_ROOT / "assets" / "templates" / "main" / "gacha.png"),
    name="CHECK_MAIN",
)

# 主界面 → 招集页
BTN_GACHA = Button(
    area=(902, 344, 1073, 547),
    button=(902, 344, 1073, 547),
    file=str(_ROOT / "assets" / "templates" / "main" / "gacha.png"),
    name="GACHA",
)
