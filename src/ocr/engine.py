"""
OCR 引擎封装 — EasyOCR，每N页重建防止内存泄漏
"""

from typing import Optional
import gc
import numpy as np
from PIL import Image
from loguru import logger


class OCREngine:
    def __init__(self) -> None:
        self._ocr = None
        self._call_count = 0
        self._max_calls = 30  # 每30次OCR调用后重建

    def _init(self) -> None:
        if self._ocr is not None:
            del self._ocr
            gc.collect()
        import easyocr
        self._ocr = easyocr.Reader(["ch_sim", "en"], gpu=False)
        self._call_count = 0
        logger.info("EasyOCR 已就绪")

    @property
    def engine(self):
        if self._ocr is None:
            self._init()
        self._call_count += 1
        if self._call_count >= self._max_calls:
            logger.info("OCR 引擎重建（已调用{}次）", self._call_count)
            self._init()
        return self._ocr

    def recognize(self, image: np.ndarray | Image.Image) -> list[dict]:
        if isinstance(image, Image.Image):
            image = np.array(image.convert("RGB"))
        results = self.engine.readtext(image)
        parsed = []
        for box, text, confidence in results:
            parsed.append({
                "text": text,
                "confidence": float(confidence),
                "box": [[int(p[0]), int(p[1])] for p in box],
            })
        return parsed

    def recognize_text_only(self, image: np.ndarray | Image.Image) -> list[str]:
        return [r["text"] for r in self.recognize(image)]

    def recognize_region(self, image: np.ndarray, x1: int, y1: int, x2: int, y2: int) -> list[dict]:
        return self.recognize(image[y1:y2, x1:x2])


_ocr_engine: Optional[OCREngine] = None


def get_ocr_engine() -> OCREngine:
    global _ocr_engine
    if _ocr_engine is None:
        _ocr_engine = OCREngine()
    return _ocr_engine
