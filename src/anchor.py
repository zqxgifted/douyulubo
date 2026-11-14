# SPDX-License-Identifier: MIT
# Copyright (c) 2026 douyu-vod-toolkit contributors
"""主播 ID 解析与清晰度档位定义（Python 侧）。

支持粘贴这类链接自动解析：
    https://v.douyu.com/author-replay/AbCdEf123456
    https://v.douyu.com/author/AbCdEf123456
    https://v.douyu.com/author/AbCdEf123456?page=1
    AbCdEf123456                                （直接给 ID）
"""
from __future__ import annotations

import json
import re
import urllib.request

UP_ID_PATTERN = re.compile(r"/author(?:-replay)?/([A-Za-z0-9]+)")
BARE_ID_PATTERN = re.compile(r"^[A-Za-z0-9]{6,32}$")

API_SHOW_LIST = "https://v.douyu.com/wgapi/vod/center/authorShowVideoList"
DEFAULT_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")

# 清晰度档位：值与 douyu 返回的画质名 / bit_rate 匹配
QUALITY_PRESETS = [
    ("highest", "优先最高清晰度（默认）"),
    ("original", "原画（等同最高）"),
    ("1080p", "1080P"),
    ("720p", "720P"),
    ("540p", "540P"),
    ("480p", "480P"),
    ("360p", "360P"),
    ("audio", "纯音频"),
]

# 各档位优先匹配的画质名关键词（按顺序尝试）
QUALITY_ALIASES = {
    "original": ["原画", "原畫", "1080p60", "1440p"],
    "1080p": ["1080", "原画", "高清 1080"],
    "720p": ["720", "high", "高清"],
    "540p": ["540"],
    "480p": ["480", "normal", "标清"],
    "360p": ["360", "low", "流畅"],
    "audio": ["audio", "音频"],
}


def parse_up_id(text: str) -> str | None:
    """从链接或裸 ID 中解析出 up_id；解析不出返回 None。"""
    if not text:
        return None
    s = text.strip()
    m = UP_ID_PATTERN.search(s)
    if m:
        return m.group(1)
    if BARE_ID_PATTERN.match(s):
        return s
    return None


def fetch_anchor_name(up_id: str, ua: str = DEFAULT_UA, timeout: int = 15) -> str | None:
    """通过公开接口取主播昵称；失败返回 None（不抛异常）。"""
    url = f"{API_SHOW_LIST}?up_id={up_id}&page=1&limit=1"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": ua})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8"))
    except Exception:  # noqa: BLE001
        return None

    d = data.get("data") or {}
    # 常见位置：data.list[0].nickname / data.nickname / data.author.nickname
    for path in (
        lambda o: (o.get("list") or [{}])[0].get("nickname"),
        lambda o: o.get("nickname"),
        lambda o: (o.get("author") or {}).get("nickname"),
        lambda o: (o.get("list") or [{}])[0].get("author"),
    ):
        try:
            v = path(d)
            if v and isinstance(v, str) and v.strip():
                return v.strip()
        except Exception:  # noqa: BLE001
            continue
    return None


def quality_aliases(quality: str) -> list[str]:
    """返回某档位应尝试匹配的关键词列表（含自身）。"""
    q = str(quality or "highest").strip()
    if q in QUALITY_ALIASES:
        return QUALITY_ALIASES[q]
    return [q] if q else []
