#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Step 4 — 按分段拉取弹幕，输出 B 站格式 XML（文件名与视频一致）。

用法：
    DOUYU_CONFIG=/path/to/config.json python scripts/step4_pull_danmaku.py [--limit 3]

输入：data/download_list.json（由 step2 生成，含 hash / title / duration_sec / folder）
输出：danmaku/<YYYYMM>/<场次名>.xml

设计说明：弹幕的 point_id 是「分段」级的，一律以 step2 产出的 raw_detail.json /
download_list.json 为准，不依赖任何会话转录、网盘快照或本机私有路径。
支持断点续跑（已存在且 >200 字节的 XML 自动跳过）。

归属说明：B站弹幕 XML 的 8 色映射表与 <d p> 字段顺序参考自公开的弹幕格式规范，
以及 renmu123/douyu-video-cli 的 douyu-api convert2Xml 实现（未复制其源码，未使用
fast-xml-parser 依赖）。详见仓库根目录 THIRD_PARTY_NOTICES.md。
"""
from __future__ import annotations

import json
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.config import load  # noqa: E402

API_BARRAGE = "https://v.douyu.com/wgapi/vod/center/getBarrageList"


def fetch_json(url: str, ua: str, retries: int = 4) -> dict:
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": ua})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception:  # noqa: BLE001
            if i == retries - 1:
                raise
            time.sleep(2 + i * 2)
    return {}


def fetch_all(hash_id: str, duration_sec: float, ua: str,
              max_windows: int = 60, pause: float = 0.12) -> list[dict]:
    items, start = [], 0
    dur_ms = max(1, int(duration_sec * 1000))
    for _ in range(max_windows):
        u = API_BARRAGE + "?" + urllib.parse.urlencode(
            {"vid": hash_id, "start_time": start, "end_time": dur_ms})
        d = fetch_json(u, ua)
        lst = (d.get("data") or {}).get("list") or []
        items.extend(lst)
        if len(lst) < 500:
            break
        tls = [int(x.get("tl") or 0) for x in lst]
        nxt = max(tls) + 1 if tls else 0
        if nxt <= start:
            break
        start = nxt
        if pause:
            time.sleep(pause)
    seen, uniq = set(), []
    for x in items:
        k = (x.get("uid"), x.get("sts"), x.get("ctt"))
        if k in seen:
            continue
        seen.add(k)
        uniq.append(x)
    return uniq


COLORS = {0: "#FFFFFF", 7: "#FF5654", 8: "#FF7523", 9: "#FE69B3", 10: "#FFBC00",
          11: "#78C946", 12: "#9E7FFF", 13: "#3D9BFF"}


def xml_escape(t) -> str:
    return (str(t) if t is not None else "").replace("&", "&amp;").replace("<", "&lt;") \
        .replace(">", "&gt;").replace('"', "&quot;")


def to_xml(items: list[dict], meta: dict) -> str:
    lines = ['<?xml version="1.0" encoding="utf-8"?>', "<i>", "  <metadata>"]
    for k, v in meta.items():
        if v not in (None, ""):
            lines.append(f"    <{k}>{xml_escape(v)}</{k}>")
    lines.append("  </metadata>")
    for x in items:
        tl = int(x.get("tl") or 0) // 1000
        col = COLORS.get(x.get("col"), "#FFFFFF")
        color_dec = int(col.lstrip("#"), 16)
        p = ",".join([str(tl), "1", "25", str(color_dec), str(int(x.get("sts") or 0)),
                      "0", str(x.get("mid") or ""), str(x.get("uid") or ""), "0"])
        lines.append(f'  <d p="{p}">{xml_escape(x.get("ctt"))}</d>')
    lines.append("</i>")
    return "\n".join(lines)


def safe_name(name: str) -> str:
    import re
    return re.sub(r'[\\/:*?"<>|]', "_", name or "").strip().rstrip(".")


def main() -> None:
    cfg = load()
    cfg.ensure_dirs()
    list_file = cfg.data_dir / "download_list.json"
    if not list_file.is_file():
        raise SystemExit(f"缺少 {list_file}，请先运行 step2_fetch_detail.py")
    items = json.loads(list_file.read_text(encoding="utf-8"))

    limit = None
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])

    targets = []
    for it in items:
        base = safe_name(it["title"])
        if not base:
            continue
        targets.append({
            "hash": it["hash"], "title": it["title"], "folder": it["folder"],
            "dur": float(it.get("duration_sec") or 7200), "base": base,
            "path": cfg.danmaku_dir / it["folder"] / (base + ".xml"),
        })

    todo = [t for t in targets if not (t["path"].exists() and t["path"].stat().st_size > 200)]
    print(f"总分段 {len(targets)}，已完成 {len(targets) - len(todo)}，待拉取 {len(todo)}", flush=True)
    if limit:
        todo = todo[:limit]

    ok = fail = done = 0
    t0 = time.time()
    fails = []
    for t in todo:
        t["path"].parent.mkdir(parents=True, exist_ok=True)
        try:
            barrage = fetch_all(t["hash"], t["dur"], cfg.ua)
            meta = {
                "chatserver": "chat.douyu.com", "chatid": t["hash"],
                "user_name": cfg.anchor_name, "room_title": t["title"],
                "platform": "douyu", "source_key": t["base"],
            }
            t["path"].write_text(to_xml(barrage, meta), encoding="utf-8")
            ok += 1
        except Exception as e:  # noqa: BLE001
            fail += 1
            fails.append({"hash": t["hash"], "err": f"{type(e).__name__}: {e}"})
            print(f"[{done + 1}/{len(todo)}] FAIL {t['base'][:50]}: {e}", flush=True)
        done += 1
        if done % 10 == 0 or done == len(todo):
            (cfg.danmaku_dir / "_progress.json").write_text(json.dumps({
                "total": len(targets), "todo": len(todo), "done": done, "ok": ok, "fail": fail,
                "updated": datetime.now().isoformat(timespec="seconds"),
            }, ensure_ascii=False, indent=1), encoding="utf-8")
        if done % 10 == 0:
            eta = (time.time() - t0) / done * (len(todo) - done) / 60
            print(f"[{done}/{len(todo)}] ok={ok} fail={fail} | ETA {eta:.0f}min", flush=True)
        time.sleep(0.15)

    if fails:
        (cfg.danmaku_dir / "_failed.json").write_text(
            json.dumps(fails, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"DONE ok={ok} fail={fail} elapsed={time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
