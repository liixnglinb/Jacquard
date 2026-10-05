# -*- coding: utf-8 -*-
"""设置类接口的往返与边界：这些值是直接喂给 CLI 命令行参数的，不能靠前端兜。"""
import json

import pytest

from conftest import STATIC_DIR

from app import db  # noqa: E402  (conftest 已经把数据目录挪进沙箱)


def _get(client):
    r = client.get("/api/agents")
    assert r.status_code == 200
    return r.json()


def test_agents_payload_shape(client):
    d = _get(client)
    for key in ("agents", "default_engine", "sandbox_options", "effort_options",
                "step_retry", "reasoning_effort", "auto_continue", "paths"):
        assert key in d, f"/api/agents 少了 {key}"
    # 出厂库没了，这两个字段就不该再出现（留着会变成永远为空的假信息）
    assert "bundled_skills" not in d and "library_version" not in d
    assert {a["engine"] for a in d["agents"]} == {"claude", "codex"}
    assert d["effort_options"][0] == "auto"


def test_agents_roundtrip(client):
    body = {"codex_sandbox": "read-only", "reasoning_effort": "high",
            "step_retry": "2", "auto_continue": "1", "agent_timeout": "900"}
    assert client.post("/api/agents", json=body).status_code == 200
    d = _get(client)
    assert d["codex_sandbox"] == "read-only"
    assert d["reasoning_effort"] == "high"
    assert d["step_retry"] == "2"
    assert d["auto_continue"] == "1"
    assert d["agent_timeout"] == "900"


@pytest.mark.parametrize("body,field", [
    ({"codex_sandbox": "no-pe"}, "沙箱"),
    ({"reasoning_effort": "ultra"}, "推理"),
    ({"step_retry": "9"}, "重试"),
    ({"step_retry": "-1"}, "重试"),
    ({"step_retry": "abc"}, "重试"),
    ({"agent_timeout": "5"}, "超时"),
    ({"agent_timeout": "99999"}, "超时"),
    ({"agent_timeout": "soon"}, "超时"),
    ({"default_engine": "gpt"}, "引擎"),
])
def test_agents_rejects_bad_values(client, body, field):
    assert client.post("/api/agents", json=body).status_code == 400


def test_bad_request_leaves_setting_untouched(client):
    client.post("/api/agents", json={"step_retry": "1"})
    before = _get(client)["step_retry"]
    assert client.post("/api/agents", json={"step_retry": "77"}).status_code == 400
    assert _get(client)["step_retry"] == before


def test_partial_post_keeps_other_fields(client):
    client.post("/api/agents", json={"reasoning_effort": "low", "step_retry": "3",
                                     "codex_sandbox": "danger-full-access"})
    assert client.post("/api/agents", json={"step_retry": "0"}).status_code == 200
    d = _get(client)
    assert d["step_retry"] == "0"
    assert d["reasoning_effort"] == "low"
    assert d["codex_sandbox"] == "danger-full-access"


def test_empty_string_clears(client):
    client.post("/api/agents", json={"claude_cli": "C:/nowhere/claude.exe"})
    assert _get(client)["claude_cli"] == "C:/nowhere/claude.exe"
    client.post("/api/agents", json={"claude_cli": ""})
    assert _get(client)["claude_cli"] in ("", None)


def test_appearance_bulk_roundtrip(client):
    body = {"ui_lang": "en", "ui_theme": "light", "ui_accent": "gold", "ui_font": "mono"}
    assert client.post("/api/settings/bulk", json=body).status_code == 200
    d = client.get("/api/settings").json()
    assert d["ui_accent"] == "gold" and d["ui_theme"] == "light"


def test_appearance_bulk_cannot_touch_engine_keys(client):
    """外观面板只能写 ui_*，别想从这儿把 default_engine / claude_cli 改掉。"""
    client.post("/api/agents", json={"step_retry": "1"})
    before = _get(client)["step_retry"]
    client.post("/api/settings/bulk",
                json={"ui_theme": "dark", "step_retry": "3", "default_engine": "codex",
                      "claude_cli": "C:/evil.exe"})
    d = _get(client)
    assert d["step_retry"] == before
    assert d["default_engine"] != "codex"
    assert d["claude_cli"] == ""


def test_pipelines_expose_run_count(client, dbsession, fresh_runs):
    """侧栏「项目」= 真跑过的流程，靠 /api/pipelines 里的 runs 字段筛。"""
    dbsession.create_pipeline("proj-a", label="A", steps=[{"key": "a"}])
    dbsession.create_pipeline("proj-b", label="B", steps=[{"key": "b"}])
    for i in range(2):
        dbsession.create_run(f"run-projcount{i}", "proj-a", steps=[])
    dbsession.create_run("run-projcount-x", "proj-b", steps=[])
    try:
        d = client.get("/api/pipelines").json()
        by = {p["name"]: p["runs"] for p in d["pipelines"]}
        assert by["proj-a"] == 2 and by["proj-b"] == 1
        assert all(isinstance(p["runs"], int) for p in d["pipelines"])
    finally:
        conn = dbsession.get_conn()
        conn.execute("DELETE FROM runs WHERE pipeline IN ('proj-a','proj-b')")
        conn.execute("DELETE FROM pipeline_definitions WHERE name IN ('proj-a','proj-b')")
        conn.commit(); conn.close()


def test_ships_with_no_default_content(client, dbsession, fresh_runs):
    """软件不再带任何默认配置：技能与流程两个列表开箱都得是空的。

    这条就是"删掉出厂库"这件事本身的回归 —— 以后谁再往 import 期塞一次
    播种，这里会立刻红，而不是悄悄回到随包发一套模板的老样子。
    """
    assert dbsession.run_counts() == {}
    assert client.get("/api/pipelines").json()["pipelines"] == []
    assert client.get("/api/skills").json()["skills"] == []
    # 恢复出厂 / 库复位这两个入口应当已经不存在
    assert client.post("/api/pipelines/anything/restore").status_code == 404
    assert client.post("/api/library/reset").status_code == 404


def test_reveal_rejects_arbitrary_path(client, monkeypatch):
    """只认白名单键；命中后真去开资源管理器的动作要打桩，测试不能弹窗口。"""
    import subprocess
    opened = []
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: opened.append(a))
    assert client.post("/api/reveal", params={"which": "../../windows"}).status_code == 400
    assert client.post("/api/reveal", params={"which": "data"}).status_code == 200
    assert len(opened) == 1


SECRET = "sk-NEVER-ECHO-9f3a2b"


def _mk_preset(client, name):
    r = client.post("/api/providers", json={"name": name, "provider": "openai",
                                            "api_base": "http://127.0.0.1:9/v1",
                                            "api_key": SECRET, "model": "m1"})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def test_preset_list_never_echoes_the_key(client):
    """清单曾经是 SELECT * 原样回吐，等于每开一次设置页密钥就上一遍网络，
    前端再把它回传给 /test 和 /models/list。现在只准回 has_key / key_hint。"""
    _mk_preset(client, "gate-mask-1")
    d = client.get("/api/providers").json()
    hits = [p for p in d["presets"] if p["name"] == "gate-mask-1"]
    assert hits, "预设没建出来，这条测试就什么也没守住"
    assert "api_key" not in hits[0]
    assert hits[0]["has_key"] is True
    assert SECRET not in client.get("/api/providers").text


def test_preset_mutations_also_mask(client):
    pid = _mk_preset(client, "gate-mask-2")
    assert SECRET not in client.post(f"/api/providers/{pid}/default").text
    assert SECRET not in client.put(f"/api/providers/{pid}",
                                    json={"name": "gate-mask-2", "model": "m2"}).text


def test_provider_test_resolves_key_server_side(client, monkeypatch):
    """按 id 让服务端自己取密钥：前端不再持有它，也就无从回传。"""
    from app import llm
    seen = {}
    monkeypatch.setattr(llm, "test_connection",
                        lambda provider, api_base, api_key, model="":
                        seen.update(api_key=api_key, api_base=api_base) or (True, "ok"))
    pid = _mk_preset(client, "gate-mask-3")
    r = client.post("/api/providers/test", json={"id": pid, "provider": "openai"})
    assert r.status_code == 200 and r.json()["ok"]
    assert seen.get("api_key") == SECRET, "服务端没按 id 把密钥取出来"


def test_error_text_from_upstream_is_redacted(client, monkeypatch):
    """上游网关的 4xx body 会被原样回吐，里面可能带我们发出去的 Authorization。"""
    from app import llm
    monkeypatch.setattr(llm, "test_connection",
                        lambda *a, **k: (False, f"401 bad key {a[2]}"))
    pid = _mk_preset(client, "gate-mask-4")
    msg = client.post("/api/providers/test", json={"id": pid}).json()["msg"]
    assert SECRET not in msg and "[REDACTED]" in msg
def _catalog():
    src = (STATIC_DIR / "providers-catalog.js").read_text(encoding="utf-8")
    return json.loads(src[src.index("["):src.rindex("]") + 1])


# base 以 /v1 结尾、且实测那条 /v1/messages 真的存在（401 而不是 404）的才许留在名单里
V1_BASES_OK = {"硅基流动"}


def test_anthropic_catalog_bases_are_not_openai_paths():
    """以 /v1 结尾是 OpenAI 的写法。抄别家工具的配置最容易连这个一起抄，
    于是 anthropic_url 拼出 /v1/messages。2026-09-21 不带密钥逐个探过：
    月之暗面 404（它的 anthropic 路在 /anthropic）、百度千帆 404（在 /anthropic），
    两条都已就地改掉；剩下的 /v1 只有硅基流动是真的。"""
    from app import llm
    for e in _catalog():
        assert e["api_base"].startswith("https://"), e["name"]
        url = llm.anthropic_url(e["api_base"])
        assert url.endswith("/messages"), e["name"]
        assert "/messages" in url
        if e["api_base"].rstrip("/").endswith("/v1"):
            assert e["name"] in V1_BASES_OK, f'{e["name"]} 的 base 是 OpenAI 写法：{url}'


def test_a_caller_chosen_base_never_carries_the_stored_key(dbsession):
    """清单不外泄 api_key，所以测试/拉模型改成"按 id 让服务端自己取"。
    但原来那版是 `api_base or 库里base` —— 调用方传的 base 赢，而 key 兜底取库里的，
    于是 `POST /api/providers/test {id, api_base:"https://evil"}` 就把真密钥发去了
    对方指定的地址。改端点就必须重新填密钥（git credential / gh 同一套规矩）。"""
    from app import main
    pid = dbsession.add_preset("creds-x", provider="openai",
                               api_base="https://legit.test/v1", api_key="sk-stored")
    assert main._preset_creds(pid, "", "") == \
        ("https://legit.test/v1", "sk-stored", ""), "不改端点时要照常替前端取凭证"
    base, key, err = main._preset_creds(pid, "https://evil.test/", "")
    assert key == "", "调用方指定的端点拿到了库里存的密钥"
    assert err, "拒绝时还得给一句能显示给用户的话"
    assert main._preset_creds(pid, "https://evil.test/", "sk-mine") == \
        ("https://evil.test/", "sk-mine", ""), "调用方自己带的凭证是它自己的，允许"
    assert main._preset_creds(0, "https://fresh.test/", "sk-new") == \
        ("https://fresh.test/", "sk-new", ""), "新建未存预设（无 id）不受影响"


def _defaults(d):
    return [x["name"] for x in d["presets"] if x.get("is_default")]


def test_deleting_the_default_preset_leaves_a_default(client):
    """删掉「默认」那一张，以前库里就一个默认都不剩：get_default_preset() 回 None，
    于是所有没显式挑端点的步骤从此静默地不注入端点 —— 整套 API 接入不再起作用，
    而界面上没有任何一处说它没了。删的时候必须把默认挪到还留着的那一张上。

    库是会话级共享的、别的用例也会留下预设，所以这里只断言不变量：
    删完之后恰好还剩一个默认，且它仍在这张表里、不是被删掉那一张。"""
    a = _mk_preset(client, "gate-def-a")
    b = _mk_preset(client, "gate-def-b")
    try:
        assert client.post(f"/api/providers/{b}/default").status_code == 200
        d = client.delete(f"/api/providers/{b}").json()
        left = _defaults(d)
        assert len(left) == 1, f"删掉默认之后剩了 {len(left)} 个默认：{left}"
        assert left[0] != "gate-def-b", "补位补到了刚被删掉那一张上"
        assert left[0] in [x["name"] for x in d["presets"]]
        assert db.get_default_preset(), "服务端已经拿不到默认预设"
    finally:
        client.delete(f"/api/providers/{a}")


def test_deleting_a_non_default_preset_does_not_move_the_default(client):
    """反向钉住：只有删的确实是默认那一张时才补位。
    否则删一张备用端点会把用户挑好的默认悄悄换掉。"""
    keep = _mk_preset(client, "gate-keep")
    extra = _mk_preset(client, "gate-extra")
    try:
        assert client.post(f"/api/providers/{keep}/default").status_code == 200
        d = client.delete(f"/api/providers/{extra}").json()
        assert _defaults(d) == ["gate-keep"], _defaults(d)
    finally:
        client.delete(f"/api/providers/{keep}")


def test_retired_setting_keys_are_purged_on_init(client):
    """功能下线之后，那行设置必须真的从库里走掉。

    /api/settings 是整表吐出去的（app/main.py:998 → db.get_all_settings()），
    所以"代码不再读它"并不等于"它不存在"—— update_repo / update_asset /
    library_version / ui_accent 四把键就是这么在每台机器的 settings 表里躺到
    现在的，接口一直往外回一个没人读的值。init_db() 里那张具名单负责收口。"""
    for k in db.RETIRED_SETTINGS:
        db.set_setting(k, "stale-value")
    # 一把活键当对照：清退役键不许顺手把别人的也清了
    db.set_setting("default_engine", "claude")
    db.init_db()
    left = db.get_all_settings()
    for k in db.RETIRED_SETTINGS:
        assert k not in left, f"退役键 {k} 还留在 settings 表里"
    assert left.get("default_engine") == "claude", "清退役键时把活键一起清了"
    body = client.get("/api/settings").json()
    for k in db.RETIRED_SETTINGS:
        assert k not in body, f"/api/settings 还在往外回退役键 {k}"


def test_the_retired_list_names_only_keys_no_code_reads(client):
    """反向锁：这张名单里不许出现代码还在读的键。
    写错一个名字就是一次静默的数据删除，比留着孤儿值严重得多。"""
    import re
    from pathlib import Path
    src = {}
    for p in list((Path(__file__).resolve().parents[1] / "app").glob("*.py")) + \
             list((Path(__file__).resolve().parents[1] / "static").glob("*.js")):
        src[p.name] = p.read_text(encoding="utf-8")
    for k in db.RETIRED_SETTINGS:
        # ui_* 是整批按前缀读/写的，那类键要单独确认前端映射表里没有它
        if k.startswith("ui_"):
            assert f"'{k}'" not in src["ui.js"] and f'"{k}"' not in src["ui.js"], \
                f"{k} 还在 ui.js 的外观白名单里，不能算退役"
        hits = [n for n, s in src.items() if re.search(r"[\"']" + re.escape(k) + r"[\"']", s)
                and n not in ("db.py",)]
        assert not hits, f"{k} 仍被 {hits} 引用，它不是退役键"
