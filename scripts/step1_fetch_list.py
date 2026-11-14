#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Step 1 — 抓取主播全部录播场次与分段。

用法：
    DOUYU_CONFIG=/path/to/config.json python scripts/step1_fetch_list.py

产出（位于 <work_dir>/data/）：
    raw_shows.json     全部 show
    raw_segments.json  扁平化后的全部分段（分段才是视频单元）

配置见 examples/config.example.json。无需登录态，只需正常 User-Agent。
"""
from __future__ import annotations

import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.config import load  # noqa: E402

API_SHOW_LIST = "https://v.douyu.com/wgapi/vod/center/authorShowVideoList"
API_REPLAY_LIST = "https://v.douyu.com/wgapi/vod/center/getShowReplayList"


def get_json(session: requests.Session, url: str, params: dict, retries: int = 4) -> dict:
    last = None
    for i in range(retries):
        try:
            r = session.get(url, params=params, timeout=20)
            r.raise_for_status()
            return r.json()
        except Exception as e:  # noqa: BLE001
            last = e
            if i < retries - 1:
                time.sleep(1.5 * (i + 1))
    raise RuntimeError(f"请求失败 {url}: {last}")


def fetch_all_shows(session: requests.Session, up_id: str, page_size: int = 50) -> tuple[list, int]:
    shows, page = [], 1
    while True:
        d = get_json(session, API_SHOW_LIST, {"up_id": up_id, "page": page, "limit": page_size})
        data = d.get("data") or {}
        lst = data.get("list") or []
        shows.extend(lst)
        total = int(data.get("count") or 0)
        print(f"page {page}: +{len(lst)}, collected {len(shows)}/{total}", flush=True)
        if not lst or (total and len(shows) >= total):
            break
        page += 1
        time.sleep(0.4)
    return shows, total or len(shows)


def fetch_segments(session: requests.Session, show: dict, up_id: str) -> tuple[str | None, list]:
    video_list = show.get("video_list") or []
    if not video_list:
        return show.get("show_id"), []
    vid = video_list[0].get("hash_id")
    if not vid:
        return show.get("show_id"), []
    d = get_json(session, API_REPLAY_LIST, {"vid": vid, "up_id": up_id})
    return show.get("show_id"), (d.get("data") or {}).get("list") or []


def main() -> None:
    cfg = load()
    cfg.ensure_dirs()
    session = requests.Session()
    # 不走系统代理：很多机器开着失效的代理设置会导致连接被拒
    session.trust_env = False
    session.headers.update(cfg.headers())

    print(f"up_id={cfg.up_id} work_dir={cfg.work_dir}", flush=True)
    shows, total = fetch_all_shows(session, cfg.up_id)
    (cfg.data_dir / "raw_shows.json").write_text(
        json.dumps(shows, ensure_ascii=False, indent=1), encoding="utf-8")

    segments: list[dict] = []
    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = {ex.submit(fetch_segments, session, s, cfg.up_id): s for s in shows}
        for fu in as_completed(futs):
            sid, lst = fu.result()
            for seg in lst:
                seg["_show_id"] = sid
                segments.append(seg)
            if len(segments) % 100 < 8:
                print(f"segments so far: {len(segments)}", flush=True)

    (cfg.data_dir / "raw_segments.json").write_text(
        json.dumps(segments, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"TOTAL SHOWS={total}  TOTAL SEGMENTS={len(segments)}", flush=True)
    if len(segments) < len(shows):
        print("警告：分段数少于场次数，请检查接口返回。", file=sys.stderr)


if __name__ == "__main__":
    main()
