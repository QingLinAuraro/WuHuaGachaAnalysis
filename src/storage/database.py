"""
数据库操作模块
使用 SQLAlchemy ORM 管理 MySQL 数据库
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    create_engine, Column, Integer, String, DateTime, Index, ForeignKey, func,
)
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker, relationship
from loguru import logger

from src.models.gacha_record import GachaRecord, Rarity, BannerType
from src.config import config


# ── ORM 模型 ────────────────────────────────────────────

class Base(DeclarativeBase):
    pass


class AccountORM(Base):
    """账户表"""
    __tablename__ = "accounts"

    id = Column(Integer, primary_key=True, autoincrement=True, nullable=False)
    name = Column(String(64), unique=True, nullable=False)
    created_at = Column(DateTime, default=datetime.now, nullable=False)

    records = relationship("GachaRecordORM", back_populates="account",
                           cascade="all, delete-orphan")


class GachaRecordORM(Base):
    """抽卡记录 ORM 表"""
    __tablename__ = "gacha_records"

    id = Column(Integer, primary_key=True, autoincrement=True, nullable=False)
    record_id = Column(String(32), unique=True, nullable=False, index=True)
    character_name = Column(String(64), nullable=False)
    rarity = Column(Integer, nullable=False)  # Rarity 枚举值
    pull_time = Column(DateTime, nullable=False)
    banner_name = Column(String(128), default="")
    banner_type = Column(String(32), default=BannerType.UNKNOWN)
    pull_number = Column(Integer, default=0)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True, index=True)
    text_hash = Column(String(16), default="")  # OCR文本哈希（跨扫描稳定）

    account = relationship("AccountORM", back_populates="records")

    __table_args__ = (
        Index("idx_banner_time", "banner_name", "pull_time"),
        Index("idx_rarity", "rarity"),
        Index("idx_account_banner_time", "account_id", "banner_name", "pull_time"),
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
            account_id=self.account_id or 0,
            text_hash=self.text_hash or "",
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
            account_id=record.account_id if record.account_id else None,
            text_hash=record.text_hash or "",
        )


# ── 数据库管理器 ──────────────────────────────────────

class Database:
    """MySQL 数据库管理器"""

    DEFAULT_ACCOUNT_NAME = "默认"

    def __init__(self) -> None:
        host = config.get("database.host", "localhost")
        port = config.get("database.port", 3306)
        user = config.get("database.user", "root")
        password = config.get("database.password", "")
        db_name = config.get("database.name", "wuhua_gacha")
        charset = config.get("database.charset", "utf8mb4")

        url = (f"mysql+pymysql://{user}:{password}@{host}:{port}/"
               f"{db_name}?charset={charset}")
        self._engine = create_engine(
            url, echo=False,
            pool_pre_ping=True,      # 自动检测断连
            pool_recycle=3600,        # 每小时回收连接
        )
        self._Session = sessionmaker(bind=self._engine, expire_on_commit=False)

        self._init_db()

    def _init_db(self) -> None:
        """创建表并确保默认账户存在"""
        try:
            Base.metadata.create_all(self._engine)

            with self.session as s:
                default = s.query(AccountORM).filter_by(name=self.DEFAULT_ACCOUNT_NAME).first()
                if default is None:
                    default = AccountORM(name=self.DEFAULT_ACCOUNT_NAME)
                    s.add(default)
                    s.commit()
                    logger.info("已创建默认账户")
        except Exception as e:
            logger.warning("数据库初始化失败 (MySQL 未连接?): {}", e)

    @property
    def session(self) -> Session:
        return self._Session()

    # ── 账户管理 ──────────────────────────────────────

    def create_account(self, name: str) -> Optional[AccountORM]:
        """创建新账户，返回 AccountORM 或 None（重名时）"""
        name = name.strip()
        if not name:
            return None
        with self.session as s:
            existing = s.query(AccountORM).filter_by(name=name).first()
            if existing:
                return None
            account = AccountORM(name=name)
            s.add(account)
            s.commit()
            logger.info("已创建账户: {}", name)
            return account

    def list_accounts(self) -> list[AccountORM]:
        """列出所有账户（按创建时间排序）"""
        with self.session as s:
            return s.query(AccountORM).order_by(AccountORM.id.asc()).all()

    def get_account(self, account_id: int) -> Optional[AccountORM]:
        """按 ID 获取账户"""
        with self.session as s:
            return s.query(AccountORM).filter_by(id=account_id).first()

    def rename_account(self, account_id: int, new_name: str) -> bool:
        """重命名账户"""
        new_name = new_name.strip()
        if not new_name:
            return False
        with self.session as s:
            # 检查重名
            dup = s.query(AccountORM).filter(
                AccountORM.name == new_name,
                AccountORM.id != account_id,
            ).first()
            if dup:
                return False
            account = s.query(AccountORM).filter_by(id=account_id).first()
            if account is None:
                return False
            account.name = new_name
            s.commit()
            return True

    def delete_account(self, account_id: int) -> bool:
        """删除账户及其所有记录（级联）"""
        with self.session as s:
            account = s.query(AccountORM).filter_by(id=account_id).first()
            if account is None:
                return False
            if account.name == self.DEFAULT_ACCOUNT_NAME:
                logger.warning("不允许删除默认账户")
                return False
            s.delete(account)  # cascade 自动删除关联记录
            s.commit()
            logger.info("已删除账户: {} (ID={})", account.name, account_id)
            return True

    # ── 记录操作 ──────────────────────────────────────

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
        account_id: Optional[int] = None,
        banner_name: Optional[str] = None,
        rarity: Optional[int] = None,
        limit: int = 0,
        offset: int = 0,
        order_by: str = "pull_time",
    ) -> list[GachaRecord]:
        """查询抽卡记录，支持按账户筛选和分页"""
        with self.session as s:
            q = s.query(GachaRecordORM)
            if account_id is not None:
                q = q.filter(GachaRecordORM.account_id == account_id)
            if banner_name:
                q = q.filter(GachaRecordORM.banner_name == banner_name)
            if rarity is not None:
                q = q.filter(GachaRecordORM.rarity == rarity)
            if order_by == "pull_number":
                q = q.order_by(GachaRecordORM.pull_number.asc())
            else:
                q = q.order_by(GachaRecordORM.pull_time.desc())
            if offset:
                q = q.offset(offset)
            if limit:
                q = q.limit(limit)
            return [orm.to_record() for orm in q.all()]

    def get_record_count(
        self,
        account_id: Optional[int] = None,
        banner_name: Optional[str] = None,
    ) -> int:
        """获取记录总数"""
        with self.session as s:
            q = s.query(GachaRecordORM)
            if account_id is not None:
                q = q.filter(GachaRecordORM.account_id == account_id)
            if banner_name:
                q = q.filter(GachaRecordORM.banner_name == banner_name)
            return q.count()

    def get_rarity_counts(
        self,
        account_id: Optional[int] = None,
        banner_name: Optional[str] = None,
    ) -> dict[int, int]:
        """统计各稀有度数量"""
        with self.session as s:
            q = s.query(
                GachaRecordORM.rarity,
                func.count(GachaRecordORM.id)
            )
            if account_id is not None:
                q = q.filter(GachaRecordORM.account_id == account_id)
            if banner_name:
                q = q.filter(GachaRecordORM.banner_name == banner_name)
            q = q.group_by(GachaRecordORM.rarity)
            return {rarity: count for rarity, count in q.all()}

    def get_banner_names(
        self,
        account_id: Optional[int] = None,
    ) -> list[str]:
        """获取所有卡池名称"""
        with self.session as s:
            q = s.query(GachaRecordORM.banner_name)
            if account_id is not None:
                q = q.filter(GachaRecordORM.account_id == account_id)
            results = q.distinct().all()
            return [r[0] for r in results if r[0]]

    def clear_all(self, account_id: Optional[int] = None) -> int:
        """清空记录，返回删除数量"""
        with self.session as s:
            q = s.query(GachaRecordORM)
            if account_id is not None:
                q = q.filter(GachaRecordORM.account_id == account_id)
            count = q.count()
            q.delete()
            s.commit()
            return count


# 全局数据库实例
db = Database()
