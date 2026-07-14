"""
ADB 客户端
封装 ADB 命令，提供连接、截图、点击、滑动等操作
"""

import subprocess
import re
import time
from pathlib import Path
from typing import Optional

from loguru import logger

from src.config import config


class ADBClient:
    """ADB 客户端封装"""

    def __init__(self, serial: Optional[str] = None) -> None:
        adb_path = config.get("adb.path", "adb")
        if adb_path == "adb":
            adb_path = find_adb()
        self._adb_path: str = adb_path
        self._serial: Optional[str] = serial

    # ── 基础命令 ──────────────────────────────────────

    def _adb_cmd(self, *args: str) -> list[str]:
        """构建ADB命令"""
        cmd = [self._adb_path]
        if self._serial:
            cmd += ["-s", self._serial]
        cmd.extend(args)
        return cmd

    def _run(self, *args: str, timeout: int = 10) -> tuple[int, str, str]:
        """执行ADB命令，返回 (返回码, stdout, stderr)"""
        cmd = self._adb_cmd(*args)
        logger.debug("ADB 执行: {}", " ".join(cmd))
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                encoding="utf-8",
                errors="replace",
            )
            return proc.returncode, proc.stdout.strip(), proc.stderr.strip()
        except subprocess.TimeoutExpired:
            logger.error("ADB 命令超时: {}", " ".join(cmd))
            return -1, "", "timeout"
        except FileNotFoundError:
            logger.error("ADB 未找到: {}，请检查配置文件中的 adb.path", self._adb_path)
            return -1, "", "adb not found"

    def shell(self, cmd: str, timeout: int = 10) -> tuple[int, str]:
        """执行 adb shell 命令"""
        code, stdout, stderr = self._run("shell", cmd, timeout=timeout)
        return code, stdout or stderr

    # ── 连接管理 ──────────────────────────────────────

    def connect(self, address: str) -> bool:
        """连接到指定设备地址 (如 127.0.0.1:7555)"""
        code, stdout, _ = self._run("connect", address, timeout=5)
        success = code == 0 and ("connected" in stdout.lower() or "already" in stdout.lower())
        if success:
            logger.info("ADB 已连接到 {}", address)
        else:
            logger.warning("ADB 连接 {} 失败: {}", address, stdout)
        return success

    def disconnect(self, address: Optional[str] = None) -> bool:
        """断开连接"""
        args = ["disconnect"]
        if address:
            args.append(address)
        code, stdout, _ = self._run(*args, timeout=5)
        return code == 0

    def is_connected(self) -> bool:
        """检查设备是否连接"""
        code, stdout, _ = self._run("get-state", timeout=5)
        return code == 0 and "device" in stdout

    # ── 设备信息 ──────────────────────────────────────

    def get_screen_size(self) -> tuple[int, int]:
        """获取屏幕分辨率 (宽, 高)"""
        code, output = self.shell("wm size")
        if code == 0:
            match = re.search(r"(\d+)\s*x\s*(\d+)", output)
            if match:
                return int(match.group(1)), int(match.group(2))
        logger.warning("无法获取屏幕尺寸，使用默认 1280x720")
        return 1280, 720

    def get_orientation(self) -> int:
        """获取屏幕方向: 0=竖屏, 1=横屏"""
        code, output = self.shell("dumpsys input | grep SurfaceOrientation")
        if code == 0:
            match = re.search(r"SurfaceOrientation:\s*(\d+)", output)
            if match:
                return int(match.group(1))
        return 0

    def get_package_name(self) -> str:
        """获取当前前台应用的包名"""
        code, output = self.shell("dumpsys activity activities | grep mResumedActivity")
        if code == 0:
            match = re.search(r"u0\s+([\w.]+)/", output)
            if match:
                return match.group(1)
        return ""

    # ── 操作 ──────────────────────────────────────────

    def click(self, x: int, y: int) -> bool:
        """点击屏幕指定坐标"""
        code, _ = self.shell(f"input tap {x} {y}")
        return code == 0

    def swipe(
        self,
        x1: int, y1: int,
        x2: int, y2: int,
        duration: int = 300,
    ) -> bool:
        """滑动屏幕"""
        code, _ = self.shell(f"input swipe {x1} {y1} {x2} {y2} {duration}")
        return code == 0

    def long_press(self, x: int, y: int, duration: int = 1000) -> bool:
        """长按"""
        return self.swipe(x, y, x, y, duration)

    def input_text(self, text: str) -> bool:
        """输入文字（需先聚焦输入框）"""
        # 转义特殊字符
        safe_text = text.replace(" ", "%s").replace("&", "\\&")
        code, _ = self.shell(f"input text '{safe_text}'")
        return code == 0

    def send_keyevent(self, keycode: int) -> bool:
        """发送按键事件 (4=返回, 3=Home, 26=电源)"""
        code, _ = self.shell(f"input keyevent {keycode}")
        return code == 0

    # ── 应用管理 ──────────────────────────────────────

    def start_app(self, package: str, activity: Optional[str] = None) -> bool:
        """启动应用"""
        if activity:
            cmd_str = f"am start -n {package}/{activity}"
        else:
            cmd_str = f"monkey -p {package} -c android.intent.category.LAUNCHER 1"
        code, output = self.shell(cmd_str)
        return code == 0 and "Error" not in output

    def stop_app(self, package: str) -> bool:
        """强制停止应用"""
        code, _ = self.shell(f"am force-stop {package}")
        return code == 0

    # ── 截图 ──────────────────────────────────────────

    def screenshot(self, local_path: str) -> bool:
        """
        截图并保存到本地
        流程: screencap → pull → 删除设备端文件
        """
        remote_path = "/sdcard/wuhua_screen.png"

        # 1. 设备端截图
        code, _ = self.shell(f"screencap -p {remote_path}")
        if code != 0:
            logger.error("截图失败")
            return False

        # 2. 拉取到本地
        code, stdout, stderr = self._run("pull", remote_path, local_path)
        if code != 0:
            logger.error("截图拉取失败: {}", stderr)
            return False

        # 3. 清理设备端文件
        self.shell(f"rm {remote_path}")

        if Path(local_path).exists():
            logger.debug("截图已保存: {}", local_path)
            return True
        return False

    def screenshot_bytes(self) -> Optional[bytes]:
        """
        截图并以 bytes 形式返回（不存盘）
        """
        remote_path = "/sdcard/wuhua_screen.png"
        code, _ = self.shell(f"screencap -p {remote_path}")
        if code != 0:
            return None

        # 使用 subprocess 执行 pull 到 stdout
        cmd = self._adb_cmd("exec-out", "cat", remote_path)
        try:
            proc = subprocess.run(cmd, capture_output=True, timeout=10)
            self.shell(f"rm {remote_path}")
            if proc.returncode == 0:
                return proc.stdout
        except Exception as e:
            logger.error("截图读取失败: {}", e)
        return None


# ── 设备自动检测 ──────────────────────────────────────

KNOWN_EMULATOR_PORTS = {
    "mumu": 16384,
    "ldplayer": 5555,
    "bluestacks": 5555,
}


# ADB 可执行文件搜索路径（按优先级）
_ADB_SEARCH_PATHS = [
    # MuMu 12 (多版本目录结构)
    r"C:\Program Files\Netease\MuMu\nx_device\*\shell\adb.exe",
    r"C:\Program Files\Netease\MuMu Player 12\shell\adb.exe",
    # 雷电
    r"C:\Program Files\ldplayer9\adb.exe",
    # 蓝叠
    r"C:\Program Files\BlueStacks_nxt\HD-Adb.exe",
]


def find_adb() -> str:
    """自动查找 adb.exe，找不到时返回 'adb'（依赖系统PATH）"""
    import glob as _glob

    # 1. 先检查系统 PATH
    import shutil
    path_adb = shutil.which("adb")
    if path_adb:
        logger.info("系统PATH中找到 adb: {}", path_adb)
        return path_adb

    # 2. 搜索已知模拟器目录
    for pattern in _ADB_SEARCH_PATHS:
        matches = _glob.glob(pattern)
        if matches:
            logger.info("自动搜索找到 adb: {}", matches[0])
            return matches[0]

    # 3. 兜底
    logger.warning("未找到 adb，回退到系统PATH")
    return "adb"


def list_devices() -> list[str]:
    """列出所有已连接的设备"""
    adb_path = config.get("adb.path", "adb")
    try:
        proc = subprocess.run(
            [adb_path, "devices"],
            capture_output=True, text=True, timeout=5
        )
        lines = proc.stdout.strip().split("\n")[1:]  # 跳过首行 "List of devices"
        devices = []
        for line in lines:
            if "\tdevice" in line:
                devices.append(line.split("\t")[0])
        return devices
    except Exception:
        return []


def auto_detect_device() -> Optional[str]:
    """自动检测并连接模拟器"""
    devices = list_devices()
    if devices:
        logger.info("检测到已连接设备: {}", devices[0])
        return devices[0]

    # 尝试连接已知模拟器端口
    for emu_type, port in KNOWN_EMULATOR_PORTS.items():
        address = f"127.0.0.1:{port}"
        logger.info("尝试连接 {} ({})", emu_type, address)
        client = ADBClient()
        if client.connect(address):
            return address

    logger.warning("未检测到任何模拟器设备")
    return None
