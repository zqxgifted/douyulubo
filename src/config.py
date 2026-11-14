# SPDX-License-Identifier: MIT
# Copyright (c) 2026 douyu-vod-toolkit contributors
"""统一配置加载（Python 侧）。

不含任何真实账号、设备号、本机路径或会话信息。

优先级（高 -> 低）：
  1. 环境变量 DOUYU_CONFIG 指向的 JSON 文件
  2. 当前工作目录下的 config.json
  3. DOUYU_* 环境变量
  4. 内置默认值

`up_id` 与 `work_dir` 为必填项：未提供时直接报错退出，不会回落到任何真实主播。
`did` 未提供时每次运行随机生成 32 位 hex（接口允许），也可在配置里固定。
"""

from __future__ import annotations

import json
import os
import secrets
import sys
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)

# 明显是占位符的值一律视为「未配置」，避免把示例值当成真实 ID 跑起来
_PLACEHOLDERS = {"", "<UP_ID>", "REPLACE_WITH_UP_ID", "YOUR_UP_ID", "xxx"}

_DEFAULTS = {
    "concurrent": 2,
    "ffmpeg": "ffmpeg",              # 依赖 PATH；不要写死本机绝对路径
    "danmaku_factory": "",           # XML -> ASS 时才需要
    "ua": DEFAULT_UA,
    "did": "",
    "workers_per_task": 8,
    "min_file_mb": 100,
    "anchor_name": "",               # 只写进弹幕 XML 元数据，可留空
    "quality": "highest",            # highest | original | 1080p | 720p | 540p | 480p | 360p | audio
    "danmaku_mode": "ass",           # ass | xml | none
    # ---- 弹幕排版参数（对应 DanmakuFactory 同名配置，详见 docs/DANMAKU.md）----
    "font_size": 50,
    "font_size_strict": False,
    "scroll_duration": 8.0,
    "fixed_duration": 4.5,
    "line_spacing": 0,
    "top_margin": 0,
    "bottom_margin": 0,
    "opacity": 255,
    "outline": 1.0,
    "shadow": 0.0,
    "bold": False,
    "displayarea": 1.0,
    "scrollarea": 1.0,
    "time_shift": 0.0,
    "no_overlap": True,
    "block_types": [],
    # ---- 转码（下载后自动）----
    # 开源默认用 h265：兼容性好、体积小、所有 NVENC 显卡都支持。
    # AV1 压缩率更高但需要 RTX 40 系以上，适合在本地 config.json 里覆盖。
    "transcode_enabled": False,
    "transcode_codec": "h265",       # h265 | av1 | h264
    "transcode_quality": "balanced", # high | balanced | small | tiny
    "transcode_qp": -1,              # >=0 时直接指定 QP，覆盖 quality
    "transcode_preset": 5,           # GPU preset 1-7
    "transcode_delete_src": False,
    "transcode_audio_encode": False,
    "transcode_suffix": "",         # 文件名后缀，如 AV1 -> xxx_AV1.mp4
    "transcode_merge_ts": True,     # 直接从 ts 分片合并转码（不产生中间 mp4）

}

_ENV_KEYS = {
    "up_id": "DOUYU_UP_ID",
    "work_dir": "DOUYU_WORK_DIR",
    "ffmpeg": "DOUYU_FFMPEG",
    "danmaku_factory": "DOUYU_DANMAKU_FACTORY",
    "ua": "DOUYU_UA",
    "did": "DOUYU_DID",
    "concurrent": "DOUYU_CONCURRENT",
    "workers_per_task": "DOUYU_WORKERS_PER_TASK",
    "min_file_mb": "DOUYU_MIN_FILE_MB",
    "transcode_codec": "DOUYU_TRANSCODE_CODEC",
    "transcode_quality": "DOUYU_TRANSCODE_QUALITY",
    "anchor_name": "DOUYU_ANCHOR_NAME",
    "quality": "DOUYU_QUALITY",
    "danmaku_mode": "DOUYU_DANMAKU_MODE",
}

_INT_KEYS = {"concurrent", "workers_per_task", "min_file_mb", "transcode_qp", "transcode_preset"}


@dataclass
class Config:
    up_id: str
    work_dir: Path
    concurrent: int = 2
    ffmpeg: str = "ffmpeg"
    danmaku_factory: str = ""
    ua: str = DEFAULT_UA
    did: str = ""
    workers_per_task: int = 8
    min_file_mb: int = 100
    anchor_name: str = ""
    quality: str = "highest"         # 默认优先最高清晰度
    danmaku_mode: str = "ass"        # 默认下载弹幕并转 ASS
    # 弹幕排版参数
    font_size: int = 50
    font_size_strict: bool = False
    scroll_duration: float = 8.0
    fixed_duration: float = 4.5
    line_spacing: int = 0
    top_margin: int = 0
    bottom_margin: int = 0
    opacity: int = 255
    outline: float = 1.0
    shadow: float = 0.0
    bold: bool = False
    displayarea: float = 1.0
    scrollarea: float = 1.0
    time_shift: float = 0.0
    no_overlap: bool = True
    block_types: list = field(default_factory=list)
    # 转码（下载后自动）
    transcode_enabled: bool = False
    transcode_codec: str = "h265"        # h265 | av1 | h264
    transcode_quality: str = "balanced"  # high | balanced | small | tiny
    transcode_qp: int = -1               # >=0 时覆盖 quality
    transcode_preset: int = 5
    transcode_delete_src: bool = False
    transcode_audio_encode: bool = False
    transcode_suffix: str = ""
    transcode_merge_ts: bool = True
    raw: dict = field(default_factory=dict, repr=False)

    def danmaku_options(self):
        """构造 src.danmaku_ass.Options。"""
        from .danmaku_ass import Options  # 延迟导入，避免循环依赖
        return Options(
            font_name="微软雅黑",
            font_size=self.font_size,
            font_size_strict=self.font_size_strict,
            scroll_duration=self.scroll_duration,
            fixed_duration=self.fixed_duration,
            line_spacing=self.line_spacing,
            top_margin=self.top_margin,
            bottom_margin=self.bottom_margin,
            opacity=self.opacity,
            outline=self.outline,
            shadow=self.shadow,
            bold=self.bold,
            displayarea=self.displayarea,
            scrollarea=self.scrollarea,
            time_shift=self.time_shift,
            no_overlap=self.no_overlap,
            block_types=list(self.block_types or []),
        )

    # 固定目录布局（全部位于 work_dir 下，便于跨平台与避免中文路径问题）
    @property
    def data_dir(self) -> Path:
        return self.work_dir / "data"

    @property
    def download_dir(self) -> Path:
        return self.work_dir / "downloads"

    @property
    def danmaku_dir(self) -> Path:
        return self.work_dir / "danmaku"

    @property
    def danmaku_ass_dir(self) -> Path:
        return self.work_dir / "danmaku_ass"

    @property
    def tmp_dir(self) -> Path:
        return self.work_dir / "tmp"

    def ensure_dirs(self) -> None:
        for d in (
            self.data_dir,
            self.download_dir,
            self.danmaku_dir,
            self.danmaku_ass_dir,
            self.tmp_dir,
        ):
            d.mkdir(parents=True, exist_ok=True)

    def headers(self) -> dict:
        return {"User-Agent": self.ua}


def _project_root() -> Path:
    """项目根目录（src/ 的上一级）。"""
    return Path(__file__).resolve().parent.parent


def _read_one(p: Path) -> dict:
    """读单个 JSON 配置，失败返回空字典。"""
    if not p.is_file():
        return {}
    try:
        # utf-8-sig 兼容 Windows 工具生成的带 BOM 文件
        data = json.loads(p.read_text(encoding="utf-8-sig"))
        return {k: v for k, v in data.items() if not k.startswith("_")} \
            if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as e:
        print(f"[config] 无法读取 {p}: {e}", file=sys.stderr)
        return {}


def _read_file_cfg() -> dict:
    """按优先级合并配置文件。

    顺序（后者覆盖前者）：
      1. config/defaults.json   通用默认（进仓库）
      2. config/user.json       用户私有（.gitignore，不进仓库）
      3. DOUYU_CONFIG 指定文件   临时覆盖
      4. 旧位置 ./config.json    向后兼容
    """
    root = _project_root()
    merged: dict = {}
    merged.update(_read_one(root / "config" / "defaults.json"))
    merged.update(_read_one(root / "config" / "user.json"))

    env_path = os.environ.get("DOUYU_CONFIG", "")
    if env_path:
        merged.update(_read_one(Path(env_path)))

    # 兼容旧位置（若存在则优先级最高）
    merged.update(_read_one(root / "config.json"))
    return merged


def load() -> Config:
    file_cfg = _read_file_cfg()
    merged = dict(_DEFAULTS)
    merged.update({k: v for k, v in file_cfg.items() if v is not None})

    # 环境变量覆盖
    for key, env in _ENV_KEYS.items():
        val = os.environ.get(env)
        if val is not None and val != "":
            merged[key] = val

    for key in _INT_KEYS:
        try:
            merged[key] = int(merged[key])
        except (TypeError, ValueError):
            merged[key] = _DEFAULTS[key]

    up_id = str(merged.get("up_id", "") or "").strip()
    work_dir = str(merged.get("work_dir", "") or "").strip()
    if up_id in _PLACEHOLDERS:
        _die("缺少 up_id：请在 config/user.json 填写，或设置 DOUYU_UP_ID。\n"
             "up_id 是主播录播页 https://v.douyu.com/author/<up_id> 里那段 ID。")
    if work_dir in _PLACEHOLDERS or work_dir in {".", ".."}:
        # 留空时用默认目录：脚本所在项目根下的 downloads
        root = Path(__file__).resolve().parent.parent
        work_dir = str(root / "downloads")

    did = str(merged.get("did", "") or "").strip()
    if not did:
        did = secrets.token_hex(16)  # 32 位 hex，接口允许随机设备号

    return Config(
        up_id=up_id,
        work_dir=Path(work_dir).expanduser().resolve(),
        concurrent=merged["concurrent"],
        ffmpeg=str(merged["ffmpeg"]),
        danmaku_factory=str(merged["danmaku_factory"]),
        ua=str(merged["ua"]),
        did=did,
        workers_per_task=merged["workers_per_task"],
        min_file_mb=merged["min_file_mb"],
        anchor_name=str(merged["anchor_name"]),
        quality=str(merged["quality"]),
        danmaku_mode=str(merged["danmaku_mode"]),
        transcode_enabled=bool(merged.get("transcode_enabled", False)),
        transcode_codec=str(merged.get("transcode_codec") or "h265"),
        transcode_quality=str(merged.get("transcode_quality") or "balanced"),
        transcode_qp=int(merged.get("transcode_qp", -1)),
        transcode_preset=int(merged.get("transcode_preset", 5)),
        transcode_delete_src=bool(merged.get("transcode_delete_src", False)),
        transcode_audio_encode=bool(merged.get("transcode_audio_encode", False)),
        transcode_suffix=str(merged.get("transcode_suffix") or ""),
        transcode_merge_ts=bool(merged.get("transcode_merge_ts", True)),
        font_size=int(merged["font_size"]),
        font_size_strict=bool(merged["font_size_strict"]),
        scroll_duration=float(merged["scroll_duration"]),
        fixed_duration=float(merged["fixed_duration"]),
        line_spacing=int(merged["line_spacing"]),
        top_margin=int(merged["top_margin"]),
        bottom_margin=int(merged["bottom_margin"]),
        opacity=int(merged["opacity"]),
        outline=float(merged["outline"]),
        shadow=float(merged["shadow"]),
        bold=bool(merged["bold"]),
        displayarea=float(merged["displayarea"]),
        scrollarea=float(merged["scrollarea"]),
        time_shift=float(merged["time_shift"]),
        no_overlap=bool(merged["no_overlap"]),
        block_types=list(merged["block_types"] or []),
        raw=file_cfg,
    )


def _die(msg: str) -> None:
    print(f"[config] {msg}", file=sys.stderr)
    raise SystemExit(2)


def _add_src_to_path() -> None:
    """供 scripts/ 下的脚本调用：把仓库 src/ 加入 sys.path。"""
    root = Path(__file__).resolve().parent.parent
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))


if __name__ == "__main__":
    c = load()
    print(json.dumps({
        "up_id": c.up_id,
        "work_dir": str(c.work_dir),
        "data_dir": str(c.data_dir),
        "download_dir": str(c.download_dir),
        "danmaku_dir": str(c.danmaku_dir),
        "ffmpeg": c.ffmpeg,
        "did": c.did,
    }, ensure_ascii=False, indent=2))
