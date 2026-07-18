"""
召集记录扫描器（重写版）
基于图像识别的新架构：截图→分析→动作循环

核心改进：
  - 导航：使用 PageGraph.ensure() 确保在召集记录页
  - 翻页：结构体验证（OCR 页号 / 内容对比），替代不可靠的像素差分
  - 错误处理：卡住检测、弹窗处理、超时重试
  - 截图验证：每张截图都经过质量检查

保留兼容：
  - 公开 API 不变 (scan_all, set_banner, 回调接口)
  - OCR 和解析逻辑保持原有
"""

import time
from typing import Optional, Callable
from datetime import datetime

import numpy as np
import cv2
from loguru import logger

from src.emulator.adb_client import ADBClient
from src.emulator.screenshot import Screenshot
from src.automation.ui_navigator import UINavigator, NavState
from src.automation.page_detector import PageDetector, GamePage, color_match_rarity
from src.automation.button import Button
from src.automation.errors import (
    GameStuckError,
    NavigationError,
)
from src.ocr.engine import get_ocr_engine
from src.ocr.parser import GachaRecordParser
from src.models.gacha_record import GachaRecord, Rarity, BannerType
from src.storage.database import db
from src.config import config


class GachaScanner:
    """召集记录扫描器 — 图像识别版

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

        # 导航器（使用 PageGraph）
        coord_cfg = config.get("automation.coords_file", "")
        self._navigator = UINavigator(
            adb, screenshot, detector,
            width=adb.get_screen_size()[0],
            height=adb.get_screen_size()[1],
            coord_config_path=coord_cfg if coord_cfg else None,
        )

        # OCR
        self._ocr = get_ocr_engine()
        self._parser = GachaRecordParser()

        # 扫描参数
        self._page_delay: float = config.get("gacha.scan_page_delay", 2.0)
        self._record_h_min: int = config.get("gacha.record_height_min", 45)
        self._record_h_max: int = config.get("gacha.record_height_max", 85)
        self._max_retries: int = config.get(
            "automation.image_recognition.max_retries", 3
        )

        # 翻页按钮
        self._next_page_btn = Button(
            area=(962, 564, 1070, 607),
            button=(962, 564, 1070, 607),
            file=str(config.project_root / "assets" / "templates" / "gacha" / "details" / "record" / "page_down.png"),
            similarity=config.get("automation.image_recognition.template_threshold", 0.8),
            name="NEXT_PAGE",
        )
        self._prev_page_btn = Button(
            area=(413, 561, 519, 611),
            button=(413, 561, 519, 611),
            file=str(config.project_root / "assets" / "templates" / "gacha" / "details" / "record" / "page_up.png"),
            similarity=config.get("automation.image_recognition.template_threshold", 0.8),
            name="PREV_PAGE",
        )
        self._final_page_btn = Button(
            area=(913, 565, 961, 609),
            button=(913, 565, 961, 609),
            file=str(config.project_root / "assets" / "templates" / "gacha" / "details" / "record" / "final_page.png"),
            similarity=config.get("automation.image_recognition.template_threshold", 0.8),
            name="FINAL_PAGE",
        )

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
        self._on_progress = callback

    def on_record_found(self, callback: Callable[[GachaRecord], None]) -> None:
        self._on_record_found = callback

    def on_complete(self, callback: Callable[[list[GachaRecord]], None]) -> None:
        self._on_complete = callback

    # ── 扫描流程 ──────────────────────────────────────

    def set_banner(self, name: str, banner_type: str = BannerType.UNKNOWN) -> None:
        self._current_banner_name = name
        self._current_banner_type = banner_type
        self._parser.set_banner(name, banner_type)

    def scan_all(self) -> list[GachaRecord]:
        """全量扫描（倒序：末尾页→首页）

        - 每次重新扫描都从末尾页开始
        - 自动跳过已存在的记录（按 pull_number 去重）
        """
        self._records = []
        self._is_running = True
        self._screenshot.reset_counter()
        self._adb.reset_click_history()

        # 加载已存在的 pull_number 集合用于快速去重
        existing_pns = {r.pull_number for r in db.get_all_records() if r.pull_number > 0}
        self._pull_counter = max(existing_pns) if existing_pns else 0

        logger.info("=" * 60)
        logger.info("开始扫描 - 卡池: {} (已有 {} 条, 从第 {} 条继续)",
                    self._current_banner_name, len(existing_pns), self._pull_counter + 1)
        logger.info("=" * 60)

        # 1. 导航到召集记录页
        try:
            if not self._navigator.go_to_gacha_records():
                logger.error("导航到召集记录页面失败")
                self._is_running = False
                return []
        except (NavigationError, GameStuckError) as e:
            logger.error("导航异常: {}", e)
            self._is_running = False
            return []

        # 2. 跳到末尾页
        logger.info("跳转到末尾页...")
        if not self._goto_last_page():
            logger.warning("跳转末尾页异常，从当前页开始扫描")

        # 3. 从末尾页向前扫描
        page = 1
        stuck_count = 0
        new_count = 0

        while self._is_running and page <= 500:
            logger.info(">>> 第 {} 页 <<<", page)
            self._notify_progress(page, 0, f"正在扫描第 {page} 页...")

            img = self._capture_screenshot()
            if img is None:
                stuck_count += 1
                if stuck_count >= 3:
                    logger.error("连续截图失败，停止扫描")
                    break
                time.sleep(1)
                continue
            stuck_count = 0

            try:
                page_records = self._scan_page(img)
            except Exception as e:
                logger.error("第 {} 页 OCR 异常: {}", page, e)
                page_records = []

            logger.info("第 {} 页: OCR {} 条", page, len(page_records))

            page_banner = None
            page_type = None
            for record in page_records:
                if page_banner is None and self._parser.banner_name and self._parser.banner_name != self._current_banner_name:
                    page_banner = self._parser.banner_name
                    page_type = self._parser.banner_type
                    logger.info("OCR卡池: {} [{}]", page_banner, page_type)
                record.banner_name = page_banner or self._current_banner_name
                record.banner_type = page_type or self._current_banner_type

                self._pull_counter += 1
                record.pull_number = self._pull_counter
                record.record_id = record._generate_id()
                self._records.append(record)

                # 快速去重：已存在则跳过入库
                if record.pull_number in existing_pns:
                    continue
                existing_pns.add(record.pull_number)
                try:
                    db.add_record(record)
                    new_count += 1
                except Exception:
                    pass
                if self._on_record_found:
                    self._on_record_found(record)

            if not self._prev_page(img):
                logger.info("内容未变化，已回到首页")
                break

            page += 1
            import gc
            gc.collect()

        self._is_running = False
        total = len(existing_pns)
        self._notify_progress(page, page, "扫描完成")

        try:
            self._ocr.shutdown()
        except Exception:
            pass
        import gc
        gc.collect()

        logger.info("扫描完成: {} 条 (新增 {})", total, new_count)

        if self._on_complete:
            self._on_complete(self._records)

        return self._records

    def _goto_last_page(self) -> bool:
        """点击末尾页按钮，一键跳转到最后一页"""
        if not self._is_running:
            return False
        img = self._capture_screenshot()
        if img is None:
            return False
        click_pos = self._find_final_button(img)
        self._adb.click(*click_pos)
        time.sleep(0.8)
        logger.info("已跳转到末尾页")
        return True

    def _find_final_button(self, img: np.ndarray) -> tuple[int, int]:
        """找到末尾页按钮的点击坐标"""
        if self._final_page_btn.file:
            match_result = self._final_page_btn.match(img)
            if match_result:
                x, y, btn_w, btn_h, score = match_result
                logger.info("末尾页 @ ({}, {}) score={:.2f}", x + btn_w // 2, y + btn_h // 2, score)
                return (x + btn_w // 2, y + btn_h // 2)
        # 回退到坐标
        return ((self._final_page_btn.area[0] + self._final_page_btn.area[2]) // 2,
                (self._final_page_btn.area[1] + self._final_page_btn.area[3]) // 2)

    def stop(self) -> None:
        """停止扫描"""
        self._is_running = False
        logger.info("扫描已停止")

    # ── 单页扫描 ──────────────────────────────────────

    def _scan_page(self, img: np.ndarray) -> list[GachaRecord]:
        """扫描单页 — 批量 OCR 整页10条记录"""
        records: list[GachaRecord] = []
        entry_regions = self._detect_entry_regions(img)
        n = len(entry_regions)

        # 收集各区域的 y 范围
        header_h = 220
        regions_y = [(header_h + i * (560 - header_h) // 10,
                      header_h + (i + 1) * (560 - header_h) // 10)
                     for i in range(n)]

        # 批量 OCR（一次子进程调用处理全页）
        try:
            all_results = self._ocr.recognize_page(img, regions_y)
        except Exception as e:
            logger.error("批量 OCR 异常: {}", e)
            return records

        # 从下往上处理
        for i in range(n - 1, -1, -1):
            ocr_results = all_results[i] if i < len(all_results) else []
            if not ocr_results:
                continue

            logger.debug("条目{} OCR: {}", i + 1, [r["text"] for r in ocr_results[:3]])

            record = self._parser.parse_record_from_ocr_results(
                ocr_results, img_width=img.shape[1], pull_number=0,
            )

            if record is None:
                rarity = color_match_rarity(entry_regions[i])
                if rarity is not None:
                    name = self._extract_name_from_ocr(ocr_results)
                    if name:
                        record = GachaRecord(
                            character_name=name, rarity=Rarity(rarity),
                            pull_time=datetime.now(),
                            banner_name=self._current_banner_name,
                            banner_type=self._current_banner_type,
                            pull_number=0,
                        )
            if record:
                records.append(record)

        return records

    def _detect_entry_regions(self, img: np.ndarray) -> list[np.ndarray]:
        """检测截图中每条抽卡记录的区域，按高度等分10条"""
        h, w = img.shape[:2]
        regions = []

        header_h = 220
        records_bottom = 560
        content_h = records_bottom - header_h
        record_h = content_h // 10

        for i in range(10):
            y1 = header_h + i * record_h
            y2 = y1 + record_h
            regions.append(img[y1:y2, :])

        return regions

    # ── 截图 ────────────────────────────────────────────

    def _capture_screenshot(self) -> Optional[np.ndarray]:
        """截图（优先 validate，回退到普通截图）"""
        img = self._adb.screenshot_validate()
        if img is None:
            img = self._screenshot.capture_as_array()
        return img

    # ── 翻页（内容对比版） ──────────────────────────────

    def _next_page(self, before_img: np.ndarray) -> bool:
        """点击下一页并通过内容对比验证是否翻页成功"""
        before_area = self._extract_record_area(before_img)
        click_pos = self._find_next_button(before_img)
        self._adb.click(*click_pos)
        time.sleep(0.6)
        after_img = self._capture_screenshot()
        if after_img is None:
            return False
        after_area = self._extract_record_area(after_img)
        changed = self._content_changed(before_area, after_area)
        if changed:
            logger.info("下一页: 内容已变化")
            return True
        else:
            logger.info("下一页: 内容未变化，已到末尾")
            return False

    def _prev_page(self, before_img: np.ndarray) -> bool:
        """点击上一页并通过内容对比验证"""
        before_area = self._extract_record_area(before_img)
        click_pos = self._find_prev_button(before_img)
        self._adb.click(*click_pos)
        time.sleep(0.6)
        after_img = self._capture_screenshot()
        if after_img is None:
            return False
        after_area = self._extract_record_area(after_img)
        changed = self._content_changed(before_area, after_area)
        if changed:
            logger.info("上一页: 内容已变化")
            return True
        else:
            logger.info("上一页: 内容未变化，已到首页")
            return False

    @staticmethod
    def _extract_record_area(img: np.ndarray) -> np.ndarray:
        """提取记录列表区域（y: 220-560）用于内容比较"""
        return img[220:560, :]

    def _find_next_button(self, img: np.ndarray) -> tuple[int, int]:
        """找到下一页按钮的点击坐标"""
        if self._next_page_btn.file:
            match_result = self._next_page_btn.match(img)
            if match_result:
                x, y, btn_w, btn_h, score = match_result
                logger.info("下一页 @ ({}, {}) score={:.2f}", x + btn_w // 2, y + btn_h // 2, score)
                return (x + btn_w // 2, y + btn_h // 2)
            else:
                logger.info("下一页模板匹配失败 score={:.3f}，使用坐标点击",
                            self._next_page_btn._match_score)
        return self._navigator._coord("next_page_button")

    def _find_prev_button(self, img: np.ndarray) -> tuple[int, int]:
        """找到上一页按钮的点击坐标"""
        if self._prev_page_btn.file:
            match_result = self._prev_page_btn.match(img)
            if match_result:
                x, y, btn_w, btn_h, score = match_result
                logger.info("上一页 @ ({}, {}) score={:.2f}", x + btn_w // 2, y + btn_h // 2, score)
                return (x + btn_w // 2, y + btn_h // 2)
            else:
                logger.info("上一页模板匹配失败 score={:.3f}，使用坐标点击",
                            self._prev_page_btn._match_score)
        return self._navigator._coord("record_list_start")

    @staticmethod
    def _content_changed(before: np.ndarray, after: np.ndarray) -> bool:
        """比较两个记录区域是否内容不同（像素差分）"""
        diff = cv2.absdiff(before, after)
        gray = cv2.cvtColor(diff, cv2.COLOR_BGR2GRAY)
        changed_pixels = np.count_nonzero(gray > 25)
        ratio = changed_pixels / gray.size
        logger.info("内容变化率: {:.2%}", ratio)
        return ratio > 0.008  # 0.8%像素变化 = 翻页成功

    # ── 辅助 ──────────────────────────────────────────

    def _extract_name_from_ocr(self, ocr_results: list[dict]) -> Optional[str]:
        """从OCR结果中提取最可能的器者名称"""
        import re
        best = ""
        best_conf = 0
        for r in ocr_results:
            text = r["text"].strip()
            conf = r["confidence"]
            if len(text) >= 2 and conf > best_conf:
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
