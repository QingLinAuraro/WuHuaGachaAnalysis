"""
物华弥新抽卡分析器 启动器

编译为 .exe:
    pyinstaller --onefile --windowed --name="物华弥新抽卡分析器" launcher.py
"""
import os
import subprocess
import sys
from pathlib import Path

# PyInstaller --onefile 打包后 __file__ 指向临时目录，
# 必须用 sys.executable 获取 .exe 所在的实际目录
if getattr(sys, "frozen", False):
    ROOT = Path(sys.executable).resolve().parent
else:
    ROOT = Path(__file__).resolve().parent


def _show_error(title: str, message: str) -> None:
    """显示错误（兼容 --windowed 无控制台模式）"""
    if sys.stdin is not None:
        # 有控制台，直接打印
        print(f"\n{title}")
        print(message)
        try:
            input("\n按回车键退出...")
        except (EOFError, RuntimeError):
            pass
    else:
        # 无控制台（--windowed），弹出消息框
        try:
            import subprocess
            subprocess.run(
                [
                    "msg",
                    "*",
                    "/TIME:0",
                    f"{title}\n\n{message}",
                ],
                capture_output=True,
                timeout=5,
            )
        except Exception:
            pass
        # 回退：写入错误日志
        try:
            log = ROOT / "logs" / "launcher_error.log"
            log.parent.mkdir(parents=True, exist_ok=True)
            with open(log, "a", encoding="utf-8") as f:
                f.write(f"{title}\n{message}\n")
        except Exception:
            pass


def setup_environment() -> None:
    """设置 PATH 指向 toolkit 中的 Python / Git / ADB"""
    if os.name != "nt":
        return

    paths = [
        str(ROOT / "toolkit"),
        str(ROOT / "toolkit" / "Scripts"),
        str(ROOT / "toolkit" / "Git" / "mingw64" / "bin"),
        str(ROOT / "toolkit" / "adb"),
    ]
    sep = ";"
    current = os.environ.get("PATH", "")
    os.environ["PATH"] = sep.join(paths) + sep + current


def main() -> None:
    os.chdir(str(ROOT))
    setup_environment()

    python_exe = str(ROOT / "toolkit" / "python.exe")

    if not os.path.exists(python_exe):
        _show_error(
            "错误：未找到 Python 运行时",
            f"路径: {python_exe}\n\n请确保 toolkit/ 目录完整，不要移动或删除 .exe 文件。",
        )
        sys.exit(1)

    # 1. 运行更新器
    print("正在检查更新...")
    result = subprocess.run(
        [python_exe, "-m", "deploy.installer"],
        cwd=str(ROOT),
    )
    if result.returncode != 0:
        _show_error(
            "更新失败",
            "请检查网络连接后重试。\n\n如持续失败，请删除 config/deploy.yaml 后重新运行。",
        )
        sys.exit(1)

    # 2. 启动主程序
    print("正在启动...")
    creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    subprocess.Popen(
        [python_exe, "-m", "src.main"],
        cwd=str(ROOT),
        creationflags=creationflags,
    )
    sys.exit(0)


if __name__ == "__main__":
    main()
