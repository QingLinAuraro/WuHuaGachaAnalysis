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
        max_pages = 500  # 安全上限
        consecutive_empty = 0  # 连续空页计数

        while self._is_running and page <= max_pages:
            self._notify_progress(page, 0, f"正在扫描第 {page} 页...")

            # 截图
            img = self._screenshot.capture_as_array()
            if img is None:
                logger.error("第 {} 页截图失败", page)
                break

            # 保存截图（调试用）
            self._screenshot.capture_and_save()

            # OCR识别当前页
            page_records = self._scan_page(img)

            if page_records:
                consecutive_empty = 0
                logger.info("第 {} 页: 识别到 {} 条记录", page, len(page_records))

                for record in page_records:
                    record.banner_name = self._current_banner_name
                    record.banner_type = self._current_banner_type
                    self._records.append(record)

                    # 存入数据库
                    if db.add_record(record):
                        logger.debug("新增记录: {} ({}★)", record.character_name, record.rarity.value)
                    if self._on_record_found:
                        self._on_record_found(record)
            else:
                consecutive_empty += 1
                logger.info("第 {} 页: 无新记录", page)
                if consecutive_empty >= 3:
                    logger.info("连续 {} 页无记录，扫描结束", consecutive_empty)
                    break

            # 3. 滑动翻到下一页
            if not self._click_next_page():
                logger.info("无法继续翻页，可能已到最后一页")
                break

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
        1. 定位每条抽取记录的区域（基于颜色/布局特征）
        2. 对每个区域进行OCR识别
        3. 解析为 GachaRecord
        """
        records: list[GachaRecord] = []

        # 检测并分割每条记录条目
        entry_regions = self._detect_entry_regions(img)
        logger.debug("检测到 {} 个记录条目区域", len(entry_regions))

        for i, region in enumerate(entry_regions):
            # OCR识别该区域
            ocr_results = self._ocr.recognize(region)
            texts = [r["text"] for r in ocr_results]

            if not texts:
                continue

            # 解析记录
            self._pull_counter += 1
            record = self._parser.parse_record_from_texts(texts, self._pull_counter)

            if record is None:
                # 尝试用颜色辅助判断稀有度
                rarity = color_match_rarity(region)
                if rarity is not None:
                    # 至少有稀有度信息，尝试构造记录
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

        策略：
        1. 通过颜色/边缘检测定位每条记录的水平分割线
        2. 每条记录通常有固定的高度范围
        3. 返回每个条目区域的截图
        """
        h, w = img.shape[:2]
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        # 边缘检测
        edges = cv2.Canny(gray, 50, 150)

        # 水平投影（找到水平分割线）
        horizontal_projection = np.mean(edges, axis=1)

        # 找到分割线位置（水平投影值高的行）
        threshold = np.mean(horizontal_projection) * 1.5
        split_lines = np.where(horizontal_projection > threshold)[0]

        if len(split_lines) == 0:
            # 没有找到分割线，可能是一整页新样式
            # 尝试按固定高度分割
            return self._split_by_height(img, h)

        # 将相邻的分割线合并
        merged_lines = self._merge_lines(split_lines.tolist(), gap=5)

        # 根据分割线提取条目区域
        regions = []
        for i in range(len(merged_lines) - 1):
            y1 = merged_lines[i]
            y2 = merged_lines[i + 1]
            region_h = y2 - y1
            if self._record_h_min <= region_h <= self._record_h_max:
                regions.append(img[y1:y2, :])

        # 如果没有找到有效区域，使用固定高度分割
        if not regions:
            return self._split_by_height(img, h)

        return regions

    def _split_by_height(self, img: np.ndarray, h: int) -> list[np.ndarray]:
        """按固定高度分割条目（兜底方案）"""
        regions = []
        record_height = 120  # 默认每条记录约120px高
        y = 0
        while y + record_height <= h:
            regions.append(img[y:y + record_height, :])
            y += record_height
        return regions

    def _merge_lines(self, lines: list[int], gap: int = 5) -> list[int]:
        """合并相邻的分割线"""
        if not lines:
            return []
        merged = [lines[0]]
        for val in lines[1:]:
            if val - merged[-1] > gap:
                merged.append(val)
        return merged

    def _click_next_page(self) -> bool:
        """
        点击"下一页"按钮翻页
        先尝试模板匹配定位按钮，失败则用预设坐标点击
        返回是否成功翻页
        """
        # 截图确认当前内容
        before = self._screenshot.capture_as_array()
        if before is None:
            return False

        # 方式1：模板匹配找"下一页"按钮
        clicked = False
        if self._detector.has_template(GamePage.GACHA_RECORD):
            from pathlib import Path
            next_btn_template_path = self._detector._templates_dir / "gacha_record" / "next_page.png"
            if next_btn_template_path.exists():
                template = cv2.imread(str(next_btn_template_path))
                if template is not None:
                    pos = self._detector.find_button(before, template)
                    if pos:
                        logger.info("模板匹配到下一页按钮: ({}, {})", pos[0], pos[1])
                        self._adb.click(pos[0], pos[1])
                        clicked = True

        # 方式2：预设坐标点击（兜底）
        if not clicked:
            x, y = self._navigator._coord("next_page_button")
            logger.info("使用预设坐标点击下一页: ({}, {})", x, y)
            self._adb.click(x, y)

        time.sleep(1.0)

        # 截图确认内容是否变化
        after = self._screenshot.capture_as_array()
        if after is None:
            return False

        # 比较是否翻页成功（像素差异）
        diff = cv2.absdiff(before, after)
        diff_ratio = np.count_nonzero(cv2.cvtColor(diff, cv2.COLOR_BGR2GRAY) > 30) / diff.size

        logger.debug("页面变化率: {:.2%}", diff_ratio)
        return diff_ratio > 0.01  # 至少1%像素有变化

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

    # ── 辅助 ──────────────────────────────────────────

    def _notify_progress(self, current: int, total: int, info: str) -> None:
        if self._on_progress:
            self._on_progress(current, total, info)


# ── 工厂函数 ──────────────────────────────────────────

def create_scanner(adb: ADBClient) -> GachaScanner:
    """创建扫描器实例的便捷函数"""
    screenshot = Screenshot(adb)
    detector = PageDetector()
    return GachaScanner(adb, screenshot, detector)
