"""
数据导出模块
支持 JSON 文件导出 / 导入（含账户支持）
"""

import json
from pathlib import Path
from datetime import datetime
from typing import Optional

from src.models.gacha_record import GachaRecord
from src.storage.database import db


def export_to_json(
    output_path: Optional[str] = None,
    account_id: Optional[int] = None,
    banner_name: Optional[str] = None,
) -> str:
    """
    导出抽卡记录为 JSON 文件
    返回导出文件的路径
    """
    records = db.get_all_records(account_id=account_id, banner_name=banner_name)

    data = {
        "export_time": datetime.now().isoformat(),
        "app_version": __import__("src").__version__,
        "account_id": account_id,
        "total_count": len(records),
        "records": [r.to_dict_full() for r in records],
    }

    if output_path is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = f"gacha_export_{timestamp}.json"

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

    records = [GachaRecord.from_dict(item) for item in data.get("records", [])]
    if account_id:
        for r in records:
            r.account_id = account_id
            r.record_id = r._generate_id()  # 重新生成ID防止冲突
    return db.add_records(records)
