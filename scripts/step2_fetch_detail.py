#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Step 2 — 抓取每个分段的官方详情（时长 / 弹幕数 / point_id）。

用法：
    DOUYU_CONFIG=/path/to/config.json python scripts/step2_fetch_detail.py

输入：<work_dir>/data/raw_segments.json（由 step1 生成）
产出：
    raw_detail.json    对象，key = hash_id
    download_list.json 下载清单 [{hash, file, folder, point_id, title, duration_sec}]
    probe_input.json   下载器输入（含 point_id）

注意：raw_detail.json 是对象不是数组；关联场次一律用 hash_id，不要用 title 里的日期。
"""
from __future__ import annotations

import json
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.config import load  # noqa: E402

lock = threading.Lock()


def extract(html: str, vid: str) -> dict:
    """从播放页 HTML 里提取元数据。页面结构变化时这些正则可能需要更新。"""
    point = re.search(r'\{"vid":"%s","point_id":(\d+)' % re.escape(vid), html)
    dm = re.search(r'"danmu_num":(\d+)', html)
    dur = re.search(r'"video_duration":([\d.]+)', html)
    title = re.search(r'"name":"(.*?)","pic"', html)
    return {
        "point_id": int(point.group(1)) if point else None,
        "danmu_num": int(dm.group(1)) if dm else None,
        "duration_sec": float(dur.group(1)) if dur else None,
        "title": title.group(1).encode().decode("unicode_escape") if title else None,
    }


def sanitize(name: str) -> str:
    return re.sub(r'[\\/:*?"<>|]', "_", name or "").strip().rstrip(".")


def folder_of(title: str | None, fallback: str = "unknown") -> str:
    m = re.search(r"(20\d{2})-(\d{1,2})", title or "")
    return f"{int(m.group(1)):04d}{int(m.group(2)):02d}" if m else fallback


def fetch_one(session: requests.Session, seg: dict, detail: dict) -> tuple[str, bool]:
    vid = seg["hash_id"]
    for i in range(5):
        try:
            r = session.get(f"https://v.douyu.com/show/{vid}", timeout=25)
            info = extract(r.text, vid)
            if info["point_id"] is None and i < 4:
                time.sleep(1.5)
                continue
            with lock:
                detail[vid] = {**seg, **info}
            return vid, info["point_id"] is not None
        except Exception:  # noqa: BLE001
            if i == 4:
                with lock:
                    detail[vid] = {**seg, "point_id": None, "danmu_num": None, "duration_sec": None}
                return vid, False
            time.sleep(1.5)
    return vid, False


def main() -> None:
    cfg = load()
    cfg.ensure_dirs()
    seg_file = cfg.data_dir / "raw_segments.json"
    idx_file = cfg.data_dir / "shows_index.json"

    if seg_file.is_file():
        segs = json.loads(seg_file.read_text(encoding="utf-8"))
    elif idx_file.is_file():
        # GUI 场景：只抓了场次索引（还没抓分段），就用索引里的首段当作一个段。
        # 这样「勾选若干场 → 直接下载」不需要先跑一遍完整的分段抓取。
        print("未找到 raw_segments.json，改用 shows_index.json 的场次首段", flush=True)
        segs = []
        for s in json.loads(idx_file.read_text(encoding="utf-8")):
            if not s.get("hash_id"):
                continue
            segs.append({
                "hash_id": s["hash_id"],
                "title": s.get("title", ""),
                "_show_id": s.get("show_id"),
                "video_duration": s.get("duration_sec"),
            })
    else:
        raise SystemExit(f"缺少 {seg_file} 或 {idx_file}，请先运行 list_shows.py 或 step1_fetch_list.py")

    # 从场次索引读分段信息（list_shows.py 生成），用于展开多段连播；
    # 找不到时退化为「每个场次一个段」。
    index_by_hash: dict[str, dict] = {}
    if idx_file.is_file():
        try:
            for s in json.loads(idx_file.read_text(encoding="utf-8")):
                if s.get("hash_id"):
                    index_by_hash[str(s["hash_id"])] = s
        except (OSError, json.JSONDecodeError):
            pass

    # --only 指定的 hash 优先（GUI 勾选后只抓选中的）
    only_arg = ""
    if "--only" in sys.argv:
        i = sys.argv.index("--only")
        if i + 1 < len(sys.argv):
            only_arg = sys.argv[i + 1]
    elif any(a.startswith("--only=") for a in sys.argv):
        only_arg = next(a.split("=", 1)[1] for a in sys.argv if a.startswith("--only="))

    if only_arg:
        wanted_path = Path(only_arg)
        wanted: set[str] = set()
        if wanted_path.is_file():
            payload = json.loads(wanted_path.read_text(encoding="utf-8"))
            if isinstance(payload, list):
                wanted = {str(x) for x in payload}
        if not wanted:
            print(f"--only 文件没有可用 hash：{only_arg}", file=sys.stderr)
            raise SystemExit(2)
        segs = [s for s in segs if str(s.get("hash_id")) in wanted]
        print(f"按选择过滤后：{len(segs)} 个分段", flush=True)

    print(f"segments to fetch: {len(segs)}", flush=True)

    session = requests.Session()
    # 不走系统代理：很多机器开着失效的代理设置会导致连接被拒
    session.trust_env = False
    session.headers.update(cfg.headers())
    detail: dict = {}
    done = 0
    with ThreadPoolExecutor(max_workers=10) as ex:
        futs = [ex.submit(fetch_one, session, s, detail) for s in segs]
        for fu in as_completed(futs):
            _, ok = fu.result()
            done += 1
            if done % 50 == 0:
                with lock:
                    (cfg.data_dir / "raw_detail.json").write_text(
                        json.dumps(detail, ensure_ascii=False), encoding="utf-8")
                print(f"progress {done}/{len(segs)} (last_ok={ok})", flush=True)

    (cfg.data_dir / "raw_detail.json").write_text(
        json.dumps(detail, ensure_ascii=False, indent=1), encoding="utf-8")

    # 生成下载清单：以 hash_id 为唯一键
    download_list = []
    probe_input = []
    for vid, d in sorted(detail.items()):
        title = d.get("title") or vid
        folder = folder_of(title, datetime.now().strftime("%Y%m"))
        file = sanitize(title) + ".mp4"
        point_id = d.get("point_id")
        if point_id is None:
            continue  # 取不到 point_id 的段无法下载，单独报告
        download_list.append({
            "hash": vid, "file": file, "folder": folder,
            "title": title, "duration_sec": d.get("duration_sec"), "point_id": point_id,
        })
        probe_input.append({
            "hash": vid, "key": title[:32], "folder": folder,
            "title": title, "point_id": point_id, "netdisk_size": 0,
        })

    (cfg.data_dir / "download_list.json").write_text(
        json.dumps(download_list, ensure_ascii=False, indent=1), encoding="utf-8")
    (cfg.data_dir / "probe_input.json").write_text(
        json.dumps(probe_input, ensure_ascii=False, indent=1), encoding="utf-8")

    ok = sum(1 for v in detail.values() if v.get("point_id"))
    print(f"DONE: {len(detail)} segments, {ok} with point_id; "
          f"download_list={len(download_list)}", flush=True)
    if len(download_list) < len(segs):
        print(f"警告：{len(segs) - len(download_list)} 个分段缺少 point_id，已跳过。", file=sys.stderr)


if __name__ == "__main__":
    main()
