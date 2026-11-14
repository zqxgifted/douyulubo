#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 douyu-vod-toolkit contributors
"""从斗鱼 ts 分片直接合并 + 转码为单文件（不产生中间 mp4）。

为什么直接读 ts
---------------
斗鱼下载下来的是 m3u8 分片（segment00000.ts ...），它们本身就是完整的 h264 视频。
先拼成 mp4 再转码会：
  1. 多一次全片磁盘读写（1 小时录播约 2-3GB）
  2. 封装对齐会丢约 0.5-1 秒时长（实测 375.33s 的分片拼成 mp4 变 374.73s）

ffmpeg 的 concat 支持「读取时拼接」，所以合并与编码可以一趟完成。

命名规则
--------
    <场次时间> <标题> P<N> <分段场次>
    例：2021-04-01 21:30 4.1你信不信 反正我信了 P1 21点场.mp4

    带后缀时：2021-04-01 21:30 4.1你信不信 反正我信了 P1 21点场_AV1.mp4
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.config import load  # noqa: E402

# 编码器：codec -> (gpu 编码器, QP 上限)
CODECS = {
    "av1": ("av1_nvenc", 255),
    "h265": ("hevc_nvenc", 51),
    "h264": ("h264_nvenc", 51),
}
# 质量档 -> h264 基准 QP
QUALITY_QP = {"high": 20, "balanced": 26, "small": 30, "tiny": 36}
AV1_SCALE = 4

_BAD_CHARS = re.compile(r'[\\/:*?"<>|\r\n\t]')


def safe_name(s: str, limit: int = 120) -> str:
    """去掉 Windows 非法字符，压掉多余空格。"""
    s = _BAD_CHARS.sub("_", str(s or ""))
    s = re.sub(r"\s+", " ", s).strip()
    return s[:limit]


def strip_show_prefix(title: str) -> str:
    """把标题清理成纯内容。

    『【2021-04-01 21点场】某主播：4.1你信不信』 -> 『4.1你信不信』
    『6.19 我来拉！ 2019-06-19 22点场』            -> 『6.19 我来拉！』
    """
    s = str(title or "")
    # 去掉【...】前缀
    s = re.sub(r"^【[^】]*】", "", s).strip()
    # 去掉「主播名：」前缀（取第一个冒号后的内容）
    for sep in ("：", ":"):
        if sep in s:
            head, tail = s.split(sep, 1)
            if len(head) <= 20 and tail.strip():
                s = tail.strip()
                break
    # 去掉尾部的日期 + 场次（如「 2019-06-19 22点场」「 20200202 20点场」）
    s = re.sub(r"\s*\d{4}-\d{2}-\d{2}\s*\d{1,2}点场\s*$", "", s).strip()
    s = re.sub(r"\s*\d{4}-\d{2}-\d{2}\s*$", "", s).strip()
    return s


def build_filename(seg: dict, show: dict, suffix: str = "", ext: str = "mp4") -> str:
    """按「场次时间 标题 P<N> 分段场次」拼文件名。"""
    # 时间统一用「分段自身」的 time_str：
    #   show.time_str 是整场开播时间（如 17:42），
    #   seg.time_str  是本段起播时间（如 19:00），文件名里用后者才不矛盾。
    when = str(seg.get("time_str") or "").strip()
    if not when:
        when = str(show.get("time_str") or "").strip()
    if not when:
        when = str(seg.get("date") or "").strip()
    # 冒号在 Windows 文件名里非法 -> 用短横
    when = when.replace(":", "-").replace("：", "-")

    title = strip_show_prefix(seg.get("title") or show.get("title") or "")

    seg_no = int(seg.get("seg_no") or 1)
    seg_total = int(seg.get("seg_total") or 1)
    remark = str(seg.get("seg_remark") or "").strip()

    parts = []
    if when:
        parts.append(safe_name(when, 40))
    if title:
        parts.append(safe_name(title, 60))
    # P1 / P2 只在多分段时加，单段不写 P1
    if seg_total > 1:
        p = f"P{seg_no}"
        if remark:
            p += f" {remark}"
        parts.append(safe_name(p, 30))
    elif remark:
        parts.append(safe_name(remark, 30))

    name = " ".join(x for x in parts if x).strip() or str(seg.get("hash_id") or "video")
    if suffix:
        name += f"_{safe_name(suffix, 20)}"
    return f"{name}.{ext}"


def _match_dir(dir_name: str, by_hash: dict[str, dict]) -> dict:
    """把 ts 目录名（如 20210204_2217-ts）匹配到分段元数据。

    优先精确匹配「日期_时分」，匹配不到再按日期+小时模糊匹配。
    """
    m = re.match(r"(\d{8})_(\d{4})", dir_name)
    if not m:
        return {}
    ymd, hm = m.group(1), m.group(2)
    want_date = f"{ymd[0:4]}-{ymd[4:6]}-{ymd[6:8]}"
    want_hm = f"{hm[0:2]}:{hm[2:4]}"

    # 精确：日期 + 时分都对上
    for g in by_hash.values():
        if str(g.get("date") or "") == want_date and want_hm in str(g.get("time_str") or ""):
            return g
    # 退化：只比日期 + 小时
    for g in by_hash.values():
        ts = str(g.get("time_str") or "")
        if str(g.get("date") or "") == want_date and ts[11:13] == hm[0:2]:
            return g
    # 最后：只比日期
    for g in by_hash.values():
        if str(g.get("date") or "") == want_date:
            return g
    return {}


def find_ffmpeg(cfg) -> str:
    cand = str(getattr(cfg, "ffmpeg", "") or "").strip()
    if cand and Path(cand).is_file():
        return cand
    root = Path(__file__).resolve().parent.parent
    local = root / "bin" / "ffmpeg.exe"
    if local.is_file():
        return str(local)
    return shutil.which("ffmpeg") or "ffmpeg"


def qp_of(codec: str, quality: str, explicit: int = -1) -> int:
    if explicit >= 0:
        return explicit
    base = QUALITY_QP.get(quality, 26)
    return min(255, base * AV1_SCALE) if codec == "av1" else min(51, base)


def concat_ts(ff: str, ts_dir: Path, dst: Path, codec: str, qp: int,
              preset: int, audio_copy: bool = False) -> tuple[bool, str]:
    """把 ts 分片直接转成一个文件。"""
    segs = sorted(ts_dir.glob("segment*.ts"))
    if not segs:
        return False, "目录里没有 segment*.ts"
    # 注意：只取 segment*.ts，排除任何 output.ts 残留
    lst = Path(os.environ.get("TEMP", ".")) / f"_concat_{ts_dir.name}.txt"
    lst.write_text(
        "\n".join(f"file '{p.as_posix()}'" for p in segs),
        encoding="utf-8")

    enc, _ = CODECS.get(codec, CODECS["av1"])
    p = preset if 1 <= preset <= 7 else 5
    aargs = ["-c:a", "copy"] if audio_copy else ["-c:a", "aac", "-b:a", "192k"]
    cmd = [ff, "-hide_banner", "-loglevel", "error",
           "-f", "concat", "-safe", "0", "-i", str(lst),
           "-c:v", enc, "-rc", "constqp", "-qp", str(qp), "-preset", f"p{p}",
           *aargs, "-y", str(dst)]

    t0 = time.time()
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, errors="replace",
                           creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    except OSError as e:
        return False, f"启动 ffmpeg 失败: {e}"
    finally:
        lst.unlink(missing_ok=True)

    if r.returncode != 0 or not dst.is_file() or dst.stat().st_size < 10240:
        err = (r.stderr or "").strip().splitlines()
        return False, (err[-1] if err else f"rc={r.returncode}")

    src_mb = sum(s.stat().st_size for s in segs) / 1048576
    dst_mb = dst.stat().st_size / 1048576
    return True, (f"{len(segs)} 片 {src_mb:.0f}MB -> {dst_mb:.1f}MB"
                  f"（{dst_mb / src_mb * 100:.0f}%）{time.time() - t0:.0f}s")


def main() -> None:
    ap = argparse.ArgumentParser(description="ts 分片直接合并转码")
    ap.add_argument("ts_dir", help="包含 segment*.ts 的目录（或上层目录）")
    ap.add_argument("-o", "--output", default="", help="输出目录")
    ap.add_argument("--codec", default="av1", choices=list(CODECS))
    ap.add_argument("--quality", default="balanced", choices=list(QUALITY_QP))
    ap.add_argument("--qp", type=int, default=-1)
    ap.add_argument("--preset", type=int, default=5)
    ap.add_argument("--suffix", default="", help="文件名后缀，如 AV1")
    ap.add_argument("--delete-ts", action="store_true", help="成功后删除 ts 目录")
    ap.add_argument("--audio-copy", action="store_true", help="音频直接复制（更快）")
    args = ap.parse_args()

    cfg = load()
    ff = find_ffmpeg(cfg)
    if not Path(ff).is_file() and not shutil.which(ff):
        print(f"找不到 ffmpeg：{ff}", file=sys.stderr)
        raise SystemExit(1)

    root = Path(args.ts_dir)
    if not root.is_dir():
        print(f"目录不存在：{root}", file=sys.stderr)
        raise SystemExit(1)

    # 识别分片目录：自身含 segment*.ts，或子目录里含 segment*.ts
    # 命名有两种：斗鱼风格 xxx-ts、下载器临时目录 douyulubo-seg-<md5>
    def _has_segs(d: Path) -> bool:
        return any(d.glob("segment*.ts"))

    if _has_segs(root):
        dirs = [root]
    else:
        dirs = sorted(d for d in root.iterdir()
                      if d.is_dir() and (_has_segs(d) or d.name.endswith("-ts")))

    # 下载脚本会把保留的分片目录记在 pending_ts.json 里
    pending_file = cfg.data_dir / "pending_ts.json"
    pending: dict = {}
    if pending_file.is_file():
        try:
            pending = json.loads(pending_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            pending = {}

    # 若传进来的是下载目录，把 pending 里的分片目录也纳入处理范围
    pending_dirs = []
    for hid, info in pending.items():
        d = Path(str(info.get("dir") or ""))
        if d.is_dir() and list(d.glob("segment*.ts")):
            pending_dirs.append(d)
    if pending_dirs and root == Path(args.output or root):
        pass
    # 把 pending 目录合并进来（去重）
    seen = {d.resolve() for d in dirs}
    for d in pending_dirs:
        if d.resolve() not in seen:
            dirs.append(d)
            seen.add(d.resolve())

    # 读分段元数据，用于生成中文名
    meta_file = cfg.data_dir / "segments_index.json"
    shows_file = cfg.data_dir / "shows_index.json"
    by_hash: dict[str, dict] = {}
    if meta_file.is_file():
        try:
            for g in json.loads(meta_file.read_text(encoding="utf-8")):
                by_hash[str(g.get("hash_id"))] = g
        except (OSError, json.JSONDecodeError):
            pass
    by_show: dict[str, dict] = {}
    if shows_file.is_file():
        try:
            for s in json.loads(shows_file.read_text(encoding="utf-8")):
                by_show[str(s.get("show_id"))] = s
        except (OSError, json.JSONDecodeError):
            pass

    qp = qp_of(args.codec, args.quality, args.qp)
    enc, _ = CODECS[args.codec]
    print(f"编码器: {enc}  QP={qp}  preset=p{args.preset}")
    print(f"待处理: {len(dirs)} 个 ts 目录", flush=True)
    print("", flush=True)

    outdir = Path(args.output) if args.output else None
    if outdir:
        outdir.mkdir(parents=True, exist_ok=True)

    ok = fail = 0
    t_all = time.time()
    for i, d in enumerate(dirs, 1):
        segs = sorted(d.glob("segment*.ts"))
        if not segs:
            print(f"[{i}/{len(dirs)}] 跳过（无分片）{d.name}", flush=True)
            continue
        # 优先：从 pending_ts.json 反查（key 就是 hash，最准）
        info = {}
        for hid, pinfo in pending.items():
            if Path(str(pinfo.get("dir") or "")).name == d.name:
                info = by_hash.get(hid, {})
                if not info:
                    info = {"hash_id": hid}
                break
        if not info:
            # 退化：按目录名（日期_时分）匹配
            info = _match_dir(d.name, by_hash)
        show = by_show.get(str(info.get("show_id")), {})
        fname = build_filename(info, show, args.suffix, "mp4")
        dst = (outdir / fname) if outdir else d.parent / fname

        if dst.exists() and dst.stat().st_size > 10240:
            print(f"[{i}/{len(dirs)}] 跳过（已存在）{dst.name}", flush=True)
            ok += 1
            continue

        print(f"[{i}/{len(dirs)}] {d.name}", flush=True)
        print(f"  -> {fname}", flush=True)
        good, msg = concat_ts(ff, d, dst, args.codec, qp, args.preset, args.audio_copy)
        if good:
            ok += 1
            print(f"  OK {msg}", flush=True)
            if args.delete_ts:
                shutil.rmtree(d, ignore_errors=True)
                print("  （已删除 ts 目录）", flush=True)
        else:
            fail += 1
            print(f"  失败 {msg}", flush=True)

    el = time.time() - t_all
    print("", flush=True)
    print(f"完成: 成功 {ok}，失败 {fail}，用时 {el / 60:.1f} 分钟")
    print("TRANSCODE_DONE " + json.dumps(
        {"ok": ok, "fail": fail, "seconds": round(el, 1)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
