"""页面按钮 — 按界面分文件管理

每个文件定义一个页面的识别按钮和跳转按钮。
截图存到 assets/templates/{页面名}/ 下自动生效。

新增页面只需：
  1. 复制此目录下任意文件 → 改名为新页面名.py
  2. 修改 Button 坐标
  3. 在 page_graph.py 里加 Page + link
"""

from src.automation.pages.main import CHECK_MAIN, BTN_GACHA
from src.automation.pages.gacha_home import CHECK_GACHA_HOME, BTN_DETAILS
from src.automation.pages.gacha_record import CHECK_GACHA_RECORD, BTN_PAGE_DOWN

__all__ = [
    "CHECK_MAIN", "BTN_GACHA",
    "CHECK_GACHA_HOME", "BTN_DETAILS",
    "CHECK_GACHA_RECORD", "BTN_PAGE_DOWN",
]
