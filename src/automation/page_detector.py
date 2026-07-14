"""
页面识别模块
使用 OpenCV 模板匹配识别当前游戏页面
"""

import cv2
import numpy as np
from pathlib import Path
from enum import Enum, auto
from typing import Optional

from loguru import logger

from src.config import config


class GamePage(Enum):
    """游戏页面枚举"""
    UNKNOWN = auto()          # 未知页面
    MAIN = auto()             # 主界面（首页）
    GACHA_ENTRANCE = auto()   # 招集入口（主界面中）
    GACHA_HOME = auto()       # 招集主页（选择卡池）
    GACHA_RECORD = auto()     # 召集记录列表
    GACHA_DETAIL = auto()     # 记录详情
    OTHER = auto()            # 其他页面（需要处理）


class PageDetector:
    """
    页面识别器
    使用模板匹配来识别当前游戏处于哪个页面
    """

    def __init__(self, templates_dir: Optional[str] = None) -> None:
        self._templates_dir = Path(
            templates_dir or config.project_root / "assets" / "templates"
        )
        self._templates: dict[GamePage, list[np.ndarray]] = {}
        self._threshold: float = 0.8  # 匹配阈值
        self._load_templates()

    def _load_templates(self) -> None:
        """加载所有模板图片"""
        if not self._templates_dir.exists():
            logger.warning("模板目录不存在: {}，请放置模板图片", self._templates_dir)
            logger.warning("目录结构应为:")
            logger.warning("  templates/main/*.png     - 主界面特征图")
            logger.warning("  templates/gacha_home/*.png - 招集主页特征图")
            logger.warning("  templates/gacha_record/*.png - 召集记录特征图")
            return

        page_map = {
            "main": GamePage.MAIN,
            "gacha_entrance": GamePage.GACHA_ENTRANCE,
            "gacha_home": GamePage.GACHA_HOME,
            "gacha_record": GamePage.GACHA_RECORD,
            "gacha_detail": GamePage.GACHA_DETAIL,
        }

        for dir_name, page in page_map.items():
            dir_path = self._templates_dir / dir_name
            if dir_path.exists():
                templates = []
                for img_file in dir_path.glob("*.png"):
                    img = cv2.imread(str(img_file))
                    if img is not None:
                        templates.append(img)
                        logger.debug("加载模板: {} ({})", img_file.name, page.name)
                if templates:
                    self._templates[page] = templates

        logger.info(
            "模板加载完成: {} 个页面, {} 个模板",
            len(self._templates),
            sum(len(v) for v in self._templates.values()),
        )

    def detect(self, screenshot: np.ndarray) -> GamePage:
        """
        检测当前截图对应的游戏页面

        Args:
            screenshot: BGR 格式的截图 numpy 数组

        Returns:
            识别到的页面类型
        """
        if not self._templates:
            return GamePage.UNKNOWN

        best_page = GamePage.UNKNOWN
        best_score = 0.0

        for page, templates in self._templates.items():
            for template in templates:
                score = self._match_template(screenshot, template)
                if score > best_score:
                    best_score = score
                    best_page = page

        if best_score >= self._threshold:
            logger.debug("页面识别: {} (置信度: {:.2f})", best_page.name, best_score)
            return best_page

        return GamePage.UNKNOWN

    def is_page(self, screenshot: np.ndarray, page: GamePage) -> bool:
        """检查当前截图是否为指定页面"""
        return self.detect(screenshot) == page

    def _match_template(
        self, screenshot: np.ndarray, template: np.ndarray
    ) -> float:
        """模板匹配，返回最高置信度"""
        # 如果模板比截图大，缩放模板
        if (template.shape[0] > screenshot.shape[0] or
                template.shape[1] > screenshot.shape[1]):
            scale = min(
                screenshot.shape[0] / template.shape[0],
                screenshot.shape[1] / template.shape[1],
            )
            new_w = int(template.shape[1] * scale)
            new_h = int(template.shape[0] * scale)
            template = cv2.resize(template, (new_w, new_h))

        result = cv2.matchTemplate(screenshot, template, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, _ = cv2.minMaxLoc(result)
        return float(max_val)

    def find_button(
        self, screenshot: np.ndarray, template: np.ndarray
    ) -> Optional[tuple[int, int]]:
        """
        查找按钮在截图中的位置，返回中心坐标

        Returns:
            (center_x, center_y) 或 None
        """
        score = self._match_template(screenshot, template)
        if score < self._threshold:
            return None

        result = cv2.matchTemplate(screenshot, template, cv2.TM_CCOEFF_NORMED)
        _, _, _, max_loc = cv2.minMaxLoc(result)
        center_x = max_loc[0] + template.shape[1] // 2
        center_y = max_loc[1] + template.shape[0] // 2
        return center_x, center_y

    def has_template(self, page: GamePage) -> bool:
        """检查是否有某页面的模板"""
        return page in self._templates and len(self._templates[page]) > 0


def color_match_rarity(region: np.ndarray) -> Optional[int]:
    """
    通过颜色检测判断稀有度
    物华弥新：红=特出(5), 黄=优异(4), 蓝=精良(3)

    Args:
        region: 抽取记录条目区域的截图（BGR格式）

    Returns:
        稀有度值 (5/4/3) 或 None
    """
    # 转为 HSV 便于颜色检测
    hsv = cv2.cvtColor(region, cv2.COLOR_BGR2HSV)

    # 红色范围（两个区间，因为HSV红色在两端）
    red_lower1 = np.array([0, 100, 100])
    red_upper1 = np.array([10, 255, 255])
    red_lower2 = np.array([160, 100, 100])
    red_upper2 = np.array([180, 255, 255])

    # 黄色范围
    yellow_lower = np.array([20, 100, 100])
    yellow_upper = np.array([35, 255, 255])

    # 蓝色范围
    blue_lower = np.array([100, 100, 100])
    blue_upper = np.array([130, 255, 255])

    red_mask1 = cv2.inRange(hsv, red_lower1, red_upper1)
    red_mask2 = cv2.inRange(hsv, red_lower2, red_upper2)
    red_ratio = (cv2.countNonZero(red_mask1) + cv2.countNonZero(red_mask2)) / region.size

    yellow_mask = cv2.inRange(hsv, yellow_lower, yellow_upper)
    yellow_ratio = cv2.countNonZero(yellow_mask) / region.size

    blue_mask = cv2.inRange(hsv, blue_lower, blue_upper)
    blue_ratio = cv2.countNonZero(blue_mask) / region.size

    # 阈值判断
    if red_ratio > 0.05:
        return 5  # 特出
    elif yellow_ratio > 0.05:
        return 4  # 优异
    elif blue_ratio > 0.05:
        return 3  # 精良

    return None
