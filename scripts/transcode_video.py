#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 douyu-vod-toolkit contributors
"""视频转码：H.264 / H.265 / AV1，支持 GPU 硬件编码。

QP 量程换算（重要）
-------------------
不同编码器的 QP 刻度不一样，同样数字画质差很多：

    h264_nvenc / hevc_nvenc : QP 0-51
    av1_nvenc               : QP 0-255   ← 刻度约 4 倍

用户只需要选「质量档」，本脚本按编码器自动换算成对应刻度，
避免出现「选了 AV1 结果文件反而变大」这种困惑。

质量档定义（以 h264 QP 为基准）：
    high      h264:20  hevc:20  av1:80
    balanced  h264:26  hevc:26  av1:104   ← 默认
    small     h264:30  hevc:30  av1:120
    tiny      h264:36  hevc:36  av1:144

实测参考（720p 849kbps 374秒源片，43.9MB）：
    AV1  qp=80  -> 15.6MB    qp=104 -> 12.0MB
    H265 qp=26  -> 14.0MB    qp=30  -> 11.0MB

用法：
    python scripts/transcode_video.py <输入> [-o 输出目录]
        [--codec av1|h265|h264] [--quality balanced] [--qp 数值]
        [--preset 5] [--delete] [--audio-encode]
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.config import load  # noqa: E402

VIDEO_EXTS = {".mp4", ".flv", ".ts", ".mkv", ".mov", ".avi", ".webm", ".m4v"}

# 编码器定义：QP 上限、默认 preset、显示名
CODECS = {
    "av1": {"encoder": "av1_nvenc", "qp_max": 255, "label": "AV1（压缩率最高）"},
    "h265": {"encoder": "hevc_nvenc", "qp_max": 51, "label": "H.265 / HEVC"},
    "h264": {"encoder": "h264_nvenc", "qp_max": 51, "label": "H.264（兼容性最好）"},
}

# 质量档 -> 以 h264 为基准的 QP；实际用时会按编码器换算
QUALITY_LEVELS = {
    "high": {"h264": 20, "label": "高画质（接近原片）"},
    "balanced": {"h264": 26, "label": "平衡（推荐）"},
    "small": {"h264": 30, "label": "省空间"},
    "tiny": {"h264": 36, "label": "极限压缩"},
}

# AV1 的 QP 刻度约为 H.264 的 4 倍
_AV1_SCALE = 4


def qp_of(codec: str, quality: str) -> int:
    """把质量档换算成该编码器的 QP。"""
    base = QUALITY_LEVELS.get(quality, QUALITY_LEVELS["balanced"])["h264"]
    if codec == "av1":
        return min(255, base * _AV1_SCALE)
    return min(51, base)


def find_ffmpeg(cfg) -> str:
    cand = str(getattr(cfg, "ffmpeg", "") or "").strip()
    if cand and Path(cand).is_file():
        return cand
    root = Path(__file__).resolve().parent.parent
    local = root / "bin" / "ffmpeg.exe"
    if local.is_file():
        return str(local)
    return shutil.which("ffmpeg") or "ffmpeg"


def transcode_one(ff: str, src: Path, dst: Path, codec: str, qp: int,
                  preset: int, copy_audio: bool = True) -> tuple[bool, str]:
    spec = CODECS.get(codec) or CODECS["h265"]
    enc = spec["encoder"]
    # GPU 编码器：preset 用 p1-p7
    p = preset if 1 <= preset <= 7 else 5
    vargs = ["-c:v", enc, "-rc", "constqp", "-qp", str(qp), "-preset", f"p{p}"]
    aargs = ["-c:a", "copy"] if copy_audio else ["-c:a", "aac", "-b:a", "192k"]

    cmd = [ff, "-hide_banner", "-loglevel", "error", "-i", str(src),
           *vargs, *aargs, "-map_metadata", "0", "-y", str(dst)]

    t0 = time.time()
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, errors="replace",
                           creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    except OSError as e:
        return False, f"启动 ffmpeg 失败: {e}"
    cost = time.time() - t0

    if r.returncode != 0 or not dst.is_file() or dst.stat().st_size < 10240:
        err = (r.stderr or "").strip().splitlines()
        return False, (err[-1] if err else f"ffmpeg 返回 {r.returncode}")

    sm = src.stat().st_size / 1048576
    dm = dst.stat().st_size / 1048576
    return True, f"{sm:.1f}MB -> {dm:.1f}MB（{dm / sm * 100:.0f}%）耗时 {cost:.0f}s"


def main() -> None:
    ap = argparse.ArgumentParser(description="视频转码（H.264 / H.265 / AV1）")
    ap.add_argument("input", help="输入文件或目录")
    ap.add_argument("-o", "--output", default="", help="输出目录")
    ap.add_argument("--codec", default="h265", choices=list(CODECS))
    ap.add_argument("--quality", default="balanced", choices=list(QUALITY_LEVELS))
    ap.add_argument("--qp", type=int, default=-1, help="直接指定 QP（覆盖 quality）")
    ap.add_argument("--preset", type=int, default=5, help="GPU preset p1(快)-p7(好)")
    ap.add_argument("--preview", type=int, default=0,
                    help="只转前 N 秒估算体积（不保留输出）")
    ap.add_argument("--delete", action="store_true", help="成功后删除源文件")
    ap.add_argument("--audio-encode", action="store_true", help="音频重编码 AAC 192k")
    args = ap.parse_args()

    cfg = load()
    ff = find_ffmpeg(cfg)
    if not Path(ff).is_file() and not shutil.which(ff):
        print(f"找不到 ffmpeg：{ff}", file=sys.stderr)
        raise SystemExit(1)

    src = Path(args.input)
    if src.is_dir():
        files = sorted(p for p in src.rglob("*")
                       if p.is_file() and p.suffix.lower() in VIDEO_EXTS)
    elif src.is_file():
        files = [src]
    else:
        print(f"输入不存在：{src}", file=sys.stderr)
        raise SystemExit(1)

    # 跳过临时目录与中间文件
    files = [f for f in files if "-ts" not in f.parts and not f.name.startswith("output")]
    if not files:
        print("没有可转码的视频文件")
        return

    qp = args.qp if args.qp >= 0 else qp_of(args.codec, args.quality)
    spec = CODECS[args.codec]
    print(f"编码器: {spec['label']}  ({spec['encoder']})")
    print(f"质量档: {args.quality}  ->  QP {qp}")
    print(f"待处理: {len(files)} 个文件", flush=True)
    print("", flush=True)

    outdir = Path(args.output) if args.output else None
    if outdir:
        outdir.mkdir(parents=True, exist_ok=True)

    if args.preview > 0:
        f = files[0]
        dst = Path(os.environ.get("TEMP", ".")) / f"_preview.{args.codec}.mp4"
        print(f"试算: {f.name} 前 {args.preview} 秒", flush=True)
        spec2 = CODECS[args.codec]
        cmd = [ff, "-hide_banner", "-loglevel", "error", "-t", str(args.preview),
               "-i", str(f), "-c:v", spec2["encoder"], "-rc", "constqp",
               "-qp", str(qp), "-preset", f"p{args.preset}",
               "-c:a", "copy", "-y", str(dst)]
        t1 = time.time()
        subprocess.run(cmd, capture_output=True,
                       creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        if dst.is_file() and dst.stat().st_size > 10240:
            mb = dst.stat().st_size / 1048576
            dur = 0.0
            try:
                pr = subprocess.run(
                    [str(Path(ff).with_name("ffprobe.exe")), "-v", "error",
                     "-show_entries", "format=duration", "-of", "default=nw=1:nk=1",
                     str(f)],
                    capture_output=True, text=True,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
                dur = float(pr.stdout.strip() or 0)
            except (ValueError, OSError, subprocess.SubprocessError):
                pass
            est = mb * (dur / args.preview) if dur > args.preview else mb
            print(f"  {args.preview} 秒输出 {mb:.2f} MB，耗时 {time.time() - t1:.0f}s")
            if dur > 0:
                print(f"  全片 {dur:.0f} 秒，预计约 {est:.1f} MB")
            dst.unlink(missing_ok=True)
        else:
            print("  试算失败")
        print("TRANSCODE_DONE " + json.dumps({"preview": True}, ensure_ascii=False))
        return

    ok = fail = 0
    t0 = time.time()
    for i, f in enumerate(files, 1):
        suffix = "." + args.codec
        dst = ((outdir / f"{f.stem}{suffix}.mp4") if outdir
               else f.with_name(f"{f.stem}{suffix}.mp4"))
        if dst.exists() and dst.stat().st_size > 10240:
            print(f"[{i}/{len(files)}] 跳过（已存在）{dst.name}", flush=True)
            ok += 1
            continue
        print(f"[{i}/{len(files)}] {f.name}", flush=True)
        good, msg = transcode_one(ff, f, dst, args.codec, qp,
                                  args.preset, not args.audio_encode)
        if good:
            ok += 1
            print(f"  OK {msg}", flush=True)
            if args.delete:
                try:
                    f.unlink()
                    print("  （已删除源文件）", flush=True)
                except OSError as e:
                    print(f"  删除失败: {e}", flush=True)
        else:
            fail += 1
            print(f"  失败 {msg}", flush=True)

    el = time.time() - t0
    print("", flush=True)
    print(f"完成: 成功 {ok}，失败 {fail}，用时 {el / 60:.1f} 分钟")
    print("TRANSCODE_DONE " + json.dumps(
        {"ok": ok, "fail": fail, "seconds": round(el, 1)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
