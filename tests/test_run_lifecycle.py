# -*- coding: utf-8 -*-
"""跑一次真实子进程的完整生命周期：用假 CLI 顶替 claude / codex。

刻意走 subprocess 而不是打桩 Popen —— 要验的就是「行协议 → 状态机 →
落盘 → 事件总线 → 转录日志」这一整条链路，包括 Windows 下 .cmd 垫片。
"""
import json
import os
import stat
import sys
import time
from pathlib import Path

import pytest

from app import agents, db, runner

STUB = r'''
import json, sys, time
if "--version" in sys.argv:
    print("loom-stub 0.0.1"); sys.exit(0)
sys.stdin.read()                      # 提示词从 stdin 进来，读掉别堵管道
mode = "ok"
for a in sys.argv:
    if a.startswith("--stub-mode="):
        mode = a.split("=", 1)[1]
w = sys.stdout.write
w(json.dumps({"type": "system", "subtype": "init", "model": "stub-1",
              "tools": ["Read", "Write"]}) + "\n")
w(json.dumps({"type": "assistant", "message": {"content": [
    {"type": "tool_use", "name": "Write", "input": {"file_path": "draft.md"}}]}}) + "\n")
w(json.dumps({"type": "user", "message": {"content": [
    {"type": "tool_result", "content": "written"}]}}) + "\n")
if mode == "slow":
    # 先吐两段真正文，再每隔 50ms 一行 ping：够测试等到 delta，也够它按停止
    w(json.dumps({"type": "assistant", "message": {"content": [
        {"type": "text", "text": "第一段已经流出的正文"}]}}) + "\n")
    sys.stdout.flush()
    w(json.dumps({"type": "assistant", "message": {"content": [
        {"type": "text", "text": "第二段已经流出的正文"}]}}) + "\n")
    sys.stdout.flush()
    for _ in range(400):
        w(json.dumps({"type": "system", "subtype": "ping"}) + "\n")
        sys.stdout.flush()
        time.sleep(0.05)
    sys.exit(0)
if mode == "fail":
    w(json.dumps({"type": "system", "subtype": "api_retry", "attempt": 1,
                  "max_retries": 3, "error": "ConnectionRefused",
                  "retry_delay_ms": 1000}) + "\n")
    w(json.dumps({"type": "result", "is_error": True, "num_turns": 1,
                  "duration_ms": 420, "result": "连不上端点"}) + "\n")
else:
    w(json.dumps({"type": "assistant", "message": {"content": [
        {"type": "text", "text": "# 草稿\n桩产出的正文"}]}}) + "\n")
    w(json.dumps({"type": "result", "is_error": False, "num_turns": 2,
                  "duration_ms": 1400, "total_cost_usd": 0.0123,
                  "result": "# 草稿\n桩产出的正文"}) + "\n")
sys.stdout.flush()
'''


@pytest.fixture
def stub_cli(tmp_path):
    """生成一个假 CLI 并把 claude_cli 指过去；返回可注入的额外参数。"""
    script = tmp_path / "stub_agent.py"
    script.write_text(STUB, encoding="utf-8")
    if os.name == "nt":
        shim = tmp_path / "stub-claude.cmd"
        # 批处理按本机 ANSI 码页读，用 utf-8 写会把中文用户名路径解成乱码
        shim.write_bytes(
            ("@echo off\r\nset PYTHONIOENCODING=utf-8\r\n"
             f'"{sys.executable}" "{script}" %*\r\n').encode("mbcs"))
    else:
        shim = tmp_path / "stub-claude"
        shim.write_text(
            f'#!/bin/sh\nPYTHONIOENCODING=utf-8 exec "{sys.executable}" '
            f'"{script}" "$@"\n', encoding="utf-8")
        shim.chmod(shim.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP)
    db.set_setting("claude_cli", str(shim))
    db.set_setting("default_engine", "claude")
    agents.clear_bin_cache()
    yield str(shim)
    db.set_setting("claude_cli", "")
    agents.clear_bin_cache()


@pytest.fixture
def flow(dbsession):
    dbsession.create_pipeline("lifecycle-flow", label="生命周期",
                              steps=[{"key": "draft", "label": "起草", "out": "draft.md",
                                      "engine": "claude", "skill": ""}])
    yield "lifecycle-flow"
    dbsession.delete_pipeline("lifecycle-flow")


def _wait(run_id, timeout=60):
    deadline = time.time() + timeout
    while time.time() < deadline:
        r = db.get_run(run_id)
        if r and r["status"] not in ("running", "revising", "pending"):
            return r
        time.sleep(0.15)
    raise AssertionError(f"运行 {run_id} {timeout}s 还没收敛：{db.get_run(run_id)}")


def test_stub_binary_resolves(stub_cli):
    assert agents.resolve_binary("claude") == stub_cli


def test_happy_path_end_to_end(client, stub_cli, flow, workspaces):
    run = runner.start_run(flow, label="一次跑", brief="写点什么")
    done = _wait(run["id"])
    assert done["status"] == "done", done["error"]
    step = done["steps"][0]
    assert step["status"] == "done"
    assert step["meta"]["tools"] == 1 and step["meta"]["turns"] == 2
    assert step["meta"]["duration_ms"] == 1400
    assert step["meta"]["log"].endswith(".jsonl")
    assert step["engine_used"] == "claude"

    # 智能体只把正文打在回答里、没真落盘 —— runner 兜底代写，下游才有输入
    f = runner.workspace_dir(run['id']) / "draft.md"
    assert f.is_file() and "桩产出的正文" in f.read_text(encoding="utf-8")

    body = client.get(f"/api/runs/{run['id']}").json()
    assert "draft.md" in body["artifacts"]
    names = [x["name"] for x in body["logs"]]
    assert names == [step["meta"]["log"]]

    d = client.get(f"/api/runs/{run['id']}/logs/{names[0]}").json()
    parsed = [json.loads(x) for x in d["lines"]]
    assert parsed[0]["subtype"] == "init"
    assert parsed[-1]["type"] == "result"
    assert not d["truncated"]


def test_run_level_model_override_reaches_every_step(client, stub_cli, dbsession, workspaces):
    """下任务时选的模型覆盖每一步，规则和 run 级引擎那套一模一样。
    「留空 = 不覆盖」必须钉住：不然每次起跑都把编辑器里挑好的端点抹平。"""
    dbsession.create_pipeline("ovr-flow", label="覆盖", steps=[
        {"key": "a", "label": "A", "out": "a.md", "engine": "claude", "skill": "", "model": "步级A"},
        {"key": "b", "label": "B", "out": "b.md", "engine": "claude", "skill": "", "model": "步级B"}])
    r = client.post("/api/pipelines/ovr-flow/run",
                    json={"brief": "写", "model": "端点卡"}).json()["run"]
    assert [s["model"] for s in r["steps"]] == ["端点卡", "端点卡"]
    _wait(r["id"])
    r2 = client.post("/api/pipelines/ovr-flow/run", json={"brief": "写"}).json()["run"]
    assert [s["model"] for s in r2["steps"]] == ["步级A", "步级B"]
    _wait(r2["id"])
    dbsession.delete_pipeline("ovr-flow")


def test_failed_step_keeps_log(client, stub_cli, flow, monkeypatch, workspaces):
    monkeypatch.setattr(agents, "_claude_args",
                        lambda *a, **k: ["--stub-mode=fail"])
    run = runner.start_run(flow, label="会失败")
    done = _wait(run["id"])
    assert done["status"] == "failed"
    step = done["steps"][0]
    assert step["status"] == "failed"
    assert "连不上端点" in step["msg"]
    assert step["meta"]["log"], "失败步骤必须留下可诊断的转录"
    log = runner.workspace_dir(run['id']) / "_turn_logs" / step["meta"]["log"]
    assert "api_retry" in log.read_text(encoding="utf-8")
    # 失败时引擎的 final 是报错文本，不能当产物落盘给下一步
    assert not (runner.workspace_dir(run['id']) / "draft.md").exists()


def test_transcript_log_is_per_step_not_shared(stub_cli, dbsession, workspaces):
    dbsession.create_pipeline("two-step", label="两步", steps=[
        {"key": "a", "label": "A", "out": "a.md", "engine": "claude", "skill": ""},
        {"key": "b", "label": "B", "out": "b.md", "engine": "claude", "skill": ""}])
    run = runner.start_run("two-step", label="两步")
    done = _wait(run["id"])
    logs = [s["meta"]["log"] for s in done["steps"]]
    assert len(set(logs)) == 2, f"两步共用了同一份转录：{logs}"
    assert logs[0].startswith("01_a_") and logs[1].startswith("02_b_")
    dbsession.delete_pipeline("two-step")


def test_checkpoint_waits_then_resumes(stub_cli, dbsession, workspaces):
    dbsession.create_pipeline("gated", label="有闸", steps=[
        {"key": "a", "label": "A", "out": "a.md", "engine": "claude", "skill": "",
         "checkpoint": True},
        {"key": "b", "label": "B", "out": "b.md", "engine": "claude", "skill": ""}])
    run = runner.start_run("gated", label="带检查点")
    paused = _wait(run["id"])
    assert paused["status"] == "waiting", paused["status"]
    assert paused["steps"][0]["status"] == "done"
    assert paused["steps"][1]["status"] == "pending"
    runner.resume_run(run["id"])
    done = _wait(run["id"])
    assert done["status"] == "done"
    assert [s["status"] for s in done["steps"]] == ["done", "done"]
    dbsession.delete_pipeline("gated")


def test_auto_continue_skips_checkpoint(stub_cli, dbsession, workspaces):
    db.set_setting("auto_continue", "1")
    dbsession.create_pipeline("auto", label="全自动", steps=[
        {"key": "a", "label": "A", "out": "a.md", "engine": "claude", "skill": "",
         "checkpoint": True},
        {"key": "b", "label": "B", "out": "b.md", "engine": "claude", "skill": ""}])
    run = runner.start_run("auto", label="一次推到底")
    done = _wait(run["id"])
    assert done["status"] == "done", done["status"]
    assert done["steps"][1]["status"] == "done"
    db.set_setting("auto_continue", "0")
    dbsession.delete_pipeline("auto")


def test_retry_loop_gives_up_after_configured_attempts(stub_cli, dbsession, monkeypatch):
    db.set_setting("step_retry", "2")
    calls = {"n": 0}
    real = agents.run_agent

    def flaky(*a, **k):
        calls["n"] += 1
        return real(*a, **k)

    monkeypatch.setattr(agents, "run_agent", flaky)
    monkeypatch.setattr(agents, "_claude_args",
                        lambda *a, **k: ["--stub-mode=fail"])
    dbsession.create_pipeline("flaky", label="老失败", steps=[
        {"key": "a", "label": "A", "out": "a.md", "engine": "claude", "skill": ""}])
    run = runner.start_run("flaky", label="重试")
    done = _wait(run["id"])
    assert done["status"] == "failed"
    assert calls["n"] == 3, f"step_retry=2 应该一共 3 次，实际 {calls['n']}"
    db.set_setting("step_retry", "0")
    dbsession.delete_pipeline("flaky")


# ==================== 局部修订的并发守卫 ====================
# 这三条都必须在真的起线程之前就 raise，所以用例故意让它们在守卫处返回。

def _run_with(dbsession, run_id, steps, status="done"):
    dbsession.create_run(run_id, "auto-workflow", "t", steps)
    dbsession.update_run(run_id, status=status, steps=steps)


def test_revise_refuses_while_the_pipeline_is_running(dbsession):
    """修订线程和流水线线程各持一份 steps 整体回写同一行 JSON，
    同跑一步就是后写覆盖前写；codex 那路还要抢工作区的 AGENTS.md。"""
    _run_with(dbsession, "run-rev-run", [{"key": "a", "label": "A", "status": "pending", "out": "a.md"}], status="running")
    try:
        with pytest.raises(ValueError):
            runner.revise_step("run-rev-run", 0, "改一下")
    finally:
        # 整库是会话级共享的：这条 running 留在那儿，后面 test_updater 里
        # 那条「源码运行拒绝安装」就会被 count_active_runs 顶成 409，
        # 红不红全看文件顺序。
        dbsession.delete_run("run-rev-run")


def test_revise_refuses_a_second_concurrent_revision(dbsession):
    _run_with(dbsession, "run-rev-two", [
        {"key": "a", "label": "A", "status": "revising", "out": "a.md"},
        {"key": "b", "label": "B", "status": "done", "out": "b.md"}])
    with pytest.raises(ValueError):
        runner.revise_step("run-rev-two", 1, "改一下")


def test_revise_clears_a_stale_cancel_flag(dbsession):
    """cancel_run 只往 _CANCEL 里加，清它的活儿原先只在 _run_thread 的 finally。
    取消过一次再从那条 run 上发起修订，agents 一进来就当被取消，之后每次都秒失败。"""
    _run_with(dbsession, "run-rev-cancel", [{"key": "a", "label": "A", "status": "done", "out": ""}])
    runner._CANCEL.add("run-rev-cancel")
    with pytest.raises(ValueError):
        runner.revise_step("run-rev-cancel", 0, "改一下")
    assert "run-rev-cancel" not in runner._CANCEL


# ==================== 选工作文件夹（只换智能体的 cwd） ====================

def _start(client, flow, body):
    return client.post(f"/api/pipelines/{flow}/run", json=body)


def test_run_workdir_becomes_the_agent_cwd_only(client, stub_cli, flow,
                                               workspaces, tmp_path):
    """Loom 自己的三样东西（转录、步骤产物、给 claude 的系统提示文件）仍旧写在
    派生工作区里 —— 用户选的那个目录一个字节都不该被我们动过。"""
    import os
    d = tmp_path / "我的工程"
    d.mkdir()
    r = _start(client, flow, {"brief": "写点什么", "workdir": str(d)})
    assert r.status_code == 200, r.text
    run = r.json()["run"]
    assert os.path.normcase(run["workdir"]) == os.path.normcase(str(d))
    assert run["workspace"] == runner._ws_path(run["id"]).name, \
        "库里的派生目录名必须和磁盘上真存在的那个一致"
    done = _wait(run["id"])
    assert done["status"] == "done", done["error"]
    assert list(d.iterdir()) == [], "往用户目录里写了东西：" + str(list(d.iterdir()))
    assert (runner._ws_path(run["id"]) / "_turn_logs").is_dir()


def test_run_workdir_must_be_an_existing_absolute_directory(
        client, stub_cli, flow, workspaces, tmp_path):
    d = tmp_path / "ok"
    d.mkdir()
    ok = _start(client, flow, {"brief": "x", "workdir": str(d)})
    assert ok.status_code == 200, ok.text
    _wait(ok.json()["run"]["id"])
    for bad in ["", "  ", "relative/dir", str(d / "没有这个子目录"), str(tmp_path / "file.md")]:
        (tmp_path / "file.md").write_text("文件不是目录", encoding="utf-8")
        r = _start(client, flow, {"brief": "x", "workdir": bad})
        if bad:
            assert r.status_code == 400, f"{bad!r} 竟然收下了"
            assert "文件夹" in r.json()["detail"] or "目录" in r.json()["detail"]
        else:
            assert r.status_code == 200, "留空=不选，必须照常能跑"
            _wait(r.json()["run"]["id"])


def test_codex_refuses_a_run_with_a_custom_workdir(client, dbsession,
                                                   workspaces, tmp_path):
    """codex 的项目指令是从 cwd 里读 AGENTS.md 的。换成用户的目录，要么我们的系统提示
    它一个字都读不到（静默没指令），要么把人家仓库里的 AGENTS.md 覆盖了 —— 两个都不接受，
    所以这个组合在起跑前就拒，等引擎解析那一步的兜底也没留到以后才补。"""
    d = tmp_path / "工程"
    d.mkdir()
    dbsession.create_pipeline("cx-flow", label="覆盖用例", steps=[
        {"key": "a", "label": "A", "out": "", "engine": "codex", "skill": ""}])
    r = _start(client, "cx-flow", {"brief": "x", "workdir": str(d)})
    assert r.status_code == 400, r.text
    assert "codex" in r.json()["detail"]
    assert not d.exists() or list(d.iterdir()) == []
    dbsession.delete_pipeline("cx-flow")   # 库是共享的，别把这条流程漏给"出厂为空"那条断言


def test_a_run_with_a_workdir_pins_the_engine_it_started_with(
        client, stub_cli, dbsession, workspaces, tmp_path):
    """上一条测的是"起跑那一刻拒得对"，这条测的是**之后**：步级 engine 留空时
    resolve_engine 每一步都重新读设置里的 default_engine，于是起跑通过之后跑到一半
    去设置里把默认换成 codex，后半条 run 就带着用户的工作文件夹跑起来了 ——
    正是起跑前拒掉的那个组合。选了工作文件夹就得把引擎钉进这一步的快照。"""
    # codex 也指到那个桩上：万一钉不住，这里跑的也是桩，
    # 不会去碰本机真装的 codex（测试不该花用户的额度）。
    # settings 有会话级的还原（conftest 的 _restore_settings），这里不用自己擦。
    db.set_setting("codex_cli", stub_cli)
    agents.clear_bin_cache()
    d = tmp_path / "工程"
    d.mkdir()
    dbsession.create_pipeline("pin-flow", label="钉住", steps=[
        {"key": "a", "label": "A", "out": "", "engine": "", "skill": "",
         "checkpoint": True},
        {"key": "b", "label": "B", "out": "", "engine": "", "skill": ""}])
    try:
        r = _start(client, "pin-flow", {"brief": "x", "workdir": str(d)})
        assert r.status_code == 200, r.text
        run = r.json()["run"]
        assert [s["engine"] for s in run["steps"]] == ["claude", "claude"], \
            "选了工作文件夹却没把解析出的引擎钉进步骤快照"
        _wait(run["id"])                      # 第一步跑完，停在检查点
        db.set_setting("default_engine", "codex")
        agents.clear_bin_cache()
        runner.resume_run(run["id"])
        done = _wait(run["id"])
        assert done["status"] == "done", done["error"]
        assert done["steps"][1]["engine_used"] == "claude", \
            "中途换默认引擎，后半条 run 被拐去 codex 了"
    finally:
        agents.clear_bin_cache()
        dbsession.delete_pipeline("pin-flow")


def test_deleting_a_run_never_touches_the_chosen_folder(client, stub_cli, flow,
                                                        workspaces, tmp_path):
    """delete_run 里那句 rmtree 吃的是派生工作区。这条钉死它别顺手扩到用户目录：
    删一条运行记录，不该变成删掉人家整个工程。"""
    d = tmp_path / "工程"
    d.mkdir()
    keep = d / "keep.md"
    keep.write_text("# 用户的文件\n别删\n", encoding="utf-8")
    run = _start(client, flow, {"brief": "写", "workdir": str(d)}).json()["run"]
    _wait(run["id"])
    assert client.delete(f"/api/runs/{run['id']}").status_code == 200
    assert keep.is_file() and keep.read_text(encoding="utf-8").startswith("# 用户的文件")
    assert [p.name for p in d.iterdir()] == ["keep.md"]


def test_startup_reconcile_clears_zombie_running_rows(dbsession):
    """running / revising 是线程持有型状态：只有那个跑任务的线程会把它改成终态。
    进程被杀 / 断电 / 更新器 os._exit(0) 之后这一行永远停在 running，而重启后没有
    任何线程会来救它 —— 侧栏永远转圈、"停止"改了库也没人读、重跑被"运行中"挡住，
    而 count_active_runs() 一直把它算成活跃，**应用内更新从此永久 409**。
    """
    for rid, st in (("zom-r", "running"), ("zom-v", "revising"), ("zom-w", "waiting")):
        dbsession.create_run(rid, "zombie-pipeline", rid)
        dbsession.update_run(rid, status=st)
    # 整个会话共用一个库，别的模块可能留下自己的活跃行 —— 所以断言增量而不是绝对值，
    # 并且只认我们自己那三行。
    before = dbsession.count_active_runs()
    assert before >= 3
    assert dbsession.reconcile_interrupted_runs() >= 2
    assert dbsession.get_run("zom-r")["status"] == "failed"
    assert dbsession.get_run("zom-v")["status"] == "failed"
    assert "中断" in (dbsession.get_run("zom-r")["error"] or "")
    assert dbsession.get_run("zom-w")["status"] == "waiting", \
        "停在检查点是可跨重启恢复的状态，不能一起抹掉"
    assert dbsession.count_active_runs() <= before - 2
    assert dbsession.reconcile_interrupted_runs() == 0, "第二次必须是 0，别每次启动都改一遍库"
    for rid in ("zom-r", "zom-v", "zom-w"):
        dbsession.delete_run(rid)


def test_cancel_on_a_zombie_running_row_actually_lands_in_the_db(dbsession):
    """以前 cancel_run 只判 waiting，对 running 行只往内存 _CANCEL 塞一个 id 就当成功了，
    而重启后没有任何线程在读那个集合 —— 前端照样 toast「已取消」，库里还是 running。"""
    dbsession.create_run("zom-c", "zombie-pipeline", "僵尸")
    dbsession.update_run("zom-c", status="running")
    runner._BUSES.pop("zom-c", None)
    assert runner.cancel_run("zom-c")["status"] == "cancelled"
    assert dbsession.get_run("zom-c")["status"] == "cancelled"
    dbsession.delete_run("zom-c")


def test_cancel_does_not_force_a_live_run_out_of_running(dbsession):
    """反方向也要钉住：总线还活着说明真有线程在跑，那时只能等它自己收尾，
    强行改库会让那个线程后面把状态又写回去。"""
    class _LiveBus:
        closed = False

        def publish(self, ev):
            pass

    dbsession.create_run("live-c", "zombie-pipeline", "在跑")
    dbsession.update_run("live-c", status="running")
    runner._BUSES["live-c"] = _LiveBus()
    try:
        assert runner.cancel_run("live-c")["status"] == "running"
    finally:
        runner._BUSES.pop("zom-c", None)
        runner._CANCEL.discard("zom-c")
        dbsession.delete_run("zom-c")


def test_stopping_mid_step_keeps_the_streamed_text(stub_cli, flow, monkeypatch, workspaces):
    """十分钟流出来的正文不能跟着一次停止一起蒸发。"""
    monkeypatch.setattr(agents, "_claude_args", lambda *a, **k: ["--stub-mode=slow"])
    run = runner.start_run(flow, label="跑到一半按停止")
    bus = runner.bus_for(run["id"])
    deadline = time.time() + 30
    while not any(e.get("type") == "delta" for e in bus.history):
        if time.time() > deadline:
            raise AssertionError("桩一个字都没流出来，这条测试什么也没验")
        time.sleep(0.05)
    runner.cancel_run(run["id"])
    done = _wait(run["id"])
    assert done["status"] == "cancelled", done["status"]

    ws = runner.workspace_dir(run["id"])
    part = ws / "partial-draft.md"
    assert part.is_file(), "按停止把已经流出来的正文连同调用栈一起扔了"
    body = part.read_text(encoding="utf-8")
    assert "第一段" in body and "第二段" in body, body
    assert "ping" not in body
    # 残包绝不能顶替正式产物名：下游那一步会把它当完整文件读
    assert not (ws / "draft.md").exists()
    line = (done["steps"][0].get("trace") or [])[-1]
    assert line["kind"] == "note" and "partial-draft.md" in line["text"], line
    # 这份正文还得看得见：产物品类按后缀认，名字不带 .md 就等于没有入口
    arts = runner.read_artifacts(done)
    assert "partial-draft.md" in arts, sorted(arts)


# ==================== 单条 run 的 token 预算线 ====================

def _fixed_tokens_agent(real, per_call):
    """给每一步钉一个固定 token 数 —— 预算判的是累计量，没必要为了测试真烧配额。
    注：`run_agent` 返回的是 res，步骤上的 meta.tokens 由 _run_step 从 res["tokens"] 搬。"""
    def wrapped(*a, **k):
        r = real(*a, **k)
        r["tokens"] = {"total": per_call}
        return r
    return wrapped


def test_budget_line_pauses_before_the_next_step(stub_cli, dbsession, monkeypatch):
    dbsession.create_pipeline("budgeted", label="有预算", steps=[
        {"key": "a", "label": "A", "out": "a.md", "engine": "claude", "skill": ""},
        {"key": "b", "label": "B", "out": "b.md", "engine": "claude", "skill": ""},
        {"key": "c", "label": "C", "out": "c.md", "engine": "claude", "skill": ""}])
    db.set_setting("run_token_cap", "1500")
    monkeypatch.setattr(agents, "run_agent", _fixed_tokens_agent(agents.run_agent, 1000))
    run = runner.start_run("budgeted", label="预算")
    try:
        paused = _wait(run["id"])
        assert paused["status"] == "waiting", paused["status"]
        assert paused["waiting_reason"] == "budget"
        assert [s["status"] for s in paused["steps"]] == ["done", "done", "pending"]
        assert paused["cur_step"] == 2, "停在第 3 步之前，不是已经跑掉第 3 步"
        runner.resume_run(run["id"])
        done = _wait(run["id"])
        assert done["status"] == "done"
        assert runner.tokens_spent(done["steps"]) == 3000
    finally:
        db.set_setting("run_token_cap", "0")
        dbsession.delete_pipeline("budgeted")


def test_budget_never_pauses_on_the_last_step(stub_cli, dbsession, monkeypatch):
    """最后一步跑完就该是 done：在它之后再挂一个"等人点继续"是纯粹的骚扰。"""
    dbsession.create_pipeline("budget-last", label="末步", steps=[
        {"key": "a", "label": "A", "out": "a.md", "engine": "claude", "skill": ""}])
    db.set_setting("run_token_cap", "1")
    monkeypatch.setattr(agents, "run_agent", _fixed_tokens_agent(agents.run_agent, 5000))
    run = runner.start_run("budget-last", label="末步")
    try:
        done = _wait(run["id"])
        assert done["status"] == "done", done["status"]
        assert runner.tokens_spent(done["steps"]) == 5000
    finally:
        db.set_setting("run_token_cap", "0")
        dbsession.delete_pipeline("budget-last")


def test_tokens_spent_follows_the_stats_page_definition():
    steps = [{"meta": {"tokens": {"total": 10}}},
             {"meta": {"tokens": {"in": 3, "out": 4, "cache_read": 2, "cache_write": 1}}},
             {"meta": {}}, {}, None]
    assert runner.tokens_spent(steps) == 20


def test_tokens_spent_leaves_reasoning_out_of_the_total():
    """统计页那段 SQL 没把 reasoning 计进 total，这里也必须不算 ——
    两处口径不一致时，预算线和用户看到的数字会互相打脸。"""
    assert runner.tokens_spent([{"meta": {"tokens": {"reason": 999}}}]) == 0


def test_run_token_cap_falls_back_to_unlimited_on_garbage(dbsession):
    for bad in ("abc", "", "-5", str(agents._RUN_CAP_MAX + 1), "1.5"):
        db.set_setting("run_token_cap", bad)
        assert agents.run_token_cap() == 0, f"脏值 {bad!r} 被当成了预算"
    db.set_setting("run_token_cap", "200000")
    assert agents.run_token_cap() == 200000


def test_budget_setting_is_validated_at_the_door(client):
    assert client.post("/api/agents", json={"run_token_cap": "abc"}).status_code == 400
    assert client.post("/api/agents", json={"run_token_cap": "-1"}).status_code == 400
    r = client.post("/api/agents", json={"run_token_cap": "50000"})
    assert r.status_code == 200 and r.json()["run_token_cap"] == "50000"
    assert "50000" in [str(x) for x in r.json()["run_token_caps"]]
