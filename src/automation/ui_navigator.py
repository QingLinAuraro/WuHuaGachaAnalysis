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

import time
from enum import Enum, auto
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
from src.automation.resolution import ResolutionAdapter
from src.automation.errors import (
    NavigationError,
    GameStuckError,
)


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
        resolution: Optional[ResolutionAdapter] = None,
        width: int = 1280,
        height: int = 720,
    ) -> None:
        self._adb = adb
        self._screenshot = screenshot
        self._detector = detector
        self._width = width
        self._height = height
        self._state = NavState.IDLE
        self._coords = self._get_coords()

        # 分辨率适配器（首次截图时自动检测实际分辨率）
        self._res = resolution or ResolutionAdapter()

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
        """安全截图回调（返回 1280×720 设计分辨率图像）"""
        try:
            img = self._screenshot.capture_as_array()
            if img is not None:
                h, w = img.shape[:2]
                logger.debug("原始截图: {}x{}", w, h)
                img = self._res.resize_screenshot(img)
            return img
        except Exception as e:
            logger.error("截图失败: {}", e)
            return None

    def _safe_click(self, x: int, y: int) -> bool:
        """安全点击回调（1280×720 坐标 → 实际屏幕坐标）"""
        try:
            real_x, real_y = self._res.to_real(x, y)
            return self._adb.click(real_x, real_y)
        except Exception as e:
            logger.error("点击失败: {}", e)
            return False

    # ── 坐标管理（所有坐标基于 1280×720 设计分辨率）──

    def _get_coords(self) -> dict:
        """返回 1280×720 设计分辨率下的预设坐标"""
        return dict(self.COORDS_1280x720)

    def _coord(self, key: str) -> tuple[int, int]:
        """获取 1280×720 设计分辨率下的坐标（实际屏幕坐标由 _safe_click 转换）"""
        return self._coords.get(key, (0, 0))

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
        """坐标盲操作导航（旧版兼容，坐标已由 adapter 缩放）"""
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
                x, y = self._res.to_real(*self._coord("gacha_button"))
                logger.info("坐标点击: 招集 ({}, {})", x, y)
                self._adb.click(x, y)
                time.sleep(2)

            elif current_page == GamePage.GACHA_HOME:
                x, y = self._res.to_real(*self._coord("record_button"))
                logger.info("坐标点击: 召集记录 ({}, {})", x, y)
                self._adb.click(x, y)
                time.sleep(2)

            else:
                # UNKNOWN — 尝试盲点
                logger.info("盲操作: 点击招集 + 召集记录")
                if attempt < 3:
                    self._adb.click(*self._res.to_real(*self._coord("gacha_button")))
                    time.sleep(2)
                    self._adb.click(*self._res.to_real(*self._coord("record_button")))
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

            # 2. 点击（1280×720 坐标 → 实际屏幕坐标）
            click_pos = self._get_click_position(screenshot, button)
            real_x, real_y = self._res.to_real(*click_pos)
            logger.info(
                "点击 '{}' @ ({}, {}) (尝试 {}/{})",
                button.name, real_x, real_y,
                attempt + 1, max_retries,
            )
            self._adb.click(real_x, real_y)

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
            real_pos = self._res.to_real(*pos)
            logger.info("点击关闭弹窗 @ ({}, {})", real_pos[0], real_pos[1])
            self._adb.click(*real_pos)
            return True

        # 回退：尝试按返回键
        self._adb.send_keyevent(4)
        return True

    def handle_popup(self, screenshot: np.ndarray) -> bool:
        """检测并关闭意外弹窗（公开 API）"""
        if self._detect_popup(screenshot):
            return self._handle_popup()
        return False
