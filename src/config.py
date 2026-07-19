"""
配置管理模块
三层配置优先级：user_config.yaml > config/default_config.yaml > 代码默认值
"""
import os
import yaml
from pathlib import Path
from typing import Any, Optional


def get_resource_root() -> Path:
    """资源根目录（只读）：源码、模板、默认配置所在目录"""
    return Path(__file__).parent.parent.resolve()


def get_data_root() -> Path:
    """用户数据根目录（可写）：数据库、截图、日志、用户配置"""
    env = os.environ.get("WUHUA_DATA_DIR", "")
    if env:
        return Path(env)
    return get_resource_root()


class Config:
    """全局配置管理器（单例）"""

    _instance: Optional["Config"] = None

    def __new__(cls, *args: Any, **kwargs: Any) -> "Config":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if hasattr(self, "_initialized") and self._initialized:
            return
        self._initialized = True

        self._resource_root: Path = get_resource_root()
        self._data_root: Path = get_data_root()
        self._default_config_path: Path = (
            self._resource_root / "config" / "default_config.yaml"
        )
        self._user_config_path: Path = self._data_root / "user_config.yaml"
        self._data: dict = {}

        self._ensure_dirs()
        self._load()

    def _ensure_dirs(self) -> None:
        """确保数据目录存在"""
        for d in ["data", "logs", "screenshots"]:
            (self._data_root / d).mkdir(parents=True, exist_ok=True)

    def _load(self) -> None:
        """加载配置：默认值 → default_config.yaml → user_config.yaml"""
        # 第一层：代码默认值
        merged = self._defaults()

        # 第二层：default_config.yaml
        if self._default_config_path.exists():
            try:
                with open(self._default_config_path, "r", encoding="utf-8") as f:
                    default_data = yaml.safe_load(f) or {}
                self._deep_merge(merged, default_data)
            except Exception:
                pass

        # 第三层：user_config.yaml（最高优先级）
        if self._user_config_path.exists():
            try:
                with open(self._user_config_path, "r", encoding="utf-8") as f:
                    user_data = yaml.safe_load(f) or {}
                self._deep_merge(merged, user_data)
            except Exception:
                pass

        self._data = merged

    @staticmethod
    def _deep_merge(base: dict, override: dict) -> None:
        """深度合并 override 到 base"""
        for key, value in override.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                Config._deep_merge(base[key], value)
            else:
                base[key] = value

    def _defaults(self) -> dict:
        """返回代码内置默认值（最终兜底）"""
        return {
            "adb": {
                "path": "adb",
                "serial": "auto",
                "screenshot_dir": str(self._data_root / "screenshots"),
                "search_paths": [
                    "%ProgramFiles%/Netease/MuMu/nx_device/*/shell/adb.exe",
                    "%ProgramFiles%/Netease/MuMu Player 12/shell/adb.exe",
                    "%ProgramFiles%/ldplayer9/adb.exe",
                    "%ProgramFiles%/BlueStacks_nxt/HD-Adb.exe",
                ],
            },
            "gacha": {
                "scan_page_delay": 2.0,
            },
            "database": {
                "path": str(self._data_root / "data" / "gacha.db"),
            },
            "gui": {
                "window_width": 900,
                "window_height": 600,
                "last_account_id": 1,
            },
            "automation": {
                "image_recognition": {
                    "action_interval": 0.5,
                    "color_tolerance": 10,
                    "max_retries": 3,
                    "min_height": 360,
                    "min_width": 640,
                    "navigation_timeout": 30,
                    "template_threshold": 0.8,
                },
            },
        }

    # ---- 公共 API ----

    @property
    def resource_root(self) -> Path:
        """资源根目录（只读）：模板图片、默认配置等"""
        return self._resource_root

    @property
    def data_root(self) -> Path:
        """用户数据根目录（可写）：数据库、截图、日志"""
        return self._data_root

    @property
    def screenshot_dir(self) -> Path:
        d = Path(self.get("adb.screenshot_dir"))
        d.mkdir(parents=True, exist_ok=True)
        return d

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

    def set(self, key: str, value: Any) -> None:
        """设置配置项（写入 user_config.yaml），支持点分隔路径"""
        keys = key.split(".")
        target: dict = self._data
        for k in keys[:-1]:
            if k not in target or not isinstance(target[k], dict):
                target[k] = {}
            target = target[k]
        target[keys[-1]] = value
        self._save()

    def _save(self) -> None:
        """保存到 user_config.yaml（不污染 default_config.yaml）"""
        try:
            with open(self._user_config_path, "w", encoding="utf-8") as f:
                yaml.safe_dump(
                    self._data, f, allow_unicode=True, default_flow_style=False
                )
        except Exception:
            pass


config = Config()
