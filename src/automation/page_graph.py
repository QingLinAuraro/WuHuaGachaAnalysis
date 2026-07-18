"""
页面图系统 — 参照 ALAS module/ui/page.py

将游戏 UI 建模为有向图：
  - Page 节点 = 游戏页面（通过 check_button 识别）
  - Button 边 = 点击按钮可从一个页面跳转到另一个页面

提供 A* 最短路径寻路，实现"从任意页面自动导航到目标页面"。
"""

import time
from pathlib import Path
from typing import Optional, Callable

import numpy as np
from loguru import logger

from src.automation.button import Button
from src.automation.errors import (
    GameStuckError,
    PageUnknownError,
    NavigationError,
)


class Page:
    """游戏页面节点

    Attributes:
        name: 页面名称（全局唯一标识）
        check_button: 用于识别"我在这一页"的按钮
        links: {destination Page → 跳转用的 Button}
        parent: A* 路径反指针（运行时计算）
    """

    # 全局页面注册表 {name → Page}
    all_pages: dict[str, "Page"] = {}

    @classmethod
    def clear_connection(cls) -> None:
        """清除所有页面的 parent 指针（每次路径计算前调用）"""
        for page in cls.all_pages.values():
            page.parent = None

    @classmethod
    def init_connection(cls, destination: "Page") -> None:
        """A* 最短路径计算（BFS 从目标反向搜索）

        填充每个页面的 parent 字段，形成从任意页面到 destination 的最短路径。

        Args:
            destination: 目标页面
        """
        cls.clear_connection()

        visited = {destination}
        while True:
            new = visited.copy()
            for page in visited:
                for link in cls.iter_pages():
                    if link in visited:
                        continue
                    if page in link.links:
                        link.parent = page
                        new.add(link)
            if len(new) == len(visited):
                break
            visited = new

    @classmethod
    def iter_pages(cls):
        """遍历所有已注册页面"""
        return cls.all_pages.values()

    @classmethod
    def iter_check_buttons(cls):
        """遍历所有页面的 check_button"""
        for page in cls.all_pages.values():
            yield page.check_button

    def __init__(self, check_button: Button):
        """
        Args:
            check_button: 用于识别此页面的按钮（必须有 appearance 检测能力）
        """
        self.check_button = check_button
        self.links: dict[Page, Button] = {}  # {destination → transit_button}
        self.parent: Optional[Page] = None   # A* 路径：parent 是下一步要去的页面

        # 从调用栈自动获取变量名作为页面名称
        import traceback
        (_, _, _, text) = traceback.extract_stack()[-2]
        self.name = text[:text.find("=")].strip() if "=" in text else text.strip()

        Page.all_pages[self.name] = self
        logger.debug("注册页面: {}", self.name)

    def __eq__(self, other) -> bool:
        if isinstance(other, Page):
            return self.name == other.name
        return False

    def __hash__(self) -> int:
        return hash(self.name)

    def __str__(self) -> str:
        return self.name

    __repr__ = __str__

    def link(self, button: Button, destination: "Page") -> None:
        """添加一条有向边：点击 button → 到达 destination"""
        self.links[destination] = button
        logger.debug("页面连接: {} --[{}]--> {}", self.name, button.name, destination.name)


class PageGraph:
    """页面图 — 提供识别和导航能力

    使用方式:
        graph = PageGraph()
        graph.register_pages(page_main, page_gacha_home, page_gacha_record)

        screenshot = adb.screenshot_validate()
        current = graph.get_current_page(screenshot)

        graph.goto(page_gacha_record, screenshot_fn, click_fn)
    """

    def __init__(self, config: Optional[dict] = None):
        self._pages: list[Page] = []
        self._config = config or {}
        self._nav_timeout: float = self._config.get("navigation_timeout", 30.0)
        self._action_interval: float = self._config.get("action_interval", 0.5)
        self._max_retries: int = self._config.get("max_retries", 3)

        # 卡住检测
        self._stuck_start: float = 0.0
        self._stuck_page: Optional[str] = None

    @staticmethod
    def register_pages(*pages: Page) -> None:
        """注册所有页面到全局注册表

        页面在创建时会自动添加到 Page.all_pages，
        此方法是批量注册的便捷入口。
        """
        for page in pages:
            if page.name not in Page.all_pages:
                Page.all_pages[page.name] = page
        logger.info("页面图已注册 {} 个页面", len(Page.all_pages))

    # ── 页面识别 ──────────────────────────────────────

    def get_current_page(
        self,
        screenshot: np.ndarray,
    ) -> Optional[Page]:
        """识别当前截图属于哪个页面

        遍历所有已注册页面，用 check_button.appear() 检测。
        跳过无检测能力的页面（无 file 且无 color 的纯坐标按钮）。

        Args:
            screenshot: BGR 格式截图

        Returns:
            匹配的 Page 或 None（未知页面 / 无可用的检测模板）
        """
        detectable_pages = 0
        best_name = ""
        best_score = 0.0
        for page in Page.iter_pages():
            btn = page.check_button
            # 跳过无检测能力的 check_button（没模板也没颜色 = 无法识别）
            if btn.file is None and btn.color is None:
                continue
            detectable_pages += 1
            try:
                if btn.appear(screenshot):
                    logger.debug("当前页面: {}", page.name)
                    return page
                if btn._match_score > best_score:
                    best_score = btn._match_score
                    best_name = page.name
            except Exception as e:
                logger.debug("检测页面 {} 时出错: {}", page.name, e)
                continue

        if detectable_pages == 0:
            logger.debug("所有页面均无可用的检测模板，无法识别")
        else:
            logger.warning(
                "无法识别当前页面 ({}x{}, {} 个页面, 最高分 {}={:.3f})",
                screenshot.shape[1], screenshot.shape[0],
                detectable_pages, best_name, best_score,
            )
        return None

    def is_page(self, screenshot: np.ndarray, page: Page) -> bool:
        """快速判断是否在指定页面

        如果 check_button 无检测能力（无file且无color），返回 False。
        """
        btn = page.check_button
        if btn.file is None and btn.color is None:
            return False  # 无法检测，保守返回 False
        try:
            return btn.appear(screenshot)
        except Exception:
            return False

    # ── 导航 ──────────────────────────────────────────

    def goto(
        self,
        destination: Page,
        screenshot_fn: Callable[[], Optional[np.ndarray]],
        click_fn: Callable[[int, int], bool],
        max_retries: Optional[int] = None,
    ) -> bool:
        """从当前页面导航到目标页面

        完整的导航流程：
          1. 截图 → 识别当前页面
          2. 用 A* (BFS) 计算最短路径
          3. 沿路径逐跳点击 + 验证到达
          4. 每跳检测并处理意外弹窗
          5. 检测卡住状态

        Args:
            destination: 目标页面
            screenshot_fn: 截图回调 → np.ndarray 或 None
            click_fn: 点击回调 (x, y) → bool
            max_retries: 最大重试次数（None 使用默认值）

        Returns:
            True 表示到达目标页面
        """
        max_retries = max_retries or self._max_retries

        logger.info("页面导航: → {}", destination.name)

        # 计算 A* 路径
        Page.init_connection(destination)

        for hop in range(max_retries * 3):  # 总体保护（最多 3 * 跳数 次尝试）
            screenshot = screenshot_fn()
            if screenshot is None:
                logger.error("截图失败")
                raise NavigationError(
                    from_page="unknown",
                    to_page=destination.name,
                    reason="截图失败",
                )

            current = self.get_current_page(screenshot)

            # 已在目标页面
            if current == destination:
                logger.info("已到达目标页面: {}", destination.name)
                self._reset_stuck()
                return True

            # 未知页面 → 尝试返回
            if current is None:
                logger.warning("当前页面未知，尝试返回处理")
                if not self._handle_unknown(screenshot, screenshot_fn, click_fn):
                    raise PageUnknownError("无法识别当前页面且无法恢复")
                time.sleep(self._action_interval)
                continue

            # 检查路径
            if current.parent is None:
                logger.error("页面 '{}' 无法到达 '{}'（无路径）", current.name, destination.name)
                raise NavigationError(
                    from_page=current.name,
                    to_page=destination.name,
                    reason="无可用路径",
                )

            # 获取当前页面到 parent 的跳转按钮
            next_page = current.parent
            transit_button = current.links.get(next_page)
            if transit_button is None:
                logger.error("页面 '{}' 缺少到 '{}' 的跳转按钮", current.name, next_page.name)
                raise NavigationError(
                    from_page=current.name,
                    to_page=next_page.name,
                    reason="缺少跳转按钮",
                )

            # 执行一次跳转：点击 → 等待 → 验证
            if self._execute_hop(
                current, next_page, transit_button,
                screenshot_fn, click_fn,
            ):
                time.sleep(self._action_interval)
                continue
            else:
                # 跳转失败，可能卡住了
                logger.warning("跳转 {} → {} 失败", current.name, next_page.name)
                if self._check_stuck(current.name):
                    raise GameStuckError(page_name=current.name, timeout=self._nav_timeout)
                time.sleep(self._action_interval)

        raise NavigationError(
            to_page=destination.name,
            reason=f"超过最大重试次数 ({max_retries})",
        )

    def ensure(
        self,
        destination: Page,
        screenshot_fn: Callable[[], Optional[np.ndarray]],
        click_fn: Callable[[int, int], bool],
    ) -> bool:
        """goto() 的便捷包装：先检查，已在目标页则跳过"""
        screenshot = screenshot_fn()
        if screenshot is not None and self.is_page(screenshot, destination):
            logger.info("已在目标页面: {}", destination.name)
            return True
        return self.goto(destination, screenshot_fn, click_fn)

    # ── 单跳执行 ──────────────────────────────────────

    def _execute_hop(
        self,
        from_page: Page,
        to_page: Page,
        button: Button,
        screenshot_fn: Callable[[], Optional[np.ndarray]],
        click_fn: Callable[[int, int], bool],
    ) -> bool:
        """执行一次页面跳转：确认按钮可见 → 点击 → 验证到达

        Args:
            from_page: 起始页面
            to_page: 目标页面
            button: 跳转按钮
            screenshot_fn: 截图回调
            click_fn: 点击回调

        Returns:
            True 表示成功到达 to_page
        """
        # 1. 确认按钮在截图中可见
        screenshot = screenshot_fn()
        if screenshot is None:
            return False

        if not button.appear(screenshot):
            # 可能已经不在 from_page 了，重新检查
            current = self.get_current_page(screenshot)
            if current == to_page:
                return True  # 已经到达
            logger.warning("按钮 '{}' 在页面 '{}' 中不可见", button.name, from_page.name)
            return False

        # 2. 找到点击坐标并点击
        # 先用模板匹配精确定位
        if button.file:
            match_result = button.match(screenshot)
            if match_result:
                x, y, w, h, score = match_result
                click_pos = (x + w // 2, y + h // 2)
                logger.debug("模板匹配定位: {} @ ({}, {}) score={:.2f}", button.name, *click_pos, score)
            else:
                click_pos = button.coord()
        else:
            click_pos = button.coord()

        logger.info("点击 {} ({}, {})", button.name, click_pos[0], click_pos[1])
        click_fn(*click_pos)

        # 3. 等待并验证到达目标页
        return self._wait_for_page(to_page, screenshot_fn, timeout=5.0)

    def _wait_for_page(
        self,
        page: Page,
        screenshot_fn: Callable[[], Optional[np.ndarray]],
        timeout: float = 5.0,
        interval: float = 0.5,
    ) -> bool:
        """循环截图等待直到识别到目标页面

        Args:
            page: 等待的目标页面
            screenshot_fn: 截图回调
            timeout: 超时时间（秒）
            interval: 截图间隔（秒）

        Returns:
            True 表示到达目标页面
        """
        start = time.time()
        while time.time() - start < timeout:
            time.sleep(interval)
            screenshot = screenshot_fn()
            if screenshot is None:
                continue

            # 检查是否到达目标页
            if self.is_page(screenshot, page):
                logger.debug("已到达页面: {}", page.name)
                return True

            # 检查是否有弹窗
            if self._detect_popup(screenshot):
                logger.info("检测到弹窗，尝试关闭...")
                self._close_popup(screenshot_fn)

        logger.warning("等待页面 '{}' 超时 ({:.1f}s)", page.name, timeout)
        return False

    # ── 弹窗处理 ──────────────────────────────────────

    def _detect_popup(self, screenshot: np.ndarray) -> bool:
        """检测意外弹窗

        策略：检测常见弹窗特征（后续可添加模板匹配）
        目前使用简单策略：如果无法匹配任何已知页面，可能是弹窗。
        """
        # TODO: 在 assets/templates/shared/ 中添加常见弹窗关闭按钮模板
        return False

    def _close_popup(
        self,
        screenshot_fn: Callable[[], Optional[np.ndarray]],
    ) -> bool:
        """尝试关闭弹窗（点击屏幕中心或返回键）

        TODO: 通过模板匹配找到关闭按钮并点击
        目前使用简单策略。
        """
        # 弹窗通常可以通过返回键关闭
        logger.info("尝试关闭弹窗")
        return True

    # ── 未知页面处理 ──────────────────────────────────

    def _handle_unknown(
        self,
        screenshot: np.ndarray,
        screenshot_fn: Callable[[], Optional[np.ndarray]],
        click_fn: Callable[[int, int], bool],
    ) -> bool:
        """处理无法识别的页面：尝试返回或关闭"""
        # 策略：先尝试 send back，再尝试点击屏幕中心
        logger.info("处理未知页面...")
        return True  # 由上层调用 goto() 的循环重试

    # ── 卡住检测 ──────────────────────────────────────

    def _check_stuck(self, page_name: str) -> bool:
        """检测是否卡在某个页面太久"""
        now = time.time()
        if self._stuck_page != page_name:
            self._stuck_page = page_name
            self._stuck_start = now
            return False
        if now - self._stuck_start > self._nav_timeout:
            return True
        return False

    def _reset_stuck(self) -> None:
        """重置卡住状态"""
        self._stuck_page = None
        self._stuck_start = 0.0


# ═══════════════════════════════════════════════════════════
# 物华弥新页面定义
# ═══════════════════════════════════════════════════════════

def build_wuhua_pages() -> tuple[Page, ...]:
    """构建物华弥新的页面图

    按钮定义在各页面文件中:
      src/automation/pages/main.py       → 主界面按钮
      src/automation/pages/gacha_home.py → 招集主页按钮
      src/automation/pages/gacha_details.py → 概率详情按钮
      src/automation/pages/gacha_record.py → 召集记录按钮

    修改按钮坐标 → 编辑对应的页面文件
    添加新页面   → 复制一个页面文件改坐标，再在这里加 Page + link
    """
    from src.automation.pages.main import CHECK_MAIN, BTN_GACHA
    from src.automation.pages.gacha_home import CHECK_GACHA_HOME, BTN_DETAILS, BTN_BACK1
    from src.automation.pages.gacha_details import CHECK_GACHA_DETAILS, BTN_GACHA_RECORD, BTN_BACK as BTN_BACK_DETAILS
    from src.automation.pages.gacha_record import CHECK_GACHA_RECORD, BTN_SELECT, BTN_BACK as BTN_BACK_RECORD

    # ── 页面注册 ──
    PAGE_MAIN = Page(CHECK_MAIN)
    PAGE_GACHA_HOME = Page(CHECK_GACHA_HOME)
    PAGE_GACHA_DETAILS = Page(CHECK_GACHA_DETAILS)
    PAGE_GACHA_RECORD = Page(CHECK_GACHA_RECORD)

    # ── 连线（A* 自动寻路） ──
    # 主界面 → 招集页
    PAGE_MAIN.link(BTN_GACHA, PAGE_GACHA_HOME)

    # 招集页 → 召集详情 / 返回
    PAGE_GACHA_HOME.link(BTN_DETAILS, PAGE_GACHA_DETAILS)
    PAGE_GACHA_HOME.link(BTN_BACK1, PAGE_MAIN)

    # 召集详情 → 召集记录 / 返回
    PAGE_GACHA_DETAILS.link(BTN_GACHA_RECORD, PAGE_GACHA_RECORD)
    PAGE_GACHA_DETAILS.link(BTN_BACK_DETAILS, PAGE_GACHA_HOME)

    # 召集记录 → 选择卡池 / 返回
    PAGE_GACHA_RECORD.link(BTN_SELECT, PAGE_GACHA_RECORD)
    PAGE_GACHA_RECORD.link(BTN_BACK_RECORD, PAGE_GACHA_HOME)

    logger.info(
        "页面图: {} 页, {} 边 ({} 页有检测模板)",
        len(Page.all_pages),
        sum(len(p.links) for p in Page.all_pages.values()),
        sum(1 for p in Page.all_pages.values()
            if p.check_button.file is not None or p.check_button.color is not None),
    )

    return PAGE_MAIN, PAGE_GACHA_HOME, PAGE_GACHA_RECORD


# ── 便捷属性获取 ──────────────────────────────────────

def get_page(name: str) -> Optional[Page]:
    """按名称获取已注册页面"""
    return Page.all_pages.get(name)


def get_page_names() -> list[str]:
    """获取所有已注册页面名称"""
    return list(Page.all_pages.keys())
