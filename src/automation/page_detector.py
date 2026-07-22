"""
页面识别模块
基于 Button 多层级检测（颜色 → 模板匹配 → 全图搜索）的页面识别

改造自原 page_detector.py，现在使用 Button 统一识别对象，
支持颜色检测（最快）、模板匹配（中等）、多模板投票（精确）。
"""

import cv2
import numpy as np
from pathlib import Path
from enum import Enum, auto
from typing import Optional

from loguru import logger

from src.automation.button import Button
from src.config import config


class GamePage(Enum):
    """游戏页面枚举（保留兼容）"""
    UNKNOWN = auto()          # 未知页面
    MAIN = auto()             # 主界面（首页）
    GACHA_ENTRANCE = auto()   # 招集入口（主界面中）
    GACHA_HOME = auto()       # 招集主页（选择卡池）
    GACHA_RECORD = auto()     # 召集记录列表
    GACHA_DETAIL = auto()     # 记录详情
    OTHER = auto()            # 其他页面（需要处理）


class PageDetector:
    """页面识别器 — 使用 Button 多层级检测

    检测策略（由快到慢）：
      1. 颜色检测   — 对比 ROI 区域平均颜色（毫秒级）
      2. 模板匹配   — cv2.matchTemplate 在 ROI 区域内搜索（十毫秒级）
      3. 多模板投票 — 多个 check_button 联合投票（百毫秒级）

    兼容旧 API：保留 detect()、is_page()、has_template()、find_button() 等方法。
    """

    def __init__(self, templates_dir: Optional[str] = None) -> None:
        self._templates_dir = Path(
            templates_dir or config.resource_root / "assets" / "templates"
        )
        # 页面 check_buttons: page_name → list[Button]
        self._page_buttons: dict[str, list[Button]] = {}
        self._threshold: float = config.get(
            "automation.image_recognition.template_threshold", 0.8
        )
        self._color_tolerance: int = config.get(
            "automation.image_recognition.color_tolerance", 10
        )

        # 自动加载模板
        self._load_templates()

        # 兼容旧代码的模板缓存
        self._legacy_templates: dict[GamePage, list[np.ndarray]] = {}
        self._load_legacy_templates()

    # ── 模板加载 ──────────────────────────────────────

    def _load_templates(self) -> None:
        """从 assets/templates/ 自动加载页面 check_button 和导航按钮

        目录结构（ALAS 风格，支持嵌套）：
          assets/templates/
            main/
              gacha.png           # 页面识别 + 导航
            gacha/
              details.png / back1.png
              details/
                record.png / back.png
                record/
                  page_up.png / page_down.png / final_page.png / select.png / pool.png / back.png
        """
        if not self._templates_dir.exists():
            logger.warning("模板目录不存在: {}", self._templates_dir)
            logger.warning("请放置模板图片后重启程序")
            logger.warning("目录结构应为: assets/templates/{page_name}/*.png")
            return

        # 递归扫描所有包含 .png 文件的子目录
        scanned_dirs = set()
        for img_file in self._templates_dir.rglob("*.png"):
            page_dir = img_file.parent
            if page_dir in scanned_dirs:
                continue
            scanned_dirs.add(page_dir)

            # 用相对于 templates_dir 的路径作为 page_name（如 "gacha/details/record"）
            page_name = str(page_dir.relative_to(self._templates_dir)).replace("\\", "/")
            if page_name == "shared" or "shared" in page_name.split("/"):
                continue

            buttons: list[Button] = []
            for png in page_dir.glob("*.png"):
                btn = Button(
                    area=(0, 0, 1280, 720),  # 默认全图搜索
                    file=str(png),
                    similarity=self._threshold,
                    name=f"check_{page_name}_{png.stem}",
                )
                buttons.append(btn)

            if buttons:
                self._page_buttons[page_name] = buttons
                logger.debug(
                    "加载页面 '{}': {} 个检测按钮",
                    page_name, len(buttons),
                )

        logger.info(
            "模板加载完成: {} 个页面, {} 个检测按钮",
            len(self._page_buttons),
            sum(len(v) for v in self._page_buttons.values()),
        )

    def _load_legacy_templates(self) -> None:
        """兼容旧代码：加载原始模板图片到缓存

        （逐步迁移后移除）
        """
        page_map = {
            "main": GamePage.MAIN,
            "gacha": GamePage.GACHA_HOME,
        }

        for dir_name, page in page_map.items():
            dir_path = self._templates_dir / dir_name
            if dir_path.exists():
                templates = []
                for img_file in dir_path.glob("*.png"):
                    img_array = np.fromfile(str(img_file), dtype=np.uint8)
                    img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
                    if img is not None:
                        templates.append(img)
                if templates:
                    self._legacy_templates[page] = templates

        if self._legacy_templates:
            logger.info(
                "旧版模板缓存: {} 个页面, {} 个模板",
                len(self._legacy_templates),
                sum(len(v) for v in self._legacy_templates.values()),
            )

    # ── 核心检测（基于 Button） ────────────────────────

    def detect(self, screenshot: np.ndarray) -> GamePage:
        """检测当前截图对应的游戏页面

        检测策略：
          1. 先尝试 Button 对象检测（颜色 + 模板匹配）
          2. 回退到旧版全图模板匹配

        Args:
            screenshot: BGR 格式截图

        Returns:
            识别到的页面类型
        """
        # 1. 优先使用 Button 对象检测
        if self._page_buttons:
            result = self._detect_by_buttons(screenshot)
            if result is not None:
                return result

        # 2. 回退到旧版模板匹配
        if self._legacy_templates:
            return self._detect_by_legacy_templates(screenshot)

        return GamePage.UNKNOWN

    def _detect_by_buttons(self, screenshot: np.ndarray) -> Optional[GamePage]:
        """使用 Button 对象检测页面

        返回第一个匹配的页面，或 None。
        """
        best_page = GamePage.UNKNOWN
        best_score = 0.0

        for page_name, buttons in self._page_buttons.items():
            for btn in buttons:
                if btn.file:
                    # 模板匹配
                    match_result = btn.match(screenshot)
                    if match_result and match_result[4] > best_score:
                        best_score = match_result[4]
                        best_page = self._page_name_to_enum(page_name)

        if best_score >= self._threshold and best_page != GamePage.UNKNOWN:
            logger.debug(
                "Button 识别: {} (置信度: {:.2f})",
                best_page.name, best_score,
            )
            return best_page

        return None

    def _detect_by_legacy_templates(self, screenshot: np.ndarray) -> GamePage:
        """旧版全图模板匹配（兼容）"""
        best_page = GamePage.UNKNOWN
        best_score = 0.0

        for page, templates in self._legacy_templates.items():
            for template in templates:
                score = self._match_template(screenshot, template)
                if score > best_score:
                    best_score = score
                    best_page = page

        if best_score >= self._threshold:
            logger.debug(
                "旧版识别: {} (置信度: {:.2f})",
                best_page.name, best_score,
            )
            return best_page

        return GamePage.UNKNOWN

    def is_page(self, screenshot: np.ndarray, page: GamePage) -> bool:
        """检查当前截图是否为指定页面"""
        return self.detect(screenshot) == page

    # ── 页面名称映射 ──────────────────────────────────

    @staticmethod
    def _page_name_to_enum(name: str) -> GamePage:
        """将页面目录名（相对路径）映射到 GamePage 枚举"""
        # 支持递归目录路径，如 "gacha/details/record" → GACHA_RECORD
        mapping = {
            "main": GamePage.MAIN,
            "gacha": GamePage.GACHA_HOME,
            "gacha/details": GamePage.GACHA_DETAIL,
            "gacha/details/record": GamePage.GACHA_RECORD,
        }
        # 也兼容简短名称（旧版或别名）
        short_mapping = {
            "gacha_entrance": GamePage.GACHA_ENTRANCE,
            "gacha_record": GamePage.GACHA_RECORD,
            "gacha_detail": GamePage.GACHA_DETAIL,
        }
        if name in mapping:
            return mapping[name]
        return short_mapping.get(name, GamePage.UNKNOWN)

    @staticmethod
    def page_enum_to_name(page: GamePage) -> str:
        """GamePage → 目录名"""
        mapping = {
            GamePage.MAIN: "main",
            GamePage.GACHA_ENTRANCE: "gacha_entrance",
            GamePage.GACHA_HOME: "assemble",
            GamePage.GACHA_RECORD: "gacha_record",
            GamePage.GACHA_DETAIL: "gacha_detail",
        }
        return mapping.get(page, "unknown")

    # ── 模板匹配（兼容旧API） ─────────────────────────

    def _match_template(
        self, screenshot: np.ndarray, template: np.ndarray
    ) -> float:
        """模板匹配，返回最高置信度"""
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
        """查找按钮在截图中的位置，返回中心坐标 (兼容旧API)"""
        score = self._match_template(screenshot, template)
        if score < self._threshold:
            return None

        result = cv2.matchTemplate(screenshot, template, cv2.TM_CCOEFF_NORMED)
        _, _, _, max_loc = cv2.minMaxLoc(result)
        center_x = max_loc[0] + template.shape[1] // 2
        center_y = max_loc[1] + template.shape[0] // 2
        return center_x, center_y

    def has_template(self, page: GamePage) -> bool:
        """检查是否有某页面的模板 (兼容旧API)"""
        # 先检查新 Button 系统
        page_name = self.page_enum_to_name(page)
        if page_name in self._page_buttons:
            return len(self._page_buttons[page_name]) > 0
        # 再检查旧版模板
        return page in self._legacy_templates and len(self._legacy_templates[page]) > 0

    # ── Button 相关的新 API ───────────────────────────

    def get_page_button(self, page: GamePage) -> Optional[Button]:
        """获取指定页面的 check_button"""
        page_name = self.page_enum_to_name(page)
        buttons = self._page_buttons.get(page_name, [])
        return buttons[0] if buttons else None

    def get_button_by_name(self, page_name: str, file_stem: str) -> Optional[Button]:
        """按页面名和文件名查找 Button"""
        buttons = self._page_buttons.get(page_name, [])
        for btn in buttons:
            if btn.file and Path(btn.file).stem == file_stem:
                return btn
        return None

    def find_click_target(
        self, screenshot: np.ndarray, button: Button
    ) -> Optional[tuple[int, int]]:
        """找到按钮的精确点击位置

        优先使用模板匹配结果，否则使用按钮区域中心。
        """
        if button.file:
            match_result = button.match(screenshot)
            if match_result:
                x, y, w, h, _ = match_result
                return (x + w // 2, y + h // 2)
        return button.coord()


# ═══════════════════════════════════════════════════════════
# 颜色匹配稀有度（保留，供 GachaScanner 使用）
# ═══════════════════════════════════════════════════════════

def color_match_rarity(region: np.ndarray) -> Optional[int]:
    """通过颜色检测判断稀有度

    物华弥新：红=特出(5), 黄=优异(4), 蓝=精良(3)

    Args:
        region: 抽取记录条目区域的截图（BGR格式）

    Returns:
        稀有度值 (5/4/3) 或 None
    """
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

    if red_ratio > 0.05:
        return 5
    elif yellow_ratio > 0.05:
        return 4
    elif blue_ratio > 0.05:
        return 3

    return None
