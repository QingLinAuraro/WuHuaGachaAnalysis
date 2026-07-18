"""
自动化异常类
"""


class AutomationError(Exception):
    """自动化基础异常"""
    pass


class GameStuckError(AutomationError):
    """游戏卡住异常"""
    def __init__(self, page_name: str = "", timeout: float = 10.0):
        super().__init__(f"游戏卡在页面 '{page_name}' 超过 {timeout:.0f} 秒")
        self.page_name = page_name
        self.timeout = timeout


class PageUnknownError(AutomationError):
    """无法识别的页面异常"""
    def __init__(self, message: str = "无法识别当前游戏页面"):
        super().__init__(message)


class NavigationError(AutomationError):
    """导航失败异常"""
    def __init__(self, from_page: str = "", to_page: str = "", reason: str = ""):
        msg = f"导航失败: {from_page} → {to_page}"
        if reason:
            msg += f" ({reason})"
        super().__init__(msg)
        self.from_page = from_page
        self.to_page = to_page
        self.reason = reason
