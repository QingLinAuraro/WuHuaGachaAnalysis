# 🎴 WuHuaGachaAnalysis

《物华弥新》抽卡记录 OCR 识别与统计分析工具。

## 功能

- 🖥️ **PC端自动化扫描**：通过 ADB 连接模拟器，图像识别自动导航至"召集记录"，逐页截图并 OCR 识别
- 🧭 **图像识别导航**：基于模板匹配 + 颜色检测 + A* BFS 最短路径的智能页面导航（参照 ALAS 设计）
- 📊 **数据统计分析**：按卡池时间线展示特出记录、UP/歪统计、垫抽计数
- 💾 **数据管理**：SQLite 本地存储（自动去重），支持 JSON 导入/导出
- 🎨 **可视化图表**：pyecharts 图表展示（远期完善）
- 🔮 **远期规划**：微信小程序数据展示、手机端悬浮窗采集

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
│   │   ├── gacha_scanner.py        # 召集记录扫描主逻辑
│   │   ├── errors.py               # 自动化异常类
│   │   └── pages/                  # 各页面按钮定义
│   │       ├── main.py             #   主界面
│   │       ├── gacha_home.py       #   招集主页
│   │       ├── gacha_details.py    #   概率详情页
│   │       └── gacha_record.py     #   召集记录页
│   ├── ocr/                        # OCR 识别
│   │   ├── engine.py               # EasyOCR 子进程封装
│   │   ├── worker.py               # OCR 子进程脚本
│   │   └── parser.py               # 结果解析（按列位置 + 模糊匹配纠错）
│   ├── models/                     # 数据模型
│   │   └── gacha_record.py         # 抽卡记录（5★特出/4★优异/3★新生...）
│   ├── storage/                    # 数据存储
│   │   ├── database.py             # SQLite (SQLAlchemy ORM)
│   │   └── exporter.py             # JSON 导出/导入
│   └── gui/                        # 桌面 GUI (PyQt6)
│       ├── main_window.py          # 主窗口（暗色主题）
│       └── pages/                  # 各页面
│           ├── home_page.py        # 首页概览（卡池时间线）
│           └── settings_page.py    # 设置页（模拟器/OCR/扫描）
├── assets/
│   ├── templates/                  # UI 模板图片（页面识别用）
│   │   ├── main/                   #   主界面模板
│   │   ├── gacha/                  #   招集页模板
│   │   ├── gacha/details/          #   详情页模板
│   │   ├── gacha/details/record/   #   记录页模板（翻页/选择等）
│   │   └── shared/                 #   通用模板
│   ├── icons/                      # 图标
│   └── styles/                     # 样式
├── config/
│   ├── default_config.yaml         # 默认配置（ADB/OCR/扫描参数）
│   └── names.yaml                  # 器者名称 + 卡池 UP 词库
├── tools/
│   └── coordinate_viewer.py        # 坐标标记查看工具
├── tests/
├── requirements.txt
└── README.md
```

## 快速开始

### 环境要求

- Python 3.10+
- Windows / macOS / Linux
- ADB (Android Debug Bridge)
- 模拟器（MuMu / 雷电 / 蓝叠）

### 安装

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

# 启动应用
python -m src.main
```

### 使用说明

1. 在模拟器中打开《物华弥新》
2. 启动本程序，进入"设置"页面连接模拟器
3. 点击"开始扫描"，程序将自动导航到召集记录并逐页识别
4. 在"首页概览"查看按卡池分组的时间线和 UP/歪统计

## 技术栈

| 模块 | 技术 |
|------|------|
| GUI | PyQt6 |
| OCR | EasyOCR（子进程批量处理） |
| 图像识别 | OpenCV（模板匹配 + 颜色检测） |
| 模拟器控制 | ADB (subprocess) |
| 数据库 | SQLite + SQLAlchemy |
| 图表 | pyecharts (ECharts) |
| 日志 | loguru |
| 后端 (远期) | FastAPI |
| 小程序 (远期) | uni-app (Vue3) |
