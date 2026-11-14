#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 douyu-vod-toolkit contributors
"""工具 — 批量把 XML 弹幕转成 ASS（保留 XML 原件）。

两种后端，默认用内置纯 Python 实现（解压即用包不需要额外下载任何东西）：
  --backend builtin  纯 Python（默认）；see src/danmaku_ass.py
  --backend danmaku-factory  调用外部 DanmakuFactory CLI（需配置 danmaku_factory）

用法：
    python scripts/util_convert_danmaku_ass.py [--limit 2] [--backend builtin|danmaku-factory]
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.config import load  # noqa: E402
from src.danmaku_ass import Options, convert_file  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description="XML 弹幕 → ASS")
    ap.add_argument("--limit", type=int, default=None, help="只处理前 N 个（先试跑）")
    ap.add_argument("--backend", choices=["builtin", "danmaku-factory"], default="builtin")
    args = ap.parse_args()

    cfg = load()
    cfg.ensure_dirs()
    if args.backend == "danmaku-factory" and (not cfg.danmaku_factory or not Path(cfg.danmaku_factory).exists()):
        raise SystemExit("未配置 DanmakuFactory CLI：请在 config.json 设置 danmaku_factory，"
                         "或改用 --backend builtin（默认，无需额外依赖）")

    files = sorted(glob.glob(os.path.join(cfg.danmaku_dir, "**", "*.xml"), recursive=True))
    todo = []
    for f in files:
        rel = Path(os.path.relpath(f, cfg.danmaku_dir)).with_suffix(".ass")
        out = cfg.danmaku_ass_dir / rel
        if out.exists() and out.stat().st_size > 200:
            continue
        todo.append((f, out))
    print(f"XML 总数 {len(files)}，已转 {len(files) - len(todo)}，待转 {len(todo)}，后端={args.backend}", flush=True)
    if args.limit:
        todo = todo[:args.limit]

    opt = cfg.danmaku_options()
    print(f"排版参数: 字号={opt.font_size} 滚动={opt.scroll_duration}s "
          f"固定={opt.fixed_duration}s 行距={opt.line_spacing or '自动'} "
          f"屏蔽={opt.block_types or '无'}", flush=True)
    ok = fail = 0
    t0 = time.time()
    for i, (src, out) in enumerate(todo, 1):
        out.parent.mkdir(parents=True, exist_ok=True)
        try:
            if args.backend == "builtin":
                n = convert_file(src, str(out), opt)
                ok += 1
                print(f"[{i}/{len(todo)}] OK {out.name[:50]} | {n} 条 | {out.stat().st_size // 1024}KB", flush=True)
            else:
                cmd = [cfg.danmaku_factory, "-o", "ass", str(out), "-i", "xml", str(src),
                       "-r", "1920x1080", "--displayarea", "0.25", "--scrollarea", "0.25"]
                r = subprocess.run(cmd, capture_output=True, text=True,
                                   encoding="utf-8", errors="ignore", timeout=180)
                if out.exists() and out.stat().st_size > 200:
                    ok += 1
                    print(f"[{i}/{len(todo)}] OK {out.name[:50]} | {out.stat().st_size // 1024}KB", flush=True)
                else:
                    fail += 1
                    print(f"[{i}/{len(todo)}] FAIL(no output) {Path(src).name} | rc={r.returncode}", flush=True)
        except Exception as e:  # noqa: BLE001
            fail += 1
            print(f"[{i}/{len(todo)}] FAIL {Path(src).name}: {type(e).__name__} {e}", flush=True)
        if i % 20 == 0:
            (cfg.danmaku_ass_dir / "_progress.json").write_text(json.dumps({
                "done": i, "ok": ok, "fail": fail, "backend": args.backend,
            }, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"DONE ok={ok} fail={fail} elapsed={time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
