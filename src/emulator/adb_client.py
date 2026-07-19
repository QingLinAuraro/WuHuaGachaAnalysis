"""
ADB 客户端（增强版）
封装 ADB 命令，提供连接、截图、点击、滑动等操作

新增 ALAS 风格增强：
  - click_button()      : 在 Button 区域内随机取点点击
  - screenshot_validate(): 截图 + 质量验证（非黑屏、分辨率正确）
  - 点击历史追踪          : 防重复点击 + 卡住检测
"""

import subprocess
import re
import time
from pathlib import Path
from typing import Optional, TYPE_CHECKING

import numpy as np
import cv2
from loguru import logger

from src.config import config

if TYPE_CHECKING:
    from src.automation.button import Button


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
        self._record_click(x, y)
        return code == 0

    def click_button(self, button: "Button") -> bool:
        """在 Button 区域内随机取点点击（模拟人类，防止反外挂检测）

        优先使用模板匹配的精确位置，否则在 button 区域内按正态分布取点。

        Args:
            button: Button 对象

        Returns:
            bool
        """
        # 如果有模板匹配结果，直接使用
        if button._match_point is not None:
            x, y = button._match_point
        else:
            # 在 button 区域内随机取点（偏向中心的正态分布）
            x1, y1, x2, y2 = button.button
            cx = (x1 + x2) // 2
            cy = (y1 + y2) // 2
            sigma_x = max(1, (x2 - x1) // 6)
            sigma_y = max(1, (y2 - y1) // 6)
            x = int(np.random.normal(cx, sigma_x))
            y = int(np.random.normal(cy, sigma_y))
            x = max(x1, min(x2 - 1, x))
            y = max(y1, min(y2 - 1, y))

        logger.debug("点击按钮 '{}' @ ({}, {})", button.name, x, y)
        return self.click(x, y)

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

    def click_random(
        self,
        x1: int, y1: int, x2: int, y2: int,
    ) -> bool:
        """在矩形区域内随机取点点击

        Args:
            x1, y1: 左上角坐标
            x2, y2: 右下角坐标
        """
        x = int(np.random.uniform(x1, x2))
        y = int(np.random.uniform(y1, y2))
        return self.click(x, y)

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

    def screenshot_validate(self) -> Optional[np.ndarray]:
        """截图 + 质量验证

        验证内容：
          1. 非空（连接正常）
          2. 非全黑（游戏画面正常渲染）
          3. 分辨率在合理范围（非小窗/缩略图）

        Returns:
            BGR 格式的 numpy 数组，验证失败返回 None
        """
        img_bytes = self.screenshot_bytes()
        if img_bytes is None:
            logger.error("截图验证失败: 无法获取截图")
            return None

        img_array = np.frombuffer(img_bytes, dtype=np.uint8)
        img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
        if img is None:
            logger.error("截图验证失败: 无法解码图像")
            return None

        h, w = img.shape[:2]

        # 验证分辨率
        min_w = config.get("automation.image_recognition.min_width", 640)
        min_h = config.get("automation.image_recognition.min_height", 360)
        if w < min_w or h < min_h:
            logger.error("截图验证失败: 分辨率过小 ({}x{})", w, h)
            return None

        # 验证非全黑
        mean_val = cv2.mean(img)
        # mean_val 是 (B, G, R, A) 的均值
        avg_brightness = (mean_val[0] + mean_val[1] + mean_val[2]) / 3
        if avg_brightness < 1.0:
            logger.error("截图验证失败: 全黑画面 (亮度={:.1f})", avg_brightness)
            return None

        logger.debug("截图验证通过: {}x{}, 平均亮度={:.1f}", w, h, avg_brightness)
        return img

    # ── 点击历史 & 卡住检测 ────────────────────────────

    def _init_click_history(self) -> None:
        """初始化点击历史（首次调用 click 时自动初始化）"""
        if not hasattr(self, "_click_history"):
            self._click_history: list[tuple[int, int, float]] = []

    def _record_click(self, x: int, y: int) -> None:
        """记录每次点击"""
        self._init_click_history()
        self._click_history.append((x, y, time.time()))
        if len(self._click_history) > 100:
            self._click_history = self._click_history[-100:]

    def reset_click_history(self) -> None:
        """重置点击历史"""
        self._click_history = []


# ── 设备自动检测 ──────────────────────────────────────

KNOWN_EMULATOR_PORTS = {
    "mumu": 16384,
    "ldplayer": 5555,
    "bluestacks": 5555,
}


def find_adb() -> str:
    """自动查找 adb.exe，找不到时返回 'adb'（依赖系统PATH）"""
    import glob as _glob
    import shutil

    # 1. 先检查系统 PATH
    path_adb = shutil.which("adb")
    if path_adb:
        logger.info("系统PATH中找到 adb: {}", path_adb)
        return path_adb

    # 2. 搜索已知模拟器目录（从配置读取，展开环境变量）
    search_paths = config.get("adb.search_paths", [])
    for pattern in search_paths:
        expanded = os.path.expandvars(pattern)
        matches = _glob.glob(expanded)
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
