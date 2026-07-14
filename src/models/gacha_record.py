"""
抽卡记录数据模型
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import IntEnum
from typing import Optional
import hashlib
import json


class Rarity(IntEnum):
    """器者稀有度（物华弥新）"""
    SPECIAL = 5   # 特出（红卡 / 5★）
    EXCELLENT = 4 # 优异（黄卡 / 4★）
    FINE = 3      # 精良（蓝卡 / 3★）
    # 可能还有更低的，按需扩展
    COMMON = 2    # 普通
    BASIC = 1     # 基础


class BannerType(str):
    """卡池类型常量"""
    EVENT = "event"             # 活动招募
    STANDARD = "standard"       # 常规招募
    NEWBIE = "newbie"           # 新人招募
    COLLECTION = "collection"   # 器者征集
    UNKNOWN = "unknown"         # 未知


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

    def __post_init__(self) -> None:
        if not self.record_id:
            self.record_id = self._generate_id()

    def _generate_id(self) -> str:
        """基于关键字段生成唯一ID"""
        raw = f"{self.character_name}_{self.rarity.value}_{self.pull_time.isoformat()}_{self.banner_name}"
        return hashlib.md5(raw.encode()).hexdigest()[:12]

    def to_dict(self) -> dict:
        return {
            "record_id": self.record_id,
            "character_name": self.character_name,
            "rarity": self.rarity.value,
            "rarity_name": self.rarity.name,
            "pull_time": self.pull_time.isoformat(),
            "banner_name": self.banner_name,
            "banner_type": self.banner_type,
            "pull_number": self.pull_number,
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
        )


@dataclass
class GachaBanner:
    """卡池信息"""
    name: str                    # 卡池名称
    banner_type: str             # 卡池类型
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    pity_count: int = 70         # 保底抽数（物华弥新通常是70抽保底）
    rate_up_characters: list = field(default_factory=list)  # UP角色列表
