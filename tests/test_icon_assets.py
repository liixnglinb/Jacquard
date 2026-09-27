# -*- coding: utf-8 -*-
"""图标资产本身的清晰度契约。

这些是"图标看着发虚"真正的守门条件：ico 少了某一档，Windows 在 150% 缩放下
就会拿 32 强缩成 24；黑底白字标的竖笔一旦掉到 2 列以下，任务栏上先没的就是它。
两者都不会被别的测试碰到。
"""
import io
import re
import struct
from pathlib import Path

import pytest

Image = pytest.importorskip("PIL.Image")

BASE = Path(__file__).resolve().parents[1]
ASSETS = BASE / "assets"
STATIC = BASE / "static"

# 20/24/40 是给 125%/150%/175% 缩放用的，缺哪一档哪一档就是系统帮你硬缩
ICO_SIZES = [16, 20, 24, 32, 40, 48, 64, 128, 256]


def _frames():
    data = (ASSETS / "loom.ico").read_bytes()
    count = struct.unpack("<H", data[4:6])[0]
    out = {}
    for i in range(count):
        o = 6 + i * 16
        w, h, _cc, _r, _pl, bpp, size, off = struct.unpack("<BBBBHHII", data[o:o + 16])
        payload = data[off:off + size]
        slot = w or 256
        img = Image.open(io.BytesIO(payload)).convert("RGBA")
        out[slot] = (img, payload, bpp)
    return out


def test_ico_declares_every_size_it_actually_carries():
    frames = _frames()
    assert sorted(frames) == ICO_SIZES, (
        f"ico 档位不对，缺的会被系统强行缩放：{set(ICO_SIZES) ^ set(frames)}")
    for slot, (img, payload, bpp) in frames.items():
        assert img.size == (slot, slot), f"{slot}x{slot} 槽里装的是 {img.size}"
        assert bpp == 32, f"{slot}x{slot} 不是 32 位"
        assert payload[:8] == b"\x89PNG\r\n\x1a\n", f"{slot}x{slot} 不是 PNG 载荷"


@pytest.mark.parametrize("n", [16, 20, 24, 32, 40])
def test_small_marks_read_as_a_j(n):
    """黑底白字标在任务栏上的可读条件：竖笔至少 2 列、横脚至少是竖笔的两倍宽、
    记号高度占画面一半以上。2026-09-27 字标从 L 水平镜像成 J（随改名），于是
    "对齐"那条从左边换到**右边**：竖笔与横脚右端齐，否则就成了 T 或 I。
    还多了一条 J 才有的判据 —— 钩尖与竖笔之间那段负空间至少 2 列，
    少了它 16px 上就连成一坨（实测各档都有 5~6 列）。
    缩略图糊掉通常不是"认不出是哪个字母"，而是竖笔先没 —— 所以盯最窄那一行。"""
    px = _frames()[n][0].load()

    def light(x, y):
        r, g, b, a = px[x, y]
        return a >= 40 and r > 200 and g > 200 and b > 200

    rows = [[x for x in range(n) if light(x, y)] for y in range(n)]
    glyph = [r for r in rows if r]
    assert len(glyph) >= n * 0.5, f"{n}px 上记号只占 {len(glyph)} 行高，太小了"
    stem = min(len(r) for r in glyph)
    foot = max(len(r) for r in glyph)
    assert stem >= 2, f"{n}px 竖笔只有 {stem} 列，任务栏上会先没"
    assert foot >= stem * 2, f"{n}px 横脚 {foot} 列 / 竖笔 {stem} 列，读不出是 J"
    assert glyph[0][-1] == glyph[-1][-1],         f"{n}px 竖笔右端 {glyph[0][-1]} 与横脚右端 {glyph[-1][-1]} 不齐"

    # 钩尖：找一行里出现两段独立笔画的，量它们之间的黑列数
    gaps = []
    for y in range(n):
        runs, start = [], None
        prev = None
        for x in range(n):
            if light(x, y):
                if start is None:
                    start = x
                prev = x
            elif start is not None:
                runs.append((start, prev))
                start = None
        if start is not None:
            runs.append((start, prev))
        if len(runs) >= 2:
            gaps.append(runs[1][0] - runs[0][1] - 1)
    assert gaps, f"{n}px 上没有一行出现两段笔画 —— 钩尖丢了，字标退回成了直角括号"
    assert min(gaps) >= 2, f"{n}px 钩尖与竖笔之间只剩 {min(gaps)} 列，会连成一坨"


def test_small_favicons_are_exported_for_the_browser_tab():
    """16/32 的 PNG 兜底必须在，标签页那格矢量原图会糊。"""
    for name in ("favicon-16.png", "favicon-32.png"):
        p = STATIC / name
        assert p.is_file(), f"缺 {p}，先跑 make_icon.py"
        img = Image.open(p)
        n = int(p.stem.split("-")[1])
        assert img.size == (n, n)


def test_sidebar_logo_is_the_small_variant_not_the_master():
    """侧栏那格只有 20 CSS px，必须指向小尺寸变体。"""
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    assert "logo-sm.svg" in html
    assert (STATIC / "logo-sm.svg").is_file(), "先跑 make_icon.py 生成 logo-sm.svg"


def test_generated_small_svg_matches_the_snapped_table():
    """logo-sm.svg 必须跟 SMALL[20] 同源，改了一头另一头不许偷偷漂。"""
    import make_icon

    svg = (STATIC / "logo-sm.svg").read_text(encoding="utf-8")
    g = make_icon.SMALL[20]
    for x0, y0, x1, y1 in (g["stem"], g["foot"], g["hook"]):
        frag = f'<rect x="{x0}" y="{y0}" width="{x1 - x0 + 1}" height="{y1 - y0 + 1}" fill="#FFFFFF"/>'
        assert frag in svg, f"logo-sm.svg 与 SMALL[20] 漂了，缺：{frag}"
    # 反向也要钉：SVG 里的白矩形数量必须和表一致，多一块少一块都算漂
    assert svg.count('fill="#FFFFFF"') == 3, svg.count('fill="#FFFFFF"')


def _row_halves(img, y, xl, xr):
    px = img.load()

    def mean(x0, x1):
        v = [sum(px[x, y][:3]) / 3.0 for x in range(x0, x1)]
        return sum(v) / len(v)

    return mean(*xl), mean(*xr)


def test_the_tile_is_lit_from_the_upper_left_only_where_there_are_pixels():
    """砖上那道偏心柔光是这一轮给图标加的唯一细节，两种失败都不会报错：
    ① SVG 的 stop 顺序写反（中心透明、外缘亮）—— 标签页里就是一圈雾；这一条
    就是抓到的真 bug，第一版 svg_master() 正是反的。
    ② 光也铺到 16~40 那五档 —— 光场在 16px 上就是几列脏灰，先把竖笔弄脏。
    所以盯两件事：大尺寸**同一行左右**要有差（光是偏心的，不是竖向渐变），
    小尺寸同一行左右必须一样（只剩原有的竖向渐变，没有横向的光）。"""
    import make_icon

    svg = (STATIC / "logo.svg").read_text(encoding="utf-8")
    body = svg.split('id="sheen"')[1].split("</radialGradient>")[0]
    ops = [float(v) for v in re.findall(r'stop-opacity="([\d.]+)"', body)]
    assert len(ops) == 4, f"sheen 该有 4 段 stop，实际 {len(ops)}：{ops}"
    assert ops[0] > ops[1] > ops[2] > ops[3], f"柔光方向反了：中心 {ops[0]} → 外缘 {ops[3]}"
    assert ops[-1] == 0.0, f"外缘没收干净（{ops[-1]}），砖外会起一层雾"

    big = make_icon.render(256).convert("RGB")
    left, right = _row_halves(big, 30, (40, 90), (170, 220))
    assert left - right > 4.0, f"256 上左上只比右下亮 {left - right:.1f}，柔光没生效"

    for n, y in ((16, 2), (24, 3), (40, 5)):
        s = make_icon.render(n).convert("RGB")
        pad = max(3, n // 5)
        a, b = _row_halves(s, y, (pad, n // 2 - 1), (n // 2 + 1, n - pad))
        assert abs(a - b) < 2.0, (
            f"{n}px 同一行左右差 {a - b:.1f} —— 柔光铺到小尺寸上了，那档必须平涂")
