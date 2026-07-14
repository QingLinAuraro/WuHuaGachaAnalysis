"""
配置管理模块
读取和解析 config/default_config.yaml
"""

import os
import yaml
from pathlib import Path
from typing import Any, Optional


class Config:
    """全局配置管理器（单例）"""

    _instance: Optional["Config"] = None

    def __new__(cls, *args: Any, **kwargs: Any) -> "Config":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, config_path: Optional[str] = None) -> None:
        if hasattr(self, "_initialized") and self._initialized:
            return
        self._initialized = True

        self._project_root: Path = Path(__file__).parent.parent.resolve()
        self._config_path: str = config_path or str(
            self._project_root / "config" / "default_config.yaml"
        )
        self._data: dict = {}
        self._load()

    def _load(self) -> None:
        """加载YAML配置文件"""
        config_file = Path(self._config_path)
        if config_file.exists():
            with open(config_file, "r", encoding="utf-8") as f:
                self._data = yaml.safe_load(f) or {}
        else:
            self._data = self._defaults()

    def _defaults(self) -> dict:
        """返回默认配置"""
        return {
            "adb": {
                "path": "adb",  # 默认使用系统PATH中的adb，找不到则自动搜索模拟器目录
                "serial": "auto",  # 自动检测设备
                "screenshot_dir": str(self._project_root / "screenshots"),
            },
            "emulator": {
                "type": "auto",  # auto / mumu / ldplayer / bluestacks
                "adb_port": {
                    "mumu": 16384,
                    "ldplayer": 5555,
                    "bluestacks": 5555,
                },
            },
            "game": {
                "package_name": "com.cipaishe.wuhua.bilibili",
            },
            "ocr": {
                "engine": "paddleocr",
                "lang": "ch",
                "use_gpu": False,
            },
            "gacha": {
                "scan_page_delay": 1.5,  # 翻页后等待秒数（增加避免触发保护）
                "record_height_min": 45,  # 每条记录最小高度（像素）
                "record_height_max": 85,  # 每条记录最大高度（像素）
            },
            "database": {
                "path": str(self._project_root / "data" / "gacha.db"),
            },
            "gui": {
                "theme": "dark",
                "window_width": 900,
                "window_height": 600,
            },
        }

    def get(self, key: str, default: Any = None) -> Any:
        """获取配置项，支持点分隔的路径如 'adb.path'"""
        keys = key.split(".")
        value: Any = self._data
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
            else:
                return default
            if value is None:
                return default
        return value

    @property
    def project_root(self) -> Path:
        return self._project_root

    @property
    def data_dir(self) -> Path:
        d = Path(self.get("database.path")).parent
        d.mkdir(parents=True, exist_ok=True)
        return d

    @property
    def screenshot_dir(self) -> Path:
        d = Path(self.get("adb.screenshot_dir"))
        d.mkdir(parents=True, exist_ok=True)
        return d


config = Config()
