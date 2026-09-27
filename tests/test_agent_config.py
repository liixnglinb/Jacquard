# -*- coding: utf-8 -*-
"""引擎与端点解析阶梯：决定「这一步到底拿什么配置去喂 CLI」。

这条阶梯是软件的核心约定（正文只能由智能体产出，API 预设只是注入给 CLI），
所以每一级的优先级都要钉住。
"""
import ast
from pathlib import Path

import pytest

from app import agents, db, runner


@pytest.fixture(autouse=True)
def _clean_presets():
    conn = db.get_conn()
    conn.execute("DELETE FROM api_presets")
    conn.commit()
    conn.close()
    yield


@pytest.fixture
def both_clis(monkeypatch):
    """假装两个 CLI 都在，别依赖测试机的 PATH。"""
    monkeypatch.setattr(agents, "resolve_binary",
                        lambda e: f"C:/fake/{e}.cmd" if e in agents.ENGINES else "")


def test_engine_ladder(both_clis):
    assert runner.resolve_agent_config({})["engine"] == "claude"      # ENGINES 里第一个
    db.set_setting("default_engine", "codex")
    assert runner.resolve_agent_config({})["engine"] == "codex"
    assert runner.resolve_agent_config({"engine": "claude"})["engine"] == "claude"
    assert runner.resolve_agent_config({"engine": "gpt"})["engine"] == "codex"


def test_no_cli_anywhere_raises(monkeypatch):
    monkeypatch.setattr(agents, "resolve_binary", lambda e: "")
    with pytest.raises(RuntimeError, match="未检测到任何智能体 CLI"):
        runner.resolve_agent_config({})


def test_no_preset_injects_nothing(both_clis):
    c = runner.resolve_agent_config({"engine": "claude"})
    assert c["api_base"] == "" and c["api_key"] == "" and c["model"] == ""
    assert c["warn"] == ""


def test_step_model_matching_a_preset_name_wins(both_clis):
    db.add_preset("deepseek", provider="openai", api_base="https://x/v1",
                  api_key="k-1", model="deepseek-chat")
    db.add_preset("kimi", provider="openai", api_base="https://k/v1",
                  api_key="k-2", model="kimi-k2")
    db.set_default_preset(db.get_preset_by_name("deepseek")["id"])
    c = runner.resolve_agent_config({"engine": "codex", "model": "kimi"})
    assert c["api_base"] == "https://k/v1" and c["api_key"] == "k-2"
    assert c["preset"] == "kimi"


def test_bare_model_id_rides_on_default_preset(both_clis):
    db.add_preset("kimi", provider="openai", api_base="https://k/v1",
                  api_key="k-2", model="kimi-k2")
    c = runner.resolve_agent_config({"engine": "codex", "model": "glm-4.6"})
    assert c["api_base"] == "https://k/v1"
    assert c["model"] == "glm-4.6"


def test_model_map_then_fallback_then_preset_model(both_clis):
    db.add_preset("route", provider="openai", api_base="https://r/v1", api_key="k",
                  model="base-model",
                  extra={"fallback_model": "fb-model",
                         "model_map": {"draft": "mapped-model"}})
    step = {"engine": "codex", "key": "draft"}
    assert runner.resolve_agent_config(step)["model"] == "mapped-model"
    step["key"] = "review"
    assert runner.resolve_agent_config(step)["model"] == "fb-model"
    db.update_preset(db.get_preset_by_name("route")["id"], extra={})
    assert runner.resolve_agent_config(step)["model"] == "base-model"


def test_wire_api_forwarded(both_clis):
    db.add_preset("kimi", provider="openai", api_base="https://k/v1", api_key="k",
                  model="m", extra={"wire_api": "responses"})
    assert runner.resolve_agent_config({"engine": "codex"})["wire_api"] == "responses"


def test_protocol_mismatch_drops_injection(both_clis):
    """anthropic 端点喂给 codex：不注入，改走 CLI 自身登录，并留下原因。"""
    db.add_preset("claude-ep", provider="anthropic", api_base="https://a/api",
                  api_key="k", model="claude-x")
    c = runner.resolve_agent_config({"engine": "codex", "key": "draft"})
    assert c["api_base"] == "" and c["api_key"] == ""
    assert "不兼容" in c["warn"]


def test_anthropic_hint_counts_as_compatible(both_clis):
    db.add_preset("relay", provider="", api_base="https://gate/apps/anthropic",
                  api_key="k", model="claude-x")
    c = runner.resolve_agent_config({"engine": "claude", "key": "draft"})
    assert c["api_base"] == "https://gate/apps/anthropic"
    assert c["warn"] == ""


# ---------------- 协议门本身 ----------------

@pytest.mark.parametrize("engine,provider,base,ok", [
    ("claude", "", "", True),
    ("claude", "anthropic", "https://x/api", True),
    ("claude", "openai", "https://x/v1", False),
    ("claude", "openai", "https://x/claudecode", True),
    ("claude", "", "https://x/tokenplan/personal", True),
    ("codex", "openai", "https://x/v1", True),
    ("codex", "anthropic", "https://x/api", False),
    ("codex", "", "", True),
])
def test_protocol_ok(engine, provider, base, ok):
    assert agents.protocol_ok(engine, provider, base) is ok


def test_codex_args_carry_reasoning_effort(monkeypatch, tmp_path):
    monkeypatch.setattr(db, "get_setting", lambda k, d="": {
        "reasoning_effort": "high", "codex_sandbox": "workspace-write"}.get(k, d))
    args = agents._codex_args(tmp_path, None, "gpt-5", "", "", "")
    joined = " ".join(args)
    assert 'model_reasoning_effort="high"' in joined
    assert "network_access=true" in joined
    assert "--skip-git-repo-check" in joined


def test_codex_args_omit_effort_when_auto(monkeypatch, tmp_path):
    monkeypatch.setattr(db, "get_setting", lambda k, d="": "")
    args = " ".join(agents._codex_args(tmp_path, None, "", "", "", ""))
    assert "model_reasoning_effort" not in args
    assert 'model="' not in args             # 没填模型就别越权指定


def test_provider_display_name_follows_the_brand_not_the_old_names(monkeypatch, tmp_path):
    args = " ".join(agents._codex_args(tmp_path, None, "", "https://k/v1", "k", ""))
    assert 'name="Jacquard"' in args
    assert "FLOWFORGE_API_KEY" in args       # 环境变量名是内部契约，改名要同步


def test_codex_defaults_to_the_responses_wire(monkeypatch, tmp_path):
    """本机装的 codex 0.154 里写着 `wire_api = "chat"` is no longer supported，
    默认值再留 chat，凡是配了端点的 codex 步骤都会在启动那一刻就失败。"""
    args = " ".join(agents._codex_args(tmp_path, None, "", "https://k/v1", "k", ""))
    assert 'wire_api="responses"' in args
    assert 'wire_api="chat"' not in args
    mine = " ".join(agents._codex_args(tmp_path, None, "", "https://k/v1", "k", "responses"))
    assert 'wire_api="responses"' in mine     # 显式填过的照原样发出去


# ==================== 权限模式（输入台那三档） ====================
# 枚举值直接沿用 claude 的 --permission-mode 取值，映射到 codex 时再翻译：
# 少造一层词，就少一处会写错的地方。claude 的完整枚举是
# acceptEdits / auto / bypassPermissions / manual / dontAsk / plan（本机 --help 实测），
# 我们只开放三家都能落地的三档 —— manual 要回调工具、codex exec 根本没有回通道。

def _modes(setting):
    return {
        "plan": ("--permission-mode plan", "read-only"),
        "acceptEdits": ("--permission-mode acceptEdits", "workspace-write"),
        "bypassPermissions": ("--permission-mode bypassPermissions", "danger-full-access"),
    }[setting]


def test_no_mode_picked_keeps_todays_behaviour(monkeypatch, tmp_path):
    """默认档必须一个字节都不改现有行为：claude 照旧 --dangerously-skip-permissions，
    codex 照旧读它自己的沙箱设置。新功能的起点是"没点就等于没看见"。"""
    monkeypatch.setattr(db, "get_setting", lambda k, d="": {
        "codex_sandbox": "workspace-write"}.get(k, d))
    cl = " ".join(agents._claude_args(tmp_path, None, "", False))
    cx = " ".join(agents._codex_args(tmp_path, None, "", "", "", ""))
    assert "--dangerously-skip-permissions" in cl
    assert "--permission-mode" not in cl
    assert "-s workspace-write" in cx


def test_each_mode_reaches_both_engines(monkeypatch, tmp_path):
    for mode in ("plan", "acceptEdits", "bypassPermissions"):
        cl_flag, cx_sandbox = _modes(mode)
        monkeypatch.setattr(db, "get_setting", lambda k, d="", m=mode: {
            "permission_mode": m, "codex_sandbox": "workspace-write"}.get(k, d))
        cl = " ".join(agents._claude_args(tmp_path, None, "", False))
        cx = " ".join(agents._codex_args(tmp_path, None, "", "", "", ""))
        assert cl_flag in cl, f"{mode} 没传给 claude：{cl}"
        assert "--dangerously-skip-permissions" not in cl, f"{mode} 下还在全放行"
        assert f"-s {cx_sandbox}" in cx, f"{mode} 没传给 codex：{cx}"


def test_codex_mode_overrides_the_stale_sandbox_setting(monkeypatch, tmp_path):
    """模式接管沙箱之后，旧的 codex_sandbox 存值只在"没选模式"时兜底 ——
    否则会出现"chip 显示计划模式、codex 其实全开"这种骗人的状态。"""
    monkeypatch.setattr(db, "get_setting", lambda k, d="": {
        "permission_mode": "plan", "codex_sandbox": "danger-full-access"}.get(k, d))
    cx = " ".join(agents._codex_args(tmp_path, None, "", "", "", ""))
    assert "-s read-only" in cx and "danger-full-access" not in cx


def test_unknown_or_deferred_mode_falls_back(monkeypatch, tmp_path):
    """manual（要回调工具）和任何乱填的值都退回默认档，不能拼出半截参数把 CLI 噎住。"""
    for bad in ("manual", "dontAsk", "auto", "", "yolo", "PLAN"):
        monkeypatch.setattr(db, "get_setting", lambda k, d="", b=bad: {
            "permission_mode": b, "codex_sandbox": "workspace-write"}.get(k, d))
        cl = " ".join(agents._claude_args(tmp_path, None, "", False))
        assert "--permission-mode" not in cl, f"{bad!r} 竟然被认下了"
        assert "--dangerously-skip-permissions" in cl
    assert agents.PERM_MODES == ("plan", "acceptEdits", "bypassPermissions")


def test_permission_mode_round_trips_and_validates(client):
    """设置页/输入台都走这条端点：值必须能存回来，且没开放的四档进不来。
    被拒时不能顺手把已存的值改掉 —— 校验要写在落盘之前。"""
    got = client.get("/api/agents").json()
    assert got["permission_mode"] == ""
    assert got["permission_modes"] == ["plan", "acceptEdits", "bypassPermissions"]
    assert client.post("/api/agents", json={"permission_mode": "plan"}).status_code == 200
    assert client.get("/api/agents").json()["permission_mode"] == "plan"
    for bad in ("manual", "dontAsk", "yolo", "PLAN"):
        assert client.post("/api/agents", json={"permission_mode": bad}).status_code == 400
        assert client.get("/api/agents").json()["permission_mode"] == "plan", f"{bad} 被拒却改掉了存值"
    assert client.post("/api/agents", json={"permission_mode": ""}).json()["permission_mode"] == ""


def test_every_child_process_launch_suppresses_the_console():
    r"""打包版是 loom.spec 的 console=False —— 一个没有控制台的 GUI 进程。
    它去起控制台子进程（npm 的 .cmd 垫片会被 _argv 包成 cmd.exe /c），Windows 就
    给它新建一个控制台窗口，于是"每次开软件都弹一个黑窗"：boot() 打 /api/agents，
    agents_status() 给两个引擎各跑一次 --version，所以是两次。

    坑在于 capture_output=True 只接管管道，**不抑制控制台分配**，看着像已经处理过了。
    实测抓到的调用参数就是 ['cmd.exe','/c','D:\npm-global\claude.CMD','--version']
    加 creationflags 未传。这里用 ast 点名每一个 subprocess.run / Popen，
    以后新加一处忘了带就会红。
    """
    tree = ast.parse(Path(agents.__file__).read_text(encoding="utf-8"))
    sites = [n for n in ast.walk(tree)
             if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
             and isinstance(n.func.value, ast.Name) and n.func.value.id == "subprocess"
             and n.func.attr in ("run", "Popen")]
    assert sites, "一个 subprocess 调用点都没找到，这条测试本身失效了"

    missing = [f"{s.func.attr}@line{s.lineno}" for s in sites
               if not any(k.arg == "creationflags" for k in s.keywords)]
    assert not missing, f"这些起进程的地方没关控制台，会弹黑窗：{missing}"

    for s in sites:
        cf = next(k for k in s.keywords if k.arg == "creationflags")
        assert isinstance(cf.value, ast.Name) and cf.value.id == "NO_WINDOW", (
            f"line {s.lineno}：creationflags 该用模块级 NO_WINDOW，"
            "别在调用点各写一套平台判断")
