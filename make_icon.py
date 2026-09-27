# -*- coding: utf-8 -*-
"""生成 assets/loom.ico 与配套 PNG，并写出 static/ 下那三个 SVG（同一套数值）。

为什么用代码画而不是转 SVG：本机没有 cairosvg / inkscape，而这个图标只有
圆角方块 + 三个矩形（竖笔 / 横脚 / 钩尖），按 SVG 里的坐标复画比引一个渲染依赖更可控。

小尺寸不是从大图缩出来的。16/20/24/32/40 各自按目标像素网格硬对齐来画：
一根 2px 的笔画缩到半像素上，任务栏里就是一条灰边。每档的圆角和笔画宽度
都是各自定过整数的，见 SMALL。
 ICO 一次写 16/20/24/32/40/48/64/128/256 九档 —— 少了 20/24/40，
Windows 在 125%/150%/175% 缩放下就没得挑，只能把 32 强行缩成 24，那才是"图标发虚"的主因。

砖上那道偏心柔光（SHEEN_*）只走 build()，也就是 48 及以上；SMALL 那五档（16/20/24/32/40）
继续平涂。试过给小尺寸也加，光场在 16px 上就是几列脏灰 —— 细节要有像素可花。
"""
import struct
import sys
from pathlib import Path

from PIL import Image, ImageDraw

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
# 母版几何（viewBox 120）：竖笔 + 横脚 + 钩尖三个矩形拼。
# 2026-09-27 随改名（Loom → Jacquard）把原来的 L **水平镜像**成 J：
# 无衬线 J 就是"右侧竖笔 + 底部左钩"，镜像能原样保住每一档量过的笔画宽度、
# 高度和光学居中（L 左重所以偏右，镜像后右重所以偏左，同一套偏移自动反过来）。
# HOOK 是钩尖起的那一段 —— 没有它，256 上读起来更像"直角括号"而不是 J。
# 实测它在 16px 上仍留 5 列负空间（糊掉的阈值是 2 列），所以五档小尺寸都给。
STEM = (70, 26, 86, 94)
FOOT = (32, 78, 86, 94)
HOOK = (32, 62, 48, 94)

ICO_SIZES = [16, 20, 24, 32, 40, 48, 64, 128, 256]

# 小尺寸全部按整数像素各自定，坐标是 (x0,y0,x1,y1) 闭区间。
# 为什么不一律缩放原几何：16px 上母版那 14/120 的笔画只剩 1.87px，落在半个像素上，
# 任务栏里就是一条灰边。每一档的笔画都取整数（16/20 用 2px，24 用 3px，32/40 用 5~6px），
# 并且让记号的包围盒在画布里光学居中（J 右重，所以整体比几何中心略偏左）。
# 这套数是 L 那版逐档镜像过来的，钩尖宽度取竖笔同宽、高度 n*0.16 起（最少 3 列）。
SMALL = {
    16: dict(tile_r=3, stem=(10, 3, 11, 12), foot=(3, 11, 11, 12), hook=(3, 8, 4, 11)),
    20: dict(tile_r=4, stem=(12, 4, 14, 16), foot=(4, 14, 14, 16), hook=(4, 11, 6, 14)),
    24: dict(tile_r=5, stem=(14, 4, 17, 19), foot=(5, 16, 17, 19), hook=(5, 12, 8, 16)),
    32: dict(tile_r=7, stem=(18, 6, 22, 26), foot=(7, 22, 22, 26), hook=(7, 17, 11, 22)),
    40: dict(tile_r=9, stem=(22, 7, 28, 33), foot=(9, 28, 28, 33), hook=(9, 22, 15, 28)),
}


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


def build(size: int = SIZE, samples: int = 4) -> Image.Image:
    """矢量那套几何画在 size 画布上，samples>1 时超采样一次，边缘才是干净的。"""
    ss = size * samples
    img = Image.new("RGBA", (ss, ss), (0, 0, 0, 0))
    strip = Image.new("RGBA", (ss, ss))
    d = ImageDraw.Draw(strip)
    for y in range(ss):
        d.line([(0, y), (ss, y)], fill=grad(y * 120 / ss) + (255,))
    mask = Image.new("L", (ss, ss), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, ss - 1, ss - 1], radius=s(27, ss), fill=255)
    img.paste(strip, (0, 0), mask)
    # 光也裁进同一块圆角砖内，才不会在砖外留一层雾
    img.paste(Image.new("RGBA", (ss, ss), LIGHT + (255,)), (0, 0),
              Image.composite(sheen_field(ss), Image.new("L", (ss, ss), 0), mask))

    d = ImageDraw.Draw(img)
    k = size / 120.0 * samples
    for x0, y0, x1, y1 in (STEM, FOOT, HOOK):
        d.rectangle([x0 * k, y0 * k, x1 * k - 1, y1 * k - 1], fill=LIGHT + (255,))
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
    for box in (g["stem"], g["foot"], g["hook"]):
        d.rectangle(box, fill=LIGHT + (255,))
    return img


def render(n: int) -> Image.Image:
    if n in SMALL:
        return build_snapped(n)
    # 64 起五官有六七个像素可给，回到矢量那套几何，圆角也才够十几级
    return build(n, samples=2 if n >= 64 else 1)


def svg_master() -> str:
    """母版 SVG（120 viewBox）。以前它是手写的，于是改图标要改两处、而且这两处会漂。
    柔光在 SVG 里只能靠 stop 分段逼近 (1-d²/r²)²：取 d/r = 0 / .5 / .75 / 1 四点，
    误差在肉眼之外，别再为它引一个渲染依赖。"""
    f = lambda d2: round(SHEEN_A * (1.0 - d2) ** 2, 4)
    stops = "".join(
        f'<stop offset="{o}" stop-color="#FFFFFF" stop-opacity="{f(d2)}"/>'
        for o, d2 in ((0, 0.0), (0.5, 0.25), (0.75, 0.5625), (1, 1.0)))
    r = round(SHEEN_R * 120, 1)
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
        '  </defs>\n'
        '  <rect width="120" height="120" rx="27" fill="url(#loom)"/>\n'
        '  <rect width="120" height="120" rx="27" fill="url(#sheen)"/>\n'
        f'  <rect x="{STEM[0]}" y="{STEM[1]}" width="{STEM[2] - STEM[0]}"'
        f' height="{STEM[3] - STEM[1]}" fill="#FFFFFF"/>\n'
        f'  <rect x="{FOOT[0]}" y="{FOOT[1]}" width="{FOOT[2] - FOOT[0]}"'
        f' height="{FOOT[3] - FOOT[1]}" fill="#FFFFFF"/>\n'
        f'  <rect x="{HOOK[0]}" y="{HOOK[1]}" width="{HOOK[2] - HOOK[0]}"'
        f' height="{HOOK[3] - HOOK[1]}" fill="#FFFFFF"/>\n'
        '</svg>\n')


def svg_snapped(n: int) -> str:
    """把 SMALL[n] 那套整数几何写成 SVG —— 侧边栏那颗只有 20 CSS px，标签页那档
    在 150% 缩放下约 24 个设备像素，缩放母版会让笔画落在半个像素上。
    大图那套原样留在 logo.svg，这里只是同一个记号的小尺寸版本。"""
    g = SMALL[n]
    body = [f'<rect width="{n}" height="{n}" rx="{g["tile_r"]}" fill="url(#loom)"/>']
    for x0, y0, x1, y1 in (g["stem"], g["foot"], g["hook"]):
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
