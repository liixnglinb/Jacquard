# -*- coding: utf-8 -*-
"""生成 assets/loom.ico 与配套 PNG，并写出 static/ 下那三个 SVG（同一套数值）。

为什么用代码画而不是转 SVG：本机没有 cairosvg / inkscape，而这个图标只有
圆角方块 + 一条带两个弯的字标中心线，按 SVG 里的坐标复画比引一个渲染依赖更可控。

小尺寸不是从大图缩出来的。16/20/24/32/40 各自按目标像素网格硬对齐来画：
一根 2px 的笔画缩到半像素上，任务栏里就是一条灰边。每档的圆角和笔画宽度
都是各自定过整数的，见 SMALL。
 ICO 一次写 16/20/24/32/40/48/64/128/256 九档 —— 少了 20/24/40，
Windows 在 125%/150%/175% 缩放下就没得挑，只能把 32 强行缩成 24，那才是"图标发虚"的主因。

砖上那道偏心柔光（SHEEN_*）与内沿亮/暗（BEVEL_*）只走 build()，也就是 48 及以上；
SMALL 那五档（16/20/24/32/40）继续平涂。试过给小尺寸也加，光场在 16px 上就是几列脏灰
—— 细节要有像素可花。
"""
import math
import struct
import sys
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw

BASE = Path(__file__).resolve().parent
OUT = BASE / "assets"
SIZE = 1024                      # 大图的画布，圆角边缘靠它才不会锯齿
# 黑底 + 白字标 L。底不是纯黑而是极浅的自上而下渐变：纯 #000 压在深色任务栏上
# 会整颗消失，留一点顶亮底暗才有边界。
TOP = (0x1F, 0x1F, 0x1F)
BOT = (0x00, 0x00, 0x00)
LIGHT = (0xFF, 0xFF, 0xFF)
# 2026-09-25 给砖加受光方向：一块只有竖向渐变的砖读起来是"色块"而不是"表面"。
# 偏心柔光（光心在左上，半径给到 0.92 个画布，所以边界完全落在砖外，看不到弧）。
# **只加在大尺寸上**：16~40 那五档是硬对齐到像素网格的平涂，光场在那儿只会变成脏。
SHEEN_CX, SHEEN_CY, SHEEN_R, SHEEN_A = 0.30, 0.16, 0.92, 0.16
# 砖的厚度：沿内边缘描一圈，上沿亮、下沿暗。整圈等亮会读成描边，不会读成厚度。
BEVEL_W, BEVEL_TOP_A, BEVEL_BOT_A = 2.0, 0.20, 0.13
# 母版几何（viewBox 120）：字标是**一条带两个弯的中心线**加笔画宽度，不再是三个矩形拼。
# 2026-09-27 随改名把 L 水平镜像成 J；2026-09-28 把左端那截直角钩换成顺势卷出的圆弧 ——
# 三个矩形拼出来的钩是"竖笔 + 一个往回上的台阶"，读起来像括号而不像 J 的尾巴。
# 中心线端点平切（butt），所以两端就是字标的方头。竖笔 x70~86、横脚 y78~94、
# 钩尖 x32~48 三处边界与矩形那版逐值相同，改的只有转角。
STROKE = 16
R1, R2 = 16, 12                       # 底弯半径 / 钩部半径
STEM_X, FOOT_Y, TIP_X, TIP_Y = 78.0, 86.0, 40.0, 62.0
GLYPH_D = (f"M{STEM_X:.0f} 26 L{STEM_X:.0f} {FOOT_Y - R1:.0f} "
           f"A{R1} {R1} 0 0 1 {STEM_X - R1:.0f} {FOOT_Y:.0f} "
           f"L{TIP_X + R2:.0f} {FOOT_Y:.0f} "
           f"A{R2} {R2} 0 0 1 {TIP_X:.0f} {FOOT_Y - R2:.0f} "
           f"L{TIP_X:.0f} {TIP_Y:.0f}")


def glyph_points(seg: int = 24):
    """把 GLYPH_D 那条中心线采样成点列，给 PIL 画粗折线用。SVG 与位图共用同一组
    常数，改半径不会只改一头。"""
    c1 = (STEM_X - R1, FOOT_Y - R1)
    c2 = (TIP_X + R2, FOOT_Y - R2)
    pts = [(STEM_X, 26.0), (c1[0] + R1, c1[1])]
    pts += [(c1[0] + R1 * math.cos(math.pi / 2 * i / seg),
             c1[1] + R1 * math.sin(math.pi / 2 * i / seg)) for i in range(1, seg + 1)]
    pts += [(c2[0] + R2 * math.cos(math.pi / 2 + math.pi / 2 * i / seg),
             c2[1] + R2 * math.sin(math.pi / 2 + math.pi / 2 * i / seg))
            for i in range(0, seg + 1)]
    pts.append((TIP_X, TIP_Y))
    return pts


# 小尺寸全部按整数像素各自定，坐标是 (x0,y0,x1,y1) 闭区间；fillet 是内角补的那一个像素。
# 为什么不一律缩放原几何：16px 上母版那 16/120 的笔画只剩 2.1px，落在半个像素上，
# 任务栏里就是一条灰边。每一档的笔画都取整数（16/20 用 2px，24 用 3px，32/40 用 5~6px），
# 并且让记号的包围盒在画布里光学居中（J 右重，所以整体比几何中心略偏左）。
# 这套数是 L 那版逐档镜像过来的。2026-09-28 圆弧只落在 48 以上：16px 上没有像素可弯，
# 硬画只会变成脏灰 —— 小尺寸改成"钩尖收短一档 + 内角补一个像素"，把台阶感去掉就够了。
SMALL = {
    16: dict(tile_r=3, stem=(10, 3, 11, 12), foot=(3, 11, 11, 12), hook=(3, 9, 4, 11),
             fillet=(5, 10)),
    20: dict(tile_r=4, stem=(12, 4, 14, 16), foot=(4, 14, 14, 16), hook=(4, 12, 6, 14),
             fillet=(7, 13)),
    24: dict(tile_r=5, stem=(14, 4, 17, 19), foot=(5, 16, 17, 19), hook=(5, 13, 8, 16),
             fillet=(9, 15)),
    32: dict(tile_r=7, stem=(18, 6, 22, 26), foot=(7, 22, 22, 26), hook=(7, 18, 11, 22),
             fillet=(12, 21)),
    40: dict(tile_r=9, stem=(22, 7, 28, 33), foot=(9, 28, 28, 33), hook=(9, 23, 15, 28),
             fillet=(16, 27)),
}

ICO_SIZES = [16, 20, 24, 32, 40, 48, 64, 128, 256]




def grad(y: float) -> tuple:
    """按 viewBox 高度（0~120）取渐变颜色，userSpaceOnUse 就是这个语义。"""
    t = max(0.0, min(1.0, y / 120.0))
    return tuple(round(a + (b - a) * t) for a, b in zip(TOP, BOT))


def s(v: float, size: int = SIZE) -> float:
    return v * size / 120.0


def sheen_field(n: int) -> Image.Image:
    """柔光的 alpha 场，按 (1 - d²/r²)² 衰减 —— 这是"漫射"的形状，
    线性衰减会看出一颗圆盘。在 256 上算完再 bicubic 放大：场本身没有高频，
    逐像素算到 4096 只是慢，不会更准。"""
    N = 256
    img = Image.new("L", (N, N), 0)
    px = img.load()
    cx, cy, r = SHEEN_CX * N, SHEEN_CY * N, SHEEN_R * N
    for y in range(N):
        dy2 = (y - cy) ** 2
        for x in range(N):
            d2 = ((x - cx) ** 2 + dy2) / (r * r)
            px[x, y] = 0 if d2 >= 1.0 else round(SHEEN_A * 255 * (1.0 - d2) ** 2)
    return img.resize((n, n), Image.BICUBIC)


def _ramp(n: int, mode: str) -> Image.Image:
    """一条 1px 宽、n 高的竖向渐变再横向放大 —— 直接 putdata 满幅会在 4096 的
    超采样画布上生成一千七百万个 Python 对象。"""
    col = Image.new("L", (1, n))
    col.putdata([max(0, min(255, round(255 * ((1.0 - (y / max(1, n - 1)) / .34)
                   if mode == "top" else ((y / max(1, n - 1)) - .66) / .34))))
                 for y in range(n)])
    return col.resize((n, n), Image.BILINEAR)


def bevel(img: Image.Image, ss: int, radius: float) -> None:
    """沿砖的内边缘描一圈，上沿压白、下沿压黑 —— 只有上亮下暗，砖才从"色块"
    变成"有厚度的表面"。整圈等亮就只是一条描边。"""
    edge = Image.new("L", (ss, ss), 0)
    ImageDraw.Draw(edge).rounded_rectangle([0, 0, ss - 1, ss - 1], radius=radius,
                                           outline=255, width=max(1, round(BEVEL_W * ss / 120)))
    for mode, color, a in (("top", LIGHT, BEVEL_TOP_A), ("bot", (0, 0, 0), BEVEL_BOT_A)):
        m = ImageChops.multiply(edge, _ramp(ss, mode)).point(lambda v: int(v * a))
        img.paste(Image.new("RGBA", (ss, ss), color + (255,)), (0, 0), m)


def _resample(pts, step: float):
    """按弧长等距重采样。"""
    out = [pts[0]]
    acc = 0.0
    for (ax, ay), (bx, by) in zip(pts, pts[1:]):
        x0, y0, x1, y1 = ax, ay, bx, by
        while True:
            L = math.hypot(x1 - x0, y1 - y0)
            if acc + L < step:
                acc += L
                break
            t = (step - acc) / L
            x0, y0 = x0 + t * (x1 - x0), y0 + t * (y1 - y0)
            out.append((x0, y0))
            acc = 0.0
    out.append(pts[-1])
    return out



def glyph_mask(n: int) -> Image.Image:
    """字标位图 = 沿中心线排一串圆盘的并集。
    为什么不用 PIL 的粗折线：密采样下它是一节一节四边形拼的，节与节之间会露出
    楔形缝，超采样缩下来就是碗部那一圈放射状白刺（2026-09-28 第一版就是这么坏的）。
    圆盘相邻必重叠，没有缝。代价是两端变圆头 —— 字标两端本来就是方头，
    所以再各按一条水平线切平，切出来的结果与 SVG 的 stroke-linecap="butt" 一致。"""
    k = n / 120.0
    m = Image.new("L", (n, n), 0)
    d = ImageDraw.Draw(m)
    r = STROKE / 2 * k
    for x, y in _resample(glyph_points(seg=64), 0.55):
        d.ellipse([x * k - r, y * k - r, x * k + r, y * k + r], fill=255)
    d.rectangle([0, 0, n, 26 * k - 1], fill=0)                          # 竖笔顶
    d.rectangle([0, 0, (TIP_X + STROKE / 2) * k - 1, TIP_Y * k - 1], fill=0)  # 钩尖
    return m


def build(size: int = SIZE, samples: int = 4) -> Image.Image:
    """矢量那套几何画在 size 画布上，samples>1 时超采样一次，边缘才是干净的。"""
    ss = size * samples
    img = Image.new("RGBA", (ss, ss), (0, 0, 0, 0))
    strip = Image.new("RGBA", (ss, ss))
    d = ImageDraw.Draw(strip)
    for y in range(ss):
        d.line([(0, y), (ss, y)], fill=grad(y * 120 / ss) + (255,))
    mask = Image.new("L", (ss, ss), 0)
    r = s(27, ss)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, ss - 1, ss - 1], radius=r, fill=255)
    img.paste(strip, (0, 0), mask)
    # 光也裁进同一块圆角砖内，才不会在砖外留一层雾
    img.paste(Image.new("RGBA", (ss, ss), LIGHT + (255,)), (0, 0),
              Image.composite(sheen_field(ss), Image.new("L", (ss, ss), 0), mask))
    bevel(img, ss, r)
    img.paste(Image.new("RGBA", (ss, ss), LIGHT + (255,)), (0, 0), glyph_mask(ss))
    if samples > 1:
        img = img.resize((size, size), Image.LANCZOS)
    return img




def build_snapped(n: int) -> Image.Image:
    """小尺寸：外轮廓可以软（那是跟透明背景交界，本来就该有），里面全部硬边、
    全部落在网格上。缩放原几何会同时毁掉这两件事 —— 轮廓带出一圈灰边，
    笔画又全都压在半个像素上。"""
    g = SMALL[n]
    k = 4
    tile = Image.new("RGBA", (n * k, n * k), (0, 0, 0, 0))
    td = ImageDraw.Draw(tile)
    td.rounded_rectangle([0, 0, n * k - 1, n * k - 1], radius=g["tile_r"] * k, fill=(255, 255, 255, 255))
    strip = Image.new("RGBA", (n * k, n * k))
    sd = ImageDraw.Draw(strip)
    for y in range(n * k):
        sd.line([(0, y), (n * k, y)], fill=grad((y + 0.5) * 120 / (n * k)) + (255,))
    tile.paste(strip, (0, 0), tile.split()[3])
    # 整数倍 BOX 降采样就是纯面积平均，不会像 LANCZOS 那样在轮廓外侧振出一圈灰边
    img = tile.resize((n, n), Image.BOX)
    d = ImageDraw.Draw(img)
    fx, fy = g["fillet"]
    for box in (g["stem"], g["foot"], g["hook"], (fx, fy, fx, fy)):
        d.rectangle(box, fill=LIGHT + (255,))
    return img


def render(n: int) -> Image.Image:
    if n in SMALL:
        return build_snapped(n)
    # 48 起才有像素可弯，回到矢量那套几何。超采样倍数按档位给足：
    # 圆盘并集的边缘是硬边，倍数不够就是锯齿。
    return build(n, samples=4 if n >= 256 else (2 if n >= 48 else 1))


def svg_master() -> str:
    """母版 SVG（120 viewBox）。以前它是手写的，于是改图标要改两处、而且这两处会漂。
    柔光在 SVG 里只能靠 stop 分段逼近 (1-d²/r²)²：取 d/r = 0 / .5 / .75 / 1 四点，
    误差在肉眼之外，别再为它引一个渲染依赖。
    内沿亮/暗同理：描一圈之后用竖向渐变把不透明度在前 34% / 后 34% 里收放，
    和位图那边 _ramp() 的曲线是同一个形状。"""
    f = lambda d2: round(SHEEN_A * (1.0 - d2) ** 2, 4)
    stops = "".join(
        f'<stop offset="{o}" stop-color="#FFFFFF" stop-opacity="{f(d2)}"/>'
        for o, d2 in ((0, 0.0), (0.5, 0.25), (0.75, 0.5625), (1, 1.0)))
    r = round(SHEEN_R * 120, 1)
    bw = 3.0                                        # BEVEL_W 在 120 画布上的描边宽
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="120" height="120" '
        'viewBox="0 0 120 120">\n'
        '  <defs>\n'
        '    <linearGradient id="loom" gradientUnits="userSpaceOnUse" x1="0" y1="0" x2="0" y2="120">\n'
        '      <stop offset="0" stop-color="#1F1F1F"/><stop offset="1" stop-color="#000000"/>\n'
        '    </linearGradient>\n'
        f'    <radialGradient id="sheen" gradientUnits="userSpaceOnUse" '
        f'cx="{round(SHEEN_CX * 120, 1)}" cy="{round(SHEEN_CY * 120, 1)}" r="{r}">\n'
        f'      {stops}\n'
        '    </radialGradient>\n'
        f'    <linearGradient id="bevel-top" gradientUnits="userSpaceOnUse" x1="0" y1="0" x2="0" y2="{round(120 * 0.34, 1)}">\n'
        f'      <stop offset="0" stop-color="#FFFFFF" stop-opacity="{BEVEL_TOP_A}"/>'
        '<stop offset="1" stop-color="#FFFFFF" stop-opacity="0"/>\n'
        '    </linearGradient>\n'
        f'    <linearGradient id="bevel-bot" gradientUnits="userSpaceOnUse" x1="0" y1="{round(120 * 0.66, 1)}" x2="0" y2="120">\n'
        '      <stop offset="0" stop-color="#000000" stop-opacity="0"/>'
        f'      <stop offset="1" stop-color="#000000" stop-opacity="{BEVEL_BOT_A}"/>\n'
        '    </linearGradient>\n'
        '  </defs>\n'
        '  <rect width="120" height="120" rx="27" fill="url(#loom)"/>\n'
        '  <rect width="120" height="120" rx="27" fill="url(#sheen)"/>\n'
        f'  <rect x="{bw / 2}" y="{bw / 2}" width="{120 - bw}" height="{120 - bw}" rx="25.5"'
        ' fill="none" stroke="url(#bevel-top)" stroke-width="3"/>\n'
        f'  <rect x="{bw / 2}" y="{bw / 2}" width="{120 - bw}" height="{120 - bw}" rx="25.5"'
        ' fill="none" stroke="url(#bevel-bot)" stroke-width="3"/>\n'
        f'  <path d="{GLYPH_D}" fill="none" stroke="#FFFFFF" stroke-width="{STROKE}"'
        ' stroke-linecap="butt" stroke-linejoin="round"/>\n'
        '</svg>\n')



def svg_snapped(n: int) -> str:
    """把 SMALL[n] 那套整数几何写成 SVG —— 侧边栏那颗只有 20 CSS px，标签页那档
    在 150% 缩放下约 24 个设备像素，缩放母版会让笔画落在半个像素上。
    大图那套原样留在 logo.svg，这里只是同一个记号的小尺寸版本。"""
    g = SMALL[n]
    body = [f'<rect width="{n}" height="{n}" rx="{g["tile_r"]}" fill="url(#loom)"/>']
    fx, fy = g["fillet"]
    for x0, y0, x1, y1 in (g["stem"], g["foot"], g["hook"], (fx, fy, fx, fy)):
        body.append(f'<rect x="{x0}" y="{y0}" width="{x1 - x0 + 1}"'
                    f' height="{y1 - y0 + 1}" fill="#FFFFFF"/>')
    parts = body + ['</svg>']
    return ('<svg xmlns="http://www.w3.org/2000/svg" width="{0}" height="{0}" viewBox="0 0 {0} {0}">'
            '<defs><linearGradient id="loom" gradientUnits="userSpaceOnUse" x1="0" y1="0" x2="0" y2="{0}">'
            '<stop offset="0" stop-color="#1F1F1F"/><stop offset="1" stop-color="#000000"/>'
            '</linearGradient></defs>').replace("{0}", str(n)) + "".join(parts)


def main() -> int:
    OUT.mkdir(exist_ok=True)
    big = build()
    big.save(OUT / "loom-1024.png")
    for n, name in ((256, "loom-256.png"), (64, "logo-64.png"), (48, "favicon-48.png")):
        render(n).save(OUT / name)
    for n in (16, 24, 32):
        render(n).save(OUT / f"favicon-{n}.png")
    # 浏览器标签页那 16/32 也从这里出：static/favicon.svg 在 150% 缩放下
    # 只有约 24 个设备像素，矢量那套眼距会糊成一整条嘴，得给 PNG 兜底。
    static = BASE / "static"
    for n in (16, 32):
        render(n).save(static / f"favicon-{n}.png")
    # 母版 SVG 以前是手写的 —— 改一处几何要记得改另一处，柔光这种新加的东西最容易
    # 只落在 PNG 上，于是标签页/文档里的 SVG 和安装包图标不是同一个记号。现在同源。
    (static / "logo.svg").write_text(svg_master(), encoding="utf-8")
    (static / "logo-sm.svg").write_text(svg_snapped(20), encoding="utf-8")
    # favicon.svg 以前是手写的母版几何，不在这条流水线里 —— 于是标签页上一直是
    # 眼距 9/120 那张糊脸（Chromium 优先用 SVG，PNG 兜底根本轮不到）。
    # 现在由同一张 SMALL 表生成，改图标只需要改一处。
    (static / "favicon.svg").write_text(svg_snapped(16), encoding="utf-8")

    frames = [render(n) for n in ICO_SIZES]
    head = struct.pack("<HHH", 0, 1, len(frames))
    body, offset = b"", 6 + 16 * len(frames)
    for n, fr in zip(ICO_SIZES, frames):
        import io
        buf = io.BytesIO()
        fr.save(buf, format="PNG", optimize=True)
        data = buf.getvalue()
        head += struct.pack("<BBBBHHII", n % 256, n % 256, 0, 0, 1, 32,
                            len(data), offset)
        body += data
        offset += len(data)
    (OUT / "loom.ico").write_bytes(head + body)

    for f in sorted(OUT.iterdir()):
        print(f"{f.name:18s} {f.stat().st_size/1024:6.1f} KB")
    print("ico 内各档:", " ".join(f"{n}" for n in ICO_SIZES))
    return 0


if __name__ == "__main__":
    sys.exit(main())
