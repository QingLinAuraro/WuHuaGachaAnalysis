# 物华弥新抽卡分析器 — 代码导读

> 版本 1.0.0 | 面向后续扩展维护的代码级理解文档

---

## 目录

- [1. 启动流程](#1-启动流程)
- [2. 配置体系](#2-配置体系)
- [3. 图形界面 (GUI)](#3-图形界面-gui)
- [4. 模拟器控制 (Emulator)](#4-模拟器控制-emulator)
- [5. 自动化引擎 (Automation)](#5-自动化引擎-automation)
- [6. OCR 识别](#6-ocr-识别)
- [7. 数据模型与存储](#7-数据模型与存储)
- [8. 自更新模块 (Deploy)](#8-自更新模块-deploy)
- [9. 构建与打包](#9-构建与打包)
- [10. 开发工具](#10-开发工具)
- [11. 已知问题与改进方向](#11-已知问题与改进方向)
- [12. 快速索引](#12-快速索引)

---

## 1. 启动流程

### 1.1 整体流转

```
双击 .exe
  └─ launcher.py  ──── 配置 PATH → 运行更新器 → 启动主程序
       ├─ deploy/installer.py  ──── git pull + pip install
       └─ src/main.py  ──── 配置日志 → 启动 GUI
            └─ src/gui/main_window.py  ──── PyQt6 主窗口启动
```

### 1.2 `launcher.py` — 启动器（PyInstaller 编译为 .exe）

```
launcher.py
├─ L14-16   frozen 检测：打包后 sys.executable 所在目录 = Root
├─ L20-53   _show_error()        弹窗/控制台错误提示（双模式：msg.exe 或 print）
├─ L56-69   setup_environment()  将 toolkit/python、toolkit/Git、toolkit/adb 插入 PATH 最前面
├─ L72-108  main()
│   ├─ L74   setup_environment()
│   ├─ L79   检查 python.exe 存在，否则 _show_error 退出
│   ├─ L88   subprocess: python -m deploy.installer  运行更新器
│   │          失败 → _show_error 退出
│   └─ L101  subprocess.Popen: python -m src.main   启动主程序 → detach，launcher 立即退出
└─ L110     if __name__ == "__main__": main()
```

**关键点**：
- launcher 启动后立刻把 toolkit 目录下的嵌入式 Python / Git / ADB 加入 PATH
- 先跑更新器，再启动主程序，更新失败则不会进入主程序
- 主程序通过 `Popen` detach 启动，launcher 本身立即退出

### 1.3 `src/main.py` — 主程序入口

```
src/main.py
├─ L17-36   setup_logging()
│   ├─ L19   loguru 移除默认 handler
│   ├─ L22   添加 stdout handler（INFO 级别，带颜色）
│   └─ L27   添加文件 handler（DEBUG 级别，按日+10MB 轮转，保留1天）
├─ L39-47   main()
│   ├─ L41   setup_logging()
│   ├─ L44   打印版本号
│   └─ L47   launch_gui()  → 跳转 src/gui/main_window.py:711
└─ L50      if __name__ == "__main__": main()
```

**跳转链**：
- `launch_gui()` → `main_window.py:711`
  - 创建 `QApplication` → 创建 `MainWindow()` → 设置暗色主题 → `app.exec()`

---

## 2. 配置体系

### 2.1 `src/config.py` — 配置管理器

**类**：`Config`（单例，`__new__` 控制）

```
config.py
├─ L11-14   get_resource_root()   资源根目录（源码/模板/配置，只读）
├─ L16-19   get_data_root()       数据根目录（数据库/截图/日志，可写）
│            可通过环境变量 WUHUA_DATA_DIR 覆盖
├─ L29-49   Config.__new__ / __init__
│   ├─ L33   单例检查：_instance 存在则直接返回
│   ├─ L39   resource_root = get_resource_root()
│   ├─ L40   data_root = get_data_root()
│   ├─ L47   _ensure_dirs()  → 创建 data/ screenshots/ logs/
│   └─ L48   _load()  → 合并三层配置
└─ 方法
    ├─ L55-77   _load()
    │   ├─ L58   _defaults()  → 返回代码硬编码的默认值字典
    │   ├─ L62   读取 config/default_config.yaml  → _deep_merge()
    │   ├─ L68   检查 user_config.yaml 是否存在
    │   │   ├─ 存在 → 读取 → _deep_merge()
    │   │   └─ 不存在 → 复制 default_config.yaml 为 user_config.yaml
    │   └─ L75   把合并结果赋给 self._data
    ├─ L80-87   _deep_merge(base, override)
    │            递归合并：override 的键值覆盖 base，嵌套字典继续递归
    ├─ L89-125  _defaults()
    │            代码默认值：adb.path=None, template_threshold=0.8, gui: 900x600 等
    └─ L145-155 Config.get(key, default)
          支持点分隔路径如 "adb.path"、"automation.image_recognition.template_threshold"
```

**配置三层优先级**（高→低）：
1. 代码默认值（`_defaults()` 返回）
2. `config/default_config.yaml`（随版本分发）
3. `config/user_config.yaml`（用户修改，不随版本更新覆盖）

⚠️ **已知问题**：`_save()` 会将 `self._data` 完整写回 user_config.yaml，导致 user_config 不是"增量覆盖"而是"全量快照"。当 default_config 新增配置项后，user_config 会包含所有默认值，语义不够干净。

### 2.2 `config/default_config.yaml` — 默认配置

```yaml
adb:
  path: null                 # ADB 可执行文件路径（null = 用 PATH 中的 adb）
  screenshot_dir: screenshots
  serial: auto               # 设备串号（auto = 自动检测）
  search_paths:              # 模拟器搜索路径（Windows 专有 %ProgramFiles%）
    - ...
automation:
  image_recognition:
    action_interval: 0.5     # 操作间隔秒
    color_tolerance: 10      # 颜色匹配容差
    max_retries: 3
    min_width: 640
    min_height: 360
    navigation_timeout: 30   # 导航超时秒
    template_threshold: 0.8  # 模板匹配阈值
  # database.path 不写在这里：写相对路径会按启动时的 CWD 解析，换个启动方式就换了库。
  # 默认由 config.database_path 给出绝对路径 <数据目录>/data/gacha.db
  gacha:
    scan_page_delay: 2.0     # 每页扫描延迟
  gui:
    window_width: 900        # 窗口默认大小
    window_height: 600
    last_account_id: 1
```

### 2.3 `config/names.yaml` — 词库（238行）

两大数据块：

```yaml
characters:           # 角色名称，按职业-稀有度三级分组
  轻锐:
    特出: [...]      # 5★ 角色名列表
    优异: [...]      # 4★
    新生: [...]      # 3★
  远击: ...
  宿卫: ...
  构术: ...
  战略: ...

banners:              # 卡池名 → UP 角色名 映射
  金碧流彩: 金瓯永固杯
  杯酒释兵: 雪景寒林图
  ...
```

**用途**：OCR 解析阶段的词库纠错和稀有度查表。
- 角色名 → 模糊匹配 OCR 文本（`fuzzywuzzy` 的 `SequenceMatcher`，阈值 0.5/0.6）
- 卡池名 → 同样模糊匹配
- 稀有度 → 从角色在词库中的分组直接获取（不需要颜色识别）

---

## 3. 图形界面 (GUI)

### 3.1 文件结构

```
src/gui/
├── __init__.py          仅模块 docstring
├── main_window.py       主窗口 + 账户对话框 + 信号桥 + 样式 (720行)
└── pages/
    ├── home_page.py     首页概览：抽卡时间线、统计、导出导入 (291行)
    └── settings_page.py 设置页：模拟器连接、账户管理入口 (126行)
```

### 3.2 `main_window.py` — 核心详细解读

#### ScannerSignals (L275-280) — 跨线程信号桥

```python
class ScannerSignals(QObject):
    log_msg = pyqtSignal(str)      # 后台线程 → 主线程日志
    status_msg = pyqtSignal(str)   # 后台线程 → 主线程状态栏
    scan_done = pyqtSignal(int)    # 扫描完成 → 携带记录数
    scan_error = pyqtSignal(str)   # 扫描异常 → 携带错误消息
```

**设计意图**：扫描在后台 `threading.Thread` 中执行，不能直接操作 Qt 组件。通过信号桥将事件安全投递到主线程。

#### AccountDialog (L283-381) — 账户管理弹窗

```
AccountDialog(QDialog)
├─ __init__         接收 current_account_id → 固定 350x280 → _setup()
├─ _setup()         QListWidget + 新建/重命名/删除 三个按钮 + OK
├─ _refresh_list()  从 DB 拉取账户 → 填充列表，当前账户高亮
├─ _selected_id()   返回当前选中账户 ID（通过 list 的 data 存储）
├─ _on_new()        QInputDialog.getText → db.create_account() → _refresh_list()
├─ _on_rename()     QInputDialog.getText → db.rename_account()
│                   ⚠️ 成功后没有调 _refresh_list()，UI 不刷新
└─ _on_delete()     二次确认 QMessageBox → db.delete_account() → _refresh_list()
```

**跳转**：
- `_on_new` → `database.py:135 create_account()`
- `_on_rename` → `database.py:160 rename_account()`
- `_on_delete` → `database.py:180 delete_account()`
- 被调用位置：`MainWindow._on_manage_accounts` (L498)、`SettingsPage._open_account_dialog` (settings_page.py:92)

#### MainWindow (L384-708) — 主窗口

**状态属性**：

| 属性 | 初始值 | 类型 |
|------|--------|------|
| `_adb` | `None` | `Optional[ADBClient]` |
| `_scanner` | `None` | `Optional[GachaScanner]` |
| `_signals` | `ScannerSignals()` | 信号桥单例 |
| `_current_account_id` | `0` | 从 config 恢复 |
| `_accounts` | `[]` | 账户对象列表 |
| `_pages` | `[HomePage, SettingsPage]` | 页面实例列表 |

**生命周期流程**：

```
MainWindow.__init__ (L385)
├─ L391   _adb/scanner 置 None
├─ L392   _setup_ui()  → 构建全部 UI
├─ L393   _connect_signals()  → 连接信号/槽
├─ L394   _load_accounts()  → 从 DB 加载账户
└─ L397   设置窗口默认/最小尺寸 = 1100x680, min 800x500

MainWindow._setup_ui (L506) — 119行的 UI 构建
├─ L507   从 config 获取窗口尺寸
├─ L512   主布局 QVBoxLayout
├─ L515   顶栏 (QHBoxLayout, 固定高度 40px)
│   ├─ L522   标题 QLabel "物华弥新 抽卡分析器" (14pt, 白色)
│   ├─ L528   账户下拉框 QComboBox (固定高度 24px)
│   ├─ L532   管理按钮 QPushButton "..." (26x22)
│   ├─ L539   设备状态标签 QLabel (初始 "未连接 ●")
│   └─ L543   右侧弹簧 (addStretch)
├─ L549   中栏 (QHBoxLayout)
│   ├─ L553   侧边导航栏 (固定宽度 140px)
│   │   ├─ L558   ["概览", "设置"] 导航按钮
│   │   ├─ L563   每个按钮 36px 高
│   │   ├─ L571   右侧弹簧
│   │   └─ L574   开始扫描按钮 (38px 高)
│   └─ L585   内容区 QStackedWidget
│       ├─ L588   HomePage(account_id=0)  ← 首页
│       └─ L589   SettingsPage()           ← 设置页
│           ├─ L591   settings_page.on_adb_connected = self._on_adb_ready  ⚠️ monkey-patch
│           └─ L593   settings_page.main_window = self  ⚠️ monkey-patch
├─ L598   日志面板 (QTextEdit, 只读, 最大 2000 block)
└─ L616   状态栏 (QStatusBar, 固定高度 22px)

MainWindow._connect_signals (L403)
├─ ScannerSignals.log_msg      → _on_log       (追加日志)
├─ ScannerSignals.status_msg   → set_status     (更新状态栏)
├─ ScannerSignals.scan_done    → _on_scan_done  (扫描完成处理)
└─ ScannerSignals.scan_error   → _on_scan_error (扫描异常处理)
```

**核心方法详解**：

| 方法 | 行 | 功能 | 调用链 |
|------|-----|------|--------|
| `_on_log` | L409 | 追加日志行 + 每50条触发清理 | → `_trim_old_logs()` (L419) |
| `_trim_old_logs` | L419 | 移除 >10分钟的旧日志 | QTextDocument 逐 block 遍历解析时间戳 |
| `_on_scan_done` | L449 | 扫描完成：刷新所有页面，恢复按钮 | → `refresh_all_pages()`、`set_scan_enabled(True)` |
| `_on_scan_error` | L456 | 扫描失败：记录错误，恢复按钮 | → `set_scan_enabled(True)` |
| `_load_accounts` | L467 | 从 DB 加载账户到下拉框 | → `get_db().list_accounts()` |
| `_on_account_changed` | L490 | 切换账户：保存到 config，刷新页面 | → `config.set()`、`refresh_all_pages()` |
| `_on_manage_accounts` | L498 | 弹出账户对话框 | → `AccountDialog(...)` → `_load_accounts()` |
| **`_on_scan`** | L660 | 启动/停止扫描 ⭐ | 见下方详细流程 |
| `_on_adb_ready` | L655 | ADB 就绪回调（来自 SettingsPage） | 更新 `self._adb`，通知状态 |
| `refresh_all_pages` | L706 | 刷新所有页面 | → `page.refresh()` |
| `launch_gui` | L711 | 模块级函数，应用入口 | `QApplication` → `MainWindow()` → `exec()` |

#### `_on_scan` — 启动/停止扫描 (L660-696)

```
_on_scan()
├─ if self._scanner is not None and _scanner._is_running:
│   ├─ scanner.stop()        # 设置 _is_running = False
│   └─ set_scan_enabled(True)
│
├─ if self._adb is None:
│   ├─ log_msg("未连接")
│   └─ return
│
├─ scanner = create_scanner(self._adb)  → gacha_scanner.py:463
│   └─ return GachaScanner(adb, Screenshot(adb), PageDetector())
│       ├─ GachaScanner.__init__ (gacha_scanner.py:67)
│       │   ├─ self._adb = adb
│       │   ├─ self._screenshot = Screenshot(adb)    → screenshot.py:22
│       │   ├─ 获取屏幕尺寸 → self._screen_w, self._screen_h
│       │   ├─ self._navigator = UINavigator(...)    → ui_navigator.py:79
│       │   ├─ self._engine = get_ocr_engine()       → engine.py:70
│       │   └─ self._parser = GachaRecordParser()    → parser.py:42
│       └─ 内部定义"下一页"按钮 (_next_page_btn)
│
├─ scanner.set_account(self._current_account_id)
├─ scanner.set_banner("", BannerType.UNKNOWN)   # 卡池名/类型由 OCR 逐页覆盖
├─ scanner.on_progress = lambda msg: self._signals.log_msg.emit(...)
├─ scanner.on_record_found = lambda msg: self._signals.log_msg.emit(...)
├─ self._scanner = scanner
├─ set_scan_enabled(False)  # 按钮变为"停止扫描"
│
└─ threading.Thread(target=scanner.scan_all, daemon=True).start()
    └─ → gacha_scanner.py:153  scan_all()
```

### 3.3 `home_page.py` — 首页概览

#### 模块级常量与函数

| 名称 | 行 | 功能 | 注意 |
|------|-----|------|------|
| `_TYPE_ORDER` / `_TYPE_LABEL` | L179 / L187 | 5 类渠道的顺序与中文标签 | 未知类型殿后 |
| `_OFF_CAPABLE_TYPES` | L203 | **只有限定/限时判歪** | 招集/征集/赛季固定无歪 |
| `_RATE_TYPES` | L207 | 计入"不歪率"分母的类型 | 限定/限时/招集；征集、赛季不算 |
| `_find_duplicate_banner_keys()` | L21 | 扫原文找 `banners` 段重复卡池名 | YAML 会静默丢弃，解析后看不到，只能扫原文 |
| `_warn_duplicate_banner_keys()` | L79 | 重复时记日志 | 值相同→WARNING；**值不同→ERROR**（危险） |
| `_load_up_map()` | L105 | 从 `config/names.yaml` 读 banners 段 | 带 mtime 缓存；**失败返回 None，不静默给 `{}`** |
| `_lookup_up()` | L154 | 查某卡池的 UP 角色 | 多级容错：原样 → 去 `类型/` 前缀 → 去空白 |
| `_pool_key()` | L210 | 把 BannerType 归约为字符串键 | 用于按池子分组 |
| `_build_timeline()` | L217 | 核心：构建卡池抽卡时间线 | 返回 8 元组（含 `up_ready`, `rated_5`, `stats`） |

#### 卡池词库的键设计：复刻池**不需要**重复登记

`banners` 是「卡池名 → UP 角色」的直接映射（字典），判定歪不歪时只看**卡池名**，
与第几次上线、哪个版本无关。所以复刻池**沿用原键即可，不写第二遍**。

| 事项 | 结论 |
|------|------|
| 复刻池要不要再写一次 | **不要**。同一个键写两次，YAML 会静默丢弃前面那条 |
| 值相同（UP 没变） | 结果碰巧正确，但只是冗余；程序记 WARNING |
| **值不同（UP 换了 / 写错字）** | **危险**：新值静默覆盖旧值 → 历史记录的歪/不歪判定凭空改变；程序记 ERROR |
| 版本注释（`# 1.0` ~ `# 3.4`） | 纯给人看，YAML 解析时已丢弃，程序读不到，不参与任何逻辑 |

实测（**清理前**的状态，留作参考）：源文件 77 个键行 → 去重 73 → YAML 解析 **68** 条，
多出来的重复是 `乐彼之园` / `如君执笔` / `四海无争` / `刻名存念` 各 2 次（值都相同），
另有一处错字 `金声振玉`（正确写法是 `金声玉振`）。

**已于 2026-10-06 清理完毕**，现在文件是干净的：

| 清理项 | 处理 |
|--------|------|
| `乐彼之园`（3.3 段重复） | 删除，保留 1.6 段首次登记 |
| `如君执笔`（3.3 段重复） | 删除，保留 2.2 段首次登记 |
| `四海无争`（3.4 段重复） | 删除，保留 2.4 段首次登记 |
| `刻名存念`（3.4 段重复） | 删除，保留 2.5 段首次登记 |
| `金声振玉`（3.3 段错字） | 删除（正确写法 `金声玉振` 在 1.6 段） |

清理原则：**删后出现的复刻项，保留首次上线的那条**（版本归属更准确）。
清理后 `banners` 解析 67 条，键行数与解析条数一致（无键被吞），程序加载零告警。

> 提醒：删掉的是"源文件里的重复行"，不是"解析结果里的键"——
> 重复键本来就被 YAML 吞掉、不占解析条数，所以**解析条数不会等量减少**。
> 判断有没有误删的有效方法是比对"解析结果里消失的键"是否为空。

#### `_load_up_map()` —— 为什么不能静默失败

以前这里是 `try: ... except Exception: return {}`。词库读失败时悄悄给空字典，
界面上**所有红卡都会显示成"不歪"**，日志里却一点痕迹都没有 ——
用户只会看到"重开之后全不歪"，完全无法判断是数据问题还是真的没歪。

现在改成：

| 情况 | 返回 | 副作用 |
|------|------|--------|
| 文件不存在 / 读失败 / 解析失败 | `None` | `logger.error` 打一次（`_UP_MAP_WARNED` 去重防刷屏） |
| 正常 | `dict` | 按 `(路径, mtime)` 缓存，文件没改就不重复读盘 |

调用方 (`_build_timeline`) 据 `up_map is None` 把 `up_ready` 置 False，
UI 显示"⚠ 卡池词库未加载，歪/不歪统计不可用"，而不是给出错误的 0% 歪率。

#### 歪/不歪判定：**按渠道类型**决定，不是所有池都判

游戏里只有「限定」和「限时」两类渠道存在"歪"——UP 角色可能被别的红卡顶掉。
其余三类池子池内只出固定几个角色，**不存在歪的概念**：

| 渠道 | 池子性质 | 歪判定 | 计入不歪率 | 界面标签 |
|------|---------|--------|-----------|---------|
| **限定** | 有 UP，可能被顶 | 查 `banners` 词库判三态 | ✅ 计入 | `歪` / `UP` / `?` |
| **限时** | 有 UP，可能被顶 | 查 `banners` 词库判三态 | ✅ 计入 | `歪` / `UP` / `?` |
| **招集** | 自选复刻池，玩家自选四个角色，只在这四个里出 | **固定判无歪** | ✅ 计入 | **不打标签** |
| **征集** | 征集券日常池，固定四个红角色，**无保底** | **固定判无歪** | ❌ 不计入 | **不打标签** |
| **赛季** | 40 抽保底，池内只有一个赛季角色 | **固定判无歪** | ❌ 不计入 | **不打标签** |

代码里由两个常量控制：

```python
_OFF_CAPABLE_TYPES = (BannerType.LIMITED, BannerType.LIMITED_TIME)          # 只有这两类判歪
_RATE_TYPES = (BannerType.LIMITED, BannerType.LIMITED_TIME,
               BannerType.SUMMON)                                          # 计入不歪率的类型
```

> ⚠️ 这三类**不去查词库**。否则查不到 UP 就会落到 `unknown`，界面上冒出一堆
> 问号，反而让用户以为"数据有问题"——而实际上这类池根本不存在歪的概念。

#### `off` 的四态

| `off` | `off_state` | 含义 | UI |
|-------|-------------|------|-----|
| `True` | `"off"` | 歪了（出了非 UP 红卡） | 红框 + "歪" |
| `False` | `"up"` | 没歪（正好是 UP） | 蓝框 + "UP" |
| `None` | `"unknown"` | **无从判断**：限定/限时的卡池不在 `banners` 里，或词库未加载 | 灰框 + "?" |
| `False` | `"no_off"` | **该池无歪概念**（招集/征集/赛季） | 蓝框 + **不打标签** |

> ⚠️ 老写法 `off = bool(up_char) and name != up_char` 把"查不到 UP"和"真的没歪"
> 混成一件事，是"全变不歪"的直接原因。现在必须区分。
>
> `"no_off"` 是在此基础上的第二层修正：招集/征集/赛季确实"不歪"，
> 但它们不是"查不到 UP 所以猜不歪"，而是**规则上就没有歪**。

#### `_build_timeline(account_id)` 算法

```
1. up_map = _load_up_map()
   up_ready = (up_map is not None)；None 时用 {} 兜底但标记不可信
2. get_db().get_all_records(account_id) → 按 (pull_time, -seq_no) 升序（= 真实抽取顺序）
   ⚠️ 排序键必须含 seq_no：同分钟几十条的 pull_time 完全相同，
      只按它排会退化成按 record_id 的 md5 哈希排 → 真实顺序被随机打乱
3. 预扫一遍 records，算每条记录"在本分钟内的序位"（从最新端数，最新 = 0）：
   minute_pos[id(r)] = 该分钟总条数 - 该条在本分钟内的位次
   用途：切分"十连"（每 10 条一发），判定十连双红。
   ⚠️ 不用 seq_no：老库该列全 0，会把整分钟误并成一段
4. 遍历每条记录：
   - 维护 pity 字典（按 pool_key 分组，记录垫抽计数）
   - ⚠️ pity[pk] += 1 在"是否 SPECIAL"判断**之前**执行；
     因此 SPECIAL 分支里读到的 pity[pk] 就是"本次出红消耗的抽数"
   - 遇到 Rarity.SPECIAL(5★)：
       a. 【按渠道分两路】
          pk ∈ 限定/限时：
              up_char = _lookup_up(up_map, banner_name)
              ├ 有值 → off = (出的人 != up_char)，off_state 为 "off"/"up"
              └ 无值 → off = None，off_state = "unknown"，记入 unknown_banner_names
          pk ∈ 招集/征集/赛季：
              up_char = ""，off = False，off_state = "no_off"   # 不查词库
       b. 追加 {name, pull_number, pull_date, off, off_state, up_char, pity,
                ten_key}                                     # ten_key 用于十连分组
       c. pk ∈ _AVG_RATE_TYPES(限定/限时)：累加 avg_pulls[pk]
          ├ a["pulls"] += pity[pk]     # 本次出红消耗（含本次）
          └ a["hits"]  += 1
       d. 重置该池子的 pity = 0
          sec["offs"] / sec["unknowns"] 计数
          pk ∈ _RATE_TYPES 时 sec["specials_off_capable"] += 1
   - 其他稀有度：pity += 1
5. 循环结束：非零 pity 追加为"垫抽"提示行（**征集照旧显示垫抽**）
6. 每个 banner 的 chars 列表反转（最新出货在最前）
7. 对每个 banner 的 chars 调 `_mark_double_gold()`：
   按 ten_key 聚合，同一次十连里 ≥2 张红 → 打 gold_box/gold_total/gold_first
8. 【全局聚合 —— 注意排除征集】
   collect_total = 征集.total；collect_5 = 征集.specials
   total   = len(records) - collect_total        # 总抽数不含征集
   total_5 = Σspecials - collect_5               # 总特出不含征集
   avg_pull = Σavg_pulls[*].pulls / Σavg_pulls[*].hits   # 仅限定+限时，无数据则 None
9. unknown_count > 0 → logger.warning 列出涉及的卡池名
   up_ready 为 False → logger.error
10. 返回 (sections, total, total_5, off_count, account_name, up_ready, rated_5, stats)
    # 8 元组；stats = {avg_pull, avg_hits, collect_total, collect_5}
    ⚠️ 空库提前返回也必须给 8 个值（曾漏改成 6 个导致 GUI 启动崩溃）
```

**跳转**：
- `_load_up_map` 被 `_build_timeline:136` 调用
- `_lookup_up` 被 `_build_timeline:186` 调用（**只在限定/限时分支**）
- `_build_timeline` 被 `HomePage.refresh:336` 调用
- `_pool_key` 被 `_build_timeline:154` 调用

#### HomePage 类

```
HomePage(QWidget)
├─ __init__ (L235)
│   ├─ 顶部统计栏(self._stat) + 导出/导入按钮（固定高度）
│   └─ QTabWidget(self._tabs) 作为内容容器（setDocumentMode(True)）
├─ on_activated (L270) → refresh()
├─ _export_json (L273) → QFileDialog → export_to_json() → exporter.py
├─ _import_json (L287) → QFileDialog → import_from_json() → exporter.py
├─ refresh (L335)
│   ├─ _build_timeline(account_id) → 解包 **8 元组**（含 up_ready、rated_5、stats）
│   ├─ 统计栏 = self._stat_row + self._stat_row2（两行 QHBoxLayout，可自动换行）
│   │   每次刷新 takeAt 清空两行重建；段之间插 "|" 分隔
│   │   换行逻辑：_put() 先估总宽（中文13px/ASCII7px，含 ⓘ 的 24px），
│   │   超过 max(420, width*0.62) 且非行首 → 挪到第 2 行（**换行不补分隔线**）
│   │   ├─ account_name           → "[名字]"（蓝色加粗）
│   │   ├─ 总抽数（不含征集）      + ⓘ total  说明为何剔除征集
│   │   ├─ not up_ready           → "⚠ 卡池词库未加载，歪/不歪统计不可用"
│   │   ├─ rated_5 > 0 且可判断   → "特出: N/歪M"（**无 ⓘ**）
│   │   │                           + "不歪率: X%" + ⓘ rate
│   │   │                           （分母 = rated_5 - unknowns，只算限定/限时/招集）
│   │   ├─ rated_5 == 0 但有红卡  → 只报"特出: N"
│   │   └─ avg_pull is not None   → "平均出红: X.X 抽/红（N 次）" + ⓘ avg
│   │   ⚠️ "特出/歪" 后面【不挂 ⓘ】：曾误挂 rate 的 ⓘ 导致文案对不上
│   ├─ resizeEvent → 宽度变化 > 40px 时 refresh（重排统计栏换行）
│   ├─ 清空所有标签页（while count: removeTab）
│   ├─ 空库 → 统计栏放"暂无记录" + addTab(概览占位, "概览")
│   ├─ 有数据 → 逐渠道 addTab(_make_section_page(sec), _tab_label(sec))
│   │           _tab_label = f"{sec['label']} ({sec['total']})"
│   └─ 尽量恢复到刷新前选中的那个 tab
├─ _tab_label          (L499) 标签页标题："限定 (212)"
├─ _info_button        (模块级) 16px 圆形"!"按钮，点击 QMessageBox 弹口径说明
├─ _INFO_ALGORITHM     (模块级) dict：avg / total / rate / section 四份口径文案
├─ _make_section_page  (L503) 单个渠道页：
│       固定顶部渠道统计条（不再被列表挤没）+ QScrollArea(NoFrame)
│       内含垫抽行 + 各卡池 block
│       ⚠️ 卡池 block 用 QSizePolicy(Preferred, Maximum) + 布局末尾 addStretch()：
│          否则 block/标题行会分掉 col 剩余的纵向空间 → 标题高度随记录数变化
│       ⚠️ 卡池 block 不再画 border（用户要求去框线），只剩最淡底色
├─ _make_section_header (L406)  渠道统计条（setFixedHeight(34)）
│       底色 #26282d、无边框（原左侧 4px 蓝条已按"去框线"要求移除）
│       限定/限时："共N抽·特出N·歪N[·?K]"
│       征集     ："共N抽 · 出红 N 个"（单列说明走 ⓘ，不堆括号文案）
│       招集/赛季："共N抽·特出N"（不出现"歪 N"）
│       末尾统一跟一个 ⓘ 按钮（_info_button(_INFO_ALGORITHM["section"])）
├─ _make_title          (L656)  卡池标题：橙色、14px、粗体
│       ⚠️ setFixedHeight(30) + QSizePolicy(Fixed) —— 不能用 setMinimumHeight：
│          记录少时列表下方留白多，若标题行可纵向拉伸会被摊高/压扁
├─ _make_pity           (L780)  垫抽行：文字"已垫 N 抽"+ 同款柱体（颜色按区间，无头像）
│       行底：border-bottom 1px rgba(255,255,255,0.13) 浅白分割线
├─ _make_pull           (L747)  普通出货行 = _make_row(ch, "normal") 的薄封装
├─ _make_gold_group     (L755)  十连双红/三红组容器（**一次十连共用一个无缝背景**）：
│       QFrame **浅青底** rgb(28,44,50)≈#1c2c32、无边框；
│       顶部 head 区(setFixedHeight(22)) 放角标（浅青白 #bfeaf3 11px 粗体
│       "十连双红"/"十连N红"，位于该组最上方 ≈ 最上面那个头像的位置）
│       下面依次 addWidget(_make_row(c, "gold")) —— 组内各行透明 → 视觉连成一块
│       柱体与普通行同款（按抽数判色），组只负责"底色 + 角标"
├─ _make_row            (L787)  单个记录行的实际渲染（_make_pull / _make_gold_group 共用）：
│       布局 = 头像 | 角色名(固定 84px) | 柱状图 | 日期 | [歪]
│       · mode="normal"：底 #252526 + border-bottom 浅白细线（相邻记录的分割线）
│       · mode="gold"  ：background:transparent（让外层浅青底透出来，组内无缝）
│       ⚠️ 组内行必须显式 transparent，否则子行底色会盖掉外层容器底色，
│          又变回"两块颜色一样但有分割"的样子
│       · 只标注"歪"（红底白字）；不歪 / 无从判断一律不打标签
├─ _make_bar            (L815)  柱体：QFrame 绝对定位在 holder 里 + 柱内 QLabel
│       · 柱体宽度 = min(抽数,70) × 6px（最短 38px 保证柱内文字放得下）
│       · 柱内写"N抽"（纯白、标准字、无描边），**固定贴左 3px**，柱太窄自动缩字号
│       · 颜色：< 50 绿(#3fae5a) / 50-59 黄(#d7a52b) / ≥ 60 红(#c0392b)
│       · 双金组的柱体**也走同一套配色**（不再有金色特殊分支）
├─ _make_avatar         (L845)  角色头像：assets/avatars/<角色名>.png|jpg|webp
│                               有图则显示，无图回退"首字色块"占位
└─ ▲ 颜色/宽度辅助函数（模块级）：
        _bar_color(pulls)  /  _bar_width(pulls)
        _BAR_MAX_PULLS=70  /  _BAR_UNIT_PX=6.0  /  _BAR_MIN_PX=38
        _GOLD_GROUP_BG=(28,44,50)  十连双红组底（浅青）

> 十连双红的识别（`_ten_group_key` / `_mark_double_gold`，模块级）：
>   一次十连 = 同一分钟的 10 条记录；同分钟可能抽了多次十连 → 每 10 条切一段。
>   段的位置**从最新端数**（`_build_timeline` 里预先算好每条记录在本分钟内的
>   序位 `minute_pos`：分钟总条数 - 已数到位次）。
>   ⚠️ 不能直接用 `seq_no` 分组：老库该列全是 0，会把整分钟误并成一段。
```

> 标签页样式（`QTabWidget::pane` / `QTabBar::tab` / `:selected` 2px 蓝线）已在项目 QSS 里，无需新增。
> 头像素材：把 `<角色名>.png` 放进 `assets/avatars/` 即自动生效，无需改代码。

### 3.4 `settings_page.py` — 设置页

```
SettingsPage(QWidget)
├─ __init__ (L14)  回调初始化为 None，调用 _setup_ui
├─ _setup_ui (L21) 构建 UI
│   ├─ "模拟器连接" GroupBox
│   │   ├─ ADB 路径 QLineEdit（默认填 config 中的 adb.path）
│   │   ├─ 设备地址 QLineEdit（默认 "127.0.0.1:16384"）
│   │   ├─ 模拟器类型 QComboBox（["auto", "MuMu", "雷电", "蓝叠"]）
│   │   ├─ "检测" 按钮 → _detect()
│   │   └─ "连接" 按钮 → _connect()
│   ├─ "账户管理" GroupBox
│   │   └─ "管理账户" 按钮 → _open_account_dialog()
│   └─ "扫描设置" GroupBox（空壳占位，无控件）
├─ on_activated (L86)  pass（预留）
├─ refresh       (L89)  pass（预留）
├─ _open_account_dialog (L92)
│   ├─ 动态 import AccountDialog（避免循环导入）
│   ├─ AccountDialog(current_id).exec()
│   └─ main_window._load_accounts()  ⚠️ 反向调用 MainWindow
├─ _detect  (L106)
│   ├─ log_msg("正在检测设备...")
│   └─ addr = auto_detect_device()  → adb_client.py:383
│       ├─ 成功：填充地址输入框，log "检测到设备: {addr}"
│       └─ 失败：log "未检测到设备"
└─ _connect (L114)
    ├─ 创建 ADBClient(adb_path=path, serial=addr)
    ├─ adb.connect()  → adb_client.py:75
    ├─ 成功：
    │   ├─ self._adb = adb
    │   ├─ self._adb._serial = addr  ⚠️ 直接修改私有属性
    │   └─ on_adb_connected(adb)  → MainWindow._on_adb_ready
    └─ 失败：log 错误
```

### 3.5 GUI 样式系统

**两层样式**：

1. **全局 QSS**：`main_window.py:12-271`  `STYLE` 常量（~250行）
   - 类 VS Code 暗色主题
   - 选中 `QMainWindow`、`QPushButton`、`QTextEdit`、`QComboBox`、`QScrollBar` 等全局组件

2. **内联样式**：`home_page.py` 中大量使用 `widget.setStyleSheet(...)`
   - 卡池标题、出货行、垫抽行的颜色/字号/边框
   - ⚠️ 与全局 QSS 风格不统一

**配色方案**：
- 主背景：`#1e1e1e`（深灰黑）
- 侧边栏：`#252526`（稍浅）
- 选中高亮：`#37373d`
- 橙色（卡池标题）：`#f39c12`
- 蓝色（UP 标签）：`#3498db`
- 红色（歪标签）：`#e74c3c`

---

## 4. 模拟器控制 (Emulator)

### 4.1 文件结构

```
src/emulator/
├── __init__.py
├── adb_client.py    ADB 命令封装 (399行)
└── screenshot.py    截图工具 (67行)
```

### 4.2 `adb_client.py` — ADB 客户端

#### 模块级函数

```
find_adb(search_paths) → Optional[str]   L340
  ├─ 依次在三处查找 adb.exe：
  │   1. 环境变量 PATH
  │   2. 配置文件中的 search_paths（模拟器安装目录）
  │   3. shutil.which("adb")
  └─ 返回完整路径

list_devices(adb_path) → list[str]       L365
  └─ 执行 adb devices | grep device$ → 解析串号列表

auto_detect_device(path, serial) → str   L383
  ├─ 已有 serial → 直接返回
  ├─ 调用 find_adb + list_devices
  │   - 0 设备 → 抛异常
  │   - 1 设备 → 返回
  │   - 多设备 → EMULATOR_PORT_MAP:
  │       16384 → MuMu, 5555 → 雷电/蓝叠
  └─ 返回匹配的串号
```

**跳转**：`auto_detect_device` 被 `settings_page.py:107` 调用

#### ADBClient 类

```
ADBClient
├─ __init__(adb_path, serial, timeout=10)    L30
│   ├─ self._adb_path = find_adb() 或给定的 path
│   └─ self._serial = serial 或 auto_detect_device()
│
├─ 内部方法
│   ├─ _adb_cmd(args)              L39   构造 ADB 命令（-s serial 设备选择）
│   ├─ _run(args, check, timeout)  L47   执行 ADB 命令（subprocess.run）
│   └─ shell(cmd)                  L68   执行 ADB shell 命令
│
├─ 连接管理
│   ├─ connect()         L75   adb connect + 连接验证（shell echo）
│   ├─ disconnect()      L85   adb disconnect
│   └─ is_connected()    L93   检查连接状态（shell echo）
│
├─ 设备信息
│   ├─ get_screen_size()    L100  wm size → 解析 1280x720
│   ├─ get_orientation()    L110  dumpsys input
│   └─ get_package_name()   L119  dumpsys window
│
├─ 操作
│   ├─ click(x, y)          L130  input tap x y + 防抖 sleep(0.05)
│   ├─ click_button(btn)    L136  接受 Button 对象，取 coord() 坐标点击
│   ├─ swipe(x1, y1, x2, y2, duration=300)   L165
│   ├─ long_press(x, y, duration=1000)        L175
│   ├─ input_text(text)     L179  input text '...'  ⚠️ 注入风险
│   ├─ send_keyevent(code)  L186  input keyevent KEYCODE_BACK 等
│   └─ click_random(area)   L191  区域内随机坐标点击
│
├─ 应用管理
│   ├─ start_app(pkg)  L207  monkey -p pkg ... 或 am start
│   └─ stop_app(pkg)   L216  am force-stop
│
├─ 截图
│   ├─ screenshot(local_path)       L223  screencap → pull → rm（三步）
│   ├─ screenshot_bytes()           L250  screencap → exec-out cat → rm（一步，返回 bytes）
│   └─ screenshot_validate()        L270  调用 screenshot_bytes → 解码为 numpy
│       ├─ 验证分辨率 >= 640x360
│       ├─ 验证非全黑（平均亮度 > 1.0）
│       └─ 失败抛 AutomationError 或返回 numpy array
│
└─ 点击历史（未使用）
    ├─ _init_click_history()    L314  初始化 deque(maxlen=100)
    ├─ _record_click(x, y)      L325  记录 (x,y,time)
    └─ reset_click_history()    L326  清空历史
```

**跳转关键路径**：
- `screenshot_validate()` → `gacha_scanner.py:393`（扫描截图）
- `screenshot()` → `screenshot.py:32`（Screenshot.capture）
- `click()` → `ui_navigator.py:127`、`gacha_scanner.py:302,403`
- `connect()` → `settings_page.py:120`

### 4.3 `screenshot.py` — 截图工具

```
Screenshot(adb_client)
├─ capture()             L28   ADB 截图到临时文件 → PIL Image.open
│                             临时文件 = tempdir / "wuhua_tmp.png"  ⚠️ 固定路径
├─ capture_as_array()    L41   capture() → convert("RGB") → BGR numpy [::-1]
└─ capture_and_save(dir) L49   capture → 编号保存 + 返回 (numpy, path)
```

---

## 5. 自动化引擎 (Automation)

### 5.1 文件结构与层级

```
src/automation/
├── __init__.py           公开 API 汇总
├── errors.py             异常类 (37行)
├── button.py             按钮识别对象 (594行)
├── page_graph.py         页面图 + BFS 导航 (537行)
├── page_detector.py      页面识别器 (334行)
├── ui_navigator.py       导航器（双策略）(393行)
├── gacha_scanner.py      扫描器主流程 (468行)
└── pages/                页面按钮定义
    ├── main.py            主页按钮
    ├── gacha_home.py      招集主页按钮
    ├── gacha_details.py   概率详情按钮
    ├── gacha_record.py    召集记录按钮
    └── gacha_channel.py   渠道切换面板（5 个渠道条目）
```

### 5.2 `button.py` — Button 统一识别对象 (参照 ALAS 框架)

```
Button
├─ __init__(area, color, button, file, similarity=0.85, threshold=10)
│   至少需要 area。file=模板图片路径，color=(r,g,b)颜色检测，button=在area内的子区域
│   ⚠️ area / button 对外统一传 xywh：(x, y, w, h)，w 向右、h 向下
│      内部经 xywh_to_xyxy() 转为 xyxy 存入 self.area / self.button
│   ⚠️ 如果 color 和 file 都是 None → 纯坐标按钮，appear() 永远 True
│
├─ _ensure_template()     L466  延迟加载模板图片（首次调用时才加载）
│
├─ appear(image)          L282  三级检测：
│   ├─ if color 存在 → _appear_by_color(image)    ← 最快
│   ├─ elif file 存在 → _appear_by_template(image) ← 较慢
│   └─ else → True（纯坐标按钮，始终"可见"）
│
├─ _appear_by_color    L306  区域平均颜色 + 相似度判断
├─ _appear_by_template L311  cv2.matchTemplate + 阈值判断
│   ⚠️ 结果矩阵 = (H_area - h_tpl + 1, W_area - w_tpl + 1)
│      若 area 尺寸 == 模板尺寸 → 退化为 1×1，零位移容错，极易误判"不可见"
│      故 area 必须比模板大一圈（建议各边留 15~25px 余量）
│
├─ match(image)        L343  模板匹配，返回 (x, y, w, h, score) 或 None
│   搜索范围：area 指定的区域
│
├─ match_multi(image)  L375  查找所有匹配位置
│   去重逻辑：曼哈顿距离 < min_distance=10 视为同一匹配
│
├─ coord()             L427  推荐点击坐标
│   ├─ 先 try match() → 用匹配区域的随机点
│   └─ 否则 → button_center() 区域中心 + 正态分布随机偏移 (sigma=2)
│
├─ button_center()     L436  返回 button 区域中心坐标
│
└─ 组合方法
    ├─ crop_button(area)  L502  创建子 Button，area 传相对 xywh
    ├─ move_button(vec)   L524  平移按钮
    └─ _from_xyxy(...)    L536  内部构造，直接使用 xyxy（跳过转换），供上述两者使用
```

**坐标工具函数**：
- `xywh_to_xyxy(box)` — `(x, y, w, h)` → `(x1, y1, x2, y2)`，Button 入口处唯一转换点
- `crop` / `get_color` / `area_offset` / `random_point_in_area` — 全部沿用 xyxy 语义，无需改动

**调用关系**：
- `appear()` → 被 `page_graph.py` 识别页面、`ui_navigator.py` 检测弹窗调用
- `match()` → 被 `page_graph.py` 精确定位、`gacha_scanner.py` 查找翻页按钮调用
- `coord()` → 被 `page_graph.py` 和 `ui_navigator.py` 获取点击坐标

### 5.3 `errors.py` — 异常类

```python
AutomationError          基类异常
├── GameStuckError       卡住异常（携带 page_name, timeout）
├── PageUnknownError     页面未知异常（携带 message）
└── NavigationError      导航失败异常（携带 from_page, to_page, reason）
```

### 5.4 `pages/*.py` — 页面按钮定义

4 个文件结构一致，每个导出 `CHECK_*`（页面识别按钮）和 `BTN_*`（跳转按钮）。

⚠️ **坐标格式统一为 xywh**：`(x, y, w, h)` —— x/y 是左上角，**w 向右延伸，h 向下延伸**。
`Button.__init__` 内部会调用 `xywh_to_xyxy()` 转成 xyxy 存储，因此 `crop` / `get_color` /
`area_offset` / 匹配坐标反算等内部逻辑仍按 xyxy 语义工作，外部无需感知。

```
pages/main.py         (主页)
├── CHECK_MAIN        area=(902, 344, 171, 203)   ← "召集"入口识别
└── BTN_GACHA         area=(902, 344, 171, 203)   ← "召集"入口点击

pages/gacha_home.py   (招集主页)
├── CHECK_GACHA_HOME  area=(945, 77, 149, 51)     ← "概率详情"按钮识别
├── BTN_DETAILS       area=(945, 77, 149, 51)     ← "概率详情"按钮点击
└── BTN_BACK1         area=(5, 4, 199, 56)        ← 返回主界面

pages/gacha_details.py (概率详情页)
├── CHECK_GACHA_DETAILS  area=(752, 65, 250, 61)  ← "召集记录" tab 识别
├── BTN_GACHA_RECORD     area=(752, 65, 250, 61)  ← "召集记录" tab 点击
└── BTN_BACK             area=(522, 638, 247, 56)

pages/gacha_record.py (召集记录页)
├── CHECK_GACHA_RECORD  area=(395, 553, 695, 67)   ← 覆盖翻页栏漂移范围
├── BTN_PAGE_UP         area=(395, 553, 335, 67)   button=(413, 561, 106, 50)  ← "上一页"
├── BTN_PAGE_DOWN       area=(750, 553, 340, 67)   button=(962, 564, 108, 43)  ← "下一页"
├── BTN_SELECT          area=(1185, 137, 46, 38)   ← 展开渠道选择面板（下拉箭头，紧贴框）
└── BTN_BACK            area=(522, 638, 247, 56)

pages/gacha_channel.py (渠道切换面板)
├── CHANNEL_PANEL_AREA  = (1048, 175, 185, 235)    ← 面板展开后的整块列表区域
├── CHANNEL_ORDER       = (限时, 限定, 招集, 征集, 赛季)   ← 面板内自上而下
├── CHANNEL_BUTTONS     = {类型: Button}           ← 每个类型一个条目模板
│   └── area 全部用 CHANNEL_PANEL_AREA，match() 在区域内搜索对应条目模板
│       限时=xianshi.png  限定=xianding.png  招集=zhaoji.png
│       征集=zhengji.png  赛季=saiji.png
├── find_visible_channels(img) → [类型, ...]        ← 面板里"未选中态"的条目，自上而下
└── channel_by_elimination(visible) → 类型 | UNKNOWN ← 排除法猜当前选中渠道
```

**⚠️ 渠道条目模板是"未选中态"**

面板展开时，**当前渠道**处于选中态（浅色高亮底 + 绿勾），与未选中态模板差异很大，
拿它自己的模板去反查会失配。实测：截图里「限时渠道」选中时，
用 `xianshi.png` 匹配得到 **0.891**，且最佳位置落在「**限定渠道**」上（张冠李戴）。

由此可以反推出一条规律，`find_visible_channels()` 就建立在它上面：

| 面板里的条目 | 匹配模板 | 含义 |
| --- | --- | --- |
| 未选中态（深色底、无勾） | 匹配得到（实测 0.988 ~ 0.990） | 可切换的目标 |
| 选中态（浅色高亮底 + 绿勾） | 匹配不到 | 当前正在看的渠道 |

- **切换渠道**：只对目标渠道匹配。目标必然是未选中态（当前选中的那个刚扫完、已进已扫集合），
  所以不会踩坑 —— 实测 4 个未选中条目的得分 0.988 ~ 0.990，点击位置全部准确。
- **点错行的防护**：`find_visible_channels()` 按得分从高到低收录，中心 y 相差 ≤ 20px 的只留高分那个。
  不加这一步，上面那个 0.891 的张冠李戴会让「限时」和「限定」各占一条，
  面板条目数被算多 1 个，"全部扫完"的判定就永远到不了。
- **识别"当前是哪个渠道"**：首选用 OCR（`GachaScanner._detect_channel`，记录内容里带类型）；
  OCR 认不出类型时，再用 `channel_by_elimination()` 兜底 —— 面板里恰好少一个就是它。
  **但不要在能走 OCR 时改用排除法**：账号没开通全部渠道类型时，剩下好几个，判断不出来。

**⚠️ 扫描渠道总数以"展开后显示的条目"为准**

`gacha.auto_switch_channel = true` 时，每扫完一个渠道就把面板展开一次，
用 `find_visible_channels()` 数出面板上实际有几条，再算总数：

```
total_channels = len(set(visible) | {当前渠道})     # 当前选中那条匹配不上，单独补进来
```

不能写死成 5（`CHANNEL_ORDER` 的长度）—— 账号可能只开通了其中几个，
游戏以后也可能再加渠道类型。终止条件为 `len(scanned_channels) >= total_channels`；
另外还有一道保险：面板里已经挑不出"没扫过"的条目时也停。

**⚠️ 模板匹配的 area 必须比模板大一圈（展开按钮是唯一的例外）**

`_appear_by_template()` 走的是 `cv2.matchTemplate(crop(image, area), template, TM_CCOEFF_NORMED)`。
结果矩阵尺寸 = `(H_area - h_tpl + 1, W_area - w_tpl + 1)`。

**若 `area` 尺寸恰好等于模板尺寸，结果矩阵退化为 `1×1` —— 只有唯一一个采样点，位移容错为 0。**
此时画面只要有几个像素的抖动/抗锯齿差异，得分就会暴跌到阈值以下，表现为"模板明明一样却匹配不到"。
实测：同一画面下，零位移得分 0.99；仅平移 5px 后，精确 area 掉到 **0.775**（低于 0.8 阈值 → 失败），
而 `area` 外扩 20px 后依然 **0.99**。

**更隐蔽的翻车方式：搜索区比模板还小。** `_appear_by_template` 里有
`if search_region.shape < template.shape: return False` —— 高度或宽度差 1px 就永远匹配不上。
（历史案例：`select.png` 曾是 41×39，而用户给的紧贴框 `(1185,137,46,38)` 只有 38px 高，直接失效。）

**例外：`BTN_SELECT` 故意用了紧贴框**。模板换新后 `select.png` = 46×38，与搜索区
`(1185, 137, 46, 38)` **尺寸完全相等**，也就是上面说的 1×1 零容错。之所以敢这么用，是因为实测：

- 该点得分 **0.9940**（阈值 0.8），余量极大；
- 左/右移 20px、上/下移 15px 后得分全部 **≤ 0.0059** —— 唯一性极好，不存在"差几像素就匹配到别处"的风险；
- **不放大**才使它（y 137~175）与下方渠道面板（y 175~410）完全不重叠。
  早前外扩成 `(1175, 127, 62, 56)` 时，y 会伸到 183px，与面板顶部交叠。

所以：一般按钮请在模板外包一圈余量（建议上下左右各 15~25px）；
只有在"模板稳定、位置固定、且外扩会引入干扰区域"时才考虑紧贴框，并且必须实测周边平移得分来证明唯一性。

⚠️ **坐标基准**：全部基于 1280×720 分辨率，非此分辨率的模拟器需要缩放（`UINavigator._coord()` 有缩放逻辑，但 Page 图中的 Button 直接使用原始坐标，未做缩放适配）。

### 5.5 `page_graph.py` — 页面图导航系统

#### Page 类 — 页面节点

```python
class Page:
    name: str                       # 页面名称（自动从变量名获取）
    check_button: Button            # 识别按钮（appear=True → 当前在此页面）
    links: dict[str, Button]        # {目标页面名: 跳转按钮}
    parent: Optional[Page]          # BFS 寻路后的父节点（指向来源页面）
```

**关键方法**：

| 方法 | 行 | 功能 |
|------|-----|------|
| `clear_connection()` | L40 | 清除所有 Page 的 parent（准备重新寻路） |
| `init_connection(dest)` | L46 | **BFS 反向搜索**：从 destination 出发，BFS 遍历所有页面填充 parent 指针。⚠️ 注释说 A* 但实际是纯 BFS（无启发函数） |
| `iter_pages()` | L70 | 遍历 all_pages 注册表 |
| `link(page, button)` | L111 | 添加一条边（自身 → page，通过 button 跳转） |

#### PageGraph 类 — 导航引擎

```
PageGraph
├─ __init__(pages)                    L130  接收页面列表
│
├─ get_current_page(screenshot)       L155
│   ├─ 遍历所有 Page 的 check_button
│   └─ 返回第一个 appear=True 的 Page（或 None）
│
├─ is_page(page, screenshot)          L200
│   └─ page.check_button.appear(screenshot)
│
├─ ⭐ goto(destination, screenshot_fn, click_fn)  L215  核心导航
│   └─ 流程：
│       1. L245  Page.init_connection(dest)  → BFS 构建路径树
│       2. L257  get_current_page() → 确认当前位置
│       3. L262  _reset_stuck() → 重置卡住计时
│       4. L264  循环直到到达目标（最多 max_retries * 3 次）：
│           a. L268  如果当前页未知 → _handle_unknown()  ⚠️ 空实现！
│           b. L278  通过 parent 链找下一步（从当前位置回溯到目标的前一步）
│           c. L294  _execute_hop(from, to, button) → 执行单跳
│           d. L303  _check_stuck() → 超时检测
│           e. L305  重试+间隔
│
├─ ensure(destination, ...)           L312  快捷版：先检查是否已在目标，否则 goto
│
├─ _execute_hop(from, to, button)     L327  执行单跳
│   ├─ L352  button.appear(screenshot) → 确认按钮可见
│   ├─ L363  button.match(screenshot)  → 精确定位
│   ├─ L369  button.coord() → 获取点击坐标
│   ├─ L371  click_fn(coord) → 执行点击
│   └─ L377  _wait_for_page(to) → 等待并验证到达
│       ├─ 最多等待 navigation_timeout 秒
│       ├─ 每 0.5s 截图 + is_page() 检查
│       └─ 超时返回 False
│
├─ _wait_for_page(expected, ...)      L379
│
├─ _detect_popup(screenshot)          L419  ⚠️ 永远返回 False（空实现）
├─ _close_popup(screenshot, click_fn) L428  ⚠️ 空实现（只 log）
├─ _handle_unknown(screenshot, click) L443  ⚠️ 空实现（只 log → True）
│
├─ _check_stuck()                     L456  检查是否超时（基于 _nav_timeout）
└─ _reset_stuck()                     L467  重置开始时间
```

#### build_wuhua_pages() — 构建页面图 (L477-526)

```python
def build_wuhua_pages():
    PAGE_MAIN = Page("PAGE_MAIN", CHECK_MAIN)
    PAGE_GACHA_HOME = Page("PAGE_GACHA_HOME", CHECK_GACHA_HOME)
    PAGE_GACHA_DETAILS = Page("PAGE_GACHA_DETAILS", CHECK_GACHA_DETAILS)
    PAGE_GACHA_RECORD = Page("PAGE_GACHA_RECORD", CHECK_GACHA_RECORD)

    PAGE_MAIN.link(PAGE_GACHA_HOME, BTN_GACHA)              # 主页 → 招集主页
    PAGE_GACHA_HOME.link(PAGE_MAIN, BTN_BACK1)              # 招集主页 → 主页
    PAGE_GACHA_HOME.link(PAGE_GACHA_DETAILS, BTN_DETAILS)   # 招集主页 → 概率详情
    PAGE_GACHA_DETAILS.link(PAGE_GACHA_HOME, BTN_BACK_DETAILS)  # 概率详情 → 招集主页
    PAGE_GACHA_DETAILS.link(PAGE_GACHA_RECORD, BTN_GACHA_RECORD) # 概率详情 → 召集记录
    PAGE_GACHA_RECORD.link(PAGE_GACHA_HOME, BTN_BACK_RECORD)     # 召集记录 → 招集主页

    return [PAGE_MAIN, PAGE_GACHA_HOME, PAGE_GACHA_DETAILS, PAGE_GACHA_RECORD]
```

**页面图拓扑**：
```
PAGE_MAIN ──→ PAGE_GACHA_HOME ──→ PAGE_GACHA_DETAILS ──→ PAGE_GACHA_RECORD
   ↑              ↑                      │
   └──────────────┘◄─────────────────────┘
```

### 5.6 `page_detector.py` — 页面识别器（旧系统）

⚠️ **两套识别系统并存**：`PageDetector` 和 `PageGraph.get_current_page()` 功能重叠但实现独立。

```
PageDetector
├─ __init__(templates_root)
│   ├─ _load_templates()        加载 assets/templates/ 下所有子目录的 Button
│   └─ _load_legacy_templates() 加载旧版全图模板
│
├─ detect(screenshot) → GamePage 枚举
│   ├─ _detect_by_buttons()         优先：遍历所有 Button.appear()
│   └─ _detect_by_legacy_templates() 回退：全图模板匹配
│
└─ 工具方法
    ├─ _match_template(img, template_path)  cv2.matchTemplate + 缩放适配
    └─ _page_name_to_enum(name)             目录名 → GamePage（仅映射 main/gacha）
```

**使用场景**：供 `_try_image_navigation()` 之前的页面识别，以及 `gacha_scanner._next_page()`
里的"是否还认得当前页面"判断（认得不出就安全停机）。

### 5.7 `ui_navigator.py` — UI 导航器

```
UINavigator
├─ __init__(adb, screenshot, page_detector, graph)
│   └─ self._popup_close_btn = Button(area=右上角区域)  ⚠️ 无模板文件
│
├─ NavState 状态机：
│   IDLE → NAVIGATING_TO_GACHA → AT_RECORDS → SCANNING → COMPLETED/ERROR
│
├─ go_to_gacha_records()  ⭐ 主入口
│   └─ _try_image_navigation()      唯一策略：PageGraph 图像识别
│       ├─ _safe_screenshot()
│       ├─ PageGraph.get_current_page()
│       │   ├─ 识别不出当前页 → 报错返回 False（不做盲点击）
│       │   └─ 可识别 → PageGraph.ensure(GACHA_RECORD)
│       └─ 到达 GACHA_RECORD → 返回 True
│
├─ _safe_screenshot()     L116  调用 screenshot.capture_as_array()
├─ _safe_click(x, y)      L124  调用 adb.click() + _record_click()
│
├─ _detect_popup          无模板时恒返回 False
├─ _handle_popup          只有配置了关闭按钮模板才点击，否则不做任何操作
└─ go_back()              发送 KEYCODE_BACK
```

**调用关系**：
- `go_to_gacha_records()` ← `gacha_scanner.py:182`
- `_safe_screenshot()` ← 多处内部调用 (L188,220,292,322,367)
- `_safe_click()` ← 作为 click_fn 回调传给 `PageGraph.goto()` (L201)

### 5.8 `gacha_scanner.py` — 扫描器主流程 ⭐

#### 模块级函数

```
_compute_text_hash(text)           L44  → hashlib.md5(text).hexdigest()（text_hash，调试用）
create_scanner(adb)                L463 → GachaScanner(adb, Screenshot(adb), PageDetector())
```

#### GachaScanner 类

```
GachaScanner
├─ __init__(adb, screenshot, page_detector)   L67
│   ├─ 核心依赖注入：adb, screenshot, page_detector
│   ├─ L77  self._navigator = UINavigator(adb, screenshot, page_detector, graph)
│   │       其中 graph = PageGraph(build_wuhua_pages())
│   ├─ L79  获取屏幕尺寸 → self._screen_w, self._screen_h
│   ├─ L83  self._engine = get_ocr_engine()   → engine.py:70（延迟加载）
│   ├─ L84  self._parser = GachaRecordParser() → parser.py:42（加载词库）
│   ├─ L92  翻页按钮定义（⚠️ 与 pages/gacha_record.py 重复）
│   │   └─ _next_page_btn   area=(750, 553, 340, 67)  button=(962, 564, 108, 43)  # 只向前翻页
│   └─ L109 渠道切换相关
│       ├─ _expand_channel_btn = pages/gacha_record.py 的 BTN_SELECT（下拉箭头）
│       ├─ _panel_delay        = config: gacha.channel_panel_delay（面板弹出等待）
│       ├─ _max_pages          = config: gacha.max_pages_per_channel
│       └─ _action_interval    = config: automation.image_recognition.action_interval
│
├─ 回调设置
│   ├─ on_progress(msg)       L128  → UI 进度日志
│   ├─ on_record_found(msg)   L131  → UI 记录日志
│   ├─ on_complete(count)     L134  → (未被调用)
│   ├─ set_banner(name, type) L139  → 设置卡池上下文
│   └─ set_account(id)        L144  → 设置当前账户
│
├─ stop()                     L148  → self._is_running = False
│
├─ ⭐ scan_all()              L153  核心扫描流程
│   │
│   ├─ 初始化阶段
│   │   ├─ L159  stop() → 重置状态
│   │   ├─ screenshot.reset_counter()
│   │   ├─ adb.reset_click_history()
│   │   └─ 加载已有记录，构建"内容键 → 已有个数"计数表 (db_counts)
│   │       └─ get_db().get_all_records(account_id) → Counter(make_record_key(r))
│   │
│   ├─ 导航阶段
│   │   └─ navigator.go_to_gacha_records() → ui_navigator（识别不出页面就放弃，不盲点）
│   │
│   ├─ ⭐ 逐渠道扫描（外层循环 while _is_running）
│   │   │
│   │   ├─ 内层：逐页扫描循环 (while _is_running and page <= _max_pages)
│   │   │   ├─ _capture_screenshot() → 获取当前页截图
│   │   │   │   └─ → adb.screenshot_validate() → screenshot.capture_as_array() 回退
│   │   │   │
│   │   │   ├─ _scan_page(img) → 解析当前页所有记录
│   │   │   │   └─ 详见下方 _scan_page 详解
│   │   │   │
│   │   │   ├─ 第 1 页时 _detect_channel(records) → 核对"当前是哪个渠道"
│   │   │   │   切换成功后已有权威值（就是点进去的那个），OCR 只用来复核：
│   │   │   │   万一点错了条目，以页面实际内容为准（否则会把没扫过的渠道记成已扫）
│   │   │   │
│   │   │   ├─ 逐条补齐 banner_name / banner_type / account_id，暂存到 new_records
│   │   │   │
│   │   │   ├─ _next_page(img) → 点"下一页" + 像素差分判断是否真翻页
│   │   │   │   ├─ 匹配不到"下一页"按钮：
│   │   │   │   │   ├─ 仍能认出召集记录页 → 判定末页，正常结束
│   │   │   │   │   └─ 所有页面模板都匹配不上 → _abort_reason 置位 + 安全停机
│   │   │   │   └─ 内容未变化 → 退出内层循环（本渠道已到末页）
│   │   │   │
│   │   │   └─ 内层结束
│   │   │
│   │   ├─ scanned_channels.add(当前渠道)
│   │   │
│   │   ├─ 终止判断 A（满足任一即退出外层）
│   │   │   ├─ 安全停机 / 用户中断 / 连续截图失败
│   │   │   └─ config: gacha.auto_switch_channel = false
│   │   │
│   │   ├─ _open_channel_panel() → 展开面板，返回展开后的截图
│   │   │   └─ 判定"已展开"靠 find_visible_channels(img) 非空
│   │   │      （不能靠展开箭头：面板开/关时那支箭头外观一模一样）
│   │   │
│   │   ├─ visible = find_visible_channels(img) → 面板里"未选中态"的条目
│   │   │
│   │   ├─ 当前渠道仍未知（OCR 失败）→ channel_by_elimination(visible) 兜底
│   │   │   └─ 恰好剩一个 → 就是它；剩多个 → UNKNOWN（账号没开通那么多类型）
│   │   │
│   │   ├─ 终止判断 B
│   │   │   ├─ 渠道类型仍为 UNKNOWN → 停（否则会反复扫同一个渠道）
│   │   │   ├─ total_channels = len(set(visible) | {当前渠道})
│   │   │   │    len(scanned_channels) >= total_channels → 全部完成
│   │   │   │    ⚠️ 总数以"展开后显示的条目"为准，不写死 CHANNEL_ORDER 的长度
│   │   │   └─ target = visible 中第一个不在 scanned_channels 的 → 没有则停
│   │   │
│   │   └─ _switch_channel(target) → 失败则整体停机（不盲点击）
│   │       ├─ 截图 → get_channel_button(target).match(img)
│   │       │   ├─ 匹配不到 → 面板未展开 → 点 _expand_channel_btn，等待后重试
│   │       │   └─ 匹配到   → 点条目中心 (x + w//2, y + h//2)
│   │       ├─ 再截图，确认面板已收起（该区域不再匹配到条目）
│   │       └─ 重试 _max_retries 次仍失败 → 返回 False
│   │
│   ├─ 存在性判断 + 编号 + 入库（全部渠道扫描结束后一次性处理）
│   │   ├─ ordered = reversed(new_records)  → 旧→新，即内容键的规范顺序
│   │   ├─ 逐条过滤：pull_time.microsecond != 0 的行（时间未识别）剔除不入库
│   │   ├─ 分组计数：group_total[key] = 过滤后该内容键的条数
│   │   ├─ 逐条：seq = 距该组【最新那条】的偏移（最新 = 0，越旧越大）
│   │   │   ├─ (内容键, seq, 名称) 已在库 → 跳过
│   │   │   ├─ 否则 record_id = make_record_id(record, seq)
│   │   │   ├─ **record.seq_no = seq**（落库！否则同分钟排不出先后）
│   │   │   └─ pull_number 占位 0
│   │   ├─ get_db().add_records(to_insert) → database.py:332
│   │   └─ _resequence_numbers() → 按 **(pull_time, -seq_no)** 全库重编 pull_number
│   │
│   │   ⚠️ 判重不用 record_id，用 (内容键, seq, 名称) 三元组：
│   │      ID 算法换过几版，老记录的 ID 与新算法算的不是一回事，
│   │      直接比 ID 会把整批老记录当成新记录重复入库。
│   │      三元组可由老记录直接反推（seq = 组内时间降序名次），故能兼容。
│   │   ⚠️ 库内 seq 的还原键是 **(pull_time, pull_number) 降序**，不是 record_id：
│   │      record_id 是 md5 哈希，同分钟多条会被随机打乱顺序（曾导致
│   │      "水晶杯实际第 10 抽被算成第 1 抽"）；
│   │      pull_number 是按 (时间, seq_no) 全局重编过的稳定值，
│   │      老库里它就是插入顺序（实测与 id 完全一致）→ 新老数据都对。
│   │   ⚠️ **_resequence_numbers 的排序键必须是 `(pull_time, -seq_no)`**，
│   │      绝不能用 record_id —— 那是本次计数 bug 的根因。
│   │   ⚠️ db_keys 统计时跳过微秒非 0 的老记录（旧 now() 兜底产物，
│   │      内容键不可靠）——它们不参与判重，避免把该分钟的真实条数阈值抬高。
│   │      老记录本身不删除、不修改，界面照常显示。
│   │   ⚠️ seq 必须在【过滤后】的 ordered 上算。若拿过滤前的记录编号，
│   │      被剔除的兜底行会占掉位次，而它两次扫描"在不在本批里"可能不同，
│   │      导致其后每条记录的 seq 整体错开 → 判重失效、永久漏记录。
│   │
│   ├─ engine.shutdown()
│   └─ _notify_progress("扫描完成") → on_complete(count)
│
├─ _scan_page(img)           单页解析
│   │
│   ├─ 裁剪区域：header_h=218, records_bottom=551
│   │   img_cropped = img[218:551, 420:]    ← 去除顶部和左侧
│   │   ⚠️ 硬编码坐标，仅适配 1280×720
│   │
│   ├─ 计算 10 个记录行的 y 范围
│   │   total_h = records_bottom - header_h = 333
│   │   row_h = total_h / 10 = 33.3
│   │   regions = [(i*row_h, (i+1)*row_h) for i in range(10)]
│   │
│   ├─ ocr_results = engine.recognize_page(img_cropped, regions)
│   │   → OCR 子进程返回 [[{text, confidence, box}, ...], ...]
│   │   └─ 全部为空时重试一次（子进程超时兜底）
│   │
│   ├─ 逐行解析 (i = 0→9，页内从上到下 = 由新到旧)
│   │   ├─ _parser.parse_record_from_ocr_results(...) → GachaRecord
│   │   ├─ _extract_name_from_ocr() → 第一块名称文本
│   │   ├─ _parser.lookup_rarity(name) → 词库查稀有度
│   │   ├─ _parser._extract_time(...) → 解析时间
│   │   └─ 计算 text_hash（仅调试用）
│   │
│   ├─ 时间兜底修正（两步）：时间没识别出来的行用的是 datetime.now()，每次扫描都不同，
│   │   ① 先看上方最近一条已识别时间（同页更新的那条），跨页用 _last_known_time 续
│   │   ② 上方全都没有时（页首连续失败），改用下方最近一条已识别时间
│   │   → 保证多次扫描算出一致的"内容键"
│   │
│   └─ 返回 records 列表
│
├─ ⭐ _detect_channel(records)  L550  从记录推断"当前是哪个渠道"
│   └─ 取第一条 banner_type 非 UNKNOWN 的记录；全无则返回 UNKNOWN
│       ⚠️ 不要改用面板模板反查（当前渠道是选中态，会张冠李戴）。
│          OCR 认不出时由 scan_all 用 channel_by_elimination() 兜底。
│
├─ ⭐ _open_channel_panel()     L570  确保渠道面板展开，返回展开后的截图
│   ├─ 截图 → find_visible_channels(img) 非空 → 已展开，直接返回
│   ├─ 为空 → 点 _expand_channel_btn → 等待 _panel_delay → 重试
│   └─ 重试 _max_retries 次仍为空 → None（调用方据此停止自动切换）
│       ⚠️ 只能靠"面板里出现了渠道条目"判断展开，不能靠展开箭头 ——
│          实测面板开/关时 select.png 都是 0.9940，箭头外观完全一样
│
├─ ⭐ _switch_channel(target)   L609  展开渠道面板并点击目标条目
│   ├─ 截图 → get_channel_button(target).match(img)
│   │   ├─ 匹配不到 → 面板未展开 → 点 _expand_channel_btn，等待后重试
│   │   └─ 匹配到   → 点条目中心 (x + w//2, y + h//2)
│   ├─ 再截图确认面板已收起（该区域不再匹配到条目）
│   └─ 重试 _max_retries 次仍失败 → False（调用方据此整体停机）
│
├─ _capture_screenshot()
│   ├─ try: adb.screenshot_validate()  ← 带质量验证
│   └─ except: screenshot.capture_as_array()  ← 无验证回退
│
├─ _next_page(img)           翻页（只向前）
│   ├─ _extract_record_area(img) → 提取记录区域（用于差分比较）
│   ├─ _find_next_button(before) → Button.match() 找"下一页"；匹配不到返回 None
│   ├─ 匹配不到 → 交给 scan_all 的安全停机分支（不做盲点击）
│   ├─ adb.click(coord) → sleep(page_delay) → 再截图
│   └─ _content_changed(old, new) → 内容变化率 > 0.8% 视为翻页成功
│
├─ _content_changed(old, new)
│   └─ cv2.absdiff → gray > 25 的像素占比 > 0.008
│
└─ _notify_progress(msg)
    └─ if on_progress: on_progress(msg)
```

**关键设计点**：
1. **去重**：record_id = `md5(内容键 + 出现序号 + 角色名)`，
   内容键 = **时间(到分)|账户**；序号 = **距该组最新那条的偏移**（最新 = 0，越旧越大）。
   判定"存在"时**不比 record_id**，而是比 `(内容键, 序号, 角色名)` 三元组 ——
   这样无论库里老记录的 ID 是哪一版算法算的，都能认出"已入过库"
   - 序号必须以**最新那条**为基准：扫描永远从该组最新那条开始，
     读到一半中断时库里存的是"最新端连续若干条"，重扫算出的 seq 才能对上；
     若以最旧那条为基准，组的起点会随中断位置漂移，重扫会算成新记录重复入库
   - **角色名放进 record_id**：同一分钟能出几十条，光靠 seq 只表达"第几个位置"。
     若某位置库内是 A、本次读到 B（库里那条来自更早扫描、内容其实对不上），
     只靠 seq 会把 B 当成"位置已占用"而丢弃，B 永远进不来。
     加上名称后 A、B 各占一个位置，都能入库
   - 库内 seq 由**组内 (pull_time, pull_number) 降序名次**还原，
     **不能**用 record_id（md5 哈希会把同分钟多条随机打乱），
     也**不是**直接用 pull_number 当 seq（它是全库编号，每入库一批就整体重排）
   - seq 必须在**剔除兜底行之后**、基于真要入库的记录计算
   - 判重表统计时**跳过微秒非 0 的老记录**（旧 now() 兜底产物，内容键不可靠），
     否则会把该分钟的真实条数阈值抬高，导致该分钟最新的若干条真实记录被永久跳过。
     老记录不删除、不修改，界面照常显示
   - 代价：角色名来自 names.yaml，跨版本改词库（改名/加别名/调阈值）会让同一条
     记录算出不同的 record_id。靠上面的三元组判重来兼容，不影响正确性
2. **pull_number 分配**：入库后按【全库时间序】统一重编（`_resequence_numbers`），
   只作排序键。**排序键 = `(pull_time, -seq_no)`**：
   - 中断补齐更旧的记录时，若按"追加到最大值之后"编号，
     UI 按 pull_number 排序会把更旧的记录排到最新之后（垫抽顺序错乱）
   - **绝不能用 record_id 当同分钟内的次级排序键**：它是 md5 哈希，
     同一分钟几十条（一次十连必然同分钟）的顺序会被完全随机打乱 ——
     实测"水晶杯明明是第 10 抽却被算成第 1 抽、剩下 9 抽算进垫池"，
     就是旧版按 `(pull_time, record_id)` 排序造成的。改用 `seq_no` 后正确
   - 垫抽计数实际由 home_page 按渠道各自累加，与 pull_number 无关
3. **翻页检测**：像素差分比较，变化率 > 0.8% = 翻页成功
4. **扫描方向**：进入记录页默认在第 1 页，用"下一页"逐页向后读（正序）；
   页内 OCR 从上到下（i=0→9）= 由新到旧，配合扫描方向得到全局新→旧
5. **安全停机**：所有页面模板都匹配不上时不点任何东西，直接停止本轮扫描
6. **时间兜底两步**：`datetime.now()` 兜底的行（微秒非 0）先沿页内上方时间回填、
   页首再沿下方时间回填 —— 让内容键跨扫描稳定
7. **兜底行不入库**：回填后仍带微秒的记录（时间是 now()）逐条过滤掉，
   整批都是兜底时全拦。否则每次扫描都算出新内容键 → 反复重复计入

---

## 6. OCR 识别

### 6.1 文件结构

```
src/ocr/
├── __init__.py
├── engine.py     OCR 引擎（主进程调度，子进程隔离 PaddleOCR）
├── worker.py     OCR 子进程（独立进程运行 PaddleOCR）
└── parser.py     解析器（OCR 文本 → 结构化数据 + 词库纠错）
```

### 6.2 `engine.py` — OCR 引擎

```
OCREngine
├─ recognize_page(image: np.ndarray, regions: list[(y1,y2)])  L22
│   ├─ L26  输入验证：image 尺寸、regions 数量
│   ├─ L29  tempfile: 写入临时 PNG（delete=False）
│   ├─ L33  序列化 regions → JSON 字符串
│   ├─ L34  tmp_out = tmp_in.name + ".json"
│   ├─ L39  subprocess.run([
│   │         python, worker.py, 图片路径, regions_json, 输出json路径
│   │       ], timeout=60)
│   ├─ L42  超时/异常/非零返回 → 返回全空结果
│   └─ L61  finally: 删除两个临时文件
│
├─ shutdown()  L63  pass（空实现，无子进程清理逻辑）
└─ get_ocr_engine()  L70  模块级懒加载单例
    └─ global _ocr_engine; if None: _ocr_engine = OCREngine()
```

**⚠️ 性能核心问题**：每次 `recognize_page()` 都启动新的 Python 子进程，PaddleOCR 在子进程中重新初始化（加载模型 5-15 秒）。应改为长生命周期 worker 进程池，通过 stdin/stdout 或 socket 持续通信。

### 6.3 `worker.py` — OCR 子进程

```
ocr_regions(image_path, regions_json) → list[list[dict]]   L11
├─ L12  ocr = PaddleOCR(use_angle_cls=False, lang="ch", show_log=False)
├─ L15  img = cv2.imread(image_path)
│   └─ if img is None: return [[]]
├─ L18  遍历 regions:
│   ├─ L19  region = img[y1:y2, :]  ← 裁剪单行
│   ├─ L22  raw = ocr.ocr(region, cls=False)
│   │   └─ ⚠️ raw[0] 不检查长度，格式异常会崩溃
│   └─ L24  格式化为 [{text, confidence, box}, ...]
└─ L44  CLI 入口：argparse → ocr_regions() → json.dump
```

**环境变量**（L7-8）：`OMP_NUM_THREADS=1`, `MKL_NUM_THREADS=1` — 限制 CPU 线程数。

### 6.4 `parser.py` — 解析器 ⭐

```
GachaRecordParser
├─ __init__(banner_name)             L42
│   └─ L49  _load_name_dict() → 加载 names.yaml
│       ├─ L87  构建 _name_rarity_map: {角色名: Rarity值}
│       └─ L93  构建 _banner_up: {卡池名: UP角色名}  ⚠️ 死代码（从未使用）
│
├─ set_banner(name)                  L51
├─ lookup_rarity(name) → int         L56
│   └─ return self._name_rarity_map.get(name, Rarity.FINE)
│
├─ ⭐ parse_record_from_ocr_results(ocr_results, img_width, pull_number)
│   │                              L146  核心解析入口
│   │
│   ├─ L180  预处理：把所有 OCR 文本展平为 {x, y, text, confidence} 列表
│   │
│   ├─ L187  COLUMN_RANGES 列位置分离：
│   │   ├─ (0, 330)   → 名称列
│   │   ├─ (330, 500) → 卡池列
│   │   └─ (500, 830) → 时间列
│   │   ⚠️ 基于 860px 宽的裁剪后图片，硬编码像素范围
│   │
│   ├─ L190  按列归类 OCR 文本
│   │
│   ├─ L196  名称列 → _extract_name_from_column()  模糊纠错
│   │   ├─ L259  先取第一块文本作为候选名
│   │   ├─ L265  _fuzzy_match(候选, 所有角色名, threshold=0.6)
│   │   └─ 如果没有直接匹配 → 尝试拼接所有 OCR 文本后再模糊匹配
│   │
│   ├─ L197  lookup_rarity(name) → 从词库获取稀有度
│   │
│   ├─ L198  _extract_time() → 5 种正则模式匹配
│   │   ├─ 模式1: "%Y-%m-%d %H:%M" / "%Y-%m-%d %H:%M:%S"
│   │   ├─ 模式2: "YYYY年MM月DD日HH时MM分" 中文格式
│   │   ├─ 模式3: OCR 容错 "YYYY年MM月DD日HH时"（丢分）
│   │   └─ 模式4-5: 进一步容错变体
│   │
│   └─ L200  _extract_banner_from_text() → 卡池名称 + 类型推断
│       ├─ L242  _fuzzy_match(卡池OCR文本, 所有卡池名, threshold=0.5)
│       └─ L249  BannerType 推断（含"限时"/"限定"关键词）
│
├─ _fuzzy_match(text, candidates, threshold)  L115
│   └─ difflib.SequenceMatcher 计算相似度 → 选最佳匹配
│
└─ COLUMN_RANGES  L140  [(0,330), (330,500), (500,830)]
```

---

## 7. 数据模型与存储

### 7.1 `src/models/gacha_record.py` — 数据模型

```python
class Rarity(IntEnum):          # 稀有度
    SPECIAL = 5                 # 特出（红/5★）
    EXCELLENT = 4               # 优异（黄/4★）
    FINE = 3                    # 精良（蓝/3★）

class BannerType(str):          # 卡池类型（继承 str！方便直接比较字符串）
    LIMITED = "限定"
    LIMITED_TIME = "限时"
    SUMMON = "招集"
    COLLECT = "征集"
    SEASON = "赛季"
    UNKNOWN = "unknown"         # 没识别出类型时的占位
```

```python
@dataclass
class GachaRecord:
    character_name: str         # 角色名
    rarity: Rarity              # 稀有度
    pull_time: datetime         # 抽卡时间
    banner_name: str            # 卡池名
    banner_type: str            # 卡池类型
    pull_number: int            # 抽卡序号（全库重编，**只作排序键**，不参与统计）
    record_id: str = ""         # 去重 ID（MD5）
    account_id: int = 0         # 所属账户
    text_hash: str = ""         # OCR 文本哈希（调试用）
    seq_no: int = 0             # 同分钟组内顺序号：距该组【最新那条】的偏移
                                # （最新 = 0，越旧越大）。见 make_record_id 的说明。
                                # 落库的原因：游戏的记录页时间只精确到"分"，
                                # 同一分钟能有几十条，光靠 pull_time 排不出先后，
                                # 必须靠这个显式顺序号才能还原真实抽取顺序。

    def __post_init__(self):
        self.pull_date = self.pull_time.strftime("%m-%d")   # 缓存日期字符串
        self.record_id = self._generate_id()                # 自动生成 ID

    def _generate_id(self) -> str:
        # 兜底：内容键 + 序号 0（扫描器会按真实序号覆盖）
        return make_record_id(self, 0)


# record_id = md5(内容键 + 出现序号 + 角色名)[:12]
# 内容键 = 时间(到分)|账户
# 出现序号 = 距该组【最新那条】的偏移（最新 = 0，越旧越大）
def make_record_key(record) -> str: ...
def make_record_id(record, seq=0) -> str: ...
# 判重用三元组，不比 record_id（老记录 ID 是别的算法算的）
def make_dedup_key(record, seq=0) -> tuple: ...   # (内容键, seq, 角色名)
```

### 7.2 `src/storage/database.py` — 数据库

#### 数据库文件位置（升级不丢数据）

```
Database.__init__ 里的路径处理顺序：
  1. db_path 为 None → 用 config.database_path（绝对路径）
     显式传入的相对路径也按 config.data_root 解析，不跟 CWD 走
  2. _migrate_legacy_db(target)：target 不存在时，
     在 resource_root / data_root 下递归找所有 gacha.db（跳过 .venv/build/dist 等），
     挑"记录条数最多"的那个 copy 过来，并在日志里列出没采用的那些
  3. _init_db()：create_all（只建缺失的表）
     → _ensure_columns()（PRAGMA table_info 比对，缺哪列 ALTER TABLE 补哪列）
     → 默认账户 + 老数据 account_id 为 NULL 的修补
```

历史坑：旧版本 `database.path` 写的是相对路径 `data/gacha.db`，SQLAlchemy 按启动时的
CWD 解析，于是在不同目录下启动会读写到不同的库，仓库里攒出了
`<根>/data/gacha.db`、`<根>/src/data/gacha.db`、`<根>/src/automation/pages/data/gacha.db`
三个文件。现在统一到绝对路径 + 自动迁移，界面上的总抽数不会再"归零"。

#### ORM 模型

```
AccountORM → 表 account
├─ id           INTEGER PK
├─ name         String(50), unique
├─ created_at   DateTime, default=now
└─ records      一对多 relationship → GachaRecordORM（级联删除）

GachaRecordORM → 表 gacha_record
├─ id              INTEGER PK
├─ record_id       String(32), unique, index   ← 去重 ID
├─ character_name  String(64)
├─ rarity          Integer                      ← Rarity 枚举值
├─ pull_time       DateTime
├─ banner_name     String(64)
├─ banner_type     String(32)
├─ pull_number     Integer                      ← 全库重编，只作排序键
├─ account_id      Integer, FK → account.id, index
├─ text_hash       String(16)                   ⚠️ 定义但从未使用
├─ seq_no          Integer, default=0           ← 同分钟组内顺序号（距最新偏移）
└─ created_at      DateTime, default=now
   索引：(record_id), (rarity), (banner_name, pull_time),
        (account_id, banner_name, pull_time), (account_id, pull_time, seq_no)
   ⚠️ 新增列靠 `_ensure_columns()` 自动补（老库升级不丢数据）；
      但**新索引不会自动建**（它只比对列，不动索引）→ 老库少一个 idx_order，
      只影响性能不影响正确性；要补需重建库或手动 CREATE INDEX
```

#### Database 类

```
Database
├─ __init__(db_path)              L96
│   └─ SQLAlchemy engine + sessionmaker + _init_db()
│
├─ _init_db()                     L106
│   ├─ Base.metadata.create_all()  ← 自动建表
│   ├─ 如果没有账户 → 创建默认账户 "默认"
│   └─ 修复旧记录的 account_id=NULL
│
├─ session (property)             L129  每次返回新 Session
│
├─ 账户 CRUD
│   ├─ create_account(name)       L135
│   ├─ list_accounts()            L150
│   ├─ get_account(account_id)    L155
│   ├─ rename_account(id, name)   L160
│   └─ delete_account(id)         L180
│
├─ 记录操作
│   ├─ add_record(record)         L196  单条添加（按 record_id 去重）
│   │   ├─ 检查 record_id 是否已存在 → 存在则 skip
│   │   └─ 不存在 → GachaRecordORM.from_record() → s.add() → commit
│   │
│   ├─ add_records(records)       L208  批量添加（逐条去重后 commit）
│   └─ get_all_records(account_id, banner, order_by)
│       └─ L222  支持按 pull_number 或 pull_time 排序
│
└─ get_db()                       L310  全局单例（懒加载）
```

### 7.3 `src/storage/exporter.py` — JSON 导入导出

```
export_to_json(output_path, account_id, banner_name)   L16
├─ L25  get_db().get_all_records() → 查询记录
├─ L31-36  包装元数据：export_time, app_version, account_id, total_count
├─ L34  每条记录 GachaRecord.to_dict_full() → 序列化
└─ 写入 JSON（utf-8, indent=2, ensure_ascii=False）

import_from_json(file_path, account_id)                L50
├─ 读取 JSON → 遍历 records 列表
├─ L61  GachaRecord.from_dict(item) → 反序列化
├─ 过滤 pull_time.microsecond != 0 的行（时间未识别，内容键会漂移）不入库
├─ 按内容键分组；组内按 JSON 出现顺序编号（= 距最新那条的偏移，与扫描器一致）
│    导出时按 pull_number 升序再 reverse，故 JSON 顺序即全局"新→旧"
├─ 建库内三元组 (内容键, seq, 角色名)，seq = 组内时间降序名次
│    ✅ 与扫描器同一套拆重规则；同一个文件重复导入 = 新增 0 条
│    ✅ 跳过微秒非 0 的老记录（同扫描器，不抬高阈值、不误判）
└─ 重新计算 record_id：make_record_id(record, seq) → get_db().add_record(record)
   导入后调用 _resequence(account_id) 按全库时间序重编 pull_number
```

---

## 8. 自更新模块 (Deploy)

### 8.1 文件结构

```
deploy/
├── __init__.py
├── config.py    部署配置（ConfigModel + DeployConfig）
├── utils.py     无外部依赖工具（简易 YAML + cached_property）
├── git.py       Git 更新管理
├── pip.py       Pip 依赖管理
├── installer.py 更新编排器
└── template     配置模板文件
```

### 8.2 `deploy/installer.py` — 更新编排器

```
Installer(GitManager, PipManager)  ← 多重继承
└─ install()  L19
    ├─ pip_install()  ← 先装依赖
    └─ git_install()  ← 再拉代码
```

### 8.3 `deploy/git.py` — Git 更新

```
GitManager
├─ git_install()  L19
│   ├─ L35  git init（如果 .git 不存在）
│   ├─ L41  git config http.proxy
│   ├─ L46  git config --local ...
│   ├─ L49  git remote set-url origin
│   ├─ L68  git fetch origin {branch} --depth=1
│   ├─ L74  如果 fetch 失败 → 打印提示，跳过更新
│   ├─ L87  清理 .git/*.lock 残留锁文件
│   ├─ L91  git reset --hard origin/{branch}  ⚠️ 破坏性操作
│   └─ L92  git pull --ff-only（reset 后冗余）
```

### 8.4 `deploy/pip.py` — Pip 依赖管理

```
PipManager
├─ installed_deps (property)   L63  扫描 site-packages/*.dist-info 目录
├─ required_deps (property)    L76  正则解析 requirements.txt
├─ deps_to_install (property)  L94  差集计算（required - installed）
└─ pip_install()               L97  执行 pip install + --trusted-host + -i mirror
```

### 8.5 `deploy/utils.py` — 无外部依赖工具

```
poor_yaml_read(text) → dict    L28   极简 YAML 解析（仅顶层 key: value）
  ⚠️ 不支持嵌套、不支持列表、不支持引号内冒号

poor_yaml_write(template, config)  L61  正则替换写回

cached_property(func)  L14  自定义缓存属性装饰器
```

---

## 9. 构建与打包

### 9.1 `build_portable.py` — 7 步构建脚本

```
步骤1: step_cleanup()          清空上次构建残留
步骤2: step_python()           下载 embedded Python 3.11.9 → toolkit/
步骤3: step_git()              下载 MinGit → toolkit/Git/
步骤4: step_adb()              下载 Android Platform Tools → toolkit/adb/
步骤5: step_compile()          PyInstaller --onefile --windowed launcher.py
步骤6: step_cleanup_junk()     清理 PyInstaller 中间产物
步骤7: step_package()          打包为 WuHuaGachaAnalysis-v1.0.0.zip
```

### 9.2 `requirements.txt`

```
PyQt6>=6.5.0,<7.0.0
paddlepaddle>=2.6.0,<3.0.0     # ~500MB 重型依赖
paddleocr>=2.8.0,<3.0.0
opencv-python>=4.8.0,<5.0.0
Pillow>=10.0.0,<12.0.0
numpy>=1.24.0
pyyaml>=6.0,<7.0.0
sqlalchemy>=2.0.0,<3.0.0
loguru>=0.7.0,<1.0.0
```

---

## 10. 开发工具

### 10.1 `tools/coordinate_viewer.py`

Tkinter GUI 工具，用于辅助获取游戏截图中的坐标信息。

**功能**：
- 图片加载与缩放（1%~3000%，滚轮缩放，倍率 1.15）
- 四种模式：
  - **框选 (select)**：拖拽框选区域 → 预览 → 命名保存截图 + 复制坐标到剪贴板
  - **标记 (marker)**：点击添加标记点
  - **取色 (picker)**：获取像素 RGB / HSV 值
  - **测量 (measure)**：两点距离测量
- 坐标导出：YAML / JSON / Python 三种格式
- 自动检测项目根目录（向上查找标记文件）

**⚠️ 已知 Bug**：测量模式 (measure) 中 `self.measure_info` Label 未创建，点击第二个点时会 `AttributeError`。

---

## 11. 已知问题与改进方向

### 🔴 高优先级

| # | 问题 | 位置 | 建议 |
|---|------|------|------|
| 1 | `_handle_unknown` / `_detect_popup` / `_close_popup` 空实现 | page_graph.py:419-452 | 实现弹窗检测和未知页面恢复逻辑 |
| 2 | OCR 子进程每次重新初始化 PaddleOCR（性能瓶颈） | engine.py:39 | 改为长生命周期 worker 进程池 |
| 3 | `adb_client.py` 可能缺少 `import os` | adb_client.py:342 | 在 `find_adb()` 顶部添加 `import os` |
| 4 | COLUMN_RANGES 硬编码 860px 宽度 | parser.py:140 | 从图像实际宽度动态计算比例 |
| 5 | 坐标硬编码仅适配 1280×720 | 多处 | 统一坐标适配层，覆盖所有 Button |

### 🟡 中优先级

| # | 问题 | 位置 | 建议 |
|---|------|------|------|
| 6 | 两套页面识别系统并存 (PageGraph vs PageDetector) | 全局 | 合并为单一系统 |
| 7 | 翻页按钮在 gacha_scanner.py 和 pages/gacha_record.py 重复定义 | 两处 | 统一引用 pages/ 中的定义 |
| 8 | `git_install()` 中 `reset --hard` 会丢失本地修改 | deploy/git.py:91 | 更新前检查 working tree，自动 stash |
| 9 | SettingsPage ↔ MainWindow monkey-patch 双向耦合 | main_window.py:591-593 | 改为信号/槽解耦 |
| 10 | QSS 样式分散（全局 STYLE + 内联 setStyleSheet） | main_window.py, home_page.py | 统一到 .qss 文件 |
| 11 | `_banner_up` 字典赋值后从未读取（死代码） | parser.py:93 | 移除或实现 UP 角色匹配功能 |
| 12 | `text_hash` 字段定义但从未写入 | database.py:51 + gacha_record.py | 移除或实现跨扫描 OCR 文本去重 |

### 🟢 低优先级

| # | 问题 | 位置 | 建议 |
|---|------|------|------|
| ~~13~~ | ~~`_load_up_map()` 每次调用重新读 YAML，无缓存~~ | home_page.py:20 | ✅ 已实现 `(路径, mtime)` 模块级缓存 |
| 14 | `_trim_old_logs` 计数器不重置 | main_window.py:419 | 清理后重置计数器 |
| 15 | `shutdown()` 空实现 | engine.py:63 | 实现子进程清理 |
| 16 | `_setup_ui` 方法过长 (119行) | main_window.py:506 | 拆分为多个子方法 |
| 17 | `_on_scan` 方法过长 (37行) | main_window.py:660 | 拆分为 `_start_scan` / `_stop_scan` |
| 18 | HomePage 中账户 ID 获取模式重复 3 次 | home_page.py:134,148,157 | 抽取为属性 |
| 19 | 坐标查看器测量模式 Bug | coordinate_viewer.py:603 | 创建 measure_info Label |
| 20 | `poor_yaml_write` 正则匹配前缀歧义 | deploy/utils.py:77 | 添加 `^` 行首锚点 |

---

## 12. 快速索引

### 12.1 按功能跳转

| 想看什么 | 直接跳到 |
|---------|---------|
| 程序如何启动 | `launcher.py:72` → `main()` |
| 窗口怎么构建的 | `main_window.py:506` → `_setup_ui()` |
| 点击"开始扫描"后发生什么 | `main_window.py:660` → `_on_scan()` |
| 扫描器主循环 | `gacha_scanner.py:153` → `scan_all()` |
| 单页 OCR 如何工作 | `gacha_scanner.py:319` → `_scan_page()` |
| OCR 如何解析角色名 | `parser.py:146` → `parse_record_from_ocr_results()` |
| 页面导航如何寻路 | `page_graph.py:215` → `goto()` |
| 按钮怎么被识别 | `button.py:282` → `appear()` |
| 数据怎么存进数据库 | `database.py:196` → `add_record()` |
| 首页时间线怎么生成 | `home_page.py:30` → `_build_timeline()` |
| JSON 怎么导入导出 | `exporter.py:16` → `export_to_json()` / `exporter.py:50` → `import_from_json()` |
| 更新器怎么工作 | `deploy/installer.py:19` → `install()` |
| 怎么打包成 exe | `build_portable.py` |
| ADB 截图怎么做的 | `adb_client.py:270` → `screenshot_validate()` |

### 12.2 关键数据结构

| 结构 | 定义位置 | 用途 |
|------|---------|------|
| `GachaRecord` | models/gacha_record.py:30 | 抽卡记录数据类 |
| `Rarity` | models/gacha_record.py:9 | 稀有度枚举（3/4/5） |
| `BannerType` | models/gacha_record.py:16 | 卡池类型枚举 |
| `GachaRecordORM` | database.py:37 | SQLAlchemy ORM 模型 |
| `AccountORM` | database.py:22 | 账户 ORM 模型 |
| `GamePage` | page_detector.py:31 | 游戏页面枚举 |
| `NavState` | ui_navigator.py:32 | 导航状态机枚举 |
| `Page` | page_graph.py:81 | 页面图节点 |
| `Button` | button.py:231 | 按钮识别对象 |
| `COLUMN_RANGES` | parser.py:140 | OCR 列位置定义 |

### 12.3 全局单例

| 单例 | 获取方式 | 定义位置 |
|------|---------|---------|
| Config | `from src.config import config` | config.py:180 |
| Database | `get_db()` | database.py:310 |
| OCREngine | `get_ocr_engine()` | engine.py:70 |
| ScannerSignals | `MainWindow._signals` | main_window.py:389 |

### 12.4 回调/Monkey-patch 注入点

| 回调 | 赋值位置 | 用途 |
|------|---------|------|
| `scanner.on_progress` | main_window.py:686 | 扫描进度 → 日志信号 |
| `scanner.on_record_found` | main_window.py:687 | 新记录发现 → 日志信号 |
| `settings_page.on_adb_connected` | main_window.py:591 | ADB 就绪 → MainWindow |
| `settings_page.main_window` | main_window.py:593 | 反向引用主窗口 |

---

> 文档基于项目 v1.0.0 代码生成。修改代码后请同步更新本文档中对应的行号引用。
