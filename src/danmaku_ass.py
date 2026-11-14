# SPDX-License-Identifier: MIT
# Copyright (c) 2026 douyu-vod-toolkit contributors
"""纯 Python 的 B站 XML 弹幕 → ASS 字幕转换（内置实现，无外部依赖）。

可调参数全部对应 DanmakuFactory 的同名配置项（见 docs/DANMAKU.md 的对照表），
因此从 DanmakuFactory 迁过来的用户可以直接对上号：

    resolution      1920x1080   分辨率
    displayarea     1.0         显示区域占屏幕高度比例
    scrollarea      1.0         滚动区域占显示区域比例
    scrolltime      8.0         滚动时长（秒）
    fixtime         4.5         固定弹幕停留时长（秒）
    density         0           同屏密度限制（0=不限制，正数=每行最多几条）
    lineSpacing     0           行间距（像素，0=自动）
    topMargin       0           顶部留白（像素）
    bottomMargin    0           底部留白（像素）
    fontsize        50          字号
    fontSizeStrict  false       严格使用指定字号（不按分辨率缩放）
    fontname        Microsoft YaHei
    opacity         255         不透明度 0-255
    outline         1.0         描边宽度
    outlineBlur     0.0         描边模糊
    outlineOpacity  255         描边不透明度
    shadow          0.0         阴影偏移
    bold            false       加粗

另外支持：
    blockTypes      屏蔽的弹幕类型列表，如 ["top","bottom","special","color","repeat"]
    timeShift       整体时间轴偏移（秒，可为负）
    noOverlap       是否强制不重叠（默认 true；false 时允许轻微重叠以保留更多弹幕）
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

DEFAULT_RES = (1920, 1080)
DEFAULT_FONT = "微软雅黑"

ASS_HEADER = """[Script Info]
Title: Douyu VOD Danmaku
ScriptType: v4.00+
PlayResX: {w}
PlayResY: {h}
WrapStyle: 2
ScaledBorderAndShadow: yes
YCbCr Matrix: TV.709

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font},{fs},{primary},{primary},{outline_c},{back_c},{bold},0,0,0,100,100,0,0,1,{outline},{shadow},2,0,0,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


@dataclass
class ScrollSlot:
    """一条滚动轨道。

    必须记录该轨道上**仍在屏幕内的所有弹幕**，而不只是最近一条：
    慢速/窄弹幕离场前，轨道上可能已经排了后面几条；只比较最近一条会漏判，
    导致与前几条发生视觉重叠（这是最容易出错的地方）。
    """
    active: list = field(default_factory=list)   # [(start, width, speed), ...]

    @property
    def start(self) -> float:
        return self.active[-1][0] if self.active else -1e9

    def push(self, start: float, width: float, speed: float, screen_w: float) -> None:
        entry = (start, width, speed)
        # 只保留「尚未完全离开屏幕」的条目：离场时刻 = start + (W+width)/speed
        self.active = [e for e in self.active if e[0] + (screen_w + e[1]) / e[2] > start]
        self.active.append(entry)


@dataclass
class FixedSlot:
    """顶部/底部轨道的占用截止时间。"""
    free_at: float = 0.0


@dataclass
class Options:
    # --- 几何 ---
    width: int = DEFAULT_RES[0]
    height: int = DEFAULT_RES[1]
    displayarea: float = 1.0          # 显示区域（占屏幕高度）
    scrollarea: float = 1.0           # 滚动区域（占显示区域）
    top_margin: int = 0
    bottom_margin: int = 0
    # --- 文字 ---
    font_name: str = DEFAULT_FONT
    font_size: int = 50
    font_size_strict: bool = False
    opacity: int = 255
    outline: float = 1.0
    outline_blur: float = 0.0
    outline_opacity: int = 255
    shadow: float = 0.0
    bold: bool = False
    # --- 时间 ---
    scroll_duration: float = 8.0
    fixed_duration: float = 4.5
    time_shift: float = 0.0
    # --- 排版 ---
    line_spacing: int = 0             # 0 = 自动（字号 × 1.05）
    density: int = 0                  # 0 = 不限制
    no_overlap: bool = True
    # --- 过滤 ---
    block_types: list = field(default_factory=list)

    # 兼容旧字段名
    @property
    def top_ratio(self) -> float:
        return self.displayarea * self.scrollarea

    def line_height(self) -> float:
        return float(self.line_spacing) if self.line_spacing > 0 else self.font_size * 1.05

    def text_width(self, text: str) -> float:
        """按字符类别估算像素宽度：中文/全角算 1.0，ASCII 算 0.55。"""
        w = 0.0
        for ch in text:
            w += 1.0 if ord(ch) > 0x2E80 else 0.55
        return max(w * self.font_size, self.font_size)

    def effective_font_size(self) -> int:
        """未设 fontSizeStrict 时按 1080p 基准等比缩放。"""
        if self.font_size_strict:
            return self.font_size
        return max(8, int(round(self.font_size * self.height / 1080.0)))


def _ass_time(t: float) -> str:
    t = max(0.0, float(t))
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = t % 60
    return f"{h:d}:{m:02d}:{s:05.2f}"


def _ass_color(rgb: int) -> str:
    """十进制 RGB -> ASS 的 &HBBGGRR&。"""
    r = (rgb >> 16) & 0xFF
    g = (rgb >> 8) & 0xFF
    b = rgb & 0xFF
    return f"&H{b:02X}{g:02X}{r:02X}&"


def _ass_alpha(opacity: int) -> str:
    """不透明度 255(不透明) -> ASS alpha 00(不透明)。"""
    a = max(0, min(255, int(opacity)))
    return f"&H{255 - a:02X}&"


def _esc(text: str) -> str:
    """ASS 文本转义：反斜杠/花括号是控制字符，换行用 \\N。"""
    t = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    t = t.replace("\\", "＼").replace("{", "｛").replace("}", "｝")
    return t.replace("\n", "\\N")


def _parse_p(p: str) -> tuple[float, int, int, int]:
    """解析 <d p="...">，返回 (时间秒, 模式, 颜色十进制, 字号)。"""
    parts = (p or "").split(",")
    def num(i, default, cast=float):
        try:
            return cast(parts[i])
        except (IndexError, ValueError):
            return default
    return num(0, 0.0), num(1, 1, int), num(3, 0xFFFFFF, int), num(2, 25, int)


def _track_ys(opt: Options, top: bool) -> list[int]:
    """把可用区域按行高均分，返回每行基线 y。

    顶部区域从 top_margin 开始；滚动弹幕占 displayarea*scrollarea 的高度。
    额外留出半个行高的内边距，避免第一行贴顶。
    """
    lh = opt.line_height()
    usable_h = opt.height * opt.displayarea
    pad = int(lh * 0.35)
    if top:
        y0 = opt.top_margin + pad
        y1 = usable_h * opt.scrollarea
    else:
        y0 = opt.height - opt.bottom_margin - usable_h * (1.0 - opt.scrollarea)
        y1 = opt.height - opt.bottom_margin - pad
    y0 = max(0, int(y0))
    y1 = min(opt.height, int(y1))
    if y1 <= y0:
        y1 = min(opt.height, y0 + int(lh))
    n = max(1, int((y1 - y0) // lh))
    return [int(y0 + i * lh) for i in range(n)]


def convert(xml_text: str, opt: Options | None = None) -> str:
    """把 B站 XML 弹幕文本转换成 ASS 文本。"""
    opt = opt or Options()
    root = ET.fromstring(xml_text)

    blocked = {str(b).lower() for b in (opt.block_types or [])}
    items: list[tuple[float, int, int, str]] = []
    seen_text = set()
    for d in root.iter("d"):
        t, mode, color, fsize = _parse_p(d.get("p", ""))
        txt = _esc(d.text or "")
        if not txt:
            continue
        t += opt.time_shift
        if t < 0:
            continue
        # 按类型屏蔽
        mode_name = {4: "bottom", 5: "top", 7: "special", 8: "code"}.get(mode, "scroll")
        if mode_name in blocked:
            continue
        if "color" in blocked and color != 0xFFFFFF:
            continue
        if "special" in blocked and mode in (7, 8):
            continue
        if "repeat" in blocked:
            if txt in seen_text:
                continue
            seen_text.add(txt)
        items.append((t, mode, color, txt, fsize))
    items.sort(key=lambda x: (x[0], x[1]))

    W = opt.width
    H = opt.height
    fs = opt.effective_font_size()
    scroll_ys = _track_ys(opt, top=True)
    bottom_ys = _track_ys(opt, top=False)
    # 密度限制：每条轨道最多同时存在 density 条（0=不限制）
    scroll_slots = [ScrollSlot() for _ in scroll_ys]
    top_slots = [FixedSlot() for _ in scroll_ys]
    bottom_slots = [FixedSlot() for _ in bottom_ys]

    primary = _ass_color(0xFFFFFF)   # 实际颜色在每行 \c 覆盖
    outline_c = _ass_color(0x000000)
    back_c = _ass_color(0x000000)
    alpha = _ass_alpha(opt.opacity)

    out: list[str] = []

    def base_tags(color: int) -> str:
        tags = f"\\c{_ass_color(color)}"
        if opt.opacity < 255:
            tags += f"\\alpha{alpha}"
        if opt.outline != 1.0:
            tags += f"\\bord{opt.outline}"
        if opt.shadow:
            tags += f"\\shad{opt.shadow}"
        if opt.outline_blur:
            tags += f"\\blur{opt.outline_blur}"
        return tags

    def emit(start: float, end: float, text: str, color: int, body: str) -> None:
        out.append(
            f"Dialogue: 0,{_ass_time(start)},{_ass_time(end)},Default,,0,0,0,,"
            f"{{{base_tags(color)}}}{body}{{\\fs{fs}}}{text}"
        )

    for entry in items:
        t, mode, color, text, _fsize = entry
        w = opt.text_width(text)

        if mode == 5:  # 顶部固定
            free = [i for i, s in enumerate(top_slots) if s.free_at <= t]
            i = free[0] if free else min(range(len(top_slots)), key=lambda k: top_slots[k].free_at)
            start = max(t, top_slots[i].free_at)
            top_slots[i].free_at = start + opt.fixed_duration + 0.1
            y = scroll_ys[i]
            emit(start, start + opt.fixed_duration, text, color,
                 f"{{\\an8\\pos({W // 2},{y})}}")

        elif mode == 4:  # 底部固定
            free = [i for i, s in enumerate(bottom_slots) if s.free_at <= t]
            i = free[0] if free else min(range(len(bottom_slots)), key=lambda k: bottom_slots[k].free_at)
            start = max(t, bottom_slots[i].free_at)
            bottom_slots[i].free_at = start + opt.fixed_duration + 0.1
            y = bottom_ys[i]
            emit(start, start + opt.fixed_duration, text, color,
                 f"{{\\an2\\pos({W // 2},{y})}}")

        else:  # 滚动（mode 1 及其它）
            v = (W + w) / opt.scroll_duration

            def x_of(tt: float, st: float, speed: float) -> float:
                return W - speed * (tt - st)

            def overlap_visible(la: float, ra: float, lb: float, rb: float) -> bool:
                a0, a1 = max(la, 0.0), min(ra, float(W))
                b0, b1 = max(lb, 0.0), min(rb, float(W))
                return a1 > a0 and b1 > b0 and a0 < b1 and b0 < a1

            def collides(tn: float, wn: float, vn: float, slot: ScrollSlot,
                         samples: int = 32) -> bool:
                for (sp, wp, vp) in slot.active:
                    en = tn + (W + wn) / vn
                    ep = sp + (W + wp) / vp
                    t0, t1 = max(tn, sp), min(en, ep)
                    if t1 <= t0:
                        continue
                    for k in range(samples + 1):
                        tt = t0 + (t1 - t0) * k / samples
                        nl = x_of(tt, tn, vn)
                        pl = x_of(tt, sp, vp)
                        if overlap_visible(nl, nl + wn, pl, pl + wp):
                            return True
                return False

            if opt.no_overlap:
                free = [i for i, s in enumerate(scroll_slots) if not collides(t, w, v, s)]
                chosen = min(free, key=lambda i: scroll_slots[i].start) if free else -1
            else:
                chosen = 0

            if chosen < 0:
                # 所有轨道都满：顺延到最早空出的时刻；失败则退化为顶部固定弹幕
                best_i, best_t = -1, t
                for i, s in enumerate(scroll_slots):
                    cand = t
                    for _ in range(40):
                        if not collides(cand, w, v, s):
                            break
                        cand += 0.05
                    else:
                        continue
                    if cand < best_t or best_i < 0:
                        best_i, best_t = i, cand
                if best_i >= 0:
                    chosen, t = best_i, best_t
                else:
                    free = [i for i, s in enumerate(top_slots) if s.free_at <= t]
                    i = free[0] if free else min(range(len(top_slots)),
                                                 key=lambda k: top_slots[k].free_at)
                    start = max(t, top_slots[i].free_at)
                    top_slots[i].free_at = start + opt.fixed_duration + 0.1
                    y = scroll_ys[i]
                    emit(start, start + opt.fixed_duration, text, color,
                         f"{{\\an8\\pos({W // 2},{y})}}")
                    continue

            scroll_slots[chosen].push(t, w, v, W)
            y = scroll_ys[chosen]
            # \an7 = 左上对齐，x 才代表左边缘；起点 W → 终点 -w
            emit(t, t + opt.scroll_duration, text, color,
                 f"{{\\an7\\move({W},{y},{-int(w)},{y})}}")

    header = ASS_HEADER.format(
        w=W, h=H, font=opt.font_name, fs=fs,
        primary=primary, outline_c=outline_c, back_c=back_c,
        bold=-1 if opt.bold else 0,
        outline=opt.outline, shadow=opt.shadow,
    )
    return header + "\n".join(out) + "\n"


def convert_file(xml_path: str, ass_path: str, opt: Options | None = None) -> int:
    """转换单个文件，返回生成的弹幕条数。"""
    with open(xml_path, "r", encoding="utf-8") as f:
        xml_text = f.read()
    out = convert(xml_text, opt)
    with open(ass_path, "w", encoding="utf-8") as f:
        f.write(out)
    return out.count("Dialogue:")
