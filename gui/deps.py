# SPDX-License-Identifier: MIT
# Copyright (c) 2026 douyulubo contributors
"""依赖探测与解析（完整包 / 代码包共用）。

查找顺序（对每个组件都一样）：
    1. 包内 bin\\ 目录        —— 完整包自带
    2. 系统 PATH              —— 用户已装并加进环境变量
    3. 常见安装位置            —— Node 默认目录、ffmpeg 常见路径等
    4. 用户在 config.json 里指定的路径（ffmpeg 支持）

三个组件：
    node    —— 下载 / 取流 / 探测脚本（必需）
    ffmpeg  —— TS→MP4 转封装（必需）
    python  —— 只脚本部分需要；完整包里由 exe 自带，代码包用系统 Python
"""
from __future__ import annotations

import json
import os
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path

# 每个组件的说明与下载指引（给用户看的中文提示）
DEPENDENCY_INFO = {
    "node": {
        "label": "Node.js",
        "why": "下载视频、取流、探测清晰度都要用它",
        "url": "https://nodejs.org/zh-cn/download",
        "home": "https://nodejs.org/",
        "hint": "下载 LTS 版（长期支持版）的 Windows 安装包，一路默认安装即可",
        "file": "node.exe",
    },
    "ffmpeg": {
        "label": "ffmpeg",
        "why": "把下载的分片合并转成 mp4",
        "url": "https://github.com/BtbN/FFmpeg-Builds/releases",
        "home": "https://ffmpeg.org/download.html",
        "hint": ("下载 ffmpeg-master-latest-win64-gpl.zip，解压后把里面的 ffmpeg.exe "
                 "放进 bin 文件夹；或把它的 bin 目录加到系统 PATH"),
        "file": "ffmpeg.exe",
    },
    "python": {
        "label": "Python",
        "why": "抓清单、抓弹幕、转换字幕这几步要用",
        "url": "https://www.python.org/downloads/windows/",
        "home": "https://www.python.org/",
        "hint": "安装时务必勾选「Add Python to PATH」",
        "file": "python.exe",
    },
}


@dataclass
class Resolved:
    """单个组件的解析结果。"""
    name: str
    path: str | None = None
    source: str = ""          # "bundle" | "path" | "common" | "config" | ""
    extra: dict = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return bool(self.path)

    @property
    def from_bundle(self) -> bool:
        return self.source == "bundle"


def _root() -> Path:
    """包根目录：打包后=exe 所在目录；源码运行=项目根。"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


ROOT = _root()


def _common_locations() -> dict[str, list[str]]:
    """各组件在 Windows 上的常见安装位置。"""
    pf = os.environ.get("ProgramFiles", r"C:\Program Files")
    pf86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
    local = os.environ.get("LOCALAPPDATA", "")
    roaming = os.environ.get("APPDATA", "")
    return {
        "node": [
            rf"{pf}\nodejs\node.exe",
            rf"{pf86}\nodejs\node.exe",
            rf"{local}\Programs\nodejs\node.exe",
        ],
        "ffmpeg": [
            rf"{pf}\ffmpeg\bin\ffmpeg.exe",
            r"D:\ffmpeg\bin\ffmpeg.exe",
            r"C:\ffmpeg\bin\ffmpeg.exe",
            rf"{local}\Microsoft\WinGet\Links\ffmpeg.exe",
            # 本机常见的 scoop / choco 位置
            rf"{local}\Programs\ffmpeg\bin\ffmpeg.exe",
        ],
        "python": [
            rf"{local}\Programs\Python\Python312\python.exe",
            rf"{local}\Programs\Python\Python311\python.exe",
            rf"{local}\Programs\Python\Python310\python.exe",
            rf"{pf}\Python312\python.exe",
            rf"{pf}\Python311\python.exe",
            rf"{roaming}\..\Local\Programs\Python\Python312\python.exe",
        ],
    }


def _config_value(key: str):
    """读 config.json 里的配置（不抛异常）。"""
    p = ROOT / "config.json"
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8-sig")).get(key)
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None


def resolve(name: str) -> Resolved:
    """解析一个组件的位置。

    优先级：
      1. config.json 里手动指定的路径（用户在设置页填的，最高优先）
      2. 包内 bin\\
      3. 系统 PATH
      4. 常见安装位置
    """
    info = DEPENDENCY_INFO[name]
    exe_name = info["file"]

    # 1) 用户手动指定（config 里的 node_path / ffmpeg / python_path）
    cfg_key = {"node": "node_path", "ffmpeg": "ffmpeg", "python": "python_path"}[name]
    cfg = _config_value(cfg_key)
    if cfg and str(cfg).strip():
        p = Path(str(cfg).strip())
        if p.is_file():
            return Resolved(name, str(p), "config")

    # 2) 包内 bin\
    bundle = ROOT / "bin" / exe_name
    if bundle.is_file():
        return Resolved(name, str(bundle), "bundle")

    # 3) 系统 PATH
    found = shutil.which(exe_name) or shutil.which(name)
    if found:
        return Resolved(name, found, "path")

    # 4) 常见位置
    for cand in _common_locations().get(name, []):
        if cand and Path(cand).is_file():
            return Resolved(name, str(cand), "common")

    # 5) Python 特殊：当前解释器本身就能用
    if name == "python" and sys.executable and not getattr(sys, "frozen", False):
        return Resolved(name, sys.executable, "common")

    return Resolved(name, None, "")


def resolve_all() -> dict[str, Resolved]:
    return {n: resolve(n) for n in DEPENDENCY_INFO}


def missing(resolved: dict[str, Resolved] | None = None) -> list[str]:
    r = resolved or resolve_all()
    return [n for n, v in r.items() if not v.ok]


def build_env(base: dict | None = None) -> dict:
    """构造子进程环境：优先用解析到的真实路径。"""
    env = dict(base or os.environ)
    bindir = ROOT / "bin"
    if bindir.is_dir():
        env["PATH"] = str(bindir) + os.pathsep + env.get("PATH", "")

    # 把用户手动指定的目录也加进 PATH，便于相关工具链找到彼此的依赖
    for name in ("node", "ffmpeg"):
        r = resolve(name)
        if r.ok and not r.from_bundle:
            d = str(Path(r.path).parent)
            if d not in env.get("PATH", ""):
                env["PATH"] = d + os.pathsep + env.get("PATH", "")

    # Python 解释器：打包的 exe 自己就是解释器
    if getattr(sys, "frozen", False):
        env["DOUYU_PY"] = str(Path(sys.executable).resolve())
    else:
        py = resolve("python")
        if py.ok:
            env["DOUYU_PY"] = py.path

    # ffmpeg 路径显式传给脚本，避免脚本里再猜
    ff = resolve("ffmpeg")
    if ff.ok:
        env["DOUYU_FFMPEG"] = ff.path
    return env


def node_path(env: dict | None = None) -> str | None:
    """取 node 可执行文件的绝对路径（GUI 起子进程用）。"""
    r = resolve("node")
    if r.ok:
        return r.path
    e = env or os.environ
    return shutil.which("node", path=e.get("PATH"))


def summary_lines(resolved: dict[str, Resolved] | None = None) -> list[tuple[str, str, str]]:
    """返回 [(状态, 名称, 说明)]，给 GUI / 日志展示。"""
    r = resolved or resolve_all()
    src_label = {"bundle": "包内自带", "path": "系统 PATH",
                 "common": "常见安装位置", "config": "设置里指定", "": ""}
    out = []
    for name, res in r.items():
        info = DEPENDENCY_INFO[name]
        if res.ok:
            out.append(("ok", f"{info['label']}",
                        f"{src_label.get(res.source, res.source)}：{res.path}"))
        else:
            out.append(("miss", f"{info['label']}", info["why"]))
    return out


if __name__ == "__main__":
    r = resolve_all()
    for status, label, text in summary_lines(r):
        mark = "OK  " if status == "ok" else "MISS"
        print(f"[{mark}] {label:10s} {text}")
    miss = missing(r)
    if miss:
        print("\n缺少组件，下载地址：")
        for n in miss:
            info = DEPENDENCY_INFO[n]
            print(f"  {info['label']}: {info['url']}")
            print(f"    {info['hint']}")
