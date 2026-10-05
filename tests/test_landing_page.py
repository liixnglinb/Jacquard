# -*- coding: utf-8 -*-
"""下载页自己的设计不变量。

test_landing_sync.py 守的是"版本号别漏改"，这个文件守的是另外四件容易被顺手改回去的事：

① 页面不许自己长出蓝色。软件的强调色是黑白反转，全站只有一个淡蓝令牌 --accent-soft
   表示"选中/高亮"。之前 hero、CTA、阴影、选中色、呼吸光晕各自抄了一份蓝，
   合起来就是一张和软件不像的脸 —— 而且散在十几处，没人会记得改。
② 分区留白只能从 --sp-sec / --sp-band 取。原来 section 写死 160、.runit 用 9vh 的
   clamp，两套数叠在 mock 和下一条分区线之间能挤出 264px。
③ GitHub 那颗镜像按钮只能由清单决定。前端自己拼 releases/download 直链，
   会把"忘了发 Release"变成一个静默 404（同 publish_github.py 的约定）。
④ 数字读数要等宽、体积要保留一位小数 —— 清单 fetch 回来时不许换写法。

页面在另一个仓库（D 盘那个站点）。这台机器上没有就跳过，不编。
"""
import re
from pathlib import Path

import pytest

PAGE = Path(r"D:\Voyra 个人网站\public\modelflow\index.html")

# 从软件逐值抄来的两个淡蓝令牌，是整页唯一允许存在的蓝。
ALLOWED_BLUES = {"#ebf4ff", "#001d3d"}


@pytest.fixture(scope="module")
def src():
    if not PAGE.exists():
        pytest.skip("这台机器上没有站点仓库")
    return PAGE.read_text(encoding="utf-8")


def _body(src):
    """<body> 之后的全部行为代码 —— 含被外置出去的那几段脚本。

    2026-10-04 站点仓库 954f720 把 7 个下载页的内联 <script> 原位换成
    <script src="./app-N.js">，因为 CSP 的 script-src 去掉了 unsafe-inline
    （机理见 Voyra 说明 §11.2）。本文件当时只读 index.html，于是"进度条没接进
    滚动帧""镜像按钮不受清单控制""体积读数写法换了"三条一起变成假失败 ——
    代码一行没少，只是搬了个文件。断言必须跟着真正会跑起来的那份读。
    """
    tail = src[src.index("<body>"):]
    extra = []
    for name in sorted(set(re.findall(r'src="\./([\w.-]+\.js)"', src))):
        f = PAGE.parent / name
        if f.exists():
            extra.append(f.read_text(encoding="utf-8"))
    return tail + "\n" + "\n".join(extra)


def _style_block(text):
    m = re.search(r"<style>(.*?)</style>", text, re.S)
    assert m, "页里没有 <style> 块"
    return re.sub(r"/\*.*?\*/", "", m.group(1), flags=re.S)


def _blue_dominant(r, g, b):
    return b >= r + 12 and b > g + 6


def invented_blues(css):
    """扫样式块里所有色值，返回"不是那两份令牌"的蓝。"""
    bad = set()
    for h in re.findall(r"#([0-9a-fA-F]{6})\b", css):
        r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
        if _blue_dominant(r, g, b):
            bad.add("#" + h.lower())
    for h in re.findall(r"#([0-9a-fA-F]{3})\b", css):
        r, g, b = (int(c * 2, 16) for c in h)
        if _blue_dominant(r, g, b):
            bad.add("#" + h.lower())
    for m in re.finditer(r"rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*(?:,[^)]*)?\)", css):
        r, g, b = (int(x) for x in m.groups()[:3])
        if _blue_dominant(r, g, b):
            bad.add(m.group(0).replace(" ", ""))
    return bad - ALLOWED_BLUES


def test_page_grows_no_blue_of_its_own(src):
    bad = invented_blues(_style_block(src))
    assert not bad, f"页面自己长出了蓝：{sorted(bad)} —— 软件只有 --accent-soft 一份淡蓝"


def test_section_rhythm_comes_from_tokens(src):
    css = _style_block(src)
    assert "--sp-sec:" in css and "--sp-band:" in css, "节奏令牌没定义"
    assert re.search(r"^section\{[^}]*padding:var\(--sp-sec\) 24px 0", css, re.M), \
        "section 的上边距没走 --sp-sec"
    assert re.search(r"^\.runit\{padding:var\(--sp-sec\) 0 var\(--sp-band\)\}", css, re.M), \
        ".runit 又自带一套垂直留白"
    for stray in ("padding:160px", "clamp(52px,9vh,104px)"):
        assert stray not in css, f"样式块里还留着写死的 {stray}"


def test_mirror_button_is_manifest_gated(src):
    body = _body(src)
    assert 'id="dlGithub"' in body, "镜像按钮没了"
    m = re.search(r'<a[^>]*id="dlGithub"[^>]*>', body)
    assert " hidden" in m.group(0), "镜像按钮默认就该藏着"
    assert "releases/download" not in body, \
        "页里写死了 GitHub 直链 —— 那个源存不存在由清单 mirrors 说了算"
    assert re.search(r"\(d\.mirrors\s*\|\|\s*\[\]\)\[0\]", body), "没按清单 mirrors 决定"
    assert 'id="dlSrcNote"' in body and "hidden" in re.search(
        r'<p[^>]*id="dlSrcNote"[^>]*>', body).group(0), "两个源同包同校验和的说明没跟着藏"


def test_numeric_readouts_stay_put(src):
    css = _style_block(src)
    assert re.search(r"\.pill \.ver,\.hero-note b,\.sha,\.foot \.en\{"
                     r"font-variant-numeric:tabular-nums\}", css), \
        "等宽数字那条规则没了：清单 fetch 回来时版本号会把版面推一下"
    body = _body(src)
    assert "d.size/1048576).toFixed(1)" in body, \
        "体积又取整了：兜底值 36.2 MB 和 fetch 后的 36 MB 会显示成两个数"


def test_nav_progress_line_is_transform_driven(src):
    css = _style_block(src)
    assert re.search(r"\.nav-progress\{[^}]*transform:scaleX\(0\)", css), "进度条样式没走 transform"
    body = _body(src)
    assert 'id="navProgress"' in body, "进度条节点没了"
    assert "function applyProgress()" in body
    assert re.search(r"function update\(\)\{[^}]*applyProgress\(\)", body), "进度条没接进滚动帧"
    assert re.search(r"if \(REDUCED\)\{\s*applyProgress\(\);", body), \
        "减动效档下首帧没量：后台打开会停在 0"


def test_page_is_six_bands_with_one_h2_each(src):
    """十段并成六段之后，锚点、导航、二级标题数量都是钉死的 —— 再长出第七段或
    第二段 h2 就得回这里说清楚为什么。"""
    ids = re.findall(r'<section[^>]*\bid="([^"]+)"', src)
    assert ids == ["flow", "run", "start", "local", "faq", "dl"], ids
    assert len(re.findall(r"<h2>", src)) == 6, "一段只许一个 h2"
    assert src.count('class="band-head" data-rise') == 4, "段内二级标题"
    for gone in ("cap", "runit", "pipeline", "how", "req", "omni"):
        assert f'id="{gone}"' not in src, f"#{gone} 该并掉了"
    nav = re.findall(r'<a href="#([\w-]+)">', src[src.index('id="navLinks"'):src.index('class="nav-right"')])
    assert nav == ["flow", "run", "start", "local", "faq"], nav
    for href in set(re.findall(r'href="#([\w-]+)"', src)):
        assert f'id="{href}"' in src, f"页内锚点 #{href} 指向不存在的位置"


def test_mobile_band_padding_overrides_the_class_rule(src):
    """.runit 是类选择器，压得住窄屏那条 section{padding:20px} —— 收成令牌之后
    不补这一行，产品图带在手机上会照抄桌面的 144。"""
    css = _style_block(src)
    narrow = css[css.index("@media (max-width:860px)"):]
    assert re.search(r"\.runit\{padding:var\(--sp-band\) 0\}", narrow), \
        "窄屏少了 .runit 的覆盖：类选择器会盖过 section"


# ---------------------------------------------------------------- 第三轮
def test_hero_shows_the_working_ui_not_the_update_dialog(src):
    """首屏那半屏必须是软件真的在跑的样子。居中那张"v1.2.7 已下载好"浮层
    （连它底下那层遮罩）是页面自己加的戏，用户明说没人要看 —— 删干净，
    样式行也别留着。"""
    for gone in ("m-upd", "m-mask", "已下载好", "安装并重启"):
        assert gone not in src, f"首屏还留着更新浮层的东西：{gone}"
    css = _style_block(src)
    assert re.search(r"\.hero\{[^}]*min-height:100vh", css), "hero 不再是一屏高"
    assert re.search(r"\.hero-in\{[^}]*flex:0 0 auto", css), \
        "文案区还在 flex:1 撑满 —— 产品图会被顶到二屏去"
    assert re.search(r"\.hero-stage\{[^}]*flex:1 1 auto[^}]*align-items:flex-end", css), \
        "产品图没吃掉剩下的整屏并贴住底边"


def test_stats_columns_match_the_number_of_items(src):
    """数字条曾经 5 列只放 4 格 —— 后面空一格，谁看都知道是凑数。
    基础规则和每一处改列数的媒体查询都要对上格数。"""
    css = _style_block(src)
    n = len(re.findall(r'<div class="stat">', src))
    assert n >= 2, f"数字条只剩 {n} 格？"
    cols = [int(m) for m in re.findall(r"\.stats\{[^}]*?repeat\((\d+),1fr\)", css)]
    assert cols, "没找到 .stats 的列数"
    assert all(c == n or c == 2 for c in cols), \
        f"数字条有 {n} 格，但某处列数是 {cols} —— 会空出一格（2 列是窄屏两行排，允许）"


def test_hover_only_motion_is_gated_off_for_touch(src):
    """跟光标的柔光和进场扫光都只在真有指针的设备上跑；触屏没有 hover，
    留着就是白挂一个 pointermove 监听。"""
    css = _style_block(src)
    assert "--mx" in css and "--my" in css, "柔光圆心不再是自定义量"
    assert re.search(r"\.card:hover::before,\.stage:hover::before,\.lc:hover::before\{opacity:1\}", css)
    body = _body(src)
    assert re.search(r"if \(REDUCED \|\| !matchMedia\('\(hover:hover\)'\)\.matches\) return;", body), \
        "柔光/扫光没在触屏与减动效档下早退"
    assert "@keyframes pillShine" in css and ".js .pill.shine::after" in css
    assert ".lc{position:relative}" in css, ".lc 没定位，柔光会跑到视口上"


def test_rise_motion_clears_its_transform(src):
    """段进场从纯淡入改成淡入 + 上浮。两个失败都得抓：① 忘了在 .shown 里
    收回 transform，卡片永远抬着 18px；② 减动效档只关了 opacity 没关 transform。"""
    css = _style_block(src)
    assert re.search(r"\.js \[data-rise\]\{opacity:0;transform:translateY\(\d+px\)", css), \
        "进场没有上浮了"
    assert re.search(r"\.js \[data-rise\]\.shown\{opacity:1;transform:none\}", css), \
        ".shown 没收回 transform"
    assert re.search(r"\.js \[data-rise\]\{opacity:1;transform:none", css), \
        "减动效档只关了淡入，没关位移"


