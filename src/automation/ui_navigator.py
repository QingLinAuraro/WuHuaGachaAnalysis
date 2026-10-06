"""
UI 导航器（重写版）
基于 PageGraph 页面图的图像识别导航系统

核心改变：
  - 旧版：固定坐标 + 盲操作 → 新版：图像识别 + 页面图导航
  - 旧版：sleep(2) 等待 → 新版：循环截图验证 + 超时保护
  - 旧版：无错误恢复 → 新版：弹窗处理 + 卡住检测 + 重试

安全约束：
  - 任何一步识别不出当前页面都直接失败返回，不做坐标盲点击。
    盲点击可能落到抽卡按钮上，造成用户资源损失。
  - 没有配置关闭模板的弹窗处理不执行任何点击。

保留对外 API 兼容：
  - go_to_gacha_records()   → 内部使用 PageGraph.ensure()
  - go_back()               → send keyevent 4
  - state / set_state_callback() → 状态变化通知
"""

import time
from enum import Enum, auto
from typing import Optional, Callable

import numpy as np
from loguru import logger

from src.emulator.adb_client import ADBClient
from src.emulator.screenshot import Screenshot
from src.automation.page_detector import PageDetector
from src.automation.page_graph import (
    PageGraph,
    build_wuhua_pages,
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
            area=(1200, 10, 70, 50),
            button=(1200, 10, 70, 50),
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
        """自动导航到召集记录页面（只用图像识别，不做坐标盲操作）

        任意一步识别不出当前页面都直接失败返回：盲点击可能落到抽卡按钮上，
        造成用户资源损失，所以宁可放弃这一轮扫描。

        Returns:
            是否成功到达召集记录页
        """
        self._set_state(NavState.NAVIGATING_TO_GACHA)

        if self._try_image_navigation():
            self._set_state(NavState.AT_RECORDS)
            return True

        logger.error("图像识别导航失败：无法用界面模板确认当前页面，已停止操作（不做盲点击）")
        self._set_state(NavState.ERROR)
        return False

    def _try_image_navigation(self) -> bool:
        """使用 PageGraph 进行图像识别导航"""
        # 检查是否有可用的模板
        screenshot = self._safe_screenshot()
        if screenshot is None:
            logger.error("截图失败，无法导航")
            return False

        # 测试是否有任何页面能被识别
        current = self._page_graph.get_current_page(screenshot)
        if current is None:
            logger.error("所有页面模板都匹配不上，当前界面未知 —— 停止导航")
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

    def go_back(self) -> None:
        """返回上一页（发送 Android 返回键）"""
        self._adb.send_keyevent(4)
        time.sleep(0.5)

    # ── 弹窗处理 ──────────────────────────────────────

    def _detect_popup(self, screenshot: np.ndarray) -> bool:
        """检测意外弹窗"""
        # 检查是否有关闭按钮模板
        if self._popup_close_btn.file:
            if self._popup_close_btn.appear(screenshot):
                return True
        return False

    def _handle_popup(self) -> bool:
        """处理弹窗：点击关闭按钮

        没有配置关闭按钮模板时不做任何点击 —— 盲点（含返回键）都可能误触游戏内按钮。
        """
        if self._popup_close_btn.file is None and self._popup_close_btn.color is None:
            logger.warning("未配置弹窗关闭按钮模板，跳过弹窗处理（不做任何点击）")
            return False

        screenshot = self._safe_screenshot()
        if screenshot is None:
            return False

        if self._popup_close_btn.appear(screenshot):
            pos = self._popup_close_btn.coord()
            real_pos = self._res.to_real(*pos)
            logger.info("点击关闭弹窗 @ ({}, {})", real_pos[0], real_pos[1])
            self._adb.click(*real_pos)
            return True

        return False

    def handle_popup(self, screenshot: np.ndarray) -> bool:
        """检测并关闭意外弹窗（公开 API）"""
        if self._detect_popup(screenshot):
            return self._handle_popup()
        return False
