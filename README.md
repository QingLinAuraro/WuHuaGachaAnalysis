# WuHuaGachaAnalysis

《物华弥新》抽卡记录 OCR 识别与统计分析工具。

## 功能

-  **PC端自动化扫描**：通过 ADB 连接模拟器，图像识别自动导航至"召集记录"，逐页截图并 OCR 识别
-  **图像识别导航**：基于模板匹配 + A\* BFS 最短路径的智能页面导航
-  **PaddleOCR 识别**：子进程批量处理，按列位置解析角色名/卡池/时间，稀有度从词库直接匹配
-  **数据统计分析**：按卡池时间线展示特出记录、UP/歪统计、垫抽计数
-  **多账户支持**：可创建多个账户分别管理不同账号的抽卡记录
-  **本地 SQLite 存储**：零配置，自动创建，SQLAlchemy ORM，支持 JSON 导入/导出

---

## 🚀 快速开始（无需编程基础）

> 适用人群：不会 Python、不想装环境、只想双击运行的用户。

1. 前往 [Releases](https://github.com/QingLinAuraro/WuHuaGachaAnalysis/releases) 页面
2. 下载最新的 `WuHuaGachaAnalysis-便携版-*.zip`
3. 解压到任意目录（**请勿放在中文路径过深的位置**）
4. 双击 `物华弥新抽卡分析器.exe`
5. 程序自动检查更新 → 安装依赖 → 启动 GUI
6. 之后每次打开都会自动拉取最新版本

> 💡 首次启动可能需要 10-30 秒初始化，请耐心等待。

### 使用说明

1. 模拟器打开《物华弥新》，进入主界面
2. 启动程序，在"设置"页面连接模拟器
3. 点击"开始扫描"，程序自动导航并识别全部召集记录
4. 在"首页概览"查看按卡池分组的时间线和统计

---

## 🛠 开发者安装（有编程基础）

```bash
# 克隆仓库
git clone https://github.com/QingLinAuraro/WuHuaGachaAnalysis.git
cd WuHuaGachaAnalysis

# 创建虚拟环境（推荐）
python -m venv .venv
# Windows: .venv\Scripts\activate
source .venv/bin/activate  # Linux/macOS

# 安装依赖
pip install -r requirements.txt

# 启动应用
python -m src.main
```

---

## 📦 构建便携版（开发者）

将项目打包为自包含的 `.exe` + `.zip`，供无基础用户使用。

### 前置要求

- Python 3.11+（系统安装）
- PyInstaller（`pip install pyinstaller`）
- 网络连接（首次构建需下载约 150MB）

### 一键构建

```bash
# 仅本地构建（产出 build/ 目录 + .zip）
python build_portable.py

# 构建 + 自动推送到 GitHub release 分支
python build_portable.py --push
```

### 构建流程

| 步骤 | 说明 |
|------|------|
| 下载嵌入式 Python 3.11 | 自包含运行时，无需用户安装 Python |
| pip install 依赖 | PyQt6 + PaddleOCR + OpenCV 等全部打包 |
| 下载 MinGit | 内嵌 Git，用于自更新 |
| 下载 ADB | 模拟器通信工具 |
| 复制源码 | src/ config/ assets/ deploy/ |
| 编译 .exe | PyInstaller 将 launcher.py 打包 |
| 打包 .zip | ~400MB 分发包 |
| Git 推送 | 推送到 `release` 分支 |

### 命令行参数

```
python build_portable.py [选项]

选项:
  --push              构建后自动推送到 Git 远程仓库
  --remote URL        Git 远程仓库地址（默认: 本仓库）
  --branch BRANCH     推送目标分支（默认: release）
  --skip-download     跳过运行时下载（toolkit/ 已就绪时使用）
```

### 产物

```
build/
├── 物华弥新抽卡分析器.exe           # 启动器 (~9MB)
├── WuHuaGachaAnalysis-便携版-*.zip  # 分发包 (~400MB)
├── toolkit/                         # Python + Git + ADB + 所有依赖
├── src/ config/ assets/ deploy/     # 源码
└── .git/                            # 追踪源码，推送至 release 分支
```

---

## 🔄 自更新机制

便携版 `.exe` 内置自动更新：

```
用户双击 .exe
  → deploy/installer.py
    → git fetch origin release    # 拉取最新源码
    → pip install -r requirements # 增量安装依赖
  → 启动 src.main (GUI)
```

- 有网络时自动更新到最新版本
- **离线/首次运行时自动跳过更新**，不影响正常使用
- 更新配置位于 `config/deploy.yaml`（首次运行时从 `deploy/template` 自动生成）

---

## 📁 项目结构

```
WuHuaGachaAnalysis/
├── src/                           # 源码
│   ├── main.py                    # 程序入口
│   ├── config.py                  # 配置管理（单例）
│   ├── emulator/                  # 模拟器控制
│   │   ├── adb_client.py          # ADB 连接、截图、点击
│   │   └── screenshot.py          # 截图模块（PIL + numpy）
│   ├── automation/                # 自动化引擎
│   │   ├── button.py              # 多层级按钮识别
│   │   ├── page_graph.py          # A* BFS 页面图导航
│   │   ├── page_detector.py       # 页面识别 + 颜色匹配
│   │   ├── ui_navigator.py        # 导航器
│   │   ├── gacha_scanner.py       # 扫描主逻辑 + 页指纹去重
│   │   ├── errors.py              # 自动化异常类
│   │   └── pages/                 # 各页面按钮定义
│   ├── ocr/                       # OCR 识别
│   │   ├── engine.py              # PaddleOCR 子进程封装
│   │   ├── worker.py              # OCR 子进程脚本
│   │   └── parser.py              # 结果解析 + 模糊匹配纠错
│   ├── models/                    # 数据模型
│   │   └── gacha_record.py        # 抽卡记录
│   ├── storage/                   # 数据存储
│   │   ├── database.py            # SQLite (SQLAlchemy ORM)
│   │   └── exporter.py            # JSON 导出/导入
│   └── gui/                       # 桌面 GUI (PyQt6)
│       ├── main_window.py         # 主窗口（暗色主题 + 账户管理）
│       └── pages/
│           ├── home_page.py       # 首页概览
│           └── settings_page.py   # 设置页
├── deploy/                        # 自更新模块
│   ├── installer.py               # 更新器入口
│   ├── git.py                     # Git 拉取逻辑
│   ├── pip.py                     # 依赖管理
│   ├── config.py                  # 部署配置
│   ├── utils.py                   # 工具函数
│   └── template                   # 配置模板
├── config/
│   ├── default_config.yaml        # 默认配置
│   └── names.yaml                 # 器者名称词库 + 卡池映射
├── assets/templates/              # UI 模板图片
├── launcher.py                    # 启动器（编译为 .exe）
├── build_portable.py              # 一键构建脚本
├── requirements.txt
├── LICENSE
└── README.md
```

## 仓库分支说明

| 分支 | 用途 |
|------|------|
| `master` | 完整源码（开发者使用） |
| `release` | 发布版文件（供便携版 .exe 自动更新拉取） |

## 鸣谢

- [AzurLaneAutoScript (ALAS)](https://github.com/LmeSzinc/AzurLaneAutoScript) — 页面图导航（A\* BFS）和 Button 多层级识别设计参照
- [PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR) — OCR 识别引擎
