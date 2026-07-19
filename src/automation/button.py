"""
Button 统一识别对象
参照 ALAS 设计：多层级图像识别（颜色 → 模板匹配 → 全图搜索）

每个按钮支持三级检测：
  1. 颜色检测（最快）   — 对比 ROI 区域平均颜色
  2. 模板匹配（中等）   — cv2.matchTemplate
  3. 全图搜索（最慢）   — 在整个截图中搜索模板位置
"""

import cv2
import numpy as np
from pathlib import Path
from typing import Optional

from loguru import logger


# ═══════════════════════════════════════════════════════════
# 图像工具函数（参照 ALAS module/base/utils.py）
# ═══════════════════════════════════════════════════════════

def get_color(image: np.ndarray, area: tuple[int, int, int, int]) -> tuple[int, int, int]:
    """获取图像指定区域的平均颜色 (r, g, b)

    Args:
        image: BGR 格式 numpy 数组
        area: (x1, y1, x2, y2)
    """
    x1, y1, x2, y2 = area
    region = image[y1:y2, x1:x2]
    if region.size == 0:
        return 0, 0, 0
    mean = cv2.mean(region)
    return int(mean[2]), int(mean[1]), int(mean[0])  # BGR → RGB


def color_similar(
    color1: tuple[int, int, int],
    color2: tuple[int, int, int],
    threshold: int = 10,
) -> bool:
    """Photoshop 风格的容差比较

    容差计算: max(positive_rgb_diffs) - min(negative_rgb_diffs)
    与 Photoshop 中的颜色容差概念一致。

    Args:
        color1: (r, g, b)
        color2: (r, g, b)
        threshold: 默认 10
    """
    diff_r = color1[0] - color2[0]
    diff_g = color1[1] - color2[1]
    diff_b = color1[2] - color2[2]

    max_positive = 0
    max_negative = 0
    if diff_r > max_positive:
        max_positive = diff_r
    elif diff_r < max_negative:
        max_negative = diff_r
    if diff_g > max_positive:
        max_positive = diff_g
    elif diff_g < max_negative:
        max_negative = diff_g
    if diff_b > max_positive:
        max_positive = diff_b
    elif diff_b < max_negative:
        max_negative = diff_b

    diff = max_positive - max_negative
    return diff <= threshold


def color_similarity_2d(image: np.ndarray, color: tuple[int, int, int]) -> np.ndarray:
    """像素级颜色相似度热力图

    Args:
        image: BGR 格式图像
        color: (r, g, b) 目标颜色

    Returns:
        单通道 uint8 数组，值越大越相似（255 = 完全匹配）
    """
    # BGR → RGB then compare
    diff = cv2.subtract(image, (*color, 0))
    r, g, b = cv2.split(diff)
    cv2.max(r, g, dst=r)
    cv2.max(r, b, dst=r)
    positive = r

    cv2.subtract((*color, 0), image, dst=diff)
    r, g, b = cv2.split(diff)
    cv2.max(r, g, dst=r)
    cv2.max(r, b, dst=r)
    negative = r

    cv2.add(positive, negative, dst=positive)
    cv2.subtract(255, positive, dst=positive)
    return positive


def rgb2luma(image: np.ndarray) -> np.ndarray:
    """RGB 转亮度 (YUV Y通道)"""
    image = cv2.cvtColor(image, cv2.COLOR_RGB2YUV)
    luma, _, _ = cv2.split(image)
    return luma


def extract_letters(
    image: np.ndarray,
    letter: tuple[int, int, int] = (255, 255, 255),
    threshold: int = 128,
) -> np.ndarray:
    """从背景中提取文字（用于 OCR 预处理）

    Args:
        image: BGR 格式
        letter: 文字颜色 (r, g, b)，默认白色
        threshold: 二值化阈值

    Returns:
        单通道灰度图，文字区域为黑色，背景为白色
    """
    diff = cv2.subtract(image, (*letter, 0))
    r, g, b = cv2.split(diff)
    cv2.max(r, g, dst=r)
    cv2.max(r, b, dst=r)
    positive = r

    cv2.subtract((*letter, 0), image, dst=diff)
    r, g, b = cv2.split(diff)
    cv2.max(r, g, dst=r)
    cv2.max(r, b, dst=r)
    negative = r

    cv2.add(positive, negative, dst=positive)
    if threshold != 255:
        cv2.convertScaleAbs(positive, alpha=255.0 / threshold, dst=positive)
    return positive


def crop(image: np.ndarray, area: tuple[int, int, int, int]) -> np.ndarray:
    """安全裁剪图像区域"""
    x1, y1, x2, y2 = area
    h, w = image.shape[:2]
    x1 = max(0, x1)
    y1 = max(0, y1)
    x2 = min(w, x2)
    y2 = min(h, y2)
    return image[y1:y2, x1:x2]


def load_image(file_path: str, area: Optional[tuple[int, int, int, int]] = None) -> np.ndarray:
    """加载图像，支持中文路径

    Args:
        file_path: 图像文件路径
        area: 可选裁剪区域
    """
    img_array = np.fromfile(str(file_path), dtype=np.uint8)
    img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
    if img is None:
        raise FileNotFoundError(f"无法加载图像: {file_path}")
    if area is not None:
        img = crop(img, area)
    return img


def area_offset(
    area: tuple[int, int, int, int],
    offset: tuple[int, int],
) -> tuple[int, int, int, int]:
    """平移区域"""
    return (
        area[0] + offset[0],
        area[1] + offset[1],
        area[2] + offset[0],
        area[3] + offset[1],
    )


def random_point_in_area(
    area: tuple[int, int, int, int],
) -> tuple[int, int]:
    """在区域内随机取一个点，偏向中心的正态分布（模拟人类点击）"""
    x1, y1, x2, y2 = area
    cx = (x1 + x2) // 2
    cy = (y1 + y2) // 2
    sigma_x = max(1, (x2 - x1) // 6)
    sigma_y = max(1, (y2 - y1) // 6)
    x = int(np.random.normal(cx, sigma_x))
    y = int(np.random.normal(cy, sigma_y))
    x = max(x1, min(x2 - 1, x))
    y = max(y1, min(y2 - 1, y))
    return x, y


# ═══════════════════════════════════════════════════════════
# Button 类
# ═══════════════════════════════════════════════════════════

class Button:
    """统一按钮对象 — 支持三层识别：颜色 → 模板匹配 → 全图搜索

    使用示例:
        # 纯颜色检测按钮
        CHECK_MAIN = Button(
            area=(100, 200, 200, 240),
            color=(255, 200, 100),
            button=(100, 200, 200, 240),
            name="main_check",
        )

        # 模板匹配按钮
        NEXT_PAGE = Button(
            area=(1100, 600, 1280, 700),
            button=(1100, 600, 1280, 700),
            file="assets/templates/gacha_record/next_page.png",
            similarity=0.8,
            name="next_page",
        )

        # 使用时
        if btn.appear(screenshot):
            pos = btn.coord()
            adb.click(*pos)
    """

    def __init__(
        self,
        area: tuple[int, int, int, int] = (0, 0, 0, 0),
        color: Optional[tuple[int, int, int]] = None,
        button: Optional[tuple[int, int, int, int]] = None,
        file: Optional[str] = None,
        similarity: float = 0.85,
        name: str = "BUTTON",
    ):
        """
        Args:
            area: 按钮检测区域 (x1, y1, x2, y2)
            color: 期望颜色 (r, g, b)，None 表示不用颜色检测
            button: 可点击区域 (x1, y1, x2, y2)，默认与 area 相同
            file: 模板图片路径，None 表示不用模板匹配
            similarity: 模板匹配阈值
            name: 按钮名称（用于日志）
        """
        self.area = area
        self.color = color
        self.button = button if button is not None else area
        self.file = file
        self.similarity = similarity
        self.name = name

        # 模板缓存
        self._template: Optional[np.ndarray] = None
        self._template_loaded: bool = False

        # 最近一次匹配信息
        self._match_point: Optional[tuple[int, int]] = None
        self._match_score: float = 0.0

    def __str__(self) -> str:
        return self.name

    __repr__ = __str__

    def __bool__(self) -> bool:
        return True

    def __eq__(self, other) -> bool:
        if isinstance(other, Button):
            return self.name == other.name
        return False

    def __hash__(self) -> int:
        return hash(self.name)

    # ── 核心检测方法 ──────────────────────────────────

    def appear(self, image: np.ndarray, threshold: int = 10) -> bool:
        """检查按钮是否出现在截图中

        检测顺序（由快到慢）：
          1. 有 color → 颜色检测
          2. 有 file  → 模板匹配
          3. 都没有   → 总是返回 True（纯坐标按钮，用作始终可点的跳转）

        Args:
            image: BGR 格式截图
            threshold: 颜色容差（仅颜色检测时使用）

        Returns:
            bool
        """
        # 三级检测：颜色 → 模板 → 坐标
        if self.color is not None:
            return self._appear_by_color(image, threshold)
        elif self.file is not None:
            return self._appear_by_template(image)
        else:
            # 纯坐标按钮：始终"可见"
            return True

    def _appear_by_color(self, image: np.ndarray, threshold: int) -> bool:
        """通过颜色检测判断按钮是否可见"""
        actual_color = get_color(image, self.area)
        return color_similar(actual_color, self.color, threshold)

    def _appear_by_template(self, image: np.ndarray) -> bool:
        """通过模板匹配判断按钮是否可见"""
        self._ensure_template()
        if self._template is None:
            return False

        search_region = crop(image, self.area)
        if search_region.size == 0:
            return False

        t_h, t_w = self._template.shape[:2]
        if search_region.shape[0] < t_h or search_region.shape[1] < t_w:
            return False

        result = cv2.matchTemplate(search_region, self._template, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(result)

        self._match_score = float(max_val)
        if max_val >= self.similarity:
            self._match_point = (
                self.area[0] + max_loc[0] + t_w // 2,
                self.area[1] + max_loc[1] + t_h // 2,
            )
            return True

        logger.info(
            "模板匹配失败 '{}': score={:.3f} < threshold={:.2f} (crop={}x{} tpl={}x{})",
            self.name, max_val, self.similarity,
            search_region.shape[1], search_region.shape[0], t_w, t_h,
        )
        return False

    def match(
        self, image: np.ndarray
    ) -> Optional[tuple[int, int, int, int, float]]:
        """模板匹配，返回匹配区域和分数

        Returns:
            (x, y, w, h, score) 或 None
        """
        self._ensure_template()
        if self._template is None:
            return None

        search_region = crop(image, self.area)
        if search_region.size == 0:
            return None

        t_h, t_w = self._template.shape[:2]
        if search_region.shape[0] < t_h or search_region.shape[1] < t_w:
            return None

        result = cv2.matchTemplate(search_region, self._template, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(result)

        self._match_score = float(max_val)
        if max_val >= self.similarity:
            x = self.area[0] + max_loc[0]
            y = self.area[1] + max_loc[1]
            self._match_point = (x + t_w // 2, y + t_h // 2)
            return (x, y, t_w, t_h, float(max_val))

        return None

    def match_multi(
        self, image: np.ndarray, min_distance: int = 10
    ) -> list[tuple[int, int, int, int, float]]:
        """找出截图中所有匹配位置（用于列表项等）

        Args:
            image: 截图
            min_distance: 匹配点之间的最小距离（去重用）

        Returns:
            [(x, y, w, h, score), ...]
        """
        self._ensure_template()
        if self._template is None:
            return []

        search_region = crop(image, self.area)
        if search_region.size == 0:
            return []

        t_h, t_w = self._template.shape[:2]
        if search_region.shape[0] < t_h or search_region.shape[1] < t_w:
            return []

        result = cv2.matchTemplate(search_region, self._template, cv2.TM_CCOEFF_NORMED)

        # 找到所有超过阈值的匹配位置
        locations = np.where(result >= self.similarity)
        matches = []
        seen = []

        for pt in zip(*locations[::-1]):  # (x, y)
            x = self.area[0] + pt[0]
            y = self.area[1] + pt[1]
            score = float(result[pt[1], pt[0]])

            # 去重：跳过与已记录点太近的匹配
            too_close = False
            for sx, sy in seen:
                if abs(x - sx) < min_distance and abs(y - sy) < min_distance:
                    too_close = True
                    break
            if too_close:
                continue

            seen.append((x, y))
            matches.append((x, y, t_w, t_h, score))

        return matches

    # ── 坐标方法 ──────────────────────────────────────

    def coord(self) -> tuple[int, int]:
        """获取按钮的推荐点击坐标

        优先使用最近一次模板匹配的结果，否则在 button 区域内随机取点
        """
        if self._match_point is not None:
            return self._match_point
        return random_point_in_area(self.button)

    def button_center(self) -> tuple[int, int]:
        """获取 button 区域的中心坐标"""
        x1, y1, x2, y2 = self.button
        return ((x1 + x2) // 2, (y1 + y2) // 2)

    @property
    def is_detection_only(self) -> bool:
        """是否仅为检测用途（无点击区域）"""
        x1, y1, x2, y2 = self.button
        return x1 == 0 and y1 == 0 and x2 == 0 and y2 == 0

    # ── 内部方法 ──────────────────────────────────────

    def _ensure_template(self) -> None:
        """延迟加载模板图像"""
        if self._template_loaded:
            return
        self._template_loaded = True

        if self.file is None:
            return

        file_path = Path(self.file)
        if not file_path.exists():
            logger.warning("模板文件不存在: {}", self.file)
            return

        try:
            img_array = np.fromfile(str(file_path), dtype=np.uint8)
            self._template = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
            if self._template is not None:
                logger.debug("加载模板: {} ({})", file_path.name, self.name)
        except Exception as e:
            logger.error("加载模板失败: {} - {}", self.file, e)

    def release(self) -> None:
        """释放模板缓存（内存管理）"""
        self._template = None
        self._template_loaded = False
        self._match_point = None
        self._match_score = 0.0

    def reset_match(self) -> None:
        """重置匹配状态"""
        self._match_point = None
        self._match_score = 0.0

    # ── 衍生 Button ───────────────────────────────────

    def crop_button(
        self,
        area: tuple[int, int, int, int],
        image: Optional[np.ndarray] = None,
        name: Optional[str] = None,
    ) -> "Button":
        """基于相对坐标创建子按钮"""
        name = name or self.name
        new_area = area_offset(area, offset=self.area[:2])
        new_button = area_offset(area, offset=self.button[:2])
        btn = Button(
            area=new_area,
            color=self.color,
            button=new_button,
            file=self.file,
            similarity=self.similarity,
            name=name,
        )
        if image is not None:
            btn.color = get_color(image, btn.area)
        return btn

    def move_button(
        self, vector: tuple[int, int], name: Optional[str] = None
    ) -> "Button":
        """平移按钮"""
        name = name or self.name
        return Button(
            area=area_offset(self.area, vector),
            color=self.color,
            button=area_offset(self.button, vector),
            file=self.file,
            similarity=self.similarity,
            name=name,
        )


# ═══════════════════════════════════════════════════════════
# ButtonGrid — 网格按钮生成器（参考 ALAS）
# ═══════════════════════════════════════════════════════════

class ButtonGrid:
    """从网格模板生成一组按钮

    用于整齐排列的列表项（如抽卡记录条目）。

    示例:
        grid = ButtonGrid(
            origin=(0, 220),       # 网格左上角
            delta=(0, 34),          # 每个按钮间距 (dx, dy)
            button_shape=(1280, 34), # 每个按钮大小
            grid_shape=(1, 10),     # 1 列 10 行
        )
        for _, _, btn in grid.generate():
            if btn.appear(screenshot):
                ...
    """

    def __init__(
        self,
        origin: tuple[int, int],
        delta: tuple[int, int],
        button_shape: tuple[int, int],
        grid_shape: tuple[int, int],
        name: str = "GRID",
    ):
        self.origin = np.array(origin)
        self.delta = np.array(delta)
        self.button_shape = np.array(button_shape)
        self.grid_shape = np.array(grid_shape)
        self.name = name

    def __getitem__(self, item: tuple[int, int]) -> Button:
        base = np.round(np.array(item) * self.delta + self.origin).astype(int)
        area = tuple(np.append(base, base + self.button_shape))
        return Button(
            area=area,
            button=area,
            name=f"{self.name}_{item[0]}_{item[1]}",
        )

    def generate(self):
        """生成所有按钮 (x, y, Button)"""
        for y in range(self.grid_shape[1]):
            for x in range(self.grid_shape[0]):
                yield x, y, self[x, y]

    @property
    def buttons(self) -> list[Button]:
        return [btn for _, _, btn in self.generate()]
