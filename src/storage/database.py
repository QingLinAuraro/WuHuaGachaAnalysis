"""
数据库操作模块
使用 SQLAlchemy ORM 管理 SQLite 数据库
"""

import os
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path
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
    # 同分钟组内的顺序号（距该组最新那条的偏移，最新=0）。
    # 游戏的记录页时间只到"分"，同一分钟能出几十条，单靠 pull_time 无法排序；
    # 少了这一列就只能按 record_id 的哈希排，会把真实抽取顺序彻底打乱
    # （表现为"水晶杯明明是第 10 抽却被算成第 1 抽"）。
    seq_no = Column(Integer, default=0)

    account = relationship("AccountORM", back_populates="records")

    __table_args__ = (
        Index("idx_banner_time", "banner_name", "pull_time"),
        Index("idx_rarity", "rarity"),
        Index("idx_account_banner_time", "account_id", "banner_name", "pull_time"),
        Index("idx_order", "account_id", "pull_time", "seq_no"),
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
            seq_no=self.seq_no or 0,
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
            seq_no=record.seq_no,
        )


# ── 历史数据库迁移 ────────────────────────────────────
#
# 旧版本的 database.path 是相对路径（data/gacha.db），SQLAlchemy 按启动时的
# CWD 解析，于是同一个程序在不同目录下启动会读写到不同的库，仓库里能攒出好几个：
#   <根>/data/gacha.db
#   <根>/src/data/gacha.db
#   <根>/src/automation/pages/data/gacha.db
# 现在统一到绝对路径后，如果目标位置还没有库，就把"记录最多的那个历史库"
# 复制过来，避免用户升级后数据凭空消失。

_WALK_SKIP_DIRS = {
    ".venv", "venv", "env", "build", "dist", "node_modules",
    ".git", "__pycache__", ".idea", ".vscode", "site-packages",
}


def _find_legacy_dbs(roots: list[Path]) -> list[Path]:
    """在若干根目录下找所有 gacha.db（跳过依赖/构建目录）"""
    found: list[Path] = []
    seen: set[str] = set()
    for root in roots:
        if not root.exists():
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in _WALK_SKIP_DIRS]
            if "gacha.db" not in filenames:
                continue
            p = (Path(dirpath) / "gacha.db").resolve()
            key = str(p).lower()
            if key not in seen:
                seen.add(key)
                found.append(p)
    return found


def _count_records(db_file: Path) -> int:
    """只读统计一个库里的记录数；不是库/读不出来返回 -1"""
    try:
        con = sqlite3.connect(f"file:{db_file.as_posix()}?mode=ro", uri=True)
        try:
            return int(con.execute("select count(*) from gacha_records").fetchone()[0])
        finally:
            con.close()
    except Exception:
        return -1


def _migrate_legacy_db(target: Path) -> Optional[Path]:
    """目标库不存在时，把记录最多的历史库复制过去

    Returns:
        迁移来源路径；无需迁移/没找到可用历史库时返回 None
    """
    if target.exists():
        return None

    candidates: list[tuple[int, Path]] = []
    for p in _find_legacy_dbs([config.resource_root, config.data_root]):
        if p == target:
            continue
        n = _count_records(p)
        if n > 0:
            candidates.append((n, p))

    if not candidates:
        return None

    # 记录多的优先；条数相同取路径短的（更浅、更可能是主库）
    candidates.sort(key=lambda item: (-item[0], len(str(item[1]))))
    count, source = candidates[0]
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    logger.warning(
        "检测到历史数据库 {}（{} 条记录）→ 已迁移到 {}",
        source, count, target,
    )
    if len(candidates) > 1:
        logger.warning("另有 {} 个历史库未采用: {}",
                       len(candidates) - 1,
                       ", ".join(str(p) for _, p in candidates[1:]))
    return source


# ── 数据库管理器 ──────────────────────────────────────

class Database:
    """SQLite 数据库管理器"""

    DEFAULT_ACCOUNT_NAME = "默认"

    def __init__(self, db_path: Optional[str] = None) -> None:
        if db_path is None:
            path = config.database_path
        else:
            path = Path(db_path)
            if not path.is_absolute():
                # 显式传入的相对路径也按数据目录解析，不跟 CWD 走
                path = config.data_root / path
        self._db_path = path

        _migrate_legacy_db(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        self._engine = create_engine(f"sqlite:///{path.as_posix()}", echo=False)
        self._Session = sessionmaker(bind=self._engine, expire_on_commit=False)

        self._init_db()

    @property
    def path(self) -> Path:
        """数据库文件路径"""
        return self._db_path

    def _init_db(self) -> None:
        """创建表并确保默认账户存在"""
        Base.metadata.create_all(self._engine)
        self._ensure_columns()

        with self.session as s:
            default = s.query(AccountORM).filter_by(name=self.DEFAULT_ACCOUNT_NAME).first()
            if default is None:
                default = AccountORM(name=self.DEFAULT_ACCOUNT_NAME)
                s.add(default)
                s.commit()
                logger.info("已创建默认账户")

            # 修复旧记录 account_id 为 NULL 的情况
            nulls = s.query(GachaRecordORM).filter(
                GachaRecordORM.account_id == None
            ).count()
            if nulls > 0:
                s.query(GachaRecordORM).filter(
                    GachaRecordORM.account_id == None
                ).update({"account_id": default.id})
                s.commit()
                logger.info("已将 {} 条旧记录迁移到默认账户", nulls)

    def _ensure_columns(self) -> None:
        """给老库补上新增的列（只加列，不动数据）

        create_all() 只会建缺失的表，不会给已有的表加列 ——
        以后版本加字段时，没有这一步老用户升级会直接报 no such column。
        """
        table = GachaRecordORM.__tablename__
        with self._engine.connect() as conn:
            rows = conn.exec_driver_sql(f"PRAGMA table_info({table})").fetchall()
            if not rows:
                return  # 表刚建出来，列是全的
            have = {r[1] for r in rows}
            for col in GachaRecordORM.__table__.columns:
                if col.name in have:
                    continue
                try:
                    conn.exec_driver_sql(
                        f"ALTER TABLE {table} ADD COLUMN {col.name} {col.type}"
                    )
                    conn.commit()
                    logger.warning("数据库升级: 已补列 {}.{}", table, col.name)
                except Exception as e:
                    logger.error("数据库升级失败 {}.{}: {}", table, col.name, e)

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

    def set_pull_numbers(self, pairs: list[tuple[str, int]]) -> int:
        """批量更新 pull_number（按 record_id 定位），返回更新条数

        pull_number 只是排序键，中断补齐更旧的记录后需要全库重编，
        见 GachaScanner._resequence_numbers()。
        """
        if not pairs:
            return 0
        updated = 0
        with self.session as s:
            for record_id, number in pairs:
                row = s.query(GachaRecordORM).filter_by(record_id=record_id).first()
                if row is not None and row.pull_number != number:
                    row.pull_number = number
                    updated += 1
            s.commit()
        return updated

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
                # 「时间倒序 + 同分钟内顺序号倒序」= 严格的"新 → 旧"。
                # ⚠️ 不能只按 pull_time 排：同一分钟几十条的 pull_time 完全相同，
                #    SQLite 对相等的键不保证顺序，返回次序可能变，界面就会跳。
                #    同分钟内 seq_no 越小越新（0 = 最新），所以倒序即"新在前"。
                q = q.order_by(
                    GachaRecordORM.pull_time.desc(),
                    GachaRecordORM.seq_no.asc(),
                )
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


# 全局数据库实例（懒加载）
_db_instance = None


def get_db(db_path: str = None) -> "Database":
    """获取全局数据库实例（懒加载）"""
    global _db_instance
    if _db_instance is None:
        _db_instance = Database(db_path)
    return _db_instance
