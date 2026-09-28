# -*- coding: utf-8 -*-
"""下载页同步脚本的契约。

这个脚本改的是**线上页面的兜底值**，而它最容易犯的错是"漏一处且不报错"：
fetch 正常时没人看得见兜底值，fetch 一挂就给用户印一个说谎的版本号。
所以这里不测"能不能跑"，测的是"漏了会不会红"。
"""
import importlib.util
import re
import sys
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location(
    "sync_landing", Path(__file__).resolve().parent.parent / "sync_landing.py")
sync_landing = importlib.util.module_from_spec(_spec)
sys.modules["sync_landing"] = sync_landing
_spec.loader.exec_module(sync_landing)

# 2026-09-28 下载页首屏撤掉了居中那张"已下载好"的更新浮层，于是显示位从 7 处收到 6 处，
# 也没有"浮层里那行当前版本"了。注释里那句历史说明留着 —— 它正是"注释里的旧版本号
# 不该被改"这条判据的用例。
PAGE = """<html><head><style>
/* 更新浮层。而 9.9.8 开始浮层还会显示这一段发版说明 —— 历史说明，不该跟着漂 */
.m-card{{border-radius:16px}}
</style></head><body>
<span class="ver" id="navVer">9.9.9</span>
<span class="ver" id="heroVer">9.9.9</span>
<span class="ver" id="btnVer">9.9.9</span>
<span class="ver" id="ftVer">9.9.9</span>
<div class="m-up">更新至 9.9.9</div>
<a href="https://x/Loom-9.9.9-setup.exe">下载</a>
<div id="heroSize">36.2 MB</div><div id="btnSize">36.2 MB</div>
<p>安装包约 36.2 MB，全本地运行</p>
<p>日志 2.4 MB · 需要约 200 MB 磁盘</p>
</body></html>"""


def test_every_registered_spot_moves_and_nothing_else_does():
    out = sync_landing.sync_versions(PAGE, "9.9.9", "9.9.10")
    assert len(re.findall(r"9\.9\.10", out)) == len(sync_landing.SPOTS)
    # 注释里那句历史说明原样不动
    assert "9.9.8 开始浮层还会显示" in out
    assert "9.9.9" not in out.replace("9.9.8 开始浮层还会显示", ""), "有旧版本号没被换掉"


def test_a_missing_spot_fails_instead_of_silently_skipping():
    """少一处（把页脚那个 span 删掉）必须红，而不是"换了 5 处，算了"。"""
    broken = PAGE.replace('<span class="ver" id="ftVer">9.9.9</span>', "")
    with pytest.raises(AssertionError) as e:
        sync_landing.sync_versions(broken, "9.9.9", "9.9.10")
    assert "页脚版本" in str(e.value)


def test_an_unregistered_visible_version_fails():
    """新加一处显示位却没登记：残留检查要把它抓出来，而不是当注释放过。"""
    grown = PAGE + '\n<div class="badge">最新版本 9.9.9</div>'
    with pytest.raises(AssertionError) as e:
        sync_landing.sync_versions(grown, "9.9.9", "9.9.10")
    assert "不属于任何已登记的显示位" in str(e.value)


def test_size_anchors_ignore_other_mb_numbers():
    out, cur = sync_landing.sync_size(PAGE, "37.5")
    assert cur == "36.2"
    assert out.count("37.5 MB") == 3
    assert "2.4 MB" in out and "约 200 MB 磁盘" in out, "把别的 MB 数字一起改了"


def test_the_real_page_still_matches_the_registered_spots():
    """这条是防"页里长出新位置而脚本不知道"：直接拿真页跑一遍计数，
    不写回去。哪天真页加了一处显示位而没登记，这里先红。"""
    p = Path(r"D:\Voyra 个人网站\public\modelflow\index.html")
    if not p.exists():
        pytest.skip("这台机器上没有那个站仓库")
    s = p.read_text(encoding="utf-8")
    vers = sorted(set(re.findall(r"\b\d+\.\d+\.\d+\b", s)),
                  key=lambda v: [int(x) for x in v.split(".")])
    newest = vers[-1]
    out = sync_landing.sync_versions(s, newest, "99.99.99")
    assert len(re.findall(r"99\.99\.99", out)) == len(sync_landing.SPOTS)
