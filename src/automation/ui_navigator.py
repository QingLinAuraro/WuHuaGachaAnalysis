"""
UI 导航器
基于状态机模式的游戏界面导航
自动从主页面导航到"召集记录"页面
"""

import time
from enum import Enum, auto
from typing import Optional, Callable

import numpy as np
from loguru import logger

from src.emulator.adb_client import ADBClient
from src.emulator.screenshot import Screenshot
from src.automation.page_detector import PageDetector, GamePage


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
    """
    UI 导航器
    负责从主界面自动导航到"召集记录"页面

    导航路径（参考ALAS状态机设计）：
    主页 → 招集入口 → 招集主页（选择卡池）→ 召集记录 → 记录列表
    """

    # 模拟器 1280x720 分辨率下的预设坐标
    # 这些坐标需要根据实际游戏界面截图来校准
    COORDS_1280x720 = {
        # 主界面 → 点击"招集"按钮
        "gacha_button": (1100, 620),
        # 招集主页 → 点击"召集记录"按钮
        "record_button": (640, 680),
        # 召集记录列表 → 翻页滑动区域
        "record_list_start": (640, 560),
        "record_list_end": (640, 160),
        # 返回按钮
        "back_button": (60, 40),
        # 确认/关闭按钮
        "confirm_button": (640, 400),
        # 召集记录页 → "下一页"按钮
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
    ) -> None:
        self._adb = adb
        self._screenshot = screenshot
        self._detector = detector
        self._width = width
        self._height = height
        self._state = NavState.IDLE
        self._coords = self._get_coords()

        # 回调
        self._on_state_change: Optional[Callable[[NavState], None]] = None

    def _get_coords(self) -> dict:
        """根据分辨率选择坐标映射"""
        if self._width == 1920 and self._height == 1080:
            return self.COORDS_1920x1080
        return self.COORDS_1280x720

    def _coord(self, key: str) -> tuple[int, int]:
        """获取坐标，已按分辨率缩放"""
        base_w, base_h = 1280, 720
        x, y = self._coords.get(key, (0, 0))
        # 如果不是基准分辨率，按比例缩放
        if self._width != base_w or self._height != base_h:
            x = int(x * self._width / base_w)
            y = int(y * self._height / base_h)
        return x, y

    @property
    def state(self) -> NavState:
        return self._state

    def set_state_callback(self, callback: Callable[[NavState], None]) -> None:
        """设置状态变化回调（用于GUI更新）"""
        self._on_state_change = callback

    def _set_state(self, state: NavState) -> None:
        self._state = state
        logger.info("导航状态: {}", state.name)
        if self._on_state_change:
            self._on_state_change(state)

    def go_to_gacha_records(self) -> bool:
        """
        自动导航到召集记录页面
        返回是否成功
        """
        self._set_state(NavState.NAVIGATING_TO_GACHA)

        # 如果已有模板，尝试页面识别导航
        if self._detector.has_template(GamePage.MAIN) or \
           self._detector.has_template(GamePage.GACHA_RECORD):
            return self._navigate_by_template()

        # 没有模板，盲操作：假定用户已在召集记录页面
        return self._blind_navigate()

    def _navigate_by_template(self) -> bool:
        """基于模板匹配的页面导航"""
        max_retries = 5

        for attempt in range(max_retries):
            img = self._screenshot.capture_as_array()
            if img is None:
                time.sleep(1)
                continue

            current_page = self._detector.detect(img)
            logger.info("页面: {} (尝试 {}/{})", current_page.name, attempt + 1, max_retries)

            if current_page == GamePage.GACHA_RECORD:
                self._set_state(NavState.AT_RECORDS)
                return True

            if current_page == GamePage.MAIN:
                x, y = self._coord("gacha_button")
                logger.info("点击招集 ({}, {})", x, y)
                self._adb.click(x, y)
                time.sleep(2)

            elif current_page == GamePage.GACHA_HOME:
                x, y = self._coord("record_button")
                logger.info("点击召集记录 ({}, {})", x, y)
                self._adb.click(x, y)
                time.sleep(2)

            else:
                # UNKNOWN - 尝试按顺序盲点
                logger.info("未识别页面，尝试盲操作")
                if attempt < 3:
                    self._adb.click(*self._coord("gacha_button"))
                    time.sleep(2)
                    self._adb.click(*self._coord("record_button"))
                    time.sleep(2)
                else:
                    break

        self._set_state(NavState.ERROR)
        return False

    def _blind_navigate(self) -> bool:
        """无模板时的盲导航：假定已在召集记录页，尝试验证"""
        logger.info("模板未加载，假定已在召集记录页")
        # 做一次测试点击（右下角空白区域），验证ADB工作
        img = self._screenshot.capture_as_array()
        if img is None:
            self._set_state(NavState.ERROR)
            return False
        h, w = img.shape[:2]
        # 在右下角点一下（不干扰游戏操作）
        self._adb.click(w - 50, h - 20)
        time.sleep(0.3)
        self._set_state(NavState.AT_RECORDS)
        return True

    def go_back(self) -> None:
        """返回上一页"""
        self._adb.send_keyevent(4)
        time.sleep(0.5)
