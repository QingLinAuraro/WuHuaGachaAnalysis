"""
UI 导航器（重写版）
基于 PageGraph 页面图的图像识别导航系统

核心改变：
  - 旧版：固定坐标 + 盲操作 → 新版：图像识别 + 页面图导航
  - 旧版：sleep(2) 等待 → 新版：循环截图验证 + 超时保护
  - 旧版：无错误恢复 → 新版：弹窗处理 + 卡住检测 + 重试

保留对外 API 兼容：
  - go_to_gacha_records()   → 内部使用 PageGraph.ensure()
  - go_back()               → send keyevent 4
  - state / set_state_callback() → 状态变化通知
  - set_coords() / reload_coords() → 坐标 fallback（保留兼容）
"""

import json
import time
from enum import Enum, auto
from pathlib import Path
from typing import Optional, Callable

import numpy as np
from loguru import logger

from src.emulator.adb_client import ADBClient
from src.emulator.screenshot import Screenshot
from src.automation.page_detector import PageDetector, GamePage
from src.automation.page_graph import (
    Page,
    PageGraph,
    build_wuhua_pages,
    get_page,
)
from src.automation.button import Button
from src.automation.errors import (
    NavigationError,
    GameStuckError,
)

# YAML 为可选依赖
try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False


class NavState(Enum):
    """导航状态"""
    IDLE = auto()
    NAVIGATING_TO_GACHA = auto()     # 前往招集页面
    NAVIGATING_TO_RECORDS = auto()   # 前往召集记录
    AT_RECORDS = auto()              # 已在召集记录页
    SCANNING = auto()                # 正在扫描
    COMPLETED = auto()               # 扫描完成
    ERROR = auto()                   # 出错


class UINavigator:
    """UI 导航器 — 基于页面图的图像识别导航

    导航路径：
      主页 ──[GACHA]──→ 招集主页 ──[DETAILS]──→ 概率详情 ──[RECORD]──→ 召集记录
    """

    # 模拟器 1280x720 分辨率下的预设坐标（fallback）
    COORDS_1280x720 = {
        "gacha_button": (1100, 620),
        "record_button": (640, 680),
        "record_list_start": (640, 560),
        "record_list_end": (640, 160),
        "back_button": (60, 40),
        "confirm_button": (640, 400),
        "next_page_button": (1180, 640),
    }

    COORDS_1920x1080 = {
        "gacha_button": (1650, 930),
        "record_button": (960, 1020),
        "record_list_start": (960, 840),
        "record_list_end": (960, 240),
        "back_button": (90, 60),
        "confirm_button": (960, 600),
        "next_page_button": (1770, 960),
    }

    def __init__(
        self,
        adb: ADBClient,
        screenshot: Screenshot,
        detector: PageDetector,
        width: int = 1280,
        height: int = 720,
        coord_config_path: Optional[str] = None,
    ) -> None:
        self._adb = adb
        self._screenshot = screenshot
        self._detector = detector
        self._width = width
        self._height = height
        self._state = NavState.IDLE

        # 坐标 fallback
        if coord_config_path:
            loaded = self._load_coords_from_file(coord_config_path)
            if loaded:
                self._coords = loaded
                logger.info("坐标配置已从文件加载: {}", coord_config_path)
            else:
                self._coords = self._get_coords()
        else:
            self._coords = self._get_coords()

        # 构建页面图
        self._page_graph = PageGraph()
        self._pages = build_wuhua_pages()
        self._page_main, self._page_gacha_home, self._page_gacha_record = self._pages

        # 截图 + 点击回调（供 PageGraph 使用）
        self._screenshot_fn = self._safe_screenshot
        self._click_fn = self._safe_click

        # 回调
        self._on_state_change: Optional[Callable[[NavState], None]] = None

        # 弹窗按钮
        self._popup_close_btn = Button(
            area=(1200, 10, 1270, 60),
            button=(1200, 10, 1270, 60),
            name="POPUP_CLOSE",
        )

    # ── 截图 & 点击回调 ───────────────────────────────

    def _safe_screenshot(self) -> Optional[np.ndarray]:
        """安全截图回调"""
        try:
            return self._screenshot.capture_as_array()
        except Exception as e:
            logger.error("截图失败: {}", e)
            return None

    def _safe_click(self, x: int, y: int) -> bool:
        """安全点击回调"""
        try:
            return self._adb.click(x, y)
        except Exception as e:
            logger.error("点击失败: {}", e)
            return False

    # ── 坐标管理（向后兼容）──────────────────────────

    def _get_coords(self) -> dict:
        """根据分辨率选择内置的坐标映射"""
        if self._width == 1920 and self._height == 1080:
            return dict(self.COORDS_1920x1080)
        return dict(self.COORDS_1280x720)

    def _load_coords_from_file(self, path: str) -> Optional[dict]:
        """从 YAML 或 JSON 文件加载坐标配置"""
        file_path = Path(path)
        if not file_path.exists():
            logger.warning("坐标配置文件不存在: {}", path)
            return None

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                ext = file_path.suffix.lower()
                if ext in (".yaml", ".yml"):
                    if not HAS_YAML:
                        logger.error("需要安装 PyYAML: pip install pyyaml")
                        return None
                    data = yaml.safe_load(f)
                elif ext == ".json":
                    data = json.load(f)
                else:
                    return None

            if "coords" in data:
                raw = data["coords"]
            else:
                raw = {k: v for k, v in data.items()
                       if isinstance(v, dict) and "x" in v and "y" in v}

            if not raw:
                return None

            coords = {}
            for key, val in raw.items():
                if isinstance(val, dict) and "x" in val and "y" in val:
                    coords[key] = (int(val["x"]), int(val["y"]))
                elif isinstance(val, (list, tuple)) and len(val) == 2:
                    coords[key] = (int(val[0]), int(val[1]))

            return coords
        except Exception as e:
            logger.error("加载坐标配置文件失败: {}", e)
            return None

    def _coord(self, key: str) -> tuple[int, int]:
        """获取坐标，已按分辨率缩放"""
        base_w, base_h = 1280, 720
        x, y = self._coords.get(key, (0, 0))
        if self._width != base_w or self._height != base_h:
            x = int(x * self._width / base_w)
            y = int(y * self._height / base_h)
        return x, y

    def set_coords(self, coords: dict) -> None:
        """运行时设置坐标"""
        self._coords.update({
            k: (int(v[0]), int(v[1])) if isinstance(v, (list, tuple)) else v
            for k, v in coords.items()
        })

    def reload_coords(self, path: str) -> bool:
        """重新加载坐标配置文件"""
        loaded = self._load_coords_from_file(path)
        if loaded:
            self._coords = loaded
            return True
        return False

    def get_all_coords(self) -> dict:
        """获取当前所有坐标"""
        return dict(self._coords)

    # ── 状态管理 ──────────────────────────────────────

    @property
    def state(self) -> NavState:
        return self._state

    def set_state_callback(self, callback: Callable[[NavState], None]) -> None:
        self._on_state_change = callback

    def _set_state(self, state: NavState) -> None:
        self._state = state
        logger.info("导航状态: {}", state.name)
        if self._on_state_change:
            self._on_state_change(state)

    # ── 核心导航 ──────────────────────────────────────

    def go_to_gacha_records(self) -> bool:
        """自动导航到召集记录页面

        优先使用图像识别（PageGraph），回退到坐标盲操作。

        Returns:
            是否成功到达召集记录页
        """
        self._set_state(NavState.NAVIGATING_TO_GACHA)

        # 1. 尝试页面图导航（图像识别）
        if self._try_image_navigation():
            self._set_state(NavState.AT_RECORDS)
            return True

        # 2. 回退：坐标盲操作
        logger.warning("图像识别导航失败，回退到坐标点击")
        return self._fallback_coord_navigation()

    def _try_image_navigation(self) -> bool:
        """使用 PageGraph 进行图像识别导航"""
        # 检查是否有可用的模板
        screenshot = self._safe_screenshot()
        if screenshot is None:
            return False

        # 测试是否有任何页面能被识别
        current = self._page_graph.get_current_page(screenshot)
        if current is None:
            logger.warning("当前页面无法识别，无法使用图像导航")
            return False

        logger.info("图像识别: 当前在 '{}'", current.name)

        try:
            self._page_graph.ensure(
                self._page_gacha_record,
                self._screenshot_fn,
                self._click_fn,
            )
            logger.info("图像导航成功: 已到达召集记录页")
            return True
        except (NavigationError, GameStuckError) as e:
            logger.error("图像导航失败: {}", e)
            return False
        except Exception as e:
            logger.error("图像导航异常: {}", e)
            return False

    def _fallback_coord_navigation(self) -> bool:
        """坐标盲操作导航（旧版兼容）"""
        max_retries = 5

        for attempt in range(max_retries):
            img = self._safe_screenshot()
            if img is None:
                time.sleep(1)
                continue

            # 尝试用检测器识别
            current_page = self._detector.detect(img)
            logger.info("坐标导航: 检测到 {} ({}/{})", current_page.name, attempt + 1, max_retries)

            if current_page == GamePage.GACHA_RECORD:
                self._set_state(NavState.AT_RECORDS)
                return True

            if current_page in (GamePage.MAIN, GamePage.GACHA_ENTRANCE):
                x, y = self._coord("gacha_button")
                logger.info("坐标点击: 招集 ({}, {})", x, y)
                self._adb.click(x, y)
                time.sleep(2)

            elif current_page == GamePage.GACHA_HOME:
                x, y = self._coord("record_button")
                logger.info("坐标点击: 召集记录 ({}, {})", x, y)
                self._adb.click(x, y)
                time.sleep(2)

            else:
                # UNKNOWN — 尝试盲点
                logger.info("盲操作: 点击招集 + 召集记录")
                if attempt < 3:
                    self._adb.click(*self._coord("gacha_button"))
                    time.sleep(2)
                    self._adb.click(*self._coord("record_button"))
                    time.sleep(2)
                else:
                    break

        self._set_state(NavState.ERROR)
        return False

    def go_back(self) -> None:
        """返回上一页（发送 Android 返回键）"""
        self._adb.send_keyevent(4)
        time.sleep(0.5)

    # ── 鲁棒点击（带验证） ────────────────────────────

    def click_with_confirm(
        self,
        button: Button,
        target_page: Page,
        max_retries: int = 3,
        timeout: float = 5.0,
    ) -> bool:
        """点击按钮并验证到达目标页面

        流程：
          1. 截图 → 确认按钮可见
          2. 在 button 区域内随机取点点击
          3. 循环截图 → 检查 target_page.check_button.appear()
          4. 超时 → 检测弹窗 → 关闭弹窗重试
          5. 最多重试 max_retries 次

        Args:
            button: 要点击的按钮
            target_page: 期望到达的目标页面
            max_retries: 最大重试次数
            timeout: 单次等待超时

        Returns:
            True 表示成功到达目标页面
        """
        for attempt in range(max_retries):
            screenshot = self._safe_screenshot()
            if screenshot is None:
                continue

            # 1. 确认按钮可见
            if not button.appear(screenshot):
                logger.warning(
                    "按钮 '{}' 不可见 (尝试 {}/{})",
                    button.name, attempt + 1, max_retries,
                )
                # 检查是否已经在目标页
                if target_page.check_button.appear(screenshot):
                    logger.info("已在目标页面: {}", target_page.name)
                    return True
                time.sleep(0.5)
                continue

            # 2. 点击
            click_pos = self._get_click_position(screenshot, button)
            logger.info(
                "点击 '{}' @ ({}, {}) (尝试 {}/{})",
                button.name, click_pos[0], click_pos[1],
                attempt + 1, max_retries,
            )
            self._adb.click(*click_pos)

            # 3. 等待并验证到达
            start = time.time()
            while time.time() - start < timeout:
                time.sleep(0.5)
                after = self._safe_screenshot()
                if after is None:
                    continue

                if target_page.check_button.appear(after):
                    logger.info("已到达目标页面: {}", target_page.name)
                    return True

                # 4. 检测弹窗
                if self._detect_popup(after):
                    logger.info("检测到弹窗，尝试关闭...")
                    self._handle_popup()
                    time.sleep(0.5)

            logger.info("等待页面 '{}' 超时 ({}s)", target_page.name, timeout)

        logger.error("点击确认失败: {} → {}", button.name, target_page.name)
        return False

    def _get_click_position(
        self, screenshot: np.ndarray, button: Button
    ) -> tuple[int, int]:
        """获取按钮的最佳点击位置

        优先模板匹配精确定位，其次按钮区域中心。
        """
        if button.file:
            match_result = button.match(screenshot)
            if match_result:
                x, y, w, h, score = match_result
                return (x + w // 2, y + h // 2)
        return button.coord()

    # ── 弹窗处理 ──────────────────────────────────────

    def _detect_popup(self, screenshot: np.ndarray) -> bool:
        """检测意外弹窗"""
        # 检查是否有关闭按钮模板
        if self._popup_close_btn.file:
            if self._popup_close_btn.appear(screenshot):
                return True
        return False

    def _handle_popup(self) -> bool:
        """处理弹窗：点击关闭按钮"""
        screenshot = self._safe_screenshot()
        if screenshot is None:
            return False

        if self._popup_close_btn.appear(screenshot):
            pos = self._popup_close_btn.coord()
            logger.info("点击关闭弹窗 @ ({}, {})", pos[0], pos[1])
            self._adb.click(*pos)
            return True

        # 回退：尝试按返回键
        self._adb.send_keyevent(4)
        return True

    def handle_popup(self, screenshot: np.ndarray) -> bool:
        """检测并关闭意外弹窗（公开 API）"""
        if self._detect_popup(screenshot):
            return self._handle_popup()
        return False
