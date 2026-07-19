"""
一键构建便携发行版

流程：
0. 清理上次构建残留
1. 下载 Python 3.11 embedded → build/toolkit/
2. 配置嵌入式 Python（pip + site-packages）
3. pip install -r requirements.txt
4. 下载 MinGit → build/toolkit/Git/
5. 下载 ADB → build/toolkit/adb/
6. 复制源码
7. 编译启动器 .exe
8. 清理构建产物
9. 写入发布版 .gitignore
10. git init + commit
11. 打包 .zip
12. Git 推送（可选）

用法:
    python build_portable.py                     # 仅本地构建
    python build_portable.py --push              # 构建 + 推送到默认仓库
    python build_portable.py --remote <url>      # 指定 Git 远程仓库
    python build_portable.py --branch release    # 指定推送分支（默认 master）
"""
import argparse
import datetime
import os
import shutil
import stat
import subprocess
import sys
import time
import urllib.request
import zipfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.resolve()
BUILD_DIR = PROJECT_ROOT / "build"
TOOLKIT_DIR = BUILD_DIR / "toolkit"

# === 配置 ===
VERSION = "1.0.0"
PYTHON_VERSION = "3.11.9"
PYTHON_EMBED_URL = (
    f"https://www.python.org/ftp/python/{PYTHON_VERSION}/"
    f"python-{PYTHON_VERSION}-embed-amd64.zip"
)
GET_PIP_URL = "https://bootstrap.pypa.io/get-pip.py"

# MinGit: 官方最小 Git for Windows 发行版
MINGIT_URL = (
    "https://github.com/git-for-windows/git/releases/download/"
    "v2.47.1.windows.1/MinGit-2.47.1-64-bit.zip"
)

# Google Platform Tools (ADB)
PLATFORM_TOOLS_URL = (
    "https://dl.google.com/android/repository/"
    "platform-tools-latest-windows.zip"
)

# 默认 Git 远程
DEFAULT_REMOTE = "https://github.com/QingLinAuraro/WuHuaGachaAnalysis.git"
DEFAULT_BRANCH = "master"

# 构建专用 .gitignore 内容
BUILD_GITIGNORE = """\
# ============================================
# WuHuaGachaAnalysis 便携版 - Git 忽略规则
# ============================================

# --- 构建产物 ---
_pyinstaller_build/
*.zip
get-pip.py
*.spec
*.manifest
.DS_Store
Thumbs.db

# --- 自包含运行时（太大不进 git）---
/toolkit/

# --- 编译产物 ---
__pycache__/
*.py[codz]
*.pyc
*.pyd
*.so
*.dll

# --- 用户运行时数据 ---
*.db
*.sqlite3
/user_config.yaml
/config/deploy.yaml
gacha_export*.json

# --- 日志 ---
logs/*.log
!logs/.gitkeep

# --- 截图（保留 .gitkeep）---
screenshots/*.png
!screenshots/.gitkeep
!screenshots/_*.png

# --- IDE / 编辑器 ---
.idea/
.vscode/
*.swp
*.swo

# --- Python 相关 ---
.venv/
venv/
env/
.eggs/
*.egg-info/

# --- 测试 & 工具（便携版不需要）---
tools/
tests/
"""


def robust_rmtree(path: Path, retries: int = 3) -> None:
    """健壮的目录删除（处理 Windows 文件锁定）"""
    if not path.exists():
        return

    def _onerror(func, p, excinfo):
        """权限错误时尝试修改权限后重试"""
        try:
            os.chmod(p, stat.S_IWRITE)
            func(p)
        except Exception:
            pass

    for attempt in range(retries):
        try:
            shutil.rmtree(str(path), onerror=_onerror)
            return
        except PermissionError:
            if attempt < retries - 1:
                time.sleep(1)
            else:
                # 最后尝试用 shell 删除
                subprocess.run(
                    ["cmd", "/c", "rmdir", "/s", "/q", str(path)],
                    capture_output=True,
                )
                if path.exists():
                    raise


def download(url: str, dest: Path) -> None:
    """下载文件"""
    print(f"  下载: {url}")
    dest.parent.mkdir(parents=True, exist_ok=True)

    def _report(count, block_size, total_size):
        pct = int(count * block_size * 100 / total_size) if total_size > 0 else 0
        if pct % 20 == 0:
            print(f"    {pct}%")

    urllib.request.urlretrieve(url, str(dest), _report)
    print(f"  完成: {dest}")


def extract_zip(zip_path: Path, dest: Path) -> None:
    """解压 zip"""
    print(f"  解压: {zip_path} → {dest}")
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(dest)


def step_cleanup_previous() -> None:
    """步骤 0: 清理上次构建残留（保留 toolkit 避免重复下载）"""
    print("\n" + "=" * 50)
    print("  [0/10] 清理上次构建残留")
    print("=" * 50)

    # 清理打包产物
    for name in [
        "_pyinstaller_build",
        "_adb_tmp",
        "python-embed.zip",
        "mingit.zip",
        "platform-tools.zip",
        "get-pip.py",
        "物华弥新抽卡分析器.spec",
    ]:
        p = BUILD_DIR / name
        if p.is_dir():
            robust_rmtree(p)
            print(f"  已删除: {name}/")
        elif p.exists():
            p.unlink()
            print(f"  已删除: {name}")

    # 删除旧的 .git（重新初始化）
    git_dir = BUILD_DIR / ".git"
    if git_dir.exists():
        robust_rmtree(git_dir)
        print("  已删除: .git/")

    # 清理旧 zip
    for f in BUILD_DIR.glob("WuHuaGachaAnalysis*.zip"):
        f.unlink()
        print(f"  已删除: {f.name}")


def step_python() -> None:
    """步骤 1-3: 嵌入式 Python + pip + 依赖"""
    print("\n" + "=" * 50)
    print("  [1/10] 设置嵌入式 Python")
    print("=" * 50)

    python_zip = BUILD_DIR / "python-embed.zip"
    pip_py = BUILD_DIR / "get-pip.py"

    if not (TOOLKIT_DIR / "python.exe").exists():
        # 下载
        if not python_zip.exists():
            download(PYTHON_EMBED_URL, python_zip)
        extract_zip(python_zip, TOOLKIT_DIR)

        # 启用 site-packages（取消 #import site 注释）
        pth_file = TOOLKIT_DIR / "python311._pth"
        if pth_file.exists():
            content = pth_file.read_text()
            content = content.replace("#import site", "import site")
            # 添加项目根目录（.. = build/），使 deploy/src 等模块可导入
            content += "\n..\n"
            content += "Lib/site-packages\n"
            pth_file.write_text(content)

        # 安装 pip
        if not pip_py.exists():
            download(GET_PIP_URL, pip_py)
        subprocess.run(
            [str(TOOLKIT_DIR / "python.exe"), str(pip_py)],
            cwd=str(TOOLKIT_DIR),
            check=True,
        )

    # pip install 依赖
    print("\n  安装依赖...")
    subprocess.run(
        [
            str(TOOLKIT_DIR / "python.exe"),
            "-m",
            "pip",
            "install",
            "-r",
            str(PROJECT_ROOT / "requirements.txt"),
            "--disable-pip-version-check",
        ],
        cwd=str(BUILD_DIR),
        check=True,
    )


def step_git() -> None:
    """步骤 4: MinGit"""
    print("\n" + "=" * 50)
    print("  [2/10] 下载 MinGit")
    print("=" * 50)

    git_dir = TOOLKIT_DIR / "Git"
    if git_dir.exists():
        print("  MinGit 已存在，跳过")
        return

    git_zip = BUILD_DIR / "mingit.zip"
    if not git_zip.exists():
        download(MINGIT_URL, git_zip)
    extract_zip(git_zip, git_dir)


def step_adb() -> None:
    """步骤 5: ADB"""
    print("\n" + "=" * 50)
    print("  [3/10] 下载 ADB")
    print("=" * 50)

    adb_dir = TOOLKIT_DIR / "adb"
    if adb_dir.exists():
        print("  ADB 已存在，跳过")
        return

    pt_zip = BUILD_DIR / "platform-tools.zip"
    if not pt_zip.exists():
        download(PLATFORM_TOOLS_URL, pt_zip)

    tmp = BUILD_DIR / "_adb_tmp"
    extract_zip(pt_zip, tmp)
    shutil.move(str(tmp / "platform-tools"), str(adb_dir))
    robust_rmtree(tmp)


def step_copy_source() -> None:
    """步骤 6: 复制源码（不含根目录 .gitignore，稍后写入专用版）"""
    print("\n" + "=" * 50)
    print("  [4/10] 复制源码")
    print("=" * 50)

    for item in ["src", "assets", "config", "deploy", "requirements.txt"]:
        src = PROJECT_ROOT / item
        dst = BUILD_DIR / item
        if dst.exists():
            if dst.is_dir():
                shutil.rmtree(str(dst))
            else:
                dst.unlink()
        if src.is_dir():
            shutil.copytree(str(src), str(dst))
        else:
            shutil.copy2(str(src), str(dst))
        print(f"  复制: {item}")

    # 复制启动辅助文件（不复制根 .gitignore）
    for item in ["控制台.bat"]:
        src = PROJECT_ROOT / item
        dst = BUILD_DIR / item
        if src.exists():
            shutil.copy2(str(src), str(dst))
            print(f"  复制: {item}")

    # 创建空数据目录
    for d in ["data", "logs", "screenshots"]:
        (BUILD_DIR / d).mkdir(parents=True, exist_ok=True)
    print("  创建: data/ logs/ screenshots/")


def step_compile_launcher() -> None:
    """步骤 7: 编译启动器 .exe"""
    print("\n" + "=" * 50)
    print("  [5/10] 编译启动器 .exe")
    print("=" * 50)

    launcher_py = PROJECT_ROOT / "launcher.py"
    if not launcher_py.exists():
        print("  跳过：launcher.py 不存在")
        return

    subprocess.run(
        [
            sys.executable,
            "-m",
            "PyInstaller",
            "--onefile",
            "--windowed",
            "--name=物华弥新抽卡分析器",
            "--distpath",
            str(BUILD_DIR),
            "--workpath",
            str(BUILD_DIR / "_pyinstaller_build"),
            "--specpath",
            str(BUILD_DIR),
            str(launcher_py),
        ],
        check=True,
    )
    print("  编译完成 → build/物华弥新抽卡分析器.exe")


def step_cleanup_build() -> None:
    """步骤 8: 清理构建产物（删除下载残留和 PyInstaller 临时文件）"""
    print("\n" + "=" * 50)
    print("  [6/10] 清理构建产物")
    print("=" * 50)

    for name in [
        "_pyinstaller_build",
        "_adb_tmp",
        "python-embed.zip",
        "mingit.zip",
        "platform-tools.zip",
        "get-pip.py",
        "物华弥新抽卡分析器.spec",
    ]:
        p = BUILD_DIR / name
        if p.is_dir():
            robust_rmtree(p)
            print(f"  已删除: {name}/")
        elif p.exists():
            p.unlink()
            print(f"  已删除: {name}")


def step_write_gitignore() -> None:
    """步骤 9: 写入发布版 .gitignore"""
    print("\n" + "=" * 50)
    print("  [7/10] 写入发布版 .gitignore")
    print("=" * 50)

    gi = BUILD_DIR / ".gitignore"
    gi.write_text(BUILD_GITIGNORE, encoding="utf-8")
    print("  已写入: .gitignore")


def step_git_init() -> None:
    """步骤 10: Git 初始化 + 提交"""
    print("\n" + "=" * 50)
    print("  [8/10] Git 初始化")
    print("=" * 50)

    # 删除旧 .git（如果有）
    git_dir = BUILD_DIR / ".git"
    if git_dir.exists():
        robust_rmtree(git_dir)
        print("  已删除旧 .git/")

    # 确保空目录有 .gitkeep
    for d in ["data", "logs", "screenshots"]:
        gk = BUILD_DIR / d / ".gitkeep"
        gk.parent.mkdir(parents=True, exist_ok=True)
        if not gk.exists():
            gk.touch()
            print(f"  创建: {d}/.gitkeep")

    os.chdir(str(BUILD_DIR))
    subprocess.run(["git", "init"], check=True)
    subprocess.run(["git", "add", "-A"], check=True)
    subprocess.run(
        ["git", "commit", "-m", f"WuHuaGachaAnalysis 便携版 v{VERSION}"],
        check=True,
    )
    os.chdir(str(PROJECT_ROOT))
    print("  Git 仓库初始化完成")


def step_package_zip() -> Path:
    """步骤 11: 打包 .zip"""
    print("\n" + "=" * 50)
    print("  [9/10] 打包 .zip")
    print("=" * 50)

    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    zip_name = f"WuHuaGachaAnalysis-便携版-v{VERSION}-{stamp}.zip"
    zip_path = BUILD_DIR / zip_name

    print(f"  创建: {zip_name}")
    print(f"  （这可能需要几分钟，文件约 1.4GB）...")

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(str(BUILD_DIR)):
            # 排除不需要打包的内容
            dirs[:] = [
                d
                for d in dirs
                if d not in (".git", "_pyinstaller_build", "_adb_tmp", "__pycache__")
            ]
            for f in files:
                if f.endswith(".zip") or f == "get-pip.py" or f.endswith(".spec"):
                    continue
                abs_path = os.path.join(root, f)
                arcname = os.path.relpath(abs_path, str(BUILD_DIR))
                zf.write(abs_path, arcname)

    size_mb = zip_path.stat().st_size / (1024 * 1024)
    print(f"  打包完成: {zip_name} ({size_mb:.1f} MB)")

    return zip_path


def step_git_push(remote: str, branch: str) -> None:
    """步骤 12: 推送到远程 Git 仓库"""
    print("\n" + "=" * 50)
    print("  [10/10] Git 推送")
    print("=" * 50)

    print(f"  远程仓库: {remote}")
    print(f"  目标分支: {branch}")

    os.chdir(str(BUILD_DIR))

    # 设置 remote
    subprocess.run(
        ["git", "remote", "remove", "origin"],
        cwd=str(BUILD_DIR),
        capture_output=True,
    )
    subprocess.run(
        ["git", "remote", "add", "origin", remote],
        cwd=str(BUILD_DIR),
        check=True,
    )

    # 强制推送到目标分支
    print(f"  推送中...")
    result = subprocess.run(
        ["git", "push", "-f", "origin", f"master:{branch}"],
        cwd=str(BUILD_DIR),
        capture_output=True,
        text=True,
    )

    os.chdir(str(PROJECT_ROOT))

    if result.returncode == 0:
        print("  Git 推送成功！")
    else:
        print(f"  Git 推送失败:")
        print(f"  {result.stderr.strip()}")
        print(f"\n  提示：请确保已配置 Git 凭据，或使用 SSH remote。")
        print(f"  您可以稍后手动推送：")
        print(f"    cd build")
        print(f'    git remote add origin {remote}')
        print(f"    git push -f origin master:{branch}")


def main() -> None:
    """主流程"""
    parser = argparse.ArgumentParser(
        description="WuHuaGachaAnalysis 便携版一键构建",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
示例:
  python build_portable.py                     仅本地构建
  python build_portable.py --push              构建并推送到默认仓库
  python build_portable.py --push --branch release  推送到 release 分支
  python build_portable.py --remote git@github.com:user/repo.git  指定 SSH 远程
""",
    )
    parser.add_argument(
        "--push",
        action="store_true",
        help="构建完成后自动推送到 Git 远程仓库",
    )
    parser.add_argument(
        "--remote",
        default=DEFAULT_REMOTE,
        help=f"Git 远程仓库 URL（默认: {DEFAULT_REMOTE}）",
    )
    parser.add_argument(
        "--branch",
        default=DEFAULT_BRANCH,
        help=f"推送目标分支（默认: {DEFAULT_BRANCH}）",
    )
    parser.add_argument(
        "--skip-download",
        action="store_true",
        help="跳过运行时下载（假定 toolkit/ 已就绪）",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("  WuHuaGachaAnalysis 便携版构建脚本")
    print(f"  版本: v{VERSION}")
    print("=" * 60)

    BUILD_DIR.mkdir(parents=True, exist_ok=True)

    try:
        step_cleanup_previous()

        if not args.skip_download:
            step_python()
            step_git()
            step_adb()
        else:
            print("\n  （跳过下载步骤，使用现有 toolkit/）")

        step_copy_source()
        step_compile_launcher()
        step_cleanup_build()
        step_write_gitignore()
        step_git_init()

        zip_path = step_package_zip()

        if args.push:
            step_git_push(args.remote, args.branch)
        else:
            print("\n  （跳过 Git 推送，使用 --push 参数启用）")

    except Exception as e:
        print(f"\n构建失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    print("\n" + "=" * 60)
    print("  构建完成!")
    print(f"  输出目录: {BUILD_DIR}")
    if "zip_path" in locals():
        print(f"  分发包:   {zip_path}")
    print("=" * 60)
    print()
    print("  非技术用户使用方式：")
    print(f"  1. 解压 WuHuaGachaAnalysis-便携版-*.zip")
    print("  2. 双击 物华弥新抽卡分析器.exe")
    print("  3. 程序自动检查更新并启动")
    print()


if __name__ == "__main__":
    main()
