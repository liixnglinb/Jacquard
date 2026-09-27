# -*- coding: utf-8 -*-
"""品牌字样的落点守卫。

2026-09-27 显示层改名 织流 Loom → 织流 Jacquard，第一次做漏了五处：codex 的 provider
显示名、FastAPI 的 title（`/docs` 页头上就是它）、`make_release.py` 的兜底 notes（它会
进 latest.json，软件里的更新卡片和下载页都读那份）、源码启动横幅和端口提示。
一个都没有测试钉着，所以"改完了"这件事全靠人眼扫 —— 这条测试就是替掉那只眼。

扫的是**会到用户眼前的那批字符串**，不是全仓库 grep：注释和 docstring 里留着 Loom 是
历史叙述，而那些恰恰是正则扫描最爱误伤的地方（这一轮已经被自己的注释绊过四次）。
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def _dict_values(src: str, locale: str = None):
    """ui.js 里 DICT 的译文。按 `'key': 'value'` 取，注释结构上就进不来。
    locale 给定就只取那一半 —— zh 在前 en 在后，合并取字典会让 en 悄悄盖掉 zh。"""
    body = src[src.index("const DICT = {"):src.index("const ICONS = {")]
    if locale is None:
        span = body
    else:
        i = body.index(f"{locale}: {{")
        j = body.find("en: {", i) if locale == "zh" else -1
        span = body[i:] if j < 0 else body[i:j]
    return re.findall(r"'([A-Za-z0-9_.]+)':\s*'([^']*)'", span)


def test_no_translated_copy_still_says_loom():
    pairs = _dict_values(_read("static/ui.js"))
    assert len(pairs) > 500, f"译文只解析出 {len(pairs)} 条，八成是 ui.js 换了写法，守卫失效"
    stale = [(k, v) for k, v in pairs if "Loom" in v or "loom" in v]
    assert not stale, f"这些文案还带着旧名：{stale}"


def test_brand_copy_is_jacquard_in_both_locales():
    zh = dict(_dict_values(_read("static/ui.js"), "zh"))
    en = dict(_dict_values(_read("static/ui.js"), "en"))
    assert zh["brand.full"] == "Jacquard 织流"
    assert zh["brand.name"] == "织流"        # 中文短名一直是「织流」，拉丁名才换
    assert en["brand.name"] == "Jacquard" and en["brand.full"] == "Jacquard"


def test_shell_surfaces_carry_the_new_name():
    """五处不在译文表里、但一样会露脸的字符串。逐个钉，改回去就红。"""
    checks = [
        ("loom_launch.py", 'WINDOW_TITLE = "织流 Jacquard"'),
        ("static/index.html", "<title>Jacquard 织流</title>"),
        ("app/main.py", 'FastAPI(title="Jacquard 织流")'),
        ("app/agents.py", '.name="Jacquard"'),
        ("make_release.py", 'f"织流 Jacquard {ver}"'),
        ("run.py", 'Jacquard 织流 启动'),
        ("run.py", '旧 Jacquard 进程'),
        ("installer.iss", '#define MyAppName "织流 Jacquard"'),
    ]
    for rel, frag in checks:
        assert frag in _read(rel), f"{rel} 里找不到 {frag!r}"


def test_deliberately_unchanged_identifiers_stay_loom():
    """改名**刻意**没动的四样，反过来钉住：动它们会伤到已装的人，不是遗漏。
    ① 安装包产物名与 COS key ② 安装目录 ③ 命名互斥体 ④ 升级身份 AppId 与 exe 名。
    AppId 是 Inno 认"这是同一个程序"的依据，动了它 1.2.6 就不再替换 1.2.5，
    「添加或删除程序」里会留两个条目 —— 所以才只换 MyAppName（显示名）。"""
    assert 'APP = "Loom"' in _read("make_release.py")
    assert "LoomZhiLiu.SingleInstance" in _read("loom_launch.py")
    iss = _read("installer.iss")
    assert re.search(r"Programs\\\\Loom|Programs\\Loom", iss), "安装目录不该跟着改名"
    assert 'AppId={{7C1D4E9A-2B6F-4C38-9A51-LOOMFLOW0100}' in iss
    assert '#define MyAppExe "Loom.exe"' in iss


def test_skill_source_vocabulary_is_the_stored_contract():
    """技能来源存进流程 JSON 的是 `""` / claude / codex —— 自家那份一直是**空串**，
    从来不是 'loom'。所以改名压根不涉及这个字段；钉住取值集合，别有人在白名单里
    加个 'jacquard' 去"配合新名字"，那会让存量流程的技能引用落空。"""
    src = _read("app/pipelines.py")
    assert '("", "claude", "codex")' in src
