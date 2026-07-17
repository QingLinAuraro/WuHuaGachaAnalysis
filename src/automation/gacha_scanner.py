"""
召集记录扫描器
核心扫描逻辑：自动翻页、截图、OCR识别、数据提取
"""

import time
from typing import Optional, Callable
from pathlib import Path
from datetime import datetime

import numpy as np
import cv2
from loguru import logger

from src.emulator.adb_client import ADBClient
from src.emulator.screenshot import Screenshot
from src.automation.ui_navigator import UINavigator, NavState
from src.automation.page_detector import PageDetector, GamePage, color_match_rarity
from src.ocr.engine import get_ocr_engine
from src.ocr.parser import GachaRecordParser
from src.models.gacha_record import GachaRecord, Rarity, BannerType
from src.storage.database import db
from src.config import config


class GachaScanner:
    """
    召集记录扫描器
    自动扫描召集记录页面，逐页截图识别，直到扫描完所有记录

    使用方式：
        scanner = GachaScanner(adb, screenshot, detector)
        scanner.set_banner("活动招募", BannerType.EVENT)
        records = scanner.scan_all()
    """

    def __init__(
        self,
        adb: ADBClient,
        screenshot: Screenshot,
        detector: PageDetector,
    ) -> None:
        self._adb = adb
        self._screenshot = screenshot
        self._detector = detector

        # 导航器
        self._navigator = UINavigator(
            adb, screenshot, detector,
            width=adb.get_screen_size()[0],
            height=adb.get_screen_size()[1],
        )

        # OCR
        self._ocr = get_ocr_engine()
        self._parser = GachaRecordParser()

        # 扫描参数
        self._page_delay: float = config.get("gacha.scan_page_delay", 0.5)
        self._record_h_min: int = config.get("gacha.record_height_min", 80)
        self._record_h_max: int = config.get("gacha.record_height_max", 200)

        # 状态
        self._records: list[GachaRecord] = []
        self._is_running: bool = False
        self._current_banner_name: str = ""
        self._current_banner_type: str = BannerType.UNKNOWN
        self._pull_counter: int = 0

        # 回调
        self._on_progress: Optional[Callable[[int, int, str], None]] = None
        self._on_record_found: Optional[Callable[[GachaRecord], None]] = None
        self._on_complete: Optional[Callable[[list[GachaRecord]], None]] = None

    # ── 回调设置 ──────────────────────────────────────

    def on_progress(self, callback: Callable[[int, int, str], None]) -> None:
        """进度回调 (当前页, 总页数, 状态信息)"""
        self._on_progress = callback

    def on_record_found(self, callback: Callable[[GachaRecord], None]) -> None:
        """发现新记录回调"""
        self._on_record_found = callback

    def on_complete(self, callback: Callable[[list[GachaRecord]], None]) -> None:
        """扫描完成回调"""
        self._on_complete = callback

    # ── 扫描流程 ──────────────────────────────────────

    def set_banner(self, name: str, banner_type: str = BannerType.UNKNOWN) -> None:
        """设置当前扫描的卡池信息"""
        self._current_banner_name = name
        self._current_banner_type = banner_type
        self._parser.set_banner(name, banner_type)

    def scan_all(self) -> list[GachaRecord]:
        """
        执行全量扫描
        返回所有识别到的抽卡记录
        """
        self._records = []
        self._is_running = True
        self._pull_counter = 0
        self._screenshot.reset_counter()

        logger.info("=" * 60)
        logger.info("开始扫描召集记录 - 卡池: {}", self._current_banner_name)
        logger.info("=" * 60)

        # 1. 导航到召集记录页面
        if not self._navigator.go_to_gacha_records():
            logger.error("导航到召集记录页面失败")
            self._is_running = False
            return []

        # 2. 开始逐页扫描
        page = 1
        max_pages = 500

        while self._is_running and page <= max_pages:
            logger.info(">>> 开始第 {} 页 <<<", page)
            self._notify_progress(page, 0, f"正在扫描第 {page} 页...")

            # 一次截图
            result = self._screenshot.capture_and_save()
            if result is None:
                logger.error("第 {} 页截图失败", page)
                break
            img, fname = result
            logger.info("截图已保存: {}", Path(fname).name)

            # OCR
            page_records = self._scan_page(img)
            logger.info("第 {} 页 OCR 完成: {} 条", page, len(page_records))

            if page_records:
                logger.info("第 {} 页: 识别到 {} 条记录", page, len(page_records))
                for record in page_records:
                    record.banner_name = self._current_banner_name
                    record.banner_type = self._current_banner_type
                    self._records.append(record)
                    if db.add_record(record):
                        logger.debug("新增: {}", record.character_name)
                    if self._on_record_found:
                        self._on_record_found(record)
            else:
                logger.info("第 {} 页: 无记录", page)

            # 翻页
            if not self._click_next_page():
                logger.info("翻页失败，扫描结束")
                break

            # 等待页面稳定加载
            time.sleep(self._page_delay)

            page += 1

        self._is_running = False
        self._notify_progress(page, page, "扫描完成")

        # 更新 pull_number（按时间排序后重新编号）
        self._records.sort(key=lambda r: r.pull_time, reverse=True)
        total = len(self._records)
        for i, record in enumerate(self._records):
            record.pull_number = total - i

        logger.info("扫描完成: 共 {} 条记录", total)

        if self._on_complete:
            self._on_complete(self._records)

        return self._records

    def stop(self) -> None:
        """停止扫描"""
        self._is_running = False
        logger.info("扫描已停止")

    # ── 单页扫描 ──────────────────────────────────────

    def _scan_page(self, img: np.ndarray) -> list[GachaRecord]:
        """
        扫描单页截图中的所有抽卡记录

        步骤：
        1. 定位每条抽取记录的区域（按 y 坐标等分）
        2. 放大 2 倍 + 锐化，提升 OCR 识别率
        3. OCR 识别，利用 box 坐标按列解析
        4. 解析为 GachaRecord
        """
        records: list[GachaRecord] = []

        # 检测并分割每条记录条目
        entry_regions = self._detect_entry_regions(img)
        logger.info("检测到 {} 个记录条目", len(entry_regions))

        for i, region in enumerate(entry_regions):
            try:
                # 预处理：放大 2 倍让文字更清晰，减少乱码
                h, w = region.shape[:2]
                region_up = cv2.resize(region, (w * 2, h * 2), interpolation=cv2.INTER_CUBIC)

                # 锐化增强文字边缘
                kernel = np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]], dtype=np.float32)
                region_up = cv2.filter2D(region_up, -1, kernel)

                # EasyOCR 期望 RGB 输入
                region_rgb = cv2.cvtColor(region_up, cv2.COLOR_BGR2RGB)
                ocr_results = self._ocr.recognize(region_rgb)
            except Exception as e:
                logger.warning("条目{} OCR 识别异常: {}", i + 1, e)
                continue

            if not ocr_results:
                continue

            logger.debug("条目{} OCR 结果: {}", i + 1, [r["text"] for r in ocr_results])

            # 按列位置解析（利用 box 坐标）
            self._pull_counter += 1
            record = self._parser.parse_record_from_ocr_results(
                ocr_results, img_width=w * 2, pull_number=self._pull_counter,
            )
            logger.debug(
                "条目{} 解析: {} -> {}",
                i + 1, [r["text"] for r in ocr_results],
                record.character_name if record else "失败",
            )

            if record is None:
                # 回退：颜色辅助判断稀有度
                rarity = color_match_rarity(region)
                if rarity is not None:
                    name = self._extract_name_from_ocr(ocr_results)
                    if name:
                        record = GachaRecord(
                            character_name=name,
                            rarity=Rarity(rarity),
                            pull_time=datetime.now(),
                            banner_name=self._current_banner_name,
                            banner_type=self._current_banner_type,
                            pull_number=self._pull_counter,
                        )

            if record:
                records.append(record)

        return records

    def _detect_entry_regions(self, img: np.ndarray) -> list[np.ndarray]:
        """
        检测截图中每条抽卡记录的区域
        物华弥新每页固定10条记录，直接按高度等分

        页面布局（y坐标）：
          0-180:   顶部标题
          180-220: 表头（稀有度、器者、召集、时间）
          220-560: 10条抽卡记录（340px / 10 = 34px/条）
          560-640: 页码列表
          640+:    关闭按钮
        """
        h, w = img.shape[:2]
        regions = []

        # 记录从表头下方开始：220px ~ 560px
        header_h = 220
        records_bottom = 560
        content_h = records_bottom - header_h  # 340px
        record_h = content_h // 10              # 34px/条

        for i in range(10):
            y1 = header_h + i * record_h
            y2 = y1 + record_h
            regions.append(img[y1:y2, :])

        return regions

    # ── 辅助 ──────────────────────────────────────────

    def _click_next_page(self) -> bool:
        """
        点击"下一页"按钮翻页
        模板匹配到了就信任，没匹配到用像素对比
        """
        before = self._screenshot.capture_as_array()
        if before is None:
            return False

        # 模板匹配找"下一页"按钮
        clicked_template = False
        if self._detector.has_template(GamePage.GACHA_RECORD):
            next_btn = self._detector._templates_dir / "gacha_record" / "next_page.png"
            if next_btn.exists():
                template = cv2.imread(str(next_btn))
                if template is not None:
                    pos = self._detector.find_button(before, template)
                    if pos:
                        logger.info("点击下一页 ({}, {})", pos[0], pos[1])
                        self._adb.click(pos[0], pos[1])
                        clicked_template = True

        if not clicked_template:
            x, y = self._navigator._coord("next_page_button")
            logger.info("坐标点击下一页 ({}, {})", x, y)
            self._adb.click(x, y)

        time.sleep(2.0)  # 等待翻页完成后页面加载

        # 模板匹配到的直接信任
        if clicked_template:
            return True

        after = self._screenshot.capture_as_array()
        if after is None:
            return False

        diff = cv2.absdiff(before, after)
        ratio = np.count_nonzero(cv2.cvtColor(diff, cv2.COLOR_BGR2GRAY) > 30) / diff.size
        logger.info("翻页像素变化: {:.2%}", ratio)
        return ratio > 0.002

    def _extract_name_from_ocr(self, ocr_results: list[dict]) -> Optional[str]:
        """从OCR结果中提取最可能的器者名称"""
        best = ""
        best_conf = 0
        for r in ocr_results:
            text = r["text"].strip()
            conf = r["confidence"]
            # 找置信度高且长度合理的中文字符串
            if len(text) >= 2 and conf > best_conf:
                # 排除纯数字和特殊字符
                import re
                if re.search(r"[\u4e00-\u9fff]", text):
                    best = text
                    best_conf = conf
        return best if best else None

    def _notify_progress(self, current: int, total: int, info: str) -> None:
        if self._on_progress:
            self._on_progress(current, total, info)


# ── 工厂函数 ──────────────────────────────────────────

def create_scanner(adb: ADBClient) -> GachaScanner:
    """创建扫描器实例的便捷函数"""
    screenshot = Screenshot(adb)
    detector = PageDetector()
    return GachaScanner(adb, screenshot, detector)
