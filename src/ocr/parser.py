"""
OCR 结果解析器
将 OCR 识别的原始文本解析为结构化的抽卡记录
"""

import re
from datetime import datetime
from typing import Optional

from loguru import logger

from src.models.gacha_record import GachaRecord, Rarity, BannerType


class GachaRecordParser:
    """
    抽卡记录 OCR 结果解析器

    物华弥新召集记录每条通常包含：
    - 器者名称（中文，如"万工轿"、"T型帛画"）
    - 稀有度标识（红/黄/蓝，对应 特出/优异/精良）
    - 抽取时间（如 "2025-01-15 14:30:00"）
    - 卡池名称
    """

    # 常见时间格式正则
    TIME_PATTERNS = [
        # "2025年01月15日14时30分" — 物华弥新实际格式
        re.compile(r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日\s*(\d{1,2})\s*时\s*(\d{1,2})\s*分"),
        # "2025-01-15 14:30:00" — 备选
        re.compile(r"(\d{4}[-/]\d{1,2}[-/]\d{1,2}\s+\d{1,2}:\d{2}(:\d{2})?)"),
    ]

    # 稀有度关键词
    RARITY_KEYWORDS = {
        "特出": Rarity.SPECIAL,
        "优异": Rarity.EXCELLENT,
        "新生": Rarity.FINE,
    }

    def __init__(self, banner_name: str = "") -> None:
        self.banner_name = banner_name
        self.banner_type = BannerType.UNKNOWN

    def set_banner(self, name: str, banner_type: str = BannerType.UNKNOWN) -> None:
        """设置当前扫描的卡池信息"""
        self.banner_name = name
        self.banner_type = banner_type

    def parse_record_from_texts(
        self,
        texts: list[str],
        pull_number: int = 0,
    ) -> Optional[GachaRecord]:
        """
        从一组 OCR 识别文本中解析出一条抽卡记录

        Args:
            texts: OCR 识别出的所有文本行
            pull_number: 在该卡池中的序号

        Returns:
            GachaRecord 或 None（解析失败）
        """
        # 合并所有文本
        full_text = " ".join(texts)

        character_name = self._extract_character_name(texts)
        rarity = self._extract_rarity(texts)
        pull_time = self._extract_time(full_text)

        # 提取卡池名称（召集列：限时/卡池名 或 限定/卡池名）
        banner_from_ocr = self._extract_banner(texts)
        if banner_from_ocr:
            self.banner_name = banner_from_ocr
            self.banner_type = BannerType.EVENT  # 限时/限定都属于活动卡池

        if not character_name or rarity is None:
            logger.debug("解析失败 - 文本: {}", texts)
            return None

        # 如果没有识别到时间，使用当前时间
        if pull_time is None:
            pull_time = datetime.now()
            logger.debug("未识别到时间信息，使用当前时间")

        return GachaRecord(
            character_name=character_name,
            rarity=rarity,
            pull_time=pull_time,
            banner_name=self.banner_name,
            banner_type=self.banner_type,
            pull_number=pull_number,
        )

    def parse_records_batch(
        self,
        all_texts: list[list[str]],
    ) -> list[GachaRecord]:
        """
        批量解析多条记录

        Args:
            all_texts: 每组是一条记录的文本列表

        Returns:
            解析成功的 GachaRecord 列表
        """
        records = []
        for i, texts in enumerate(all_texts):
            record = self.parse_record_from_texts(texts, pull_number=i + 1)
            if record:
                records.append(record)
        logger.info("批量解析完成: {} 条成功 / {} 条输入", len(records), len(all_texts))
        return records

    def _extract_character_name(self, texts: list[str]) -> Optional[str]:
        """
        从文本行中提取器者名称

        物华弥新召集记录为四列表格：稀有度 | 器者 | 召集 | 时间
        OCR 识别的文本通常按从左到右、从上到下排列
        如果有4条文本，第2条（索引1）就是器者名称
        """
        # 策略1：恰好4条文本 — 按表格列顺序，取第2列
        if len(texts) == 4:
            name = texts[1].strip()
            # 过滤掉明显不是名称的内容
            if len(name) >= 1 and not re.match(r"^\d+$", name):
                return name

        # 策略2：从所有文本中找最长且合理的名称
        best_name = ""
        best_len = 0
        for text in texts:
            cleaned = re.sub(r"[^\u4e00-\u9fffA-Za-z0-9·]", "", text.strip())
            if len(cleaned) >= 2 and len(cleaned) > best_len:
                if not re.match(r"^\d{2,}$", cleaned):
                    if not re.match(r"\d{4}[-/年]", cleaned):
                        # 排除稀有度关键词
                        if cleaned not in ("特出", "优异", "新生"):
                            best_name = cleaned
                            best_len = len(cleaned)

        return best_name if best_name else None

    def _extract_rarity(self, texts: list[str]) -> Optional[Rarity]:
        """从文本中提取稀有度信息"""
        full = " ".join(texts)
        for keyword, rarity in self.RARITY_KEYWORDS.items():
            if keyword in full:
                return rarity
        return None

    def _extract_banner(self, texts: list[str]) -> Optional[str]:
        """
        从文本中提取卡池名称
        物华弥新格式：召集列为 "限时/卡池名" 或 "限定/卡池名"
        """
        for text in texts:
            text = text.strip()
            # 匹配 "限时/XXX" 或 "限定/XXX" 格式
            if "/" in text and len(text) >= 3:
                # 取 "/" 后的卡池名称
                parts = text.split("/", 1)
                if len(parts) == 2 and parts[1]:
                    return parts[1].strip()
                return text.strip()
            # 直接匹配 "限时" 或 "限定" 开头
            if text.startswith(("限时", "限定")) and len(text) > 2:
                return text[2:].strip()
        return None

    def _extract_time(self, text: str) -> Optional[datetime]:
        """从文本中提取时间"""
        for pattern in self.TIME_PATTERNS:
            match = pattern.search(text)
            if match:
                groups = match.groups()
                # 格式1: "2025年01月15日14时30分" → groups = (2025, 01, 15, 14, 30)
                if len(groups) == 5 and groups[4] is not None:
                    try:
                        return datetime(
                            int(groups[0]), int(groups[1]), int(groups[2]),
                            int(groups[3]), int(groups[4]),
                        )
                    except ValueError:
                        pass
                # 格式2: "2025-01-15 14:30:00" 或 "2025-01-15 14:30"
                time_str = match.group(1)
                for fmt in [
                    "%Y-%m-%d %H:%M:%S",
                    "%Y-%m-%d %H:%M",
                    "%Y/%m/%d %H:%M:%S",
                    "%Y/%m/%d %H:%M",
                ]:
                    try:
                        return datetime.strptime(time_str, fmt)
                    except ValueError:
                        continue
        return None
