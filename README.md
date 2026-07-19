# WuHuaGachaAnalysis

《物华弥新》抽卡记录 OCR 识别与统计分析工具。

## 功能

-  **PC端自动化扫描**：通过 ADB 连接模拟器，图像识别自动导航至"召集记录"，逐页截图并 OCR 识别
-  **图像识别导航**：基于模板匹配 + A* BFS 最短路径的智能页面导航
-  **PaddleOCR 识别**：子进程批量处理，按列位置解析角色名/卡池/时间，稀有度从词库直接匹配
-  **数据统计分析**：按卡池时间线展示特出记录、UP/歪统计、垫抽计数
-  **多账户支持**：可创建多个账户分别管理不同账号的抽卡记录
-  **本地 SQLite 存储**：零配置，自动创建，SQLAlchemy ORM，支持 JSON 导入/导出

## 项目结构

```
WuHuaGachaAnalysis/
├── src/
│   ├── main.py                     # 程序入口
│   ├── config.py                   # 配置管理（单例）
│   ├── emulator/                   # 模拟器控制
│   │   ├── adb_client.py           # ADB 连接、截图、点击（含质量验证）
│   │   └── screenshot.py           # 截图模块（PIL + numpy）
│   ├── automation/                 # 自动化引擎
│   │   ├── button.py               # Button 多层级识别（颜色→模板→全图搜索）
│   │   ├── page_graph.py           # 页面图导航系统（A* BFS 最短路径）
│   │   ├── page_detector.py        # 页面识别 + 颜色匹配稀有度
│   │   ├── ui_navigator.py         # 导航器（图像识别优先 + 坐标回退）
│   │   ├── gacha_scanner.py        # 召集记录扫描主逻辑 + 页指纹去重
│   │   ├── errors.py               # 自动化异常类
│   │   └── pages/                  # 各页面按钮定义
│   ├── ocr/                        # OCR 识别
│   │   ├── engine.py               # PaddleOCR 子进程封装
│   │   ├── worker.py               # OCR 子进程脚本
│   │   └── parser.py               # 结果解析（按列位置 + 模糊匹配纠错）
│   ├── models/                     # 数据模型
│   │   └── gacha_record.py         # 抽卡记录（5★特出/4★优异/3★新生）
│   ├── storage/                    # 数据存储
│   │   ├── database.py             # SQLite (SQLAlchemy ORM，自动创建)
│   │   └── exporter.py             # JSON 导出/导入
│   └── gui/                        # 桌面 GUI (PyQt6)
│       ├── main_window.py          # 主窗口（暗色主题 + 账户管理）
│       └── pages/
│           ├── home_page.py        # 首页概览（卡池时间线 + 垫抽）
│           └── settings_page.py    # 设置页（ADB 连接/扫描）
├── assets/
│   └── templates/                  # UI 模板图片（页面识别用）
├── config/
│   ├── default_config.yaml         # 默认配置（ADB/扫描参数）
│   └── names.yaml                  # 器者名称词库 + 卡池 UP 映射
├── requirements.txt
├── LICENSE
└── README.md
```

## 有编程基础安装

```bash
# 克隆仓库
git clone https://github.com/QingLinAuraro/WuHuaGachaAnalysis.git
cd WuHuaGachaAnalysis

# 创建虚拟环境（推荐）
python -m venv .venv
source .venv/bin/activate  # Linux/macOS
# .venv\Scripts\activate   # Windows

# 安装依赖
pip install -r requirements.txt

# 启动应用（数据库自动创建，无需配置）
python -m src.main
```
## 无编程基础安装

1. 在当前界面右侧找到Release中的最新版本，点击进入
2. 进入后在Assets中找到对应的.zip文件下载，下载后解压
3. 进入解压后的文件夹，点击.exe文件运行，会自动下载需求文件等，请耐心等待

### 使用说明

1. 模拟器打开《物华弥新》，进入主界面
2. 启动程序，在"设置"页面连接模拟器
3. 点击"开始扫描"，程序自动导航并识别全部召集记录
4. 在"首页概览"查看按卡池分组的时间线和统计

## 鸣谢

- [AzurLaneAutoScript (ALAS)](https://github.com/LmeSzinc/AzurLaneAutoScript) — 本项目的页面图导航（A* BFS）和 Button 多层级识别设计参照了 ALAS 的架构
