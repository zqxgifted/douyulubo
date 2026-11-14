#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 douyulubo contributors
"""douyulubo —— 斗鱼录播归档工具箱 图形界面。

页面结构（4 个页签）
--------------------
① 首页     搜索主播 + 搜索结果（可勾选要下载的场次）
② 下载     清晰度、并发、目录等下载相关设置 + 下载操作
③ 弹幕     弹幕处理方式 + 转 ASS 的全部排版参数
④ 配置     运行环境、路径、其他杂项；说明日志输出位置

日志：不做独立页签，改为主窗口底部可折叠面板（折叠时几乎不占空间）。
窗口：启动即最大化（不是全屏）。
"""
from __future__ import annotations

import json
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import tkinter as tk
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

APP_TITLE = "斗鱼录播工具箱"
APP_SUBTITLE = "douyulubo"

sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    import deps as deps_mod
except ImportError:
    deps_mod = None
try:
    import theme
except ImportError:
    theme = None
try:
    from result_tree import ResultTree
except ImportError:
    ResultTree = None


def _find_root() -> Path:
    here = Path(__file__).resolve().parent
    if (here.parent / "core" / "douyu.mjs").is_file():
        return here.parent
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return here.parent


class ScrollableFrame(ttk.Frame):
    """可垂直滚动的容器：内容超出窗口时出现滚动条（鼠标滚轮可用）。

    用法：内部控件都放进 self.body。
    """

    def __init__(self, parent: tk.Misc, **kw) -> None:
        super().__init__(parent, **kw)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        self.canvas = tk.Canvas(self, borderwidth=0, highlightthickness=0,
                                background=theme.BG if theme else "#f4f5f7")
        self.canvas.grid(row=0, column=0, sticky="nsew")

        self.vsb = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.vsb.grid(row=0, column=1, sticky="ns")
        self.canvas.configure(yscrollcommand=self.vsb.set)

        self.body = ttk.Frame(self.canvas)
        self._win = self.canvas.create_window((0, 0), window=self.body, anchor="nw")

        self.body.bind("<Configure>", self._on_body_config)
        self.canvas.bind("<Configure>", self._on_canvas_config)
        # 鼠标进入时绑定滚轮，离开时解绑，避免抢别处的滚动
        self.canvas.bind("<Enter>", lambda _e: self._bind_wheel())
        self.canvas.bind("<Leave>", lambda _e: self._unbind_wheel())

    def _on_body_config(self, _e) -> None:
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas_config(self, e) -> None:
        # 让内容宽度跟随画布，避免横向裁切
        self.canvas.itemconfigure(self._win, width=e.width)
        self._toggle_scrollbar()

    def _toggle_scrollbar(self) -> None:
        need = self.body.winfo_reqheight() > self.canvas.winfo_height()
        if need:
            self.vsb.grid()
        else:
            self.vsb.grid_remove()

    def _bind_wheel(self) -> None:
        self.canvas.bind_all("<MouseWheel>", self._on_wheel)

    def _unbind_wheel(self) -> None:
        self.canvas.unbind_all("<MouseWheel>")

    def _on_wheel(self, e) -> None:
        if self.body.winfo_reqheight() <= self.canvas.winfo_height():
            return
        self.canvas.yview_scroll(int(-e.delta / 120), "units")


ROOT = _find_root()
CONFIG_PATH = ROOT / "config.json"
EXAMPLE_CONFIG = ROOT / "examples" / "config.example.json"
CLI = ROOT / "core" / "douyu.mjs"
IS_WINDOWS = os.name == "nt"

# 内容类型：录播 / 投稿（两套接口，数据结构不同）
# 转码编码器
TRANSCODE_CODECS = [
    ("h265", "H.265 / HEVC（推荐）"),
    ("av1", "AV1（压缩率最高）"),
    ("h264", "H.264（兼容性最好）"),
]

# 质量档（数字由脚本按编码器换算成 QP）
TRANSCODE_QUALITIES = [
    ("high", "高画质（接近原片）"),
    ("balanced", "平衡（推荐）"),
    ("small", "省空间"),
    ("tiny", "极限压缩"),
]

CONTENT_TYPES = [
    ("replay", "录播（直播回放）"),
    ("post", "投稿（上传视频）"),
]

QUALITY_CHOICES = [
    ("highest", "优先最高清晰度（默认）"),
    ("original", "原画"),
    ("1080p", "1080P"),
    ("720p", "720P"),
    ("540p", "540P"),
    ("480p", "480P"),
    ("360p", "360P"),
    ("audio", "纯音频（仅音频流）"),
]
DANMAKU_CHOICES = [
    ("ass", "下载弹幕并转换 ASS 格式（默认）"),
    ("xml", "只下载 XML 原始弹幕"),
    ("none", "不下载弹幕"),
]
BLOCK_CHOICES = [
    ("top", "屏蔽顶部弹幕"),
    ("bottom", "屏蔽底部弹幕"),
    ("color", "屏蔽彩色弹幕"),
    ("repeat", "屏蔽重复弹幕"),
    ("special", "屏蔽特殊弹幕"),
]
# 搜索范围：默认只看最新的 N 个录播（主播可能几年没更新，用"最近24小时"会搜不到）
LATEST_PRESETS = [
    ("last10", "最新 10 个"),
    ("last30", "最新 30 个"),
    ("last50", "最新 50 个"),
    ("last100", "最新 100 个"),
    ("all", "全部录播"),
    ("custom", "自定义日期范围"),
]
# 兼容旧配置里的值
DATE_PRESETS = LATEST_PRESETS


def load_config() -> dict:
    if CONFIG_PATH.is_file():
        try:
            return json.loads(CONFIG_PATH.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            return {}
    return {}


def save_config(cfg: dict) -> None:
    CONFIG_PATH.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")


def parse_up_id(text: str) -> str | None:
    if not text:
        return None
    s = text.strip()
    m = re.search(r"/author(?:-replay)?/([A-Za-z0-9]+)", s)
    if m:
        return m.group(1)
    if re.fullmatch(r"[A-Za-z0-9]{6,32}", s):
        return s
    return None


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(f"{APP_TITLE} · {APP_SUBTITLE}")
        self.minsize(1000, 680)
        self._set_window_icon()

        self.log_queue: queue.Queue[tuple[str, str]] = queue.Queue()
        self.proc: subprocess.Popen | None = None
        self.proc_lock = threading.Lock()
        self.running = False
        self._anchor_name = ""
        self._shows: list[dict] = []
        self._posts: list[dict] = []
        self._checked: set[int] = set()
        self.page = 1              # 当前页
        self.page_size = 5         # 每页场次数
        self.select_state = 0      # 0=未选 1=本页 2=全部
        self.probing = False       # 是否正在探测当前页
        self._probe_retry = None   # 探测中又来了新请求，记下来

        if theme:
            theme.apply(self)
        self._maximize()
        self._build_ui()
        self._poll_log()
        self.after(200, self._load_state)
        self._log("info", f"程序目录：{ROOT}")

    def _set_window_icon(self) -> None:
        """设置窗口图标（鲸鱼）。"""
        ico = Path(__file__).resolve().parent / "whale.ico"
        try:
            if ico.is_file():
                self.iconbitmap(default=str(ico))
        except tk.TclError:
            pass

    def _maximize(self) -> None:
        """最大化窗口（不是全屏，仍保留标题栏与任务栏）。"""
        try:
            if IS_WINDOWS:
                self.state("zoomed")
            else:
                self.attributes("-zoomed", True)
        except tk.TclError:
            sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
            self.geometry(f"{int(sw * 0.92)}x{int(sh * 0.88)}+{int(sw * 0.04)}+{int(sh * 0.05)}")

    # ================= 构建 UI =================
    def _build_ui(self) -> None:
        self._build_topbar()

        body = ttk.Frame(self)
        body.pack(fill="both", expand=True, padx=14, pady=(0, 0))

        self.nb = ttk.Notebook(body)
        self.nb.pack(fill="both", expand=True)

        # 每个页签内容都放进可滚动容器，窗口变小时也能看全
        self.tab_home = ttk.Frame(self.nb)
        self.tab_dl = ttk.Frame(self.nb)
        self.tab_cfg = ttk.Frame(self.nb)
        self.nb.add(self.tab_home, text="搜索")
        self.nb.add(self.tab_dl, text="下载管理")
        self.nb.add(self.tab_cfg, text="配置")

        # 首页：用普通 Frame（结果表自己滚动，整页不滚）
        self.scroll_home = ttk.Frame(self.tab_home, padding=(14, 12))
        self.scroll_home.pack(fill="both", expand=True)
        self.scroll_home.body = self.scroll_home     # 兼容旧引用

        # 配置页：内容多，保留整页滚动
        self.scroll_cfg = ScrollableFrame(self.tab_cfg)
        self.scroll_cfg.pack(fill="both", expand=True, padx=14, pady=12)

        self.tab_dl_body = ttk.Frame(self.tab_dl, padding=(14, 12))
        self.tab_dl_body.pack(fill="both", expand=True)

        self._build_home(self.scroll_home.body)
        self._build_download(self.tab_dl_body)
        self._build_config(self.scroll_cfg.body)

    def _build_topbar(self) -> None:
        # 顶部白底条 + 橙色品牌点
        bar = ttk.Frame(self, style="Header.TFrame")
        bar.pack(fill="x", padx=0, pady=0)

        inner = ttk.Frame(bar, style="Header.TFrame")
        inner.pack(fill="x", padx=16, pady=(14, 10))

        left = ttk.Frame(inner, style="Header.TFrame")
        left.pack(side="left", fill="x", expand=True)

        if theme:
            title = ttk.Frame(left, style="Header.TFrame")
            title.pack(side="left", padx=(0, 22))
            # 橙色小方块 + 应用名
            dot = tk.Frame(title, background=theme.ORANGE, width=4, height=22)
            dot.pack(side="left", padx=(0, 8))
            dot.pack_propagate(False)
            ttk.Label(title, text="斗鱼录播", style="AccentTitle.TLabel").pack(side="left")

        self.var_anchor = tk.StringVar(value="未识别主播")
        self.lbl_anchor = ttk.Label(left, textvariable=self.var_anchor, style="TLabel",
                                    font=("Microsoft YaHei UI", 10, "bold"))
        self.lbl_anchor.pack(side="left", padx=(14, 0))
        if theme:
            self.lbl_anchor.configure(foreground=theme.MUTED)

        # 右上角状态标签已移除（状态改在搜索结果表的「状态」列里显示）

        # 顶部与正文之间的细分隔线
        if theme:
            tk.Frame(self, background=theme.BORDER, height=1).pack(fill="x")

    def _build_download(self, parent) -> None:
        """下载历史页签。"""
        parent.rowconfigure(0, weight=1)
        parent.columnconfigure(0, weight=1)
        # 右下：下载管理
        dm = ttk.LabelFrame(parent, text="  下载历史  ", padding=12)
        dm.grid(row=0, column=0, sticky="nsew")
        dm.rowconfigure(1, weight=1)
        dm.columnconfigure(0, weight=1)

        # 顶部：状态 + 刷新
        head = ttk.Frame(dm)
        head.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        self.var_dl_status = tk.StringVar(value="暂无任务")
        ttk.Label(head, textvariable=self.var_dl_status,
                  style="CardMuted.TLabel").pack(side="left")
        ttk.Button(head, text="刷新", style="Small.TButton",
                   command=self.refresh_history).pack(side="right")

        # 任务/历史列表
        cols = ("dl_time", "air_time", "title", "size", "progress", "state")
        self.tree_hist = ttk.Treeview(dm, columns=cols, show="headings",
                                      selectmode="browse", height=16)
        heads = {"dl_time": "下载时间", "air_time": "录播时间", "title": "标题",
                 "size": "大小", "progress": "进度 / 速度", "state": "状态"}
        widths = {"dl_time": 108, "air_time": 108, "title": 340,
                  "size": 82, "progress": 150, "state": 68}
        for c in cols:
            self.tree_hist.heading(c, text=heads[c])
            self.tree_hist.column(c, width=widths[c], anchor="center")
        if theme:
            theme.stripe_tree(self.tree_hist)
        vs2 = ttk.Scrollbar(dm, orient="vertical", command=self.tree_hist.yview)
        self.tree_hist.configure(yscrollcommand=vs2.set)
        self.tree_hist.grid(row=1, column=0, sticky="nsew")
        vs2.grid(row=1, column=1, sticky="ns")
        self.tree_hist.bind("<Double-1>", self._on_hist_double)

        # 底部：打开目录
        bt = ttk.Frame(dm)
        bt.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        ttk.Button(bt, text="打开下载目录", style="Small.TButton",
                   command=self.open_download_dir).pack(side="left")
        ttk.Button(bt, text="清空记录", style="Small.TButton",
                   command=self.clear_history).pack(side="left", padx=6)

    # ---------- ① 首页：搜索 + 结果 ----------
    def _build_home(self, f) -> None:
        f.rowconfigure(1, weight=1)     # 只让结果区伸缩
        f.columnconfigure(0, weight=1)

        # ① 搜索卡片：单行横排，节省纵向空间
        sc = ttk.LabelFrame(f, text="  搜索  ", padding=(12, 8))
        sc.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        sc.columnconfigure(0, weight=1)

        row = ttk.Frame(sc)
        row.grid(row=0, column=0, sticky="ew")

        ttk.Label(row, text="主播链接").pack(side="left")
        self.var_upid = tk.StringVar()
        e = ttk.Entry(row, textvariable=self.var_upid, width=32)
        e.pack(side="left", padx=(6, 12))
        e.bind("<Return>", lambda _ev: self.do_search())

        self.var_ctype = tk.StringVar(value=CONTENT_TYPES[0][1])
        self.cmb_ctype = ttk.Combobox(row, textvariable=self.var_ctype, state="readonly",
                                      width=16, values=[x for _, x in CONTENT_TYPES])
        self.cmb_ctype.pack(side="left")
        self.cmb_ctype.set(CONTENT_TYPES[0][1])
        self.cmb_ctype.bind("<<ComboboxSelected>>", lambda _ev: self._on_ctype_change())

        self.var_range = tk.StringVar(value=LATEST_PRESETS[0][1])
        self.cmb_range = ttk.Combobox(row, textvariable=self.var_range, state="readonly",
                                      width=13, values=[x for _, x in LATEST_PRESETS])
        self.cmb_range.pack(side="left", padx=(8, 0))
        self.cmb_range.bind("<<ComboboxSelected>>", lambda _ev: self._on_range_change())

        self.btn_search = ttk.Button(row, text="搜索", style="Accent.TButton",
                                     command=self.do_search)
        self.btn_search.pack(side="left", padx=(10, 0))

        self.var_ctype_hint = tk.StringVar(value="")
        ttk.Label(sc, textvariable=self.var_ctype_hint,
                  style="CardMuted.TLabel").grid(row=1, column=0, sticky="w", pady=(4, 0))

        # ② 筛选相关变量（控件已合并到结果栏）
        self.var_from = tk.StringVar()
        self.var_to = tk.StringVar()
        self.var_kw = tk.StringVar()
        self.var_summary = tk.StringVar(value="")

        # 下半区：左 2/3 结果树，右 1/3 下载管理
        lower = ttk.Frame(f)
        lower.grid(row=1, column=0, sticky="nsew")
        lower.rowconfigure(0, weight=1)
        lower.columnconfigure(0, weight=1)

        # 结果树（场次 → 分段）
        tf = ttk.LabelFrame(lower, text="  搜索结果  ", padding=10)
        tf.grid(row=0, column=0, sticky="nsew")
        tf.rowconfigure(1, weight=1)
        tf.columnconfigure(0, weight=1)
        tf.rowconfigure(1, weight=1)
        tf.columnconfigure(0, weight=1)

        # 顶部工具栏：筛选 + 全选 + 下载 + 分页，全部在同一行
        bar = ttk.Frame(tf)
        bar.grid(row=0, column=0, sticky="ew", pady=(0, 8))

        # —— 左：筛选 ——
        ttk.Label(bar, text="关键词", style="CardMuted.TLabel").pack(side="left")
        kw = ttk.Entry(bar, textvariable=self.var_kw, width=16)
        kw.pack(side="left", padx=(4, 8))
        kw.bind("<Return>", lambda _e: self.apply_filter())

        ttk.Button(bar, text="应用筛选", style="Small.TButton",
                   command=self.apply_filter).pack(side="left")

        # 自定义日期（默认隐藏，选「自定义」时出现）
        self.frm_custom = ttk.Frame(bar)
        self.frm_custom.pack(side="left", padx=(8, 0))
        ttk.Label(self.frm_custom, text="从").pack(side="left")
        ttk.Entry(self.frm_custom, textvariable=self.var_from, width=10).pack(side="left", padx=2)
        ttk.Label(self.frm_custom, text="到").pack(side="left")
        ttk.Entry(self.frm_custom, textvariable=self.var_to, width=10).pack(side="left", padx=2)

        ttk.Separator(bar, orient="vertical").pack(side="left", fill="y", padx=10)

        # —— 中：全选 + 下载 ——
        self.btn_select_all = ttk.Button(bar, text="全选本页", style="Ghost.TButton",
                                         command=self.cycle_select_all)
        self.btn_select_all.pack(side="left")

        self.btn_download_sel = ttk.Button(bar, text="下载选中", style="Accent.TButton",
                                           command=self.download_selected)
        self.btn_download_sel.pack(side="left", padx=8)

        self.var_sel = tk.StringVar(value="未选择")
        ttk.Label(bar, textvariable=self.var_sel, style="Muted.TLabel").pack(side="left", padx=6)

        # —— 右：分页 ——
        ttk.Button(bar, text="下一页 ▶", style="Small.TButton",
                   command=self.next_page).pack(side="right")
        self.var_page = tk.StringVar(value="1 / 1")
        ttk.Label(bar, textvariable=self.var_page, style="CardMuted.TLabel").pack(
            side="right", padx=6)
        ttk.Button(bar, text="◀ 上一页", style="Small.TButton",
                   command=self.prev_page).pack(side="right")

        # 汇总：显示在分页按钮左侧
        ttk.Label(bar, textvariable=self.var_summary,
                  style="CardMuted.TLabel").pack(side="right", padx=(0, 14))


        # 树
        if ResultTree:
            self.rtree = ResultTree(tf, on_select_change=self._on_tree_select)
            self.rtree.grid(row=1, column=0, sticky="nsew")
            self.tree = self.rtree.tree   # 兼容旧引用
        else:
            self.rtree = None


    # ---------- ② 下载 ----------
    def _build_danmaku(self, f) -> None:
        # 已合并到配置页，此方法保留为空实现（避免旧引用报错）
        return

    def _build_config(self, f) -> None:
        f.columnconfigure(0, weight=1)

        # ---- 运行组件：状态只显示 ✔ / ✘，路径直接放在输入框里 ----
        comp = ttk.LabelFrame(f, text="  运行组件  ", padding=14)
        comp.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        comp.columnconfigure(2, weight=1)

        ttk.Label(comp, text="组件", style="CardMuted.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(comp, text="状态", style="CardMuted.TLabel").grid(
            row=0, column=1, sticky="w", padx=(0, 12))
        ttk.Label(comp, text="路径", style="CardMuted.TLabel").grid(
            row=0, column=2, sticky="w")

        self.comp_entries: dict[str, ttk.Entry] = {}
        self._comp_var_map: dict[str, tk.StringVar] = {}
        self.comp_status: dict[str, tk.StringVar] = {}
        comp_fields = [
            ("node_path", "node", "Node.js", "node.exe"),
            ("python_path", "python", "Python", "python.exe"),
            ("ffmpeg", "ffmpeg", "ffmpeg", "ffmpeg.exe"),
        ]
        for i, (key, dep, label, exe) in enumerate(comp_fields, start=1):
            ttk.Label(comp, text=label, width=8).grid(row=i, column=0, sticky="w", pady=6)
            st = tk.StringVar(value="—")
            self.comp_status[dep] = st
            lbl = ttk.Label(comp, textvariable=st, style="Card.TLabel", width=4)
            lbl.grid(row=i, column=1, sticky="w", padx=(0, 12))
            self.comp_status_label = getattr(self, "comp_status_label", {})
            self.comp_status_label[dep] = lbl

            v = tk.StringVar()
            e = ttk.Entry(comp, textvariable=v, foreground=theme.MUTED if theme else "#888")
            e.grid(row=i, column=2, sticky="ew", pady=6)
            self.comp_entries[key] = e
            self._comp_var_map[key] = v
            # 用户手动改过就变黑色（表示"这是我指定的"）
            v.trace_add("write", lambda *_a, ent=e, var=v: self._on_comp_edit(ent, var))
            ttk.Button(comp, text="浏览…", style="Small.TButton",
                       command=lambda k=key, e2=exe: self.pick_exe(k, e2)).grid(
                row=i, column=3, padx=(8, 0))

        cbtn = ttk.Frame(comp)
        cbtn.grid(row=len(comp_fields) + 1, column=0, columnspan=4, sticky="w", pady=(10, 0))
        ttk.Button(cbtn, text="重新检测", style="Small.TButton",
                   command=self.detect_components).pack(side="left")
        ttk.Label(cbtn, text="灰色=自动检测到的路径，手动填写后会变黑",
                  style="CardMuted.TLabel").pack(side="left", padx=10)

        # ---- 下载设置 ----
        dl = ttk.LabelFrame(f, text="  下载设置  ", padding=14)
        dl.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        dl.columnconfigure(1, weight=1)

        ttk.Label(dl, text="清晰度", width=16).grid(row=0, column=0, sticky="w", pady=5)
        self.var_quality = tk.StringVar()
        self.cmb_quality = ttk.Combobox(dl, textvariable=self.var_quality, state="readonly",
                                        width=26, values=[x for _, x in QUALITY_CHOICES])
        self.cmb_quality.grid(row=0, column=1, sticky="w", pady=5)
        self.cmb_quality.set(QUALITY_CHOICES[0][1])

        ttk.Label(dl, text="同时下载数", width=16).grid(row=1, column=0, sticky="w", pady=5)
        self.var_concurrent = tk.StringVar(value="2")
        tk.Spinbox(dl, from_=1, to=8, width=6, textvariable=self.var_concurrent).grid(
            row=1, column=1, sticky="w", pady=5)
        ttk.Label(dl, text="默认 2；太高容易被限流", style="CardMuted.TLabel").grid(
            row=1, column=2, sticky="w", padx=(10, 0))

        ttk.Label(dl, text="已下载的录播", width=16).grid(row=2, column=0, sticky="w", pady=5)
        self.var_skip_done = tk.BooleanVar(value=True)
        ttk.Checkbutton(dl, text="跳过（避免重复下载）", variable=self.var_skip_done,
                        style="Page.TCheckbutton").grid(row=2, column=1, sticky="w", pady=5)

        ttk.Label(dl, text="小于多少 MB 视为失败", width=16).grid(row=3, column=0, sticky="w", pady=5)
        self.var_min_mb = tk.StringVar(value="100")
        tk.Spinbox(dl, from_=0, to=2000, width=8, textvariable=self.var_min_mb).grid(
            row=3, column=1, sticky="w", pady=5)
        ttk.Label(dl, text="默认 100；超短录播可填 0", style="CardMuted.TLabel").grid(
            row=3, column=2, sticky="w", padx=(10, 0))

        # ---- 弹幕设置 ----
        dm = ttk.LabelFrame(f, text="  弹幕设置  ", padding=14)
        dm.grid(row=2, column=0, sticky="ew", pady=(0, 10))
        dm.columnconfigure(1, weight=1)

        ttk.Label(dm, text="处理方式", width=16).grid(row=0, column=0, sticky="w", pady=5)
        self.var_danmaku = tk.StringVar()
        self.cmb_danmaku = ttk.Combobox(dm, textvariable=self.var_danmaku, state="readonly",
                                        width=26, values=[x for _, x in DANMAKU_CHOICES])
        self.cmb_danmaku.grid(row=0, column=1, sticky="w", pady=5)
        self.cmb_danmaku.set(DANMAKU_CHOICES[0][1])

        ttk.Label(dm, text="屏蔽类型", width=16).grid(row=1, column=0, sticky="nw", pady=6)
        blk = ttk.Frame(dm)
        blk.grid(row=1, column=1, columnspan=2, sticky="w", pady=6)
        self.block_vars: dict[str, tk.BooleanVar] = {}
        for k, lab in BLOCK_CHOICES:
            v = tk.BooleanVar(value=False)
            self.block_vars[k] = v
            ttk.Checkbutton(blk, text=lab, variable=v, style="Page.TCheckbutton").pack(
                side="left", padx=(0, 12))

        lay = ttk.Frame(dm)
        lay.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(8, 0))
        for c in (1, 3):
            lay.columnconfigure(c, weight=1)
        self.var_font_size = tk.StringVar(value="50")
        self.var_scroll = tk.StringVar(value="8")
        self.var_fixed = tk.StringVar(value="4.5")
        self.var_line_sp = tk.StringVar(value="0")
        self.var_top_m = tk.StringVar(value="0")
        self.var_bottom_m = tk.StringVar(value="0")
        self.var_opacity = tk.StringVar(value="255")
        self.var_font_name = tk.StringVar(value="微软雅黑")
        self.var_bold = tk.BooleanVar(value=False)
        self.var_outline = tk.StringVar(value="1.0")
        self.var_shadow = tk.StringVar(value="0.0")
        self.var_time_shift = tk.StringVar(value="0.0")
        self.var_no_overlap = tk.BooleanVar(value=True)

        layout_rows = [
            ("字号", self.var_font_size, "滚动时长(秒)", self.var_scroll),
            ("固定停留(秒)", self.var_fixed, "行间距(像素)", self.var_line_sp),
            ("顶部留白", self.var_top_m, "底部留白", self.var_bottom_m),
            ("不透明度", self.var_opacity, "时间轴偏移", self.var_time_shift),
            ("描边宽度", self.var_outline, "阴影偏移", self.var_shadow),
        ]
        for i, (l1, v1, l2, v2) in enumerate(layout_rows):
            ttk.Label(lay, text=l1, width=16).grid(row=i, column=0, sticky="w", pady=4)
            ttk.Entry(lay, textvariable=v1, width=10).grid(row=i, column=1, sticky="w", pady=4)
            ttk.Label(lay, text=l2, width=16).grid(row=i, column=2, sticky="w", pady=4, padx=(16, 0))
            ttk.Entry(lay, textvariable=v2, width=10).grid(row=i, column=3, sticky="w", pady=4)

        ext = ttk.Frame(dm)
        ext.grid(row=3, column=0, columnspan=3, sticky="w", pady=(8, 0))
        ttk.Label(ext, text="字体").pack(side="left")
        ttk.Entry(ext, textvariable=self.var_font_name, width=16).pack(side="left", padx=6)
        ttk.Checkbutton(ext, text="加粗", variable=self.var_bold).pack(side="left", padx=(14, 0))
        ttk.Checkbutton(ext, text="强制不重叠", variable=self.var_no_overlap).pack(
            side="left", padx=(14, 0))
        ttk.Button(ext, text="手动转换 XML→ASS", style="Small.TButton",
                   command=self.task_convert_xml).pack(side="left", padx=(20, 0))

        # ---- 转码设置 ----
        tc = ttk.LabelFrame(f, text="  转码  ", padding=14, style="Card.TLabelframe")
        tc.grid(row=3, column=0, sticky="ew", pady=(0, 10))
        tc.columnconfigure(1, weight=1)

        ttk.Label(tc, text="下载后自动转码", width=18).grid(
            row=0, column=0, sticky="w", pady=5)
        self.var_tc_enabled = tk.BooleanVar(value=False)
        ttk.Checkbutton(tc, text="开启（转码完成才算下载结束）",
                        variable=self.var_tc_enabled).grid(row=0, column=1, sticky="w", pady=5)

        ttk.Label(tc, text="编码格式", width=18).grid(row=1, column=0, sticky="w", pady=5)
        self.var_tc_codec = tk.StringVar()
        self.cmb_tc_codec = ttk.Combobox(tc, textvariable=self.var_tc_codec,
                                         state="readonly", width=30,
                                         values=[x for _, x in TRANSCODE_CODECS])
        self.cmb_tc_codec.grid(row=1, column=1, sticky="w", pady=5)
        self.cmb_tc_codec.set(TRANSCODE_CODECS[0][1])
        self.cmb_tc_codec.bind("<<ComboboxSelected>>",
                               lambda _e: self._on_tc_codec_change())

        ttk.Label(tc, text="质量档", width=18).grid(row=2, column=0, sticky="w", pady=5)
        self.var_tc_quality = tk.StringVar()
        self.cmb_tc_quality = ttk.Combobox(tc, textvariable=self.var_tc_quality,
                                           state="readonly", width=30,
                                           values=[x for _, x in TRANSCODE_QUALITIES])
        self.cmb_tc_quality.grid(row=2, column=1, sticky="w", pady=5)
        self.cmb_tc_quality.set(TRANSCODE_QUALITIES[1][1])
        self.cmb_tc_quality.bind("<<ComboboxSelected>>",
                                 lambda _e: self._on_tc_codec_change())

        ttk.Label(tc, text="当前 QP", width=18).grid(row=3, column=0, sticky="w", pady=5)
        qp_row = ttk.Frame(tc)
        qp_row.grid(row=3, column=1, sticky="w", pady=5)
        self.var_tc_qp = tk.StringVar(value="自动")
        ttk.Label(qp_row, textvariable=self.var_tc_qp,
                  style="CardMuted.TLabel").pack(side="left")
        self.var_tc_qp_hint = tk.StringVar(value="")
        ttk.Label(qp_row, textvariable=self.var_tc_qp_hint,
                  style="CardMuted.TLabel").pack(side="left", padx=(12, 0))

        ttk.Label(tc, text="速度预设", width=18).grid(row=4, column=0, sticky="w", pady=5)
        p_row = ttk.Frame(tc)
        p_row.grid(row=4, column=1, sticky="w", pady=5)
        self.var_tc_preset = tk.StringVar(value="5")
        tk.Spinbox(p_row, from_=1, to=7, width=5,
                   textvariable=self.var_tc_preset).pack(side="left")
        ttk.Label(p_row, text="p1 最快 / p7 画质最好",
                  style="CardMuted.TLabel").pack(side="left", padx=(10, 0))

        ttk.Label(tc, text="文件名后缀", width=18).grid(row=5, column=0, sticky="w", pady=5)
        sfx_row = ttk.Frame(tc)
        sfx_row.grid(row=5, column=1, sticky="w", pady=5)
        ttk.Label(sfx_row, text="_", style="CardMuted.TLabel").pack(side="left")
        self.var_tc_suffix = tk.StringVar(value="")
        ttk.Entry(sfx_row, textvariable=self.var_tc_suffix, width=12).pack(side="left")
        ttk.Label(sfx_row, text="留空则不加；填 AV1 得到 name_AV1.mp4",
                  style="CardMuted.TLabel").pack(side="left", padx=(10, 0))

        ttk.Label(tc, text="转码后", width=18).grid(row=6, column=0, sticky="w", pady=5)
        opt = ttk.Frame(tc)
        opt.grid(row=6, column=1, sticky="w", pady=5)
        self.var_tc_delete = tk.BooleanVar(value=False)
        ttk.Checkbutton(opt, text="删除源文件", variable=self.var_tc_delete).pack(side="left")
        self.var_tc_audio = tk.BooleanVar(value=False)
        ttk.Checkbutton(opt, text="音频重编码 AAC 192k",
                        variable=self.var_tc_audio).pack(side="left", padx=(16, 0))

        act = ttk.Frame(tc)
        act.grid(row=7, column=0, columnspan=2, sticky="w", pady=(10, 0))
        ttk.Button(act, text="转码下载目录", style="Accent.TButton",
                   command=self.task_transcode_all).pack(side="left")
        ttk.Button(act, text="转码选中的记录", style="Ghost.TButton",
                   command=self.task_transcode_selected).pack(side="left", padx=8)
        ttk.Button(act, text="试算体积（60秒）", style="Small.TButton",
                   command=self.task_transcode_preview).pack(side="left")

        # ---- 其他路径 ----
        paths = ttk.LabelFrame(f, text="  其他设置  ", padding=14)
        paths.grid(row=4, column=0, sticky="ew", pady=(0, 10))
        paths.columnconfigure(1, weight=1)
        self.cfg_vars: dict[str, tk.StringVar] = {}
        fields = [
            ("work_dir", "工作目录", True, "留空 = 程序目录下的 downloads 文件夹"),
            ("danmaku_factory", "DanmakuFactory", True, "留空 = 用内置转换器"),
        ]
        for i, (key, label, browse, hint) in enumerate(fields):
            ttk.Label(paths, text=label, width=16).grid(row=i, column=0, sticky="w", pady=6)
            v = tk.StringVar()
            self.cfg_vars[key] = v
            ttk.Entry(paths, textvariable=v).grid(row=i, column=1, sticky="ew", pady=6)
            if browse:
                ttk.Button(paths, text="浏览…", style="Small.TButton",
                           command=lambda k=key: self.pick_path(k)).grid(row=i, column=2, padx=(8, 0))
            ttk.Label(paths, text=hint, style="CardMuted.TLabel").grid(
                row=i + 1, column=1, sticky="w")

        # ---- 日志（直接嵌在配置页里，不再单独占窗口底部）----
        logbox = ttk.LabelFrame(f, text="  运行日志  ", padding=14)
        logbox.grid(row=2, column=0, sticky="nsew", pady=(0, 10))
        logbox.columnconfigure(0, weight=1)
        logbox.rowconfigure(1, weight=1)
        f.rowconfigure(5, weight=1)

        self.var_log_path = tk.StringVar()
        head = ttk.Frame(logbox)
        head.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        ttk.Label(head, textvariable=self.var_log_path, style="CardMuted.TLabel",
                  justify="left", wraplength=700).pack(side="left", fill="x", expand=True)
        ttk.Button(head, text="打开文件夹", style="Small.TButton",
                   command=self.open_log_dir).pack(side="right")
        ttk.Button(head, text="清空", style="Small.TButton",
                   command=self.clear_log).pack(side="right", padx=6)

        self.log_wrap = ttk.Frame(logbox)
        self.log_wrap.grid(row=1, column=0, sticky="nsew")
        self.log_text = (theme.make_log_widget(self.log_wrap) if theme
                         else tk.Text(self.log_wrap, wrap="word", font=("Consolas", 9),
                                      state="disabled"))
        vs = ttk.Scrollbar(self.log_wrap, orient="vertical", command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=vs.set, height=10, width=1)
        self.log_text.pack(side="left", fill="both", expand=True)
        vs.pack(side="right", fill="y")

        # ---- 底部按钮 ----
        bf = ttk.Frame(f)
        bf.grid(row=6, column=0, sticky="w", pady=(4, 0))
        ttk.Button(bf, text="保存设置", style="Accent.TButton",
                   command=self.save_all).pack(side="left")
        ttk.Button(bf, text="重新读取", command=self.reload_all).pack(side="left", padx=8)
        ttk.Button(bf, text="恢复默认", command=self.reset_all).pack(side="left")

        f.rowconfigure(4, weight=0)
        f.rowconfigure(5, weight=1)

    # ---------- 底部日志面板 ----------
    def _build_log_panel(self) -> None:
        wrap = ttk.Frame(self)
        wrap.pack(fill="x", padx=14, pady=(0, 8))

        head = ttk.Frame(wrap)
        head.pack(fill="x")
        self.btn_log_toggle = ttk.Button(head, text="收起日志", style="Small.TButton",
                                         command=self.toggle_log)
        self.btn_log_toggle.pack(side="left")
        self.var_log_hint = tk.StringVar(value="运行信息")
        ttk.Label(head, textvariable=self.var_log_hint, style="Muted.TLabel").pack(
            side="left", padx=8)
        ttk.Button(head, text="清空", style="Small.TButton",
                   command=self.clear_log).pack(side="right")

        self.log_wrap = ttk.Frame(wrap)
        self.log_wrap.pack(fill="both", expand=True, pady=(4, 0))
        self.log_text = (theme.make_log_widget(self.log_wrap) if theme
                         else tk.Text(self.log_wrap, wrap="word", font=("Consolas", 9),
                                      state="disabled"))
        vs = ttk.Scrollbar(self.log_wrap, orient="vertical", command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=vs.set)
        # 关键：显式设置高度，否则 pack 后会被压成一条线
        self.log_text.configure(height=8, width=1)
        self.log_text.pack(side="left", fill="both", expand=True)
        vs.pack(side="right", fill="y")

    def do_search(self) -> None:
        up_id = parse_up_id(self.var_upid.get())
        if not up_id:
            messagebox.showwarning("请输入主播链接",
                                   "请粘贴形如 https://v.douyu.com/author-replay/xxxx 的链接，\n"
                                   "或直接输入主播 ID。")
            return
        cfg = load_config()
        if cfg.get("up_id") != up_id:
            cfg["up_id"] = up_id
            save_config(cfg)
        self.var_anchor.set(f"正在获取 {up_id} 的录播列表…")
        if theme:
            self.lbl_anchor.configure(foreground=theme.WARN)
        # 先抓列表（含 point_id），再自动探测清晰度/大小
        self._run_show_search()

    def _run_show_search(self) -> None:
        """搜索：抓场次+分段+point_id → 自动探测清晰度与大小。"""
        if self.running:
            messagebox.showinfo("正在运行", "已有任务在执行，请等待完成。")
            return
        self.save_all(silent=True)
        self._log("cmd", "\n▶ 搜索录播列表（含分段与取流参数）")
        self._set_running(True)

        def work():
            env = (deps_mod.build_env() if deps_mod else os.environ.copy())
            env["PYTHONIOENCODING"] = "utf-8"
            env["PYTHONUTF8"] = "1"
            py = env.get("DOUYU_PY") or sys.executable
            # py 可能是完整路径，取文件名判断
            _b = Path(str(py)).name.lower()
            bundled = _b not in ("python.exe", "python3.exe", "pythonw.exe",
                                  "python", "python3", "pythonw")

            def run_script(script, extra, label):
                cmd = ([py, "--run-py", script, *extra] if bundled
                       else [py, script, *extra])
                self.log_queue.put(("cmd", f"\n▶ {label}"))
                p = subprocess.Popen(
                    cmd, cwd=str(ROOT), env=env,
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, encoding="utf-8", errors="replace",
                    creationflags=(subprocess.CREATE_NO_WINDOW |
                                   subprocess.CREATE_NEW_PROCESS_GROUP) if IS_WINDOWS else 0,
                )
                with self.proc_lock:
                    self.proc = p
                for line in p.stdout:  # type: ignore[union-attr]
                    line = line.rstrip("\r\n")
                    self.log_queue.put(("out", line))
                    self._append_log_file(line)
                return p.wait()

            try:
                ctype = self._ctype_value()
                if ctype == "post":
                    # 投稿模式：只抓投稿
                    rc = run_script(str(ROOT / "scripts" / "list_posts.py"),
                                    [], "抓取投稿列表")
                else:
                    # 录播模式：只抓录播（列表 + 分段）
                    rc = run_script(str(ROOT / "scripts" / "list_shows.py"),
                                    [], "抓取录播列表与分段")
                self.log_queue.put(("done", str(rc)))
            except Exception as e:  # noqa: BLE001
                self.log_queue.put(("err", f"✘ 启动失败: {e}"))
                self.log_queue.put(("done", "1"))

        threading.Thread(target=work, daemon=True).start()

    # ---------- 转码 ----------
    def _tc_codec_value(self) -> str:
        label = self.var_tc_codec.get()
        for v, x in TRANSCODE_CODECS:
            if x == label:
                return v
        return "h265"

    def _tc_quality_value(self) -> str:
        label = self.var_tc_quality.get()
        for v, x in TRANSCODE_QUALITIES:
            if x == label:
                return v
        return "balanced"

    def _tc_qp_of(self, codec: str, quality: str) -> int:
        """按编码器换算 QP（AV1 刻度约 4 倍）。"""
        base = {"high": 20, "balanced": 26, "small": 30, "tiny": 36}.get(quality, 26)
        return min(255, base * 4) if codec == "av1" else min(51, base)

    def _on_tc_codec_change(self) -> None:
        """编码器/质量档变化时刷新 QP 提示。"""
        codec = self._tc_codec_value()
        quality = self._tc_quality_value()
        qp = self._tc_qp_of(codec, quality)
        maxqp = 255 if codec == "av1" else 51
        self.var_tc_qp.set(f"{qp}（{codec.upper()} 刻度 0-{maxqp}）")
        hints = {
            "av1": "压缩率最高；需 RTX 40 系，首次转码会编译内核稍慢",
            "h265": "兼容性好，体积接近 AV1",
            "h264": "任何显卡都支持，体积略大",
        }
        self.var_tc_qp_hint.set(hints.get(codec, ""))

    def _tc_opts(self) -> dict:
        return {
            "codec": self._tc_codec_value(),
            "quality": self._tc_quality_value(),
            "preset": max(1, min(7, int(self.var_tc_preset.get() or 5))),
            "delete": bool(self.var_tc_delete.get()),
            "audio_encode": bool(self.var_tc_audio.get()),
            "suffix": str(getattr(self, "var_tc_suffix", tk.StringVar()).get() or "").strip(),
        }

    def task_transcode_all(self) -> None:
        self._start_transcode(self._work_dir() / "downloads")

    def task_transcode_selected(self) -> None:
        if not hasattr(self, "tree_hist"):
            return
        sel = self.tree_hist.selection()
        if not sel:
            messagebox.showinfo("没有选中", "请在「下载管理」页选中要转码的记录。")
            return
        path = self._hist_path_of(sel[0])
        if not path:
            messagebox.showinfo("找不到文件", "选中的记录没有可用文件路径。")
            return
        self._start_transcode(Path(path).parent)

    def task_transcode_preview(self) -> None:
        """只转前 60 秒，用于估算体积。"""
        src = None
        recs = self._history_records()
        if recs:
            for r in recs:
                f = str(r.get("file") or "")
                if f and Path(f).is_file():
                    src = Path(f)
                    break
        if not src:
            dl = self._work_dir() / "downloads"
            cands = sorted(dl.glob("*.mp4")) if dl.is_dir() else []
            src = cands[0] if cands else None
        if not src:
            messagebox.showinfo("没有视频", "下载目录里没有可试算的视频。")
            return
        o = self._tc_opts()
        argv = [str(ROOT / "scripts" / "transcode_video.py"), str(src),
                "--codec", o["codec"], "--quality", o["quality"],
                "--preset", str(o["preset"]), "--preview", "60"]
        self.nb.select(self.tab_dl)
        self._run_cli_py(argv, f"试算体积（60秒 {o['codec'].upper()}）")

    def _hist_path_of(self, iid: str) -> str:
        try:
            recs = self._history_records()
            idx = list(self.tree_hist.get_children()).index(iid)
            if 0 <= idx < len(recs):
                return str(recs[idx].get("file") or "")
        except (ValueError, AttributeError):
            pass
        return ""

    def _after_download_transcode(self) -> None:
        """下载完成后：若开启了自动转码，从 ts 直接合并转码并清理。"""
        if not getattr(self, "var_tc_enabled", None) or not self.var_tc_enabled.get():
            self._after_state_changed()
            return
        o = self._tc_opts()
        dl = self._work_dir() / "downloads"
        argv = [str(ROOT / "scripts" / "merge_ts.py"), str(dl),
                "--codec", o["codec"], "--quality", o["quality"],
                "--preset", str(o["preset"]), "--delete-ts"]
        if o["suffix"]:
            argv += ["--suffix", o["suffix"]]
        if not o["audio_encode"]:
            argv.append("--audio-copy")
        self._run_cli_py(argv, f"合并转码 {o['codec'].upper()}",
                         on_done=self._after_state_changed)

    def _start_transcode(self, target) -> None:
        if self.running:
            messagebox.showinfo("正在运行", "已有任务在执行，请等待完成。")
            return
        target = Path(target)
        if not target.exists():
            messagebox.showinfo("路径不存在", f"{target}\n\n请先下载视频。")
            return
        o = self._tc_opts()
        # 有 ts 分片就走合并转码（更快、更完整），否则转已有视频
        has_ts = any(target.glob("*-ts")) or (target / "downloads").exists() and any(
            (target / "downloads").glob("*-ts")) if target.is_dir() else False
        if has_ts:
            argv = [str(ROOT / "scripts" / "merge_ts.py"), str(target),
                    "--codec", o["codec"], "--quality", o["quality"],
                    "--preset", str(o["preset"])]
            if o["suffix"]:
                argv += ["--suffix", o["suffix"]]
            label = f"合并转码 {o['codec'].upper()}"
        else:
            argv = [str(ROOT / "scripts" / "transcode_video.py"), str(target),
                    "--codec", o["codec"], "--quality", o["quality"],
                    "--preset", str(o["preset"])]
            if o["delete"]:
                argv.append("--delete")
            if o["audio_encode"]:
                argv.append("--audio-encode")
            label = f"转码 {o['codec'].upper()}"
        self.nb.select(self.tab_dl)
        self._run_cli_py(argv, label, on_done=self._after_state_changed)

    def _refresh_anchor_name(self) -> None:
        """异步取主播昵称（不阻塞界面）。"""
        up_id = load_config().get("up_id")
        if not up_id:
            return

        def work():
            name = None
            try:
                url = (f"https://v.douyu.com/wgapi/vod/center/authorShowVideoList"
                       f"?up_id={up_id}&page=1&limit=1")
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=12) as r:
                    data = json.loads(r.read().decode("utf-8"))
                d = data.get("data") or {}
                lst = d.get("list") or []
                first = lst[0] if lst else {}
                vl = (first.get("video_list") or [{}])[0] if first else {}
                # 昵称实际在 video_list[0].author 里
                for cand in (vl.get("author"),
                             first.get("nickname"),
                             d.get("nickname"),
                             (d.get("author") or {}).get("nickname")):
                    if isinstance(cand, str) and cand.strip():
                        name = cand.strip()
                        break
            except Exception:  # noqa: BLE001
                pass

            def apply():
                if name:
                    self._anchor_name = name
                    self.var_anchor.set(f"{name}（{up_id}）")
                    if theme:
                        self.lbl_anchor.configure(foreground=theme.SUCCESS)
                else:
                    self.var_anchor.set(f"已识别 ID：{up_id}")
                    if theme:
                        self.lbl_anchor.configure(foreground=theme.MUTED)
            self.after(0, apply)
        threading.Thread(target=work, daemon=True).start()

    def _on_range_change(self) -> None:
        if self.var_range.get() == LATEST_PRESETS[-1][1]:
            if not self.frm_custom.winfo_ismapped():
                self.frm_custom.pack(side="left", padx=(8, 0))
            today = datetime.now()
            if not self.var_from.get():
                self.var_from.set((today - timedelta(days=7)).strftime("%Y-%m-%d"))
            if not self.var_to.get():
                self.var_to.set(today.strftime("%Y-%m-%d"))
        else:
            self.frm_custom.pack_forget()
        self.save_all(silent=True)   # 记住上次选择
        self.apply_filter()

    def _range_bounds(self) -> tuple[str, str, int]:
        """返回 (起始日期, 结束日期, 最多条数)。最多条数=0 表示不限。"""
        label = self.var_range.get()
        now = datetime.now()
        if label == LATEST_PRESETS[0][1]:
            return "", "", 10
        if label == LATEST_PRESETS[1][1]:
            return "", "", 30
        if label == LATEST_PRESETS[2][1]:
            return "", "", 50
        if label == LATEST_PRESETS[3][1]:
            return "", "", 100
        if label == LATEST_PRESETS[4][1]:
            return "", "", 0
        return self.var_from.get().strip(), self.var_to.get().strip(), 0

    def apply_filter(self) -> None:
        """按当前内容类型（录播/投稿）筛选并分页渲染。"""
        ctype = self._ctype_value()
        self.var_ctype_hint.set("直播回放，按场次+分段组织"
                                if ctype == "replay" else "上传的视频，不分段")
        if ctype == "post":
            self._apply_filter_posts()
            return

        data_file = self._work_dir() / "data" / "shows_index.json"
        if not data_file.is_file():
            self.var_summary.set("还没有搜索结果，请先点「搜索」")
            return
        try:
            self._shows = json.loads(data_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            self.var_summary.set(f"读取结果失败：{e}")
            return

        # 分段索引
        seg_file = data_file.parent / "segments_index.json"
        self._segments_by_show: dict[str, list] = {}
        seg_total = 0
        if seg_file.is_file():
            try:
                segs = json.loads(seg_file.read_text(encoding="utf-8"))
                seg_total = len(segs)
                for g in segs:
                    self._segments_by_show.setdefault(str(g.get("show_id")), []).append(g)
            except (OSError, json.JSONDecodeError):
                pass

        # 每段元数据（清晰度/大小）
        meta_file = data_file.parent / "segment_meta.json"
        meta = {}
        if meta_file.is_file():
            try:
                meta = json.loads(meta_file.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                pass
        if self.rtree:
            self.rtree.set_meta(meta)

        # 投稿（author-video）
        posts_file = data_file.parent / "posts_index.json"
        self._posts = []
        if posts_file.is_file():
            try:
                self._posts = json.loads(posts_file.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                self._posts = []
        if self.rtree:
            self.rtree.posts = self._posts

        total = len(self._shows)
        lo, hi, limit = self._range_bounds()
        kw = self.var_kw.get().strip().lower()

        rows = []
        for i, s in enumerate(self._shows):
            d = str(s.get("date") or "")
            if lo and d and d < lo:
                continue
            if hi and d and d > hi:
                continue
            if kw and kw not in str(s.get("title", "")).lower():
                continue
            rows.append((i, s))
            if limit and len(rows) >= limit:
                break

        self._filtered = rows
        self._render_page()

        if seg_total:
            parts = [f"录播 {total} 场 / {seg_total} 段"]
        else:
            parts = [f"录播 {total} 场"]

        if len(rows) != total:
            parts.append(f"筛选出 {len(rows)} 个场次")
        self.var_summary.set(" · ".join(parts))
        self._update_sel_label()

    def _ctype_value(self) -> str:
        """当前内容类型：replay（录播）/ post（投稿）。"""
        label = self.var_ctype.get()
        for v, x in CONTENT_TYPES:
            if x == label:
                return v
        return "replay"

    def _on_ctype_change(self) -> None:
        """切换录播/投稿：重置分页与选择，重新渲染。"""
        self.page = 1
        self.select_state = 0
        if hasattr(self, "btn_select_all"):
            self.btn_select_all.configure(text="全选本页")
        if hasattr(self, "rtree") and self.rtree:
            self.rtree.checked.clear()
        self.apply_filter()

    def _apply_filter_posts(self) -> None:
        """投稿模式：把 posts_index.json 当平铺列表渲染（投稿不分段）。"""
        data_file = self._work_dir() / "data" / "posts_index.json"
        if not data_file.is_file():
            self._filtered = []
            self._shows = []
            self._segments_by_show = {}
            if self.rtree:
                self.rtree.posts = []
                self.rtree.load_page([], {})
            self.var_summary.set("还没有投稿数据，请先点「搜索」")
            self._update_sel_label()
            return
        try:
            posts = json.loads(data_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            self.var_summary.set(f"读取投稿失败：{e}")
            return

        lo, hi, limit = self._range_bounds()
        kw = self.var_kw.get().strip().lower()
        rows = []
        for i, p in enumerate(posts):
            d = str(p.get("date") or "")
            if lo and d and d < lo:
                continue
            if hi and d and d > hi:
                continue
            if kw and kw not in str(p.get("title", "")).lower():
                continue
            rows.append((i, p))
            if limit and len(rows) >= limit:
                break

        # 投稿无分段：每个投稿映射成一个「单段场次」
        shows = []
        segs_by_show = {}
        for idx, p in rows:
            sid = "post-" + str(p.get("hash_id") or idx)
            shows.append({
                "show_id": sid,
                "hash_id": p.get("hash_id"),
                "title": p.get("title") or "",
                "date": p.get("date") or "",
                "time_str": p.get("time_str") or "",
                "segment_count": 1,
                "duration_sec": p.get("duration_sec") or 0,
            })
            segs_by_show[sid] = [{
                "hash_id": p.get("hash_id"),
                "show_id": sid,
                "title": p.get("title") or "",
                "date": p.get("date") or "",
                "time_str": p.get("time_str") or "",
                "duration_sec": p.get("duration_sec") or 0,
                "duration_str": p.get("duration_str") or "",
                "seg_no": 1,
                "seg_total": 1,
                "seg_remark": "",
            }]

        self._shows = shows
        self._segments_by_show = segs_by_show
        self._filtered = list(enumerate(shows))
        if self.rtree:
            self.rtree.posts = []          # 不再用虚拟分组
        self._render_page()
        self.var_summary.set(
            f"投稿 {len(posts)} 个"
            + (f" · 当前显示 {len(rows)} 个" if len(rows) != len(posts) else ""))
        self._update_sel_label()

    def _total_pages(self) -> int:
        n = len(getattr(self, "_filtered", []))
        return max(1, (n + self.page_size - 1) // self.page_size)

    def _render_page(self) -> None:
        rows = getattr(self, "_filtered", [])
        pages = self._total_pages()
        if self.page > pages:
            self.page = pages
        if self.page < 1:
            self.page = 1
        start = (self.page - 1) * self.page_size
        page_rows = rows[start:start + self.page_size]

        page_shows = [s for _, s in page_rows]
        if self.rtree:
            segs = {}
            for s in page_shows:
                segs[str(s.get("show_id"))] = self._segments_by_show.get(
                    str(s.get("show_id")), [])
            self.rtree.load_page(page_shows, segs)
        self.var_page.set(f"{self.page} / {pages}")
        # 先标出哪些分段还没数据（显示「获取中…」），再后台逐条填充
        if self.rtree:
            missing = []
            for s in page_shows:
                for g in self._segments_by_show.get(str(s.get("show_id")), []):
                    hid = str(g.get("hash_id"))
                    m = self.rtree._meta.get(hid) or {}
                    if not m or m.get("error"):
                        missing.append(hid)
            if missing:
                self.rtree.mark_pending(missing)
        self._probe_current_page(page_shows)

    def _probe_current_page(self, page_shows: list[dict]) -> None:
        """后台探测当前页：逐条接收结果并实时更新界面。"""
        if not page_shows:
            return
        if self.probing:
            # 正在探测：记下来，等当前批次结束后再补跑
            self._probe_retry = page_shows
            return
        show_ids = [str(s.get("show_id")) for s in page_shows if s.get("show_id")]
        if not show_ids:
            return
        # 本页若已全部探测过，就不再重复跑
        need = []
        for sid in show_ids:
            for g in self._segments_by_show.get(sid, []):
                hid = str(g.get("hash_id"))
                m = (self.rtree._meta.get(hid) if self.rtree else None) or {}
                if not m or m.get("error"):
                    need.append(hid)
        if not need:
            return
        self.probing = True
        self._probe_seq = getattr(self, "_probe_seq", 0) + 1
        my_seq = self._probe_seq

        def work():
            env = (deps_mod.build_env() if deps_mod else os.environ.copy())
            env["PYTHONIOENCODING"] = "utf-8"
            env["PYTHONUTF8"] = "1"
            node = (deps_mod.node_path(env) if deps_mod
                    else shutil.which("node", path=env.get("PATH")))
            if not node:
                self.probing = False
                return
            script = str(ROOT / "scripts" / "probe_page.mjs")
            try:
                p = subprocess.Popen(
                    [node, script, "--shows", ",".join(show_ids), "--force-time"],
                    cwd=str(ROOT), env=env,
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, encoding="utf-8", errors="replace",
                    creationflags=(subprocess.CREATE_NO_WINDOW) if IS_WINDOWS else 0,
                )
                for line in p.stdout:  # type: ignore[union-attr]
                    line = line.rstrip("\r\n")
                    if line.startswith("META "):
                        try:
                            info = json.loads(line[5:])
                        except json.JSONDecodeError:
                            self.log_queue.put(("out", f"[跳过无法解析的探测结果] {line[:60]}"))
                            continue
                        # 若已翻页则丢弃过时结果
                        if my_seq == self._probe_seq:
                            self.log_queue.put(("meta", json.dumps(info, ensure_ascii=False)))
                    elif line.strip():
                        self.log_queue.put(("out", line))
                p.wait()
            except Exception as e:  # noqa: BLE001
                self.log_queue.put(("err", f"探测失败: {e}"))
            finally:
                self.probing = False
                if my_seq == self._probe_seq:
                    self.log_queue.put(("meta_done", ""))
                # 有排队的请求就接着跑
                pending = getattr(self, "_probe_retry", None)
                if pending:
                    self._probe_retry = None
                    self.after(200, lambda: self._probe_current_page(pending))

        threading.Thread(target=work, daemon=True).start()

    def _ensure_page_probed(self) -> None:
        """检查当前页是否还有未探测的分段，有就补跑。"""
        if not self.rtree:
            return
        rows = getattr(self, "_filtered", [])
        start = (self.page - 1) * self.page_size
        page_shows = [s for _, s in rows[start:start + self.page_size]]
        missing = []
        for s in page_shows:
            for g in self._segments_by_show.get(str(s.get("show_id")), []):
                hid = str(g.get("hash_id"))
                m = self.rtree._meta.get(hid) or {}
                if not m or m.get("error"):
                    missing.append(hid)
        if missing and not self.probing:
            self._probe_current_page(page_shows)

    def _reload_meta_and_render(self) -> None:
        """只重读 segment_meta.json 并重绘当前页（不重新筛选）。"""
        meta_file = self._work_dir() / "data" / "segment_meta.json"
        meta = {}
        if meta_file.is_file():
            try:
                meta = json.loads(meta_file.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                pass
        if self.rtree:
            # 用磁盘上的完整结果覆盖，避免只拿到部分流式结果
            self.rtree._meta = dict(meta)
            self.rtree._pending.clear()
        rows = getattr(self, "_filtered", [])
        start = (self.page - 1) * self.page_size
        page_shows = [s for _, s in rows[start:start + self.page_size]]
        if self.rtree and page_shows:
            segs = {str(s.get("show_id")): self._segments_by_show.get(
                str(s.get("show_id")), []) for s in page_shows}
            self.rtree.load_page(page_shows, segs)
        self._update_sel_label()

    def next_page(self) -> None:
        if self.page < self._total_pages():
            self.page += 1
            self._render_page()

    def prev_page(self) -> None:
        if self.page > 1:
            self.page -= 1
            self._render_page()

    def cycle_select_all(self) -> None:
        """全选按钮三态：本页全选 → 全部页全选 → 取消全选。"""
        if not self.rtree:
            return
        rows = getattr(self, "_filtered", [])
        page_hashes = []
        start = (self.page - 1) * self.page_size
        for _, s in rows[start:start + self.page_size]:
            for g in self._segments_by_show.get(str(s.get("show_id")), []):
                page_hashes.append(str(g.get("hash_id")))
        all_hashes = []
        for _, s in rows:
            for g in self._segments_by_show.get(str(s.get("show_id")), []):
                all_hashes.append(str(g.get("hash_id")))

        if self.select_state == 0:
            self.rtree.set_add(page_hashes, True)
            self.select_state = 1
            self.btn_select_all.configure(text="全选所有页")
        elif self.select_state == 1:
            self.rtree.set_add(all_hashes, True)
            self.select_state = 2
            self.btn_select_all.configure(text="取消全选")
        else:
            self.rtree.set_add(all_hashes, False)
            self.select_state = 0
            self.btn_select_all.configure(text="全选本页")
        self._update_sel_label()

    def check_all(self) -> None:
        """兼容旧调用。"""
        if self.select_state != 2:
            self.cycle_select_all()

    def uncheck_all(self) -> None:
        if self.rtree:
            self.rtree.set_add(list(self.rtree.checked), False)
        self.select_state = 0
        self.btn_select_all.configure(text="全选本页")
        self._update_sel_label()

    def _on_tree_select(self) -> None:
        self._update_sel_label()

    def _on_tree_click(self, event) -> None:
        if self.rtree:
            self.rtree._on_click(event)

    def _update_sel_label(self) -> None:
        if not self.rtree:
            return
        n = len(self.rtree.checked)
        if n == 0:
            self.var_sel.set("未选择")
            return
        size = self.rtree.selected_size()
        if size:
            self.var_sel.set(f"已选 {n} 个分段 · 预计 {size / 1024 ** 3:.1f} GB")
        else:
            self.var_sel.set(f"已选 {n} 个分段")

    def _selected_hashes(self) -> list[str]:
        return self.rtree.selected() if self.rtree else []

    def download_selected(self) -> None:
        """下载选中的分段：先补 point_id，再按分段下载。"""
        hashes = self._selected_hashes()
        if hashes and hasattr(self, "rtree") and self.rtree:
            self.rtree.set_downloading(hashes)
            # 立刻在「下载管理」里显示这几条为「下载中」
            self._queue_to_download_panel(hashes)
        if not hashes:
            messagebox.showinfo("还没选分段",
                                "请在搜索结果里勾选场次或展开后勾选具体分段。")
            return
        if not self._ensure_ready():
            return
        self._write_only_file(hashes)
        self.nb.select(self.tab_home)

        # 下载前确保这些分段有 point_id（probe_page 会顺手补）
        shows = sorted({str(g.get("show_id")) for g in self._all_segments()
                        if str(g.get("hash_id")) in set(hashes)})
        prep_argv = ([str(ROOT / "scripts" / "probe_page.mjs"), "--shows", ",".join(shows)]
                     if shows else [])
        if prep_argv:
            self._run_cli_node(
                prep_argv,
                f"准备 {len(hashes)} 个分段（补全取流参数）",
                on_done=lambda: self._run_cli(
                    ["download", "--only", str(self._only_file())],
                    f"下载 {len(hashes)} 个分段",
                    on_done=self._after_download_transcode),
            )
        else:
            self._run_cli(["download", "--only", str(self._only_file())],
                          f"下载 {len(hashes)} 个分段",
                          on_done=self._after_state_changed)

    def _queue_to_download_panel(self, hashes) -> None:
        """把刚提交的分段立刻显示在「下载管理」列表里（状态=下载中）。"""
        if not hasattr(self, "tree_hist"):
            return
        seg_map = {str(g.get("hash_id")): g for g in self._all_segments()}
        # 清掉上一批的临时任务行
        for iid in list(self.tree_hist.get_children()):
            if "queued" in self.tree_hist.item(iid, "tags"):
                self.tree_hist.delete(iid)
        import datetime as _dt
        now = _dt.datetime.now().strftime("%m-%d %H:%M")
        for h in hashes:
            g = seg_map.get(str(h)) or {}
            meta = (self.rtree._meta.get(str(h)) if getattr(self, "rtree", None) else {}) or {}
            size = int(meta.get("est_size") or 0)
            air = str(g.get("time_str") or "")
            if len(air) >= 16:
                air = air[:16].replace(":", "-", 1).replace("-", "-", 0)
                air = str(g.get("time_str"))[:16]
            self.tree_hist.insert(
                "", 0, iid=f"q:{h}", tags=["queued"],
                values=(now, air or "-",
                        self._short_dl_title(str(g.get("title") or h)),
                        f"{size / 1024 ** 2:.0f} MB" if size else "-",
                        "准备中…", "下载中"))
        if hasattr(self, "var_dl_status"):
            self.var_dl_status.set(f"下载中 {len(hashes)} 个")

    def _all_segments(self) -> list[dict]:
        out = []
        for lst in self._segments_by_show.values():
            out.extend(lst)
        return out

    def _run_cli_node(self, argv: list[str], label: str, on_done=None) -> None:
        """直接跑 node 脚本。"""
        if self.running:
            messagebox.showinfo("正在运行", "已有任务在执行，请等待完成。")
            return
        self.save_all(silent=True)
        self._log("cmd", f"\n▶ {label}")
        self._set_running(True)

        def work():
            env = (deps_mod.build_env() if deps_mod else os.environ.copy())
            env["PYTHONIOENCODING"] = "utf-8"
            env["PYTHONUTF8"] = "1"
            node = (deps_mod.node_path(env) if deps_mod
                    else shutil.which("node", path=env.get("PATH")))
            if not node:
                self.log_queue.put(("err", "✘ 找不到 node"))
                self.log_queue.put(("done", "1"))
                return
            try:
                p = subprocess.Popen(
                    [node, *argv], cwd=str(ROOT), env=env,
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, encoding="utf-8", errors="replace",
                    creationflags=(subprocess.CREATE_NO_WINDOW |
                                   subprocess.CREATE_NEW_PROCESS_GROUP) if IS_WINDOWS else 0,
                )
                with self.proc_lock:
                    self.proc = p
                for line in p.stdout:  # type: ignore[union-attr]
                    line = line.rstrip("\r\n")
                    self.log_queue.put(("out", line))
                    self._append_log_file(line)
                rc = p.wait()
                self.log_queue.put(("done", str(rc)))
                if rc == 0 and on_done:
                    self.after(400, on_done)
            except Exception as e:  # noqa: BLE001
                self.log_queue.put(("err", f"✘ 启动失败: {e}"))
                self.log_queue.put(("done", "1"))

        threading.Thread(target=work, daemon=True).start()

    def _run_cli_py(self, argv: list[str], label: str, on_done=None) -> None:
        """直接跑 Python 脚本（用于 list_shows 等非 CLI 命令）。"""
        if self.running:
            messagebox.showinfo("正在运行", "已有任务在执行，请等待完成。")
            return
        self.save_all(silent=True)
        self._log("cmd", f"\n▶ {label}")
        self._set_running(True)

        def work():
            env = (deps_mod.build_env() if deps_mod else os.environ.copy())
            env["PYTHONIOENCODING"] = "utf-8"
            env["PYTHONUTF8"] = "1"
            py = (env.get("DOUYU_PY") or sys.executable)
            # 只有 DOUYU_PY 指向打包后的 douyulubo.exe 时才加 --run-py；
            # 指向 python.exe 时必须直接跑脚本（否则 python 不认识 --run-py）。
            # 注意 py 可能是完整路径，不能用 startswith 判断，要取文件名。
            _base = Path(str(py)).name.lower()
            use_runpy = _base not in ("python.exe", "python3.exe", "pythonw.exe",
                                      "python", "python3", "pythonw")
            cmd = ([py, "--run-py", *argv] if use_runpy else [py, *argv])
            try:
                p = subprocess.Popen(
                    cmd, cwd=str(ROOT), env=env,
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, encoding="utf-8", errors="replace",
                    creationflags=(subprocess.CREATE_NO_WINDOW |
                                   subprocess.CREATE_NEW_PROCESS_GROUP) if IS_WINDOWS else 0,
                )
                with self.proc_lock:
                    self.proc = p
                for line in p.stdout:  # type: ignore[union-attr]
                    line = line.rstrip("\r\n")
                    self.log_queue.put(("out", line))
                    self._append_log_file(line)
                rc = p.wait()
                self.log_queue.put(("done", str(rc)))
                if rc == 0 and on_done:
                    self.after(600, on_done)
            except Exception as e:  # noqa: BLE001
                self.log_queue.put(("err", f"✘ 启动失败: {e}"))
                self.log_queue.put(("done", "1"))

        threading.Thread(target=work, daemon=True).start()

    def download_all_filtered(self) -> None:
        """下载当前筛选结果里的全部分段。"""
        rows = getattr(self, "_filtered", [])
        if not rows:
            messagebox.showinfo("没有结果", "当前筛选结果为空，请先搜索。")
            return
        hashes = []
        for _, s in rows:
            for g in self._segments_by_show.get(str(s.get("show_id")), []):
                if g.get("hash_id"):
                    hashes.append(str(g["hash_id"]))
        if not hashes:
            messagebox.showinfo("没有分段", "当前结果里没有可下载的分段。")
            return
        if not messagebox.askyesno("确认", f"要下载当前筛选出的 {len(hashes)} 个分段吗？"):
            return
        if not self._ensure_ready():
            return
        self._write_only_file(hashes)
        self.nb.select(self.tab_home)
        py_script = ROOT / "scripts" / "list_shows.py"
        self._run_cli_py(
            [str(py_script), "--pid-only", *hashes],
            f"准备 {len(hashes)} 个分段",
            on_done=lambda: self._run_cli(
                ["download", "--only", str(self._only_file())],
                f"下载 {len(hashes)} 个分段",
                on_done=self._after_download_transcode),
        )

    def _only_file(self) -> Path:
        return self._work_dir() / "data" / "selected_hashes.json"

    def _write_only_file(self, hashes: list[str]) -> None:
        p = self._only_file()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(hashes, ensure_ascii=False), encoding="utf-8")

    def task_fetch(self) -> None:
        if not self._ensure_ready():
            return
        self._run_cli(["fetch"], "抓取完整清单", on_done=self._after_state_changed)

    def task_detail(self) -> None:
        if not self._ensure_ready():
            return
        self._run_cli(["detail"], "获取详细信息", on_done=self._after_state_changed)

    def task_download(self) -> None:
        if not self._ensure_ready():
            return
        only = self._only_file()
        if only.is_file():
            hashes = json.loads(only.read_text(encoding="utf-8"))
            if hashes:
                self._run_cli(["detail", "--only", str(only)], "更新选中项详情",
                              on_done=lambda: self._run_cli(["download"],
                                                            f"下载 {len(hashes)} 个录播",
                                                            on_done=self._after_state_changed))
                return
        self._run_cli(["download"], "开始下载", on_done=self._after_state_changed)

    def task_danmaku(self) -> None:
        if not self._ensure_ready():
            return
        mode = self._danmaku_value()
        if mode == "none":
            messagebox.showinfo("已设置为不下载弹幕",
                                "「弹幕」页当前选择的是「不下载弹幕」。")
            return
        self.save_all(silent=True)
        ass_args = ["ass"]
        self._run_cli(["danmaku"], "下载弹幕",
                      on_done=(lambda: self._run_cli(ass_args, "转换为 ASS")) if mode == "ass" else None)

    def task_probe(self) -> None:
        if not self._ensure_ready():
            return
        self._run_cli(["probe"], "核查画质与体积")

    def task_run_all(self) -> None:
        """一键全流程：有勾选就只跑勾选的，否则跑全部。"""
        if not self._ensure_ready():
            return
        hashes = self._selected_hashes()
        self.save_all(silent=True)
        if hashes:
            self._write_only_file(hashes)
            self._log("info", f"一键全流程：只处理勾选的 {len(hashes)} 个录播")
            self._run_cli(["detail", "--only", str(self._only_file())], "获取详细信息",
                          on_done=lambda: self._run_cli(["run"], "一键全流程",
                                                        on_done=self._after_state_changed))
        else:
            self._log("info", "一键全流程：处理当前筛选出的全部录播")
            self._run_cli(["run"], "一键全流程", on_done=self._after_state_changed)

    def _work_dir(self) -> Path:
        """工作目录：配置里没填就用程序目录下的 downloads。"""
        wd = self.cfg_vars.get("work_dir") if hasattr(self, "cfg_vars") else None
        raw = (wd.get().strip() if wd else "") or str(load_config().get("work_dir", "") or "")
        if not raw:
            return ROOT / "downloads"
        p = Path(raw).expanduser()
        return p if p.is_absolute() else (ROOT / p).resolve()

    def _history_dir(self) -> Path:
        return self._work_dir() / "data" / "history"

    def _history_hashes(self) -> set[str]:
        d = self._history_dir()
        if not d.is_dir():
            return set()
        return {p.stem for p in d.glob("*.json")}

    @staticmethod
    def _short_dl_title(title: str) -> str:
        """下载历史标题：去掉场次前缀与尾部时间，只留简短内容。"""
        s = str(title or "")
        if "：" in s:                      # 【...】某主播：xxx -> xxx
            s = s.split("：", 1)[1]
        # 去掉尾部的 " 2020-02-02 20点场"
        s = re.sub(r"\s*\d{4}-\d{2}-\d{2}\s*\d{1,2}点场\s*$", "", s)
        return s[:22] + ("…" if len(s) > 22 else "")

    def _history_records(self) -> list[dict]:
        """读取全部下载历史记录（按完成时间倒序）。"""
        d = self._history_dir()
        recs: list[dict] = []
        if d.is_dir():
            for p in d.glob("*.json"):
                try:
                    recs.append(json.loads(p.read_text(encoding="utf-8")))
                except (OSError, json.JSONDecodeError):
                    continue
        recs.sort(key=lambda r: str(r.get("finished_at", "")), reverse=True)
        return recs

    def _air_time_of(self, hid: str) -> str:
        """按 hash 查这个分段的录播时间（YYYY-MM-DD HH:MM）。"""
        if not hid:
            return ""
        try:
            for g in self._all_segments():
                if str(g.get("hash_id")) == hid:
                    return str(g.get("time_str") or "")[:16]
        except (AttributeError, TypeError):
            pass
        return ""

    def refresh_history(self) -> None:
        if not hasattr(self, "tree_hist"):
            return
        for i in self.tree_hist.get_children():
            self.tree_hist.delete(i)
        recs = self._history_records()
        total = sum(int(r.get("size", 0) or 0) for r in recs)
        if hasattr(self, "var_dl_status"):
            self.var_dl_status.set(f"已完成 {len(recs)} 个 · {total / 1024 ** 3:.2f} GB")
        for n, r in enumerate(recs):
            f = str(r.get("file", ""))
            ok = bool(f) and Path(f).is_file()
            tags = ["even" if n % 2 else "odd"]
            tags.append("done" if ok else "missing")
            size = int(r.get("size", 0) or 0)
            air = str(r.get("air_time") or "").strip()
            if not air:
                air = self._air_time_of(str(r.get("hash") or r.get("hash_id") or ""))
            self.tree_hist.insert("", "end", tags=tags, values=(
                str(r.get("finished_at", ""))[5:16].replace("T", " "),
                air or "-",
                self._short_dl_title(str(r.get("title", ""))),
                f"{size / 1024 ** 2:.0f} MB" if size else "-",
                "",
                "已完成" if ok else "缺失",
            ))
        # 把下载历史里的 hash 同步到结果表「状态」列
        if hasattr(self, "rtree") and self.rtree:
            done = {str(r.get("hash") or r.get("hash_id") or "") for r in recs} - {""}
            self.rtree.set_downloaded(done)
        if hasattr(self, "var_dl_status"):
            self.var_dl_status.set(f"已完成 {len(recs)} 个")

    def _on_hist_double(self, _evt) -> None:
        if not hasattr(self, "tree_hist"):
            return
        sel = self.tree_hist.selection()
        if not sel:
            return
        title = self.tree_hist.item(sel[0], "values")[1]
        d = self._history_dir()
        if not d.is_dir():
            return
        for p in d.glob("*.json"):
            try:
                rec = json.loads(p.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if str(rec.get("title", ""))[:80] == title:
                fp = Path(str(rec.get("file", "")))
                if fp.is_file():
                    self._open_path(fp.parent)
                return

    def clear_history(self) -> None:
        d = self._history_dir()
        n = len(list(d.glob("*.json"))) if d.is_dir() else 0
        if n == 0:
            messagebox.showinfo("提示", "没有下载记录。")
            return
        if not messagebox.askyesno("确认", f"清除 {n} 条下载记录？\n（只删记录，不删视频文件）"):
            return
        for p in d.glob("*.json"):
            try:
                p.unlink()
            except OSError:
                pass
        self.refresh_history()
        self._log("ok", f"已清除 {n} 条下载记录")

    def open_download_dir(self) -> None:
        d = self._work_dir() / "downloads"
        d.mkdir(parents=True, exist_ok=True)
        self._open_path(d)

    def open_log_dir(self) -> None:
        d = self._log_dir()
        d.mkdir(parents=True, exist_ok=True)
        self._open_path(d)

    def _log_dir(self) -> Path:
        return self._work_dir() / "logs"

    def _log_file(self) -> Path:
        return self._log_dir() / "douyulubo.log"

    def clear_log_file(self) -> None:
        f = self._log_file()
        if not f.is_file():
            messagebox.showinfo("提示", "还没有日志文件。")
            return
        if not messagebox.askyesno("确认", f"清空日志文件？\n{f}"):
            return
        try:
            f.write_text("", encoding="utf-8")
            self._log("ok", "日志文件已清空")
        except OSError as e:
            messagebox.showerror("失败", str(e))

    # ================= 配置读写 =================
    def _load_state(self) -> None:
        """从 config.json 恢复全部控件状态；缺省时必须有默认值。"""
        cfg = load_config()
        if cfg.get("up_id"):
            self.var_upid.set(str(cfg["up_id"]))
            self._refresh_anchor_name()

        # 清晰度：一定有一个选中项（找不到就回到第一项）
        q = str(cfg.get("quality") or "highest")
        label = next((t for v, t in QUALITY_CHOICES if v == q), None)
        self.cmb_quality.set(label or QUALITY_CHOICES[0][1])

        # 弹幕方式：同理
        dm = str(cfg.get("danmaku_mode") or "ass")
        label = next((t for v, t in DANMAKU_CHOICES if v == dm), None)
        self.cmb_danmaku.set(label or DANMAKU_CHOICES[0][1])

        # 时间范围：恢复上次选择，非法值回落「最近 24 小时」
        rng = str(cfg.get("date_range") or LATEST_PRESETS[0][1])
        valid = {t for _, t in LATEST_PRESETS}
        self.var_range.set(rng if rng in valid else LATEST_PRESETS[0][1])
        self.var_from.set(str(cfg.get("date_from") or ""))
        self.var_to.set(str(cfg.get("date_to") or ""))
        if self.var_range.get() == LATEST_PRESETS[-1][1]:
            if not self.frm_custom.winfo_ismapped():
                self.frm_custom.pack(side="left", padx=(8, 0))
            today = datetime.now()
            if not self.var_from.get():
                self.var_from.set((today - timedelta(days=7)).strftime("%Y-%m-%d"))
            if not self.var_to.get():
                self.var_to.set(today.strftime("%Y-%m-%d"))
        else:
            self.frm_custom.pack_forget()
        if hasattr(self, "var_tc_codec"):
            self.var_tc_enabled.set(bool(cfg.get("transcode_enabled", False)))
            _c = str(cfg.get("transcode_codec") or "h265")
            for _v, _x in TRANSCODE_CODECS:
                if _v == _c:
                    self.var_tc_codec.set(_x)
                    break
            _q = str(cfg.get("transcode_quality") or "balanced")
            for _v, _x in TRANSCODE_QUALITIES:
                if _v == _q:
                    self.var_tc_quality.set(_x)
                    break
            self.var_tc_preset.set(str(cfg.get("transcode_preset", 5)))
            self.var_tc_delete.set(bool(cfg.get("transcode_delete_src", False)))
            self.var_tc_audio.set(bool(cfg.get("transcode_audio_encode", False)))
            if hasattr(self, "var_tc_suffix"):
                self.var_tc_suffix.set(str(cfg.get("transcode_suffix") or ""))
            self._on_tc_codec_change()

        self.var_kw.set(str(cfg.get("keyword") or ""))

        self._set_spin(self.var_concurrent, cfg.get("concurrent", 2))
        self._set_spin(self.var_min_mb, cfg.get("min_file_mb", 100))
        self.var_skip_done.set(bool(cfg.get("skip_downloaded", True)))
        self._set_spin(self.var_font_size, cfg.get("font_size", 50))
        self._set_spin(self.var_scroll, cfg.get("scroll_duration", 8))
        self._set_spin(self.var_fixed, cfg.get("fixed_duration", 4.5))
        self._set_spin(self.var_line_sp, cfg.get("line_spacing", 0))
        self._set_spin(self.var_top_m, cfg.get("top_margin", 0))
        self._set_spin(self.var_bottom_m, cfg.get("bottom_margin", 0))
        self._set_spin(self.var_opacity, cfg.get("opacity", 255))
        fn = str(cfg.get("font_name") or "").strip()
        if fn in ("", "Microsoft YaHei"):
            fn = "微软雅黑"
        self.var_font_name.set(fn)
        self.var_bold.set(bool(cfg.get("bold", False)))
        self.var_outline.set(str(cfg.get("outline", 1.0)))
        self.var_shadow.set(str(cfg.get("shadow", 0.0)))
        self.var_time_shift.set(str(cfg.get("time_shift", 0.0)))
        self.var_no_overlap.set(bool(cfg.get("no_overlap", True)))


        blocks = set(cfg.get("block_types") or [])
        for k, v in self.block_vars.items():
            v.set(k in blocks)

        for k, v in self.cfg_vars.items():
            v.set(str(cfg.get(k, "") if cfg.get(k) is not None else ""))

        if hasattr(self, "detect_components"):
            self.detect_components()

        self._update_log_hint()
        self.refresh_history()
        self.check_env()
        self.apply_filter()

    @staticmethod
    def _set_spin(var: tk.StringVar, value) -> None:
        var.set(str(value))

    def save_all(self, silent: bool = False) -> None:
        cfg = load_config()
        cfg["quality"] = self._quality_value()
        if hasattr(self, "var_tc_codec"):
            o = self._tc_opts()
            cfg["transcode_enabled"] = bool(self.var_tc_enabled.get())
            cfg["transcode_codec"] = o["codec"]
            cfg["transcode_quality"] = o["quality"]
            cfg["transcode_preset"] = o["preset"]
            cfg["transcode_delete_src"] = o["delete"]
            cfg["transcode_audio_encode"] = o["audio_encode"]
            cfg["transcode_suffix"] = o["suffix"]
        cfg["danmaku_mode"] = self._danmaku_value()
        cfg["skip_downloaded"] = bool(self.var_skip_done.get())
        # 搜索条件也记住，下次打开保持上次的选择
        cfg["date_range"] = self.var_range.get()
        cfg["date_from"] = self.var_from.get().strip()
        cfg["date_to"] = self.var_to.get().strip()
        cfg["keyword"] = self.var_kw.get().strip()
        # 弹幕排版
        cfg["font_name"] = self.var_font_name.get().strip() or "Microsoft YaHei"
        cfg["bold"] = bool(self.var_bold.get())
        cfg["no_overlap"] = bool(self.var_no_overlap.get())

        for key, var, cast in (
            ("concurrent", self.var_concurrent, int),
            ("min_file_mb", self.var_min_mb, int),
            ("font_size", self.var_font_size, int),
            ("scroll_duration", self.var_scroll, float),
            ("fixed_duration", self.var_fixed, float),
            ("line_spacing", self.var_line_sp, int),
            ("top_margin", self.var_top_m, int),
            ("bottom_margin", self.var_bottom_m, int),
            ("opacity", self.var_opacity, int),
            ("outline", self.var_outline, float),
            ("shadow", self.var_shadow, float),
            ("time_shift", self.var_time_shift, float),
        ):
            try:
                cfg[key] = cast(var.get())
            except (TypeError, ValueError):
                cfg[key] = cfg.get(key)
        cfg["block_types"] = [k for k, v in self.block_vars.items() if v.get()]
        for k, v in self.cfg_vars.items():
            cfg[k] = v.get().strip()
        self._save_components(cfg)

        save_config(cfg)
        if not silent:
            self._log("ok", "设置已保存")
            messagebox.showinfo("已保存", "全部设置已保存。")
        self._update_log_hint()

    def reload_all(self) -> None:
        self._load_state()
        self._log("info", "已重新读取配置")

    def reset_all(self) -> None:
        if not messagebox.askyesno("确认", "恢复默认设置？\n（主播 ID 与工作目录会保留）"):
            return
        cfg = load_config()
        keep = {k: cfg.get(k) for k in ("up_id", "work_dir") if cfg.get(k)}
        cfg = dict(keep)
        cfg.update({
            "quality": "highest", "danmaku_mode": "ass", "concurrent": 2,
            "min_file_mb": 100, "font_size": 50, "scroll_duration": 8,
            "fixed_duration": 4.5, "line_spacing": 0, "top_margin": 0,
            "bottom_margin": 0, "opacity": 255, "block_types": [],
        })
        save_config(cfg)
        self._load_state()
        self._log("ok", "已恢复默认设置")

    def pick_path(self, key: str) -> None:
        if key == "work_dir":
            p = filedialog.askdirectory(title="选择工作目录")
        else:
            p = filedialog.askopenfilename(title="选择可执行文件")
        if p:
            self.cfg_vars[key].set(p)
            self.save_all(silent=True)

    def pick_exe(self, key: str, exe_name: str) -> None:
        p = filedialog.askopenfilename(
            title="选择可执行文件",
            filetypes=[(f"{exe_name}", exe_name), ("所有文件", "*.*")])
        if p:
            self._comp_var_map[key].set(p)
            self.save_all(silent=True)
            self.detect_components()

    def clear_comp_paths(self) -> None:
        for v in self._comp_var_map.values():
            v.set("")
        self.save_all(silent=True)
        self.detect_components()
        self._log("info", "已清空手动指定的组件路径，改为自动检测")

    def _on_comp_edit(self, entry: ttk.Entry, var: tk.StringVar) -> None:
        """用户改了组件路径就把它显示成黑色（表示是手动指定的）。"""
        if not theme:
            return
        val = var.get().strip()
        auto = getattr(self, "_auto_paths", {}).get(entry, "")
        color = theme.MUTED if (not val or val == auto) else theme.TEXT
        try:
            entry.configure(foreground=color)
        except tk.TclError:
            pass

    def detect_components(self) -> None:
        """把检测到的路径填进输入框（灰色=自动）；用户手动值保持黑色。"""
        if deps_mod is None:
            for st in self.comp_status.values():
                st.set("—")
            return
        resolved = deps_mod.resolve_all()
        key_of = {"node": "node_path", "python": "python_path", "ffmpeg": "ffmpeg"}
        self._auto_paths = getattr(self, "_auto_paths", {})
        cfg = load_config()

        for dep, st in self.comp_status.items():
            r = resolved.get(dep)
            ok = bool(r and r.ok)
            st.set("✔" if ok else "✘")
            lbl = getattr(self, "comp_status_label", {}).get(dep)
            if lbl and theme:
                lbl.configure(foreground=theme.SUCCESS if ok else theme.DANGER)

            key = key_of.get(dep)
            ent = self.comp_entries.get(key) if hasattr(self, "comp_entries") else None
            if not ent:
                continue
            manual = str(cfg.get(key, "") or "").strip()
            shown = manual or (r.path if ok else "")
            self._auto_paths[ent] = (r.path if ok else "")
            var = self._comp_var_map.get(key)
            if var is not None:
                var.set(shown)
            if theme:
                ent.configure(foreground=theme.TEXT if manual else theme.MUTED)
        self.check_env()

    def _save_components(self, cfg: dict) -> None:
        """只保存"用户手动指定"的路径；等于自动检测值的不存，保持自动。"""
        auto = getattr(self, "_auto_paths", {})
        for key, var in getattr(self, "_comp_var_map", {}).items():
            val = var.get().strip()
            ent = self.comp_entries.get(key) if hasattr(self, "comp_entries") else None
            auto_val = auto.get(ent, "") if ent else ""
            if val and val != auto_val:
                cfg[key] = val
            else:
                cfg.pop(key, None)

    def _quality_value(self) -> str:
        label = self.var_quality.get()
        for v, t in QUALITY_CHOICES:
            if t == label:
                return v
        return "highest"

    def _danmaku_value(self) -> str:
        label = self.var_danmaku.get()
        for v, t in DANMAKU_CHOICES:
            if t == label:
                return v
        return "ass"

    def detect_qualities(self) -> None:
        p = self._work_dir() / "data" / "quality_results.json"
        if not p.is_file():
            messagebox.showinfo("还没有清晰度数据",
                                "需要先执行一次「核查画质与体积」（只读信息，不下载视频），\n"
                                "完成后再点本按钮即可看到实际可选的清晰度。")
            return
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            messagebox.showerror("读取失败", str(e))
            return
        names = {}
        recs = data.values() if isinstance(data, dict) else data
        for rec in recs:
            for o in (rec.get("options") or []):
                nm = str(o.get("name") or "").strip()
                if nm:
                    names[nm] = o.get("bit_rate")
        if not names:
            messagebox.showinfo("没有可用档位", "探测结果里没有画质信息。")
            return
        extra = [f"{n}（{r} kbps）" if r else n
                 for n, r in sorted(names.items(), key=lambda kv: -(kv[1] or 0))]
        self.cmb_quality.configure(values=[t for _, t in QUALITY_CHOICES] + extra)
        self._log("ok", "已更新可用清晰度：" + "、".join(names))

    def check_env(self) -> None:
        """组件状态已合并到配置页表格里，这里只更新每行的状态文本与日志。"""
        if deps_mod is None:
            for st in getattr(self, "comp_status", {}).values():
                st.set("无法检测")
            return
        resolved = deps_mod.resolve_all()
        src_label = {"bundle": "包内", "path": "PATH",
                     "common": "常见位置", "config": "手动指定"}
        missing = []
        for dep, st in getattr(self, "comp_status", {}).items():
            r = resolved.get(dep)
            if r and r.ok:
                st.set("✔")
            else:
                st.set("✘")
                missing.append(dep)
        signature = ",".join(missing)
        if signature != getattr(self, "_env_sig", None):
            self._env_sig = signature
            if missing:
                self._log("err", "组件缺失：" + "、".join(missing))
            else:
                self._log("ok", "全部组件就绪")

    def _update_log_hint(self) -> None:
        if hasattr(self, "var_log_hint"):
            self.var_log_hint.set(f"运行信息（同时写入：{self._log_file()}）")
        if hasattr(self, "var_log_path"):
            self.var_log_path.set(
                f"运行日志会实时显示在窗口底部的面板里，方便随时查看进度与报错。\n"
                f"日志文件位置：{self._log_file()}\n"
                f"（如果日志文件不存在，说明本次还没有产生可写入的日志；运行任务后会自动创建。）")

    # ================= 任务执行 =================
    def _ensure_ready(self) -> bool:
        cfg = load_config()
        if not cfg.get("up_id"):
            messagebox.showwarning("还没识别主播",
                                   "请在顶部粘贴主播链接，然后点「搜索录播」。")
            self.nb.select(self.tab_home)
            return False
        # 工作目录有默认值（程序目录/downloads），不再强制要求填写
        return True

    def task_convert_xml(self) -> None:
        """手动把已下载的 XML 弹幕批量转成 ASS（独立于下载流程）。"""
        if self.running:
            messagebox.showinfo("正在运行", "已有任务在执行，请稍候。")
            return
        wd = self._work_dir()
        if not (wd / "danmaku").is_dir():
            messagebox.showinfo(
                "还没有弹幕文件",
                f"{wd / 'danmaku'} 下没有找到 XML 弹幕。\n\n"
                "请先下载录播（下载时会自动抓取弹幕），或用「下载」页的弹幕功能。")
            return
        self.save_all(silent=True)
        self._run_cli(["ass"], "转换 XML 弹幕为 ASS", on_done=self._after_state_changed)

    def _run_cli(self, args: list[str], label: str, on_done=None) -> None:
        if self.running:
            messagebox.showinfo("正在运行", "已有任务在执行，请等待完成或先停止。")
            return
        self.save_all(silent=True)
        self._log("cmd", f"\n▶ {label}")
        self._set_running(True)

        def work():
            env = (deps_mod.build_env() if deps_mod else os.environ.copy())
            # 统一 UTF-8，避免中文输出在管道里变乱码
            env["PYTHONIOENCODING"] = "utf-8"
            env["PYTHONUTF8"] = "1"
            if deps_mod is None and getattr(sys, "frozen", False):
                env["DOUYU_PY"] = str(Path(sys.executable).resolve())
            node = (deps_mod.node_path(env) if deps_mod
                    else shutil.which("node", path=env.get("PATH")))
            if not node:
                self.log_queue.put(("err", "✘ 找不到 node，请安装 Node.js 或放进 bin 文件夹"))
                self.log_queue.put(("err", "  https://nodejs.org/zh-cn/download"))
                self.log_queue.put(("err", "  也可在「配置」页手动指定 node.exe 路径"))
                self.log_queue.put(("done", "1"))
                return
            try:
                p = subprocess.Popen(
                    [node, str(CLI), *args], cwd=str(ROOT), env=env,
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, encoding="utf-8", errors="replace",
                    creationflags=(subprocess.CREATE_NO_WINDOW |
                                    subprocess.CREATE_NEW_PROCESS_GROUP) if IS_WINDOWS else 0,
                )
                with self.proc_lock:
                    self.proc = p
                for line in p.stdout:  # type: ignore[union-attr]
                    line = line.rstrip("\r\n")
                    self.log_queue.put(("out", line))
                    self._append_log_file(line)
                rc = p.wait()
                self.log_queue.put(("done", str(rc)))
                if rc == 0 and on_done:
                    self.after(600, on_done)
            except Exception as e:  # noqa: BLE001
                self.log_queue.put(("err", f"✘ 启动失败: {e}"))
                self.log_queue.put(("done", "1"))

        threading.Thread(target=work, daemon=True).start()

    def _append_log_file(self, line: str) -> None:
        """把输出同时写到日志文件（失败忽略，不影响主流程）。"""
        try:
            d = self._log_dir()
            d.mkdir(parents=True, exist_ok=True)
            with (d / "douyulubo.log").open("a", encoding="utf-8") as f:
                f.write(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {line}\n")
        except OSError:
            pass

    def _after_state_changed(self) -> None:
        self.refresh_history()
        self.apply_filter()
        self._refresh_anchor_name()
        # 若搜索产生了结果，自动切到搜索页让用户看到
        if getattr(self, "_filtered", None):
            self.nb.select(self.tab_home)

    def stop_proc(self) -> None:
        with self.proc_lock:
            p = self.proc
        if not p:
            return
        self._log("err", "正在停止任务…")
        try:
            if IS_WINDOWS:
                subprocess.run(["taskkill", "/PID", str(p.pid), "/T", "/F"],
                               capture_output=True, text=True, timeout=10,
                               creationflags=subprocess.CREATE_NO_WINDOW if IS_WINDOWS else 0)
            else:
                p.terminate()
        except Exception as e:  # noqa: BLE001
            self._log("err", f"停止失败: {e}")

    def _set_running(self, on: bool) -> None:
        self.running = on

    # ================= 日志 =================
    def _log(self, tag: str, msg: str) -> None:
        self.log_queue.put((tag, msg))

    def _poll_log(self) -> None:
        try:
            while True:
                tag, msg = self.log_queue.get_nowait()
                if tag == "out":
                    self._maybe_update_dl_progress(msg)
                if tag == "meta":
                    if self.rtree:
                        try:
                            self.rtree.apply_meta(json.loads(msg))
                        except json.JSONDecodeError:
                            pass
                    continue
                if tag == "meta_done":
                    # 兜底：重读磁盘全量结果，保证不因管道丢行而缺数据
                    self._reload_meta_and_render()
                    self._update_sel_label()
                    # 若本页还有没探测到的，再补跑一次
                    self.after(300, self._ensure_page_probed)
                    continue
                if tag == "done":
                    self._set_running(False)
                    with self.proc_lock:
                        self.proc = None
                    if msg == "0":
                        self._log("ok", "✔ 完成")
                    else:
                        self._log("err", f"✘ 结束（代码 {msg}）")
                    continue
                t = self.log_text
                t.configure(state="normal")
                t.insert("end", msg + "\n", tag if tag in ("info", "cmd", "err", "ok") else "out")
                t.see("end")
                t.configure(state="disabled")
        except queue.Empty:
            pass
        self.after(80, self._poll_log)

    def clear_log(self) -> None:
        t = self.log_text
        t.configure(state="normal")
        t.delete("1.0", "end")
        t.configure(state="disabled")

    def _open_path(self, p: Path) -> None:
        try:
            if IS_WINDOWS:
                os.startfile(str(p))  # noqa: S606
            else:
                subprocess.Popen(["xdg-open", str(p)])
        except Exception as e:  # noqa: BLE001
            self._log("err", f"无法打开 {p}: {e}")


def main() -> None:
    App().mainloop()


if __name__ == "__main__":
    main()
