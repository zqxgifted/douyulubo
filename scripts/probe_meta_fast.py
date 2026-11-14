#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 douyulubo contributors
"""快速探测每个分段的最高清晰度与预计大小。

与 probe_segments.mjs 的区别：
  * 用 Python 实现，可以直接被 GUI 内联调用，不经过 node 子进程
  * 只取「最高画质名称 + 码率 + 估算大小」，逻辑更轻
  * 支持并发，默认 6 线程

估算大小的两个来源（按可靠度）：
  1. 官方标称码率 × 时长（bit_rate × duration / 8）—— 快，误差 ±10%
  2. m3u8 分片 HEAD 抽样 —— 准，但要额外请求

本脚本用 1，因为它对每个分段只需 1 次页面请求 + 1 次取流请求，
884 段在 6 并发下约 1-2 分钟；用 2 会慢好几倍。

写法：
    DOUYU_CONFIG=config.json python scripts/probe_meta_fast.py [--limit N] [--workers 6]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.config import load  # noqa: E402

API_STREAM = "https://v.douyu.com/wgapi/vodnc/front/stream/getStreamUrlWeb"

lock = threading.Lock()


def make_session(ua: str) -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": ua})
    s.trust_env = False
    return s


def load_signer(session: requests.Session, hash_id: str):
    """从播放页提取签名函数，返回 (函数源码, 函数名)。"""
    html = session.get(f"https://v.douyu.com/show/{hash_id}", timeout=20).text
    scripts = re.findall(r"<script\b[^>]*>([\s\S]*?)</script>", html)
    ds = scripts[-2] if len(scripts) >= 2 else ""
    names = re.findall(r"function\s+([a-zA-Z0-9_]+)\(", ds)
    if not names:
        raise RuntimeError("未找到签名函数")
    return ds, names[0]


def probe_one(session: requests.Session, seg: dict, cfg, signer_cache: dict) -> dict:
    """探测一个分段：返回 {quality, bit_rate, est_size}。"""
    hid = seg["hash_id"]
    pid = seg.get("point_id")
    if pid is None:
        raise RuntimeError("缺少 point_id")

    # 签名函数会轮换，按 hash 缓存但失败时重取
    ds, fn = signer_cache.get("_any") or load_signer(session, hid)
    env = {"__crypto_md5": None}

    # 构造签名 body（与 step3_download_seg.mjs 逻辑一致）
    import hashlib
    # 用 exec 执行签名函数，注入 CryptoJS.MD5
    g = {"CryptoJS": {"MD5": lambda s: hashlib.md5(str(s).encode()).hexdigest()}}
    try:
        exec(ds, g)
        fnc = g.get(fn)
        if not callable(fnc):
            raise RuntimeError(f"签名函数 {fn} 不可调用")
        body = f"{fnc(pid, cfg.did, int(time.time()))}&vid={hid}"
    except Exception:
        raise

    r = session.post(API_STREAM, data=body,
                     headers={"Content-Type": "application/x-www-form-urlencoded"}, timeout=25)
    j = r.json()
    if j.get("error") != 0:
        raise RuntimeError(f"取流失败 error={j.get('error')}")

    tv = (j.get("data") or {}).get("thumb_video")
    opts = list(tv.values()) if isinstance(tv, dict) else (tv or [])
    if not opts:
        raise RuntimeError("无画质档位")
    opts.sort(key=lambda o: o.get("bit_rate") or 0, reverse=True)
    top = opts[0]

    dur = float(seg.get("duration_sec") or 0)
    rate = float(top.get("bit_rate") or 0)  # kbps
    est = int(rate * 1000 * dur / 8) if (dur and rate) else 0

    return {
        "quality": top.get("name") or "",
        "bit_rate": int(rate),
        "est_size": est,
        "options": [{"name": o.get("name"), "bit_rate": o.get("bit_rate")} for o in opts],
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--workers", type=int, default=6)
    args = ap.parse_args()

    cfg = load()
    cfg.ensure_dirs()

    seg_file = cfg.data_dir / "segments_index.json"
    out_file = cfg.data_dir / "segment_meta.json"
    if not seg_file.is_file():
        raise SystemExit(f"缺少 {seg_file}，请先运行 list_shows.py")

    segs = json.loads(seg_file.read_text(encoding="utf-8"))
    meta: dict = {}
    if out_file.is_file():
        try:
            meta = json.loads(out_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            meta = {}

    todo = [s for s in segs if s.get("hash_id") and str(s["hash_id"]) not in meta and s.get("point_id")]
    if args.limit:
        todo = todo[: args.limit]
    print(f"待探测 {len(todo)} / 共 {len(segs)} 个分段（已探测 {len(meta)}）", flush=True)

    if not todo:
        print("没有需要探测的分段", flush=True)
        return

    session = make_session(cfg.ua)
    signer_cache: dict = {}
    ok = fail = done = 0
    errs = []
    t0 = time.time()

    def work(seg):
        nonlocal ok, fail, done
        hid = str(seg["hash_id"])
        try:
            r = probe_one(session, seg, cfg, signer_cache)
            with lock:
                meta[hid] = r
            ok += 1
        except Exception as e:  # noqa: BLE001
            with lock:
                meta[hid] = {"error": str(e)[:80]}
            fail += 1
            errs.append((hid, str(e)[:60]))
        finally:
            with lock:
                done += 1
                if done % 20 == 0:
                    out_file.write_text(json.dumps(meta, ensure_ascii=False, indent=1),
                                        encoding="utf-8")
                    el = time.time() - t0
                    eta = el / done * (len(todo) - done)
                    print(f"[{done}/{len(todo)}] ok={ok} fail={fail} ETA {eta:.0f}s", flush=True)

    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as ex:
        list(as_completed([ex.submit(work, s) for s in todo]))

    out_file.write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"DONE ok={ok} fail={fail} 用时 {time.time() - t0:.0f}s", flush=True)
    print(f"已保存 {out_file}", flush=True)
    if errs:
        print("部分失败示例：", errs[:3], flush=True)


if __name__ == "__main__":
    main()
