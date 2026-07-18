"""
抽卡记录数据模型
"""

from dataclasses import dataclass
from datetime import datetime
from enum import IntEnum
from typing import Optional
import hashlib
import json


class Rarity(IntEnum):
    """器者稀有度（物华弥新）"""
    SPECIAL = 5   # 特出（红卡 / 5★）
    EXCELLENT = 4 # 优异（黄卡 / 4★）
    FINE = 3      # 新生（蓝卡 / 3★）
    # 可能还有更低的，按需扩展
    COMMON = 2    # 普通
    BASIC = 1     # 基础


class BannerType(str):
    """卡池类型常量"""
    EVENT = "event"             # 活动招募（通用）
    LIMITED_TIME = "限时"        # 限时卡池
    LIMITED = "限定"             # 限定卡池
    STANDARD = "standard"       # 常规招募
    NEWBIE = "newbie"           # 新人招募
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
        """基于关键字段生成唯一ID，含 pull_number 防止同页重复器者碰撞"""
        raw = f"{self.character_name}_{self.rarity.value}_{self.pull_time.isoformat()}_{self.banner_name}_{self.pull_number}"
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
