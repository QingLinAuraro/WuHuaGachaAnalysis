"""
设备管理模块
获取设备信息，管理模拟器配置
"""

from dataclasses import dataclass
from typing import Optional

from loguru import logger

from src.emulator.adb_client import ADBClient


@dataclass
class DeviceInfo:
    """设备信息"""
    serial: str
    width: int = 1280
    height: int = 720
    orientation: int = 0  # 0=竖屏, 1=横屏
    package_name: str = ""


class Device:
    """设备管理器"""

    def __init__(self, adb: ADBClient) -> None:
        self._adb = adb
        self._info: Optional[DeviceInfo] = None

    @property
    def info(self) -> DeviceInfo:
        if self._info is None:
            self.refresh()
        assert self._info is not None
        return self._info

    def refresh(self) -> DeviceInfo:
        """刷新设备信息"""
        serial = self._adb._serial or "unknown"
        width, height = self._adb.get_screen_size()
        orientation = self._adb.get_orientation()
        package_name = self._adb.get_package_name()

        # 如果是横屏且宽高反了，交换
        if orientation == 1 and width < height:
            width, height = height, width

        self._info = DeviceInfo(
            serial=serial,
            width=width,
            height=height,
            orientation=orientation,
            package_name=package_name,
        )
        logger.info(
            "设备信息: serial={}, 分辨率={}x{}, 方向={}, 前台应用={}",
            self._info.serial,
            self._info.width,
            self._info.height,
            "横屏" if self._info.orientation == 1 else "竖屏",
            self._info.package_name,
        )
        return self._info

    @property
    def is_landscape(self) -> bool:
        """是否为横屏"""
        return self.info.orientation == 1

    @property
    def screen_center(self) -> tuple[int, int]:
        """屏幕中心坐标"""
        return self.info.width // 2, self.info.height // 2
