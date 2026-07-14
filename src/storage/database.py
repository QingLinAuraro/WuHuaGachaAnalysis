"""
数据库操作模块
使用 SQLAlchemy ORM 管理 SQLite 数据库
"""

import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from sqlalchemy import (
    create_engine, Column, Integer, String, DateTime, Enum, Index
)
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from src.models.gacha_record import GachaRecord, Rarity, BannerType
from src.config import config


# ── ORM 模型 ────────────────────────────────────────────

class Base(DeclarativeBase):
    pass


class GachaRecordORM(Base):
    """抽卡记录 ORM 表"""
    __tablename__ = "gacha_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    record_id = Column(String(32), unique=True, nullable=False, index=True)
    character_name = Column(String(64), nullable=False)
    rarity = Column(Integer, nullable=False)  # Rarity 枚举值
    pull_time = Column(DateTime, nullable=False)
    banner_name = Column(String(128), default="")
    banner_type = Column(String(32), default=BannerType.UNKNOWN)
    pull_number = Column(Integer, default=0)

    __table_args__ = (
        Index("idx_banner_time", "banner_name", "pull_time"),
        Index("idx_rarity", "rarity"),
    )

    def to_record(self) -> GachaRecord:
        return GachaRecord(
            record_id=self.record_id,
            character_name=self.character_name,
            rarity=Rarity(self.rarity),
            pull_time=self.pull_time,
            banner_name=self.banner_name,
            banner_type=self.banner_type,
            pull_number=self.pull_number,
        )

    @classmethod
    def from_record(cls, record: GachaRecord) -> "GachaRecordORM":
        return cls(
            record_id=record.record_id,
            character_name=record.character_name,
            rarity=record.rarity.value,
            pull_time=record.pull_time,
            banner_name=record.banner_name,
            banner_type=record.banner_type,
            pull_number=record.pull_number,
        )


# ── 数据库管理器 ──────────────────────────────────────

class Database:
    """SQLite 数据库管理器"""

    def __init__(self, db_path: Optional[str] = None) -> None:
        db_path = db_path or config.get("database.path")
        db_dir = Path(db_path).parent
        db_dir.mkdir(parents=True, exist_ok=True)

        self._engine = create_engine(f"sqlite:///{db_path}", echo=False)
        self._Session = sessionmaker(bind=self._engine)
        Base.metadata.create_all(self._engine)

    @property
    def session(self) -> Session:
        return self._Session()

    def add_record(self, record: GachaRecord) -> bool:
        """添加一条抽卡记录（去重）"""
        with self.session as s:
            existing = s.query(GachaRecordORM).filter_by(
                record_id=record.record_id
            ).first()
            if existing:
                return False  # 已存在，跳过
            s.add(GachaRecordORM.from_record(record))
            s.commit()
            return True

    def add_records(self, records: list[GachaRecord]) -> int:
        """批量添加抽卡记录，返回新增数量"""
        count = 0
        with self.session as s:
            for record in records:
                existing = s.query(GachaRecordORM).filter_by(
                    record_id=record.record_id
                ).first()
                if not existing:
                    s.add(GachaRecordORM.from_record(record))
                    count += 1
            s.commit()
        return count

    def get_all_records(
        self,
        banner_name: Optional[str] = None,
        rarity: Optional[int] = None,
        limit: int = 0,
        offset: int = 0,
    ) -> list[GachaRecord]:
        """查询抽卡记录，支持筛选和分页"""
        with self.session as s:
            q = s.query(GachaRecordORM)
            if banner_name:
                q = q.filter(GachaRecordORM.banner_name == banner_name)
            if rarity is not None:
                q = q.filter(GachaRecordORM.rarity == rarity)
            q = q.order_by(GachaRecordORM.pull_time.desc())
            if offset:
                q = q.offset(offset)
            if limit:
                q = q.limit(limit)
            return [orm.to_record() for orm in q.all()]

    def get_record_count(self, banner_name: Optional[str] = None) -> int:
        """获取记录总数"""
        with self.session as s:
            q = s.query(GachaRecordORM)
            if banner_name:
                q = q.filter(GachaRecordORM.banner_name == banner_name)
            return q.count()

    def get_rarity_counts(self, banner_name: Optional[str] = None) -> dict[int, int]:
        """统计各稀有度数量"""
        with self.session as s:
            q = s.query(
                GachaRecordORM.rarity,
                __import__("sqlalchemy").func.count(GachaRecordORM.id)
            )
            if banner_name:
                q = q.filter(GachaRecordORM.banner_name == banner_name)
            q = q.group_by(GachaRecordORM.rarity)
            return {rarity: count for rarity, count in q.all()}

    def get_banner_names(self) -> list[str]:
        """获取所有卡池名称"""
        with self.session as s:
            results = s.query(GachaRecordORM.banner_name).distinct().all()
            return [r[0] for r in results if r[0]]

    def clear_all(self) -> int:
        """清空所有记录，返回删除数量"""
        with self.session as s:
            count = s.query(GachaRecordORM).count()
            s.query(GachaRecordORM).delete()
            s.commit()
            return count


# 全局数据库实例
db = Database()
