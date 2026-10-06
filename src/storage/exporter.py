"""
数据导出模块
支持 JSON 文件导出 / 导入（含账户支持）
"""

import json
from pathlib import Path
from datetime import datetime
from typing import Optional

from loguru import logger

from src.models.gacha_record import (
    GachaRecord, make_record_id, make_record_key, make_dedup_key,
)
from src.storage.database import get_db
from src.config import config


def export_to_json(
    output_path: Optional[str] = None,
    account_id: Optional[int] = None,
    banner_name: Optional[str] = None,
) -> str:
    """
    导出抽卡记录为 JSON 文件，按倒序（最新在前）
    返回导出文件的路径
    """
    records = get_db().get_all_records(account_id=account_id, banner_name=banner_name,
                                 order_by="pull_number")
    records.reverse()  # 最新在前

    data = {
        "export_time": datetime.now().isoformat(),
        "app_version": __import__("src").__version__,
        "account_id": account_id,
        "total_count": len(records),
        "records": [r.to_dict_full() for r in records],
    }

    if output_path is None:
        exports_dir = config.data_root / "exports"
        exports_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = str(exports_dir / f"gacha_export_{timestamp}.json")

    output_path = str(Path(output_path).resolve())
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    return output_path


def import_from_json(file_path: str, account_id: int = 0) -> int:
    """
    从 JSON 文件导入抽卡记录
    account_id: 导入到的目标账户（0=不指定）
    返回导入的新记录数量

    record_id 与扫描器用同一套规则（内容键 + 出现序号 + 角色名，
    序号以该组最新那条为基准）；
    存在性按 (内容键, seq, 角色名) 三元组对齐，所以同一个文件重复导入不会重复计入。
    """
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # 建"已入库三元组"集合，与扫描器同一套逻辑（见 gacha_scanner.scan_all）。
    # seq 由组内时间降序名次还原（第 0 条 = 该组最新那条），不用 pull_number
    # —— 那是全库编号，每次入库都会整体重排。
    # 跳过微秒非 0 的老记录（旧 now() 兜底产物，内容键不可靠，不参与判重；
    # 记录本身保留不动，界面照常显示）。
    existing = get_db().get_all_records(account_id=account_id)
    by_group: dict[str, list] = {}
    for r in existing:
        if r.pull_time.microsecond:
            continue
        by_group.setdefault(make_record_key(r), []).append(r)
    db_keys: set = set()
    for key, recs in by_group.items():
        # 组内按"新 → 旧"：同一分钟的 pull_time 完全相同，靠 pull_number 才能
        # 排出来（它是按 (时间, 组内顺序号) 全局重编过的，升序 = 旧→新）。
        # 不能按 record_id 排 —— 那是 md5 哈希，会把顺序随机打乱。
        recs.sort(key=lambda x: (x.pull_time, x.pull_number or 0), reverse=True)
        for seq, r in enumerate(recs):
            db_keys.add((key, seq, r.character_name))

    count = 0
    skipped_time = 0

    # 先过滤 + 按内容键分组。seq 用"距该组最新那条的偏移"（最新 = 0），
    # 与扫描器完全一致 —— 否则同一份数据"扫描入库"和"导入入库"会算出不同
    # record_id，两边互相认不出来，变成重复记录。
    # JSON 由 export_to_json 按 pull_number 升序再 reverse 导出，即全局"新→旧"，
    # 所以组内按出现顺序编号即得"距最新偏移"。
    groups: dict[str, list[GachaRecord]] = {}
    for item in data.get("records", []):
        record = GachaRecord.from_dict(item)
        if account_id:
            record.account_id = account_id
        # 时间未识别出来（now() 兜底，微秒非 0）的记录内容键会漂移，导入就是重复
        if record.pull_time.microsecond:
            skipped_time += 1
            continue
        groups.setdefault(make_record_key(record), []).append(record)

    for key, recs in groups.items():
        # recs 按 JSON 出现顺序（新→旧），依次得 seq = 0, 1, 2, ...
        for seq, record in enumerate(recs):
            if make_dedup_key(record, seq) in db_keys:
                continue  # 这条已经在库里了
            record.record_id = make_record_id(record, seq)
            # 顺序号一并落库，否则同分钟的多条导入后排不出先后
            record.seq_no = seq
            if get_db().add_record(record):
                count += 1
    if skipped_time:
        logger.warning("[导入] 跳过 {} 条时间未识别的记录（避免重复计入）", skipped_time)

    # 导入的记录时间可能比库内已有的更早 → 按真实抽取顺序重编 pull_number，
    # 否则 UI 按 pull_number 排序时这些记录会跑到最新之后
    if count:
        _resequence(account_id)
    return count


def _resequence(account_id: int = 0) -> None:
    """按 (pull_time, -seq_no) 重编 pull_number（与扫描器同一规则）

    排序键不能是 record_id —— 那是 md5 哈希，同分钟的多条会被随机打乱，
    表现为"实际第 10 抽被算成第 1 抽"。seq_no 是扫描/导入时按真实页序算出的
    组内偏移（0 = 该组最新），倒序即"旧 → 新"。
    """
    records = get_db().get_all_records(account_id=account_id)
    if not records:
        return
    records.sort(key=lambda r: (r.pull_time, -(r.seq_no or 0)))
    pairs = [(r.record_id, i) for i, r in enumerate(records, start=1)
             if r.pull_number != i]
    if pairs:
        n = get_db().set_pull_numbers(pairs)
        logger.info("[导入] 已按真实抽取顺序重编 pull_number（{} 条）", n)
