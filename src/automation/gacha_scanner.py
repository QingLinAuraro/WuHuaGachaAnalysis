"""
召集记录扫描器（重写版）
基于图像识别的新架构：截图→分析→动作循环

核心改进：
  - 导航：使用 PageGraph.ensure() 确保在召集记录页
  - 翻页：结构体验证（OCR 页号 / 内容对比），替代不可靠的像素差分
  - 错误处理：卡住检测、弹窗处理、超时重试
  - 截图验证：每张截图都经过质量检查
  - 去重：record_id = 内容键 + 同键出现序号，与页面/行号无关，跨扫描稳定
  - 中断：即时响应 stop()，页间/记录间可中断

保留兼容：
  - 公开 API 不变 (scan_all, set_banner, 回调接口)
  - OCR 和解析逻辑保持原有
"""

import time
import hashlib
import gc
from collections import Counter
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
from src.automation.resolution import ResolutionAdapter
from src.automation.pages.gacha_channel import (
    channel_by_elimination,
    find_visible_channels,
    get_channel_button,
)
from src.automation.pages.gacha_record import BTN_SELECT as BTN_EXPAND_CHANNEL
from src.automation.errors import (
    GameStuckError,
    NavigationError,
)
from src.ocr.engine import get_ocr_engine
from src.ocr.parser import GachaRecordParser
from src.models.gacha_record import (
    GachaRecord, Rarity, BannerType,
    make_record_id, make_record_key, make_dedup_key,
)
from src.storage.database import get_db
from src.config import config


def _compute_text_hash(ocr_results: list[dict]) -> str:
    """OCR 文本哈希（不含行号，跨扫描稳定）"""
    texts = "|".join(r["text"].strip() for r in ocr_results)
    return hashlib.md5(texts.encode()).hexdigest()[:8]


class GachaScanner:
    """召集记录扫描器 — 图像识别版

    使用方式：
        scanner = GachaScanner(adb, screenshot, detector)
        scanner.set_banner("", BannerType.UNKNOWN)   # 卡池名/类型由 OCR 逐页覆盖
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

        screen_w, screen_h = adb.get_screen_size()
        self._res = ResolutionAdapter()  # 首次截图时自动检测实际分辨率

        self._navigator = UINavigator(
            adb, screenshot, detector,
            resolution=self._res,
            width=screen_w,
            height=screen_h,
        )

        self._ocr = get_ocr_engine()
        self._parser = GachaRecordParser()

        self._page_delay: float = config.get("gacha.scan_page_delay", 2.0)
        self._max_retries: int = config.get(
            "automation.image_recognition.max_retries", 3
        )

        # 翻页按钮（只向前翻：进入记录页时默认停在第 1 页，逐页向后读到末尾）
        # 底部翻页栏横向居中、宽度随记录页数变化 → "下一页"按钮会水平漂移（纵向不动）。
        # area = 模板搜索区域，必须覆盖按钮的全部漂移范围；且必须大于模板尺寸，
        #   否则 matchTemplate 只输出 1×1，退化成"定点比对"。
        # 实测按钮中心（设计分辨率 1280×720，y 中心恒为 585~586）：
        #   下一页 x：>10页 1016 / 5页 918 / 2页 844 / 1页 820
        # button = 该按钮在原宽布局下的位置，仅作记录；匹配失败时不再据此盲点击，
        #   而是交给 _next_page 做安全停机判断。
        self._next_page_btn = Button(
            area=(750, 553, 340, 67),        # 模板 108×43 → 可滑动中心 x 804~1036
            button=(962, 564, 108, 43),
            file=str(config.resource_root / "assets" / "templates" / "gacha" / "details" / "record" / "page_down.png"),
            similarity=config.get("automation.image_recognition.template_threshold", 0.8),
            name="NEXT_PAGE",
        )

        # 渠道切换（记录页右上角下拉箭头 → 展开渠道列表 → 选条目）
        # 展开按钮复用 pages/gacha_record.py 的 BTN_SELECT
        self._expand_channel_btn = BTN_EXPAND_CHANNEL
        self._panel_delay: float = config.get("gacha.channel_panel_delay", 1.0)
        self._max_pages: int = config.get("gacha.max_pages_per_channel", 500)
        self._action_interval: float = config.get(
            "automation.image_recognition.action_interval", 0.5
        )

        # 状态
        self._records: list[GachaRecord] = []
        self._is_running: bool = False
        self._abort_reason: str = ""     # 安全停机原因（非空表示这一轮不是正常扫到末页）
        self._last_known_time: Optional[datetime] = None  # 跨页沿用最后一条已知时间
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
        """全量扫描（正序：第 1 页 → 末页）

        - 进入召集记录页时游戏默认停在第 1 页，用"下一页"逐页向后读取
        - 存在性判断：按 (内容键, 出现序号) 与库内记录对齐。
          内容键 = 时间(到分) + 账户，不含角色名/卡池名/稀有度 ——
          这三样都来自 names.yaml，跨版本改词库会让同一条记录识别成不同写法，
          放进内容键就会导致整批老记录对不上、被重复计入
        - pull_number 在入库后按【全库时间序】统一重编（见 _resequence_numbers）：
          pull_number 只作排序键（home_page / export_to_json 都按它升序），
          中断补齐更旧的记录后，按时间重编才能保证它们落在正确位置，
          而不是被追加到最新记录之后
        """
        self._records = []
        self._is_running = True
        self._abort_reason = ""
        self._last_known_time = None
        self._screenshot.reset_counter()
        self._adb.reset_click_history()

        # 加载当前账户已有记录，用于存在性判断
        existing_records = get_db().get_all_records(account_id=self._current_account_id)
        #
        # 建"已入库三元组"集合 (内容键, seq, 名称)。
        # 为什么不直接比 record_id：ID 算法换过几版，库里老记录的 ID 与
        # 新算法算的不是一回事，直接比会把整批老记录当成新记录重复入库。
        #
        # seq 从库里怎么还原：库里存的永远是该组【最新端连续若干条】
        # （扫描从第 1 页最新那条开始），所以组内按"新 → 旧"排，
        # 第 0 条就是该组最新那条，它的 seq = 0，往下依次 1、2、3……
        #
        # 组内次序怎么定：同一分钟的 pull_time 完全相同，单靠它排不出来。
        #   - 新数据（本版之后入库的）：pull_number 就是按 (pull_time, -seq_no)
        #     全局重编过的，升序 = 旧→新，所以降序即"新→旧"，与扫描器一致。
        #   - 老数据（没有 seq_no 列时入库的）：seq_no 全是 0，但 pull_number
        #     是当时的入库顺序，降序同样能还原出"新→旧"。
        #     实测老库 16 条同分钟组的 pull_number 与插入顺序完全一致，
        #     所以老库重扫依然零新增（见 wh_v2 T5）。
        #   ⚠️ 不要用 record_id 当次序键：那是 md5 哈希，会把顺序随机打乱。
        #
        # ⚠️ 跳过【微秒非 0】的老记录：那是旧代码 now() 兜底的产物，它的内容键是按
        #    "兜底那一刻"的分钟算的，与游戏里真实的那一分钟无关，不可靠。
        #    若让它参与判重，会把"该分钟真实有几条"的阈值虚高，
        #    导致这一分钟最新的若干条真实记录被误判成"已入库"而永久跳过。
        #    这些老记录本身【不删除、不修改】，界面照常显示，只是不参与判重对齐。
        reliable = [r for r in existing_records if not r.pull_time.microsecond]
        by_group: dict[str, list] = {}
        for r in reliable:
            by_group.setdefault(make_record_key(r), []).append(r)
        db_keys: set = set()
        for key, recs in by_group.items():
            # 组内按"新 → 旧"：先按时间降序，同一分钟再按 pull_number 降序
            # （pull_number 大 = 更晚 = 更新）
            recs.sort(key=lambda x: (x.pull_time, x.pull_number or 0), reverse=True)
            for seq, r in enumerate(recs):
                db_keys.add((key, seq, r.character_name))

        logger.info("=" * 60)
        logger.info("开始扫描 - 账户ID={} 卡池: {} (已有 {} 条)",
                    self._current_account_id,
                    self._current_banner_name or "(由OCR读取)",
                    len(existing_records))
        logger.info("=" * 60)

        # 0. 预热 OCR 引擎（首次加载模型到文件缓存，避免首页超时）
        self._ocr.warmup()

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

        # 2. 逐渠道扫描
        #    每个渠道（卡池类型）对应一份独立的记录：
        #      识别当前渠道 → 从第 1 页翻到末页 → 展开面板切到下一个未扫渠道 → 重复
        #    直到所有渠道都扫过，或自动切换被关闭 / 切换失败。
        #    进入记录页时默认停在第 1 页，切换渠道后同样回到第 1 页。
        #
        #    "一共要扫几个渠道"不写死：每次切换前把面板展开，按面板里实际显示的
        #    条目数来算（见 pages/gacha_channel.find_visible_channels），
        #    游戏以后加渠道类型也不会漏。
        #
        #    本批新记录按扫描顺序（渠道内：页 1→末页、页内从上到下 = 新→旧）暂存，
        #    全部渠道扫完后统一编号并入库。
        new_records: list[GachaRecord] = []
        auto_switch: bool = bool(config.get("gacha.auto_switch_channel", True))
        scanned_channels: set = set()
        overall_page = 0
        current_channel: Optional[str] = None
        panel_open = False      # 渠道面板当前是否被我们点开了（结束时需要收回去）

        while self._is_running:
            # ── 内层：扫完当前渠道的全部页 ──
            page = 1
            stuck_count = 0
            stop_all = False    # 需整体停止：截图连续失败 / 安全停机 / 用户中断

            while self._is_running and page <= self._max_pages:
                overall_page += 1
                logger.info(">>> 第 {} 页（渠道 {}）<<<", page, current_channel or "识别中")
                self._notify_progress(
                    overall_page, 0,
                    f"正在扫描「{current_channel or '当前渠道'}」第 {page} 页...",
                )

                img = self._capture_screenshot()
                if img is None:
                    stuck_count += 1
                    if stuck_count >= 3:
                        logger.error("连续截图失败，停止扫描")
                        stop_all = True
                        break
                    time.sleep(1)
                    continue
                stuck_count = 0

                try:
                    page_records = self._scan_page(img)
                except Exception as e:
                    logger.error("第 {} 页 OCR 异常: {}", page, e)
                    page_records = []

                # 第 1 页用来确定"当前看的是哪个渠道"。
                # 切换成功后的渠道已有权威值（就是点进去的那个），这里再用 OCR 复核：
                # 万一切换点错了条目，以页面实际内容为准 —— 否则会把"没扫过的渠道"
                # 误记成已扫，导致永久漏扫。
                if page == 1:
                    detected = self._detect_channel(page_records)
                    if detected != BannerType.UNKNOWN:
                        if current_channel is not None and detected != current_channel:
                            logger.warning("页面实际渠道为「{}」，与预期「{}」不符"
                                           "（切换可能点错了），以页面为准",
                                           detected, current_channel)
                        else:
                            logger.info("当前渠道: {}", detected)
                        current_channel = detected
                    else:
                        logger.info("当前渠道: 本页 OCR 未识别出类型")

                page_banner = None
                page_type = None
                for record in page_records:
                    if page_banner is None and self._parser.banner_name and self._parser.banner_name != self._current_banner_name:
                        page_banner = self._parser.banner_name
                        page_type = self._parser.banner_type
                        logger.info("OCR卡池: {} [{}]", page_banner, page_type)
                    record.banner_name = page_banner or self._current_banner_name
                    record.banner_type = page_type or self._current_banner_type
                    record.account_id = self._current_account_id
                    record.pull_date = record.pull_time.strftime("%m-%d")
                    new_records.append(record)

                logger.info("第 {} 页: OCR {} 条 (账户ID={})",
                            page, len(page_records), self._current_account_id)

                if not self._is_running:
                    logger.info("扫描已中断，本批已收集 {} 条", len(new_records))
                    stop_all = True
                    break

                if not self._next_page(img):
                    if self._abort_reason:
                        logger.error("安全停机: {} —— 已停止扫描（不做盲点击，避免误触抽卡）",
                                     self._abort_reason)
                        stop_all = True
                    else:
                        logger.info("「{}」内容未变化，本渠道已到最后一页",
                                    current_channel or "当前渠道")
                    break

                page += 1
                gc.collect()

            if stop_all or not self._is_running:
                break

            # ── 本渠道扫完 ──
            if current_channel and current_channel != BannerType.UNKNOWN:
                scanned_channels.add(current_channel)
            logger.info("「{}」扫描完成；已扫 {} 个渠道: {}",
                        current_channel or "未知渠道",
                        len(scanned_channels), sorted(scanned_channels))

            if not auto_switch:
                logger.info("自动切换渠道已关闭，结束扫描")
                break

            # ── 展开面板：看这个账号实际有哪些渠道，再挑下一个没扫过的 ──
            #    "要扫几个"完全以展开后显示的条目为准，不写死渠道种类数。
            img = self._open_channel_panel()
            if img is None:
                logger.warning("渠道面板展开失败，停止自动切换（不做盲点击）")
                break
            panel_open = True

            visible = find_visible_channels(img)
            logger.info("面板中可切换的渠道: {}", visible or "（无）")

            # 当前渠道还没认出来（OCR 失败）→ 排除法兜底：
            # 面板里匹配不到模板的那个条目就是选中态，也就是当前正在看的渠道
            if not current_channel or current_channel == BannerType.UNKNOWN:
                current_channel = channel_by_elimination(visible)
                if current_channel != BannerType.UNKNOWN:
                    logger.info("当前渠道（排除法）: {}", current_channel)
                    scanned_channels.add(current_channel)

            if not current_channel or current_channel == BannerType.UNKNOWN:
                logger.warning("渠道类型未能识别，停止自动切换（否则会反复扫同一个渠道）")
                break

            # 需要扫描的总数 = 面板里能匹配到的（未选中态）+ 当前选中这个
            # （当前选中那条是浅色高亮底，匹配不上，得单独算进来）
            total_channels = len(set(visible) | {current_channel})

            if len(scanned_channels) >= total_channels:
                logger.info("已扫描 {}/{} 个渠道，全部完成",
                            len(scanned_channels), total_channels)
                break

            # 下一个没扫过的渠道：按界面自上而下的顺序取
            target = next((t for t in visible if t not in scanned_channels), None)
            if target is None:
                logger.warning("面板中已无未扫描的渠道（已扫 {} 个 / 面板共 {} 个），结束",
                               len(scanned_channels), total_channels)
                break

            logger.info("切换渠道: {} → {}（第 {}/{} 个）",
                        current_channel, target, len(scanned_channels) + 1, total_channels)
            if not self._switch_channel(target):
                logger.error("切换到渠道「{}」失败，停止扫描（不做盲点击）", target)
                break

            # 切换成功 = 面板已被游戏自动收起
            panel_open = False
            current_channel = target
            # 新渠道是独立的时间序列，跨页时间锚点必须重置
            self._last_known_time = None
            gc.collect()

        self._is_running = False

        # 最后一轮是为了"看还有没有没扫过的渠道"才展开面板的，扫完要收回去，
        # 别让游戏停在面板展开的状态（否则可能影响下一次导航/截图）
        if panel_open:
            self._close_channel_panel()

        # 3. 存在性判断 + 分配 record_id + 入库
        #    new_records 是扫描顺序（页 1→末页、页内从上到下）= 全局"新→旧"
        #
        #    seq 的含义是"同一分钟内，距最新那条的偏移"（最新 = 0，越旧越大）。
        #    这个基准是稳定的：扫描永远从第 1 页第 1 行（该组最新那条）开始，
        #    不管中途在哪一行中断，同一条记录算出的 seq 都一样，
        #    于是 record_id 也稳定 —— 重扫时能识别出"这条已经入过库"。
        #    ⚠️ 不能用"从最旧往新数"的位次：那会把组的起点绑在"最旧那条"上，
        #       而最旧那条会随中断位置变化 —— 组内断在中间时重扫会补错记录
        #       （实测会变成 c9 c9 c8 c8 c7 c7 c6 c6 c5 c4 这种重复）。
        ordered = list(reversed(new_records))   # 旧→新（用于入库顺序与下面的排序）

        # 时间全都没识别出来 = OCR 大面积失败。这批记录没有稳定锚点，
        # 入库后每次扫描都会算出新的内容键 → 反复重复计入，宁可不入库。
        if ordered and all(r.pull_time.microsecond for r in ordered):
            logger.error("本批 {} 条记录的时间全部未识别出来，无法生成稳定的 record_id，"
                         "本次不入库（请检查 OCR 与模板）", len(ordered))
            ordered = []

        # 逐条过滤：只要有任意一条仍然是 now() 兜底（微秒非 0），说明它的时间没拿到，
        # 内容键会随每次扫描漂移 —— 入库就是一次新的重复，直接拦下不入库。
        # 宁可少记一条（下次重扫能补），绝不重复计入。
        bad_time = [r for r in ordered if r.pull_time.microsecond]
        if bad_time:
            logger.warning("发现 {} 条记录的时间未识别出来（now() 兜底），已跳过不入库: {}",
                           len(bad_time),
                           ", ".join(r.character_name for r in bad_time[:5]))
            ordered = [r for r in ordered if not r.pull_time.microsecond]

        # 为每个内容键分配 seq：seq = 距该组【最新那条】的偏移（最新 = 0，越旧越大）。
        #
        # ⚠️ 必须在过滤【之后】、基于真要入库的 ordered 来编号。
        #    若拿过滤前的 new_records 编号，被剔除的兜底行会占掉一个位次，
        #    而它两次扫描"在不在本批里"可能不同（第一次没读到 / 第二次读到并剔除），
        #    于是它后面每条记录的 seq 在两次扫描间整体错开 → 判重失效、永久漏记录。
        #
        # ordered 是旧→新，所以"距最新偏移" = 组内总条数 - 1 - 从旧数的位次。
        seq_of: dict[int, int] = {}
        group_counter: Counter = Counter()
        for record in ordered:                      # ordered：旧 → 新
            key = make_record_key(record)
            group_counter[key] += 1
        group_total = dict(group_counter)
        seen_in_group: Counter = Counter()
        for record in ordered:                      # ordered：旧 → 新
            key = make_record_key(record)
            seen_in_group[key] += 1
            seq_of[id(record)] = group_total[key] - seen_in_group[key]

        to_insert: list[GachaRecord] = []
        dup_count = 0
        for record in ordered:
            key = make_record_key(record)
            seq = seq_of[id(record)]
            if make_dedup_key(record, seq) in db_keys:
                # 这个 (分钟, 位置, 器者) 已经在库里 —— 上次扫描已经计入过
                dup_count += 1
                continue
            record.record_id = make_record_id(record, seq)
            # ⚠️ 把组内顺序号落库。游戏的记录页时间只到"分"，同一分钟能出几十条
            #    （一次十连 10 条必然同分钟），单靠 pull_time 排不出先后。
            #    以前只靠 record_id 的哈希当次序键，等于把真实抽取顺序随机打乱 ——
            #    实测"水晶杯明明是这一池的第 10 抽，却被算成第 1 抽"。
            record.seq_no = seq
            # pull_number 这里只占位，真正赋值在入库后按 (时间, 组内顺序号) 统一重编
            record.pull_number = 0
            to_insert.append(record)

        new_count = 0
        if to_insert:
            try:
                new_count = get_db().add_records(to_insert)
            except Exception as e:
                logger.warning("批量入库失败: {}", e)
            self._records = to_insert
            if self._on_record_found:
                for record in to_insert:
                    self._on_record_found(record)

        # 4. 按全库时间序重编 pull_number
        #    中断补齐时新入库的是【更旧】的记录，若按"追加到最大值之后"编号，
        #    UI 按 pull_number 升序排就会把更旧的记录排到最新之后（垫抽顺序错乱）。
        #    pull_number 只作排序键（垫抽由 home_page 按卡池类型各自累加），
        #    所以直接按 (pull_time, record_id) 全库重编，保证与时间严格同序。
        self._resequence_numbers()

        try:
            self._ocr.shutdown()
        except Exception:
            pass
        gc.collect()

        total = get_db().get_record_count(account_id=self._current_account_id)
        logger.info("扫描完成: 本次读到 {} 条, 新增 {} 条, 已在库中 {} 条, 库内共 {} 条"
                    "（共 {} 个渠道，{} 页）",
                    len(new_records), new_count, dup_count, total,
                    len(scanned_channels), overall_page)

        self._notify_progress(overall_page, overall_page,
                              f"扫描完成: 共{total}条, 新增{new_count}条")

        if self._on_complete:
            self._on_complete(self._records)

        return self._records

    def _resequence_numbers(self) -> None:
        """按真实抽取顺序重编本账户的 pull_number（1 起递增）

        pull_number 的唯一用途是排序（home_page 与 export_to_json 都用它升序），
        垫抽计数是 home_page 按卡池类型各自累加的，与它无关。
        所以只要保证「与真实抽取顺序严格同序」即可。

        排序键必须是 (pull_time, -seq_no)，不能是 (pull_time, record_id)：
          - 游戏的记录页时间只精确到"分"，一次十连 10 条 pull_time 完全相同，
            连续两次十连落在同一分钟就是 20 条 —— 同分钟内靠 pull_time 排不出先后。
          - record_id 是 md5 哈希，拿它当次序键 = 随机打乱。
            实测导致"水晶杯本该是第 10 抽被算成第 1 抽"（历史 bug）。
          - seq_no 是扫描时按"距该组最新那条的偏移"算出来的（最新 = 0，越旧越大），
            与游戏页面的真实顺序一致，所以同分钟内按 seq_no 倒序即"旧 → 新"。
        """
        account_id = self._current_account_id
        records = get_db().get_all_records(account_id=account_id)
        if not records:
            return
        # (时间, 组内顺序号倒序)：同一分钟内 seq_no 大的（更旧）排前面
        records.sort(key=lambda r: (r.pull_time, -(r.seq_no or 0)))

        changed: list[tuple[str, int]] = []
        for i, r in enumerate(records, start=1):
            if r.pull_number != i:
                changed.append((r.record_id, i))
        if not changed:
            return
        n = get_db().set_pull_numbers(changed)
        logger.info("已按真实抽取顺序重编 pull_number（{} 条）", n)

    # ── 渠道（卡池）切换 ──────────────────────────────

    @staticmethod
    def _detect_channel(records: list[GachaRecord]) -> str:
        """从当前页记录推断"当前正在看哪个渠道"

        记录页只显示当前选中渠道的记录，所以页内每条的 banner_type 相同，
        取第一条有效值即可。

        ⚠️ 不要改用面板模板反查当前渠道：面板里当前渠道处于选中态（浅色底 + 绿勾），
           与未选中态模板差异较大，会失配（实测「限时渠道」选中时，它自己的模板
           xianshi.png 反而在「限定渠道」那一行得 0.891）。识别当前渠道首选用 OCR，
           OCR 认不出类型时再用排除法兜底（见 channel_by_elimination）。

        Returns:
            BannerType 常量；识别不出时返回 BannerType.UNKNOWN
        """
        for record in records:
            banner_type = record.banner_type
            if banner_type and banner_type != BannerType.UNKNOWN:
                return banner_type
        return BannerType.UNKNOWN

    def _open_channel_panel(self) -> Optional[np.ndarray]:
        """确保渠道面板处于展开状态，返回展开后的截图；失败返回 None

        判定"已展开"的依据：面板区域里至少能匹配到一个【未选中态】渠道条目。
        注意不能靠展开按钮判断 —— 面板展开前后那支箭头外观不变
        （实测面板已展开时，select.png 依然得 0.9940，照样匹配得到）。

        ⚠️ 账号只有一个渠道时，面板里只有当前选中那一条，一个模板也匹配不到，
           这里会重试到上限并返回 None，上层据此停止自动切换。这是安全的
           （最多多点两下展开按钮，不会点到别处），而且这种账号本来也没渠道可切。
        """
        for attempt in range(1, self._max_retries + 1):
            if not self._is_running:
                return None

            img = self._capture_screenshot()
            if img is None:
                logger.warning("展开渠道面板: 截图失败（第 {} 次）", attempt)
                time.sleep(1)
                continue

            if find_visible_channels(img):
                return img

            if not self._expand_channel_btn.appear(img):
                logger.warning("展开渠道面板: 展开按钮不可见（第 {} 次）", attempt)
                time.sleep(self._action_interval)
                continue

            pos = self._expand_channel_btn.coord()
            logger.info("展开渠道面板 @ ({}, {}) score={:.2f}",
                        pos[0], pos[1], self._expand_channel_btn._match_score)
            self._adb.click(*self._res.to_real(*pos))
            time.sleep(self._panel_delay)

        logger.warning("展开渠道面板失败（已尝试 {} 次）：面板中未出现其他渠道条目",
                       self._max_retries)
        return None

    def _close_channel_panel(self) -> None:
        """收起渠道面板

        展开按钮是个开关：面板已展开时再点一下就收起（外观不变，只能靠点击来切）。
        只在"确认面板当前是展开的"之后调用。收不起来也不影响主流程，
        所以不重试、不报错 —— 目的是别让游戏界面停在展开状态影响下一次扫描。
        """
        img = self._capture_screenshot()
        if img is None or not self._expand_channel_btn.appear(img):
            return
        pos = self._expand_channel_btn.coord()
        logger.info("收起渠道面板 @ ({}, {})", pos[0], pos[1])
        self._adb.click(*self._res.to_real(*pos))
        time.sleep(self._panel_delay)

    def _switch_channel(self, target_type: str) -> bool:
        """展开渠道面板并点击目标渠道条目

        每轮流程：
          截图 → 在面板区域匹配目标条目模板
            · 匹配不到 → 说明面板未展开（或已收起）→ 点展开按钮，等待后重试
            · 匹配到   → 点击条目中心 → 再截图确认面板已收起

        为什么"匹配不到就展开"是安全的：待切换的目标渠道必然是**未选中态**
        （当前选中的渠道刚扫完、已经记进已扫描集合），未选中条目与模板一致，
        正常能匹配到；匹配不到就只可能是面板没展开。

        点击坐标取模板匹配到的区域中心，不会去点固定坐标。

        Args:
            target_type: 目标渠道类型。调用方（scan_all）从面板可见条目里挑，
                         一定是"没扫过 + 未选中态"，所以这里不会去点当前选中那条。

        Returns:
            True 表示点击已生效（面板收起）
        """
        btn = get_channel_button(target_type)
        if btn is None:
            logger.warning("渠道「{}」没有对应的面板模板，无法切换", target_type)
            return False

        for attempt in range(1, self._max_retries + 1):
            if not self._is_running:
                return False

            img = self._capture_screenshot()
            if img is None:
                logger.warning("切换渠道: 截图失败（第 {} 次）", attempt)
                time.sleep(1)
                continue

            match = btn.match(img)
            if match is None:
                # 面板未展开 → 点展开按钮
                if not self._expand_channel_btn.appear(img):
                    logger.warning("切换渠道: 展开按钮不可见（第 {} 次）", attempt)
                    time.sleep(self._action_interval)
                    continue
                pos = self._expand_channel_btn.coord()
                logger.info("展开渠道面板 @ ({}, {}) score={:.2f}",
                            pos[0], pos[1], self._expand_channel_btn._match_score)
                self._adb.click(*self._res.to_real(*pos))
                time.sleep(self._panel_delay)
                continue

            # 面板已展开且定位到目标条目 → 点击
            x, y, w, h, score = match
            click_pos = (x + w // 2, y + h // 2)
            logger.info("点击渠道「{}」@ ({}, {}) score={:.2f}",
                        target_type, click_pos[0], click_pos[1], score)
            self._adb.click(*self._res.to_real(*click_pos))
            time.sleep(self._page_delay)

            # 确认面板已收起：收起后该区域不再匹配到渠道条目
            after = self._capture_screenshot()
            if after is None or btn.match(after) is None:
                logger.info("渠道「{}」切换生效，面板已收起", target_type)
                return True
            logger.warning("点击后目标条目仍可见，面板可能未收起（第 {} 次）", attempt)
            time.sleep(self._action_interval)

        logger.error("切换渠道「{}」失败（已尝试 {} 次）", target_type, self._max_retries)
        return False

    # ── 单页扫描 ──────────────────────────────────────

    def _scan_page(self, img: np.ndarray) -> list[GachaRecord]:
        """扫描单页，返回该页 10 行里解析出的记录（从上到下 = 由新到旧）"""
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

        # 如果 OCR 全部返回空（可能是子进程超时），重试一次
        if all(not r for r in all_results):
            logger.warning("OCR 返回全空结果，可能是子进程超时，重试一次...")
            try:
                all_results = self._ocr.recognize_page(img_cropped, regions_y)
            except Exception as e:
                logger.error("OCR 重试失败: {}", e)
                return records

        # 逐行生成记录
        # 页内从上到下（row 0 → 9）= 由新到旧。配合"第 1 页→末页"的扫描方向，
        # 收集顺序就是全局的"新→旧"，最后统一倒序编号即可拿到"旧→新"
        for i in range(10):
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
                    time_text = " ".join(r["text"] for r in ocr_results if r.get("text"))
                    pull_time = self._parser._extract_time(time_text) or datetime.now()
                    record = GachaRecord(
                        character_name=name, rarity=Rarity(rarity) if rarity else Rarity.FINE,
                        pull_time=pull_time,
                        banner_name=self._current_banner_name,
                        banner_type=self._current_banner_type,
                    )

            if record is not None:
                record.text_hash = _compute_text_hash(ocr_results)
                records.append(record)

        # 时间没识别出来的行，解析器会用 datetime.now() 兜底，这个值每次扫描都不同，
        # 会让内容键漂移 → 同一条记录被反复当成新记录。
        # 记录页是按时间排好序的（页内从上到下 = 由新到旧），所以失效行有两个回填来源：
        #   1. 上方最近一条已知时间（同页更新的那条）
        #   2. 上方全都没有时（页首无锚点），用下方最近一条已知时间（同页更旧的那条）
        # 跨页时用 _last_known_time 续上，保证多次扫描算出一致的内容键。
        last = self._last_known_time
        for record in records:
            if record.pull_time.microsecond:
                # 微秒非 0 = 来自 datetime.now() 兜底（OCR 解析出的时间只到"分"）
                if last is not None:
                    logger.debug("时间未识别，沿用上一条时间 {}: {}",
                                 last.strftime("%m-%d %H:%M"), record.character_name)
                    record.pull_time = last
            else:
                last = record.pull_time

        # 兜底第二步：上方没有任何已知时间的失效行（页首连续失败），改用下方最近一条
        # 已知时间回填。仍然补不上的（整页都没识别出时间）保持原样，
        # 交给 scan_all 的不入库过滤拦下。
        nxt: Optional[datetime] = None
        for record in reversed(records):
            if record.pull_time.microsecond:
                if nxt is not None:
                    logger.debug("页首时间未识别，改用下方时间 {}: {}",
                                 nxt.strftime("%m-%d %H:%M"), record.character_name)
                    record.pull_time = nxt
            else:
                nxt = record.pull_time

        if last is not None:
            self._last_known_time = last

        logger.debug("页扫描完成: {} 条有效记录", len(records))
        return records

    # ── 截图 ────────────────────────────────────────────

    def _capture_screenshot(self) -> Optional[np.ndarray]:
        img = self._adb.screenshot_validate()
        if img is None:
            img = self._screenshot.capture_as_array()
        if img is not None:
            img = self._res.resize_screenshot(img)
        return img

    # ── 翻页 ──────────────────────────────────────────

    def _next_page(self, before_img: np.ndarray) -> bool:
        """点击"下一页"，并用表格区像素差分判断是否真的翻过去了

        匹配不到"下一页"按钮时绝不做盲点击：
          - 还能认出召集记录页 → 按钮多半是置灰了，判定为最后一页，正常结束
          - 所有页面模板都匹配不上 → 当前界面未知，写入 _abort_reason 让上层安全停机

        Returns:
            True  = 内容已变化（翻到了下一页）
            False = 未翻页（最后一页，或安全停机 —— 见 self._abort_reason）
        """
        before_area = self._extract_record_area(before_img)
        click_pos = self._find_next_button(before_img)
        if click_pos is None:
            if self._detector.detect(before_img) == GamePage.UNKNOWN:
                self._abort_reason = "所有页面模板都匹配不上，当前界面未知"
            else:
                logger.info("下一页按钮未匹配到，但仍能认出召集记录页 → 判定为最后一页")
            return False

        self._adb.click(*self._res.to_real(*click_pos))
        time.sleep(self._page_delay)
        after_img = self._capture_screenshot()
        if after_img is None:
            return False
        after_area = self._extract_record_area(after_img)
        if self._content_changed(before_area, after_area):
            logger.info("下一页: 内容已变化")
            return True
        logger.info("下一页: 内容未变化，已到最后一页")
        return False

    @staticmethod
    def _extract_record_area(img: np.ndarray) -> np.ndarray:
        return img[218:551, :]

    def _find_next_button(self, img: np.ndarray) -> Optional[tuple[int, int]]:
        """定位"下一页"按钮，返回设计分辨率坐标；模板匹配不上返回 None

        匹配不上时由调用方 _next_page 决定是"到末页了"还是"界面异常要停机"，
        这里不做任何兜底点击。
        """
        if self._next_page_btn.file:
            match_result = self._next_page_btn.match(img)
            if match_result:
                x, y, btn_w, btn_h, score = match_result
                logger.debug("下一页按钮 @ ({},{}) score={:.2f}", x + btn_w // 2, y + btn_h // 2, score)
                return (x + btn_w // 2, y + btn_h // 2)
            logger.warning("下一页按钮模板匹配失败 (score={:.3f} < {:.2f})",
                           self._next_page_btn._match_score, self._next_page_btn.similarity)
        return None

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
