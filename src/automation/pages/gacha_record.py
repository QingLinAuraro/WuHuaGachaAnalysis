"""召集记录页按钮

坐标格式统一为 (x, y, w, h)：x/y 为左上角，w 向右、h 向下。
"""

from src.config import config
from src.automation.button import Button

_ROOT = config.resource_root
_THRESHOLD = config.get("automation.image_recognition.template_threshold", 0.8)


# 页面识别
# 底部翻页栏横向居中、宽度随记录页数变化，上一页按钮会水平漂移
# （实测中心 x：>10页 466 / 5页 564 / 2页 637 / 1页 662，y 恒为 585~586）。
# 识别区域需覆盖整个漂移范围，否则页数少的布局会被判成"不在召集记录页"。
CHECK_GACHA_RECORD = Button(
    area=(395, 553, 695, 67),
    button=(395, 553, 695, 67),
    file=str(_ROOT / "assets" / "templates" / "gacha" / "details" / "record" / "page_up.png"),
    similarity=_THRESHOLD,
    name="CHECK_RECORD",
)

# 上一页
BTN_PAGE_UP = Button(
    area=(395, 553, 335, 67),
    button=(413, 561, 106, 50),
    file=str(_ROOT / "assets" / "templates" / "gacha" / "details" / "record" / "page_up.png"),
    similarity=_THRESHOLD,
    name="PAGE_UP",
)

# 下一页
BTN_PAGE_DOWN = Button(
    area=(750, 553, 340, 67),
    button=(962, 564, 108, 43),
    file=str(_ROOT / "assets" / "templates" / "gacha" / "details" / "record" / "page_down.png"),
    similarity=_THRESHOLD,
    name="PAGE_DOWN",
)

# 展开渠道选择面板（记录页右上角的下拉箭头）
# 这里用的是"紧贴框"：搜索区 (1185, 137, 46, 38) 与模板 select.png 尺寸完全相等，
# matchTemplate 的结果矩阵退化成 1×1 —— 等于定点比对，没有任何位移容错。
# 之所以敢这么用（实测数据）：
#   · 该点得分 0.9940，远超阈值 0.8
#   · 左/右/上/下平移后得分全部 ≤ 0.0059 → 唯一性极好，不会误匹配到别处
#   · 不放大，才与下方渠道面板 (y 175~410) 完全不重叠（本框 y 137~175）
# ⚠️ 以后若再换模板，必须保证"模板尺寸 ≤ 搜索区尺寸"，否则会因
#    "搜索区比模板还小" 在 Button._appear_by_template 里直接返回 False。
BTN_SELECT = Button(
    area=(1185, 137, 46, 38),
    button=(1185, 137, 46, 38),
    file=str(_ROOT / "assets" / "templates" / "gacha" / "details" / "record" / "select.png"),
    similarity=_THRESHOLD,
    name="SELECT",
)

# 返回
BTN_BACK = Button(
    area=(522, 638, 247, 56),
    button=(522, 638, 247, 56),
    file=str(_ROOT / "assets" / "templates" / "gacha" / "details" / "record" / "back.png"),
    similarity=_THRESHOLD,
    name="BACK",
)
