"""
截图模块
封装 ADB 截图功能，提供 Image 对象
"""

from pathlib import Path
from typing import Optional

import numpy as np
from PIL import Image
from loguru import logger

from src.emulator.adb_client import ADBClient
from src.config import config


class Screenshot:
    """截图管理器"""

    def __init__(self, adb: ADBClient, save_dir: Optional[str] = None) -> None:
        self._adb = adb
        self._save_dir = Path(save_dir or config.get("adb.screenshot_dir"))
        self._save_dir.mkdir(parents=True, exist_ok=True)
        self._counter = 0

    def capture(self) -> Optional[Image.Image]:
        """截图并返回 PIL Image 对象"""
        data = self._adb.screenshot_bytes()
        if data is None:
            logger.error("截图数据为空")
            return None

        try:
            from io import BytesIO
            return Image.open(BytesIO(data))
        except Exception as e:
            logger.error("截图解析失败: {}", e)
            return None

    def capture_as_array(self) -> Optional[np.ndarray]:
        """截图并返回 numpy 数组 (BGR 格式，兼容 OpenCV)"""
        img = self.capture()
        if img is None:
            return None
        return np.array(img.convert("RGB"))[:, :, ::-1]  # RGB → BGR

    def capture_and_save(self) -> Optional[str]:
        """截图并保存到文件，返回文件路径"""
        data = self._adb.screenshot_bytes()
        if data is None:
            return None

        self._counter += 1
        filename = self._save_dir / f"screen_{self._counter:04d}.png"

        with open(filename, "wb") as f:
            f.write(data)

        logger.debug("截图已保存: {}", filename)
        return str(filename)

    def reset_counter(self) -> None:
        """重置截图计数器"""
        self._counter = 0
