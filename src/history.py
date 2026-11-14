# SPDX-License-Identifier: MIT
# Copyright (c) 2026 douyu-vod-toolkit contributors
"""下载历史：每场一个 JSON 文件，位于 <work_dir>/data/history/<hash>.json。

为什么每场一个文件：批量下载是并发的，多进程同时写一个大 JSON 会互相覆盖；
每场独立文件天然无锁，且方便查询「某个录播下过没有」。

记录内容：hash / title / file / folder / size / duration_sec / quality /
danmaku 状态 / 完成时间 / 来源。
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path


def history_dir(work_dir: Path) -> Path:
    return Path(work_dir) / "data" / "history"


def _safe(hash_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9_\-]", "_", str(hash_id))[:120]


def record_path(work_dir: Path, hash_id: str) -> Path:
    return history_dir(work_dir) / f"{_safe(hash_id)}.json"


def is_downloaded(work_dir: Path, hash_id: str, min_size: int = 1) -> bool:
    """历史里有记录，且对应视频文件确实存在且够大，才算「已下载」。"""
    p = record_path(work_dir, hash_id)
    if not p.is_file():
        return False
    try:
        rec = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    f = rec.get("file")
    if not f:
        return False
    fp = Path(f)
    if not fp.is_absolute():
        fp = Path(work_dir) / fp
    try:
        return fp.is_file() and fp.stat().st_size >= min_size
    except OSError:
        return False


def mark(work_dir: Path, rec: dict) -> Path:
    """写入/更新一条历史记录。"""
    d = history_dir(work_dir)
    d.mkdir(parents=True, exist_ok=True)
    rec = dict(rec)
    rec.setdefault("finished_at", time.strftime("%Y-%m-%dT%H:%M:%S"))
    p = record_path(work_dir, rec.get("hash", "unknown"))
    p.write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
    return p


def list_all(work_dir: Path) -> list[dict]:
    """列出全部历史记录，按完成时间倒序。"""
    d = history_dir(work_dir)
    if not d.is_dir():
        return []
    out = []
    for p in d.glob("*.json"):
        try:
            out.append(json.loads(p.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            continue
    out.sort(key=lambda r: str(r.get("finished_at", "")), reverse=True)
    return out


def summary(work_dir: Path) -> dict:
    records = list_all(work_dir)
    total_size = sum(int(r.get("size", 0) or 0) for r in records)
    return {
        "count": len(records),
        "total_bytes": total_size,
        "total_gb": round(total_size / 1024 ** 3, 2),
        "records": records,
    }
