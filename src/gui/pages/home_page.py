"""首页 — 按渠道分标签页展示卡池时间线（带头像占位和日期）"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea, QFrame,
    QPushButton, QTabWidget, QSizePolicy, QMessageBox,
)
from PyQt6.QtGui import QPixmap
from PyQt6.QtCore import Qt
from loguru import logger
from src.config import config
from collections import OrderedDict
import yaml

from src.models.gacha_record import Rarity, BannerType
from src.storage.database import get_db


_UP_MAP_CACHE = None      # 缓存 (路径, mtime) -> up_map
_UP_MAP_WARNED = False    # 失败告警只打一次，避免每帧刷屏
_DUP_CHECKED_MTIME = None # 重复 key 检查按 mtime 只做一次


def _find_duplicate_banner_keys(text: str) -> list:
    """扫原文找出 banners 段里重复的卡池名

    为什么不用 yaml 的解析结果：YAML 遇到同段内重复 key 会【静默丢弃】前面那条，
       解析后的 dict 里根本看不到重复，程序无从察觉。
       而这是我们最怕出错的场景 —— 复刻池如果 UP 角色换了又重复写一遍，
       新值会悄悄覆盖旧值，导致【历史记录的歪/不歪判定凭空改变】，且没有任何日志。

    做法：纯文本扫描，只认 "banners:" 之后、下一个顶层段落之前、
       缩进恰好 2 个空格的 `键: 值` 行。characters 段的嵌套键缩进更深（4~6 空格），
       不会被误判；`#` 注释行和空行跳过。

    Returns:
        [(卡池名, [值1, 值2, ...]), ...]；没有重复则返回 []
    """
    dups = []
    seen: dict = {}
    in_banners = False
    for raw in text.splitlines():
        if not in_banners:
            # 进入 banners 段（允许行尾有注释）
            if raw.startswith("banners:") or raw.rstrip() == "banners:":
                in_banners = True
            continue

        # 离开 banners 段：出现新的顶层键（顶格、非注释、非空）
        if raw and not raw[0].isspace() and not raw.lstrip().startswith("#"):
            break

        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue

        # 只认缩进恰好 2 空格的键行（banners 的直接子项）
        indent = len(raw) - len(raw.lstrip(" "))
        if indent != 2 or ":" not in raw:
            continue

        key, _, val = raw.strip().partition(":")
        key = key.strip()
        val = val.strip()
        if not key:
            continue
        # 去掉行尾注释（简单处理：值里出现 " #" 就截断）
        if " #" in val:
            val = val.split(" #", 1)[0].strip()

        if key in seen:
            seen[key].append(val)
        else:
            seen[key] = [val]

    for key, vals in seen.items():
        if len(vals) > 1:
            dups.append((key, vals))
    return dups


def _warn_duplicate_banner_keys(text: str) -> list:
    """发现重复卡池名就记日志（同一次加载只做一次，由调用方按 mtime 控制）

    注意：值相同不算问题（复刻时 UP 没变，重写一遍只是冗余）；
        值【不同】才是真危险 —— 说明 UP 角色变了，老记录会被按新值重判。
    """
    dups = _find_duplicate_banner_keys(text)
    if not dups:
        return []
    for key, vals in dups:
        if len(set(vals)) == 1:
            logger.warning(
                "卡池词库有重复条目（值相同，仅冗余）: '{}' 出现 {} 次，"
                "YAML 只保留最后一条。建议删掉多余的（复刻池无需重复登记）",
                key, len(vals),
            )
        else:
            logger.error(
                "卡池词库有重复条目且【值不同】: '{}' -> {}，"
                "YAML 静默采用了最后一条 '{}'。这会让按旧 UP 判定的历史记录"
                "重新被算歪 ⇒ 统计结果凭空变化。请只保留正确的那一条！",
                key, vals, vals[-1],
            )
    return dups


def _load_up_map():
    """读取"卡池名 → UP 角色"映射（names.yaml 的 banners 段）

    ⚠️ 读取失败【不再静默返回空字典】。以前失败时悄悄给 {}，界面上的"歪"
       会全部变成"不歪"，而且日志里一点痕迹都没有 —— 用户只会看到
       "重开之后全不歪"，完全不知道为什么。现在改为：
         - 成功：正常返回，并缓存（按文件 mtime 判断是否要重读）
         - 失败：返回 None，调用方据此显示"词库未加载"，不给出错误的统计
    """
    global _UP_MAP_CACHE, _UP_MAP_WARNED, _DUP_CHECKED_MTIME
    path = config.resource_root / "config" / "names.yaml"
    try:
        mtime = path.stat().st_mtime
    except OSError as e:
        if not _UP_MAP_WARNED:
            logger.error("卡池词库不可用（{}），本次不统计歪/不歪: {}", path, e)
            _UP_MAP_WARNED = True
        _UP_MAP_CACHE = None
        return None

    if _UP_MAP_CACHE is not None and _UP_MAP_CACHE[0] == (str(path), mtime):
        return _UP_MAP_CACHE[1]

    try:
        # 先读原文（供重复 key 检查，YAML 解析后这些信息会丢失），再解析
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
        data = yaml.safe_load(text) or {}
        up_map = data.get("banners", {})
        if not isinstance(up_map, dict):
            raise ValueError(f"banners 段不是字典: {type(up_map).__name__}")
    except Exception as e:
        if not _UP_MAP_WARNED:
            logger.error("卡池词库解析失败（{}），本次不统计歪/不歪: {}", path, e)
            _UP_MAP_WARNED = True
        _UP_MAP_CACHE = None
        return None

    # 重复 key 检查：按 mtime 只做一次（文件没改就不重复刷日志）
    if _DUP_CHECKED_MTIME != mtime:
        _warn_duplicate_banner_keys(text)
        _DUP_CHECKED_MTIME = mtime

    _UP_MAP_WARNED = False
    _UP_MAP_CACHE = ((str(path), mtime), up_map)
    logger.debug("卡池词库已加载: {} 条", len(up_map))
    return up_map


def _lookup_up(up_map: dict, banner_name: str) -> str:
    """在 up_map 里查卡池的 UP 角色，容忍 OCR 残留的格式差异

    依次尝试：原样 → 去空白 → 去掉 "类型/" 前缀 → 模糊匹配
    """
    if not up_map or not banner_name:
        return ""
    bn = banner_name.strip()
    if bn in up_map:
        return up_map[bn] or ""
    # 去掉 "限定/金碧流彩" 这种类型前缀
    if "/" in bn:
        tail = bn.rsplit("/", 1)[-1].strip()
        if tail in up_map:
            return up_map[tail] or ""
        bn = tail
    # 全角/半角空格、不可见字符
    squeezed = "".join(bn.split())
    for k, v in up_map.items():
        if "".join(k.split()) == squeezed:
            return v or ""
    return ""


# 分区顺序（固定 5 类，无法归类的"未知"殿后）
_TYPE_ORDER = (
    BannerType.LIMITED,
    BannerType.LIMITED_TIME,
    BannerType.SUMMON,
    BannerType.COLLECT,
    BannerType.SEASON,
)

_TYPE_LABEL = {
    BannerType.LIMITED: "限定",
    BannerType.LIMITED_TIME: "限时",
    BannerType.SUMMON: "招集",
    BannerType.COLLECT: "征集",
    BannerType.SEASON: "赛季",
    BannerType.UNKNOWN: "未知",
}

# 只有"限定"和"限时"这两类渠道存在"歪"的概念（UP 角色可能被别的红卡顶掉）。
#   限定 / 限时：有 UP 角色，出别的红卡 = 歪
#   招集：自选复刻池，玩家自选四个角色，只在这四个里出 → 无歪
#   征集：征集券日常池，固定四个红角色，且**没有保底** → 无歪
#   赛季：40 抽保底，池内只有一个赛季角色 → 无歪
# 其余三类不再去 banners 词库查 UP（查不到会变 unknown 反而误导），
# 直接判定"无歪概念"，界面也不打 UP/歪 标签。
_OFF_CAPABLE_TYPES = (BannerType.LIMITED, BannerType.LIMITED_TIME)

# 计入"不歪率"分母的类型：用户口径 —— 招集计入，征集/赛季不计入。
# （征集是日常券池，混进概率分母会稀释出货率，没有参考意义。）
_RATE_TYPES = (BannerType.LIMITED, BannerType.LIMITED_TIME, BannerType.SUMMON)

# 计入"平均出红抽数"的类型：用户口径 —— 只有限定 / 限时。
# （这两类有明确的保底规则，平均值才有意义；招集是自选池、征集无保底、赛季单角色池，
#   掺进来会失真。）
_AVG_RATE_TYPES = (BannerType.LIMITED, BannerType.LIMITED_TIME)

# 统计口径说明（点"ⓘ"弹出）。放在模块级便于 UI 与文档共用同一份文案。
_INFO_ALGORITHM = {
    "avg": (
        "平均出红抽数：\n"
        "\n"
        "统计范围：仅「限定」和「限时」渠道。\n"
        "平均出红抽数 = (限定 + 限时) 的总消耗抽数 ÷ 出红个数\n"
        "其中「出红个数」= 限定与限时产出的红卡（特出）个数。\n"
        "尚未出货的垫抽不计入分子。"
    ),
    "total": (
        "总抽数：\n"
        "\n"
        "计入「限定」、「限时」、「赛季」三个渠道，\n"
        "即付费抽部分消耗的所有抽数"
    ),
    "rate": (
        "不歪率：\n"
        "\n"
        "统计范围：仅「限定」「限时」两类可歪卡池。\n"
        "计算公式：不歪率 = 未歪红卡数 ÷ （限时+限定）总出红数"
    ),
    "section": (
        "渠道统计：\n"
        "\n"
        "共 N 抽：该渠道在本账户下的抽卡记录条数（按渠道独立计数）。\n"
        "特出 N：该渠道产出的红卡个数。\n"
        "歪 N：限定/限时专属 —— 出货角色不是该卡池 UP 角色的次数。\n"
        "出红 N：征集渠道专属 —— 征集出的红卡个数。\n"
        "\n"
        "征集渠道：\n"
        "其出红个数只在这里单独显示，不并入上方顶栏的总特出数与\n"
        "不歪率、平均出红抽数等全局统计。"
    ),
}


def _info_button(text, title="统计口径"):
    """生成一个"ⓘ"小按钮，点击弹出统计算法说明。

    自绘一个圆形，里面一个"!"；比纯文字 QLabel 更醒目，也比 QToolTip
    更适合放多行说明（tooltip 太长会被截断）。
    """
    btn = QPushButton("!")
    btn.setFixedSize(16, 16)
    btn.setCursor(Qt.CursorShape.WhatsThisCursor)
    # 圆形底 + "!"：QSS 的 border-radius 取半径即可得到正圆
    btn.setStyleSheet(
        "QPushButton {"
        "  color:#3a5a70; background:#e8eef3;"
        "  border:1px solid #8aa6b8; border-radius:8px;"
        "  font-size:11px; font-weight:bold; padding:0;"
        "}"
        "QPushButton:hover {"
        "  color:#ffffff; background:#4a7a9a; border:1px solid #4a7a9a;"
        "}"
        "QPushButton:pressed {"
        "  background:#2c5a78; border:1px solid #2c5a78;"
        "}"
    )
    btn.setToolTip("点击查看统计口径")
    btn.clicked.connect(lambda: QMessageBox.information(btn, title, text))
    return btn



def _pool_key(banner_type):
    """把记录归到 5 个类型之一；没识别出类型的落到 UNKNOWN"""
    if banner_type in _TYPE_LABEL:
        return banner_type
    return BannerType.UNKNOWN


def _ten_group_key(record, minute_pos=None):
    """返回该记录所属"十连"的标识：(分钟, 第几段)

    游戏里一次十连 = 同一分钟内的 10 条记录。同一分钟可能抽了多次十连
    （20 条 = 两段），所以按时间序从**最新端**每 10 条切一段。

    ⚠️ 不依赖 `seq_no`：老库（seq_no 列出现前扫描的）全是 0，
       靠它会把整分钟都并成一段。改用调用方传进来的 `minute_pos`
       —— 该记录在本分钟内的序位（从最新端数，最新 = 0），
       由遍历完成后统一计算。
    """
    if record.pull_time is None:
        return None
    minute = record.pull_time.replace(second=0, microsecond=0)
    if minute_pos is None:
        seq = getattr(record, "seq_no", 0) or 0
        return (minute, seq // 10)
    return (minute, minute_pos // 10)


def _mark_double_gold(chars):
    """给 chars 里的记录打「十连双红」标记

    规则（用户口径）：同一次十连（同一分钟内每 10 条切一段）里出现 2 条及以上
    红卡 → 这几条用一个小框框住，框内柱子换金色，左上角标"十连双红/三红"。
    同一分钟出现多组就分多个框。

    原地写入每个 c 的：
        c["gold_box"]     = 该条所属框的组号（None = 不属于任何双金框）
        c["gold_total"]   = 该框里的红卡总数（2 = 双红，3 = 三红……）
        c["gold_first"]   = 该条是否为框内第一条（只有第一条画角标/开启框底）
    """
    for c in chars:
        c["gold_box"] = None
        c["gold_total"] = 0
        c["gold_first"] = False

    # 按十连组聚合（保持原顺序）
    groups: dict = OrderedDict()
    for idx, c in enumerate(chars):
        key = c.get("ten_key")
        if key is None:
            continue
        groups.setdefault(key, []).append(idx)

    for key, idxs in groups.items():
        if len(idxs) < 2:
            continue                     # 这一发十连只出了 1 个红，不算双金
        for n, idx in enumerate(idxs):
            chars[idx]["gold_box"] = key
            chars[idx]["gold_total"] = len(idxs)
            chars[idx]["gold_first"] = (n == 0)


# 柱状图配色阈值（用户口径）：
#   < 50 抽    → 绿（还没到保底压力）
#   50 ~ 60 抽 → 黄/橙（接近保底）
#   60 ~ 70 抽 → 红（吃满保底）
# 柱子长度上限 70 抽（限定/限时单次出红的实际最大消耗，超过不再变长）。
_BAR_MAX_PULLS = 70
_BAR_UNIT_PX = 6.0            # 每 1 抽增加的像素（用户建议 4~5px，这里取 6 让差异更明显）→ 满格 420px
_BAR_MIN_PX = 38              # 最短柱宽：必须放得下最长的柱内文本（"70抽"约 34px + 内边距）


def _bar_color(pulls):
    """按消耗抽数取柱子颜色"""
    if pulls is None:
        return "#4a4a4a"
    if pulls < 50:
        return "#3fae5a"          # 绿
    if pulls < 60:
        return "#d7a52b"          # 黄
    return "#c0392b"              # 红


def _bar_width(pulls):
    """柱子像素宽度：每抽固定增量，封顶 70 抽"""
    if not pulls or pulls <= 0:
        return 0
    n = min(pulls, _BAR_MAX_PULLS)
    return int(n * _BAR_UNIT_PX)


# 十连双红组底：浅青（与普通行的 #252526 略有色相差异，一眼能认出来但又不刺眼）
_GOLD_GROUP_BG = (28, 44, 50)        # RGB ≈ #1c2c32


def _build_timeline(account_id: int = 0):
    """按卡池类型分区构建时间线

    Returns:
        (sections, total, total_5, off_count, account_name, up_ready, rated_5, stats)
        total   : **不含征集**的总抽数（征集用征集券，不计入全局口径）
        total_5 : **不含征集**的红卡总数（征集出红个数单独在它自己的标签页显示）
        up_ready: 卡池词库是否可用。False 时限定/限时的 off 统计不可信，
                  UI 应提示而不是显示"全不歪"
        rated_5 : 计入"不歪率"分母的特出数（限定/限时/招集）。
                  征集、赛季是日常券池 / 单角色池，不参与不歪率
        stats   : dict，打包那些"只做展示、不参与解包"的派生统计：
                  avg_pull（限定+限时的平均出红抽数，None=无数据）
                  avg_hits（参与平均的出红次数）
                  collect_total / collect_5（征集抽数 / 征集出红个数）
        sections: list[dict]，按 _TYPE_ORDER 排序，每项为
            {"type", "label", "total", "specials", "specials_off_capable",
             "offs", "unknowns", "pity",
             "banners": OrderedDict(卡池名 -> {"chars": [...]})}
    """
    up_map = _load_up_map()
    up_ready = up_map is not None
    if up_map is None:
        up_map = {}          # 词库不可用时按"查不到 UP"处理，但会标记 up_ready=False
    if account_id > 0:
        records = get_db().get_all_records(account_id=account_id)
    else:
        records = get_db().get_all_records()  # 无账户筛选（兼容）
    if not records:
        # ⚠ 返回值必须与正常路径一致（8 个），少一个会让 refresh() 解包报错。
        #    空库时 rated_5 是 0，stats 给一份零值。
        return [], 0, 0, 0, "", up_ready, 0, {
            "avg_pull": None, "avg_hits": 0, "collect_total": 0, "collect_5": 0,
        }

    records.sort(key=lambda r: r.pull_number)

    # 预先算好每条记录"在本分钟内的序位"（从最新端数，最新 = 0）。
    # records 已按 pull_number 升序 = 真实时间序（旧→新），所以同一分钟内
    # 出现的先后就是旧→新；该分钟内最后一条是最新那条（序位 0）。
    # 用途：切分"十连"（每 10 条一发），判定十连双红。
    # ⚠️ 不能直接用 seq_no：老库该列全 0，会把整分钟误并成一段。
    minute_pos = {}
    _minute_seen = {}
    for r in records:
        if r.pull_time is None:
            continue
        m = r.pull_time.replace(second=0, microsecond=0)
        _minute_seen[m] = _minute_seen.get(m, 0) + 1
    _minute_total = dict(_minute_seen)
    _minute_used = {}
    for r in records:
        if r.pull_time is None:
            continue
        m = r.pull_time.replace(second=0, microsecond=0)
        _minute_used[m] = _minute_used.get(m, 0) + 1
        # 从最新端数：本分钟总条数 - 已数到位次
        minute_pos[id(r)] = _minute_total[m] - _minute_used[m]

    sections: OrderedDict = OrderedDict()
    pity: dict = {}
    unknown_banner_names: list = []      # 词库里查不到 UP 角色的卡池（歪/不歪无从判断）
    avg_pulls: dict = {}                 # 各渠道"平均出红抽数"的中间量（见下）

    for r in records:
        pk = _pool_key(r.banner_type)
        sec = sections.get(pk)
        if sec is None:
            sec = sections[pk] = {
                "type": pk,
                "label": _TYPE_LABEL.get(pk, "未知"),
                "total": 0,
                "specials": 0,
                "specials_off_capable": 0,   # 计入不歪率的那部分特出数（限定/限时/招集）
                "offs": 0,
                "unknowns": 0,
                "pity": 0,
                "banners": OrderedDict(),
                "last_banner": "",
            }

        bn = r.banner_name or "未知"
        sec["total"] += 1
        sec["last_banner"] = bn

        # 垫抽按类型各自独立累加
        pity[pk] = pity.get(pk, 0) + 1
        # 招集 / 征集：红卡数单独记一份（招集计入不歪率，征集不计），
        # 供顶栏按类型口径汇总时使用。
        if r.rarity == Rarity.SPECIAL:
            banner = sec["banners"].setdefault(bn, {"chars": []})

            if pk in _OFF_CAPABLE_TYPES:
                # 限定 / 限时：只有这两类存在"歪"的可能，查词库判三态
                up_char = _lookup_up(up_map, bn)
                # 查不到 UP 角色时【不能】当成"没歪"：那是"无从判断"。
                # 以前写成 `off = bool(up_char) and ...`，查不到就静默判 False，
                # 界面上一片"不歪"，用户根本看不出是数据问题还是真没歪。
                # 现在把它标成 unknown，UI 单独呈现。
                if up_char:
                    off = r.character_name != up_char
                    off_state = "off" if off else "up"
                else:
                    off = None
                    off_state = "unknown"
                    if bn not in unknown_banner_names:
                        unknown_banner_names.append(bn)
            else:
                # 招集 / 征集 / 赛季：池内只出固定几个角色，不存在"歪"的概念。
                # 不查词库、不打标签、永不算 unknown（查不到反而会误导成"数据有问题"）。
                up_char = ""
                off = False
                off_state = "no_off"

            banner["chars"].append({
                "name": r.character_name,
                "pull_number": r.pull_number,
                "pull_date": r.pull_date,
                "off": off,
                "off_state": off_state,
                "up_char": up_char,
                "pity": pity[pk],
                # 十连组标识：同一分钟内的记录按时间序每 10 条切一段
                # （游戏里一次十连 = 同一分钟的 10 条）。用来判定"十连双红"。
                "ten_key": _ten_group_key(r, minute_pos.get(id(r))),
            })
            sec["specials"] += 1
            sec["specials_off_capable"] += 1 if pk in _RATE_TYPES else 0
            # 平均出红抽数（仅限定/限时）：累加"这一次出红消耗了多少抽"，
            # 出货后 pity 归零（见本循环末尾），所以这里的 pity[pk] 正好是
            # 自上一次出红以来消耗的抽数，即本次的出红抽数。
            if pk in _AVG_RATE_TYPES:
                a = avg_pulls.setdefault(pk, {"pulls": 0, "hits": 0})
                a["pulls"] += pity[pk]
                a["hits"] += 1
            if off:
                sec["offs"] += 1
            elif off is None:
                sec["unknowns"] += 1
            pity[pk] = 0

    # 没有抽出特出的类型也要显示垫抽（贴到该类型下最后一个卡池）
    for pk, remaining in pity.items():
        sec = sections.get(pk)
        if sec is None or remaining <= 0:
            continue
        sec["pity"] = remaining
        bn = sec["last_banner"] or "未知"
        if bn not in sec["banners"]:
            sec["banners"][bn] = {"chars": []}

    # 每个卡池内特出倒序（最新在前）
    for sec in sections.values():
        for banner in sec["banners"].values():
            banner["chars"].reverse()

    # 标出"十连双红/三红"（必须在 reverse 之后 —— 框是按十连组聚合的，
    # 组内顺序由 ten_key 决定，与显示顺序无关，但统一在最终顺序上打标更直观）
    for sec in sections.values():
        for banner in sec["banners"].values():
            _mark_double_gold(banner["chars"])

    ordered = [sections[t] for t in _TYPE_ORDER if t in sections]
    if BannerType.UNKNOWN in sections:
        ordered.append(sections[BannerType.UNKNOWN])

    # ── 全局统计 ─────────────────────────────────────────────────────
    # 总抽数【不含征集】：征集消耗的是征集券（日常券池），混进总抽数会失真。
    # 征集的出红/抽数只在它自己的标签页里单独统计，不进任何全局口径。
    collect_total = sections[BannerType.COLLECT]["total"] if BannerType.COLLECT in sections else 0
    total = len(records) - collect_total
    # 总特出同理不含征集（征集的出红个数单独显示）
    collect_5 = sections[BannerType.COLLECT]["specials"] if BannerType.COLLECT in sections else 0
    total_5 = sum(s["specials"] for s in ordered) - collect_5
    off_count = sum(s["offs"] for s in ordered)
    unknown_count = sum(s["unknowns"] for s in ordered)
    # 计入"不歪率"分母的特出数：限定/限时/招集；征集与赛季是日常/单角色池，不掺进来
    rated_5 = sum(s.get("specials_off_capable", 0) for s in ordered)

    # 平均出红抽数（限定 + 限时 合并计算）：总消耗抽数 ÷ 出红次数
    # 合并而非分开，是因为单看某一类样本太少，平均值波动大没有参考价值。
    avg_total_pulls = sum(a["pulls"] for a in avg_pulls.values())
    avg_total_hits = sum(a["hits"] for a in avg_pulls.values())
    avg_pull = (avg_total_pulls / avg_total_hits) if avg_total_hits else None

    # 获取账户名称
    account_name = ""
    if account_id:
        acc = get_db().get_account(account_id)
        if acc:
            account_name = acc.name

    # 有红卡但"歪/不歪"无从判断时，把涉及的卡池名记下来，供 UI 提示
    # （现在只可能来自限定/限时两类 —— 招集/征集/赛季固定判无歪，不进 unknowns）
    if unknown_count:
        logger.warning("{} 条特出的卡池在词库 banners 段里查不到 UP 角色，"
                       "无法判断歪/不歪: {}", unknown_count, unknown_banner_names)
    if not up_ready:
        logger.error("卡池词库未加载，本次的歪/不歪统计不可用")

    stats = {
        "avg_pull": avg_pull,              # 平均出红抽数（限定+限时），None = 无数据
        "avg_hits": avg_total_hits,        # 参与平均的出红次数
        "collect_total": collect_total,    # 征集抽数（已从 total 中剔除）
        "collect_5": collect_5,            # 征集出红个数（不进全局）
    }
    return ordered, total, total_5, off_count, account_name, up_ready, rated_5, stats


class HomePage(QWidget):
    """概览页

    布局：顶部统计栏（总览 + 导出/导入） + 下方 QTabWidget（每个渠道一个标签页）。
    为什么改成分栏：以前 5 个渠道纵向堆在一个滚动区里，渠道标题要一直往下滚
    才能看到，窗口一窄标题还会被压扁/裁切。改成标签页后每个渠道独立滚动，
    标题永远完整，也不用来回滚动几屏找某个渠道。
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._main_window = parent
        l = QVBoxLayout(self)
        l.setContentsMargins(12, 8, 12, 8)
        l.setSpacing(6)

        # 顶部：按钮行 + 统计栏（都是固定高度，不参与滚动，不会被内容挤变形）
        # 布局分两层：
        #   第 1 行：导出 / 导入按钮（靠右）
        #   第 2 行：统计栏（左）—— 内容较多，独占一行才不会挡住或挤掉
        # 早先两者挤在同一行，窗口用初始大小时统计文字会被按钮压掉一部分。
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        btn_row.addStretch()

        btn_export = QPushButton("导出 JSON")
        btn_export.setFixedHeight(26)
        btn_export.clicked.connect(self._export_json)
        btn_row.addWidget(btn_export)

        btn_import = QPushButton("导入 JSON")
        btn_import.setFixedHeight(26)
        btn_import.clicked.connect(self._import_json)
        btn_row.addWidget(btn_import)
        l.addLayout(btn_row)

        # 统计栏：实际内容由 refresh() 逐项填充（每项后可跟一个 ⓘ 按钮），
        # 所以这里只建布局并挂到 self，不在这里塞文本。
        # 允许换行：外层用 QVBoxLayout 装两行 QHBoxLayout（见 refresh 里的换行逻辑）。
        self._stat_row = QHBoxLayout()
        self._stat_row.setSpacing(6)
        self._stat_row.addStretch()
        self._stat_row2 = QHBoxLayout()
        self._stat_row2.setSpacing(6)
        self._stat_row2.addStretch()
        l.addLayout(self._stat_row)
        l.addLayout(self._stat_row2)

        # 主体：每个渠道一个标签页
        self._tabs = QTabWidget()
        self._tabs.setDocumentMode(True)
        l.addWidget(self._tabs, 1)

        # 窗口宽度变化时重新排布统计栏（换行阈值是按宽度算的）
        self._last_w = 0

    def resizeEvent(self, event):
        """宽度明显变化时重排统计栏 —— 换行是按窗口宽度估的，得跟着更新。"""
        super().resizeEvent(event)
        w = self.width()
        # 只有变化超过 40px 才 refresh，避免拖动窗口时疯狂重绘
        if self._stat_row.count() and abs(w - self._last_w) > 40:
            self._last_w = w
            self.refresh()

    def on_activated(self):
        self.refresh()

    def _export_json(self):
        from PyQt6.QtWidgets import QFileDialog, QMessageBox
        path, _ = QFileDialog.getSaveFileName(
            self, "导出抽卡记录", "gacha_export.json", "JSON (*.json)"
        )
        if path:
            from src.storage.exporter import export_to_json
            account_id = self._main_window.current_account_id if self._main_window else 0
            try:
                result = export_to_json(path, account_id=account_id)
                QMessageBox.information(self, "导出成功", f"已导出到:\n{result}")
            except Exception as e:
                QMessageBox.warning(self, "导出失败", str(e))

    def _import_json(self):
        from PyQt6.QtWidgets import QFileDialog, QMessageBox
        path, _ = QFileDialog.getOpenFileName(
            self, "导入抽卡记录", "", "JSON (*.json)"
        )
        if path:
            from src.storage.exporter import import_from_json
            account_id = self._main_window.current_account_id if self._main_window else 0
            try:
                count = import_from_json(path, account_id=account_id)
                QMessageBox.information(self, "导入成功", f"已导入 {count} 条新记录")
                self.refresh()
            except Exception as e:
                QMessageBox.warning(self, "导入失败", str(e))

    def refresh(self):
        account_id = self._main_window.current_account_id if self._main_window else 0
        (sections, total, total_5, off_count, account_name,
         up_ready, rated_5, stats) = _build_timeline(account_id)
        logger.info("刷新首页: account_id={}, total={}, 特出={}, 计入不歪率={}, "
                    "类型分区={}, 词库可用={}, 平均出红={}, 征集={}/{}",
                    account_id, total, total_5, rated_5, len(sections), up_ready,
                    stats.get("avg_pull"), stats.get("collect_5"),
                    stats.get("collect_total"))

        # 记住当前选中的渠道，刷新后尽量停在同一个标签上
        keep = self._tabs.tabBar().currentIndex()

        # 先清掉所有旧标签页
        self._tabs.blockSignals(True)
        while self._tabs.count():
            w = self._tabs.widget(0)
            self._tabs.removeTab(0)
            if w:
                w.deleteLater()
        self._tabs.blockSignals(False)

        # 统计栏两行都要清空重建（内容含可点击的 ⓘ，不能只 setText）
        for row in (self._stat_row, self._stat_row2):
            while row.count():
                it = row.takeAt(0)
                w = it.widget()
                if w:
                    w.deleteLater()
            row.addStretch()      # takeAt 会把原来的弹簧也清掉，这里补回来

        if not sections:
            empty_lbl = QLabel("暂无记录")
            empty_lbl.setStyleSheet("color:#888; font-size:13px; "
                                    "border:none; background:transparent;")
            self._stat_row.insertWidget(0, empty_lbl)
            # 空态也放进一个占位标签页，避免出现"一个标签都没有"的怪界面
            empty = QLabel("暂无记录，点击左侧「开始扫描」获取")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setStyleSheet("color:#666; font-size:13px;")
            self._tabs.addTab(empty, "概览")
            return

        unknowns = sum(s.get("unknowns", 0) for s in sections)
        avg_pull = stats.get("avg_pull")
        avg_hits = stats.get("avg_hits") or 0

        # 统计栏改成"碎片 + ⓘ"：每个统计维度后面跟一个圆圈感叹号，
        # 点开能看到这一项的具体算法（口径说明见 _INFO_ALGORITHM）。
        # 用 QHBoxLayout 而不是一整条字符串，是因为要在中间插入可点击按钮。
        #
        # 分两行显示（第 1 行放不下就换到第 2 行）：
        #   初始窗口宽度下全部挤一行会被按钮压掉一部分，所以做了个简单的
        #   按"累计宽度"换行的逻辑：超过窗口宽度的 ~62% 且不是行首就换行。
        self._stat_wrap_px = max(420, int(self.width() * 0.62))
        self._cur_row = self._stat_row
        self._row_used = 0

        def _add_widget(w, est_px):
            """把控件放进当前行；放不下就换到第二行。返回是否发生了换行。"""
            if (self._cur_row is self._stat_row
                    and self._row_used > 0
                    and self._row_used + est_px > self._stat_wrap_px):
                self._cur_row = self._stat_row2
                self._row_used = 0
                self._cur_row.insertWidget(self._cur_row.count() - 1, w)
                self._row_used += est_px
                return True
            self._cur_row.insertWidget(self._cur_row.count() - 1, w)
            self._row_used += est_px
            return False

        def _put(text, info_key=None, est_px=None):
            """往统计栏追加一段文本；info_key 不为 None 时后面跟一个 ⓘ"""
            lbl = QLabel(text)
            lbl.setStyleSheet("color:#888; font-size:13px; border:none; background:transparent;")
            # 粗估宽度：中文字符约 13px，ASCII 约 7px
            if est_px is None:
                est_px = sum(13 if ord(c) > 127 else 7 for c in text) + 12
            # 先判断换行：只有"留在同一行"时才在它前面补分隔竖线，
            # 否则换行后行尾会挂一个孤零零的 "|"。ⓘ 按钮也一样先算总宽。
            need = est_px + (24 if info_key else 0)
            wrapped = (self._cur_row is self._stat_row
                       and self._row_used > 0
                       and self._row_used + need > self._stat_wrap_px)
            if wrapped:
                # 换到第二行：不补分隔线
                self._cur_row = self._stat_row2
                self._row_used = 0
                self._cur_row.insertWidget(self._cur_row.count() - 1, lbl)
                self._row_used += est_px
            else:
                if self._row_used > 0:
                    sep = QLabel("|")
                    sep.setStyleSheet("color:#3a3a3a; font-size:13px; "
                                      "border:none; background:transparent;")
                    self._cur_row.insertWidget(self._cur_row.count() - 1, sep)
                    self._row_used += 10
                self._cur_row.insertWidget(self._cur_row.count() - 1, lbl)
                self._row_used += est_px
            if info_key:
                self._cur_row.insertWidget(self._cur_row.count() - 1,
                                           _info_button(_INFO_ALGORITHM[info_key]))
                self._row_used += 24
            return lbl

        def _add_widget(w, est_px):
            """把已建好的控件放进当前行（放不下就换到第二行）。"""
            need = est_px
            if (self._cur_row is self._stat_row
                    and self._row_used > 0
                    and self._row_used + need > self._stat_wrap_px):
                self._cur_row = self._stat_row2
                self._row_used = 0
            self._cur_row.insertWidget(self._cur_row.count() - 1, w)
            self._row_used += est_px
            return w

        if account_name:
            nm = QLabel(f"[{account_name}]")
            nm.setStyleSheet("color:#7fb3d5; font-size:13px; font-weight:bold; "
                             "border:none; background:transparent;")
            _add_widget(nm, sum(13 if ord(c) > 127 else 7 for c in account_name) + 20)

        # 总抽数（不含征集）—— 后面跟 ⓘ 说明"为什么不含征集"
        _put(f"总抽数: {total}", "total")

        # 特出（不含征集）+ 歪 + 不歪率
        if not up_ready:
            _put(f"特出: {total_5}")
            warn = QLabel("⚠ 卡池词库未加载，歪/不歪统计不可用")
            warn.setStyleSheet("color:#e0a030; font-size:13px; "
                               "border:none; background:transparent;")
            _add_widget(warn, 240)
        else:
            judged = rated_5 - unknowns
            if rated_5 > 0 and judged > 0:
                rate = (judged - off_count) / judged * 100
                # ⚠️ 特出/歪 后面【不挂 ⓘ】：它容易被误认成"不歪率的 ⓘ"，
                #    而不歪率自己有独立的一段和 ⓘ。这里只放纯文本。
                _put(f"特出: {total_5}/歪{off_count}")
                _put(f"不歪率: {rate:.1f}%", "rate")
            else:
                _put(f"特出: {total_5}")
            if unknowns:
                warn = QLabel(f"⚠ {unknowns} 条无法判断歪/不歪")
                warn.setStyleSheet("color:#e0a030; font-size:13px; "
                                   "border:none; background:transparent;")
                _add_widget(warn, 180)

        # 平均出红抽数（仅限定+限时）—— 后面跟 ⓘ 说明算法
        if avg_pull is not None:
            _put(f"平均出红: {avg_pull:.1f} 抽/红（{avg_hits} 次）", "avg")

        # 每个渠道一个标签页
        for sec in sections:
            self._tabs.addTab(self._make_section_page(sec),
                              self._tab_label(sec))

        # 尽量回到刷新前的那个渠道
        if 0 <= keep < self._tabs.count():
            self._tabs.setCurrentIndex(keep)

    def _tab_label(self, sec):
        """标签文字：渠道名 + 抽数（抽数少时也一眼看得出哪个渠道有货）"""
        return f"{sec['label']} ({sec['total']})"

    def _make_section_page(self, sec):
        """单个渠道的页面：分区统计条（固定）+ 可滚动的卡池列表"""
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(4)

        # 渠道统计条固定在顶部，不随列表滚动 —— 标题不会再被"挤没"
        v.addWidget(self._make_section_header(sec))

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        inner = QWidget()
        col = QVBoxLayout(inner)
        col.setContentsMargins(0, 0, 0, 6)
        col.setSpacing(2)

        # 该渠道的垫抽（按渠道独立计数）
        if sec["pity"] > 0:
            col.addWidget(self._make_pity(sec["pity"]))

        # 该渠道下的各卡池
        for bn, data in sec["banners"].items():
            block = QFrame()
            # 用户要求：不要明显的框线。只保留一层极淡底色区分相邻卡池，
            # 不再画 border（辅助定位的线也一并去掉）。
            block.setStyleSheet("background:#1e1e1e; border:none;")
            # ⚠️ 卡池 block 不能被纵向拉伸：外层 col 末尾有 addStretch()，
            #    若 block 可扩展，超出内容的高度会摊到 block 里，
            #    进而把 block 内部的标题行拉高/压扁（"记录少时标题被压扁"就是这来的）。
            block.setSizePolicy(QSizePolicy.Policy.Preferred,
                                QSizePolicy.Policy.Maximum)
            bl = QVBoxLayout(block)
            bl.setContentsMargins(0, 0, 0, 4)
            bl.setSpacing(0)

            bl.addWidget(self._make_title(bn))

            # 同一次十连出的多条双金要「共用一块无缝背景」，中间不能有行间
            # 分割线 —— 所以按组切包：连续同组的多条一次性交给一个容器渲染。
            prev_group = None
            group_rows = []
            for c in data["chars"]:
                gid = c.get("gold_box")
                if gid is not None and gid == prev_group:
                    group_rows.append(c)          # 并入当前双金组
                    continue
                if group_rows:
                    bl.addWidget(self._make_gold_group(group_rows))
                group_rows = [c] if gid is not None else []
                if gid is None:
                    bl.addWidget(self._make_pull(c))
                prev_group = gid
            if group_rows:
                bl.addWidget(self._make_gold_group(group_rows))

            # 多余空间交给 stretch，别让标题行/记录行去分这些高度
            bl.addStretch()

            col.addWidget(block)

        col.addStretch()
        scroll.setWidget(inner)
        v.addWidget(scroll, 1)
        return page

    def _make_section_header(self, sec):
        """渠道统计条：渠道名 + 该渠道统计

        现在它是标签页顶部的固定条（不参与滚动），所以给足高度，
        信息多的渠道（限定那种"共212抽·特出10·歪4"）也不会被裁掉。
        """
        w = QFrame()
        # 用户要求：不要明显的框线。原来的左侧 4px 蓝条是纯定位用的，
        # 现在改成一个几乎不可见的淡色底条，不再有硬边框。
        w.setStyleSheet("background:#26282d; border:none; border-radius:4px;")
        w.setFixedHeight(34)
        row = QHBoxLayout(w)
        row.setContentsMargins(10, 0, 10, 0)
        row.setSpacing(8)

        name = QLabel(f"{sec['label']}渠道")
        name.setStyleSheet(
            "color:#e8e8e8; font-size:13px; font-weight:bold; "
            "border:none; background:transparent;"
        )
        row.addWidget(name)

        # 招集/征集/赛季不存在"歪"，分区统计里就不出现"歪 N"，免得误导
        if sec["type"] in _OFF_CAPABLE_TYPES:
            txt = f"共 {sec['total']} 抽 · 特出 {sec['specials']} · 歪 {sec['offs']}"
            if sec.get("unknowns"):
                txt += f" · ? {sec['unknowns']}"
        elif sec["type"] == BannerType.COLLECT:
            # 征集的出红只在本渠道内单独统计，不并入顶栏全局口径。
            # （"单列/不计入"这层意思已由 ⓘ 弹窗说明，这里不再堆括号文案）
            txt = f"共 {sec['total']} 抽 · 出红 {sec['specials']} 个"
        else:
            txt = f"共 {sec['total']} 抽 · 特出 {sec['specials']}"
        stat = QLabel(txt)
        stat.setStyleSheet("color:#888; font-size:12px; border:none; background:transparent;")
        row.addWidget(stat)
        # 圆圈感叹号：点开看这一栏数字的算法口径
        row.addWidget(_info_button(_INFO_ALGORITHM["section"],
                                   title=f"{sec['label']}渠道 · 统计口径"))

        row.addStretch()
        return w

    def _make_title(self, banner_name):
        w = QFrame()
        w.setStyleSheet("background:#3c3c3c;")
        # ⚠️ 必须用 setFixedHeight 而不是 setMinimumHeight：
        #    记录少时列表下方留白多，若标题行可被纵向拉伸，
        #    这些留白会被摊进标题行 → 标题时高时矮（"记录过多/过少导致压缩"）。
        #    固定高度 + Fixed 策略，标题行永远只有 30px。
        w.setFixedHeight(30)
        w.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        l = QHBoxLayout(w)
        l.setContentsMargins(10, 0, 10, 0)
        lb = QLabel(banner_name)
        lb.setStyleSheet("color:#f39c12; font-size:14px; font-weight:bold; border:none; background:transparent;")
        l.addWidget(lb)
        l.addStretch()
        return w

    def _make_pull(self, ch):
        """一条普通记录（非十连双金组）：头像 + 柱状图 + 歪标注

        ch 为 _build_timeline 里构造的 dict，字段：
            name / pull_number / pull_date / off / off_state / up_char
            pity   —— 这一发消耗的抽数（柱长与颜色都按它算）
            gold_box / gold_total / gold_first —— 十连双红框信息（本函数不用）
        双金那几条走 _make_gold_group，不走这里。
        """
        return self._make_row(ch, mode="normal")

    def _make_gold_group(self, chars):
        """十连双红/三红组：一组共用一个无缝容器

        用户口径：一次十连出的两/三个金共**同一块背景**，中间不能有
        明显分割；"十连双红/三红"角标放在**这一组的上方**（大约最上面
        那个头像的位置），因此组容器顶部留一段标题区。
        """
        total = chars[0].get("gold_total") or 0
        r, g, b = _GOLD_GROUP_BG
        box = QFrame()
        # 浅青底（与普通行的灰底只有一点色相差异，用户口径"有一点点区别就行"），
        # 无边框；组内各行透明 → 视觉连成一块
        box.setStyleSheet(
            f"background:rgb({r},{g},{b}); border:none; border-radius:4px;"
        )
        box.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        v = QVBoxLayout(box)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        # ── 组标题区：角标 + 适当加高，保证不会挤到头像/柱子 ──
        head = QWidget()
        head.setFixedHeight(22)
        hl = QHBoxLayout(head)
        hl.setContentsMargins(8, 3, 8, 0)
        hl.setSpacing(0)
        txt = "十连双红" if total == 2 else f"十连{total}红"
        corner = QLabel(txt)
        # 浅青底上用白字对比度偏低，改用亮青白（仍属浅色系，不喧宾夺主）
        corner.setStyleSheet(
            "color:#bfeaf3; font-size:11px; font-weight:bold; "
            "background:transparent; border:none;"
        )
        hl.addWidget(corner)
        hl.addStretch()
        v.addWidget(head)

        for c in chars:
            v.addWidget(self._make_row(c, mode="gold"))
        return box

    def _make_row(self, ch, mode="normal"):
        """一行的实际渲染：头像 + 角色名 + 柱状图 + 日期 + 歪标注

        mode = "normal" → 普通记录：行与行之间用浅白色细线分割（bottom border）
        mode = "gold"   → 双金组内的一条：不画任何分割线（与同组其他条连成一整块）
        """
        pull_count = ch.get("pity")
        name = ch.get("name", "")
        pull_date = ch.get("pull_date")
        off_banner = ch.get("off")
        off_state = ch.get("off_state")

        # 歪/不歪：只有"歪"要标注（用户口径：不歪不标、无从判断也不标）
        is_off = bool(off_banner) and off_state == "off"

        w = QFrame()
        if mode == "gold":
            # 双金组内：纯透明，让外层容器的浅青底透出来 → 组内无缝
            w.setStyleSheet("background:transparent; border:none;")
        else:
            # 普通行：浅白色细线分割（用户口径），只画下边线，避免双线
            w.setStyleSheet(
                "background:#252526; border:none;"
                " border-bottom:1px solid rgba(255,255,255,0.13);"
            )
        w.setFixedHeight(46)
        w.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        row = QHBoxLayout(w)
        row.setContentsMargins(6, 3, 8, 3)
        row.setSpacing(8)

        # 头像：优先按角色名找本地图片，找不到就退回"首字色块"
        row.addWidget(self._make_avatar(name))

        # 角色名（柱体左侧，固定宽度对齐）
        nm = QLabel(name)
        nm.setStyleSheet("color:#e0e0e0; font-size:13px; font-weight:bold; "
                         "border:none; background:transparent;")
        nm.setFixedWidth(84)
        row.addWidget(nm)

        # 柱状图本体
        row.addWidget(self._make_bar(pull_count))

        # 出货日期 (月-日)
        if pull_date:
            date_lbl = QLabel(pull_date)
            date_lbl.setStyleSheet("color:#888; font-size:11px; border:none; background:transparent;")
            row.addWidget(date_lbl)

        row.addStretch()

        # 只标注"歪"（不歪 / 无从判断都不打标签）
        if is_off:
            mk = QLabel("歪")
            mk.setStyleSheet("color:#fff; font-size:11px; font-weight:bold; "
                             "background:#c0392b; border-radius:3px; padding:2px 8px;")
            row.addWidget(mk)
        return w

    def _make_bar(self, pulls):
        """柱体：宽度随抽数增长（封顶 70 抽），颜色按消耗抽数区间，抽数写在柱内

        柱内抽数文字**固定贴柱子最左侧**（与左边缘留 2~3px），所有柱子一致。
        """
        holder = QWidget()
        holder.setStyleSheet("background:transparent; border:none;")
        holder.setFixedHeight(40)

        bar_w = max(_bar_width(pulls), _BAR_MIN_PX)
        holder.setFixedWidth(bar_w)

        bar = QFrame(holder)
        bar.setStyleSheet(
            f"background:{_bar_color(pulls)}; border-radius:3px; border:none;"
        )
        bar.setGeometry(0, 4, bar_w, 32)

        # 柱内抽数文字：纯白标准字体，垂直居中，**固定贴最左侧**（左边距 3px）
        txt = f"{pulls if pulls is not None else 0}抽"
        fs = 12 if bar_w >= 44 else (11 if bar_w >= 36 else 10)
        cnt = QLabel(txt, bar)
        cnt.setStyleSheet(f"color:#ffffff; font-size:{fs}px; border:none; "
                          "background:transparent;")
        cnt.adjustSize()
        cnt.move(3, (32 - cnt.height()) // 2)

        return holder

    def _make_avatar(self, name):
        """角色头像：优先加载本地图片，缺失时退回"首字色块"占位

        素材接口：把图片放到 `assets/avatars/<角色名>.png`（或 .jpg/.webp）即可
        自动生效，无需改代码。路径按 resource_root 解析（只读资源目录）。
        """
        size = 36
        if name:
            for ext in (".png", ".jpg", ".jpeg", ".webp"):
                p = config.resource_root / "assets" / "avatars" / f"{name}{ext}"
                if p.exists():
                    lbl = QLabel()
                    lbl.setFixedSize(size, size)
                    pix = QPixmap(str(p)).scaled(
                        size, size,
                        Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                    lbl.setPixmap(pix)
                    lbl.setStyleSheet("border:1px solid #4a4a4a; border-radius:6px;")
                    return lbl

        # 回退：首字母块（保留原有占位观感，颜色中性灰）
        avatar = QFrame()
        avatar.setFixedSize(size, size)
        avatar.setStyleSheet("background:#3a3a3a; border-radius:6px; border:none;")
        al = QVBoxLayout(avatar)
        al.setContentsMargins(0, 0, 0, 0)
        al.setAlignment(Qt.AlignmentFlag.AlignCenter)
        first_char = name[0] if name else "?"
        cl = QLabel(first_char)
        cl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cl.setStyleSheet("color:#d0d0d0; font-size:16px; font-weight:bold; "
                         "border:none; background:transparent;")
        al.addWidget(cl)
        return avatar

    def _make_pity(self, count):
        """垫抽行：文字"已垫 N 抽"，柱体颜色按抽数区间（<50 绿 / 50-60 黄 / 60-70 红）"""
        w = QFrame()
        # 与普通记录行同一套观感：浅白细线分割，不再留 1px 缝隙
        w.setStyleSheet(
            "background:#2d2d2d; border:none;"
            " border-bottom:1px solid rgba(255,255,255,0.13);"
        )
        w.setFixedHeight(46)
        w.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        row = QHBoxLayout(w)
        row.setContentsMargins(6, 3, 8, 3)
        row.setSpacing(8)

        # 头像位留空（垫抽没有角色）
        av = QLabel()
        av.setFixedSize(36, 36)
        av.setStyleSheet("background:#3a3a3a; border-radius:6px; border:none;")
        row.addWidget(av)
        lb = QLabel(f"已垫 {count} 抽")
        lb.setStyleSheet("color:#c8c8c8; font-size:13px; font-weight:bold; "
                         "border:none; background:transparent;")
        lb.setFixedWidth(84)
        row.addWidget(lb)

        # 垫抽也用柱体表示，长度按同一套刻度（>=70 封顶）
        row.addWidget(self._make_bar(count))
        row.addStretch()
        return w
