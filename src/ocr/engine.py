"""
OCR 引擎 — 子进程隔离 PyTorch，批量处理整页记录
"""

import subprocess
import json
import tempfile
import os
from pathlib import Path
from typing import Optional
import numpy as np
import cv2
from loguru import logger


_WORKER_SCRIPT = Path(__file__).parent / "worker.py"


class OCREngine:
    """OCR 引擎 — 子进程批量处理"""

    def recognize_page(self, image: np.ndarray, regions: list[tuple[int, int]]) -> list[list[dict]]:
        """对整页截图的多个区域批量 OCR
        
        Args:
            image: 页面截图 (BGR)
            regions: [(y1, y2), ...] 每个记录条目的垂直范围
        
        Returns:
            [[{text, confidence, box}, ...], ...] 每个区域的识别结果
        """
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp_in:
            cv2.imwrite(tmp_in.name, image)

        tmp_out = tmp_in.name + ".json"
        regions_json = json.dumps(regions)

        try:
            proc = subprocess.run(
                [os.sys.executable, str(_WORKER_SCRIPT), tmp_in.name, regions_json, tmp_out],
                capture_output=True, text=True, timeout=60,
            )
            if proc.returncode != 0:
                logger.warning("OCR 子进程失败: {}", proc.stderr.strip())
                return [[] for _ in regions]

            with open(tmp_out, "r", encoding="utf-8") as f:
                results = json.load(f)
            return results
        except subprocess.TimeoutExpired:
            logger.warning("OCR 子进程超时")
            return [[] for _ in regions]
        except Exception as e:
            logger.warning("OCR 子进程异常: {}", e)
            return [[] for _ in regions]
        finally:
            for f in [tmp_in.name, tmp_out]:
                try:
                    os.unlink(f)
                except OSError:
                    pass

    def shutdown(self) -> None:
        pass


_ocr_engine: Optional[OCREngine] = None


def get_ocr_engine() -> OCREngine:
    global _ocr_engine
    if _ocr_engine is None:
        _ocr_engine = OCREngine()
    return _ocr_engine
