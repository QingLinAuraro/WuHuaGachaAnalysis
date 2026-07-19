"""
数据导出模块
支持 JSON 文件导出 / 导入（含账户支持）
"""

import json
from pathlib import Path
from datetime import datetime
from typing import Optional

from src.models.gacha_record import GachaRecord
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
    """
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    count = 0
    for item in data.get("records", []):
        record = GachaRecord.from_dict(item)
        if account_id:
            record.account_id = account_id
        # 用稳定字段重组 record_id，不依赖 content_hash
        t = record.pull_time
        tk = f"{t.year:04d}{t.month:02d}{t.day:02d}{t.hour:02d}{t.minute:02d}"
        raw = f"{record.character_name}_{record.rarity.value}_{tk}_{record.banner_name}_{record.account_id}_{record.pull_number}"
        import hashlib
        record.record_id = hashlib.md5(raw.encode()).hexdigest()[:12]
        if get_db().add_record(record):
            count += 1
    return count
