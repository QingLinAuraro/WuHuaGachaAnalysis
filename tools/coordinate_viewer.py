#!/usr/bin/env python3
"""
截图模板快速制作工具 - WuHuaGachaAnalysis 专用
===============================================
用于在游戏截图上快速框选 UI 元素，一键导出截图和坐标。

功能:
  🖱️  拖拽框选 - 按住左键拖拽出矩形选区，松开即完成
  📸 一键导出 - 自动裁剪并保存 PNG 到 templates 目录
  📋 自动生成坐标 - 同时输出 Python/YAML 格式的坐标定义
  🏷️  命名提示 - 框选后弹出命名框，快速命名模板文件
  🔍 滚轮缩放 + 右键拖拽平移
  🎯 取色模式 - 点击获取像素精确颜色值
  📏 测量模式 - 两点测距

用法:
  python tools/coordinate_viewer.py                          # 打开文件选择对话框
  python tools/coordinate_viewer.py screenshot.png           # 直接打开指定截图
  python tools/coordinate_viewer.py --dir screenshots/       # 浏览截图目录
"""

import tkinter as tk
from tkinter import filedialog, ttk, messagebox, simpledialog
from PIL import Image, ImageTk
import sys
import os
import json

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False


def find_project_root():
    """从当前工作目录和脚本目录向上查找项目根

    寻找标记: assets/templates, src/automation, config/default_config.yaml
    """
    cwd = os.getcwd()
    candidates = [cwd]
    try:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        candidates.append(os.path.dirname(script_dir))
    except NameError:
        pass

    markers = ["assets/templates", "src/automation", "config/default_config.yaml"]

    for start in candidates:
        d = os.path.abspath(start)
        for _ in range(4):
            for m in markers:
                if os.path.exists(os.path.join(d, m)):
                    return d
            parent = os.path.dirname(d)
            if parent == d:
                break
            d = parent

    return cwd


PROJECT_ROOT = find_project_root()
TEMPLATES_BASE = os.path.join(PROJECT_ROOT, "assets", "templates")


def get_page_options():
    """扫描 assets/templates/ 下所有子目录，支持嵌套

    返回如: ['main', 'gacha', 'gacha/details', 'gacha/details/record', 'shared']
    """
    if not os.path.isdir(TEMPLATES_BASE):
        return ["shared"]

    result = set()
    for root, dirs, files in os.walk(TEMPLATES_BASE):
        # 跳过隐藏目录
        dirs[:] = [d for d in dirs if not d.startswith(".") and d != "__pycache__"]

        rel = os.path.relpath(root, TEMPLATES_BASE).replace("\\", "/")
        if rel != ".":
            result.add(rel)

    # 确保 shared 始终在列表中
    shared_dir = os.path.join(TEMPLATES_BASE, "shared")
    if "shared" not in result:
        if not os.path.isdir(shared_dir):
            os.makedirs(shared_dir, exist_ok=True)
        result.add("shared")

    return sorted(result)


class TemplateCaptureTool:
    def __init__(self, root, image_path=None):
        self.root = root
        self.root.title("模板制作器 - WuHuaGachaAnalysis")
        self.root.geometry("1500x900")
        self.root.configure(bg="#1e1e1e")

        # 图片相关
        self.pil_image = None
        self.tk_image = None
        self.zoom = 1.0
        self.pan_x = 0
        self.pan_y = 0
        self.drag_start = None          # 右键平移起点
        self.image_path = None

        # 框选相关
        self.select_start = None        # (img_x, img_y)
        self.select_end = None          # (img_x, img_y)
        self.selecting = False
        self.box_rect_id = None         # Canvas 上矩形框的 ID

        # 标记点列表 (兼容旧功能)
        self.markers: list[dict] = []

        # 取色模式
        self.locked_pixel = None
        self.measure_mode = False
        self.measure_start = None

        # 默认模板目录
        self.output_dir = tk.StringVar(value=TEMPLATES_BASE)

        self._build_ui()
        self._bind_events()

        if image_path and os.path.isfile(image_path):
            self.load_image(image_path)
        elif "--dir" in sys.argv:
            idx = sys.argv.index("--dir")
            d = sys.argv[idx + 1] if idx + 1 < len(sys.argv) else "screenshots"
            self._browse_dir(d)
        else:
            self._show_welcome()

    # ══════════════════════════════════════════════════════
    #  界面
    # ══════════════════════════════════════════════════════

    def _show_welcome(self):
        self.canvas.create_text(600, 350, text="📷 拖入截图 或 Ctrl+O 打开",
                                fill="#666", font=("Microsoft YaHei", 18), anchor="center")
        self.canvas.create_text(600, 400, text="左键拖拽框选 | 右键拖拽平移 | 滚轮缩放",
                                fill="#555", font=("Microsoft YaHei", 12), anchor="center")
        self.canvas.create_text(600, 430, text="框选后自动弹出命名保存",
                                fill="#555", font=("Microsoft YaHei", 12), anchor="center")

    def _build_ui(self):
        self._build_toolbar()
        self._build_main()
        self._build_sidebar()
        self._build_statusbar()

    def _build_toolbar(self):
        tb = tk.Frame(self.root, bg="#2d2d2d", height=40)
        tb.pack(side=tk.TOP, fill=tk.X)
        tb.pack_propagate(False)

        b = {"bg": "#3d3d3d", "fg": "#ddd", "relief": tk.FLAT, "padx": 10, "pady": 4,
             "font": ("Microsoft YaHei", 9), "activebackground": "#555", "activeforeground": "#fff"}

        tk.Button(tb, text="📂 打开 (Ctrl+O)", command=self.open_file, **b).pack(side=tk.LEFT, padx=(8,2))
        tk.Button(tb, text="📁 浏览目录", command=lambda: self._browse_dir(), **b).pack(side=tk.LEFT, padx=2)
        tk.Button(tb, text="🔄 重置视图 (R)", command=self.reset_view, **b).pack(side=tk.LEFT, padx=2)

        self.zoom_label = tk.Label(tb, text="100%", bg="#2d2d2d", fg="#aaa",
                                    font=("Consolas", 10), width=7)
        self.zoom_label.pack(side=tk.LEFT, padx=(12,0))

        tk.Frame(tb, bg="#555", width=1, height=22).pack(side=tk.LEFT, padx=10, pady=9)

        # 模式切换
        self.mode_var = tk.StringVar(value="select")
        for text, val in [("📦 框选导出", "select"), ("📌 标记模式", "marker"),
                          ("🎯 取色模式", "picker"), ("📏 测量模式", "measure")]:
            tk.Radiobutton(tb, text=text, variable=self.mode_var, value=val,
                           bg="#2d2d2d", fg="#ccc", selectcolor="#3d3d3d",
                           activebackground="#2d2d2d", activeforeground="#fff",
                           font=("Microsoft YaHei", 9)).pack(side=tk.LEFT, padx=2)

        tk.Frame(tb, bg="#555", width=1, height=22).pack(side=tk.LEFT, padx=10, pady=9)

        tk.Button(tb, text="🗑 删除最后", command=self.delete_last_marker, **b).pack(side=tk.RIGHT, padx=2)
        tk.Button(tb, text="✖ 清除全部", command=self.clear_markers, **b).pack(side=tk.RIGHT, padx=2)
        tk.Button(tb, text="📋 复制全部坐标", command=self.copy_all_python, **b).pack(side=tk.RIGHT, padx=2)

    def _build_main(self):
        main = tk.Frame(self.root, bg="#1e1e1e")
        main.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        self.canvas_frame = tk.Frame(main, bg="#1e1e1e")
        self.canvas_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.canvas = tk.Canvas(self.canvas_frame, bg="#252525",
                                highlightthickness=0, cursor="crosshair")
        self.canvas.pack(fill=tk.BOTH, expand=True)

    def _build_sidebar(self):
        sb = tk.Frame(self.root, bg="#2d2d2d", width=340)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        sb.pack_propagate(False)

        # -- 框选信息 --
        self.box_frame = tk.Frame(sb, bg="#2d2d2d")
        self.box_frame.pack(fill=tk.X, padx=8, pady=(8,4))

        tk.Label(self.box_frame, text="📦 框选信息", bg="#2d2d2d", fg="#4caf50",
                 font=("Microsoft YaHei", 11, "bold")).pack(anchor="w")

        self.box_info = tk.Label(self.box_frame, bg="#2d2d2d", fg="#888",
                                  text="拖拽左键进行框选", font=("Consolas", 9), justify="left")
        self.box_info.pack(anchor="w", pady=4)

        # 快捷参数
        param_frame = tk.Frame(sb, bg="#2d2d2d")
        param_frame.pack(fill=tk.X, padx=8, pady=(0,4))

        tk.Label(param_frame, text="目标页面:", bg="#2d2d2d", fg="#aaa",
                 font=("Microsoft YaHei", 9)).pack(anchor="w")

        page_row = tk.Frame(param_frame, bg="#2d2d2d")
        page_row.pack(fill=tk.X, pady=2)
        opts = get_page_options()
        self.page_var = tk.StringVar(value=opts[0] if opts else "shared")
        self.page_combo = ttk.Combobox(page_row, textvariable=self.page_var,
                                        values=get_page_options(), state="normal",
                                        font=("Microsoft YaHei", 9), width=14)
        self.page_combo.pack(side=tk.LEFT)

        tk.Label(param_frame, text="按钮名称:", bg="#2d2d2d", fg="#aaa",
                 font=("Microsoft YaHei", 9)).pack(anchor="w", pady=(6,0))

        name_row = tk.Frame(param_frame, bg="#2d2d2d")
        name_row.pack(fill=tk.X, pady=2)
        self.name_var = tk.StringVar(value="check_btn")
        self.name_entry = tk.Entry(name_row, textvariable=self.name_var,
                                    bg="#333", fg="#fff", insertbackground="#fff",
                                    font=("Consolas", 10), relief=tk.FLAT, width=16)
        self.name_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)

        tk.Label(param_frame, text="输出目录:", bg="#2d2d2d", fg="#aaa",
                 font=("Microsoft YaHei", 9)).pack(anchor="w", pady=(6,0))

        tk.Label(param_frame, text=f"项目根: {PROJECT_ROOT}", bg="#2d2d2d", fg="#666",
                 font=("Consolas", 7)).pack(anchor="w")

        dir_row = tk.Frame(param_frame, bg="#2d2d2d")
        dir_row.pack(fill=tk.X, pady=2)
        self.dir_entry = tk.Entry(dir_row, textvariable=self.output_dir,
                                   bg="#333", fg="#fff", insertbackground="#fff",
                                   font=("Consolas", 9), relief=tk.FLAT)
        self.dir_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        tk.Button(dir_row, text="...", command=self._choose_output_dir,
                  bg="#3d3d3d", fg="#ddd", relief=tk.FLAT, font=("Consolas", 8)).pack(side=tk.LEFT)

        # 导出按钮
        tk.Button(param_frame, text="💾 保存框选截图 + 复制坐标",
                  command=self._show_save_dialog,
                  bg="#4caf50", fg="#fff", relief=tk.FLAT,
                  padx=10, pady=6, font=("Microsoft YaHei", 10, "bold"),
                  activebackground="#66bb6a",
                  ).pack(fill=tk.X, pady=(8, 2))

        # -- 标记列表 --
        tk.Frame(sb, bg="#555", height=1).pack(fill=tk.X, padx=8, pady=4)

        header = tk.Frame(sb, bg="#2d2d2d")
        header.pack(fill=tk.X, padx=8)

        tk.Label(header, text="📍 已保存的按钮", bg="#2d2d2d", fg="#eee",
                 font=("Microsoft YaHei", 10, "bold")).pack(side=tk.LEFT)
        self.marker_count = tk.Label(header, text="(0)", bg="#2d2d2d", fg="#888",
                                      font=("Microsoft YaHei", 9))
        self.marker_count.pack(side=tk.LEFT, padx=4)

        list_frame = tk.Frame(sb, bg="#333")
        list_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)

        self.marker_listbox = tk.Listbox(list_frame, bg="#252525", fg="#ddd",
                                          selectbackground="#007acc", selectforeground="#fff",
                                          font=("Consolas", 9), relief=tk.FLAT,
                                          highlightthickness=0)
        self.marker_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb2 = tk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.marker_listbox.yview)
        sb2.pack(side=tk.RIGHT, fill=tk.Y)
        self.marker_listbox.config(yscrollcommand=sb2.set)
        self.marker_listbox.bind("<Double-Button-1>", self._on_list_double)

        # 历史导出
        tk.Frame(sb, bg="#555", height=1).pack(fill=tk.X, padx=8, pady=4)

        tk.Label(sb, text="💾 导出全部", bg="#2d2d2d", fg="#eee",
                 font=("Microsoft YaHei", 10, "bold")).pack(anchor="w", padx=8)

        btn_f = tk.Frame(sb, bg="#2d2d2d")
        btn_f.pack(fill=tk.X, padx=8, pady=4)

        bs = {"bg": "#3d3d3d", "fg": "#ddd", "relief": tk.FLAT, "padx": 6, "pady": 4,
              "font": ("Microsoft YaHei", 9), "activebackground": "#555", "activeforeground": "#fff"}

        if HAS_YAML:
            tk.Button(btn_f, text="💾 导出 YAML", command=self.export_yaml, **bs).pack(
                side=tk.LEFT, fill=tk.X, expand=True, padx=1)
        tk.Button(btn_f, text="💾 导出 JSON", command=self.export_json, **bs).pack(
            side=tk.LEFT, fill=tk.X, expand=True, padx=1)

        # 取色面板
        self.picker_frame = tk.Frame(sb, bg="#2d2d2d")
        self.picker_frame.pack(fill=tk.X, padx=8, pady=4)

        tk.Label(self.picker_frame, text="🎯 锁定像素", bg="#2d2d2d", fg="#ff9800",
                 font=("Microsoft YaHei", 9, "bold")).pack(anchor="w")
        self.picker_info = tk.Label(self.picker_frame, text="未锁定", bg="#2d2d2d", fg="#888",
                                     font=("Consolas", 9), justify="left")
        self.picker_info.pack(anchor="w")
        self.picker_swatch = tk.Canvas(self.picker_frame, width=60, height=30,
                                        bg="#2d2d2d", highlightthickness=1, highlightbackground="#555")
        self.picker_swatch.pack(anchor="w", pady=2)

    def _build_statusbar(self):
        sb = tk.Frame(self.root, bg="#007acc", height=32)
        sb.pack(side=tk.BOTTOM, fill=tk.X)
        sb.pack_propagate(False)

        self.lbl_coord = tk.Label(sb, text="X: ---  Y: ---", bg="#007acc", fg="#fff",
                                  font=("Consolas", 12, "bold"), anchor="w")
        self.lbl_coord.pack(side=tk.LEFT, padx=16)

        self.lbl_rgb = tk.Label(sb, text="R:--- G:--- B:---  |  #------", bg="#007acc", fg="#e0e0e0",
                                font=("Consolas", 10))
        self.lbl_rgb.pack(side=tk.LEFT, padx=20)

        self.lbl_ext = tk.Label(sb, text="", bg="#007acc", fg="#b0d0f0",
                                font=("Microsoft YaHei", 9))
        self.lbl_ext.pack(side=tk.RIGHT, padx=16)

    # ══════════════════════════════════════════════════════
    #  事件
    # ══════════════════════════════════════════════════════

    def _bind_events(self):
        self.canvas.bind("<Motion>", self._on_move)
        self.canvas.bind("<Button-1>", self._on_btn1_down)
        self.canvas.bind("<B1-Motion>", self._on_btn1_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_btn1_up)
        self.canvas.bind("<Button-3>", self._on_btn3_down)
        self.canvas.bind("<B3-Motion>", self._on_btn3_drag)
        self.canvas.bind("<ButtonRelease-3>", self._on_btn3_up)
        self.canvas.bind("<MouseWheel>", self._on_wheel)
        self.canvas.bind("<Button-4>", lambda e: self._on_wheel_linux(e, 1))
        self.canvas.bind("<Button-5>", lambda e: self._on_wheel_linux(e, -1))
        self.canvas.bind("<Configure>", lambda e: self._refresh())

        self.root.bind("<Control-o>", lambda e: self.open_file())
        self.root.bind("<Control-O>", lambda e: self.open_file())
        self.root.bind("<Escape>", lambda e: self._cancel_select())
        self.root.bind("<Delete>", lambda e: self.delete_last_marker())
        self.root.bind("<Control-z>", lambda e: self.delete_last_marker())
        self.root.bind("<r>", lambda e: self.reset_view())
        self.root.bind("<R>", lambda e: self.reset_view())

    # ══════════════════════════════════════════════════════
    #  图片加载
    # ══════════════════════════════════════════════════════

    def open_file(self):
        path = filedialog.askopenfilename(
            title="选择截图",
            initialdir="screenshots" if os.path.isdir("screenshots") else ".",
            filetypes=[("图片", "*.png *.jpg *.jpeg *.bmp *.webp"), ("全部", "*.*")]
        )
        if path:
            self.load_image(path)

    def _browse_dir(self, directory="screenshots"):
        if not os.path.isdir(directory):
            directory = filedialog.askdirectory(title="选择截图目录")
            if not directory: return

        images = sorted(f for f in os.listdir(directory)
                       if f.lower().endswith(('.png','.jpg','.jpeg','.bmp','.webp')))
        if not images:
            messagebox.showinfo("提示", f"目录 '{directory}' 中没有图片")
            return

        dialog = tk.Toplevel(self.root)
        dialog.title(f"选择截图 - {directory}")
        dialog.geometry("500x450")
        dialog.configure(bg="#2d2d2d")
        dialog.transient(self.root)
        dialog.grab_set()

        tk.Label(dialog, text=f"📁 {directory}", bg="#2d2d2d", fg="#eee",
                 font=("Microsoft YaHei", 11, "bold")).pack(pady=8)

        lb = tk.Listbox(dialog, bg="#252525", fg="#ddd", font=("Consolas", 10),
                        selectbackground="#007acc", relief=tk.FLAT)
        lb.pack(fill=tk.BOTH, expand=True, padx=12, pady=4)
        for img in images:
            lb.insert(tk.END, img)

        def on_select():
            sel = lb.curselection()
            if sel:
                dialog.destroy()
                self.load_image(os.path.join(directory, images[sel[0]]))

        lb.bind("<Double-Button-1>", lambda e: on_select())
        bf = tk.Frame(dialog, bg="#2d2d2d")
        bf.pack(fill=tk.X, padx=12, pady=8)
        tk.Button(bf, text="打开", command=on_select, bg="#007acc", fg="#fff",
                  relief=tk.FLAT, padx=16, pady=4, font=("Microsoft YaHei", 10)).pack(side=tk.RIGHT, padx=4)
        tk.Button(bf, text="取消", command=dialog.destroy, bg="#3d3d3d", fg="#ddd",
                  relief=tk.FLAT, padx=16, pady=4, font=("Microsoft YaHei", 10)).pack(side=tk.RIGHT, padx=4)
        self.root.wait_window(dialog)

    def load_image(self, path):
        try:
            self.pil_image = Image.open(path)
            self.image_path = path
            self.root.title(f"模板制作器 - {os.path.basename(path)}  ({self.pil_image.width}x{self.pil_image.height})")
            self.markers.clear()
            self.marker_listbox.delete(0, tk.END)
            self.marker_count.config(text="(0)")
            self.locked_pixel = None
            self.measure_start = None
            self._cancel_select()
            self.reset_view()
        except Exception as e:
            messagebox.showerror("错误", f"无法打开图片:\n{e}")

    # ══════════════════════════════════════════════════════
    #  视图
    # ══════════════════════════════════════════════════════

    def reset_view(self):
        if self.pil_image is None: return
        cw = max(self.canvas.winfo_width(), 200)
        ch = max(self.canvas.winfo_height(), 200)
        iw, ih = self.pil_image.size
        self.zoom = min(cw / iw, ch / ih, 1.0) * 0.88
        self.pan_x = (cw - iw * self.zoom) // 2
        self.pan_y = (ch - ih * self.zoom) // 2
        self.lbl_ext.config(text=f"图片: {iw}×{ih}px")
        self._refresh()

    def _refresh(self):
        if self.pil_image is None: return
        iw, ih = self.pil_image.size
        nw, nh = max(int(iw * self.zoom), 1), max(int(ih * self.zoom), 1)

        resample = Image.LANCZOS if nw * nh < 4000000 else Image.NEAREST
        disp = self.pil_image.resize((nw, nh), resample)
        self.tk_image = ImageTk.PhotoImage(disp)

        self.canvas.delete("all")
        self.canvas.create_image(self.pan_x, self.pan_y, anchor="nw",
                                 image=self.tk_image, tags="img")

        # 框选半透明蒙层
        if self.select_start and self.select_end:
            self._draw_selection_box()

        # 标记点
        self._draw_markers()

        # 取色十字
        if self.locked_pixel:
            self._draw_crosshair(*self.locked_pixel[:2], "#ffeb3b")

        # 测量点
        if self.measure_start:
            sx, sy = self.measure_start
            csx = self.pan_x + sx * self.zoom + self.zoom/2
            csy = self.pan_y + sy * self.zoom + self.zoom/2
            self.canvas.create_oval(csx-4, csy-4, csx+4, csy+4,
                                    outline="#ff5722", width=2, tags="measure")

        pct = int(self.zoom * 100)
        self.zoom_label.config(text=f"{pct}%")

    def _draw_selection_box(self):
        """绘制蓝色半透明框选矩形"""
        x1 = self.pan_x + min(self.select_start[0], self.select_end[0]) * self.zoom
        y1 = self.pan_y + min(self.select_start[1], self.select_end[1]) * self.zoom
        x2 = self.pan_x + max(self.select_start[0], self.select_end[0]) * self.zoom
        y2 = self.pan_y + max(self.select_start[1], self.select_end[1]) * self.zoom

        # 半透明填充
        self.canvas.create_rectangle(x1, y1, x2, y2,
                                     fill="#4caf50", stipple="gray50",
                                     outline="", tags="select_box")
        # 边框
        self.canvas.create_rectangle(x1, y1, x2, y2,
                                     outline="#4caf50", width=2, tags="select_box")
        # 尺寸标签
        w = int(abs(self.select_end[0] - self.select_start[0]))
        h = int(abs(self.select_end[1] - self.select_start[1]))
        self.canvas.create_text((x1+x2)/2, y1 - 12, text=f"{w}×{h}px",
                                fill="#4caf50", font=("Consolas", 10, "bold"),
                                tags="select_box")

    def _draw_markers(self):
        colors = ["#ff6b6b","#4ecdc4","#ffe66d","#a29bfe","#fd79a8",
                  "#00cec9","#e17055","#6c5ce7","#fdcb6e","#00b894"]
        for i, m in enumerate(self.markers):
            mx = self.pan_x + m["x"] * self.zoom + self.zoom/2
            my = self.pan_y + m["y"] * self.zoom + self.zoom/2
            c = colors[i % len(colors)]
            r = max(5, self.zoom * 3)
            self.canvas.create_line(mx-r*2, my, mx+r*2, my, fill=c, width=1, tags="marker")
            self.canvas.create_line(mx, my-r*2, mx, my+r*2, fill=c, width=1, tags="marker")
            self.canvas.create_oval(mx-r, my-r, mx+r, my+r, outline=c, width=2, tags="marker")
            label = m.get("name", str(i+1))
            self.canvas.create_text(mx+r+6, my-r-6, text=label,
                                    fill=c, font=("Consolas", 9, "bold"), anchor="nw", tags="marker")

    def _draw_crosshair(self, px, py, color):
        cx = self.pan_x + px * self.zoom + self.zoom/2
        cy = self.pan_y + py * self.zoom + self.zoom/2
        cw = self.canvas.winfo_width()
        ch = self.canvas.winfo_height()
        self.canvas.create_line(0, cy, cw, ch, fill=color, width=1, dash=(6,4), tags="crosshair")
        self.canvas.create_line(cx, 0, cx, ch, fill=color, width=1, dash=(6,4), tags="crosshair")
        r = max(5, self.zoom * 3)
        self.canvas.create_rectangle(cx-r, cy-r, cx+r, cy+r, outline=color, width=2, tags="crosshair")

    # ══════════════════════════════════════════════════════
    #  坐标转换
    # ══════════════════════════════════════════════════════

    def _img_coords(self, event):
        return (event.x - self.pan_x) / self.zoom, (event.y - self.pan_y) / self.zoom

    def _in_image(self, ix, iy):
        if self.pil_image is None: return False
        w, h = self.pil_image.size
        return 0 <= ix < w and 0 <= iy < h

    def _get_pixel(self, ix, iy):
        try:
            px = self.pil_image.getpixel((int(ix), int(iy)))
            if isinstance(px, int): return px, px, px
            if len(px) >= 3: return px[0], px[1], px[2]
            return px[0], px[0], px[0]
        except: return 0, 0, 0

    # ══════════════════════════════════════════════════════
    #  鼠标事件
    # ══════════════════════════════════════════════════════

    def _on_move(self, event):
        if self.pil_image is None: return
        ix, iy = self._img_coords(event)
        if self._in_image(ix, iy):
            px, py = int(ix), int(iy)
            r, g, b = self._get_pixel(ix, iy)
            hex_c = f"#{r:02X}{g:02X}{b:02X}"
            self.lbl_coord.config(text=f"X: {px:<5}  Y: {py:<5}")
            self.lbl_rgb.config(text=f"R:{r:<4} G:{g:<4} B:{b:<4} | {hex_c}")
        else:
            self.lbl_coord.config(text="X: ---  Y: ---")
            self.lbl_rgb.config(text="R:--- G:--- B:---  |  #------")

    def _on_btn1_down(self, event):
        if self.pil_image is None: return
        ix, iy = self._img_coords(event)
        if not self._in_image(ix, iy): return

        mode = self.mode_var.get()
        px, py = int(ix), int(iy)
        r, g, b = self._get_pixel(ix, iy)

        if mode == "select":
            # 开始框选
            self.select_start = (ix, iy)
            self.select_end = (ix, iy)
            self.selecting = True

        elif mode == "marker":
            name = f"point_{len(self.markers)+1}"
            self.markers.append({"name": name, "x": px, "y": py, "r": r, "g": g, "b": b})
            self._refresh_list()
            self._refresh()

        elif mode == "picker":
            self.locked_pixel = (px, py, r, g, b)
            hex_c = f"#{r:02X}{g:02X}{b:02X}"
            self.picker_info.config(
                text=f"X={px}, Y={py}\nR={r} G={g} B={b}\n{hex_c}", fg="#fff")
            self.picker_swatch.config(bg=hex_c)
            self._copy(f"({px}, {py})")
            self._refresh()

        elif mode == "measure":
            if self.measure_start is None:
                self.measure_start = (px, py)
                self.measure_info.config(text=f"起点: ({px}, {py})\n点击终点测距", fg="#ff9800")
                self._refresh()
            else:
                sx, sy = self.measure_start
                dx, dy = px - sx, py - sy
                dist = (dx**2 + dy**2) ** 0.5
                self.measure_info.config(
                    text=f"起点: ({sx},{sy})  终点: ({px},{py})\nΔX={dx} ΔY={dy}  距离: {dist:.1f}px",
                    fg="#4fc3f7")
                self._refresh()
                csx = self.pan_x + sx*self.zoom + self.zoom/2
                csy = self.pan_y + sy*self.zoom + self.zoom/2
                cex = self.pan_x + px*self.zoom + self.zoom/2
                cey = self.pan_y + py*self.zoom + self.zoom/2
                self.canvas.create_line(csx, csy, cex, cey, fill="#4fc3f7", width=2, dash=(4,2))
                self.measure_start = None

    def _on_btn1_drag(self, event):
        if self.pil_image is None: return
        ix, iy = self._img_coords(event)
        if not self.selecting: return
        ix = max(0, min(ix, self.pil_image.width - 1))
        iy = max(0, min(iy, self.pil_image.height - 1))
        self.select_end = (ix, iy)
        self._update_box_info()
        self._refresh()

    def _on_btn1_up(self, event):
        if not self.selecting: return
        self.selecting = False

        if self.select_start and self.select_end:
            # 最终框选坐标
            x1 = int(min(self.select_start[0], self.select_end[0]))
            y1 = int(min(self.select_start[1], self.select_end[1]))
            x2 = int(max(self.select_start[0], self.select_end[0]))
            y2 = int(max(self.select_start[1], self.select_end[1]))
            w, h = x2 - x1, y2 - y1

            # 小于 5px 的框选忽略（可能是误点）
            if w < 5 or h < 5:
                self._cancel_select()
                return

            self.select_start = (x1, y1)
            self.select_end = (x2, y2)
            self._update_box_info()

            # 弹出确认对话框
            self._show_save_dialog()

    def _on_btn3_down(self, event):
        self.drag_start = (event.x, event.y)

    def _on_btn3_drag(self, event):
        if self.drag_start:
            dx = event.x - self.drag_start[0]
            dy = event.y - self.drag_start[1]
            self.pan_x += dx
            self.pan_y += dy
            self.drag_start = (event.x, event.y)
            self._refresh()

    def _on_btn3_up(self, event):
        self.drag_start = None

    def _on_wheel(self, event):
        if self.pil_image is None: return
        old = self.zoom
        factor = 1.15 if event.delta > 0 else 1/1.15
        self.zoom = max(0.02, min(self.zoom * factor, 30.0))
        if old != self.zoom:
            r = self.zoom / old
            self.pan_x = event.x - r * (event.x - self.pan_x)
            self.pan_y = event.y - r * (event.y - self.pan_y)
            self._refresh()

    def _on_wheel_linux(self, event, direction):
        if self.pil_image is None: return
        old = self.zoom
        factor = 1.15 if direction > 0 else 1/1.15
        self.zoom = max(0.02, min(self.zoom * factor, 30.0))
        if old != self.zoom:
            r = self.zoom / old
            self.pan_x = event.x - r * (event.x - self.pan_x)
            self.pan_y = event.y - r * (event.y - self.pan_y)
            self._refresh()

    # ══════════════════════════════════════════════════════
    #  框选逻辑
    # ══════════════════════════════════════════════════════

    def _update_box_info(self):
        if not self.select_start or not self.select_end: return
        x1 = int(min(self.select_start[0], self.select_end[0]))
        y1 = int(min(self.select_start[1], self.select_end[1]))
        x2 = int(max(self.select_start[0], self.select_end[0]))
        y2 = int(max(self.select_start[1], self.select_end[1]))
        self.box_info.config(
            text=f"区域: ({x1},{y1}) → ({x2},{y2})\n尺寸: {x2-x1}×{y2-y1}px\n目标: {self.page_var.get()}/{self.name_var.get()}.png",
            fg="#4caf50")

    def _get_selection_rect(self):
        """返回标准化的矩形 (x1, y1, x2, y2)"""
        if not self.select_start or not self.select_end:
            return None
        x1 = int(min(self.select_start[0], self.select_end[0]))
        y1 = int(min(self.select_start[1], self.select_end[1]))
        x2 = int(max(self.select_start[0], self.select_end[0]))
        y2 = int(max(self.select_start[1], self.select_end[1]))
        if x2 - x1 < 1 or y2 - y1 < 1:
            return None
        return x1, y1, x2, y2

    def _show_save_dialog(self):
        """框选完成后弹出确认对话框，显示预览，可调整保存路径和名称"""
        rect = self._get_selection_rect()
        if rect is None: return
        x1, y1, x2, y2 = rect
        w, h = x2 - x1, y2 - y1

        dialog = tk.Toplevel(self.root)
        dialog.title("保存模板截图")
        dialog.configure(bg="#2d2d2d")
        dialog.transient(self.root)
        dialog.grab_set()

        # 防止对话框过大
        dialog.minsize(420, 320)
        dialog.resizable(True, True)

        # -- 预览 --
        preview_frame = tk.Frame(dialog, bg="#1e1e1e", width=200, height=200)
        preview_frame.pack(padx=12, pady=(12, 4))
        preview_frame.pack_propagate(False)

        crop_img = self.pil_image.crop((x1, y1, x2, y2))
        # 缩放到适合预览
        max_preview = 180
        scale = min(max_preview / w, max_preview / h, 1.0)
        pw, ph = int(w * scale), int(h * scale)
        preview = crop_img.resize((pw, ph), Image.LANCZOS)
        self._preview_tk = ImageTk.PhotoImage(preview)
        tk.Label(preview_frame, image=self._preview_tk, bg="#1e1e1e").pack(expand=True)

        # -- 信息行 --
        info_text = f"选框: ({x1},{y1}) → ({x2},{y2})  尺寸: {w}×{h}px"
        tk.Label(dialog, text=info_text, bg="#2d2d2d", fg="#aaa",
                 font=("Consolas", 9)).pack(padx=12, anchor="w")

        # -- 表单 --
        form = tk.Frame(dialog, bg="#2d2d2d")
        form.pack(fill=tk.X, padx=12, pady=8)

        # 页面选择
        tk.Label(form, text="目标页面:", bg="#2d2d2d", fg="#ccc",
                 font=("Microsoft YaHei", 9)).grid(row=0, column=0, sticky="w", pady=(0, 2))
        page_var = tk.StringVar(value=self.page_var.get())
        page_combo = ttk.Combobox(form, textvariable=page_var, values=get_page_options(),
                                   state="normal", font=("Microsoft YaHei", 10), width=18)
        page_combo.grid(row=1, column=0, sticky="ew", pady=(0, 6))

        # 文件名
        tk.Label(form, text="文件名 (不含 .png):", bg="#2d2d2d", fg="#ccc",
                 font=("Microsoft YaHei", 9)).grid(row=2, column=0, sticky="w", pady=(0, 2))
        name_entry = tk.Entry(form, bg="#333", fg="#fff", insertbackground="#fff",
                              font=("Consolas", 11), relief=tk.FLAT)
        name_entry.insert(0, self.name_var.get())
        name_entry.grid(row=3, column=0, sticky="ew", pady=(0, 8))
        name_entry.select_range(0, tk.END)
        name_entry.focus()

        # 目标路径预览
        path_label = tk.Label(form, text="", bg="#2d2d2d", fg="#888",
                              font=("Consolas", 8), anchor="w")

        def update_path(*_):
            pg = page_var.get()
            nm = name_entry.get().strip()
            if nm:
                full = os.path.join(self.output_dir.get(), pg, f"{nm}.png")
                exists = " ⚠️ 已存在，将覆盖!" if os.path.exists(full) else " ✨ 新文件"
                path_label.config(
                    text=f"→ assets/templates/{pg}/{nm}.png{exists}",
                    fg="#ff9800" if os.path.exists(full) else "#4caf50")
            else:
                path_label.config(text="→ 请输入文件名", fg="#888")

        page_var.trace_add("write", update_path)
        name_entry.bind("<KeyRelease>", update_path)
        path_label.grid(row=4, column=0, sticky="w")
        update_path()

        form.columnconfigure(0, weight=1)

        # -- 按钮 --
        btn_row = tk.Frame(dialog, bg="#2d2d2d")
        btn_row.pack(fill=tk.X, padx=12, pady=(4, 12))

        result = {"saved": False}

        def do_save():
            pg = page_var.get()
            nm = name_entry.get().strip()
            if not nm:
                messagebox.showwarning("提示", "请输入文件名", parent=dialog)
                return

            out_dir = os.path.join(self.output_dir.get(), pg)
            save_path = os.path.join(out_dir, f"{nm}.png")

            # 覆盖确认
            if os.path.exists(save_path):
                if not messagebox.askyesno("覆盖确认",
                    f"文件已存在:\n{pg}/{nm}.png\n\n确定要覆盖吗？",
                    parent=dialog):
                    return

            os.makedirs(out_dir, exist_ok=True)
            cropped = self.pil_image.crop((x1, y1, x2, y2))
            cropped.save(save_path, "PNG")

            # 复制坐标
            btn_name_upper = nm.upper().replace("-", "_")
            coord_text = (
                f'Button(\n'
                f'    area=({x1}, {y1}, {x2}, {y2}),\n'
                f'    button=({x1}, {y1}, {x2}, {y2}),\n'
                f'    file="assets/templates/{pg}/{nm}.png",\n'
                f'    name="{btn_name_upper}",\n'
                f')'
            )
            self._copy(coord_text)

            # 添加到标记列表
            self.markers.append({
                "name": f"{pg}/{nm}", "x": x1, "y": y1,
                "x2": x2, "y2": y2, "w": w, "h": h,
                "page": pg, "file": f"{nm}.png",
            })
            self._refresh_list()
            self._refresh()

            # 更新侧边栏默认值（方便连续截图）
            self.page_var.set(pg)
            self.name_var.set(nm)

            self.box_info.config(
                text=f"✅ 已保存: {pg}/{nm}.png\n区域: ({x1},{y1})-({x2},{y2})",
                fg="#66bb6a")

            result["saved"] = True
            dialog.destroy()

        def do_cancel():
            self._cancel_select()
            dialog.destroy()

        tk.Button(btn_row, text="💾 保存", command=do_save,
                  bg="#4caf50", fg="#fff", relief=tk.FLAT,
                  padx=20, pady=6, font=("Microsoft YaHei", 11, "bold"),
                  activebackground="#66bb6a").pack(side=tk.RIGHT, padx=4)
        tk.Button(btn_row, text="取消", command=do_cancel,
                  bg="#3d3d3d", fg="#ddd", relief=tk.FLAT,
                  padx=16, pady=6, font=("Microsoft YaHei", 10),
                  activebackground="#555").pack(side=tk.RIGHT, padx=4)

        dialog.bind("<Return>", lambda e: do_save())
        dialog.bind("<Escape>", lambda e: do_cancel())

        # 居中
        dialog.update_idletasks()
        dw, dh = dialog.winfo_width(), dialog.winfo_height()
        rw, rh = self.root.winfo_width(), self.root.winfo_height()
        rx, ry = self.root.winfo_x(), self.root.winfo_y()
        dialog.geometry(f"+{rx + (rw - dw) // 2}+{ry + (rh - dh) // 2}")

        self.root.wait_window(dialog)

    def _save_selection(self):
        """已废弃，使用 _show_save_dialog 替代"""
        self._show_save_dialog()

    def _cancel_select(self):
        self.select_start = None
        self.select_end = None
        self.selecting = False
        self.box_info.config(text="拖拽左键进行框选", fg="#888")
        self._refresh()

    def _choose_output_dir(self):
        d = filedialog.askdirectory(title="选择模板输出目录",
                                     initialdir=self.output_dir.get())
        if d:
            self.output_dir.set(d)

    # ══════════════════════════════════════════════════════
    #  标记列表
    # ══════════════════════════════════════════════════════

    def _refresh_list(self):
        self.marker_listbox.delete(0, tk.END)
        for i, m in enumerate(self.markers):
            name = m.get("name", f"#{i+1}")
            if "x2" in m:
                text = f" [{name:<20}] ({m['x']},{m['y']})-({m['x2']},{m['y2']}) {m['w']}×{m['h']}"
            else:
                c = f"#{m.get('r',0):02X}{m.get('g',0):02X}{m.get('b',0):02X}"
                text = f" {name:<20} ({m['x']:>4},{m['y']:>4}) {c}"
            self.marker_listbox.insert(tk.END, text)
        self.marker_count.config(text=f"({len(self.markers)})")

    def _on_list_double(self, event):
        sel = self.marker_listbox.curselection()
        if sel and self.markers:
            m = self.markers[sel[0]]
            # 复制该标记的坐标
            if "x2" in m:
                self._copy(f"({m['x']}, {m['y']}, {m['x2']}, {m['y2']})")
            else:
                self._copy(f"({m['x']}, {m['y']})")

    def delete_last_marker(self):
        if self.markers:
            self.markers.pop()
            self._refresh_list()
            self._refresh()

    def clear_markers(self):
        self.markers.clear()
        self.marker_listbox.delete(0, tk.END)
        self.marker_count.config(text="(0)")
        self._refresh()

    # ══════════════════════════════════════════════════════
    #  复制 & 导出
    # ══════════════════════════════════════════════════════

    def _copy(self, text):
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(text)
            self.root.update()
        except: pass

    def copy_all_python(self):
        if not self.markers: return
        lines = []
        for m in self.markers:
            name = m.get("name", "point").replace("/", "_").upper()
            if "x2" in m:
                page = m.get("page", "shared")
                fname = m.get("file", f"{name}.png")
                lines.append(
                    f'{name} = Button(\n'
                    f'    area=({m["x"]}, {m["y"]}, {m["x2"]}, {m["y2"]}),\n'
                    f'    button=({m["x"]}, {m["y"]}, {m["x2"]}, {m["y2"]}),\n'
                    f'    file="assets/templates/{page}/{fname}",\n'
                    f'    name="{name}",\n'
                    f')'
                )
            else:
                lines.append(f'        "{name}": ({m["x"]}, {m["y"]}),')
        self._copy("\n\n".join(lines))

    def export_yaml(self):
        if not self.markers:
            messagebox.showinfo("提示", "没有可导出的标记")
            return
        path = filedialog.asksaveasfilename(
            title="导出坐标配置 (YAML)",
            defaultextension=".yaml",
            filetypes=[("YAML", "*.yaml"), ("全部", "*.*")]
        )
        if not path: return
        data = {
            "coords": {},
            "buttons": [],
            "source_image": os.path.basename(self.image_path) if self.image_path else "",
        }
        for m in self.markers:
            if "x2" in m:
                data["buttons"].append({
                    "name": m.get("name", ""),
                    "area": [m["x"], m["y"], m["x2"], m["y2"]],
                    "page": m.get("page", ""),
                    "file": m.get("file", ""),
                })
            else:
                name = m.get("name", f"point")
                data["coords"][name] = {"x": m["x"], "y": m["y"]}
        with open(path, "w", encoding="utf-8") as f:
            yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
        messagebox.showinfo("导出成功", f"已导出到:\n{path}")

    def export_json(self):
        if not self.markers:
            messagebox.showinfo("提示", "没有可导出的标记")
            return
        path = filedialog.asksaveasfilename(
            title="导出坐标配置 (JSON)",
            defaultextension=".json",
            filetypes=[("JSON", "*.json"), ("全部", "*.*")]
        )
        if not path: return
        data = {
            "coords": {},
            "buttons": [],
            "source_image": os.path.basename(self.image_path) if self.image_path else "",
        }
        for m in self.markers:
            if "x2" in m:
                data["buttons"].append({
                    "name": m.get("name", ""),
                    "area": [m["x"], m["y"], m["x2"], m["y2"]],
                    "page": m.get("page", ""),
                    "file": m.get("file", ""),
                })
            else:
                name = m.get("name", f"point")
                data["coords"][name] = {"x": m["x"], "y": m["y"]}
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        messagebox.showinfo("导出成功", f"已导出到:\n{path}")


def main():
    root = tk.Tk()
    try:
        root.iconbitmap(default="")
    except: pass

    img_path = None
    if len(sys.argv) > 1 and not sys.argv[1].startswith("--"):
        img_path = sys.argv[1]

    TemplateCaptureTool(root, image_path=img_path)
    root.mainloop()


if __name__ == "__main__":
    main()
