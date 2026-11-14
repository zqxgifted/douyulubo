#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 douyulubo contributors
"""启动入口：双击走 GUI；作为 Python 解释器时走 --run-py。

两种调用形态（同一个 exe / 同一个 py）：
  1) 无参数                     → 启动图形界面
  2) --run-py <script.py> ...   → 用内置解释器执行脚本，参数原样透传

形态 2 让「完整包」不必额外携带 python.exe：douyu.mjs 会把 DOUYU_PY 指向本 exe，
然后以 `--run-py scripts/xxx.py` 调用 Python 脚本。

依赖处理：
  * 完整包(bin\\ 里有 node/ffmpeg) → 直接用包内的
  * 代码包(bin\\ 里没有)           → 自动找系统 PATH / 常见安装位置
  * 都找不到                       → 弹窗说明缺什么、去哪下载、放到哪里
"""
from __future__ import annotations

import io
import os
import runpy
import sys
from pathlib import Path


def resource_root() -> Path:
    """资源根目录：打包后 = exe 所在目录；源码运行 = 项目根。"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


ROOT = resource_root()


# ---------------------------------------------------------------------------
# 形态 2：作为 Python 解释器
# ---------------------------------------------------------------------------
def _rebind_std_streams() -> None:
    """PyInstaller --noconsole 下 sys.stdout/stderr 可能为 None，按 fd 重绑。"""
    if sys.stdout is None:
        try:
            sys.stdout = io.TextIOWrapper(
                open(1, "wb", closefd=False), encoding="utf-8",
                errors="replace", line_buffering=True)
        except Exception:  # noqa: BLE001
            sys.stdout = io.StringIO()
    if sys.stderr is None:
        try:
            sys.stderr = io.TextIOWrapper(
                open(2, "wb", closefd=False), encoding="utf-8",
                errors="replace", line_buffering=True)
        except Exception:  # noqa: BLE001
            sys.stderr = io.StringIO()
    try:
        sys.stdout.reconfigure(line_buffering=True)
        sys.stderr.reconfigure(line_buffering=True)
    except Exception:  # noqa: BLE001
        pass


def run_py(argv: list[str]) -> int:
    if not argv:
        print("用法: douyulubo.exe --run-py <script.py> [args...]", file=sys.stderr)
        return 2

    # 解释器自检用法
    if argv[0] in ("--version", "-V"):
        print(sys.version.split()[0])
        return 0
    if argv[0] == "-c" and len(argv) > 1:
        _rebind_std_streams()
        try:
            exec(compile(argv[1], "<string>", "exec"), {"__name__": "__main__"})
        except SystemExit as e:
            return int(e.code) if isinstance(e.code, int) else 0
        except Exception:  # noqa: BLE001
            import traceback
            traceback.print_exc()
            return 1
        return 0

    script = Path(argv[0]).resolve()
    if not script.is_file():
        print(f"脚本不存在: {script}", file=sys.stderr)
        return 2

    _rebind_std_streams()
    # 强制 UTF-8 输出：Windows 默认 GBK，管道里会变乱码
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    if str(script.parent.parent) not in sys.path:
        sys.path.insert(0, str(script.parent.parent))
    sys.argv = [str(script), *argv[1:]]
    try:
        runpy.run_path(str(script), run_name="__main__")
    except SystemExit as e:
        return int(e.code) if isinstance(e.code, int) else (0 if e.code is None else 1)
    except Exception:  # noqa: BLE001
        import traceback
        traceback.print_exc()
        return 1
    return 0


# ---------------------------------------------------------------------------
# 形态 1：GUI
# ---------------------------------------------------------------------------
def check_dependencies() -> list[str]:
    """解析依赖并把结果注入环境；返回缺失组件名列表。"""
    sys.path.insert(0, str(ROOT / "gui"))
    import deps  # noqa: E402

    resolved = deps.resolve_all()
    env_updates = deps.build_env()
    # 把解析结果写回当前进程环境，GUI 与子进程都受益
    for k in ("PATH", "DOUYU_PY", "DOUYU_FFMPEG"):
        if k in env_updates:
            os.environ[k] = env_updates[k]
    return deps.missing(resolved)


def show_missing(missing: list[str]) -> None:
    """缺失依赖提示：说清缺什么、为什么需要、去哪下载、放哪里。"""
    import tkinter as tk
    from tkinter import messagebox
    sys.path.insert(0, str(ROOT / "gui"))
    import deps

    lines = ["缺少以下必要组件，相关功能无法使用：", ""]
    for name in missing:
        info = deps.DEPENDENCY_INFO[name]
        lines.append(f"● {info['label']} —— {info['why']}")
        lines.append(f"    下载：{info['url']}")
        lines.append(f"    做法：{info['hint']}")
        lines.append("")
    lines.append(f"也可以把它们直接放到：{ROOT / 'bin'}")
    lines.append("放好后重新打开本程序即可自动识别。")

    r = tk.Tk()
    r.withdraw()
    messagebox.showwarning("缺少必要组件", "\n".join(lines))
    r.destroy()


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] == "--run-py":
        return run_py(sys.argv[2:])

    missing = check_dependencies()
    if missing:
        show_missing(missing)

    sys.path.insert(0, str(ROOT / "gui"))
    from app import App  # noqa: E402
    App().mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
