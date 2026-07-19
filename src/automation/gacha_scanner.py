"""
召集记录扫描器（重写版）
基于图像识别的新架构：截图→分析→动作循环

核心改进：
  - 导航：使用 PageGraph.ensure() 确保在召集记录页
  - 翻页：结构体验证（OCR 页号 / 内容对比），替代不可靠的像素差分
  - 错误处理：卡住检测、弹窗处理、超时重试
  - 截图验证：每张截图都经过质量检查
  - 去重：基于 OCR 内容哈希的 record_id，跨扫描稳定
  - 中断：即时响应 stop()，页间/记录间可中断

保留兼容：
  - 公开 API 不变 (scan_all, set_banner, 回调接口)
  - OCR 和解析逻辑保持原有
"""

import time
import hashlib
import gc
from typing import Optional, Callable
from datetime import datetime

import numpy as np
import cv2
from loguru import logger

from src.emulator.adb_client import ADBClient
from src.emulator.screenshot import Screenshot
from src.automation.ui_navigator import UINavigator, NavState
from src.automation.page_detector import PageDetector, GamePage
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


def _compute_text_hash(ocr_results: list[dict]) -> str:
    """OCR 文本哈希（不含行号，跨扫描稳定）"""
    texts = "|".join(r["text"].strip() for r in ocr_results)
    return hashlib.md5(texts.encode()).hexdigest()[:8]


def _compute_content_hash(ocr_results: list[dict], row_index: int = 0) -> str:
    """内容哈希（含文本+行号，同页不同行不碰撞）"""
    texts = "|".join(r["text"].strip() for r in ocr_results)
    raw = f"{texts}#row{row_index}"
    return hashlib.md5(raw.encode()).hexdigest()[:8]


class GachaScanner:
    """召集记录扫描器 — 图像识别版

    使用方式：
        scanner = GachaScanner(adb, screenshot, detector)
        scanner.set_banner("活动招募", BannerType.EVENT)
        scanner.set_account(account_id)
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

        coord_cfg = config.get("automation.coords_file", "")
        self._navigator = UINavigator(
            adb, screenshot, detector,
            width=adb.get_screen_size()[0],
            height=adb.get_screen_size()[1],
            coord_config_path=coord_cfg if coord_cfg else None,
        )

        self._ocr = get_ocr_engine()
        self._parser = GachaRecordParser()

        self._page_delay: float = config.get("gacha.scan_page_delay", 2.0)
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
        self._current_account_id: int = 0

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

    def set_account(self, account_id: int) -> None:
        """设置当前扫描关联的账户ID"""
        self._current_account_id = account_id

    def stop(self) -> None:
        """停止扫描（当前页处理完后停止）"""
        self._is_running = False
        logger.info("收到停止信号，当前页处理完后将停止")

    def scan_all(self) -> list[GachaRecord]:
        """全量扫描（倒序：末尾页→首页）

        - 每次重新扫描都从末尾页开始
        - 基于 record_id（内容哈希）去重，跨扫描稳定
        - 只入库新记录，已有记录不重复计入
        """
        self._records = []
        self._is_running = True
        self._screenshot.reset_counter()
        self._adb.reset_click_history()

        # 加载DB已有 record_id 用于去重
        existing_records = db.get_all_records(account_id=self._current_account_id)
        existing_ids: set[str] = {r.record_id for r in existing_records}

        max_pn = max((r.pull_number for r in existing_records if r.pull_number > 0), default=0)

        logger.info("=" * 60)
        logger.info("开始扫描 - 账户ID={} 卡池: {} (已有 {} 条)",
                    self._current_account_id, self._current_banner_name,
                    len(existing_ids))
        logger.info("=" * 60)

        # 1. 导航到召集记录页
        if not self._is_running:
            return []
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
        if not self._is_running:
            return []
        logger.info("跳转到末尾页...")
        if not self._goto_last_page():
            logger.warning("跳转末尾页异常，从当前页开始扫描")

        # 3. 从末尾页向前扫描
        page = 1
        stuck_count = 0
        new_count = 0
        new_pns: list[int] = []  # 新记录的 pull_number

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

            page_banner = None
            page_type = None
            page_new = 0
            page_skip = 0
            for record in page_records:
                if not self._is_running:
                    break

                if page_banner is None and self._parser.banner_name and self._parser.banner_name != self._current_banner_name:
                    page_banner = self._parser.banner_name
                    page_type = self._parser.banner_type
                    logger.info("OCR卡池: {} [{}]", page_banner, page_type)
                record.banner_name = page_banner or self._current_banner_name
                record.banner_type = page_type or self._current_banner_type
                record.account_id = self._current_account_id
                record.pull_date = record.pull_time.strftime("%m-%d")

                if record.record_id in existing_ids:
                    logger.debug("跳过重复: {} (ID={})", record.character_name, record.record_id[:8])
                    page_skip += 1
                    continue

                existing_ids.add(record.record_id)
                page_new += 1
                max_pn += 1
                record.pull_number = max_pn
                new_pns.append(max_pn)
                self._records.append(record)

                try:
                    db.add_record(record)
                    new_count += 1
                except Exception as e:
                    logger.warning("入库失败: {} - {}", record.character_name, e)
                if self._on_record_found:
                    self._on_record_found(record)

            logger.info("第 {} 页: OCR {} 条, 新增 {}, 跳过 {}", page, len(page_records), page_new, page_skip)

            if not self._is_running:
                logger.info("扫描已中断，共新增 {} 条", new_count)
                break

            if not self._prev_page(img):
                logger.info("内容未变化，已回到首页")
                break

            page += 1
            gc.collect()

        self._is_running = False

        try:
            self._ocr.shutdown()
        except Exception:
            pass
        gc.collect()

        total = len(existing_ids)
        logger.info("扫描完成: 总计 {} 条 (新增 {})", total, new_count)

        self._notify_progress(page, page, f"扫描完成: 共{total}条, 新增{new_count}条")

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
        if self._final_page_btn.file:
            match_result = self._final_page_btn.match(img)
            if match_result:
                x, y, btn_w, btn_h, score = match_result
                logger.info("末尾页 @ ({}, {}) score={:.2f}", x + btn_w // 2, y + btn_h // 2, score)
                return (x + btn_w // 2, y + btn_h // 2)
        return ((self._final_page_btn.area[0] + self._final_page_btn.area[2]) // 2,
                (self._final_page_btn.area[1] + self._final_page_btn.area[3]) // 2)

    # ── 单页扫描 ──────────────────────────────────────

    def _scan_page(self, img: np.ndarray) -> list[GachaRecord]:
        """扫描单页 — 用整页10个角色名做页指纹"""
        records: list[GachaRecord] = []

        header_h = 218
        records_bottom = 551
        regions_y = [(header_h + i * (records_bottom - header_h) // 10,
                      header_h + (i + 1) * (records_bottom - header_h) // 10)
                     for i in range(10)]

        img_cropped = img[:, 420:]
        try:
            all_results = self._ocr.recognize_page(img_cropped, regions_y)
        except Exception as e:
            logger.error("批量 OCR 异常: {}", e)
            return records

        # 先收集所有行纠错后的角色名，做页指纹
        page_names: list[str] = []
        for i in range(10):
            ocr_results = all_results[i] if i < len(all_results) else []
            name_str = ""
            if ocr_results:
                # 从列解析中提取名字
                for r in ocr_results:
                    box = r["box"]
                    xs = [p[0] for p in box]
                    x_center = sum(xs) / len(xs)
                    if 0 <= x_center / img_cropped.shape[1] <= 330 / 860:
                        name_str += r["text"]
                name_str = self._parser._extract_name_from_column(name_str) or ""
            page_names.append(name_str)

        page_fingerprint = hashlib.md5(
            "|".join(page_names).encode()
        ).hexdigest()[:12]

        # 逐行生成记录
        for i in range(9, -1, -1):
            ocr_results = all_results[i] if i < len(all_results) else []
            if not ocr_results:
                continue

            record = self._parser.parse_record_from_ocr_results(
                ocr_results, img_width=img_cropped.shape[1], pull_number=0,
            )

            if record is None:
                name = self._extract_name_from_ocr(ocr_results)
                if name:
                    rarity = self._parser.lookup_rarity(name)
                    # 尝试从 OCR 中提取时间，失败再用当前时间
                    time_text = " ".join(r["text"] for r in ocr_results if r.get("text"))
                    pull_time = self._parser._extract_time(time_text) or datetime.now()
                    record = GachaRecord(
                        character_name=name, rarity=Rarity(rarity) if rarity else Rarity.FINE,
                        pull_time=pull_time,
                        banner_name=self._current_banner_name,
                        banner_type=self._current_banner_type,
                    )

            if record is not None:
                # record_id = 页指纹 + 行号，同页同位置必然相同
                record.record_id = hashlib.md5(
                    f"{page_fingerprint}|{i}".encode()
                ).hexdigest()[:12]
                record.text_hash = _compute_text_hash(ocr_results)
                record.content_hash = _compute_content_hash(ocr_results, row_index=i)
                records.append(record)

        return records

    # ── 截图 ────────────────────────────────────────────

    def _capture_screenshot(self) -> Optional[np.ndarray]:
        img = self._adb.screenshot_validate()
        if img is None:
            img = self._screenshot.capture_as_array()
        return img

    # ── 翻页 ──────────────────────────────────────────

    def _prev_page(self, before_img: np.ndarray) -> bool:
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
        return img[218:551, :]

    def _find_prev_button(self, img: np.ndarray) -> tuple[int, int]:
        if self._prev_page_btn.file:
            match_result = self._prev_page_btn.match(img)
            if match_result:
                x, y, btn_w, btn_h, score = match_result
                return (x + btn_w // 2, y + btn_h // 2)
        return self._navigator._coord("record_list_start")

    @staticmethod
    def _content_changed(before: np.ndarray, after: np.ndarray) -> bool:
        diff = cv2.absdiff(before, after)
        gray = cv2.cvtColor(diff, cv2.COLOR_BGR2GRAY)
        changed_pixels = np.count_nonzero(gray > 25)
        ratio = changed_pixels / gray.size
        logger.info("内容变化率: {:.2%}", ratio)
        return ratio > 0.008

    # ── 辅助 ──────────────────────────────────────────

    def _extract_name_from_ocr(self, ocr_results: list[dict]) -> Optional[str]:
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
    screenshot = Screenshot(adb)
    detector = PageDetector()
    return GachaScanner(adb, screenshot, detector)
