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

## 快速开始（无需编程基础）

1. 前往 [Releases](https://github.com/QingLinAuraro/WuHuaGachaAnalysis/releases) 页面
2. 下载最新的 `WuHuaGachaAnalysis-便携版-*.zip`
3. 解压到任意目录
4. 双击 `物华弥新抽卡分析器.exe`
5. 程序自动检查更新 → 安装依赖 → 启动 GUI
6. 之后每次打开都会自动拉取最新版本

> 首次启动可能需要 10-30 秒初始化，请耐心等待。离线也能正常使用。

### 使用说明

1. 模拟器打开《物华弥新》，进入主界面
2. 启动程序，在"设置"页面连接模拟器
3. 点击"开始扫描"，程序自动导航并识别全部召集记录
4. 在"首页概览"查看按卡池分组的时间线和统计

---

## 开发者安装

```bash
git clone https://github.com/QingLinAuraro/WuHuaGachaAnalysis.git
cd WuHuaGachaAnalysis

python -m venv .venv
source .venv/bin/activate      # Linux/macOS
# .venv\Scripts\activate       # Windows

pip install -r requirements.txt
python -m src.main
```

---

## 自更新机制

便携版 `.exe` 启动流程：

```
用户双击 .exe
  → deploy/installer.py
    → git init（首次）→ git fetch origin master
    → git reset --hard origin/master    # 拉取最新源码
    → pip install -r requirements.txt   # 增量安装依赖
  → 启动 src.main (GUI)
```

- 有网络时自动更新到最新版本
- **离线/首次运行自动跳过更新**，不影响使用
- 更新配置：`config/deploy.yaml`（首次运行时从 `deploy/template` 自动生成）

---

## 项目结构

```
WuHuaGachaAnalysis/
├── src/                           # 源码
│   ├── main.py                    # 程序入口
│   ├── config.py                  # 配置管理
│   ├── emulator/                  # 模拟器控制 (ADB)
│   ├── automation/                # 自动化引擎 (页面导航/扫描)
│   ├── ocr/                       # OCR 识别 (PaddleOCR)
│   ├── models/                    # 数据模型
│   ├── storage/                   # SQLite 存储 + JSON 导出
│   └── gui/                       # 桌面 GUI (PyQt6)
├── deploy/                        # 自更新模块
│   ├── installer.py               # 更新器入口
│   ├── git.py                     # Git 拉取
│   ├── pip.py                     # 依赖管理
│   └── template                   # 配置模板
├── config/                        # 应用配置
│   ├── default_config.yaml
│   └── names.yaml                 # 器者名称词库
├── assets/templates/              # UI 模板图片
├── launcher.py                    # 启动器（编译为 .exe）
├── requirements.txt
├── .gitignore
├── README.md
└── LICENSE
```


---

## 鸣谢

- [AzurLaneAutoScript (ALAS)](https://github.com/LmeSzinc/AzurLaneAutoScript) — 页面图导航（A\* BFS）和 Button 多层级识别设计参照
- [PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR) — OCR 识别引擎
