#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 douyulubo contributors
"""搜索结果的树状表格：场次为父节点，分段为子节点，支持分页与三态全选。

单独拆出来，让 app.py 保持可读。
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk


class ResultTree(ttk.Frame):
    """结果树：父=场次，子=分段。

    勾选语义：
      * 勾父节点 → 它的所有子分段全选
      * 勾子分段 → 只选该分段
      * 已知分段为唯一下载标识（hash_id）
    """

    COLS = ("sel", "date", "time", "title", "quality", "size", "segs", "status")
    HEADS = {"sel": "选择", "date": "日期", "time": "时间", "title": "标题",
             "quality": "最高清晰度", "size": "预计大小", "segs": "分段/时长",
             "status": "状态"}
    WIDTHS = {"sel": 44, "date": 84, "time": 52, "title": 200, "quality": 78,
              "size": 78, "segs": 74, "status": 66}

    def __init__(self, parent, on_select_change=None, **kw):
        super().__init__(parent, **kw)
        self.on_select_change = on_select_change
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        # height 给小值：实际高度由父容器拉伸，内容超出时靠滚动条
        self.tree = ttk.Treeview(self, columns=self.COLS, show="tree headings",
                                 selectmode="none", height=6)
        self.tree.heading("#0", text="")
        self.tree.column("#0", width=34, stretch=False)
        for c in self.COLS:
            self.tree.heading(c, text=self.HEADS[c])
            self.tree.column(c, width=self.WIDTHS[c],
                             minwidth=40,
                             stretch=(c == "title"),
                             anchor="w" if c in ("title", "date") else "center")
        vs = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview)
        hs = ttk.Scrollbar(self, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vs.set, xscrollcommand=hs.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        vs.grid(row=0, column=1, sticky="ns")
        hs.grid(row=1, column=0, sticky="ew")
        self.rowconfigure(0, weight=1)

        self.tree.bind("<Button-1>", self._on_click)
        # 复制支持：右键菜单 + Ctrl+C（Treeview 默认不支持选中复制文本）
        self.tree.bind("<Button-3>", self._on_right_click)
        self.tree.bind("<Control-c>", lambda _e: self.copy_selected())
        self._menu = tk.Menu(self, tearoff=0)
        self._menu.add_command(label="复制此格", command=self.copy_cell)
        self._menu.add_command(label="复制整行", command=self.copy_row)
        self._menu.add_command(label="复制标题", command=self.copy_title)
        self._menu.add_separator()
        self._menu.add_command(label="复制全部（当前页）", command=self.copy_all)

        # 状态
        self.shows: list[dict] = []          # 当前页的场次
        self.segments: dict[str, list] = {}  # show_id -> 分段列表
        self.checked: set[str] = set()       # 已选分段 hash_id
        self._meta: dict = {}                # hash_id -> {quality, est_size}
        self._pending: set[str] = set()      # 正在获取中的 hash_id
        self._downloaded: set[str] = set()   # 已下载的 hash_id
        self._downloading: set[str] = set()  # 下载中的 hash_id
        self.posts: list[dict] = []          # 投稿（author-video）

    # ---------- 数据 ----------
    def set_meta(self, meta: dict) -> None:
        self._meta = meta or {}

    def load_page(self, shows: list[dict], segments: dict[str, list]) -> None:
        """载入一页数据并重绘。"""
        self.shows = shows
        self.segments = segments
        self.render()

    def render(self) -> None:
        # 记住哪些场次是展开的，重建后恢复，避免勾选/刷新时被收起
        opened = {iid for iid in self.tree.get_children() if self.tree.item(iid, "open")}
        self.tree.delete(*self.tree.get_children())
        seq = 0
        for s in self.shows:
            sid = str(s.get("show_id"))
            segs = self.segments.get(sid, [])
            total_est = 0
            quals = []
            for g in segs:
                m = self._meta.get(str(g.get("hash_id"))) or {}
                total_est += int(m.get("est_size") or 0)
                if m.get("quality"):
                    quals.append(m["quality"])
            quality = _best_quality(quals)
            pending_cnt = sum(1 for g in segs
                              if str(g.get("hash_id")) in self._pending)
            q_show = quality or ("获取中…" if pending_cnt else "-")
            size_show = (_fmt_size(total_est) if total_est
                         else ("获取中…" if pending_cnt else "-"))
            dur = int(s.get("duration_sec") or 0)
            n_sel = sum(1 for g in segs if str(g.get("hash_id")) in self.checked)
            if not segs:
                mark = "☐"
            elif n_sel == 0:
                mark = "☐"
            elif n_sel == len(segs):
                mark = "☑"
            else:
                mark = "◩"

            p_date = s.get("date") or ""
            p_time = _time_part(s.get("time_str"))
            parent = self.tree.insert(
                "", "end", iid=f"s:{sid}", open=(f"s:{sid}" in opened),
                text="",
                values=(mark, p_date,
                        p_time,
                        _wrap_title(s.get("title"), 46),
                        q_show, size_show,
                        f"{len(segs)} 段" if segs else "无分段",
                        self._status_text(segs)))
            for n, g in enumerate(segs, 1):
                hid = str(g.get("hash_id"))
                m = self._meta.get(hid) or {}
                is_pending = hid in self._pending or not m
                g_date = g.get("date") or ""
                g_time = _time_part(g.get("time_str"))
                # 只在「跨天」时显示日期与时间：
                #   分段日期 != 父场次日期 -> 显示日期+时间（可能是次日凌晨场）
                #   同一天                 -> 留空（信息已在父行，避免重复）
                same_day = (g_date == p_date) if (g_date and p_date) else True
                show_date = "" if same_day else g_date
                show_time = "" if same_day else g_time
                self.tree.insert(
                    parent, "end", iid=f"g:{hid}", text="",
                    values=("☑" if hid in self.checked else "☐",
                            show_date,
                            show_time,
                            _sub_title(g, n, len(segs)),
                            (m.get("quality") or ("获取中…" if is_pending else "-")),
                            (_fmt_size(int(m.get("est_size") or 0))
                             if m.get("est_size") else ("获取中…" if is_pending else "-")),
                            f"P{n}  {g.get('duration_str') or ''}",
                            self._status_of(hid)))
            seq += 1

    # ---------- 交互 ----------
    def _on_click(self, event) -> None:
        region = self.tree.identify("region", event.x, event.y)
        col = self.tree.identify_column(event.x)
        if region not in ("tree", "cell") or col != "#1":
            return
        iid = self.tree.identify_row(event.y)
        if not iid:
            return
        self.toggle(iid)

    def toggle(self, iid: str) -> None:
        """切换勾选。只更新受影响的行，不重建树（否则展开状态会丢）。"""
        if iid.startswith("p:"):
            hid = iid[2:]
            if hid in self.checked:
                self.checked.discard(hid)
            else:
                self.checked.add(hid)
            self._update_check(iid)
        elif iid.startswith("g:"):
            hid = iid[2:]
            if hid in self.checked:
                self.checked.discard(hid)
            else:
                self.checked.add(hid)
            self._update_check(iid)
            parent = self.tree.parent(iid)
            if parent:
                self._update_check(parent)
        elif iid.startswith("s:"):
            sid = iid[2:]
            segs = self.segments.get(sid, [])
            hids = [str(g.get("hash_id")) for g in segs]
            all_in = hids and all(h in self.checked for h in hids)
            if all_in:
                for h in hids:
                    self.checked.discard(h)
            else:
                self.checked.update(hids)
            self._update_check(iid)
            for h in hids:
                child = f"g:{h}"
                if self.tree.exists(child):
                    self._update_check(child)
        if self.on_select_change:
            self.on_select_change()

    def set_downloaded(self, hashes) -> None:
        """标记这些分段为已下载。"""
        self._downloaded = {str(h) for h in hashes if h}
        self._downloading -= self._downloaded
        self.render()

    def set_downloading(self, hashes) -> None:
        """标记这些分段为下载中。"""
        self._downloading = {str(h) for h in hashes if h}
        self.render()

    def _status_of(self, hid: str) -> str:
        if hid in self._downloading:
            return "下载中"
        if hid in self._downloaded:
            return "已下载"
        return "未下载"

    def _status_text(self, segs: list) -> str:
        """场次状态：全部已下载=已下载；有下载中=下载中；否则未下载。"""
        if not segs:
            return "-"
        hids = [str(g.get("hash_id")) for g in segs]
        if any(h in self._downloading for h in hids):
            return "下载中"
        if all(h in self._downloaded for h in hids):
            return "已下载"
        return "未下载"

    def _update_check(self, iid: str) -> None:
        """只改某一行的勾选标记（保留展开状态）。"""
        if not self.tree.exists(iid):
            return
        vals = list(self.tree.item(iid, "values"))
        if not vals:
            return
        if iid.startswith("g:") or iid.startswith("p:"):
            hid = iid[2:]
            vals[0] = "☑" if hid in self.checked else "☐"
        elif iid.startswith("s:"):
            sid = iid[2:]
            segs = self.segments.get(sid, [])
            if not segs:
                vals[0] = "☐"
            else:
                n = sum(1 for g in segs if str(g.get("hash_id")) in self.checked)
                vals[0] = "☐" if n == 0 else ("☑" if n == len(segs) else "◩")
        self.tree.item(iid, values=vals)

    def mark_pending(self, hashes) -> None:
        """把这些分段标记为「获取中」。"""
        self._pending = {str(h) for h in hashes}
        self.render()

    def apply_meta(self, entry: dict) -> None:
        """单条探测结果回来：更新该行并取消 pending。"""
        hid = str(entry.get("hash_id") or entry.get("hash") or "")
        if not hid:
            return
        self._meta[hid] = {
            "quality": entry.get("quality") or "",
            "bit_rate": entry.get("bit_rate") or 0,
            "est_size": entry.get("est_size") or 0,
            "error": entry.get("error") or "",
        }
        self._pending.discard(hid)
        self._update_row(hid)

    def _update_row(self, hid: str) -> None:
        """只刷新该分段所在的行，避免整表重绘。"""
        for parent in self.tree.get_children():
            for child in self.tree.get_children(parent):
                if child == f"g:{hid}":
                    m = self._meta.get(hid) or {}
                    vals = list(self.tree.item(child, "values"))
                    vals[4] = m.get("quality") or "-"
                    vals[5] = (_fmt_size(int(m.get("est_size") or 0))
                               if m.get("est_size") else "-")
                    self.tree.item(child, values=vals)
                    self._refresh_parent(parent)
                    return

    def _refresh_parent(self, parent: str) -> None:
        """重算父行的清晰度/大小汇总。"""
        kids = self.tree.get_children(parent)
        if not kids:
            return
        total = 0
        quals = []
        pending = 0
        for k in kids:
            hid = k[2:]
            m = self._meta.get(hid) or {}
            total += int(m.get("est_size") or 0)
            if m.get("quality"):
                quals.append(m["quality"])
            if not m:
                pending += 1
        vals = list(self.tree.item(parent, "values"))
        vals[4] = _best_quality(quals) or ("获取中…" if pending else "-")
        vals[5] = _fmt_size(total) if total else ("获取中…" if pending else "-")
        self.tree.item(parent, values=vals)

    # ---------- 复制 ----------
    def _on_right_click(self, event) -> None:
        """右键：选中该行并弹出菜单。"""
        iid = self.tree.identify_row(event.y)
        if not iid:
            return
        self.tree.selection_set(iid)
        self._ctx_row = iid
        self._ctx_col = self.tree.identify_column(event.x)
        try:
            self._menu.tk_popup(event.x_root, event.y_root)
        finally:
            self._menu.grab_release()

    def _current(self) -> tuple[str, str] | tuple[None, None]:
        iid = getattr(self, "_ctx_row", None) or (
            self.tree.selection()[0] if self.tree.selection() else None)
        if not iid:
            return None, None
        col = getattr(self, "_ctx_col", None) or ""
        return iid, col

    def _col_index(self, col: str) -> int:
        """把 '#2' 这类列标识转成 values 下标。"""
        try:
            return int(col.replace("#", "")) - 1
        except ValueError:
            return -1

    def copy_cell(self) -> None:
        """复制鼠标所在单元格。"""
        iid, col = self._current()
        if not iid:
            return
        idx = self._col_index(col) if col else -1
        vals = self.tree.item(iid, "values")
        text = str(vals[idx]) if 0 <= idx < len(vals) else ""
        self._to_clipboard(text)

    def copy_row(self) -> None:
        """复制整行（制表符分隔，可粘进 Excel）。"""
        iid, _ = self._current()
        if not iid:
            return
        vals = self.tree.item(iid, "values")
        self._to_clipboard("\t".join(str(x) for x in vals))

    def copy_title(self) -> None:
        """只复制标题列。"""
        iid, _ = self._current()
        if not iid:
            return
        vals = self.tree.item(iid, "values")
        # 标题是第 4 列（index 3）
        self._to_clipboard(str(vals[3]) if len(vals) > 3 else "")

    def copy_all(self) -> None:
        """复制当前页所有行（含表头，制表符分隔）。"""
        header = "\t".join(self.HEADS[c] for c in self.COLS)
        lines = [header]
        for parent in self.tree.get_children():
            pv = self.tree.item(parent, "values")
            lines.append("\t".join(str(x) for x in pv))
            for child in self.tree.get_children(parent):
                cv = self.tree.item(child, "values")
                lines.append("\t".join(str(x) for x in cv))
        self._to_clipboard("\n".join(lines))

    def copy_selected(self) -> None:
        """Ctrl+C：没选中行时复制全部，否则复制选中行。"""
        sel = self.tree.selection()
        if not sel:
            self.copy_all()
            return
        lines = []
        for iid in sel:
            vals = self.tree.item(iid, "values")
            lines.append("\t".join(str(x) for x in vals))
        self._to_clipboard("\n".join(lines))

    def _to_clipboard(self, text: str) -> None:
        try:
            self.clipboard_clear()
            self.clipboard_append(text)
            self.update_idletasks()
        except tk.TclError:
            pass

    def set_add(self, hashes, on: bool) -> None:
        if on:
            self.checked.update(str(h) for h in hashes)
        else:
            for h in hashes:
                self.checked.discard(str(h))
        self.render()
        if self.on_select_change:
            self.on_select_change()

    def selected(self) -> list[str]:
        return sorted(self.checked)

    def selected_size(self) -> int:
        return sum(int((self._meta.get(h) or {}).get("est_size") or 0)
                   for h in self.checked)

    def expand_all(self, on: bool = True) -> None:
        for iid in self.tree.get_children():
            self.tree.item(iid, open=on)


def _wrap_title(t, limit: int = 46) -> str:
    """标题过长时插入换行，让 Treeview 显示两行。"""
    s = str(t or "")
    if len(s) <= limit:
        return s
    return s[:limit] + "\n" + s[limit:limit * 2] + ("…" if len(s) > limit * 2 else "")


def _time_part(ts) -> str:
    """从 'YYYY-MM-DD HH:MM' 里取出 'HH:MM'。"""
    s = str(ts or "")
    if " " in s:
        return s.split(" ", 1)[1][:5]
    return ""


def _sub_title(g: dict, n: int, total: int) -> str:
    """子分段标题：优先用「P1 · 21点场」这种简短标识。"""
    remark = str(g.get("seg_remark") or "").strip()
    if remark:
        return f"  └ P{n} · {remark}"
    return f"  └ P{n}/{total} · {_short(g.get('title'))}"


def _short(t, limit: int = 46) -> str:
    s = str(t or "")
    return s if len(s) <= limit else s[:limit] + "…"


def _fmt_size(n: int) -> str:
    if not n:
        return "-"
    if n >= 1024 ** 3:
        return f"{n / 1024 ** 3:.2f} GB"
    return f"{n / 1024 ** 2:.0f} MB"


def _best_quality(names: list[str]) -> str:
    """从多个清晰度里挑最高的（按常见档位排序）。"""
    if not names:
        return ""
    order = {"原画": 100, "1080": 90, "720": 70, "540": 54, "480": 48, "360": 36}
    def score(x: str) -> int:
        for k, v in order.items():
            if k in x:
                return v
        return 10
    return sorted(set(names), key=score, reverse=True)[0]
