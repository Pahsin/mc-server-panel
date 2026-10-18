# -*- coding: utf-8 -*-
"""生成面板图标（草方块），纯标准库写 PNG + ICO，不依赖 Pillow。"""
import struct
import zlib
from pathlib import Path

SIZE = 256
W = H = SIZE


def chunk(t: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + t + data + struct.pack(">I", zlib.crc32(t + data) & 0xFFFFFFFF)


def png_bytes(rgba: bytearray, w: int, h: int) -> bytes:
    raw = b"".join(b"\x00" + bytes(rgba[y * w * 4:(y + 1) * w * 4]) for y in range(h))
    ihdr = struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def build() -> bytearray:
    px = bytearray(W * H * 4)
    rnd = __import__("random").Random(20261017)

    L, T, R, B = 24, 24, 232, 232          # 方块范围
    GRASS = T + 60                         # 草皮层基准厚度
    cells = {}
    for cy in range((B - T) // 8 + 1):
        for cx in range((R - L) // 8 + 1):
            cells[(cx, cy)] = rnd.random()

    # 草土交界做成高低不平的锯齿，像原版草方块侧面
    edge = {}
    for cx in range((R - L) // 8 + 2):
        edge[cx] = int(rnd.uniform(-9, 11))

    for y in range(T, B):
        for x in range(L, R):
            # 圆角
            if (x < L + 10 and y < T + 10 and (L + 10 - x) ** 2 + (T + 10 - y) ** 2 > 100) or \
               (x > R - 11 and y < T + 10 and (x - (R - 11)) ** 2 + (T + 10 - y) ** 2 > 100) or \
               (x < L + 10 and y > B - 11 and (L + 10 - x) ** 2 + (y - (B - 11)) ** 2 > 100) or \
               (x > R - 11 and y > B - 11 and (x - (R - 11)) ** 2 + (y - (B - 11)) ** 2 > 100):
                continue

            cx, cy = (x - L) // 8, (y - T) // 8
            c = cells.get((cx, cy), 0.5)
            grass_end = GRASS + edge.get(cx, 0)

            if y < grass_end:
                n = 0.35 * c + 0.65 * (1.0 if (x // 8 + y // 8) % 3 else c)
                if n > 0.58:
                    col = (96, 162, 100)
                elif n > 0.30:
                    col = (74, 138, 80)
                else:
                    col = (58, 118, 65)
                if y >= grass_end - 5:               # 草层底边压暗，形成厚度感
                    col = tuple(int(v * 0.82) for v in col)
            else:
                n = c
                if n > 0.66:
                    col = (152, 106, 69)
                elif n > 0.33:
                    col = (135, 92, 58)
                else:
                    col = (117, 78, 48)
                if y < grass_end + 4:                 # 土层顶边阴影
                    col = tuple(int(v * 0.80) for v in col)

            # 左侧高光 / 底部阴影
            if x < L + 4:
                col = tuple(min(255, v + 22) for v in col)
            if x > R - 5:
                col = tuple(int(v * 0.78) for v in col)
            if y > B - 5:
                col = tuple(int(v * 0.74) for v in col)

            i = (y * W + x) * 4
            px[i:i + 4] = bytes((*col, 255))
    return px


def main():
    out = Path(__file__).resolve().parent
    rgba = build()
    png = png_bytes(rgba, W, H)
    (out / "icon.png").write_bytes(png)

    hdr = struct.pack("<HHH", 0, 1, 1)
    entry = struct.pack("<BBBBHHII", 0, 0, 0, 0, 1, 32, len(png), 22)
    (out / "icon.ico").write_bytes(hdr + entry + png)
    print("icon.png", (out / "icon.png").stat().st_size, "bytes")
    print("icon.ico", (out / "icon.ico").stat().st_size, "bytes")


if __name__ == "__main__":
    main()
