#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""工具 — 由「本地文件大小 ÷ 斗鱼官方时长」估算平均码率并分档。

用法：
    DOUYU_CONFIG=/path/to/config.json python scripts/util_bitrate_stats.py \
        --sizes data/file_sizes.json

输入 --sizes 是一个 JSON 数组，每项形如：
    [{"hash": "<分段 hash_id>", "size": 2345000000}, ...]
  （例如从网盘清单导出，或本地 stat 后生成；本工具不绑定任何网盘/会话数据）

输出：控制台摘要 + data/bitrate.json
"""
from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.config import load  # noqa: E402

BUCKETS = [
    (5.0, "≥5.0 Mbps（很高，1080p 级）"),
    (2.6, "2.6–5.0 Mbps（≈720p）"),
    (1.6, "1.6–2.6 Mbps（中间）"),
    (0.9, "0.9–1.6 Mbps（≈480p）"),
    (0.0, "<0.9 Mbps（低）"),
]


def bucket_of(mbps: float) -> str:
    for lo, name in BUCKETS:
        if mbps >= lo:
            return name
    return BUCKETS[-1][1]


def main() -> None:
    ap = argparse.ArgumentParser(description="估算录播平均码率")
    ap.add_argument("--sizes", required=True, help="JSON 数组文件：[{hash, size}]")
    ap.add_argument("--min-duration", type=float, default=600.0,
                    help="忽略时长小于该秒数的分段（默认 600）")
    args = ap.parse_args()

    cfg = load()
    cfg.ensure_dirs()
    detail_file = cfg.data_dir / "raw_detail.json"
    if not detail_file.is_file():
        raise SystemExit(f"缺少 {detail_file}，请先运行 step2_fetch_detail.py")
    detail = json.loads(detail_file.read_text(encoding="utf-8"))
    sizes = json.loads(Path(args.sizes).read_text(encoding="utf-8"))

    rows = []
    for s in sizes:
        h = s.get("hash")
        sz = float(s.get("size") or 0)
        d = float((detail.get(h) or {}).get("duration_sec") or 0)
        if sz <= 0 or d < args.min_duration:
            continue
        mbps = sz * 8 / d / 1e6
        rows.append({"hash": h, "folder": (detail.get(h) or {}).get("folder", ""),
                     "size": sz, "duration_sec": d, "mbps": round(mbps, 3)})

    (cfg.data_dir / "bitrate.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")

    if not rows:
        print("没有可估算的分段（检查 --sizes 与 raw_detail.json 是否匹配）。")
        return

    bs = sorted(r["mbps"] for r in rows)
    print(f"可估算的场次：{len(rows)}（时长 > {args.min_duration / 60:.0f} 分钟）\n")
    print(f"码率 Mbps：最小 {bs[0]:.2f}  中位 {bs[len(bs) // 2]:.2f}  最大 {bs[-1]:.2f}")

    counts = collections.Counter(bucket_of(r["mbps"]) for r in rows)
    print("\n码率分档：")
    for _, name in BUCKETS:
        print(f"  {name}: {counts.get(name, 0):4d}")

    print("\n最低的 10 个：")
    for r in sorted(rows, key=lambda x: x["mbps"])[:10]:
        print(f"  {r['hash'][:16]} | {r['mbps']:.2f} Mbps | {r['size'] / 1048576:6.0f}MB / {r['duration_sec'] / 60:5.0f}min")
    print("\n明细已存 data/bitrate.json")


if __name__ == "__main__":
    main()
