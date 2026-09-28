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
    body = src[src.index("<body>"):]
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
    body = src[src.index("<body>"):]
    assert "d.size/1048576).toFixed(1)" in body, \
        "体积又取整了：兜底值 36.2 MB 和 fetch 后的 36 MB 会显示成两个数"


def test_nav_progress_line_is_transform_driven(src):
    css = _style_block(src)
    assert re.search(r"\.nav-progress\{[^}]*transform:scaleX\(0\)", css), "进度条样式没走 transform"
    body = src[src.index("<body>"):]
    assert 'id="navProgress"' in body, "进度条节点没了"
    assert "function applyProgress()" in body
    assert re.search(r"function update\(\)\{[^}]*applyProgress\(\)", body), "进度条没接进滚动帧"
    assert re.search(r"if \(REDUCED\)\{\s*applyProgress\(\);", body), \
        "减动效档下首帧没量：后台打开会停在 0"
