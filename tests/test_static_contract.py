# -*- coding: utf-8 -*-
"""静态资产契约：双语字典对齐、CSS 变量有定义、圆角只走角色刻度。

这三条本次会话靠一次性脚本临时验过，回归靠肉眼守不住。
"""
import json
import re
import time
from pathlib import Path

import pytest

from conftest import STATIC_DIR

JS_FILES = sorted(STATIC_DIR.glob("*.js"))
UI_JS = (STATIC_DIR / "ui.js").read_text(encoding="utf-8")
CSS = re.sub(r"/\*.*?\*/", "", (STATIC_DIR / "style.css").read_text(encoding="utf-8"), flags=re.S)

KEY_RE = re.compile(r"'([A-Za-z0-9._-]+)'\s*:")


def _dict_block(lang: str) -> str:
    m = re.search(rf"\n  {lang}: \{{\n(.*?)\n  \}},\n", UI_JS, re.S)
    assert m, f"ui.js 里找不到 {lang} 字典块"
    return m.group(1)


@pytest.fixture(scope="module")
def dicts():
    return set(KEY_RE.findall(_dict_block("zh"))), set(KEY_RE.findall(_dict_block("en")))


def test_zh_en_keys_match(dicts):
    zh, en = dicts
    assert zh - en == set(), f"这些 key 只有中文有翻译：{sorted(zh - en)}"
    assert en - zh == set(), f"这些 key 只有英文有翻译：{sorted(en - zh)}"


def _used_keys():
    """扫所有 JS 里的 t('x.y')；拼接出来的前缀（t('run.lg'+k)）单独登记。"""
    exact, prefixes = set(), set()
    for f in JS_FILES:
        src = re.sub(r"//[^\n]*", "", f.read_text(encoding="utf-8"))
        for m in re.finditer(r"(?<![A-Za-z0-9_$])t\(\s*'([^']+)('?\s*\+)", src):
            (prefixes if m.group(2).startswith("'") and m.group(2)[1:].strip().startswith("+")
             else exact).add(m.group(1))
        for m in re.finditer(r"(?<![A-Za-z0-9_$])t\(\s*'([^']+)'\s*[,)]", src):
            exact.add(m.group(1))
    return exact, {p for p in prefixes if p not in exact}


KEYISH = re.compile(r"'([a-z][a-z0-9]*(?:\.[A-Za-z0-9_]+)+)'")
# 长得很像 i18n key、其实不是的字符串（codex 事件类型等）。新增要写明理由。
NOT_KEYS = {
    "item.completed", "thread.started", "turn.started", "turn.completed", "turn.failed",
    "run.lg",                      # t('run.lg'+Kind) 的动态前缀
}


def _keyish_literals():
    """所有裸字面量里像 key 的。t(a?'x.y':'x.z') 这种三元里的键，
    只扫 t('...') 会漏 —— 上一轮就是这样误删了 sb.tagBuiltin / sb.tagMine。"""
    out = set()
    for f in JS_FILES + [STATIC_DIR / "index.html"]:
        if f.name == "ui.js":
            continue
        out |= set(KEYISH.findall(f.read_text(encoding="utf-8")))
    return out


def test_no_untranslated_key_reaches_the_page(dicts):
    """页面上任何被当作文案取的字符串，字典里都得有；否则 UI 会直接印出 key。"""
    zh, _ = dicts
    stray = _keyish_literals() - zh - NOT_KEYS
    assert stray == set(), f"这些字符串像 key 但字典里没有，会原样显示：{sorted(stray)}"


def test_every_used_key_exists(dicts):
    zh, _ = dicts
    exact, prefixes = _used_keys()
    missing = {k for k in exact if k not in zh}
    assert not missing, f"用到但字典里没有：{sorted(missing)}"
    for p in sorted(prefixes):
        assert any(k.startswith(p) for k in zh), f"动态前缀 {p} 在字典里一个 key 都没有"


def test_no_dead_key_outside_allowlist(dicts):
    """字典里留了没人用的 key：加条目前先想清楚是不是真的需要文案。
    判定必须并上 _keyish_literals()，不然三元里的引用会被当成死键删掉。"""
    zh, _ = dicts
    exact, prefixes = _used_keys()
    used = (exact | _keyish_literals()
            | {k for k in zh if any(k.startswith(p) for p in prefixes)})
    dead = zh - used
    assert dead == set(), f"字典里再没人用的 key：{sorted(dead)}"


# ---------------- CSS ----------------

def test_every_used_css_var_is_defined():
    defined = set(re.findall(r"(--[\w-]+)\s*:", CSS))
    # 带兜底值的 var(--x, fallback) 允许不在 CSS 里定义：那是 JS 运行时写进来的
    # （如更新胶囊的 --p 进度），缺了也只是走兜底，不会破样式。
    used = set(re.findall(r"var\((--[\w-]+)\)(?!\s*,)", CSS))
    assert used - defined == set(), f"用了没定义的变量：{sorted(used - defined)}"


def test_t_lookup_keeps_intentionally_empty_strings():
    """有些描述是故意留空的（某些分区不要副标题）。用 || 取字典会把空串
    当成缺失，直接把 'set.appearanceD' 这种 key 吐到页面上。"""
    body = re.search(r"function t\(key, params\) \{(.*?)\n\}", UI_JS, re.S)
    assert body, "找不到 t() 实现"
    code = re.sub(r"/\*.*?\*/|//[^\n]*", "", body.group(1), flags=re.S)
    assert "||" not in code, "t() 又用 || 取字典了，空文案会被渲染成 key 本身"


def test_every_stylesheet_has_balanced_comments():
    """CSS 注释里出现 */ 会**提前关掉**那条注释，剩下的中文就成了非法声明。
    2026-10-05 真踩过：给 voyra-foundation.css 写注释时打了
    "--vr-canvas/surface*/line*" 这样的字面量，那个 */ 把 :root 整块废掉，
    于是 --vr-radius-control 取空、全站按钮圆角塌成 0、min-height 一起失效 ——
    而 style.css 的契约测试一条都不会红，因为它读的是另一个文件。
    这条把四个样式表都扫一遍：注释必须成对，且 :root 那块真的解析得出来。"""
    for name in ("style.css", "voyra-ui.css", "voyra-foundation.css", "voyra-software-base.css"):
        s = (STATIC_DIR / name).read_text(encoding="utf-8")
        depth = 0
        i = 0
        while i < len(s):
            if s[i] == "/" and i + 1 < len(s) and s[i + 1] == "*":
                depth += 1
                i += 2
            elif s[i] == "*" and i + 1 < len(s) and s[i + 1] == "/":
                assert depth > 0, f"{name} 第 {i} 字符附近出现没有配对的 */（注释被提前关掉）"
                depth -= 1
                i += 2
                continue
            else:
                i += 1
        assert depth == 0, f"{name} 有 {depth} 条注释没关掉"
        stripped = re.sub(r"/\*.*?\*/", "", s, flags=re.S)
        assert stripped.count("{") == stripped.count("}"), f"{name} 去掉注释后花括号不平"
    for name in ("voyra-foundation.css",):
        s = (STATIC_DIR / name).read_text(encoding="utf-8")
        assert re.search(r":root\s*\{[^}]*--vr-canvas\s*:", s), \
            f"{name} 的 :root 块解析不出 --vr-canvas —— 十有八九是注释吃掉了它"


def test_no_hardcoded_hex_outside_token_blocks():
    """颜色一律走 var()，否则深色模式必破；只有 :root / html[data-*] 里能写字面色。"""
    bad, in_tokens = [], False
    for ln in CSS.splitlines():
        s = ln.strip()
        if s.endswith("{"):
            head = s[:-1].strip()
            in_tokens = head.startswith(":root") or head.startswith("html[")
        elif s == "}":
            in_tokens = False
        elif not in_tokens and re.search(r"#[0-9a-fA-F]{3,8}\b", s):
            bad.append(s[:80])
    assert not bad, f"这些规则写死了色值，切主题会破：{bad[:6]}"


RADIUS_SCALE = {"--r-1", "--r-2", "--r-3", "--r-4", "--r-5", "--r-pill"}


FONT_CSS = (STATIC_DIR / "fonts" / "fonts.css").read_text(encoding="utf-8")
# 八档：micro/meta/sub/body/lead + 两个展示档 + 数据大字。曾经还有 --fs-h3，
# 唯一的用户是列表页 .page-head h1，那整块早没人引用了，删掉后这一档就空了 ——
# 刻度上留一个没人站的格子，只会被下一个人随手填个新数值。
# --fs-stat 是这一轮按参考图像素量出来的（统计条那排数字字高 ≈20px）：
# lead 14.3 太小、h2 23.4 太大，只有 .st-strip b 用着。
FS_TOKENS = {"micro", "meta", "sub", "body", "lead", "h2", "h1", "stat"}


def test_font_faces_declare_one_standard_weight_each():
    """@font-face 里重复写 font-weight 时后一条生效。MiSans 子集原本先写 400
    再写原生的 330，结果全站正文都掉进 Demibold 字面、600/650/700 全挤成 Bold，
    英文看着就发糊。四档必须正好是 400/500/600/700。"""
    rules = re.findall(r"@font-face\s*\{(.*?)\}", FONT_CSS, re.S)
    assert rules, "没读到 @font-face"
    weights = []
    for r in rules:
        ws = re.findall(r"font-weight\s*:\s*([\d.]+)", r)
        assert len(ws) == 1, f"有条规则写了 {len(ws)} 个 font-weight：{ws}"
        weights.append(ws[0])
    assert set(weights) == {"400", "500", "600", "700"}, f"字面档位不对：{sorted(set(weights))}"


def test_css_never_asks_for_an_undeclared_weight():
    """请求一个没声明的字重会走 CSS 的字重匹配算法，结果反直觉
    （要 400 会给 450），所以 style.css 里只准出现已声明的四档。"""
    declared = {float(x) for x in re.findall(r"@font-face\s*\{[^}]*?font-weight\s*:\s*([\d.]+)",
                                             FONT_CSS, re.S)}
    used = {float(x) for x in re.findall(r"font-weight\s*:\s*(\d+)", CSS)}
    assert used <= declared, f"用了没声明的字重：{sorted(used - declared)}"


def test_font_sizes_go_through_the_scale():
    """字号只准取 --fs-* 那 8 档；em 是相对父级、clamp 是展示标题，另算。"""
    used, bare = set(), []
    for m in re.finditer(r"font-size\s*:\s*([^;}]+)", CSS):
        val = m.group(1).strip()
        used |= set(re.findall(r"var\((--fs-[\w-]+)\)", val))
        if re.fullmatch(r"[0-9.]+rem", val):
            bare.append(val)
    assert used <= {f"--fs-{k}" for k in FS_TOKENS}, f"字号令牌不在刻度里：{sorted(used)}"
    assert not bare, f"又出现了裸 rem 字号，请归到 var(--fs-*)：{bare[:8]}"


def test_every_fs_token_is_defined_and_used():
    defined = set(re.findall(r"(--fs-[\w-]+)\s*:", CSS))
    used = set(re.findall(r"var\((--fs-[\w-]+)\)", CSS))
    assert defined == {f"--fs-{k}" for k in FS_TOKENS}, f"档位定义不齐：{sorted(defined)}"
    assert defined - used == set(), f"定义了却没人用的档位：{sorted(defined - used)}"


def test_mono_font_mode_actually_starts_monospace():
    """等宽档若把 MiSansWeb 排在最前，拉丁字母就永远轮不到等宽字体。"""
    mono = re.search(r'html\[data-font="mono"\]\s*\{\s*--font-ui\s*:\s*([^;]+);', CSS)
    assert mono, "找不到等宽档"
    assert mono.group(1).strip().startswith("var(--font-mono)"), mono.group(1).strip()


def test_slider_readout_shares_the_css_root_size():
    """滑块读数说「13px」是从 CSS 的 1rem 基准换算来的。
    基准改了不改常量，读数就一直在报一个界面上不存在的字号。"""
    m = re.search(r"html\{font-size:calc\((\d+(?:\.\d+)?)px \* var\(--text-scale\)\)", CSS)
    assert m, "html 的 font-size 不再是 calc(<n>px * var(--text-scale))，读数逻辑得一起改"
    j = re.search(r"const ROOT_PX = (\d+(?:\.\d+)?);", APP_JS)
    assert j, "app.js 里找不到 ROOT_PX 常量"
    assert float(m.group(1)) == float(j.group(1)), f"CSS {m.group(1)}px ≠ JS {j.group(1)}"


def test_appearance_controls_read_from_the_option_maps():
    """滑块的档位、APP 的当前值、落盘的键名三处同名。改了任一处而没改另两处，
    滑块会静默停在 0 档，或者拖了却没人存。"""
    for key, table in (("textSize", "TEXT_SIZES"), ("uiZoom", "ZOOMS"), ("contentWidth", "WIDTHS")):
        assert f"{key}: () => Object.keys(window.AP_OPTS.{table})" in APP_JS, f"{key} 滑块没走 {table}"
        assert f"'{key}'" in UI_JS, f"loadAppearance 的白名单里没有 {key}"
    for key in ("THEMES",):
        assert f"window.AP_OPTS.{key}.map" in APP_JS, f"{key} 磁贴没走 AP_OPTS"


def test_accent_setting_is_gone_for_good():
    """品牌位交给黑白反转之后，"可换强调色"就没有可换的东西了 —— 留着它是一个
    拖了没人存的控件。这类"设置项还在、值还落库、代码不再读"的孤儿键以前踩过，
    所以把退场清单钉死：任何一处复活都要连带改回另外三处。"""
    for blob, name in ((APP_JS, "app.js"), (UI_JS, "ui.js"),
                       (INDEX_HTML, "index.html"), (CSS, "style.css")):
        for token in ("ACCENTS", "apAccent", "ui_accent", 'data-accent', "ap.accent"):
            assert token not in blob, f"{name} 里又出现了 {token}"


APP_JS = (STATIC_DIR / "app.js").read_text(encoding="utf-8")
INDEX_HTML = (STATIC_DIR / "index.html").read_text(encoding="utf-8")

# 路由 view -> 该高亮哪个导航项。曾经 pipelines / pipeline-edit 还写着 'home'
# （那是「工作流」还没独立成导航项时的遗留），点进去高亮就停在工作台。
NAV_OF_VIEW = {
    "skills": "skills", "skill-edit": "skills",
    "pipelines": "pipelines", "pipeline-edit": "pipelines",
    "runs": "runs", "run": "runs",
    "settings": "settings",
}


def test_router_highlights_the_matching_nav_item():
    calls = dict(re.findall(r"view==='([\w-]+)'\)\s*await run\([^,]+,\s*'([\w-]+)'\)", APP_JS))
    wrong = {v: (calls.get(v), want) for v, want in NAV_OF_VIEW.items() if calls.get(v) != want}
    assert not wrong, f"路由高亮键不对 {wrong}"
    # 只认导航项那种三件套；下拉框配置（ffSelect 的 {id, icon, onChange}）同形不同职
    nav_ids = set(re.findall(r"\{id:'([\w-]+)',\s*icon:'[\w-]+',\s*label:t\('nav\.", APP_JS))
    assert nav_ids == {"newTask", "pipelines", "skills", "runs"}, f"导航项变了：{nav_ids}"
    # 首页本身仍然不是导航项：它是默认路由，看得见的入口是主导航第一行「新建任务」
    # （2026-09-22 用户要求 composer 长在首页；23 又把入口收成导航行，别再有一个通栏按钮）。
    assert "home" not in nav_ids, "首页不该是导航项 —— 入口只有「新建任务」那一行"
    assert "view==='home') await run(window.renderHome" in APP_JS, "首页路由没了"
    assert "!raw) raw = 'home'" in APP_JS, "默认路由不再是首页"
    assert 'class="modal open" role="dialog"' not in APP_JS or "taskModalRoot" not in APP_JS, "输入台又退回弹层了"
    stray = set(calls.values()) - nav_ids - {"settings", "home"}
    assert stray == set(), f"高亮键指向了不存在的导航项：{sorted(stray)}"


def test_every_settings_section_has_a_subtitle_key():
    """页头副标题走的是 t('set.'+id+'D') 这种拼接键 —— 宽前缀让
    test_every_used_key_exists 恒过（'set.' 当然有 key），缺哪一条就只会
    在界面上把原始键名印出来。这里按分区清单逐个点名，堵住这个口径。"""
    zh, en = _dict_block("zh"), _dict_block("en")
    ids = re.findall(r"\['([\w-]+)',\s*'set\.", APP_JS)
    assert ids, "没从 SET_SECTIONS 里解析出分区 id"
    for i in sorted(set(ids)):
        assert f"'set.{i}D'" in zh, f"分区 {i} 没有 set.{i}D，页头会印出原始键名"
        assert f"'set.{i}D'" in en, f"分区 {i} 的英文副标题缺失"


def test_settings_is_not_duplicated_in_the_main_nav():
    """设置只有一个入口：左下角那一行弹层里的「设置」。外层齿轮按钮已撤，
    同一格现在归更新胶囊。"""
    items = re.search(r"const items = \[(.*?)\];", APP_JS, re.S).group(1)
    assert "id:'settings'" not in items, "主导航里又加回设置了，和左下角入口重复"
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    assert "sbSettingsBtn" not in html, "外层设置按钮又回来了"
    assert "sbUpdate" in html, "左下角那一格应该留给更新胶囊"
    assert "nav.go('settings')" in APP_JS, "弹层里的设置入口没了"


def test_border_radius_only_uses_the_scale():
    used, literal = set(), []
    for m in re.finditer(r"border-radius\s*:\s*([^;}]+)", CSS):
        val = m.group(1)
        used |= set(re.findall(r"var\((--[\w-]+)", val))
        if "var(--" not in val and "50%" not in val:
            literal.append(val.strip()[:60])
    assert used <= RADIUS_SCALE, f"圆角变量不在角色刻度里：{sorted(used - RADIUS_SCALE)}"
    assert not literal, f"圆角写了字面值，请改用 var(--r-*)：{literal[:6]}"


def test_no_class_in_markup_without_a_rule():
    """模板里写了个 CSS 没有的类名，页面不会报错，只会静默少一层样式 ——
    本次就是这样写出过一个 .pl-row-sub，量出来字号还是正文 13px。
    只认完整的字面量片段（${} 抠掉、结尾带连字符的丢掉），宁可漏报不误报。"""
    used = set()
    for f in JS_FILES + [STATIC_DIR / "index.html"]:
        for m in re.finditer(r'class="([^"]*)"', f.read_text(encoding="utf-8")):
            v = re.sub(r"\$\{[^{}]*\}", " ", m.group(1))
            used |= {t for t in v.split() if re.fullmatch(r"[a-zA-Z][\w-]*[a-zA-Z0-9]", t)}
    # New adapters are loaded by index.html; validate the actual stylesheet set,
    # not only the original monolithic style.css.
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    linked = re.findall(r'href="/static/([^"?]+\.css)(?:\?[^" ]*)?"', html)
    linked_css = "\n".join((STATIC_DIR / name).read_text(encoding="utf-8") for name in linked)
    defined = set(re.findall(r"\.([a-zA-Z][\w-]*)", linked_css))
    missing = used - defined
    assert not missing, f"这些类名在已加载的样式中没有规则：{sorted(missing)}"


def test_no_static_inline_typography_or_spacing():
    """字号/内边距写进 style="" 就绕过了刻度和令牌测试（.85rem 这种就是这么漏掉的）。
    动态算出来的宽度（style="width:${pct}%"）不在此列。"""
    bad = []
    for f in JS_FILES:
        for m in re.finditer(r'style="([^"]*)"', f.read_text(encoding="utf-8")):
            if re.search(r"(font-size|padding|margin|line-height|color|border-radius)\s*:", m.group(1)):
                bad.append(f"{f.name}: {m.group(0)[:60]}")
    assert not bad, f"这些内联样式该落到 class 上：{bad}"


def test_font_sizes_have_a_readable_floor():
    """1rem = 13px，0.72rem 已经到 9.4px，再小就是给视力好的程序员设计的。"""
    small = [m.group(1) for m in re.finditer(r"font-size\s*:\s*([0-9.]+)rem", CSS)
             if float(m.group(1)) < 0.72]
    assert not small, f"这些字号小到读不动：{small}"


@pytest.mark.parametrize("name", ["logo.svg", "favicon.svg"])
def test_brand_svg_is_self_contained(name):
    svg = (STATIC_DIR / name).read_text(encoding="utf-8")
    assert svg.lstrip().startswith("<svg")
    assert "currentColor" not in svg, "图标 SVG 不能依赖 currentColor，<img> 里不生效"
    for gid in re.findall(r"url\(#([\w-]+)\)", svg):
        assert f'id="{gid}"' in svg, f"{name} 引用了不存在的渐变 {gid}"


# ---------------- 侧栏项目行嵌套最近运行 ----------------

def test_relative_time_uses_the_reference_four_tiers():
    """参考实现只有四档紧凑写法，没有月/年档（taskListItemPresentation.ts:33-53）。
    阈值差一档，侧栏上就是"7 天前"和"0 天前"的区别 —— 所以让 node 真把函数跑一遍。"""
    import subprocess
    js = ("const s=require('fs').readFileSync(process.argv[1],'utf8');"
          "const grab=(n)=>s.match(new RegExp('function '+n+'\\\\([\\\\s\\\\S]*?\\\\n\\\\}'))[0];"
          "eval(grab('parseLdb'));eval(grab('relUnit'));"
          "const q=JSON.parse(process.argv[2]);"
          "console.log(JSON.stringify(q.map(([a,b])=>relUnit(a,b))));")
    # 库里存的是本地时间串（db._now 用 time.strftime），parseLdb 也按本地解释，
    # 所以两端都用 localtime 格式化才不会因机器时区而漂 —— 别写 gmtime±8。
    fmt = lambda ms: time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ms / 1000))
    NOW = 1777000000000                      # 定死一个"现在"，别用 Date.now
    cases = [(NOW - 30_000,        {"s": 0, "u": "now"}),
             (NOW - 59_000,        {"s": 0, "u": "now"}),
             (NOW - 60_000,        {"s": 1, "u": "m"}),
             (NOW - 59 * 60e3,     {"s": 59, "u": "m"}),
             (NOW - 60 * 60e3,     {"s": 1, "u": "h"}),
             (NOW - 23.9 * 3600e3, {"s": 23, "u": "h"}),
             (NOW - 24 * 3600e3,   {"s": 1, "u": "d"}),
             (NOW - 40 * 86400e3,  {"s": 40, "u": "d"}),   # 40 天仍是「天」，不给月档
             (NOW + 5 * 60e3,      {"s": 0, "u": "now"})]  # 时钟没同步：别印 -5 分
    # relUnit(iso, nowMs)：iso 是库里的时间串，now 是毫秒数 —— 别把 now 也格式化成串，
    # 那样 "2026-04-24 12:26:40" - 数字 = NaN，四档全部退化成"刚刚"。
    payload = json.dumps([[fmt(ms), NOW] for ms, _ in cases])
    r = subprocess.run(["node", "-e", js, str(STATIC_DIR / "app.js"), payload],
                       capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, r.stderr[:400]
    got = json.loads(r.stdout)
    assert got == [w for _, w in cases], f"阈值不对：{list(zip(got, [w for _, w in cases]))}"


def test_recent_runs_are_nested_under_their_project_not_listed_twice():
    """同一个 run 在侧栏出现两次 = 两个入口管一件事。
    参考实现是嵌在项目行下面、用一条左边框轨道缩进（workspace-grouped-tasks/types.ts:35-47）。"""
    seg = APP_JS.split("async function renderSidebarLists(")[1].split("\n}\n")[0]
    assert 'class="sb-run sb-sub' in seg, "run 没嵌进项目行"
    assert ".sb-runlist" in CSS, "缩进要有一层容器"
    rail = CSS.split(".sb-runlist")[1][:220]
    # 2026-10-05 逐像素扫参考图：嵌套行左边从 x=50 一路到 x=300 都是同一个
    # #242624，没有任何一列是缝色 —— 那条 border-left 在人家那里是缩进辅助线，
    # 不是界面元素。旧断言引的是 types.ts:35-47 的 ml-4 border-l pl-2，
    # 引的是源码而不是像素，所以它把一条不该存在的杆子钉成了契约。
    # 反过来钉住：轨道必须没有，缩进必须还在（margin+padding 两道）。
    assert "border-left" not in rail, "嵌套行左边又长出轨道了（参考图量的那条没有）"
    assert "margin-left:12px" in rail and "padding-left:8px" in rail, \
        "轨道删了要留缩进，否则项目和它的任务看起来是两拨不相干的行"
    assert "t('sb.recent')" not in seg, "「最近运行」那一组还在 —— 现在它是重复入口"
    assert "relTime(" in seg, "次行没打相对时间"
    assert "sb-gcount" in seg, "在跑计数挂在分组标题上，不是每行一个"
    # 每组最多两条：侧栏是入口不是清单
    assert ".slice(0, 2)" in seg or ".slice(0,2)" in seg, "嵌套行要有上限"


# ---------------- 首页输入台：三段 + 引擎选择器 ----------------

def _composer():
    return APP_JS.split('function tkStageHtml(')[1].split('\n}\n')[0]


def test_composer_has_a_bottom_toolbar_with_an_engine_picker():
    """参考实现的输入台是三段：上=上下文（选哪条流程），中=textarea，
    下=工具条（左边是动作，右边挨着发送）。我们原来只有上+中+一条塞着名字输入的行。"""
    seg = _composer()
    assert 'class="tk-top"' in seg and 'class="tk-field"' in seg and 'class="tk-bar"' in seg, \
        "输入台不是三段（上/中/下工具条）"
    assert ".tk-bar" in CSS, "新的一段得有自己的规则，不然只是换个名字"
    assert 'id:\'tkEngine\'' in seg, "工具条里没有引擎选择器"
    assert "taskStart()" in seg, "发送按钮没接上"
    assert "${ico('arrowUp')}" in seg, "发送键要换成参考实现那个向上箭头（原来那枚是纸飞机）"
    assert ".tk-foot" not in CSS, "旧的脚部规则还留着，两代结构会互相盖"


def test_composer_offers_only_controls_the_backend_actually_reads():
    """引擎和模型都是真能力：RunStartIn.engine / RunStartIn.model（app/main.py:490）
    → start_run 校验后逐步覆盖（app/runner.py:841-857）。
    这一条以前钉的是"输入台里不许出现 model"，因为那时后端没有这个参数；
    现在有了，改钉"候选必须来自真清单"（见 test_composer_model_chip_lists_only_real_presets）。"""
    seg = _composer()
    assert "v:'', label:t('ed.engineDefault')" in seg, "首项必须是「默认」：空串才沿用步骤自带引擎"
    assert "filter(a=>a.found)" in seg, (
        "引擎候选必须来自实测盘点：本机没装 codex 时选它，第一条任务就死在起进程那一步")
    assert "{v:'claude'" not in seg and "{v:'codex'" not in seg, "两家 CLI 不许再写死"
    assert "id:'tkModel'" in seg, "运行级模型覆盖的 chip 没了"
    assert "p.model" in seg, "菜单里的说明要用预设真有的字段，不是拼出来的假信息"


def test_picked_engine_is_sent_and_labelled():
    """选择器写了却不发出去就是装饰；选了也不该在下一行任务里悄悄留着。"""
    seg = APP_JS.split('window.taskStart = async function()')[1].split('\n};')[0]
    assert "engine: TK_ENG" in seg, "请求体里没把选中的引擎发出去"
    assert "tkEngineSet" in _composer(), "onChange 要接住选择器的值"
    assert "let TK_ENG = ''" in APP_JS, "初值不是空串会覆盖掉步骤自带的引擎"
    body = APP_JS.split('window.tkEngineSet')[1].split('\n};')[0] if 'window.tkEngineSet' in APP_JS else ''
    assert "TK_ENG = v || ''" in body, f"回填写歪了：{body[:80]}"

# ---------------- 更新：居中三态浮层 ----------------

def test_update_offers_a_centered_dialog_not_just_a_capsule():
    """胶囊留着当状态指示；三态标题 / 进度条 / MB 读数 / 动作按钮在居中浮层里。
    参考实现就是"胶囊 + 对话框"两件套（UpdateStatusButton + UpdateStatusDialog）。"""
    for k in ("upOpen", "upClose", "upDownload", "upApply", "upCheckNow"):
        assert f"window.{k}" in APP_JS, f"缺 {k}"
    assert 'id="upCard"' in INDEX_HTML and 'class="up-mask"' in INDEX_HTML
    assert "z-index:var(--z-modal)" in CSS.split(".up-mask")[1][:200], "遮罩要走 z 刻度"
    shell = CSS.split(".up-card{")[1][:320]
    assert "border-radius:var(--r-5)" in shell, "对话框壳属于 2xl 例外档"
    for key in ("up.tAvailable", "up.tDownloading", "up.tReady"):
        assert f"t('{key}'" in APP_JS, f"三态标题缺 {key}"


def test_update_dialog_renders_the_release_notes():
    """清单里的 notes 从 make_release 一路传到 STATE，却一直没被渲染 ——
    发版时写的那段说明，用户在软件里一个字都看不到，浮层只有版本号和一个按钮。"""
    seg = APP_JS.split('function upCardHtml(')[1].split('\n}\n')[0]
    assert 'class="up-notes"' in seg, "发版说明没进浮层"
    assert "${esc(u.notes)}" in seg, "notes 必须转义：它是清单里来的外部文本，全站没有 CSP"
    assert "u.phase !== 'error'" in seg, "出错那一轮要看的是错误原因，别叠一段说明"
    assert ".up-notes{" in CSS, "样式没落地，那段说明会挤成一行"
    body = CSS.split(".up-notes{")[1].split("}")[0]
    assert "max-height" in body and "overflow-y:auto" in body, \
        "清单里 notes 最长 2000 字，不封顶会把浮层顶成半屏高"


def test_the_selector_registry_does_not_grow_forever():
    """没传 id 的 ffSelect 每次渲染都领一个新号（ffs1、ffs2…），条目登记进 FF_SEL
    就没人删。编辑器每步两三枚、每重画一遍换一批号，长会话能攒上千条，
    每条还攥着整份 opts 数组。"""
    body = APP_JS.split("function ffPrune()")[1].split("\n}")[0]
    assert "querySelectorAll('.ff-sel')" in body, "判据必须是「按钮还在不在 DOM 里」"
    assert "delete FF_SEL[k]" in body, "没真删条目"
    opener = APP_JS.split("window.ffOpen = function")[1].split("\n};")[0]
    assert "ffPrune()" in opener, "修剪要挂在 ffOpen 上：那一刻点击方已在 DOM 里"
    maker = APP_JS.split("function ffSelect(")[1].split("\n}\n")[0]
    assert "ffPrune" not in maker, \
        "不能在 ffSelect 里修剪：那时它生成的字符串还没进 DOM，会把同一轮刚登记的活条目一起删掉"


def test_update_dialog_shows_real_progress_and_no_fake_buttons():
    """进度条刻度来自 got/size，不是装饰；后端只有 check/download/apply/url 四条端点，
    所以参考实现里的「取消下载」「跳过此版本」「自动下载并安装」我们一概不放。"""
    seg = APP_JS.split('function upCardHtml(')[1].split('\n}\n')[0]
    assert "up-fill" in seg and "width:${pct}%" in seg, "进度条没接 got/size"
    assert "mb(u.got" in seg and "mb(u.size" in seg, "缺「已传 / 共」读数"
    for fake in ("取消下载", "跳过此版本", "skipVersion", "cancelDownload", "自动下载"):
        assert fake not in seg, f"{fake} 是假按钮：后端没有这个端点"
    # 更新会退出进程，所以在跑/停在检查点的任务要先拦住（下载和安装两处都要）。
    # 拦的形状从"弹系统框问一句"换成了"第一下只上膛"：不 POST，先把后果摆在按钮上方。
    dl = APP_JS.split('window.upDownload = async function')[1].split('\n};')[0]
    ap = APP_JS.split('window.upApply = async function')[1].split('\n};')[0]
    assert "upArm('download')" in dl and "active_runs" in dl, "下载前不再看在跑的任务了"
    assert "upArm('apply')" in ap and "await post" in ap, "安装要么没上膛、要么根本没发请求"
    assert ap.index("upArm('apply')") < ap.index("await post"), "第一下就发请求，等于没有确认这一步"


def test_update_dialog_refreshes_with_the_poller_and_closes_on_escape():
    """浮层开着时状态是轮询推来的，不刷就成了过期数字；关掉的路径要有两条。"""
    pu = APP_JS.split('function paintUpdate()')[1].split('\n}\n')[0]
    assert "upRepaintDialog()" in pu, "状态变了浮层不跟着刷，用户看到的是过期进度"
    esc = APP_JS.split("if(e.key==='Escape')")[1][:900]
    assert "upCard" in esc, "Escape 没关更新浮层"
    """关闭顺序要跟 z 刻度一致：谁画在上面先关谁。--z-menu(100) 压过 --z-modal(60)，
    所以菜单先关。以前这条比的是源码先后 —— 顺序看着对，层级其实是另一回事，
    于是出现了"浮层关了、菜单还飘在原地"。"""
    z = dict(re.findall(r"--(z-[a-z]+):(\d+)", CSS))
    assert int(z["z-menu"]) > int(z["z-modal"]), "z 刻度变了，下面的关闭顺序要重看"
    assert esc.index("ffMenu") < esc.index("upCard"), "Escape 顺序和 z 刻度反了"
    assert 'onclick="upClose()"' in INDEX_HTML, "点遮罩要能关"


def test_update_dialog_survives_a_check_with_no_new_version():
    """胶囊没东西可报就收起是对的，但顺手把用户正开着的浮层关掉不对 ——
    点「重新检查」，窗口凭空消失，什么话都没说。"""
    pu = APP_JS.split('function paintUpdate()')[1].split('\n}\n')[0]
    assert "window.upClose()" not in pu, "paintUpdate 里不该直接关浮层"
    card = APP_JS.split('function upCardHtml(')[1].split('\n}\n')[0]
    assert "up.tUpToDate" in card, "没新版本时浮层要有的说，而不是空白或消失"


def test_update_dialog_repaint_keeps_focus_and_click_targets():
    """下载中每 400ms 轮询一次。整块换 innerHTML 会把焦点从 ✕ 上踢掉，
    还会让你按下去的那一瞬正好赶上按钮被替换 —— 所以要按阶段变化才重画结构。"""
    rp = APP_JS.split('window.upRepaintDialog = function()')[1].split('\n};')[0]
    assert "dataset.phase" in rp, "没按阶段判断，每次轮询都在整块重刷"
    assert "fill.style.width" in rp, "阶段没变时只该改进度条宽度和字节数"


def test_closed_modal_mask_does_not_swallow_clicks():
    """.up-mask 是 inset:0 的全屏层。只靠 opacity:0 收起 = 整个应用点不动，
    而且 DOM 上看不出来，只有手点才知道 —— 所以钉成测试。"""
    mask = CSS.split(".up-mask{")[1][:240]
    assert "pointer-events:none" in mask, "遮罩收起时没关指针，会吃掉全屏点击"
    on = CSS.split("body.up-on .up-mask{")[1][:120]
    assert "pointer-events:auto" in on, "展开时又忘了把指针还给遮罩"


def test_update_box_carries_no_download_arrow():
    """用户点名：「不要有下载的小箭头」。available 与 downloading 两态都不再画图标 ——
    进度由百分比和进度条说，不需要一个箭头再说一遍"在下"。"""
    v = APP_JS.split("function upView(")[1].split("\n}\n")[0]
    assert v.count("ic:''") >= 2, "下载相关两态还挂着图标"
    assert "ic:'download'" not in v and 'ic:"download"' not in v
    pu = APP_JS.split("function paintUpdate(")[1].split("\n}\n")[0]
    assert "v.ic ?" in pu, "图标 span 还是无条件渲染，去掉 ic 也还是会画出默认那颗"
    i = pu.index("v.ic ?")
    assert "'download'" not in pu[i:i + 90], "兜底值又把下载箭头放回来了"


def test_hovering_the_box_shows_what_the_update_contains():
    """用户点名：悬停要能看到更新的内容。发版说明在 STATE 里一直有，
    以前只有点开浮层才看得到；提示框宽 264px，所以截断而不是整段塞。"""
    assert "function upNoteTip(" in APP_JS
    tip = APP_JS.split("function upNoteTip(")[1].split("\n}\n")[0]
    assert "140" in tip and "notes" in tip, "没截断或没取 notes"
    v = APP_JS.split("function upView(")[1].split("\n}\n")[0]
    assert v.count("+ note") >= 3, "三态里有的没带上更新内容"


def test_install_confirm_talks_about_restarting():
    """用户的原话是"点击确认后，直接自动更新并重启"，所以文案里得是重启，
    而不是上一版那句"装完要自己再打开"—— 行为改了之后那句话就是错的。"""
    zh = _dict_block("zh")

    def val(key):
        m = re.search(rf"'{re.escape(key)}':\s*'([^']*)'", zh)
        assert m, f"中文词典里找不到 {key}"
        return m.group(1)

    assert "并重启" in val("up.askApply"), val("up.askApply")
    assert val("up.askGo") == "安装并重启"
    assert "重启" in val("up.applyStarted"), val("up.applyStarted")
    assert "自己再打开" not in val("up.askApply")
    iss = (STATIC_DIR.parent / "installer.iss").read_text(encoding="utf-8")
    # 只看真执行的行：注释里写着"不带 skipifsilent"这句话本身就会被子串判红 ——
    # 这一轮已经被自己的注释绊过好几回了。
    run = [ln for ln in iss.split("[Run]")[1].splitlines()
           if ln.strip() and not ln.strip().startswith(";")]
    assert not any("skipifsilent" in ln for ln in run), \
        "又加上 skipifsilent 了：我们是 /SILENT 装的，装上之后窗口不会自己回来"


def test_the_app_downloads_an_update_without_being_asked():
    """用户的要求：进软件自动检测、检测到就下；点那一下只管"装不装"。
    所以三条检查路径（开机、胶囊里重检、设置页重检）都要接上自动下载。"""
    assert "async function upAutoDownload(" in APP_JS
    init = APP_JS.split("async function upInit(")[1].split("\n}\n")[0]
    assert "upAutoDownload()" in init, "开机那条路没接上"
    cn = APP_JS.split("window.upCheckNow = async function")[1].split("\n};")[0]
    assert "upAutoDownload()" in cn, "胶囊里重检没接上"
    st = APP_JS.split("window.checkNow = async function")[1].split("\n};")[0]
    assert "upAutoDownload()" in st, "设置页重检没接上"
    auto = APP_JS.split("async function upAutoDownload(")[1].split("\n}")[0]
    assert "available" in auto, "没判阶段就开下：已经在下的会被重复触发"


def test_no_native_confirm_anywhere_in_the_frontend():
    """原生 confirm() 在 WebView2 里顶着一句「127.0.0.1:8000 显示」—— 那是在报
    开发服务器来源，不是软件名字；按钮是系统蓝，跟黑白金的品牌无关；还会挂起
    整页线程。1.2.6 先换了装更新那两记，1.3.3 把剩余 11 处全部换成页内 ffAsk。
    这条是全局禁令：去注释后任何前端脚本都不许再出现 confirm(。
    （历史：本测试曾只盯 upApply/upDownload/applyUpdate 三个函数——
    按函数清单禁等于给没进清单的地方发通行证，2026-10-05 起改为全量。）"""
    for name in ("app.js", "editor.js", "run.js", "ui.js", "ff-confirm.js"):
        src = (STATIC_DIR / name).read_text(encoding="utf-8")
        body = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
        body = re.sub(r"(?m)^\s*//.*$", "", body)
        assert "confirm(" not in body, f"{name} 里还有原生 confirm("
    ask = (STATIC_DIR / "ff-confirm.js").read_text(encoding="utf-8")
    assert "window.ffAsk" in ask, "ffAsk 没挂到 window 上，11 处调用点会全部 ReferenceError"
    # 结构契约：渲染成 .modal.open > .modal-box，voyra-dialogs.js 才会接管
    # 焦点陷阱 / Esc / aria / 焦点还原——写成别的类名这些就全部静默失效。
    assert "modal open ff-ask" in ask and "modal-box" in ask
    assert 'data-safe-focus' in ask, "默认焦点必须落在取消上（危险操作的安全默认是不做）"
    assert 'data-dialog-close' in ask, "Esc 关闭走 voyra-dialogs 的 data-dialog-close"
    html = INDEX_HTML
    assert "ff-confirm.js" in html, "ff-confirm.js 没进 index.html，ffAsk 是空中楼阁"


def test_update_confirm_lives_in_the_card_and_says_what_it_costs():
    """两步确认在浮层内部完成：第一次点只是"上膛"，重画出一行后果说明再点才算数。
    原来那两记 confirm（退出 + 有任务在跑）是连着弹两个，现在并成一行。"""
    card = APP_JS.split("function upCardHtml(")[1].split("\n}\n")[0]
    assert 'class="up-ask"' in card, "确认那一行没进浮层"
    for key in ("up.askApply", "up.askDownload", "up.askBusyQuit", "up.askBusyDl", "up.askGo"):
        assert f"'{key}'" in card, f"缺文案 {key}"
    assert ".up-ask{" in CSS and ".up-ask-warn{" in CSS, "样式没落地，那一行会挤成一行字"
    body = CSS.split(".up-ask-warn{")[1].split("}")[0]
    assert "var(--bad)" in body, "打断在跑任务是这件事的代价，要用警示色而不是同一级灰"


def test_update_confirm_arms_repaints_and_disarms():
    """arm 状态变了但 phase 没变 —— 重画逻辑只认 phase 的话，按钮点下去什么都不发生。
    关掉浮层、换阶段、真的开始装了，三种情况都得把膛退掉，否则下次打开还停在确认行。"""
    rp = APP_JS.split("window.upRepaintDialog = function()")[1].split("\n};")[0]
    assert "dataset.ask" in rp, "重画只看 phase，上膛后不会换按钮"
    assert APP_JS.count("UP_ASK = ''") >= 3, "退膛的地方不够（关闭 / 换阶段 / 已发请求）"
    assert "window.upAsk" in APP_JS, "缺上膛入口"


def test_failed_apply_does_not_leave_a_dead_confirm_button():
    """发请求前先清标记的话，失败后浮层还画着「确认安装并退出」，可标记已经空了 ——
    再点一下只是重新上膛、画面纹丝不动，用户读到的是"这个按钮坏了"。
    源码态必现：后端直接回"没有可替换的程序"。"""
    ap = APP_JS.split("window.upApply = async function")[1].split("\n};")[0]
    assert ap.index("UP_ASK = ''") > ap.index("await post"), "清标记不该在发请求之前"
    assert "upRepaintDialog()" in ap[ap.index("await post"):], "失败后没重画，按钮停在假状态"


# ---------------- 侧栏折叠轨道 ----------------

RAIL_HIDDEN = {
    ".sb-name": "侧栏品牌字", ".sb-item span": "主导航（含行尾的键位提示 .sb-kbd，它也是 span）",
    ".sb-group>span": "分组标题", ".sb-gcount": "在跑计数",
    ".sb-gadd": "分组加号（和顶栏创建流程重复，轨道里两个加号分不清）",
    ".sb-garch": "归档切换（图标按钮，56px 轨道里和加号挤成一行）",
    ".sb-more": "行菜单（图标按钮，轨道里整行只剩一个图标）",
    ".sb-rname": "行标题",
    ".sb-rtag": "行右侧标签", ".sb-empty": "空态文案", ".sb-me-name": "引擎名",
    ".sb-me-chev": "齿轮后的箭头", ".sb-up-tx": "更新胶囊文字",
    ".sb-group:has(+ .sb-empty)": "空分组（轨道里只剩一条孤线，是噪声）",
    ".sb-runlist": "嵌套的最近运行（56px 轨道里小图标对不上父行的图标列，在跑数量已由铃铛报）",
}


def _rail_block():
    m = re.search(r"@media \(min-width:861px\)\{(.*?)\n\}", CSS, re.S)
    assert m, "找不到折叠轨道那一段（改动请连同本测试一起想清楚）"
    return m.group(1)


def test_rail_hides_every_text_label():
    """轨道只有 56px，任何没藏起来的文字都会把侧栏撑破或自己被打断。
    双向锁：藏多了（那个类已经不存在了）也算漂移。
    两种藏法都认：display:none 是整块撤（图标按钮、子列表），
    max-width:0 + opacity:0 是跟着盒子收（文字标签）—— 后者让折叠这一步
    不再是"内容先被清空、框子才缩"。但必须两个都在：只淡出不收宽度，
    文字就还占着 168px，轨道里会挤出一列看不见的空格。"""
    block = _rail_block()
    hidden = set()
    for sels in re.findall(r"([^{}]*)\{display:none\}", block):
        for s in sels.split(","):
            s = re.sub(r'^\s*html\[data-sidebar="collapsed"\]\s*', "", s.strip())
            if s:
                hidden.add(s)
    for sels, body in re.findall(r"([^{}]*)\{([^}]*)\}", block):
        if "max-width:0" not in body:
            continue
        assert "opacity:0" in body, \
            f"用 max-width:0 收起来的标签必须同时淡出，否则它只是看不见、还占着宽度：{sels[:80]}"
        for s in sels.split(","):
            s = re.sub(r'^\s*html\[data-sidebar="collapsed"\]\s*', "", s.strip())
            if s:
                hidden.add(s)
    missing = {k: v for k, v in RAIL_HIDDEN.items() if k not in hidden}
    assert not missing, f"折叠时这些文字没藏：{missing}"
    extra = hidden - set(RAIL_HIDDEN)
    assert not extra, f"轨道藏了清单外的类，请一并更新清单：{sorted(extra)}"


def test_rail_state_is_persisted_through_the_appearance_channel():
    """折叠态走的是 ui_ 外观通道。少一环就变成「重启回到展开」或「按了没反应」。"""
    assert "ui_sidebar:'sidebar'" in INDEX_HTML, "启动预取没读 ui_sidebar，会闪一下全宽侧栏"
    assert "document.documentElement.dataset.sidebar" in INDEX_HTML, "启动时没落 data-sidebar"
    assert "html.dataset.sidebar" in UI_JS, "applyAppearance 不落 data-sidebar"
    assert "'sidebar'" in UI_JS, "loadAppearance 的回退清单里没有 sidebar"
    assert "sidebar: 'expanded'" in UI_JS, "APP 缺 sidebar 默认值"
    assert "setAppearance({sidebar:" in APP_JS, "sbToggle 没把折叠态写回设置"


KEY_ROW = re.compile(r"\{id:'([A-Za-z]+)',\s*chord:'([^']+)',\s*key:'([^']*)',\s*"
                     r"mod:'([^']*)',\s*scope:'(\w)'")


def _keymap_rows():
    return KEY_ROW.findall(APP_JS)


def test_keybindings_come_from_one_table_and_are_all_documented():
    """参考实现把键位当"唯一事实来源"（shortcutCommands.ts:57-100）。
    我们以前是绑定一处、说明一处，靠正则比对两边 —— 表化之后两边同源，
    这条测试改查三件真的会出事的事：全局条目没处理函数、处理函数没人绑、
    以及品牌位不再是那个可聚焦的开关。"""
    # 无边框之后折叠开关搬到了标题行右侧（品牌位退回纯标识，不再兼任开关）
    brand = re.search(r'<button class="[^"]*ic-btn[^"]*"[^>]*id="tbCollapse"[^>]*>', INDEX_HTML)
    assert brand, "找不到标题行里的侧栏开关"
    assert 'onclick="sbToggle()"' in brand.group(0), "标题行那枚开关没接上 sbToggle"

    rows = _keymap_rows()
    assert rows, "KEYMAP 表不见了或字段顺序变了"
    ids = [r[0] for r in rows]
    assert len(ids) == len(set(ids)), "键位表里有重复 id"
    chords = [r[1] for r in rows]
    assert len(set(chords)) == len(chords), "两条键位撞在同一个和弦上"

    body = APP_JS.split('const KEY_ACTION = {')[1].split('\n};')[0]
    glob = [r[0] for r in rows if r[4] == 'g']
    assert set(glob) == {'newTask', 'search', 'toggleSb', 'settings',
                         'switchTheme', 'close'}, f"全局键位集合变了：{sorted(glob)}"
    for i in glob:
        if i == 'close':
            continue          # close 走 Escape 专用分支：多层浮层要一层层关，不是一句 ACTION
        assert re.search(r"\b" + i + r"\s*:", body), f"{i} 声明成全局键位却没有处理函数"
    assert "KEYMAP.find(" in APP_JS, "keydown 还在写死的 if 链里，没走表"
    assert "if(k==='k')" not in APP_JS and "if(k==='b')" not in APP_JS, "残留写死的 Ctrl 分支"
    # 表就是文档源：设置页不能再自己抄一份字面量
    assert "KEYMAP.map(r =>" in APP_JS, "键位说明页没从表里渲染"


def test_the_reference_chord_map_is_preserved():
    """逐条对着参考实现的表核一遍（shortcutCommands.ts:63-83）。
    键位改一次就固化了，不写死断言下次会被人顺手改回去。"""
    want = {'newTask': 'Ctrl N', 'search': 'Ctrl K', 'toggleSb': 'Ctrl B',
            'settings': 'Ctrl ,', 'switchTheme': 'Ctrl Shift L', 'close': 'Esc',
            'send': 'Enter'}
    rows = {r[0]: r[1] for r in _keymap_rows()}
    off = {k: (rows.get(k), v) for k, v in want.items() if rows.get(k) != v}
    assert not off, f"和参考实现对不上了（实际, 期望）：{off}"


def test_every_keybind_id_has_both_i18n_strings():
    """表里每个 id 都要有 sc.<id> 和 sc.<id>D 两份（中英各一）。
    现有的死键测试把整个 sc. 前缀当"动态引用即已用"，缺文案它不会红 ——
    缺了就直接把 'sc.switchTheme' 印到页面上。"""
    ids = [r[0] for r in _keymap_rows()]
    assert ids, "KEYMAP 空了，这条测试没东西可查（别让它变成空转）"
    for i in ids:
        for suffix in ('', 'D'):
            k = f"'sc.{i}{suffix}'"
            assert UI_JS.count(k) == 2, f"{k} 应该中英各一份，实际 {UI_JS.count(k)} 份"

def test_the_sidebar_has_one_row_per_entry_point():
    """一个功能只留一个入口。侧栏原来是「顶部两个图标钮 + 一个通栏新建任务」管两件事，
    参考实现把它们收进主导航（DesktopTopOverlay.tsx:211-217 的顺序：开关→导航→新建）。"""
    assert 'id="sbNew"' not in INDEX_HTML, "通栏新建任务按钮还在，和主导航第一行重复"
    assert 'id="sbSearchBtn"' not in INDEX_HTML, "搜索图标钮还在，和主导航第二行重复"
    assert '.sb-new{' not in CSS, ".sb-new 的规则该跟着 DOM 一起删掉"
    assert "getElementById('sbSearchBtn')" not in APP_JS, "浮层定位还指着已删掉的图标钮"
    assert "row:'sbSearchRow'" in APP_JS, "搜索行要有 id，#sbFind 浮层靠它定位"
    for key in ("t('nav.newTask')", "t('sb.search')"):
        assert key in APP_JS.split('function renderNav(')[1].split('\n}\n')[0], \
            f"{key} 得出现在主导航某一行的文案里"
    # 行上的和弦提示从键位表取，不再手抄字面量
    assert "chordOf('newTask')" in APP_JS and "chordOf('search')" in APP_JS


def test_nav_rows_that_are_actions_are_buttons_and_routes_are_links():
    """折叠轨道里点得着不算完，Tab 到不了就是坏的：
    路由行必须是带真 href 的 <a>，动作行必须是 <button>（没 href 的 <a> 拿不到焦点）。"""
    seg = APP_JS.split('const items = [')[1].split('];')[0]
    assert "act:'taskModal'" in seg and "act:'sbSearch'" in seg, "前两行要声明自己是动作"
    assert "'pipelines'" in seg and "'skills'" in seg and "'runs'" in seg, "三条路由还在"
    body = APP_JS.split('function renderNav(')[1].split('\n}\n')[0]
    assert "if(n.act)" in body, "动作行没按 act 分支渲染"
    assert "</button>`" in body and "</a>`" in body, "两种行都得有收尾标签"
    assert 'href="#/${n.id}"' in body, "路由行必须带真 href"
    assert 'aria-label="${esc(n.label)}"' in body, "折叠轨道把 span 藏了，可访问名靠 aria-label"


def test_tooltip_host_honours_the_hidden_attribute():
    """.ff-tip 自己带 position:fixed，[hidden] 的 UA 规则一旦被 display 覆盖就再也藏不掉。"""
    assert 'id="ffTip"' in INDEX_HTML, "提示节点不在了"
    assert ".ff-tip[hidden]{display:none}" in CSS, "缺 .ff-tip[hidden]，收起可能失效"
    assert "data-tip-any" in APP_JS and "tipWants" in APP_JS, "轨道标签靠 tooltip 补回来"


# 展开态也只剩图标的按钮：没有 data-tip-any 就只在折叠时提示，等于平时没说明
TIP_ANY_IDS = ["tbCollapse", "sbActBtn", "sbUpdate", "winMin", "winMax", "winClose"]


def test_icon_only_buttons_tip_in_both_widths():
    for i in TIP_ANY_IDS:
        tag = re.search(r'<[^>]*id="%s"[^>]*>' % i, INDEX_HTML)
        assert tag, f"找不到 #{i}"
        assert "data-tip-any" in tag.group(0), f"#{i} 只有图标，提示却没标 data-tip-any"
    assert 'class="sb-gadd" data-tip-any="1"' in APP_JS, "分组加号同上"
    # 主导航现在是 JS 渲染的，五行（含两条动作行）都得带上轨道提示
    nav = APP_JS.split('function renderNav(')[1].split('\n}\n')[0]
    assert 'const tip = `data-tip-any="1"' in nav, "主导航行的提示没统一带上"


def test_sidebar_stopped_using_native_title():
    """原生 title 和自研提示并存会出现两套样式、两种延迟，侧栏里只留一套。"""
    side = re.search(r'<aside class="sidebar">.*?</aside>', INDEX_HTML, re.S).group(0)
    assert "title=" not in side, f"侧栏里又用了原生 title：{re.findall(r'[\\w]*title=', side)}"


# ---------------- 内联事件处理器 ----------------

HANDLER_ATTR = re.compile(r"\bon[a-zA-Z]+\s*=\s*\\?[\"']([^\"']*)\\?[\"']")
CALL_HEAD = re.compile(r"(?<![.\w$])([A-Za-z_$][\w$]*)\s*[.(]")
# 内联表达式里的关键字，和浏览器塞进作用域的两个宿主名。
# 其余宿主对象（document / window / JSON …）一个都不预先放行：现在没人用，
# 以后谁用谁就地加，条目才不会烂成一串没人信的白名单。
EXPR_WORDS = {"if", "return", "typeof", "catch", "function", "in", "of"}
HOST_GLOBALS = EXPR_WORDS | {"event", "this"}


def _handler_globals():
    """内联 onclick="x()" 里的 x 是浏览器在全局作用域里查的。
    四个脚本各自是 IIFE，没导出到 window 的函数在外面根本不存在 ——
    产出面板那个「刷新」就是这么死的：按钮照画，点一下 ReferenceError，
    而 161 条测试一条都不会红。这里把整条链子焊上。"""
    exported = set()
    for f in JS_FILES:
        exported |= set(re.findall(r"window\.([A-Za-z_$][\w$]*)\s*=",
                                   f.read_text(encoding="utf-8")))
    used = {}
    for f in JS_FILES + [STATIC_DIR / "index.html"]:
        src = f.read_text(encoding="utf-8")
        for m in HANDLER_ATTR.finditer(src):
            # ${...} 在模板串生成时就求过值了，用的是闭包里的局部变量；
            # 处理器真正拿到的是替换后的字面量，不能把它当全局名来查。
            body = re.sub(r"\$\{[^{}]*\}", "", m.group(1))
            for c in CALL_HEAD.finditer(body):
                used.setdefault(c.group(1), set()).add(f.name)
    return exported, used


def test_inline_handlers_only_call_exported_globals():
    exported, used = _handler_globals()
    missing = {k: sorted(v) for k, v in used.items()
               if k not in exported and k not in HOST_GLOBALS}
    assert missing == {}, f"这些内联处理器调的函数没导出到 window：{missing}"


def test_handler_globals_allowlist_is_not_stale():
    """兜底名用上了就是废条目 —— 别让它越积越长，长到没人信。"""
    _, used = _handler_globals()
    stale = {n for n in HOST_GLOBALS if n not in used and n not in EXPR_WORDS}
    assert stale == set(), f"HOST_GLOBALS 里这些名字已经没人用了：{sorted(stale)}"


@pytest.mark.skipif(__import__("shutil").which("node") is None, reason="本机没有 node")
def test_every_static_script_actually_parses():
    """上面那些契约全靠正则扫源码，看不见语法错误。真踩过一次：把 Python 的
    "相邻字符串自动相连"当成 JS 写进字典，设置页整个白屏（t is not a function），
    而几百条测试一条都不红。语法这一关只能交给 JS 引擎自己判。"""
    import subprocess
    for f in JS_FILES:
        r = subprocess.run(["node", "--check", str(f)], capture_output=True, text=True)
        assert r.returncode == 0, f"{f.name} 过不了 node --check：{r.stderr[:400]}"


def test_stats_page_keeps_the_measured_rhythm():
    """这几条是 2026-09-22 对着参考截图逐像素量出来的（图像 px ÷1.5 = CSS px）。
    改回去不会弄坏任何功能，只会悄悄不像 —— 所以只能靠断言钉住。"""
    need = {
        ".st-strip>div{background:var(--bg-panel);padding:11px 10px":
            "顶部条卡上下 11px（整条 72）—— 2026-10-05 随 --fs-stat 从 18 抬到 22 一起改：",
        ".st-strip span{display:block;margin-top:5px;font-size:var(--fs-meta)":
            "数字→标签 5px、标签 12px。数字抬到 22 之后 14px 的标签会把这一格撑成"
            "两行一样重，读数就没有主次了",
        ".hm-grid{display:flex;gap:3px 2px}":
            "横向节距 14 = 12 格 + 2 缝（参考 14.3），52 列才铺得下还留得住两侧内边距",
        ".hm-axis{display:flex;gap:2px;margin-top:15px}":
            "网格→月份轴 15px，且轴的节距必须跟格子一致，否则轴会逐列偏掉",
        ".hm-wrap{overflow-x:auto;padding:0 18px 2px}":
            "网格与卡片标题同一条左线（18px）",
        ".st-stats .st-block{margin-bottom:19px}":
            "统计页卡片之间 19px（别的分区仍走 28px）",
    }
    for frag, why in need.items():
        assert frag in CSS, f"{why}；这条被改动了：{frag}"


def test_durations_are_localised_in_js_not_hardcoded():
    """中文里 "7h 2m" 读不成一句话，参考图写的是 "7 小时 2 分钟"。
    单位取 unit.* 那几个键，别再退回硬编码的英文字母。"""
    body = re.search(r"function fmtDur\(ms\)\{(.*?)\n\}", APP_JS, re.S)
    assert body, "找不到 fmtDur"
    code = body.group(1)
    for k in ("unit.sec", "unit.min", "unit.hour"):
        assert f"t('{k}')" in code, f"fmtDur 的中文分支不再取 {k}"
    assert "'en'" in code, "英文分支（h/m/s）也得留着"


def test_sidebar_archive_view_always_offers_a_way_back():
    """归档视图里最后一条被取消归档后列表就空了 —— 切换钮要是跟着消失，
    人就困在「已归档」这一栏里出不来（只能刷新页面）。"""
    guard = re.search(r"const garch = \((.*?)\) \?", APP_JS, re.S)
    assert guard, "找不到侧栏归档切换钮的渲染条件"
    cond = guard.group(1)
    assert "SB_ARCH" in cond and "arch.length" in cond, f"条件该是「有归档项 或 正在归档视图」：{cond}"
    assert "sb.archivedEmpty" in APP_JS, "归档空态文案没了"


def test_sidebar_row_menu_matches_the_view_it_is_in():
    """项目视图：查看文件 / 新建任务 / 归档；归档视图：查看文件 / 取消归档 / 删除。
    「删除」只在归档视图里露 —— 先归档再删，两步隔开，正在用的流程不会被一键抹掉。"""
    body = re.search(r"window\.sbRowMore = function\(e, name\)\{(.*?)\n\};", APP_JS, re.S)
    assert body, "找不到 sbRowMore"
    code = body.group(1)
    for k in ("sb.viewFiles", "sb.newTaskHere", "sb.archive", "sb.unarchive", "c.delete"):
        assert f"t('{k}')" in code, f"行菜单少了 {k}"
    assert "ffActionMenu" in code, "行菜单没走公共外壳"
    assert "SB_ARCH" in code, "两套菜单被合成一套了"


def test_action_menu_closes_on_escape_before_the_other_popups():
    """.ff-menu 和侧栏搜索、进程浮层共用一条 Esc 处理链。动作菜单压在别人上面，
    必须第一个吃 Esc —— 顺序反了就会一路按下去把底下的弹窗一起带走。"""
    esc = APP_JS[APP_JS.index("if(e.key==='Escape'){"):]
    order = [m.group(1) for m in re.finditer(r"getElementById\('(ffMenu|sbFind|sbPop)'\)", esc)]
    assert order[:1] == ["ffMenu"], f"Esc 先关的不是动作菜单：{order[:3]}"


def test_geometry_never_uses_rem():
    """rem 跟着 html{font-size} 走，而那是「文字大小」设置在改的东西。图标、内边距、
    行高一旦用 rem，选「特大」就等于把整个界面放大 26% —— 这几轮量出来的像素节奏
    （66 的条卡、14 的节距、15 的轴距）只在默认档成立，而且和「界面缩放」职责重叠。
    所以：rem 只准出现在 --fs-* 那八档，几何一律 px。"""
    bad = []
    for ln in CSS.splitlines():
        for m in re.finditer(r"([a-zA-Z-]+|--[a-z0-9-]+)\s*:\s*[^;{}\n]*[0-9.]rem[^;{}\n]*", ln):
            if not m.group(1).startswith("--fs-"):
                bad.append(m.group(0).strip())
    assert not bad, f"这些声明又用回 rem 了（几何必须 px）：{bad[:6]}"
    fs = re.findall(r"--fs-[a-z0-9]+:([0-9.]+rem);", CSS)
    assert len(fs) == 8 and "1rem" in fs, f"字号刻度应当是 8 档全用 rem，实际：{fs}"


def test_archived_flows_stay_visible_in_the_workflows_list():
    """归档只把它们从侧栏那一栏撤走。工作流页要是也跟着藏，人就成了「东西不见了」，
    而且再没有入口把它捞回来 —— 所以行要留着、挂状态牌、⋯ 里给「取消归档」。"""
    ed = (STATIC_DIR / "editor.js").read_text(encoding="utf-8")
    assert "pl-arch-tag" in ed and "t('sb.archived')" in ed, "工作流页不再标已归档"
    assert "plArchive(name, false)" in ed, "工作流页的 ⋯ 少了取消归档"
    assert "plArchive(name, true)" in ed, "工作流页的 ⋯ 少了归档"
    assert ".pl-arch-tag{" in CSS and ".pl-card-row.archived" in CSS, "归档标记没有规则"


def test_menu_labels_that_overrun_get_an_ellipsis_not_a_clip():
    """.ff-mi 是 flex，text-overflow 对裸文本节点（匿名 flex 项）不生效 ——
    长流程名会被硬裁在边框上。标签必须包成 .ff-ml，且 min-width:0 才能收缩。"""
    assert '<span class="ff-ml">${esc(o.label)}</span>' in APP_JS, "菜单标签没包 .ff-ml"
    assert ".ff-mi .ff-ml{min-width:0;overflow:hidden;text-overflow:ellipsis}" in CSS, \
        ".ff-ml 的省略号规则被改动了"


def test_composer_step_strip_follows_the_picked_flow():
    """发送键左边那排步骤必须跟着选中的流程走。它的前身是「含 N 个检查点」那行字 ——
    一开始只按首选项算、之后再也不更新，于是显示成另一条流程的检查点（同一个坑）。
    2026-09-23 用户点名：去掉那行字和「试试这些任务」，检查点信息落到具体某一步上。"""
    sync = re.search(r"function tkSync\(\)\{(.*?)\n\}", APP_JS, re.S)
    assert sync, "找不到 tkSync"
    assert "tkPaintSteps(" in sync.group(1), "换流程时没重画步骤条"
    assert "is-on" in sync.group(1), "发送键的可用态没在这里算，就会永远灰着或永远亮"

    paint = re.search(r"function tkPaintSteps\(flow\)\{(.*?)\n\}", APP_JS, re.S)
    assert paint, "找不到 tkPaintSteps"
    p = paint.group(1)
    assert "find(x=>x.name===flow)" in p, "步骤要从传进来的那条流程取，不能读全局预选值"
    assert "s.checkpoint" in p and "has-cp" in p, "带检查点的那一步没有标记"
    assert "role=\"listitem\"" in p, "一排 chip 没有列表语义，读屏软件只会念成一串字"

    for gone in ("tkMeta", "TK_CPS", "tkHint", "tkSug", "tkPaintSugs", "TK_SUG_KEYS"):
        assert gone not in APP_JS, f"{gone} 还留在 app.js 里"
    assert "tk-hint" not in CSS and "tk-sug" not in CSS, "撤掉的块在 CSS 里还留着规则"


# ==================== 照参考实现（开源的 zai-org/ZCode）对齐的六条 ====================
# 这几处是 2026-09-22 读到 ZCode 真源码之后改的。以前只能对着截图量像素，
# 量不出"分档怎么算、填格往哪个方向、层级谁压谁"这类行为，所以只能靠断言钉住。

def test_heatmap_buckets_are_peak_relative_and_weeks_fill_bottom_up():
    """分位数分档会让每个轻活日都落在 1~2 档，一整年看过去永远满屏有色，
    恰好抹掉"哪天是我最好的一天"这个信号；周/累计档整列铺同一档也会被读成
    "这周每天都这么多"。所以：档位对峰值取比，填格自下而上。"""
    assert "Math.min(4, Math.max(1, Math.ceil(v / mx * 4)))" in APP_JS, "热力图分档不再按峰值等比"
    assert "Math.ceil(cv / mx * 7)" in APP_JS, "周/累计档不再按峰值算填几格"
    assert "i >= 7 - fill" in APP_JS, "填格方向反了（应当自下而上：周日在顶）"
    for gone in ("q(.25)", "q(.5)", "q(.75)"):
        assert gone not in APP_JS, f"分位数分档又回来了：{gone}"


def test_heatmap_ramp_uses_a_fixed_blue_not_the_brand_color():
    """srgb 插值在低百分比上偏灰，四档前密后疏；混 transparent 会让格子随卡片底色变，
    明暗两套下深浅不等价 —— 所以是 oklab 混 --bg-sunken（0 档那格本身）。
    基色必须是 --chart-1：品牌位 --accent 已经交给黑白反转，跟着它整张热力图会
    退成灰度图，四档根本读不出来。参考实现的色阶同样是固定蓝（sky-500/400）。"""
    for pct, n in ((18, 1), (36, 2), (58, 3), (82, 4)):
        frag = f".hm-l{n}{{background:color-mix(in oklab, var(--chart-1) {pct}%, var(--bg-sunken))}}"
        assert frag in CSS, f"色阶第 {n} 档被改动：{frag}"
        back = f".hm-l{n}{{background:color-mix(in oklab, var(--accent)"
        assert back not in CSS, f"色阶第 {n} 档又去跟品牌色了"
    assert "in srgb, var(--accent)" not in CSS, "srgb 混色又回来了"


def test_z_index_goes_through_the_scale_and_orders_menu_on_top():
    """裸数字写 z-index 迟早撞车：以前提示(95)压在菜单(80)上，⋯ 一开，
    上一格留下的提示就糊在菜单第一项上。顺序规定是"正在操作的那层在最上"。
    Voyra v11 把层叠表扩成八档：遮罩 / 进程栏 / 菜单各自独立成档。"""
    assert CSS.count("z-index:") == CSS.count("z-index:var(--z-"), "有 z-index 没走 --z-* 刻度"
    tok = dict(re.findall(r"--z-([a-z]+):([0-9]+);", CSS))
    want = ["sticky", "proc", "composer", "mask", "modal", "toast", "menu", "tip"]
    assert set(tok) == set(want), f"层叠刻度变了：{sorted(tok)}"
    vals = [int(tok[k]) for k in want]
    assert vals == sorted(vals), f"层级顺序不是递增的：{dict(zip(want, vals))}"


def test_row_actions_survive_devices_without_hover():
    """⋯ 和行内按钮原本只认 :hover —— 触屏/平板模式压根没有 hover 这回事，
    等于把动作对这类设备整个藏掉。"""
    assert "@media (hover:none){.sb-more{display:inline-flex}.pl-row-ops{opacity:1}}" in CSS, "没有 hover 的设备上行内动作不可达"


def test_pinyin_initial_table_actually_resolves():
    """搜索键拼的是"原文 + 首字母"，表错了不会报错、只会搜不到 ——
    所以让 JS 引擎真把表跑一遍，而不是断言那串字符还在。"""
    import subprocess
    js = ("const s=require('fs').readFileSync(process.argv[1],'utf8');"
          "const g=s.match(/const PY_GROUPS = \"([^\"]+)\";/)[1];"
          "const m={};g.split('|').forEach(x=>{const i=x.indexOf(':');"
          "for(const c of x.slice(i+1)) m[c]=x.slice(0,i).toLowerCase();});"
          "const w=JSON.parse(process.argv[2]);"
          "console.log(JSON.stringify(w.map(x=>[...x].map(c=>m[c]||'?').join(''))));")
    words = ["模型", "外观", "语言", "主题", "统计", "设置", "运行", "引擎", "密钥", "归档", "工作流"]
    want = ["mx", "wg", "yy", "zt", "tj", "sz", "yx", "yq", "my", "gd", "gzl"]
    r = subprocess.run(["node", "-e", js, str(STATIC_DIR / "app.js"), json.dumps(words)],
                       capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, r.stderr[:400]
    assert json.loads(r.stdout) == want, r.stdout[:200]
    # 无 .st-row 的卡靠这份元素清单取标题文案；统计页的卡标题是 .st-pttl，
    # 漏了它这六张卡就对搜索完全隐形（"mxy" 搜不到「模型用量」）。
    frag = "querySelectorAll('.st-label,.hm-title,.spv-title,.st-pttl,.st-t,.st-d')"
    assert frag in APP_JS, f"搜索兜底的标题清单变了：{frag}"


def test_chart_palette_has_six_slots_and_merges_only_past_six():
    """六条模型以内全画 —— 第 7 档没颜色了，但"六条 + 其他"那种只剩一个
    "其他"的图例更难看。合并的触发条件是超过六条，切成 5 具名 + 其他。"""
    assert "const CHART_N = 6;" in APP_JS, "分类色档数变了，--chart-* 得同步"
    assert CSS.count("--chart-6:") == 2, "--chart-6 必须明暗各一份"
    assert ".st-c6{background:var(--chart-6)}" in CSS and ".st-s6{stroke:var(--chart-6)}" in CSS
    assert "rows.length > CHART_N ? CHART_N - 1 : rows.length" in APP_JS, "合并规则不再是「超过六条才并」"


def test_no_window_handler_without_a_caller():
    """内联 onclick 只能调挂到 window 上的名字，所以那批函数必须导出；但反方向没人管 ——
    「把弹层改成首页」时 ✕ 按钮没了，tkHideSugs 就成了没人调的孤儿，几百条测试一条不红。
    引用数按整个 static/ 加 index.html 算，ffSelect 那种传函数名字符串的也算调用方。"""
    src = {f.name: f.read_text(encoding="utf-8") for f in JS_FILES}
    hay = "\n".join(src.values()) + INDEX_HTML
    dead = []
    for fname, body in src.items():
        for m in re.finditer(r"window\.([A-Za-z_$][\w$]*)\s*=\s*(?:async\s+)?function", body):
            if len(re.findall(r"\b" + re.escape(m.group(1)) + r"\b", hay)) <= 1:
                dead.append(f"{fname}:{m.group(1)}")
    assert not dead, f"这些导出的处理函数没有任何调用方：{dead}"


# ---------------- 圆角跟嵌套层数走（参考实现 DESIGN.md:285-341） ----------------

LADDER = ["--r-1", "--r-2", "--r-3", "--r-4", "--r-5"]
# 相对层级是参考实现写进文档的规则；绝对像素这份克隆里读不到（Tailwind 预设没被
# sparse-checkout 出来），只有一处旁证 DESIGN.md:179 的 16px 壳 / 12px 面板。
# 所以这里锁"四档递减 + 顶层 16px"，不假装量到了 sm/md/lg 的原值。
LADDER_PX = ["4px", "6px", "8px", "12px", "16px"]

# 类名 -> 它「应该」用的那一档。父壳和壳内控件成对写，改了一头另一头不许偷偷漂。
NESTED_RADIUS = {
    # 2026-09-24 按参考图像素：输入台壳的圆角量到 12（内缩在 12 CSS 归零），
    # 也就是刻度表里「第一个圆角容器 = rounded-xl」那一档。文档给主输入壳留的
    # 2xl 许可，它自己发出来的版本并没有用 —— 以像素为准，不再走 --r-5。
    ".tk-card": "--r-4",
    # .tk-input 故意不在表里：卡片是唯一的表面，textarea 不自己画盒子/圆角
    # （实测参考图 body 是一整片 #2B2B2B，没有内凹框）。见 test_composer_is_one_surface。
    ".cp-send": "--r-3",          # 图标按钮要方正，不能是正圆
    ".composer-inner": "--r-4",   # 运行台底部那个和首页那张是同一个壳
    ".modal-box": "--r-5",        # 对话框壳 = 2xl，且不计入内容层级
    ".up-card": "--r-5",          # 更新浮层同样是对话框壳
    ".card": "--r-4",             # 第一层圆角容器 = xl
    ".sc-card": "--r-4",
    ".st-panel": "--r-4",
    ".sb-pop": "--r-3",           # 浮层菜单壳 = lg，不是容器 xl
    ".ff-menu": "--r-3",
    ".ff-tip": "--r-3",           # 提示也是浮层，跟菜单壳同档
    ".sb-fi": "--r-2",            # 菜单项 = md
    ".ff-mi": "--r-2",
}


def _radius_of(sel):
    """取某个选择器**作为整条规则主语**时的圆角档位。
    只认顶格/跟在 } 或逗号之后的那种：`.tk-bar .cp-send{margin-left:auto}` 是布局微调，
    不是圆角来源，早先按"类名出现即可"匹配会被它抢走。
    取**最后**一条顶格声明：同一选择器写两遍时赢的是后一条，读第一条等于给
    不起作用的那份把脉（.tk-card 曾经前一份写 --r-4、后一份写 --r-5，
    两张表各对一个，于是两边都"通过"）。"""
    hits = re.findall(r"(?:^|[},])\s*" + re.escape(sel) + r"\s*\{([^}]*)\}", CSS, re.M)
    assert hits, f"找不到 {sel} 的规则，NESTED_RADIUS 表该更新了"
    body = hits[-1]
    v = re.search(r"border-radius:\s*([^;}]+)", body)
    assert v, f"{sel} 没有 border-radius，表里却写着它"
    got = v.group(1).strip()
    return (re.match(r"var\((--[\w-]+)\)", got) or [None, got])[1]


def test_radius_ladder_is_a_four_step_nesting_ladder():
    # Voyra v11 令牌块在每档后带注释，故不再要求五档挤在同一行。
    got = dict(re.findall(r"--r-([1-5]):\s*([\d.]+px)", CSS))
    assert got, "圆角梯子不再是五个命名档，请连同本测试一起想清楚"
    assert [got.get(str(i)) for i in range(1, 6)] == LADDER_PX, f"梯子漂了：{got}"


def test_radius_follows_the_container_nesting():
    got = {s: _radius_of(s) for s in NESTED_RADIUS}
    bad = {k: (v, NESTED_RADIUS[k]) for k, v in got.items() if v != NESTED_RADIUS[k]}
    assert not bad, f"圆角档位不对（实际, 期望）：{bad}"


# 正圆只准留给"真的是个圆"的东西：状态点、滑块圆头。参考实现同一条
# （DESIGN.md:338 rounded-full 只给故意的胶囊或正圆）。双向锁：新添正圆要过评审。
CIRCLE_50 = {".sb-pdot", ".adv-dot", ".ws-live i", ".st-state i",
             ".slider::before", ".st-range::-webkit-slider-thumb",
             ".st-range::-moz-range-thumb"}


def test_pill_is_reserved_for_deliberate_pills():
    """"按钮、标签、计数器不因类型而获得 rounded-full"（DESIGN.md:336-341）。
    toast 属于 2xl 例外之一，不是胶囊；发送键是图标按钮，不是正圆。"""
    round_sels = set()
    for m in re.finditer(r"([^{}]+)\{([^{}]*)\}", CSS):
        if re.search(r"border-radius:\s*[^;}]*50%", m.group(2)):
            round_sels.add(re.sub(r"\s+", " ", re.sub(r"/\*.*?\*/", "", m.group(1))).strip())
    assert round_sels == CIRCLE_50, (
        f"多出的正圆：{sorted(round_sels - CIRCLE_50)}；消失的正圆：{sorted(CIRCLE_50 - round_sels)}")
    assert _radius_of(".toast") == "--r-5", "toast 属于 2xl 例外，不是胶囊"
    assert _radius_of(".cp-send") != "--r-pill", "发送键是图标按钮，不是胶囊"


# ---------------- 输入台质感（照实测参考图分层） ----------------

def _rule(sel):
    m = re.search(r"(?:^|[},])\s*" + re.escape(sel) + r"\s*\{([^}]*)\}", CSS, re.M)
    assert m, f"找不到 {sel} 的规则"
    return m.group(1)


def _winning_rule(sel):
    """取真正生效的那一条：顶格声明里的**最后**一条。
    CSS.split(sel)[1] 取的是第一条，而 v11 追加段的设计就是"同选择器写在后面、
    按次序自然覆盖"（本文件 1500 行那段开头就是这么写的）—— 于是几十条断言
    一直在给已经不起作用的那份把脉。1.2.9 的"测试全绿、界面走另一套"就是这么
    上线的。断言要跟着会赢的那条读。
    外壳那批（.sidebar / .tlb-* / .sb-* / .titlebar / .topbar）已经在 2026-10-05
    合并成一份了，由 test_no_shell_selector_is_declared_twice 单独守；
    其余组件仍允许两段并存，但本函数保证读到的是生效的那段。"""
    hits = re.findall(r"(?m)^" + re.escape(sel) + r"\s*\{([^}]*)\}", CSS)
    assert hits, f"找不到顶格的 {sel} 规则"
    return hits[-1]


def test_composer_is_one_surface_with_a_darker_strip():
    """实测参考图：卡片 body 一整片 #2B2B2B，顶部「选流程」那条是更暗的 #222222，
    中间一条 #4b4b4b 分隔线；textarea 自己不画盒子。
    差别全在"谁画表面" —— 卡片画，控件不画。"""
    card = _rule(".tk-card")
    assert "background:var(--bg-composer)" in card, \
        "卡片表面要用 composer 那一档（暗色 #2B2B2B）；挂 --bg-panel 会整体暗一档"
    assert "border:1px solid var(--line)" in card, "常态边框走 --line 这一档"
    # 2026-10-05 反过来钉：聚焦**不许**改描边。
    # 这一条以前断言的是 border-color 抬到 --line-strong（当时的实测 #4b4b4b），
    # 用户这次点名"选中对话框不要旁边变成高亮"，量的就是它 —— 整张输入台外面
    # 亮起一圈比正文还亮的边。焦点反馈改由阴影承担（卡片被端起来），边框一动不动。
    focus = _winning_rule(".tk-card:focus-within")
    assert "border-color" not in focus, \
        f"输入台聚焦又在提描边了（用户点名不要的那圈高亮）：{focus}"
    assert "box-shadow" in focus, "聚焦总得有个反馈：撤了描边就要抬阴影"
    for blk in re.findall(r"(?m)^\.tk-card:focus-within\s*\{([^}]*)\}", CSS):
        assert "border-color" not in blk, "还有另一条 .tk-card:focus-within 在提描边"
    top = _rule(".tk-top")
    assert "background:var(--bg-strip)" in top, "顶部条带要有自己的底色，不然三段只是靠线分"
    assert "border-bottom:1px solid var(--line-strong)" in top, "条带下的分隔线同边框一档"
    inp = _rule(".tk-input")
    for bad in ("background:var(", "border:1px", "border-radius:"):
        assert bad not in inp, f"textarea 又自己画表面了：{bad}"


def test_bg_strip_is_darker_in_both_themes():
    """Voyra v11 起条带底改走 --bg-sunken 这一层（v10 的 --bg-strip 保留为别名
    指向它）。两套主题都必须声明，否则条带会掉成透明。

    2026-10-05 改判据：以前钉的是"写成 rgba("，那是 v11 顺手的取值而不是意图。
    真正要守的两件事是 —— ① 声明了、不透明（热力图 0 档格子拿它当 color-mix 的
    基色，混进透明底会让格子跟着卡片底色漂，四档深浅就读不出来了）；
    ② 亮色下它确实比表面暗。暗色那档反过来（比卡片亮），因为参考图里
    卡内格子 #2E332E 就是压在 #1F2120 卡片上的一个更亮的档。"""
    blocks = CSS.split("html[data-theme=\"dark\"]")
    assert len(blocks) == 2, "找不到暗色那段，这条测试的切法要跟着改"
    hexes = {}
    for name, blk in (("light", blocks[0]), ("dark", blocks[1])):
        m = re.search(r"--bg-sunken:\s*(#[0-9A-Fa-f]{6})", blk)
        assert m, f"{name} 主题的 --bg-sunken 没声明成实心 6 位十六进制（不能是透明/半透明）"
        hexes[name] = m.group(1)
        assert re.search(r"--bg-strip:\s*var\(--bg-sunken\)", blocks[0]), \
            "--bg-strip 应作为 --bg-sunken 的别名保留，别让旧规则失效"
    surf = {}
    for name, blk in (("light", blocks[0]), ("dark", blocks[1])):
        surf[name] = re.search(r"--bg-surface:\s*(#[0-9A-Fa-f]{6})", blk).group(1)
    assert _l_star(hexes["light"]) < _l_star(surf["light"]), \
        f"亮色条带 {_l_star(hexes['light']):.1f} 不比表面 {_l_star(surf['light']):.1f} 暗"
    assert _l_star(hexes["dark"]) > _l_star(surf["dark"]), \
        f"暗色卡内格子要比卡片亮（参考图 #2E332E 压在 #1F2120 上）"


def test_send_button_is_muted_until_there_is_a_brief():
    """空说明时发送键是灰的（实测 #959595 压在 #2B2B2B 上），有字才亮成品牌色。
    这是状态，不是装饰：JS 里没有对应的 toggle，按钮就会永远灰着骗人。"""
    bar = _rule(".tk-bar .cp-send")
    assert "color-mix(in oklab, var(--btn-ink) 52%, var(--bg-composer))" in bar, \
        "空态灰要用品牌色压表面混出来，写死 #959595 会在亮色主题下破"
    assert "is-on" in CSS and ".tk-bar .cp-send.is-on" in CSS, "缺亮起来的那一态"
    assert "send.classList.toggle('is-on'" in APP_JS, "JS 没接 is-on：按钮会永远灰着"


# ---------------- 权限模式 chip ----------------

def test_composer_mode_chip_offers_exactly_the_shipped_modes():
    """chip 的档位必须和后端 agents.PERM_MODES 一一对上。
    manual（变更前确认）没实现回调工具之前不许出现在这里 —— 出现了就是假控件。"""
    seg = APP_JS.split("function tkStageHtml(")[1].split("\n}\n")[0]
    assert "id:'tkPerm'" in seg, "输入台没有权限模式 chip"
    lst = re.search(r"const PERM_MODES = \[([^\]]*)\]", APP_JS)
    assert lst, "前端没有那份模式清单"
    assert lst.group(1).replace("'", "").replace(" ", "") == \
        "plan,acceptEdits,bypassPermissions", "前端模式和后端不同源"
    assert "permission_mode:" in APP_JS, "chip 选了没发出去 = 装饰"
    # chip 在工具条里必须只写名字（short），且放在顶部条带 ——
    # 实测：带上 note 的收起态会变成一整句话，把步骤条从 504px 挤到只剩 320px。
    top = seg.split('class="tk-field"')[0]
    assert "id:'tkPerm'" in top, "模式 chip 挤在底部工具条里，步骤条放不下 7 步"
    assert "short:true" in seg, "模式 chip 没开 short，收起态会把说明文字一起吃进去"


def test_composer_model_chip_lists_only_real_presets():
    """运行级模型覆盖的候选只能来自 /api/providers 里真存在的预设名。
    一个预设都没有时整枚 chip 必须消失 —— 一枚点开只有「跟随步骤」的选择器是假控件。"""
    seg = APP_JS.split("function tkStageHtml(")[1].split("\n}\n")[0]
    assert "ST.presets" in seg, "模型 chip 的候选没从预设清单来"
    assert "PSET.length ?" in seg, "没预设时这枚 chip 该整枚消失"
    assert "TK_MODEL = ''" in seg, "预设被删后 chip 显示「跟随步骤」、发出去却还是那个死名字"
    assert "id:'tkModel'" in seg, "输入台没有模型 chip"
    # 选项带 note 的 chip 必须开 short：实测不开的时候收起态直接写成
    # 「跟随步骤 · 不覆盖，每一步沿用它自己挑的端点」一整句，把步骤条挤没了。
    after = seg[seg.index("id:'tkModel'"):][:160]
    assert "short:true" in after, "模型 chip 没开 short，收起态会连说明一起吃进标签"
    assert "model: TK_MODEL" in APP_JS, "选了模型没发出去 = 装饰"
    rh = APP_JS.split("window.renderHome = async function")[1].split("\n};")[0]
    assert "api('/api/providers')" in rh, "首页没拉预设清单"
    assert "ST.presets === null" in rh, "空数组会被当成没拉过，每次回首页都多打一次请求"


def test_settings_page_no_longer_offers_a_second_sandbox_control():
    """模式接管了 codex 沙箱，设置里那行必须一起消失 ——
    一个入口改沙箱、另一个入口改模式（它也会改沙箱），两边会互相打脸。"""
    assert "saveSandbox" not in APP_JS, "设置里还留着沙箱保存函数"
    assert "rt.sandbox" not in APP_JS, "设置里那行沙箱选择器还在"
    assert "'rt.sandbox'" not in UI_JS, "沙箱那行的文案成了没人用的死键"
    # 后端仍然报告 codex_sandbox 现值（那是状态，不是控件），但不再列可选项
    assert "sandbox_options" not in APP_JS, "前端还在读沙箱候选清单"


# ---------------- 评审后补的三条：chip 不能骗人 ----------------

def test_mode_chip_is_synced_from_the_boot_fetch():
    """输入台在启动那一刻就渲染，而 permission_mode 以前只有进过设置页才读 ——
    于是服务端是 plan、chip 显示「默认」，一个权限控件显示着假状态。"""
    la = APP_JS.split('async function loadAgents()')[1].split('\n}\n')[0]
    assert "ST.permMode = r.permission_mode" in la, "开机那次 /api/agents 没读回权限模式"
    assert "permMode:''" in APP_JS.replace("permMode: ''", "permMode:''"), \
        "ST 里要有 permMode 的初值，chip 才不会读到 undefined"


def test_mode_chip_reverts_both_label_and_value_when_the_post_fails():
    """ffOpen 在调 onChange 之前就把隐藏 input 和按钮文字写好了；
    api() 对 4xx 也返回解析后的 JSON（{detail:...} 是真值），
    所以"没抛异常"不等于"存下了" —— 不显式退回，chip 会显示一个服务端没接受的模式。"""
    fn = APP_JS.split('window.tkPermSet = async function(v)')[1].split('\n};')[0]
    assert "r.detail" in fn, "没检查 detail，400 会被当成成功"
    assert "ffSetValue('tkPerm'" in fn, "只退 ST 不退 chip：按钮上还写着那个没生效的模式"
    assert "postAgents(" not in fn, "postAgents 成功后固定弹「已保存」，会把说清作用域的那句顶掉"


def test_sidebar_project_row_highlights_itself():
    """cur 取的是 hash 的第 3 段（`#/pipeline-edit/foo` → 'foo'），
    以前拿 'pipeline-edit/foo' 去比，永远不相等 —— 项目行从来不亮。"""
    seg = APP_JS.split('async function renderSidebarLists(')[1].split('\n}\n')[0]
    assert "p.name===cur" in seg, "项目行的选中态又拿带前缀的路径去比了"
    assert "'pipeline-edit/'+p.name)===cur" not in seg, "残留旧的比较式"


# ---------------- 记忆编辑器（能力分区里的唯一写入入口） ----------------

def test_only_memory_gets_an_edit_affordance_and_not_when_truncated():
    """技能 / 命令 / 子智能体那几类是 CLI 自己的格式，改坏了只有官方入口能救；
    记忆是用户自己写的 markdown，才给编辑。截断过的正文一份都不完整，
    存回去等于把尾巴抹掉 —— 所以两个条件都得成立才出按钮。"""
    seg = APP_JS.split("window.capsView = async function")[1].split("\n};")[0]
    assert "key === 'memory'" in seg, "编辑入口给到了不该给类目"
    assert "!d.truncated" in seg, "截断过的文件也允许编辑，保存会把丢掉的部分抹掉"
    assert "capsEditMem()" in seg, "预览弹窗里没有进编辑的入口"


def test_memory_save_sends_engine_and_content_only():
    """写入面越大越危险：前端只报"改哪家 CLI 的哪段正文"，路径由 cli_inventory
    从它自己那份清单里算。这样这个接口物理上写不到清单之外的文件。"""
    seg = APP_JS.split("window.capsSaveMem = async function")[1].split("\n};")[0]
    assert "engine: CAPS_VIEW.eng" in seg and "content: ta.value" in seg
    assert "path" not in seg, "前端还在往写入请求里塞路径"
    assert "ST.caps = " in seg, "存完不重算盘点，行上的字节数还是旧的"


def test_memory_editor_closes_on_a_window_function_not_a_module_let():
    """内联 oninput 走的是全局作用域，IIFE 里的 let 它看不见 ——
    写 oninput="CAPS_VIEW.dirty=true" 会直接 ReferenceError，标记脏这件事静默失效。"""
    body = APP_JS.split("window.capsEditMem = function()")[1].split("\n};")[0]
    assert "oninput=" in body, "正文改了却不记脏，关掉就白改"
    assert "CAPS_VIEW." not in body.split("oninput=")[1].split(">")[0], \
        "内联事件里直接引用了 IIFE 内的 let"
    assert "window.capsDirty" in APP_JS, "没有那个桥接函数"


def test_composer_workdir_field_is_only_a_path_the_server_judges():
    """选文件夹=只换智能体的 cwd。前端不许自己判合法性（绝对/存在/是不是目录，
    还有"codex 不接受"那条），服务端 check_workdir 是唯一裁判 —— 两边各判一套，
    迟早出现"界面能填、起跑才报错"。"""
    seg = _composer()
    assert 'id="tkDir"' in seg, "输入台没有工作文件夹这一格"
    assert "task.dirPh" in seg and "task.dirTip" in seg, "占位和悬停说明得说清留空是什么"
    body = APP_JS.split("window.taskStart = async function()")[1].split("\n};")[0]
    assert "workdir: dir" in body, "填了却没发出去 = 装饰"
    assert "TK_DIR = dir" in body, "重渲染要能把这格带回原值，不然填一半换流程就丢"


# ---------------- 2026-09-24 按参考图像素重定的那一层 ----------------

def test_type_scale_is_anchored_to_the_measured_sizes():
    """八档字号不是自己排的：14px 根（参考实现的 --ui-font-size 默认值），
    前五档对齐它的加减刻度 10/12/13/14/16/18，最大那档 27 是量首页大标题量出来的。
    漂一档就等于全站字号又回到"看着小一号"。"""
    m = re.search(r"html\{font-size:calc\((\d+)px \* var\(--text-scale\)\)", CSS)
    assert m, "html 的 font-size 不再是 calc(<n>px * var(--text-scale))"
    root = int(m.group(1))
    assert root == 14, f"根字号 {root}px，参考实现是 14px"
    want = {"--fs-micro": 11, "--fs-meta": 12, "--fs-sub": 13, "--fs-body": 14,
            "--fs-lead": 16, "--fs-stat": 22, "--fs-h2": 20, "--fs-h1": 27}
    # micro 10→11、stat 18→22 是 2026-10-05 改的，两处都有理由：
    # micro 是十阶段芯片 / 计数徽标 / Ctrl N 那几处唯一的字号，10px 的中文读不动；
    # stat 那条刻度的注释自己写着"统计条那排数字字高 ≈20px"，而 18px 字号只给得出
    # 13px 字高 —— 一直在报一个界面上不存在的读数。中间五档是被量出来的，不动。
    for key, px in want.items():
        v = re.search(re.escape(key) + r":([\d.]+)rem", CSS)
        assert v, f"{key} 从刻度里消失了"
        got = round(float(v.group(1)) * root)
        assert got == px, f"{key} 现在是 {got}px，量到的应该是 {px}px"
    j = re.search(r"const ROOT_PX = (\d+(?:\.\d+)?);", APP_JS)
    assert int(float(j.group(1))) == root, "滑块换算基准和 CSS 根字号脱钩了：读数会报一个不存在的字号"


def test_the_two_columns_are_split_by_color_and_not_by_a_line():
    """分栏的第一判据是色差，那条 1px 边只是缝的收口。
    2026-10-05 逐像素重量参考图：侧栏 #242624 / 画布 #191B1A，中间确实有一个
    单像素的 #373C37，卡片顶边也是同一个值 —— 所以"两栏之间没有任何线"那句
    旧注释是错的（它来自另一张图），而 v11 加右边框反而是照图的。两边都记下来，
    下次别再靠注释猜。
    参考图自己那对只差 ΔL* 5.4，因为它有线兜底；本项目要求 ≥6.0，
    这样即便哪天线没了，分栏也还在。"""
    dark = CSS.split('html[data-theme="dark"]')[1].split("}")[0]
    shell = re.search(r"--bg-shell:(#[0-9A-Fa-f]{6})", dark).group(1).upper()
    page = re.search(r"--bg-page:(#[0-9A-Fa-f]{6})", dark).group(1).upper()
    assert (shell, page) == ("#2A2A2A", "#1A1A1A"), \
        f"暗色两栏是 #2A2A2A / #1A1A1A，现在是 {shell} / {page}"
    d = abs(_l_star(shell) - _l_star(page))
    assert d >= 6.0, f"暗色两栏 ΔL* 只有 {d:.1f}，撑不起没有彩底的分栏"
    for name, hx in (("侧栏", shell), ("画布", page)):
        r, g, b = (int(hx[i:i + 2], 16) for i in (1, 3, 5))
        assert max(r, g, b) - min(r, g, b) <= 2, \
            f"{name} {hx} 又带回色相了（R{r}/G{g}/B{b}），中性面偏色会把金色一起染脏"
    sb = _winning_rule(".sidebar")
    assert "border-right:1px solid var(--line)" in sb, \
        "侧栏要有那条 1px 缝，且吃 --line（半透明压在两层底上会差出 5 个亮度）"
    assert "--line-soft" not in sb, "缝用最淡那档 = 看不见，等于没画"
    tb = _winning_rule(".topbar")
    assert "border-bottom" not in tb, "页头有下边线 = 右侧被切成两块"
    assert "background" not in tb, "页头铺自己的底 = 它成了独立的一条带子"


def _l_star(hx: str) -> float:
    """CIE L*。用它而不是"看起来差很多"：亮色那对十六进制数只差 8，肉眼分不出分栏。"""
    c = [int(hx[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    f = lambda v: v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = [f(v) for v in c]
    y = 0.2126 * r + 0.7152 * g + 0.0722 * b
    return 116 * y ** (1 / 3) - 16 if y > 0.008856 else 903.3 * y


def test_the_light_columns_are_split_by_the_same_margin_of_difference():
    """亮色下侧栏与页面必须看得出分栏，判据和暗色那条一样是 CIE ΔL* ≥ 6.0。
    历史上这里吃过两次亏：v11 方案给的 #ECEEF2 只到 3.2（看不出分栏），
    上一轮按 §0.9.3 上调成 slate-200 #DDE3EC 够到 7.2 但带蓝 —— 压在金色强调上
    会把中性档一起染脏。现在取 #E4E4E4（ΔL* 6.8），留在中性灰家族里。"""
    light = CSS.split(":root{")[1].split('html[data-theme="dark"]')[0]
    shell = re.search(r"--bg-shell:(#[0-9A-Fa-f]{6})", light).group(1)
    page = re.search(r"--bg-page:(#[0-9A-Fa-f]{6})", light).group(1)
    assert (shell, page) == ("#E4E4E4", "#F7F7F7"), \
        f"亮色两栏是 #E4E4E4 / #F7F7F7，现在是 {shell} / {page}"
    d = abs(_l_star(shell) - _l_star(page))
    assert d >= 6.0, f"亮色两栏 ΔL* 只有 {d:.1f}，看不出分栏"
    sb = _winning_rule(".sidebar")
    assert "border-right:1px solid var(--line)" in sb, "亮色下那条缝同档同色"


def test_the_two_palette_layers_agree():
    """style.css 的语义令牌和 voyra-foundation.css 的 --vr-* 必须逐值相等。

    这条是补 1.2.9 那次事故的洞：static/voyra-ui.css 里曾挂着一整块 :root 覆盖，
    把 style.css 的 --bg-*/--ink*/--line* 重新映射到 --vr-*。style.css 写冷 slate、
    覆盖层写橄榄，而本文件只读 style.css —— 于是"全绿上线"了一套界面上根本不
    存在的调色板，还顺手把上一轮实测过的侧栏亮度、行距、分栏线一起盖掉。
    覆盖层已经删了；这条断言保证它回来时不会又一次静默生效。"""
    found = (STATIC_DIR / "voyra-foundation.css").read_text(encoding="utf-8")
    ui = (STATIC_DIR / "voyra-ui.css").read_text(encoding="utf-8")
    # 覆盖层不许复活：voyra-ui.css 里再出现给 --bg-*/--ink*/--line* 赋值的 :root 块，
    # 就是那次事故的形状。
    for head in re.finditer(r":root[^{]*\{([^}]*)\}", ui):
        body = head.group(1)
        bad = [t for t in ("--bg-", "--ink", "--line") if re.search(re.escape(t) + r"[\w-]*\s*:", body)]
        assert not bad, f"voyra-ui.css 里又出现了给 {bad} 赋值的 :root 覆盖块（影子调色板）"
    pairs = [("--bg-page", "--vr-canvas"), ("--bg-surface", "--vr-surface"),
             ("--bg-shell", "--vr-surface-soft"), ("--bg-hover", "--vr-surface-hover"),
             ("--bg-active", "--vr-surface-active"), ("--bg-raised", "--vr-surface-raised"),
              ("--ink", "--vr-ink"), ("--ink-2", "--vr-body"),
             ("--ink-3", "--vr-muted"), ("--ink-4", "--vr-faint"),
             ("--line", "--vr-line"), ("--line-strong", "--vr-line-strong"),
             ("--brand", "--vr-brand"), ("--brand-soft", "--vr-brand-soft")]
    blocks = CSS.split('html[data-theme="dark"]')
    assert len(blocks) == 2
    for name, blk in (("亮色", blocks[0]), ("暗色", blocks[1])):
        vr = re.search(r":root\[data-theme=\"dark\"\].*?\{(.*?)\}", found, re.S) \
            if name == "暗色" else re.search(r"^:root \{(.*?)\}", found, re.S | re.M)
        assert vr, f"voyra-foundation.css 里找不到 {name} 那块"
        vrs = dict(re.findall(r"(--[\w-]+):\s*(#[0-9a-fA-F]{6})", vr.group(1)))
        mine = dict(re.findall(r"(--[\w-]+):\s*(#[0-9A-Fa-f]{6})", blk))
        for a, b in pairs:
            assert a in mine, f"{name} 的 style.css 缺 {a}"
            assert b in vrs, f"{name} 的 voyra-foundation.css 缺 {b}"
            assert mine[a].upper() == vrs[b].upper(), \
                f"{name} 下 {a}={mine[a]} 与 {b}={vrs[b]} 不相等了 —— 两层又开始各写一套"


def test_selection_states_are_neutral_not_brand():
    """选中态和悬停态必须是中性档，而且两档要分得开。
    用户点名的"选中对话框不要旁边变成高亮"：以前 --bg-active 吃的是
    --vr-brand-soft（暗色 #373021，R-B=+22 的一块米黄），划到哪个项目哪一行就
    糊出一块暖色板；而 .sb-item 的 hover 和 active 又指同一个令牌，鼠标划过
    哪行哪行就冒充"当前所在"。"""
    blocks = CSS.split('html[data-theme="dark"]')
    for name, blk in (("亮色", blocks[0]), ("暗色", blocks[1])):
        for tok in ("--bg-active", "--bg-hover"):
            hx = re.search(re.escape(tok) + r":(#[0-9A-Fa-f]{6})", blk).group(1)
            r, g, b = (int(hx[i:i + 2], 16) for i in (1, 3, 5))
            assert max(r, g, b) - min(r, g, b) <= 2, \
                f"{name} {tok}={hx} 带彩，选中行会糊成一块有色板"
        act = re.search(r"--bg-active:(#[0-9A-Fa-f]{6})", blk).group(1)
        hov = re.search(r"--bg-hover:(#[0-9A-Fa-f]{6})", blk).group(1)
        assert _l_star(act) != _l_star(hov), \
            f"{name} hover 与 active 同亮度（{hov}/{act}），划过的行会冒充选中的那行"
    hover = re.search(r"\.sb-item:hover\{([^}]*)\}", CSS).group(1)
    active = re.search(r"\.sb-item\.active\{([^}]*)\}", CSS).group(1)
    assert "var(--bg-hover)" in hover, "hover 还在吃 --bg-active"
    assert "var(--bg-active)" in active, "active 该吃 --bg-active"
    assert "font-weight:600" in active, "选中行要靠字重站住，不只靠底色"
    ic = re.search(r"\.sb-item\.active \.ic\{([^}]*)\}", CSS).group(1)
    assert "var(--brand)" in ic, f"选中行的图标没上色（{ic}）—— 底色压平之后它得负责指认"


def test_no_shell_selector_is_declared_twice():
    """外壳那批选择器整份文件里只许出现一次。
    1.2.9 的 v11 追加段用同样的选择器把 470-640 那段旧壳样式重新声明了一遍
    （分栏线、行高 34px、字号 --fs-sub、静止色 --ink-2、hover 与 active 同色），
    按 CSS 次序自然盖掉了旧段 —— 而本文件里几十条断言用 CSS.split(sel)[1]
    取的是第一条命中。于是测试给不起作用的那份把脉，真实界面走另一份。
    这条把"两份真相"本身钉死，下次再追加一段就先撞上它。"""
    shell_sels = (".titlebar", ".tlb-left", ".tlb-right", ".tlb-brand", ".tlb-drag",
                  ".tlb-acts", ".tlb-win", ".tlb-wb", ".sidebar", ".sb-scroll", ".sb-nav",
                  ".sb-item", ".sb-kbd", ".sb-group", ".sb-runlist", ".sb-run", ".sb-sub",
                  ".sb-foot", ".sb-me", ".sb-me-av", ".sb-me-name", ".topbar", ".main")
    # 只看顶格的选择器（缩进的那些在 @media 里，那是有意的响应式覆写）
    dupes = {}
    for sel in shell_sels:
        n = len(re.findall(r"(?m)^" + re.escape(sel) + r"\{", CSS))
        if n > 1:
            dupes[sel] = n
    assert not dupes, f"这些外壳选择器被声明了不止一次，后一份会静默盖掉前一份：{dupes}"


def test_no_input_paints_an_accent_halo_on_focus():
    """用户点名"点输入框时外面不要那种白色光晕"。暗色 --accent 就是 #FFFFFF，
    所以 `box-shadow:0 0 0 3px color-mix(... var(--accent) ...)` 画出来的正是它。
    输入台先改成了"只提边框亮度到 --line-strong"，这条把同一办法推广到设置页，
    并防止下一个输入框又顺手抄那圈环。"""
    assert "box-shadow:0 0 0 3px color-mix(in oklab, var(--accent)" not in CSS, \
        "又有人用 --accent 画外环：暗色下那就是一圈白晕"
    for cls in (".tk-card", ".pv-input", ".st-input"):
        rule = CSS.split(cls)[1].split("}")[0]
        assert "box-shadow:0 0 0" not in rule.split("{")[1], f"{cls} 带了外扩光环"
    for cls in (".pv-input:focus", ".st-input:focus"):
        rule = CSS.split(cls)[1].split("}")[0]
        assert "border-color:var(--line-strong)" in rule, f"{cls} 没有可看的焦点反馈"
        assert "outline:none" in rule, (
            f"{cls} 必须无条件撤 outline —— 实测文本框连鼠标点进去都算 :focus-visible，"
            "写成 :not(:focus-visible) 等于没撤")


def test_workspace_markdown_headings_are_graded_by_weight_not_only_size():
    """参考实现 DESIGN.md:229 明写 h3-h4 semibold / h5 medium / h6 normal，
    层级靠字重。四条一起挂 600 时 h5、h6 和正文就分不开。"""
    base = CSS.split(".ws-md h3,.ws-md h4,.ws-md h5,.ws-md h6{")[1].split("}")[0]
    assert "font-weight" not in base, "四条又共用一个字重了"
    for sel, w in ((".ws-md h3,.ws-md h4", "600"), (".ws-md h5", "500"),
                   (".ws-md h6", "400")):
        m = re.search(r"(?m)^%s\{([^}]*)\}" % re.escape(sel), CSS)
        assert m, f"找不到独立的一条 {sel}{{...}}"
        assert f"font-weight:{w}" in m.group(1), \
            f"{sel} 该是 {w}（DESIGN.md:229）"


def test_sidebar_row_pitch_survives_the_keycap_border():
    """行距 33 是量的（行中心 97/130/163）。撑爆它的不是文字，是那枚带 1px 边框的
    快捷键小标签：它自己的 line-box 一旦高于行的 line-height，整行就被顶到 22.3px。"""
    item = CSS.split(".sb-item{")[1].split("}")[0]
    kbd = CSS.split(".sb-kbd{")[1].split("}")[0]
    nav = CSS.split(".sb-nav{")[1].split("}")[0]
    lh = int(re.search(r"line-height:(\d+)px", item).group(1))
    klh = int(re.search(r"line-height:(\d+)px", kbd).group(1))
    pad = int(re.search(r"padding:(\d+)px \d+px", item).group(1))
    gap = int(re.search(r"gap:(\d+)px", nav).group(1))
    assert klh + 2 <= lh, f"快捷键标签 {klh}+2px 边框 > 行 {lh}px，它会把整行撑高"
    pitch = lh + pad * 2 + gap
    assert pitch == 33, f"侧栏行距算出来是 {pitch}，量到的是 33"


# ---------------- 无边框标题行（窗口外壳） ----------------

def test_the_title_bar_paints_no_surface_of_its_own():
    """参考图那条行不是"一条栏"，是左右两栏各自往上长出来的空白：
    左段取侧栏色、右段取页面色。给它自己一个底色就前功尽弃。
    下边线是允许的，而且必须有 —— 2026-10-05 逐像素量过，标题行与内容之间
    在 x=900 和 x=1600 两处都是同一个单像素 #373C37，和侧栏那道缝同色。
    取 rsplit 而不是 split：整份文件里同一选择器出现两次时，赢的是后面那条，
    断言必须跟着读得到的那份。"""
    tl = _winning_rule(".titlebar")
    assert "background" not in tl or "background:transparent" in tl, \
        "标题行铺了自己的底 = 右侧又被切出一道带子"
    left = _winning_rule(".tlb-left")
    right = _winning_rule(".tlb-right")
    assert "var(--bg-shell)" in left, "左段没跟侧栏同色"
    assert "var(--bg-page)" in right, "右段没跟页面同色"
    assert "border-bottom" not in tl, "标题行整体画线 = 左右两段的缝被糊成一条"
    for name, blk in (("左段", left), ("右段", right)):
        assert "border-bottom:1px solid var(--line)" in blk, \
            f"标题行{name}缺那条收口缝，窗口顶边会和内容粘成一片"


def test_window_buttons_only_exist_when_the_bridge_exists():
    """没有 pywebview 就没有窗口可控制 —— 三枚按不动的按钮是骗人的。
    HTML 里默认 hidden，JS 只在 bridge 到位时才把它翻开。"""
    assert '<div class="tlb-win" id="tbWin" hidden>' in INDEX_HTML
    assert ".tlb-win[hidden]{display:none}" in CSS, \
        "[hidden] 的默认 display:none 会被 display:flex 顶掉，三枚按钮会漏出来"
    fn = APP_JS.split("function paintShell()")[1].split("\n};")[0]
    assert "box.hidden = !SHELL_OK" in fn
    assert "pywebviewready" in APP_JS, "没有 bridge 就绪事件，SHELL_OK 永远是 false"


def test_maximized_window_hides_the_eight_resize_handles():
    """最大化时窗口铺满屏幕、边框本来就拉不动，那八个透明手柄还在原地等着按 ——
    pointerdown 里那道 SHELL_MAX 判断只挡住动作，挡不住"看着能按"。
    2026-09-25 用 CDP 往真窗口里量过：maximized 那一步 rzHidden 读到的是 false。"""
    fn = APP_JS.split("function paintShell()")[1].split("\n};")[0]
    assert "rz.hidden = !SHELL_OK || SHELL_MAX" in fn, "拉边手柄没跟着最大化一起藏"


def test_os_driven_maximize_and_restore_repaint_the_window_buttons():
    """Win+↑、贴边快照、拖到屏幕顶这些系统途径改的最大化不经过 winMaxToggle，
    SHELL_MAX 就停在旧值上：图标还是「最大化」、手柄还露着。resize 是这些变化
    唯一都会经过的信号（WebView2 跟着窗口一起变尺寸），focus 再兜一次。"""
    assert re.search(r"addEventListener\('resize',\s*syncShellSoon\)", APP_JS), \
        "系统改的最大化没人接"
    assert re.search(r"addEventListener\('focus',\s*syncShellSoon\)", APP_JS), \
        "重新获得焦点后没对一次状态"
    body = APP_JS.split("function syncShellSoon()")[1].split("\n}")[0]
    assert "clearTimeout" in body, "拖边框会连发几十个 resize，不能每一个都去问一次 bridge"


def test_a_failed_agents_save_does_not_leave_the_ui_lying():
    """四处调用点都写着 `if(!await postAgents(...)) return;`，而 postAgents 连失败
    都返回 {detail:...} —— 真值，于是那四道守卫一次也没生效过：保存失败照样改 ST，
    页面上显示的是一个服务端根本没收下的值。"""
    body = APP_JS.split("async function postAgents(")[1].split("\n}")[0]
    assert "return null" in body, "失败必须返回假值，否则上面那四道守卫是空的"
    assert "renderSettings()" in body, "失败要把这一节按 ST 里的旧值重画回去"
    for fn in ("saveTimeout", "saveRetry", "saveEffort", "saveAutoContinue"):
        seg = APP_JS.split(f"window.{fn} = async function")[1].split("\n};")[0]
        assert f"if(!await postAgents(" in seg, f"{fn} 没检查保存结果"


def test_the_resize_handles_and_the_launcher_agree_on_the_minimum_size():
    """无边框把系统那条可拉的边框一起没了，所以拉边是页面上八个透明手柄做的。
    夹住尺寸的那两个数必须和建窗时的 min_size 是同一个 —— 不然能拉到比允许更小，
    然后布局在没人看的地方碎掉。"""
    edges = set(re.findall(r'data-edge="(\w+)"', INDEX_HTML))
    assert edges == {"n", "s", "w", "e", "nw", "ne", "sw", "se"}, f"拉边手柄不全：{sorted(edges)}"
    for cls in edges:
        assert f".rz-{cls}{{" in CSS, f".rz-{cls} 没有定位规则"
    w = int(re.search(r"\bRZ_MIN_W = (\d+)", APP_JS).group(1))
    h = int(re.search(r"\bRZ_MIN_H = (\d+)", APP_JS).group(1))
    src = (STATIC_DIR.parent / "loom_launch.py").read_text(encoding="utf-8")
    m = re.search(r"min_size=\((\d+),\s*(\d+)\)", src)
    assert m, "建窗参数里没有 min_size"
    assert (int(m.group(1)), int(m.group(2))) == (w, h), \
        f"页面夹的是 {w}x{h}，建窗写的是 {m.group(1)}x{m.group(2)}"
    assert "frameless=True" in src and "js_api=api" in src, "窗口没开无边框或没接 bridge"


def test_the_maximize_toggle_tracks_the_real_window_state_not_a_stale_flag():
    """打包态用 CDP 往真窗口里问过：pywebview 的 Window.maximized 只是
    create_window 的那个入参，winforms 后端从不回写它。所以按 `if window.maximized`
    判分支的那次实测里，状态位恒为 False —— 第一次点最大化确实铺满了（标题行从
    1426 宽变成 1707 宽），第二次点它还是走 maximize 分支，既不还原、图标也永远
    停在"最大化"。真状态只在 events.maximized / restored 里。"""
    src = (STATIC_DIR.parent / "loom_launch.py").read_text(encoding="utf-8")
    body = src.split("class ShellApi:")[1].split("\ndef ")[0]
    assert "self.window.maximized" not in body, \
        "又去读 Window.maximized 了 —— winforms 从不回写它，见本条 docstring 的实测"
    assert "+= lambda: setattr(self, \"_max\", True)" in body, "没接 events.maximized"
    assert "+= lambda: setattr(self, \"_max\", False)" in body, "没接 events.restored"
    toggle = body.split("def win_maximize_toggle")[1].split("def ")[0]
    assert "if self._max:" in toggle and "self._window.restore()" in toggle, \
        "最大化按钮没有还原分支"
    state = body.split("def win_state")[1]
    assert '"maximized": self._max' in state, "win_state 报的还是那个没人维护的位"
    assert "api._attach(win)" in src, "建窗后没绑事件，状态位永远是初始值"


def test_the_shell_bridge_exposes_only_methods_not_the_window_object():
    """pywebview 扫 js_api 走的是 dir()，非下划线的属性只要是个对象就会**递归进去**
    （webview/util.py 的 get_functions）。实测过一次：那个公开的 `self.window` 把扫描
    一路带进 WinForms 的 .NET 对象图，日志刷出 4.2 MB
    `Error while processing window.native.DefaultFont.FontFamily.GenericSansSerif...`，
    最后 logger.error 自己在栈没恢复时又炸，注入给页面的 api 变成空对象 ——
    三枚窗控点不动，而且没有任何一处显式报错。所以桥上的成员只能是以 _ 开头的。"""
    src = (STATIC_DIR.parent / "loom_launch.py").read_text(encoding="utf-8")
    body = src.split("class ShellApi:")[1].split("\ndef ")[0]
    assigns = re.findall(r"self\.([A-Za-z_]\w*)\s*=", body)
    for name in sorted(set(assigns)):
        assert name.startswith("_"), \
            f"ShellApi 把窗口对象挂成了公开成员 {name} —— 扫描会递归进 .NET 对象图"
    exposed = [n for n in re.findall(r"\n    def (\w+)\(", body) if not n.startswith("_")]
    assert sorted(exposed) == ["win_close", "win_maximize_toggle", "win_minimize",
                              "win_resize", "win_state"], \
        f"桥上暴露的不止那五枚窗控：{sorted(exposed)}"


def test_an_empty_page_header_collapses_instead_of_holding_the_row():
    """首页没有页头标题也没有动作 —— 那条 52px 得整条收掉，不然只剩一个孤零零的
    图标占着位（无边框之后它紧挨着标题行，更像坏了）。
    .topbar 是 display:flex，所以 [hidden] 必须配一条显式的 none。"""
    fn = APP_JS.split("function paintChrome()")[1].split("\n}\n")[0]
    assert "bar.hidden = empty" in fn, "空页头没整条收起"
    assert "if(empty) return" in fn, "收起后还在往里面写图标 = 空行里剩一枚孤图标"
    assert ".topbar[hidden]{display:none}" in CSS, "display:flex 顶掉了 [hidden]"


def test_the_close_window_guard_reads_the_counter_that_is_actually_written():
    """有任务在跑时关窗口要先确认。这个确认以前恒不触发：它读 ST.activeRuns，
    而全仓只有 ST.liveRuns 被写过 —— `undefined !== undefined` 为假，n 永远是 0，
    于是点关闭直接杀掉正在跑的智能体。名字对不上不会报错，只会静默失效。"""
    fn = APP_JS.split("window.winClose")[1].split("};")[0]
    assert "ST.liveRuns" in fn, "关闭确认没读那份真被写的计数"
    assert "activeRuns" not in APP_JS, \
        "ST.activeRuns 是个从没被赋值过的名字，别再拿它当条件"
    assert "liveRuns" in APP_JS.split("ST.liveRuns =")[0], "liveRuns 得先在 ST 初值里存在"


# =====================================================================
# Voyra System Tokens v11 · 重构契约
# =====================================================================

def test_v11_design_tokens_present():
    """v11 令牌表必须完整：明暗色板、七态语义色、嵌套圆角、间距网格、动效基准。"""
    required = ["--bg-page", "--bg-shell", "--bg-surface", "--bg-raised", "--bg-sunken",
                "--bg-hover", "--bg-active", "--bg-float",
                "--ink", "--ink-2", "--ink-3", "--ink-4", "--ink-inv",
                "--line", "--line-soft", "--line-strong",
                "--btn-ink", "--btn-ink-hover",
                "--st-pending", "--st-running", "--st-waiting", "--st-done",
                "--st-failed", "--st-cancelled", "--st-revising",
                "--r-1", "--r-2", "--r-3", "--r-4", "--r-5", "--r-pill",
                "--sp-1", "--sp-2", "--sp-3", "--sp-4", "--sp-5", "--sp-6", "--sp-8",
                "--shadow-sm", "--shadow-md", "--shadow-pop",
                "--dur-fast", "--dur-base", "--ease"]
    missing = [tok for tok in required if f"{tok}:" not in CSS]
    assert not missing, f"v11 缺失核心 Design Token：{missing}"


def test_v11_seven_state_semantics_have_dark_overrides():
    """七大运行状态的语义色两套主题都要有；暗色那套必须重新取值，
    否则亮色选的深色值压在暗底上根本读不出来。"""
    light = CSS.split(":root{")[1].split('html[data-theme="dark"]')[0]
    dark = CSS.split('html[data-theme="dark"]')[1]
    for st in ["pending", "running", "waiting", "done", "failed", "cancelled", "revising"]:
        assert f"--st-{st}:" in light, f"亮色缺 --st-{st}"
        assert f"--st-{st}:" in dark, f"暗色缺 --st-{st}"
        assert f"--st-{st}-bg:" in light and f"--st-{st}-bg:" in dark, f"缺 --st-{st}-bg 底色"


def test_v11_keymap_is_the_single_source_of_truth():
    """全局快捷键由 KEYMAP 驱动，且无残留硬编码 if (k === '...') 分支。"""
    assert "const KEYMAP = [" in APP_JS, "app.js 中缺失 KEYMAP 声明"
    assert "KEYMAP.find(" in APP_JS, "快捷键派发未采用 KEYMAP 查表机制"
    assert "if(k==='n')" not in APP_JS and "if(k==='k')" not in APP_JS, "发现残留硬编码按键分支"


def test_v11_container_radius_ladder():
    """顶层容器 / 卡片 / 浮层严格遵循嵌套圆角梯度。
    这张表以前和 NESTED_RADIUS 各写一份、并且读法不同（一张取第一条、一张取最后一条），
    于是 .tk-card 同时"应该是 --r-4"和"应该是 --r-5"而两边都绿 —— 两份真相的测试
    只会一起说谎。现在先要求两张表对同一个选择器给同一档，再统一走 _radius_of
    （它读生效的那条）。"""
    expectations = {
        # 输入台壳按 2026-09-24 的像素量是 12 = --r-4，不是文档许可的 2xl；
        # 见 NESTED_RADIUS 那条注释。曾经 v11 段把它写成 --r-5，
        # 又被 voyra-ui.css 的硬编码 12px 盖回来，所以看起来一直是对的。
        ".tk-card": "--r-4", ".modal-box": "--r-5", ".up-card": "--r-5",
        ".step-card": "--r-4", ".st-panel": "--r-4", ".toast": "--r-5", ".cp-send": "--r-3",
    }
    clash = {s: (r, expectations[s]) for s, r in NESTED_RADIUS.items()
             if s in expectations and expectations[s] != r}
    assert not clash, f"两张圆角表对同一选择器给了不同档（NESTED_RADIUS, 本表）：{clash}"
    bad = {}
    for sel, want in expectations.items():
        got = _radius_of(sel)
        if got != want:
            bad[sel] = (got, want)
    assert not bad, f"圆角档位不合规（实际, 期望）：{bad}"


def test_v11_i18n_pair_coverage():
    """v11 新增的键必须在中英字典里成对出现，绝不出现单边 Key。"""
    for key in ["tk.subDesc", "ed.unsavedGuard", "sk.searchPh", "sk.emptySelect", "sk.noDesc"]:
        n = UI_JS.count("'" + key + "'")
        assert n == 2, f"{key} 未中英成对（出现 {n} 次）"
