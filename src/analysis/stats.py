"""
统计分析模块
计算抽卡数据的各项统计指标
"""

from collections import defaultdict
from datetime import datetime, timedelta
from typing import Optional

from src.models.gacha_record import GachaRecord, Rarity
from src.storage.database import db


class GachaStats:
    """抽卡统计分析器"""

    @staticmethod
    def total_pulls(banner_name: Optional[str] = None) -> int:
        """总抽数"""
        return db.get_record_count(banner_name=banner_name)

    @staticmethod
    def rarity_counts(banner_name: Optional[str] = None) -> dict[int, int]:
        """各稀有度数量统计 {稀有度值: 数量}"""
        return db.get_rarity_counts(banner_name=banner_name)

    @staticmethod
    def pity_count(banner_name: Optional[str] = None) -> int:
        """
        当前保底计数：距离上次抽到5★（特出）已经多少抽

        物华弥新保底规则：
        - 活动/常规招募: 70抽保底
        - 新人招募: 30抽保底（仅限新人）
        """
        records = db.get_all_records(banner_name=banner_name)
        if not records:
            return 0

        # 按时间升序排列
        records.sort(key=lambda r: r.pull_time)

        count = 0
        for record in reversed(records):
            if record.rarity == Rarity.SPECIAL:
                break
            count += 1

        return count

    @staticmethod
    def rate_5star(banner_name: Optional[str] = None) -> float:
        """五星（特出）出率"""
        total = db.get_record_count(banner_name=banner_name)
        if total == 0:
            return 0.0
        counts = db.get_rarity_counts(banner_name=banner_name)
        five_star = counts.get(Rarity.SPECIAL.value, 0)
        return five_star / total

    @staticmethod
    def rate_4star(banner_name: Optional[str] = None) -> float:
        """四星（优异）出率"""
        total = db.get_record_count(banner_name=banner_name)
        if total == 0:
            return 0.0
        counts = db.get_rarity_counts(banner_name=banner_name)
        four_star = counts.get(Rarity.EXCELLENT.value, 0)
        return four_star / total

    @staticmethod
    def average_pity_distance(banner_name: Optional[str] = None) -> float:
        """
        平均出5星所需抽数（平均保底距离）
        理论值约 62.5 抽（含软保底机制）
        """
        records = db.get_all_records(banner_name=banner_name)
        if not records:
            return 0.0

        records.sort(key=lambda r: r.pull_time)
        distances = []
        last_5star_idx = -1

        for i, record in enumerate(records):
            if record.rarity == Rarity.SPECIAL:
                if last_5star_idx >= 0:
                    distances.append(i - last_5star_idx)
                last_5star_idx = i

        if not distances:
            return 0.0
        return sum(distances) / len(distances)

    @staticmethod
    def pity_history(banner_name: Optional[str] = None) -> list[dict]:
        """
        保底历史记录
        返回每次出5★时的累计抽数和间隔

        Returns:
            [{pity_count, five_star_name, five_star_time}, ...]
        """
        records = db.get_all_records(banner_name=banner_name)
        if not records:
            return []

        records.sort(key=lambda r: r.pull_time)
        history = []
        count_since_last = 0

        for record in records:
            count_since_last += 1
            if record.rarity == Rarity.SPECIAL:
                history.append({
                    "pity_count": count_since_last,
                    "character_name": record.character_name,
                    "pull_time": record.pull_time.isoformat(),
                })
                count_since_last = 0

        return history

    @staticmethod
    def daily_stats(
        banner_name: Optional[str] = None,
        days: int = 30,
    ) -> list[dict]:
        """
        按日期统计每日抽卡数量

        Returns:
            [{date, total, five_star, four_star, three_star}, ...]
        """
        records = db.get_all_records(banner_name=banner_name)
        if not records:
            return []

        # 按日期分组
        by_date: dict[str, dict[str, int]] = defaultdict(
            lambda: {"total": 0, "5": 0, "4": 0, "3": 0}
        )

        for record in records:
            date_str = record.pull_time.strftime("%Y-%m-%d")
            by_date[date_str]["total"] += 1
            by_date[date_str][str(record.rarity.value)] += 1

        # 生成最近N天的完整列表
        result = []
        today = datetime.now().date()
        for i in range(days - 1, -1, -1):
            date = today - timedelta(days=i)
            date_str = date.isoformat()
            day_data = by_date.get(date_str, {"total": 0, "5": 0, "4": 0, "3": 0})
            result.append({
                "date": date_str,
                "total": day_data["total"],
                "five_star": day_data.get("5", 0),
                "four_star": day_data.get("4", 0),
                "three_star": day_data.get("3", 0),
            })

        return result

    @staticmethod
    def banner_summary() -> list[dict]:
        """
        各卡池汇总统计

        Returns:
            [{banner_name, total, five_star, four_star, rate_5star, pity_count}, ...]
        """
        banners = db.get_banner_names()
        if not banners:
            return []

        summaries = []
        for name in banners:
            total = GachaStats.total_pulls(banner_name=name)
            counts = GachaStats.rarity_counts(banner_name=name)
            summaries.append({
                "banner_name": name,
                "total": total,
                "five_star": counts.get(Rarity.SPECIAL.value, 0),
                "four_star": counts.get(Rarity.EXCELLENT.value, 0),
                "three_star": counts.get(Rarity.FINE.value, 0),
                "rate_5star": GachaStats.rate_5star(banner_name=name),
                "pity_count": GachaStats.pity_count(banner_name=name),
            })

        return summaries

    @staticmethod
    def get_recent(limit: int = 20) -> list[GachaRecord]:
        """获取最近N条记录"""
        return db.get_all_records(limit=limit)
