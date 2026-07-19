"""自动化引擎 - 基于图像识别的UI导航与数据采集"""

from src.automation.button import Button, ButtonGrid
from src.automation.errors import (
    AutomationError, GameStuckError, PageUnknownError, NavigationError,
)
from src.automation.page_graph import (
    Page, PageGraph, build_wuhua_pages, get_page, get_page_names,
)
from src.automation.page_detector import (
    PageDetector, GamePage, color_match_rarity,
)
from src.automation.ui_navigator import UINavigator, NavState
from src.automation.gacha_scanner import GachaScanner, create_scanner

__all__ = [
    "Button", "ButtonGrid",
    "AutomationError", "GameStuckError", "PageUnknownError", "NavigationError",
    "Page", "PageGraph", "build_wuhua_pages", "get_page", "get_page_names",
    "PageDetector", "GamePage", "color_match_rarity",
    "UINavigator", "NavState",
    "GachaScanner", "create_scanner",
]
