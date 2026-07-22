"""
分辨率自适应工具

参照 SRC/ALAS 框架方案：
  - 所有图像处理在 1280×720 设计分辨率下进行
  - 截图时自动检测实际分辨率（不信任 wm size，用实际帧缓冲）
  - 支持竖屏模拟器（游戏横屏居中显示），自动裁剪黑边
  - 点击/坐标按实际比例还原
"""

from typing import Optional
import cv2
import numpy as np
from loguru import logger

# 设计分辨率（所有模板和坐标的基准）
DESIGN_WIDTH = 1280
DESIGN_HEIGHT = 720

# 游戏画面宽高比
GAME_ASPECT = 16.0 / 9.0


class ResolutionAdapter:
    """分辨率适配器

    首次截图时自动检测实际分辨率（不信任 wm size 返回值）。

    用法:
        adapter = ResolutionAdapter()

        # 截图 → 裁剪游戏区域 → 缩放到 1280x720
        img = adapter.resize_screenshot(raw_screenshot)

        # 1280x720 坐标 → 实际屏幕坐标
        real_x, real_y = adapter.to_real(x, y)
    """

    def __init__(self, actual_width: int = 0, actual_height: int = 0) -> None:
        self._actual_w = actual_width
        self._actual_h = actual_height
        self._detected = False  # 是否已从实际截图检测过

        # 游戏区域在原始截图中的偏移
        self._game_offset_y: int = 0
        self._game_h: int = max(actual_height, DESIGN_HEIGHT)

        # 缩放比例
        self._scale_x: float = 1.0
        self._scale_y: float = 1.0
        self._needs_scale: bool = False

        if actual_width > 0 and actual_height > 0:
            self._detected = True
            self._recalc(actual_width, actual_height)

    def _recalc(self, w: int, h: int) -> None:
        """根据实际截图分辨率重新计算缩放参数"""
        self._actual_w = w
        self._actual_h = h
        self._game_offset_y = 0
        self._game_h = h

        # 竖屏模拟器（高度 > 宽度）：游戏横屏在中间，上下有黑边
        if h > w:
            self._game_h = int(w / GAME_ASPECT)
            self._game_offset_y = (h - self._game_h) // 2

        self._scale_x = w / DESIGN_WIDTH
        self._scale_y = self._game_h / DESIGN_HEIGHT
        self._needs_scale = (w != DESIGN_WIDTH or h != DESIGN_HEIGHT)

        logger.info(
            "分辨率适配: 实际截图={}x{} 设计={}x{} scale=({:.3f}, {:.3f}) "
            "游戏区域 y={} h={}",
            w, h, DESIGN_WIDTH, DESIGN_HEIGHT,
            self._scale_x, self._scale_y, self._game_offset_y, self._game_h,
        )

    @property
    def scale_x(self) -> float:
        return self._scale_x

    @property
    def scale_y(self) -> float:
        return self._scale_y

    @property
    def needs_scale(self) -> bool:
        return self._needs_scale

    @property
    def actual_size(self) -> tuple[int, int]:
        return (self._actual_w, self._actual_h)

    def resize_screenshot(self, img: np.ndarray) -> np.ndarray:
        """裁剪游戏画面区域 → 缩放到 1280×720 设计分辨率"""
        h, w = img.shape[:2]

        # 首次截图：用实际分辨率校准（不信任 wm size）
        if not self._detected:
            self._detected = True
            if w != self._actual_w or h != self._actual_h:
                logger.warning(
                    "截图实际分辨率 {}x{} 与 wm size {}x{} 不一致，以截图为准",
                    w, h, self._actual_w, self._actual_h,
                )
            self._recalc(w, h)

        if not self._needs_scale:
            return img

        # 竖屏模拟器：裁剪出游戏横屏区域
        if self._game_offset_y > 0:
            game_bottom = min(self._game_offset_y + self._game_h, h)
            game_top = max(self._game_offset_y, 0)
            if game_bottom > game_top:
                img = img[game_top:game_bottom, :]

        return cv2.resize(img, (DESIGN_WIDTH, DESIGN_HEIGHT))

    def to_real(self, x: int, y: int) -> tuple[int, int]:
        """设计分辨率坐标 → 实际屏幕坐标（含竖屏偏移）"""
        if not self._needs_scale:
            return x, y
        real_x = int(x * self._scale_x)
        real_y = int(y * self._scale_y) + self._game_offset_y
        return real_x, real_y

    def from_real(self, x: int, y: int) -> tuple[int, int]:
        """实际屏幕坐标 → 设计分辨率坐标"""
        if not self._needs_scale:
            return x, y
        return int(x / self._scale_x), int((y - self._game_offset_y) / self._scale_y)
