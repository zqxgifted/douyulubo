#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 douyulubo contributors
"""抓取播主的「投稿」列表（author-video）。

斗鱼有两套内容，接口和数据结构都不同：

  ① 录播（author-replay）
     authorShowVideoList → 场次(show) → getShowReplayList → 分段(segment)
     字段：show_id / video_list[0].hash_id / time_format

  ② 投稿（author-video）  ← 本脚本
     getAuthorVideosByNew → videos[]
     字段：vid / hash_id / create_time / video_duration / title

投稿通常是一次性上传的视频（剪辑、短片），不拆分段，直接一个 hash_id 一个视频。

产出：
    <work_dir>/data/posts_index.json    投稿列表

用法：
    DOUYU_CONFIG=config.json python scripts/list_posts.py [--quiet]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.config import load  # noqa: E402

API_POSTS = "https://v.douyu.com/wgapi/vod/center/getAuthorVideosByNew"


def make_session(ua: str) -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": ua})
    s.trust_env = False
    return s


def fmt_duration(v) -> tuple[int, str]:
    """时长 -> (秒, 'HH:MM:SS')。斗鱼这里给的是浮点秒。"""
    try:
        sec = int(float(v or 0))
    except (TypeError, ValueError):
        return 0, ""
    h, rem = divmod(max(0, sec), 3600)
    m, s = divmod(rem, 60)
    return sec, f"{h:02d}:{m:02d}:{s:02d}"


def main() -> None:
    ap = argparse.ArgumentParser(description="抓取播主投稿列表")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    cfg = load()
    cfg.ensure_dirs()
    session = make_session(cfg.ua)

    if not args.quiet:
        print(f"正在获取播主 {cfg.up_id} 的投稿…", flush=True)

    posts: list[dict] = []
    page = 1
    total = 0
    while True:
        params = {"page": page, "limit": 20, "cid2": 0, "tag2": 0, "up_id": cfg.up_id}
        try:
            r = session.get(API_POSTS, params=params, timeout=25)
            r.raise_for_status()
            d = r.json()
        except Exception as e:  # noqa: BLE001
            print(f"请求失败 page={page}: {e}", file=sys.stderr)
            break

        if d.get("error") != 0:
            print(f"接口返回错误：{d.get('msg')}", file=sys.stderr)
            break

        data = d.get("data") or {}
        total = int(data.get("count") or 0)
        vids = data.get("videos") or []
        if not args.quiet:
            print(f"  第 {page} 页：+{len(vids)}，累计 {len(posts)}/{total}", flush=True)

        for v in vids:
            sec, dur_str = fmt_duration(v.get("video_duration"))
            ctime = int(v.get("create_time") or 0)
            date = (datetime.fromtimestamp(ctime).strftime("%Y-%m-%d")
                    if ctime else "")
            posts.append({
                "hash_id": v.get("hash_id") or "",
                "vid": v.get("vid"),
                "title": v.get("title") or "",
                "create_time": ctime,
                "date": date,
                "time_str": (datetime.fromtimestamp(ctime).strftime("%Y-%m-%d %H:%M")
                             if ctime else ""),
                "folder": date.replace("-", "")[:6] if date else "",
                "duration_sec": sec,
                "duration_str": dur_str,
                "view_num": v.get("view_num") or 0,
                "pic": v.get("video_pic") or "",
            })

        if not vids or (total and len(posts) >= total):
            break
        page += 1
        time.sleep(0.35)

    posts.sort(key=lambda x: x.get("create_time") or 0, reverse=True)
    out = cfg.data_dir / "posts_index.json"
    out.write_text(json.dumps(posts, ensure_ascii=False, indent=1), encoding="utf-8")

    if not args.quiet:
        print("", flush=True)
        print(f"TOTAL_POSTS={len(posts)}", flush=True)
        if posts:
            print(f"最新：{posts[0].get('time_str')}  {posts[0].get('title')[:40]}", flush=True)
        print(f"已保存：{out}", flush=True)


if __name__ == "__main__":
    main()
