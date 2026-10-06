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


class BannerType(str):
    """卡池类型常量（对应游戏召集记录页右上角的"渠道"）

    招集栏格式为 "{类型}/{卡池名}"：
      限定/万嶂烟峦  → LIMITED
      限时/至乐如真  → LIMITED_TIME
      招集/xxx      → SUMMON
      征集/器者征集  → COLLECT
      /孤岛螺旋      → SEASON（类型栏为空，目前仅赛季渠道如此）
    """
    LIMITED = "限定"
    LIMITED_TIME = "限时"
    SUMMON = "招集"
    COLLECT = "征集"
    SEASON = "赛季"
    UNKNOWN = "unknown"  # 没识别出类型时的占位；出现新类型再往上面加


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
    text_hash: str = ""          # OCR 文本哈希（调试用）
    seq_no: int = 0              # 同分钟组内的顺序号：距该组【最新那条】的偏移
                                 # （最新 = 0，越旧越大）。见 make_record_id 的说明。
                                 # 落库的原因：游戏的记录页时间只精确到"分"，
                                 # 同一分钟能有几十条，光靠 pull_time 排不出先后，
                                 # 必须靠这个显式顺序号才能还原真实抽取顺序。

    def __post_init__(self) -> None:
        if not self.record_id:
            self.record_id = self._generate_id()
        if not self.pull_date:
            self.pull_date = self.pull_time.strftime("%m-%d")

    def _generate_id(self) -> str:
        """兜底 ID：内容键 + 序号 0

        正常入库路径由调用方（扫描器）按"同内容键的出现序号"显式赋值，
        这里只保证直接构造对象时也有个确定的 ID。
        """
        return make_record_id(self, 0)

    def to_dict(self) -> dict:
        return {
            "character_name": self.character_name,
            "rarity": self.rarity.value,
            "pull_time": self.pull_time.isoformat(),
            "banner_name": self.banner_name,
        }

    def to_dict_full(self) -> dict:
        """完整导出"""
        return {
            "record_id": self.record_id,
            "character_name": self.character_name,
            "rarity": self.rarity.value,
            "rarity_name": self.rarity.name,
            "pull_date": self.pull_date,
            "pull_time": self.pull_time.isoformat(),
            "banner_name": self.banner_name,
            "banner_type": self.banner_type,
            "pull_number": self.pull_number,
            "account_id": self.account_id,
            "seq_no": self.seq_no,
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
            seq_no=data.get("seq_no", 0),
        )


# ═══════════════════════════════════════════════════════════
# record_id 生成规则（跨扫描、跨版本稳定）
# ═══════════════════════════════════════════════════════════
#
# 旧规则用的是 "页指纹 + 页内行号"，而行号会随新出货整体下移：
# 用户再抽一次十连，原本第 1 页第 0 行的记录会漂到第 2 页第 x 行，
# 页指纹也变了 → 算出来的 ID 完全不同 → 同一条记录被当成新记录再算一次。
#
# 新规则只用"游戏自己给的、跟词库无关的"信息：
#   内容键 = 时间(精确到分) + 账户
#   出现序号 seq = 同一内容键的所有记录里，距【最新那条】的偏移（最新 = 0，越旧越大）
#
# 为什么序号要"以最新那条为基准"而不是"从最旧往新数"：
#   扫描永远从第 1 页第 1 行（该组最新那条）开始，读到一半中断时，
#   已经入过库的是该组【最新端的连续若干条】。以最新条为基准，
#   同一条记录不管扫几次都算出同一个 seq，判重才成立；
#   若以最旧那条为基准，组的起点会随中断位置漂移，重扫时 seq 整体错位，
#   判定成"新记录"重复入库、且会漏掉真正没入过库的那几条。
#
# 为什么 record_id 里【要】放角色名：
#   同一分钟能出几十条，光靠 seq 只能表达"这一分钟的第几个位置"。
#   若某个位置原本是 A、后来重扫发现是 B（库里那条来自更早的扫描、
#   内容其实对不上），只靠 seq 就会把 B 当成"位置已占用"而丢掉，
#   B 永远进不来。把经词库纠错后的规范名放进 ID，
#   "位置 + 器者"一起定位，A 和 B 各占一个位置，都能正确入库。
#
#   角色名同样来自 config/names.yaml（经模糊匹配纠错）。跨版本改词库
#   （改名、加别名、调阈值）会让同一条记录算出不同的 record_id。
#   对此的处理不是避免它，而是【兼容读取】—— 见 make_record_key() 的说明：
#   判重时不直接比 record_id，而是比 (内容键, seq, 名称) 三元组，
#   于是词库怎么变、老记录的 ID 是哪种算法算的，都能正确认出"已入过库"。
#
# 判断"存在"时按 (内容键, 序号, 名称) 对齐，而不是直接比 record_id：
# 这样即使库里存着旧规则生成的 ID，也能正确识别出"这条已经计入过了"。

def make_record_key(record: GachaRecord) -> str:
    """记录内容键 —— 时间到分 + 账户

    同一分钟内可能有多条（一发十连全都落在同一分钟），单靠内容键会撞车，
    所以还要带出现序号和角色名，见 make_record_id()。
    存在性判断按 (内容键, seq, 名称) 三元组对齐，而不是直接比 record_id ——
    这样无论库里存的是哪一版算法算出的 ID，都能认出"这条已经计入过了"。
    """
    t = record.pull_time
    minute = f"{t.year:04d}{t.month:02d}{t.day:02d}{t.hour:02d}{t.minute:02d}"
    return f"{minute}|{record.account_id or 0}"


def make_record_id(record: GachaRecord, seq: int = 0) -> str:
    """record_id = md5(内容键 + 出现序号 + 角色名)

    Args:
        record: 记录
        seq: 该记录在"同一内容键的所有记录"中的位置 ——
             距该组【最新那条】的偏移，最新 = 0，越旧越大

    带上角色名的原因：同一分钟能出几十条，seq 只表达"第几个位置"。
    若某个位置库里的记录和本次读到的器者不是同一个，
    只靠 seq 会把新记录当成"位置已占用"而丢弃。加上名称后，
    位置相同但器者不同 → ID 不同 → 两条都能入库。
    """
    raw = f"{make_record_key(record)}|{seq}|{record.character_name}"
    return hashlib.md5(raw.encode()).hexdigest()[:12]


def make_dedup_key(record: GachaRecord, seq: int = 0) -> tuple:
    """判重用三元组 (内容键, seq, 角色名)

    为什么不直接比 record_id：record_id 的算法换过几版，
    库里老记录的 ID 跟新算法算的不是一回事，直接比会整批认不出来。
    三元组里的三个量都能从库里已有记录反推出来（seq 由 pull_number 还原），
    所以无论老记录的 ID 是哪一版算的，都能正确判重。
    """
    return (make_record_key(record), seq, record.character_name)
