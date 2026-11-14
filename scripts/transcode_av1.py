#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 douyu-vod-toolkit contributors
"""把视频转成 AV1（支持 GPU 硬件编码 + CRF 质量档）。

关于 CRF 的重要说明
--------------------
ffmpeg 的 `-crf` 只有 **CPU 编码器**（libsvtav1 / libaom-av1）真正支持。
NVIDIA 的 `av1_nvenc` 会静默忽略 `-crf`（ffmpeg 日志会提示
"Codec AVOption crf ... has not been used for any stream"）。

NVENC 的等效做法是恒定量化参数：
    -rc constqp -qp <N>
实测 `-qp 18` 与 CPU 的 `-crf 18` 输出体积几乎一致（3.76MB vs 3.62MB / 60s），
所以本脚本在 GPU 模式下把用户填的 CRF 直接映射成 QP。

编码器一览（速度以 60 秒 720P 为参考，RTX 4060 Laptop）：
    av1_nvenc  -rc constqp -qp 18   ~56-65 倍速   体积≈CPU CRF18
    libsvtav1  -crf 18 -preset 6     ~4.4 倍速    真 CRF
    libaom-av1 -crf 18 -cpu-used 6   ~0.19 倍速   真 CRF（格式工厂用的就是这个）

用法：
    python scripts/transcode_av1.py <输入文件或目录> [-o 输出目录]
                                    [--encoder nvenc|svt|aom]
                                    [--crf 18] [--preset 6] [--delete]
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

# 编码器预设：name -> (ffmpeg 参数构造, 说明)
ENCODERS = {
    "nvenc": {
        "label": "NVIDIA GPU（最快，CRF 映射为 QP）",
        "build": lambda crf, preset: [
            "-c:v", "av1_nvenc", "-rc", "constqp", "-qp", str(crf),
            "-preset", f"p{preset if 1 <= preset <= 7 else 5}",
        ],
    },
    "svt": {
        "label": "SVT-AV1（CPU，真 CRF，速度均衡）",
        "build": lambda crf, preset: [
            "-c:v", "libsvtav1", "-crf", str(crf),
            "-preset", str(preset if 0 <= preset <= 13 else 6),
        ],
    },
    "aom": {
        "label": "libaom-AV1（CPU，真 CRF，最慢）",
        "build": lambda crf, preset: [
            "-c:v", "libaom-av1", "-crf", str(crf), "-b:v", "0",
            "-cpu-used", str(preset if 0 <= preset <= 8 else 6), "-row-mt", "1",
        ],
    },
}


def find_ffmpeg(cfg) -> str:
    """定位 ffmpeg：配置 -> bin/ -> PATH。"""
    cand = str(getattr(cfg, "ffmpeg", "") or "").strip()
    if cand and Path(cand).is_file():
        return cand
    root = Path(__file__).resolve().parent.parent
    local = root / "bin" / "ffmpeg.exe"
    if local.is_file():
        return str(local)
    found = shutil.which("ffmpeg")
    return found or "ffmpeg"


def probe_duration(ff: str, src: Path) -> float:
    """用 ffprobe/ffmpeg 读时长（秒）。失败返回 0。"""
    ffprobe = str(Path(ff).with_name("ffprobe.exe"))
    if Path(ffprobe).is_file():
        try:
            out = subprocess.run(
                [ffprobe, "-v", "error", "-show_entries", "format=duration",
                 "-of", "default=nw=1:nk=1", str(src)],
                capture_output=True, text=True, timeout=60,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            return float(out.stdout.strip() or 0)
        except (ValueError, OSError, subprocess.SubprocessError):
            pass
    return 0


def transcode_one(ff: str, src: Path, dst: Path, encoder: str,
                  crf: int, preset: int, keep_audio: bool = True) -> tuple[bool, str]:
    """转码单个文件。返回 (是否成功, 说明)。"""
    spec = ENCODERS.get(encoder) or ENCODERS["nvenc"]
    vargs = spec["build"](crf, preset)
    aargs = ["-c:a", "copy"] if keep_audio else ["-c:a", "aac", "-b:a", "192k"]

    cmd = [ff, "-hide_banner", "-loglevel", "error", "-stats",
           "-i", str(src), *vargs, *aargs,
           "-map_metadata", "0", "-y", str(dst)]

    t0 = time.time()
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, errors="replace",
                           creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    except OSError as e:
        return False, f"启动 ffmpeg 失败: {e}"
    cost = time.time() - t0

    if p.returncode != 0 or not dst.is_file() or dst.stat().st_size < 10240:
        err = (p.stderr or "").strip().splitlines()
        return False, (err[-1] if err else f"ffmpeg 返回 {p.returncode}")

    src_mb = src.stat().st_size / 1048576
    dst_mb = dst.stat().st_size / 1048576
    ratio = (dst_mb / src_mb * 100) if src_mb else 0
    return True, f"{src_mb:.1f}MB -> {dst_mb:.1f}MB（{ratio:.0f}%）耗时 {cost:.0f}s"


def main() -> None:
    ap = argparse.ArgumentParser(description="转码为 AV1")
    ap.add_argument("input", help="输入文件或目录")
    ap.add_argument("-o", "--output", default="", help="输出目录（默认与源同目录）")
    ap.add_argument("--encoder", default="nvenc", choices=list(ENCODERS),
                    help="编码器：nvenc(GPU) / svt(CPU) / aom(CPU)")
    ap.add_argument("--crf", type=int, default=18, help="质量档（越小越好，默认 18）")
    ap.add_argument("--preset", type=int, default=5,
                    help="nvenc:1-7 / svt:0-13 / aom:0-8")
    ap.add_argument("--delete", action="store_true", help="成功后删除源文件")
    ap.add_argument("--audio-encode", action="store_true", help="音频重编码为 AAC 192k")
    args = ap.parse_args()

    cfg = load()
    ff = find_ffmpeg(cfg)
    if not Path(ff).is_file() and not shutil.which(ff):
        print(f"找不到 ffmpeg：{ff}", file=sys.stderr)
        raise SystemExit(1)

    src = Path(args.input)
    if src.is_dir():
        files = sorted([p for p in src.rglob("*")
                        if p.is_file() and p.suffix.lower() in VIDEO_EXTS])
    elif src.is_file():
        files = [src]
    else:
        print(f"输入不存在：{src}", file=sys.stderr)
        raise SystemExit(1)

    # 跳过已有的临时/中间文件
    files = [f for f in files if "-ts" not in f.parts and not f.name.startswith("output")]

    if not files:
        print("没有可转码的视频文件")
        return

    outdir = Path(args.output) if args.output else None
    if outdir:
        outdir.mkdir(parents=True, exist_ok=True)

    spec_label = ENCODERS[args.encoder]["label"]
    print(f"编码器: {spec_label}")
    print(f"质量档: {args.crf}  (preset {args.preset})")
    print(f"待处理: {len(files)} 个文件")
    if args.encoder == "nvenc":
        print("提示: GPU 模式下 CRF 会映射为 NVENC 的恒定 QP（等效画质）")
    print("", flush=True)

    ok = fail = 0
    t_all = time.time()
    for i, f in enumerate(files, 1):
        dst = (outdir / f"{f.stem}.av1.mp4") if outdir else f.with_name(f"{f.stem}.av1.mp4")
        if dst.exists() and dst.stat().st_size > 10240:
            print(f"[{i}/{len(files)}] 跳过（已存在）{dst.name}", flush=True)
            ok += 1
            continue
        print(f"[{i}/{len(files)}] {f.name}", flush=True)
        good, msg = transcode_one(ff, f, dst, args.encoder, args.crf,
                                  args.preset, not args.audio_encode)
        if good:
            ok += 1
            print(f"  ✔ {msg}", flush=True)
            if args.delete:
                try:
                    f.unlink()
                    print("  （已删除源文件）", flush=True)
                except OSError as e:
                    print(f"  删除失败: {e}", flush=True)
        else:
            fail += 1
            print(f"  ✘ {msg}", flush=True)

    el = time.time() - t_all
    print("", flush=True)
    print(f"完成: 成功 {ok}，失败 {fail}，总用时 {el / 60:.1f} 分钟")
    # 给 GUI 解析用的机器可读行
    print("TRANSCODE_DONE " + json.dumps(
        {"ok": ok, "fail": fail, "seconds": round(el, 1)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
