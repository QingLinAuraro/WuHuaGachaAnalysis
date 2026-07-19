"""
抽卡记录数据模型
"""

from dataclasses import dataclass
from datetime import datetime
from enum import IntEnum
import hashlib


class Rarity(IntEnum):
    """器者稀有度（物华弥新）"""
    SPECIAL = 5   # 特出（红卡 / 5★）
    EXCELLENT = 4 # 优异（黄卡 / 4★）
    FINE = 3      # 新生（蓝卡 / 3★）
    COMMON = 2    # 普通
    BASIC = 1     # 基础


class BannerType(str):
    """卡池类型常量"""
    EVENT = "event"
    LIMITED_TIME = "限时"
    LIMITED = "限定"
    STANDARD = "standard"
    NEWBIE = "newbie"
    UNKNOWN = "unknown"


@dataclass
class GachaRecord:
    """单条抽卡记录"""

    character_name: str          # 器者名称
    rarity: Rarity               # 稀有度
    pull_time: datetime          # 抽取时间
    banner_name: str = ""        # 卡池名称
    banner_type: str = BannerType.UNKNOWN  # 卡池类型
    pull_number: int = 0         # 在该卡池中的第几抽
    record_id: str = ""          # 唯一标识（自动生成）
    account_id: int = 0          # 所属账户ID
    pull_date: str = ""          # 出货日期 (月-日格式缓存，方便UI)
    content_hash: str = ""       # OCR 内容哈希（含行号，record_id用）
    text_hash: str = ""          # OCR 文本哈希（不含行号，跨扫描去重用）

    def __post_init__(self) -> None:
        if not self.record_id:
            self.record_id = self._generate_id()
        if not self.pull_date:
            self.pull_date = self.pull_time.strftime("%m-%d")

    def _generate_id(self) -> str:
        """基于内容生成唯一ID，不含 pull_number（会变化），含 content_hash 区分同分同角色"""
        raw = (f"{self.character_name}_{self.rarity.value}_"
               f"{self.pull_time.isoformat()}_{self.banner_name}_"
               f"{self.account_id}_{self.content_hash}")
        return hashlib.md5(raw.encode()).hexdigest()[:12]

    def to_dict(self) -> dict:
        return {
            "character_name": self.character_name,
            "rarity": self.rarity.value,
            "pull_time": self.pull_time.isoformat(),
            "banner_name": self.banner_name,
        }

    def to_dict_full(self) -> dict:
        """完整导出（调试用）"""
        return {
            "record_id": self.record_id,
            "character_name": self.character_name,
            "rarity": self.rarity.value,
            "rarity_name": self.rarity.name,
            "pull_time": self.pull_time.isoformat(),
            "banner_name": self.banner_name,
            "banner_type": self.banner_type,
            "pull_number": self.pull_number,
            "account_id": self.account_id,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "GachaRecord":
        return cls(
            record_id=data.get("record_id", ""),
            character_name=data["character_name"],
            rarity=Rarity(data["rarity"]),
            pull_time=datetime.fromisoformat(data["pull_time"]),
            banner_name=data.get("banner_name", ""),
            banner_type=data.get("banner_type", BannerType.UNKNOWN),
            pull_number=data.get("pull_number", 0),
            account_id=data.get("account_id", 0),
        )
