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
        max_retries = 3

        for attempt in range(max_retries):
            # 1. 截图看当前页面
            img = self._screenshot.capture_as_array()
            if img is None:
                logger.error("截图失败")
                time.sleep(1)
                continue

            current_page = self._detector.detect(img)
            logger.info("当前页面: {} (尝试 {}/{})", current_page.name, attempt + 1, max_retries)

            if current_page in (GamePage.GACHA_RECORD, GamePage.GACHA_DETAIL):
                self._set_state(NavState.AT_RECORDS)
                return True

            if current_page == GamePage.MAIN:
                # 点击"招集"按钮
                x, y = self._coord("gacha_button")
                logger.info("点击招集按钮 ({}, {})", x, y)
                self._adb.click(x, y)
                time.sleep(1.5)

            elif current_page in (GamePage.GACHA_ENTRANCE, GamePage.GACHA_HOME):
                # 点击"召集记录"按钮
                x, y = self._coord("record_button")
                logger.info("点击召集记录按钮 ({}, {})", x, y)
                self._adb.click(x, y)
                time.sleep(1.5)

            elif current_page == GamePage.OTHER:
                # 未知页面，尝试返回
                logger.info("未知页面，尝试返回")
                self._adb.send_keyevent(4)  # KEYCODE_BACK
                time.sleep(1)

            else:  # UNKNOWN
                # 当模板匹配不可用时，尝试盲操作
                logger.info("模板不可用，尝试盲操作导航")
                if attempt == 0:
                    # 先点击招集按钮位置
                    x, y = self._coord("gacha_button")
                    self._adb.click(x, y)
                    time.sleep(2)
                elif attempt == 1:
                    # 再点击召集记录按钮
                    x, y = self._coord("record_button")
                    self._adb.click(x, y)
                    time.sleep(2)

        self._set_state(NavState.ERROR)
        logger.error("无法导航到召集记录页面")
        return False

    def go_back(self) -> None:
        """返回上一页"""
        self._adb.send_keyevent(4)
        time.sleep(0.5)
