"""
WuHuaGachaAnalysis 入口文件
"""

import sys
from pathlib import Path

# 确保项目根目录在 sys.path 中
_project_root = Path(__file__).parent.parent.resolve()
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from loguru import logger


def setup_logging() -> None:
    """配置日志系统"""
    log_dir = Path(__file__).parent.parent / "logs"
    log_dir.mkdir(exist_ok=True)

    logger.remove()  # 移除默认handler
    logger.add(
        sys.stdout,
        format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>",
        level="INFO",
    )
    logger.add(
        log_dir / "wuhua_{time:YYYY-MM-DD}.log",
        rotation="10 MB",
        retention="30 days",
        encoding="utf-8",
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} | {message}",
        level="DEBUG",
    )
    logger.info("日志系统初始化完成")


def main() -> None:
    """主入口"""
    setup_logging()
    logger.info("物华弥新抽卡分析器 v{}", __import__("src").__version__)

    # from src.storage.database import db
    # count = db.clear_all()
    # logger.info("数据库已清空 ({} 条旧记录)", count)

    # 启动 GUI
    from src.gui.main_window import launch_gui
    launch_gui()


if __name__ == "__main__":
    main()
