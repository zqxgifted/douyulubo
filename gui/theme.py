# SPDX-License-Identifier: MIT
# Copyright (c) 2026 douyulubo contributors
"""界面主题：Material Design 3 + 拟物化（Neumorphism）风格。

设计说明
--------
tkinter 没有真正的圆角与投影，所以这里用「明暗双色边框」模拟拟物浮雕感：

* **凸起（raised）**：左上浅色高光 + 右下深色阴影 → 按钮、卡片
* **凹陷（sunken）**：左上深色 + 右下浅色 → 输入框、表格

配色改用 MD3 的中性色板（灰蓝底 + 柔和阴影），橙色仍作点缀色，
只出现在主按钮、选中页签和强调文字上。

全部通过 ttk.Style 实现，零第三方依赖。
"""
from __future__ import annotations

import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk

# ---- 品牌色（点缀）----
ORANGE = "#ff7700"
ORANGE_DARK = "#e56800"
ORANGE_SOFT = "#fff3e8"
ORANGE_LINE = "#ffd9b8"

# ---- MD3 中性色（大面积）----
# 背景用带一点冷调的灰，拟物化的凸起/凹陷才有对比空间
BG = "#eef0f4"               # 窗口底（拟物基底）
CARD = "#f7f8fa"             # 卡片面（比底色略亮）
CARD_RAISED = "#fafbfc"      # 凸起面
BORDER = "#d7dbe3"           # 普通边框
DIVIDER = "#e4e8ef"          # 分割线
TEXT = "#1b1f27"             # 主文字
MUTED = "#79818f"            # 次要文字
HOVER = "#e8ebf1"            # 悬停

# ---- 拟物化的明暗边（关键）----
LIGHT = "#ffffff"            # 高光（左上）
SHADOW = "#c6ccd8"           # 阴影（右下）
SHADOW_DEEP = "#b8bfcc"      # 更深阴影（按压/凹陷）

# ---- 语义色 ----
SUCCESS = "#0f9d58"
WARN = "#b87400"
DANGER = "#d93025"
DANGER_SOFT = "#fdeceb"

HEADER_BG = "#f7f8fa"
LOG_BG = "#1e222b"

FONT_UI = "Microsoft YaHei UI"
FONT_MONO = "Consolas"


def _pick_base_theme(style: ttk.Style) -> str:
    """clam 可定制性最强，优先用它以便统一配色。"""
    try:
        available = set(style.theme_names())
    except tk.TclError:
        available = set()
    for name in ("clam", "vista", "xpnative", "default"):
        if name in available:
            return name
    return "default"


def apply(root: tk.Misc) -> ttk.Style:
    """应用主题。"""
    style = ttk.Style(root)
    style.theme_use(_pick_base_theme(style))

    # ---- 字体 ----
    for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont"):
        try:
            tkfont.nametofont(name).configure(family=FONT_UI, size=10)
        except tk.TclError:
            pass
    try:
        tkfont.nametofont("TkFixedFont").configure(family=FONT_MONO, size=9)
    except tk.TclError:
        pass

    # ---- 容器 ----
    style.configure(".", background=BG, foreground=TEXT, font=(FONT_UI, 10))
    style.configure("TFrame", background=BG)
    style.configure("Card.TFrame", background=CARD)
    style.configure("Raised.TFrame", background=CARD_RAISED,
                    relief="raised", borderwidth=1,
                    lightcolor=LIGHT, darkcolor=SHADOW)
    style.configure("Header.TFrame", background=HEADER_BG)
    style.configure("Inset.TFrame", background="#eceef3",
                    relief="sunken", borderwidth=1,
                    lightcolor=SHADOW, darkcolor=LIGHT)

    # ---- 文字 ----
    style.configure("TLabel", background=BG, foreground=TEXT)
    style.configure("Card.TLabel", background=CARD, foreground=TEXT)
    style.configure("Raised.TLabel", background=CARD_RAISED, foreground=TEXT)
    style.configure("Muted.TLabel", background=BG, foreground=MUTED, font=(FONT_UI, 9))
    style.configure("CardMuted.TLabel", background=CARD, foreground=MUTED, font=(FONT_UI, 9))
    style.configure("RaisedMuted.TLabel", background=CARD_RAISED, foreground=MUTED,
                    font=(FONT_UI, 9))
    style.configure("Title.TLabel", background=HEADER_BG, foreground=TEXT,
                    font=(FONT_UI, 15, "bold"))
    style.configure("AccentTitle.TLabel", background=HEADER_BG, foreground=ORANGE,
                    font=(FONT_UI, 15, "bold"))
    style.configure("Subtitle.TLabel", background=HEADER_BG, foreground=MUTED,
                    font=(FONT_UI, 9))
    style.configure("Section.TLabel", background=CARD, foreground=TEXT,
                    font=(FONT_UI, 10, "bold"))
    style.configure("SectionAccent.TLabel", background=CARD, foreground=ORANGE_DARK,
                    font=(FONT_UI, 10, "bold"))
    style.configure("RaisedSection.TLabel", background=CARD_RAISED, foreground=TEXT,
                    font=(FONT_UI, 10, "bold"))
    style.configure("Big.TLabel", background=CARD, foreground=TEXT,
                    font=(FONT_UI, 13, "bold"))
    style.configure("OrangeBig.TLabel", background=CARD, foreground=ORANGE,
                    font=(FONT_UI, 20, "bold"))

    # ---- 分组框（拟物凸起卡片）----
    style.configure("TLabelframe", background=CARD, bordercolor=BORDER,
                    relief="solid", borderwidth=1)
    style.configure("TLabelframe.Label", background=CARD, foreground=TEXT,
                    font=(FONT_UI, 10, "bold"))
    # 拟物卡片：明暗边制造浮起感
    style.configure("Card.TLabelframe", background=CARD, bordercolor=BORDER,
                    relief="raised", borderwidth=1,
                    lightcolor=LIGHT, darkcolor=SHADOW)
    style.configure("Card.TLabelframe.Label", background=CARD, foreground=ORANGE_DARK,
                    font=(FONT_UI, 10, "bold"))

    # ---- 按钮：拟物凸起 + MD 扁平混合 ----
    # 普通按钮：浅底 + 高光边 → 可按的浮雕感
    style.configure("TButton", background=CARD_RAISED, foreground=TEXT,
                    padding=(13, 6), relief="raised", borderwidth=1,
                    lightcolor=LIGHT, darkcolor=SHADOW, focusthickness=0)
    style.map("TButton",
              background=[("active", HOVER), ("pressed", "#e2e6ed"),
                          ("disabled", "#f2f4f7")],
              foreground=[("disabled", "#b3bac6")],
              lightcolor=[("pressed", SHADOW), ("active", LIGHT)],
              darkcolor=[("pressed", LIGHT), ("active", SHADOW_DEEP)])

    # 主按钮：橙色实心（MD Filled），按下时下沉
    style.configure("Accent.TButton", background=ORANGE, foreground="#ffffff",
                    padding=(14, 6), font=(FONT_UI, 10, "bold"),
                    relief="raised", borderwidth=1,
                    lightcolor="#ffa04d", darkcolor="#c25a00", focusthickness=0)
    style.map("Accent.TButton",
              background=[("active", ORANGE_DARK), ("pressed", "#cc5e00"),
                          ("disabled", "#ffc79a")],
              foreground=[("disabled", "#fff5ec")],
              lightcolor=[("pressed", "#c25a00")],
              darkcolor=[("pressed", "#ffa04d")])

    # 次要按钮：白底橙字（MD Outlined）
    style.configure("Ghost.TButton", background=CARD_RAISED, foreground=ORANGE_DARK,
                    padding=(13, 6), relief="raised", borderwidth=1,
                    lightcolor=LIGHT, darkcolor=ORANGE_LINE, focusthickness=0)
    style.map("Ghost.TButton",
              background=[("active", ORANGE_SOFT)],
              bordercolor=[("active", ORANGE)],
              darkcolor=[("active", ORANGE)])

    # 危险按钮
    style.configure("Danger.TButton", background=CARD_RAISED, foreground=DANGER,
                    padding=(13, 6), relief="raised", borderwidth=1,
                    lightcolor=LIGHT, darkcolor="#f0c9c6", focusthickness=0)
    style.map("Danger.TButton",
              background=[("active", DANGER_SOFT)],
              darkcolor=[("active", DANGER)])

    # 链接式（无浮雕）
    style.configure("Link.TButton", background=CARD, foreground=ORANGE_DARK,
                    padding=(4, 2), relief="flat", borderwidth=0)
    style.map("Link.TButton", background=[("active", ORANGE_SOFT)])

    # 小按钮
    style.configure("Small.TButton", background=CARD_RAISED, foreground=TEXT,
                    padding=(9, 3), relief="raised", borderwidth=1,
                    lightcolor=LIGHT, darkcolor=SHADOW, font=(FONT_UI, 9))
    style.map("Small.TButton",
              background=[("active", HOVER), ("pressed", "#e2e6ed")],
              lightcolor=[("pressed", SHADOW)],
              darkcolor=[("pressed", LIGHT)])

    style.configure("SmallAccent.TButton", background=ORANGE, foreground="#ffffff",
                    padding=(9, 3), relief="raised", borderwidth=1,
                    lightcolor="#ffa04d", darkcolor="#c25a00",
                    font=(FONT_UI, 9, "bold"))
    style.map("SmallAccent.TButton",
              background=[("active", ORANGE_DARK), ("pressed", "#cc5e00")])

    # ---- 输入：拟物凹陷（与按钮相反的明暗）----
    style.configure("TEntry", fieldbackground="#ffffff", foreground=TEXT,
                    bordercolor=BORDER, lightcolor=SHADOW, darkcolor=LIGHT,
                    padding=7, insertcolor=TEXT,
                    relief="sunken", borderwidth=1)
    style.map("TEntry",
              bordercolor=[("focus", ORANGE)],
              lightcolor=[("focus", SHADOW)],
              darkcolor=[("focus", LIGHT)])

    style.configure("TCombobox", fieldbackground="#ffffff", background="#ffffff",
                    foreground=TEXT, bordercolor=BORDER, padding=6, arrowcolor=MUTED,
                    lightcolor=SHADOW, darkcolor=LIGHT,
                    selectbackground="#ffffff", selectforeground=TEXT,
                    readonlybackground="#ffffff",
                    relief="sunken", borderwidth=1)
    # clam 默认会给「readonly + focus」套白字，必须显式覆盖，否则白底白字像空的
    style.map("TCombobox",
              foreground=[("readonly", TEXT), ("disabled", "#b3bac6"), ("!readonly", TEXT)],
              bordercolor=[("focus", ORANGE), ("hover", ORANGE_LINE)],
              fieldbackground=[("readonly", "#ffffff"), ("disabled", "#f2f4f7")],
              background=[("readonly", "#ffffff"), ("active", "#ffffff")],
              selectbackground=[("readonly", "#ffffff")],
              selectforeground=[("readonly", TEXT)])

    style.configure("TSpinbox", fieldbackground="#ffffff", foreground=TEXT,
                    bordercolor=BORDER, lightcolor=SHADOW, darkcolor=LIGHT,
                    padding=6, arrowcolor=MUTED,
                    relief="sunken", borderwidth=1)
    style.map("TSpinbox", bordercolor=[("focus", ORANGE)])

    # ---- 勾选：方形 MD 风格 ----
    style.configure("TCheckbutton", background=CARD, foreground=TEXT,
                    font=(FONT_UI, 10), focusthickness=0, padding=(2, 3))
    style.map("TCheckbutton",
              background=[("active", CARD)],
              indicatorcolor=[("selected", ORANGE), ("!selected", "#ffffff")])
    style.configure("Page.TCheckbutton", background=BG, foreground=TEXT)
    style.map("Page.TCheckbutton",
              background=[("active", BG)],
              indicatorcolor=[("selected", ORANGE), ("!selected", "#ffffff")])
    style.configure("Raised.TCheckbutton", background=CARD_RAISED, foreground=TEXT)
    style.map("Raised.TCheckbutton",
              background=[("active", CARD_RAISED)],
              indicatorcolor=[("selected", ORANGE), ("!selected", "#ffffff")])

    style.configure("TRadiobutton", background=CARD, foreground=TEXT)
    style.map("TRadiobutton",
              background=[("active", CARD)],
              indicatorcolor=[("selected", ORANGE)])

    # ---- 页签：MD 风格，选中用白底 + 橙色文字 ----
    style.configure("TNotebook", background=BG, borderwidth=0, tabmargins=(0, 8, 0, 0))
    style.configure("TNotebook.Tab", background="#e3e7ee", foreground=MUTED,
                    padding=(30, 9), font=(FONT_UI, 10), borderwidth=0)
    style.map("TNotebook.Tab",
              background=[("selected", CARD_RAISED), ("active", "#eaedf3")],
              foreground=[("selected", ORANGE_DARK), ("active", MUTED)],
              # 所有状态 padding / expand 完全一致 → 尺寸绝不跳变
              padding=[("selected", (30, 9)), ("active", (30, 9)), ("!selected", (30, 9))],
              expand=[("selected", (0, 0, 0, 0)), ("!selected", (0, 0, 0, 0))])

    # ---- 表格：凹陷容器 + MD 表头 ----
    style.configure("Treeview", background="#ffffff", fieldbackground="#ffffff",
                    foreground=TEXT, rowheight=30, borderwidth=0,
                    font=(FONT_UI, 10), relief="flat")
    style.configure("Treeview.Heading", background="#eef1f6", foreground="#5b6472",
                    font=(FONT_UI, 9, "bold"), relief="raised", padding=(10, 8),
                    bordercolor=DIVIDER, lightcolor=LIGHT, darkcolor=SHADOW)
    style.map("Treeview.Heading", background=[("active", "#e6eaf1")])
    style.map("Treeview",
              background=[("selected", ORANGE_SOFT)],
              foreground=[("selected", TEXT)])

    # ---- 滚动条：细、圆润感的灰色 ----
    style.configure("Vertical.TScrollbar", background="#cdd3dd", troughcolor="#e8ebf1",
                    borderwidth=0, arrowsize=11, gripcount=0,
                    lightcolor=LIGHT, darkcolor=SHADOW)
    style.map("Vertical.TScrollbar", background=[("active", "#b9c1cd")])
    style.configure("Horizontal.TScrollbar", background="#cdd3dd", troughcolor="#e8ebf1",
                    borderwidth=0, arrowsize=11,
                    lightcolor=LIGHT, darkcolor=SHADOW)
    style.map("Horizontal.TScrollbar", background=[("active", "#b9c1cd")])

    # ---- 进度条 ----
    style.configure("TProgressbar", background=ORANGE, troughcolor="#e0e4ec",
                    borderwidth=0, thickness=6)
    style.configure("Orange.Horizontal.TProgressbar", background=ORANGE,
                    troughcolor="#e0e4ec", borderwidth=0, thickness=6)

    # ---- 分割线 ----
    style.configure("TSeparator", background=DIVIDER)

    # ---- 状态标签 ----
    style.configure("Ok.TLabel", background=CARD, foreground=SUCCESS)
    style.configure("Warn.TLabel", background=CARD, foreground=WARN)
    style.configure("Err.TLabel", background=CARD, foreground=DANGER)

    try:
        root.configure(background=BG)
    except tk.TclError:
        pass
    return style


# ---------------------------------------------------------------------------
# 便捷构件
# ---------------------------------------------------------------------------
def make_card(parent: tk.Misc, title: str = "", accent: bool = False,
              padding: int = 16) -> ttk.Frame:
    """拟物凸起卡片，返回内部可放控件的 frame。"""
    outer = ttk.Frame(parent, style="Raised.TFrame")
    outer.pack(fill="x", pady=(0, 12))
    inner = ttk.Frame(outer, style="Raised.TFrame")
    inner.pack(fill="both", expand=True, padx=padding, pady=padding)
    if title:
        head = ttk.Frame(inner, style="Raised.TFrame")
        head.pack(fill="x", pady=(0, 10))
        ttk.Label(head, text=title,
                  style="RaisedSection.TLabel").pack(side="left")
    return inner


def stripe_tree(tree: ttk.Treeview) -> None:
    """给表格加交替行背景色（比纯白更易读）。"""
    tree.tag_configure("odd", background="#fafbfc")
    tree.tag_configure("even", background="#ffffff")
    tree.tag_configure("done", foreground=SUCCESS)
    tree.tag_configure("missing", foreground=DANGER)


def make_log_widget(parent: tk.Misc) -> tk.Text:
    """深色等宽日志控件。"""
    text = tk.Text(parent, wrap="word", font=(FONT_MONO, 9), state="disabled",
                   background=LOG_BG, foreground="#c9ced6",
                   insertbackground="#c9ced6", relief="flat", borderwidth=0,
                   padx=12, pady=10, selectbackground="#3a3f4a")
    for tag, color in (("info", "#7fb2f0"), ("cmd", "#ff9f45"),
                       ("err", "#f28b82"), ("ok", "#7ee2a8"), ("out", "#c9ced6")):
        text.tag_config(tag, foreground=color)
    return text
