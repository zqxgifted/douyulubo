# SPDX-License-Identifier: MIT
"""生成蓝色鲸鱼图标（.ico + .png），纯标准库实现，不依赖 Pillow。

做法：自己画点阵（带抗锯齿）再手写 ICO/BMP 与 PNG 文件格式。
运行：python gui/make_icon.py
"""
from __future__ import annotations

import os
import struct
import zlib

# ---- 颜色 ----
BLUE_TOP = (56, 150, 235)
BLUE_BOT = (24, 96, 200)
WHITE = (255, 255, 255)
EYE = (26, 92, 184)

SIZES = [16, 24, 32, 48, 64, 128, 256]


def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def _blend(dst, src, alpha: float):
    """按 alpha 混合两个 RGB。"""
    return tuple(int(_lerp(dst[i], src[i], alpha) + 0.5) for i in range(3))


def render(size: int) -> list[list[tuple[int, int, int, int]]]:
    """渲染一张 size×size 的 RGBA 图（返回行优先的二维数组）。"""
    SS = 4                      # 超采样倍数，用于抗锯齿
    N = size * SS
    px = [[(0, 0, 0, 0)] * N for _ in range(N)]

    cx = cy = N / 2.0
    R = N / 2.0

    def in_circle(x: float, y: float) -> bool:
        return (x - cx) ** 2 + (y - cy) ** 2 <= R * R

    def in_ellipse(x: float, y: float, x0, y0, x1, y1) -> bool:
        ex = (x0 + x1) / 2.0
        ey = (y0 + y1) / 2.0
        rx = (x1 - x0) / 2.0
        ry = (y1 - y0) / 2.0
        if rx <= 0 or ry <= 0:
            return False
        return ((x - ex) / rx) ** 2 + ((y - ey) / ry) ** 2 <= 1.0

    def in_tri(x, y, p1, p2, p3) -> bool:
        def sign(ax, ay, bx, by, px_, py_):
            return (px_ - bx) * (ay - by) - (ax - bx) * (py_ - by)
        d1 = sign(p1[0], p1[1], p2[0], p2[1], x, y)
        d2 = sign(p2[0], p2[1], p3[0], p3[1], x, y)
        d3 = sign(p3[0], p3[1], p1[0], p1[1], x, y)
        has_neg = (d1 < 0) or (d2 < 0) or (d3 < 0)
        has_pos = (d1 > 0) or (d2 > 0) or (d3 > 0)
        return not (has_neg and has_pos)

    # 形状参数（相对 1.0 的比例）
    body = (0.16, 0.40, 0.78, 0.72)
    tail = ((0.74, 0.55), (0.92, 0.38), (0.90, 0.68))
    eye = (0.28, 0.48, 0.36, 0.56)
    spout = ((0.50, 0.40), (0.50, 0.255))
    drops = [(0.42, 0.225, 0.036), (0.50, 0.165, 0.044), (0.58, 0.225, 0.036)]

    for j in range(N):
        for i in range(N):
            x, y = i + 0.5, j + 0.5
            if not in_circle(x, y):
                continue
            # 背景竖向渐变
            t = y / N
            bg = tuple(int(_lerp(BLUE_TOP[k], BLUE_BOT[k], t) + 0.5) for k in range(3))
            col = bg
            # 鲸鱼身体
            if (in_ellipse(x, y, *(v * N for v in body))
                    or in_tri(x, y, *[(px_ * N, py_ * N) for px_, py_ in tail])):
                col = WHITE
            # 眼睛
            if in_ellipse(x, y, *(v * N for v in eye)):
                col = EYE
            # 水花
            for dx, dy, rr in drops:
                if (x - dx * N) ** 2 + (y - dy * N) ** 2 <= (rr * N) ** 2:
                    col = WHITE
            # 水柱（细矩形）
            x0, y0 = spout[0][0] * N, spout[1][1] * N
            x1, y1 = spout[1][0] * N, spout[0][1] * N
            if x0 - N * 0.010 <= x <= x0 + N * 0.010 and y0 <= y <= y1:
                col = WHITE
            px[j][i] = (col[0], col[1], col[2], 255)

    # 缩小回目标尺寸（盒式平均 → 抗锯齿）
    out = [[(0, 0, 0, 0)] * size for _ in range(size)]
    area = SS * SS
    for y in range(size):
        for x in range(size):
            r = g = b = a = 0
            for dy in range(SS):
                for dx in range(SS):
                    c = px[y * SS + dy][x * SS + dx]
                    r += c[0]; g += c[1]; b += c[2]; a += c[3]
            out[y][x] = (r // area, g // area, b // area, a // area)
    return out


def _png_bytes(rows, size: int) -> bytes:
    """手写 PNG（32 位 RGBA）。"""
    raw = bytearray()
    for y in range(size):
        raw.append(0)  # filter type 0
        for x in range(size):
            r, g, b, a = rows[y][x]
            raw += bytes((r, g, b, a))

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    ihdr = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(bytes(raw), 9))
            + chunk(b"IEND", b""))


def _bmp_bytes(rows, size: int) -> bytes:
    """ICO 内嵌的 BMP（含 AND 掩码）。"""
    header = struct.pack("<IiiHHIIiiII", 40, size, size * 2, 1, 32, 0, 0, 0, 0, 0, 0)
    pixels = bytearray()
    for y in range(size - 1, -1, -1):      # BMP 自下而上
        for x in range(size):
            r, g, b, a = rows[y][x]
            pixels += bytes((b, g, r, a))
    mask_row = ((size + 31) // 32) * 4
    mask = bytearray(mask_row * size)
    for y in range(size):
        src_y = size - 1 - y
        for x in range(size):
            if rows[src_y][x][3] == 0:
                mask[y * mask_row + (x // 8)] |= 1 << (7 - (x % 8))
    return header + bytes(pixels) + bytes(mask)


def main() -> None:
    base = os.path.dirname(os.path.abspath(__file__))

    entries = []
    for s in SIZES:
        rows = render(s)
        entries.append((s, _bmp_bytes(rows, s)))
        print(f"  rendered {s}x{s}")

    # 组装 ICO
    count = len(entries)
    header = struct.pack("<HHH", 0, 1, count)
    offset = 6 + 16 * count
    dir_entries = b""
    data = b""
    for s, bmp in entries:
        dim = 0 if s >= 256 else s
        dir_entries += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(bmp), offset)
        offset += len(bmp)
        data += bmp

    ico = os.path.join(base, "whale.ico")
    with open(ico, "wb") as f:
        f.write(header + dir_entries + data)
    print("saved:", ico, os.path.getsize(ico), "bytes")

    # PNG（窗口图标用）
    png = os.path.join(base, "whale.png")
    with open(png, "wb") as f:
        f.write(_png_bytes(render(256), 256))
    print("saved:", png, os.path.getsize(png), "bytes")


if __name__ == "__main__":
    main()
