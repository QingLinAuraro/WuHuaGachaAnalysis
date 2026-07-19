"""
截图模块
封装 ADB 截图功能，提供 Image 对象
"""

import os
import tempfile
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
        """截图并返回 PIL Image 对象 — 使用 pull 方式，兼容性更好"""
        import tempfile
        tmp = os.path.join(tempfile.gettempdir(), "wuhua_tmp.png")
        if not self._adb.screenshot(tmp):
            logger.error("截图失败")
            return None
        try:
            return Image.open(tmp)
        except Exception as e:
            logger.error("截图解析失败: {}", e)
            return None

    def capture_as_array(self) -> Optional[np.ndarray]:
        """截图并返回 numpy 数组 (BGR 格式，兼容 OpenCV)"""
        img = self.capture()
        if img is None:
            return None
        arr = np.array(img.convert("RGB"))[:, :, ::-1]  # RGB → BGR
        return np.ascontiguousarray(arr)

    def capture_and_save(self) -> Optional[tuple[np.ndarray, str]]:
        """截图，保存文件并返回 numpy 数组和文件路径"""
        self._counter += 1
        filename = str(self._save_dir / f"screen_{self._counter:04d}.png")
        ok = self._adb.screenshot(filename)
        logger.info("ADB截图 {} -> {} ({} bytes)", 
                     self._counter, "OK" if ok else "FAIL",
                     Path(filename).stat().st_size if ok and Path(filename).exists() else 0)
        if not ok:
            return None
        try:
            img = Image.open(filename)
            arr = np.array(img.convert("RGB"))[:, :, ::-1]
            return np.ascontiguousarray(arr), filename
        except Exception as e:
            logger.error("截图解析失败: {}", e)
            return None

    def reset_counter(self) -> None:
        """重置截图计数器"""
        self._counter = 0
