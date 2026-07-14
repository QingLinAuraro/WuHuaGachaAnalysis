"""
OCR 引擎封装
支持 PaddleOCR（首选）和 Tesseract（备选）
"""

from typing import Optional
import numpy as np
from PIL import Image
from loguru import logger

from src.config import config


class OCREngine:
    """
    OCR 引擎封装
    封装 PaddleOCR，提供统一的文字识别接口
    """

    def __init__(self) -> None:
        self._ocr = None
        self._engine_name = config.get("ocr.engine", "paddleocr")
        self._use_gpu = config.get("ocr.use_gpu", False)
        self._initialized = False

    def _init_paddleocr(self) -> None:
        """初始化 PaddleOCR"""
        try:
            from paddleocr import PaddleOCR
            self._ocr = PaddleOCR(
                use_angle_cls=True,
                lang="ch",
                use_gpu=self._use_gpu,
                show_log=False,
            )
            logger.info("PaddleOCR 初始化完成 (GPU={})", self._use_gpu)
            self._initialized = True
        except ImportError:
            logger.error(
                "PaddleOCR 未安装，请运行: pip install paddleocr paddlepaddle"
            )
            raise
        except Exception as e:
            logger.error("PaddleOCR 初始化失败: {}", e)
            raise

    @property
    def engine(self):
        """延迟初始化 OCR 引擎"""
        if not self._initialized:
            self._init_paddleocr()
        return self._ocr

    def recognize(
        self, image: np.ndarray | Image.Image
    ) -> list[dict]:
        """
        识别图片中的文字

        Args:
            image: numpy 数组 (BGR) 或 PIL Image

        Returns:
            [{text, confidence, box}, ...]
            - text: 识别文字
            - confidence: 置信度 (0-1)
            - box: [[x1,y1],[x2,y2],[x3,y3],[x4,y4]] 四个角点
        """
        if isinstance(image, Image.Image):
            image = np.array(image.convert("RGB"))

        results = self.engine.ocr(image, cls=True)

        if not results or not results[0]:
            return []

        parsed = []
        for line in results[0]:
            box, (text, confidence) = line
            parsed.append({
                "text": text,
                "confidence": confidence,
                "box": [[int(p[0]), int(p[1])] for p in box],
            })

        return parsed

    def recognize_text_only(self, image: np.ndarray | Image.Image) -> list[str]:
        """只返回识别到的文字列表"""
        results = self.recognize(image)
        return [r["text"] for r in results]

    def recognize_region(
        self,
        image: np.ndarray,
        x1: int, y1: int, x2: int, y2: int,
    ) -> list[dict]:
        """
        识别图片中指定区域的文字

        Args:
            image: 完整图片的 numpy 数组
            x1, y1, x2, y2: 区域坐标

        Returns:
            同 recognize() 的返回格式
        """
        region = image[y1:y2, x1:x2]
        return self.recognize(region)


# 全局 OCR 引擎实例（单例延迟初始化）
_ocr_engine: Optional[OCREngine] = None


def get_ocr_engine() -> OCREngine:
    """获取全局 OCR 引擎实例"""
    global _ocr_engine
    if _ocr_engine is None:
        _ocr_engine = OCREngine()
    return _ocr_engine
