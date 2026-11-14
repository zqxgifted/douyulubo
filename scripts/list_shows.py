#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 douyulubo contributors
"""列出播主全部录播（两级展开）。

斗鱼的录播结构是两层的：
  ① authorShowVideoList   → 返回「场次」(show)，例：301 个
  ② getShowReplayList     → 每个场次下的「分段」(segment)，例：884 个

**分段才是真正的视频单元**。一个场次可能因为断流、多时段连播而拆成多段，
所以只统计第一层会严重少算（301 vs 884）。

本脚本两级都抓，产出：
    <work_dir>/data/shows_index.json     全部场次（含每场分段数）
    <work_dir>/data/segments_index.json  全部片段（下载单元）

用法：
    DOUYU_CONFIG=config.json python scripts/list_shows.py [--quiet]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.config import load  # noqa: E402

API_SHOW_LIST = "https://v.douyu.com/wgapi/vod/center/authorShowVideoList"
API_REPLAY_LIST = "https://v.douyu.com/wgapi/vod/center/getShowReplayList"


def make_session(ua: str) -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": ua})
    # 不走系统代理：很多机器开着失效的代理设置会导致连接被拒
    s.trust_env = False
    return s


def get_json(session: requests.Session, url: str, params: dict, retries: int = 4) -> dict:
    last = None
    for i in range(retries):
        try:
            r = session.get(url, params=params, timeout=25)
            r.raise_for_status()
            return r.json()
        except Exception as e:  # noqa: BLE001
            last = e
            if i < retries - 1:
                time.sleep(1.5 * (i + 1))
    raise RuntimeError(f"请求失败 {url}: {last}")


def to_seconds(v) -> int:
    """把时长统一成秒。斗鱼有时给数字，有时给 '02:00:08' 这种字符串。"""
    if v is None:
        return 0
    if isinstance(v, (int, float)):
        return int(v)
    s = str(v).strip()
    if not s:
        return 0
    if ":" in s:
        parts = s.split(":")
        try:
            nums = [int(float(p)) for p in parts]
        except ValueError:
            return 0
        total = 0
        for n in nums:
            total = total * 60 + n
        return total
    try:
        return int(float(s))
    except ValueError:
        return 0


def _fmt_datetime(date_str, time_str) -> str:
    """把 '2021-4-1' + '21:30' 合成 '2021-04-01 21:30'。"""
    d = str(date_str or "").strip()
    s = str(time_str or "").strip()
    if not d:
        return ""
    parts = d.split("-")
    if len(parts) == 3:
        try:
            d = f"{int(parts[0]):04d}-{int(parts[1]):02d}-{int(parts[2]):02d}"
        except ValueError:
            pass
    return f"{d} {s}".strip()


_SEG_TIME_RE = re.compile(r"【?(\d{4})-(\d{1,2})-(\d{1,2})\s*(\d{1,2})点场】?")


def _seg_time_from_title(title: str) -> str:
    """从分段标题解析『2021-04-01 21点场』这类时间。

    录播分段接口的 start_time 常为 None，
    但标题里一定有精确时间，例如：【2021-04-01 21点场】某主播：xxx
    """
    m = _SEG_TIME_RE.search(str(title or ""))
    if not m:
        return ""
    y, mo, d, h = (int(x) for x in m.groups())
    return f"{y:04d}-{mo:02d}-{d:02d} {h:02d}:00"


def _fmt_ts(ts) -> str:
    """时间戳 -> 'YYYY-MM-DD HH:MM'。"""
    try:
        v = int(ts)
    except (TypeError, ValueError):
        return ""
    if v <= 0:
        return ""
    return datetime.fromtimestamp(v).strftime("%Y-%m-%d %H:%M")


def _fmt_duration(v) -> str:
    """时长 -> 'HH:MM:SS'。支持数字与 '02:00:08' 两种格式。"""
    sec = to_seconds(v)
    if not sec:
        return ""
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def to_date(ts) -> str:
    """时间戳 -> YYYY-MM-DD（本地时区）。"""
    try:
        t = int(ts)
    except (TypeError, ValueError):
        return ""
    if t <= 0:
        return ""
    return datetime.fromtimestamp(t).strftime("%Y-%m-%d")


def fetch_shows(session: requests.Session, up_id: str, quiet: bool) -> tuple[list[dict], int]:
    """第一级：全部场次。"""
    shows: list[dict] = []
    page = 1
    total = 0
    while True:
        d = get_json(session, API_SHOW_LIST,
                     {"up_id": up_id, "page": page, "limit": 50})
        data = d.get("data") or {}
        lst = data.get("list") or []
        total = int(data.get("count") or 0)
        shows.extend(lst)
        if not quiet:
            print(f"  场次第 {page} 页：+{len(lst)}，累计 {len(shows)}/{total}", flush=True)
        if not lst or (total and len(shows) >= total):
            break
        page += 1
        time.sleep(0.3)
    return shows, total or len(shows)


def fetch_point_id(session: requests.Session, hash_id: str, retries: int = 3):
    """从播放页提取 point_id（取流必需）。失败返回 None。"""
    import re
    pat = re.compile(r'\{"vid":"%s","point_id":(\d+)' % re.escape(hash_id))
    for i in range(retries):
        try:
            r = session.get(f"https://v.douyu.com/show/{hash_id}", timeout=20)
            m = pat.search(r.text)
            if m:
                return int(m.group(1))
        except Exception:  # noqa: BLE001
            pass
        if i < retries - 1:
            time.sleep(1.0)
    return None


def fetch_segments(session: requests.Session, show: dict, up_id: str,
                   retries: int = 3) -> tuple[str, list]:
    """第二级：某个场次下的全部分段。

    接口偶发返回空列表（限流/瞬时故障），这里空结果会重试，
    避免把正常场次误记为「0 段」。
    """
    sid = str(show.get("show_id"))
    vl = show.get("video_list") or []
    if not vl:
        return sid, []
    vid = vl[0].get("hash_id")
    if not vid:
        return sid, []

    last_err = None
    for attempt in range(retries):
        try:
            d = get_json(session, API_REPLAY_LIST, {"vid": vid, "up_id": up_id})
            lst = (d.get("data") or {}).get("list") or []
            if lst:
                return sid, lst
            # 空结果：等一下再试（可能被限流）
            if attempt < retries - 1:
                time.sleep(0.8 * (attempt + 1))
        except Exception as e:  # noqa: BLE001
            last_err = e
            if attempt < retries - 1:
                time.sleep(1.2 * (attempt + 1))
    if last_err:
        print(f"  场次 {sid} 分段获取失败：{last_err}", file=sys.stderr)
    return sid, []


def main() -> None:
    ap = argparse.ArgumentParser(description="列出播主全部录播（场次 + 分段）")
    ap.add_argument("--quiet", action="store_true", help="只输出必要信息")
    ap.add_argument("--workers", type=int, default=5, help="抓分段的并发数")
    ap.add_argument("--with-pid", action="store_true",
                    help="同时抓每个分段的 point_id（约需 1-2 分钟，但能直接探测/下载）")
    ap.add_argument("--pid-only", nargs="*", default=None,
                    help="只给这些 hash_id 补 point_id（配合选择下载用）")
    args = ap.parse_args()

    cfg = load()
    cfg.ensure_dirs()
    session = make_session(cfg.ua)

    if not args.quiet:
        print(f"正在获取播主 {cfg.up_id} 的录播…", flush=True)

    # 只补指定 hash 的 point_id（选中后立即用，不用重抓整个列表）
    if args.pid_only is not None:
        sf = cfg.data_dir / "segments_index.json"
        if not sf.is_file():
            raise SystemExit(f"缺少 {sf}，请先运行一次完整抓取")
        segs = json.loads(sf.read_text(encoding="utf-8"))
        targets = {str(h) for h in args.pid_only}
        todo = [g for g in segs if str(g.get("hash_id")) in targets and not g.get("point_id")]
        if not args.quiet:
            print(f"需要补 point_id 的分段：{len(todo)}", flush=True)
        if todo:
            ok = 0
            with ThreadPoolExecutor(max_workers=max(1, args.workers)) as ex:
                futs = {ex.submit(fetch_point_id, session, g["hash_id"]): g for g in todo}
                for fu in as_completed(futs):
                    g = futs[fu]
                    pid = fu.result()
                    if pid:
                        g["point_id"] = pid
                        ok += 1
            sf.write_text(json.dumps(segs, ensure_ascii=False, indent=1), encoding="utf-8")
            if not args.quiet:
                print(f"补全 {ok}/{len(todo)}，已更新 {sf}", flush=True)
        return

    shows, show_total = fetch_shows(session, cfg.up_id, args.quiet)
    if not args.quiet:
        print(f"场次数：{len(shows)}，开始抓每场的分段…", flush=True)

    # 第二级：并发抓分段
    seg_by_show: dict[str, list] = {}
    done = 0
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as ex:
        futs = {ex.submit(fetch_segments, session, s, cfg.up_id): s for s in shows}
        for fu in as_completed(futs):
            sid, lst = fu.result()
            seg_by_show[sid] = lst
            done += 1
            if not args.quiet and done % 50 == 0:
                print(f"  分段进度 {done}/{len(shows)}", flush=True)

    # 组装场次索引 + 分段索引
    shows_index: list[dict] = []
    segments_index: list[dict] = []
    for it in shows:
        sid = str(it.get("show_id"))
        vl = it.get("video_list") or []
        first = vl[0] if vl else {}
        start = it.get("time") and 0 or (first.get("start_time") or 0)
        # 优先用 video_list 的 start_time
        if first.get("start_time"):
            start = first["start_time"]
        date = to_date(start)
        segs = seg_by_show.get(sid, [])
        shows_index.append({
            "show_id": sid,
            "hash_id": first.get("hash_id") or "",
            "title": it.get("title") or "",
            "start_time": int(start) if start else 0,
            "date": date,
            "folder": date.replace("-", "")[:6] if date else "",
            "segment_count": len(segs),
            "duration_sec": sum(to_seconds(x.get("video_duration")) for x in segs),
            "time_format": it.get("time_format") or "",
            "time_str": _fmt_datetime(it.get("date_format"), it.get("time_format")),
        })
        for n, seg in enumerate(segs, 1):
            sdate = to_date(seg.get("start_time")) or date
            segments_index.append({
                "hash_id": seg.get("hash_id") or "",
                "show_id": sid,
                "title": seg.get("title") or it.get("title") or "",
                "date": sdate,
                "folder": sdate.replace("-", "")[:6] if sdate else "",
                "start_time": int(seg.get("start_time") or 0),
                "duration_sec": to_seconds(seg.get("video_duration")),
                "seg_no": n,
                "seg_total": len(segs),
                "point_id": None,      # 后面补
                "cover": seg.get("cover") or "",
                "video_duration": seg.get("video_duration"),
                "seg_remark": seg.get("show_remark") or "",      # 如 "21点场"
                "duration_str": _fmt_duration(seg.get("video_duration")),
                "time_str": (_seg_time_from_title(seg.get("title"))
                             or _fmt_ts(seg.get("start_time"))
                             or _fmt_ts(first.get("start_time"))
                             or _fmt_datetime(it.get("date_format"), it.get("time_format"))),
            })

    # 并发补 point_id（可选：默认不抓，因为 884 个分段要 2 分钟）
    need_pid = [g for g in segments_index if not g.get("point_id")] if args.with_pid else []
    if need_pid:
        if not args.quiet:
            print(f"正在获取 {len(need_pid)} 个分段的 point_id…", flush=True)
        with ThreadPoolExecutor(max_workers=max(1, args.workers)) as ex:
            futs = {ex.submit(fetch_point_id, session, g["hash_id"]): g for g in need_pid}
            got = 0
            for fu in as_completed(futs):
                g = futs[fu]
                pid = fu.result()
                if pid:
                    g["point_id"] = pid
                    got += 1
        if not args.quiet:
            print(f"  point_id 获取成功 {got}/{len(need_pid)}", flush=True)

    shows_index.sort(key=lambda x: x.get("start_time") or 0, reverse=True)
    segments_index.sort(key=lambda x: x.get("start_time") or 0, reverse=True)

    (cfg.data_dir / "shows_index.json").write_text(
        json.dumps(shows_index, ensure_ascii=False, indent=1), encoding="utf-8")
    (cfg.data_dir / "segments_index.json").write_text(
        json.dumps(segments_index, ensure_ascii=False, indent=1), encoding="utf-8")

    if not args.quiet:
        dates = [s["date"] for s in shows_index if s.get("date")]
        print("", flush=True)
        print(f"TOTAL_SHOWS={len(shows_index)}", flush=True)
        print(f"TOTAL_SEGMENTS={len(segments_index)}", flush=True)
        if dates:
            print(f"日期范围：{min(dates)} ~ {max(dates)}", flush=True)
        print(f"已保存：{cfg.data_dir / 'shows_index.json'}", flush=True)
        print(f"已保存：{cfg.data_dir / 'segments_index.json'}", flush=True)


if __name__ == "__main__":
    main()
