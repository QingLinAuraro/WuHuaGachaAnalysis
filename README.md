# 🎴 WuHuaGachaAnalysis

《物华弥新》抽卡记录 OCR 识别与统计分析工具。

## 功能

- 🖥️ **PC端自动化扫描**：通过 ADB 连接模拟器，自动进入"召集记录"界面，逐页截图并 OCR 识别
- 📊 **数据统计分析**：稀有度分布、保底计数、出率分析、每日趋势等
- 🎨 **可视化图表**：饼图、折线图、柱状图等 ECharts 图表展示
- 💾 **数据管理**：SQLite 本地存储，支持 JSON 导入/导出
- 🔮 **远期规划**：微信小程序数据展示、手机端悬浮窗采集

## 项目结构

```
WuHuaGachaAnalysis/
├── src/
│   ├── main.py                 # 程序入口
│   ├── config.py               # 配置管理
│   ├── emulator/               # 模拟器控制
│   │   ├── adb_client.py       # ADB 连接与控制
│   │   ├── screenshot.py       # 截图模块
│   │   └── device.py           # 设备管理
│   ├── automation/             # 自动化引擎
│   │   ├── ui_navigator.py     # UI页面导航（状态机）
│   │   ├── gacha_scanner.py    # 召集记录扫描主逻辑
│   │   └── page_detector.py    # 页面识别（模板匹配）
│   ├── ocr/                    # OCR识别
│   │   ├── engine.py           # OCR引擎封装 (PaddleOCR)
│   │   └── parser.py           # 识别结果解析
│   ├── models/                 # 数据模型
│   │   ├── gacha_record.py     # 抽卡记录模型
│   │   └── banner.py           # 卡池信息
│   ├── storage/                # 数据存储
│   │   ├── database.py         # SQLite 数据库
│   │   └── exporter.py         # JSON 导出/导入
│   ├── analysis/               # 统计分析
│   │   ├── stats.py            # 统计计算
│   │   └── charts.py           # 图表生成 (pyecharts)
│   └── gui/                    # 桌面GUI (PyQt6)
│       ├── main_window.py      # 主窗口
│       └── pages/              # 各页面
│           ├── home_page.py    # 首页概览
│           ├── record_page.py  # 抽卡记录列表
│           ├── analysis_page.py# 统计分析页
│           └── settings_page.py# 设置页
├── assets/
│   └── templates/              # UI模板图片（页面识别用）
├── config/
│   └── default_config.yaml     # 默认配置
├── tests/                      # 测试
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

# 安装依赖
pip install -r requirements.txt

# 启动应用
python -m src.main
```

### 使用说明

1. 在模拟器中打开《物华弥新》
2. 启动本程序，进入"设置"页面连接模拟器
3. 点击"开始扫描"，程序将自动导航到召集记录并逐页识别
4. 在"首页概览"和"统计分析"中查看结果

## 技术栈

| 模块 | 技术 |
|------|------|
| GUI | PyQt6 |
| OCR | PaddleOCR |
| 模拟器控制 | ADB + OpenCV |
| 数据库 | SQLite + SQLAlchemy |
| 图表 | pyecharts (ECharts) |
| 后端 (远期) | FastAPI |
| 小程序 (远期) | uni-app (Vue3) |
