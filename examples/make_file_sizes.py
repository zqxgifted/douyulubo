#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""示例：从本地下载目录生成 util_bitrate_stats.py 需要的 --sizes 清单。

用法：
    python examples/make_file_sizes.py <下载目录> <输出.json>

它只做「文件名 -> hash」的关联示范：真实项目里请在下载清单
(data/download_list.json) 里保留 hash 与文件名的映射，再据此生成。
本示例演示一种不依赖任何私有数据的通用做法：扫描目录里所有 .mp4，
把文件大小导出，hash 字段留空时统计脚本会跳过该行。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("用法: python examples/make_file_sizes.py <下载目录> <输出.json>")
    src = Path(sys.argv[1])
    out = Path(sys.argv[2])
    rows = []
    for p in sorted(src.rglob("*.mp4")):
        rows.append({"hash": "", "file": p.name, "size": p.stat().st_size})
    out.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"已导出 {len(rows)} 个文件到 {out}")
    print("提示：请把 hash 填成 download_list.json 里对应的 hash_id 后再跑统计。")


if __name__ == "__main__":
    main()
