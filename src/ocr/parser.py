"""
OCR 结果解析器
将 OCR 识别的原始文本解析为结构化的抽卡记录
"""

import re
from datetime import datetime
from difflib import SequenceMatcher
from src.config import config
from typing import Optional

import yaml
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
        # OCR容错: "日"可能被误识别为"8"，如"2025年01月15814时30分"
        re.compile(r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*[日8]\s*(\d{1,2})\s*时\s*(\d{1,2})\s*分"),
        # OCR容错: 日字完全丢失，如"2025年01月15 14时30分"
        re.compile(r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\D+(\d{1,2})\s*时\s*(\d{1,2})\s*分"),
        # "2025-01-15 14:30:00" — 备选
        re.compile(r"(\d{4}[-/]\d{1,2}[-/]\d{1,2}\s+\d{1,2}:\d{2}(:\d{2})?)"),
    ]


    def __init__(self, banner_name: str = "") -> None:
        self.banner_name = banner_name
        self.banner_type = BannerType.UNKNOWN
        self._char_names: list[str] = []
        self._banner_names: list[str] = []
        self._banner_up: dict[str, str] = {}  # 卡池名 → UP 角色
        self._name_to_rarity: dict[str, Rarity] = {}  # 器者名 → 稀有度
        self._load_name_dict()

    def set_banner(self, name: str, banner_type: str = BannerType.UNKNOWN) -> None:
        """设置当前扫描的卡池信息"""
        self.banner_name = name
        self.banner_type = banner_type

    def lookup_rarity(self, character_name: str) -> Optional[Rarity]:
        """从词库查找器者稀有度（已纠错后的名称）"""
        return self._name_to_rarity.get(character_name)

    # ── 词库加载与模糊匹配 ──────────────────────────

    # 稀有度关键词 → Rarity 枚举
    _RARITY_MAP = {
        "特出": Rarity.SPECIAL,
        "优异": Rarity.EXCELLENT,
        "新生": Rarity.FINE,
    }

    def _load_name_dict(self) -> None:
        """加载器者名称和卡池名称词库，同时构建名称→稀有度映射"""
        names_path = config.resource_root / "config" / "names.yaml"
        if not names_path.exists():
            logger.warning("词库文件不存在: {}", names_path)
            return
        try:
            with open(names_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
            if data:
                chars = data.get("characters", {})
                self._char_names = []
                self._name_to_rarity = {}
                if isinstance(chars, dict):
                    for profession, rarities in chars.items():
                        if isinstance(rarities, dict):
                            for rarity_name, names_block in rarities.items():
                                rarity = self._RARITY_MAP.get(rarity_name, Rarity.FINE)
                                for name in self._extract_names(names_block):
                                    self._char_names.append(name)
                                    self._name_to_rarity[name] = rarity
                banners_raw = data.get("banners", {})
                if isinstance(banners_raw, dict):
                    self._banner_up = banners_raw
                    self._banner_names = list(banners_raw.keys())
                else:
                    self._banner_names = banners_raw
            logger.info("词库已加载: {} 个器者名称, {} 个卡池名称",
                        len(self._char_names), len(self._banner_names))
        except Exception as e:
            logger.warning("词库加载失败: {}", e)

    @staticmethod
    def _extract_names(node) -> list[str]:
        """递归提取所有名称，兼容任意嵌套层级（职业→稀有度→名称 等）"""
        if isinstance(node, str):
            return [n.strip() for n in node.split("\n") if n.strip()]
        if isinstance(node, list):
            return [n.strip() for n in node if n.strip()]
        if isinstance(node, dict):
            names = []
            for v in node.values():
                names.extend(GachaRecordParser._extract_names(v))
            return names
        return []

    @staticmethod
    def _fuzzy_match(text: str, candidates: list[str], threshold: float = 0.6) -> Optional[str]:
        """
        模糊匹配：在候选列表中找最相似的名称
        threshold: 相似度阈值（0~1），低于此值不返回
        """
        if not text or not candidates:
            return None
        text = text.strip()
        best_score = 0.0
        best_match = None
        for c in candidates:
            score = SequenceMatcher(None, text, c).ratio()
            if score > best_score:
                best_score = score
                best_match = c
        if best_score >= threshold and best_match:
            logger.debug("模糊匹配: '{}' -> '{}' (相似度: {:.2%})", text, best_match, best_score)
            return best_match
        return None

    # ── 基于列位置的解析 ──────────────────────

    # 三列在截图中的 x 比例范围（已裁剪稀有度列 x<420）
    # 新坐标系：原图 x-420，宽度=860
    COLUMN_RANGES = [
        ("name",   0   / 860, 330 / 860),   # 器者名称
        ("banner", 330 / 860, 500 / 860),   # 卡池
        ("time",   500 / 860, 830 / 860),   # 时间
    ]

    def parse_record_from_ocr_results(
        self,
        ocr_results: list[dict],
        img_width: int,
        pull_number: int = 0,
    ) -> Optional[GachaRecord]:
        """
        从 OCR 结果（含 box 坐标）中按列位置解析抽卡记录

        利用 EasyOCR 返回的 box 坐标，按 x 位置将文本归入四列，
        再分别提取各字段，避免因 OCR 文本顺序混乱导致的解析错误。

        Args:
            ocr_results: EasyOCR 返回的识别结果，
                         每项含 {"text", "confidence", "box"}
            img_width: 输入图片的宽度（像素），用于比例计算
            pull_number: 在该卡池中的序号

        Returns:
            GachaRecord 或 None
        """
        if not ocr_results:
            return None

        # 按 x 坐标归入各列（稀有度列已裁剪，不再读取）
        col_texts: dict[str, list[str]] = {
            "name": [], "banner": [], "time": []
        }

        for r in ocr_results:
            box = r["box"]
            xs = [p[0] for p in box]
            x_center = sum(xs) / len(xs)
            x_ratio = x_center / img_width

            for col_name, lo, hi in self.COLUMN_RANGES:
                if lo <= x_ratio <= hi:
                    col_texts[col_name].append(r["text"])
                    break

        name_str = " ".join(col_texts["name"])
        banner_str = " ".join(col_texts["banner"])
        time_str = " ".join(col_texts["time"])

        logger.debug(
            "列解析: 器者=[{}] 卡池=[{}] 时间=[{}]",
            name_str, banner_str, time_str,
        )

        # 名称（经词库纠错）→ 稀有度从 yaml 查
        character_name = self._extract_name_from_column(name_str)
        rarity = self.lookup_rarity(character_name) if character_name else None
        pull_time = self._extract_time(time_str)

        banner_from_ocr, pool_type = self._extract_banner_from_text(banner_str)
        if banner_from_ocr:
            self.banner_name = banner_from_ocr
            self.banner_type = pool_type or BannerType.EVENT

        if not character_name:
            logger.debug("列解析失败 - 器者=[{}]", name_str)
            return None

        if pull_time is None:
            pull_time = datetime.now()

        return GachaRecord(
            character_name=character_name,
            rarity=rarity or Rarity.FINE,
            pull_time=pull_time,
            banner_name=self.banner_name,
            banner_type=self.banner_type,
            pull_number=pull_number,
        )

    def _extract_banner_from_text(self, text: str) -> tuple:
        """从卡池列合并文本中提取 (卡池名称, 池类型)
        
        Returns:
            (banner_name, pool_type) 或 (None, None)
            pool_type: '限时' / '限定' / None
        """
        text = text.strip()
        if not text:
            return None, None

        pool_type = None
        raw_name = text

        if "/" in text and len(text) >= 3:
            parts = text.split("/", 1)
            prefix = parts[0].strip()
            raw_name = parts[1].strip() if len(parts) > 1 else text
            if "限时" in prefix:
                pool_type = BannerType.LIMITED_TIME
            elif "限定" in prefix:
                pool_type = BannerType.LIMITED
        elif text.startswith(("限时", "限定")) and len(text) > 2:
            if text.startswith("限时"):
                pool_type = BannerType.LIMITED_TIME
            else:
                pool_type = BannerType.LIMITED
            raw_name = text[2:].strip()
        else:
            # 纯卡池名，尝试词库匹配
            pass

        matched = self._fuzzy_match(raw_name, self._banner_names, threshold=0.5)
        banner_name = matched if matched else raw_name
        return banner_name, pool_type

    def _extract_name_from_column(self, text: str) -> Optional[str]:
        """从器者名称列合并文本中提取名称，并尝试词库纠错"""
        text = text.strip()
        if not text:
            return None
        # 去除干扰字符，保留中文、字母、数字、·
        cleaned = re.sub(r"[^\u4e00-\u9fffA-Za-z0-9·]", "", text)
        if len(cleaned) < 1:
            return None
        # 模糊匹配词库纠错
        matched = self._fuzzy_match(cleaned, self._char_names, threshold=0.5)
        return matched if matched else cleaned

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
