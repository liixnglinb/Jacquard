# -*- coding: utf-8 -*-
"""工作区文件读口的越界防护：产物下载与转录日志共用一套 resolve + 前缀校验。"""
import pytest



@pytest.fixture
def run_id(dbsession, workspaces):
    rid = "run-guardtest01"
    dbsession.create_run(rid, "guard-flow", label="守卫用例", steps=[{"key": "a", "label": "A"}])
    ws = workspaces / rid
    ws.mkdir(parents=True, exist_ok=True)
    (ws / "out.md").write_text("# 产物\n正文", encoding="utf-8")
    logs = ws / "_turn_logs"
    logs.mkdir(exist_ok=True)
    (logs / "01_a_120000.jsonl").write_text(
        '{"type":"system","subtype":"init","model":"stub"}\n'
        '{"type":"result","is_error":false,"num_turns":1}\n', encoding="utf-8")
    yield rid
    dbsession.delete_run(rid)


def test_artifact_download_ok(client, run_id):
    r = client.get(f"/api/runs/{run_id}/artifacts/out.md")
    assert r.status_code == 200
    assert "产物" in r.text


@pytest.mark.parametrize("fname", [
    "../../db/flowforge.db",
    "..%2F..%2Fdb%2Fflowforge.db",
    "%2e%2e%2f%2e%2e%2fsettings.json",
    "C:/Windows/win.ini",
    "/etc/passwd",
])
def test_artifact_download_cannot_escape(client, run_id, fname):
    r = client.get(f"/api/runs/{run_id}/artifacts/{fname}")
    assert r.status_code in (400, 404), f"{fname} 居然返回了 {r.status_code}"
    assert b"SQLite format" not in r.content


@pytest.mark.parametrize("rel", [
    "_step_system.txt", "AGENTS.md", "_turn_logs/01_a_120000.jsonl",
])
def test_artifact_download_hides_internals(client, run_id, workspaces, rel):
    """产物清单早就不列这些了，下载口却是照单全收 —— 直接在地址栏敲
    /api/runs/<id>/artifacts/_step_system.txt 就能把本步注入的系统提示词
    （里面有用户的项目内容）和引擎原始转录整份拿走。清单挡过的，下载也得挡。"""
    p = workspaces / run_id / rel
    made = not p.exists()
    if made:
        p.write_text("ENGINE-ONLY-CONTENT", encoding="utf-8")
    r = client.get(f"/api/runs/{run_id}/artifacts/{rel}")
    assert r.status_code in (400, 404), f"{rel} 居然 {r.status_code}"
    assert b"ENGINE-ONLY" not in r.content
    if made:
        p.unlink()


def test_logs_listing(client, run_id):
    d = client.get(f"/api/runs/{run_id}/logs").json()
    assert [x["name"] for x in d["logs"]] == ["01_a_120000.jsonl"]
    assert d["logs"][0]["bytes"] > 0 and "modified" in d["logs"][0]


def test_log_detail_returns_lines(client, run_id):
    d = client.get(f"/api/runs/{run_id}/logs/01_a_120000.jsonl").json()
    assert len(d["lines"]) == 2
    assert d["truncated"] is False and d["bytes"] > 0


def test_log_run_scoped(client, run_id, dbsession, workspaces):
    """另一个运行的同名日志不能被串读。"""
    other = "run-guardtest02"
    dbsession.create_run(other, "guard-flow", steps=[])
    (workspaces / other / "_turn_logs").mkdir(parents=True, exist_ok=True)
    assert client.get(f"/api/runs/{other}/logs/01_a_120000.jsonl").status_code == 404
    dbsession.delete_run(other)


@pytest.mark.parametrize("name,code", [
    # 带斜杠的在路由层就匹配不上（{name} 不含 path），等于天然挡掉目录穿越
    ("..%2F..%2Fdb%2Fflowforge.db", 404),
    ("%2e%2e%2fsettings", 404),
    ("sub%2Fdeep.jsonl", 404),
    ("01_a_120000.txt", 400),         # 后缀不对：文件名合法但不是转录
    ("..flowforge.db", 400),
    ("missing.jsonl", 404),
])
def test_log_name_validated(client, run_id, name, code):
    assert client.get(f"/api/runs/{run_id}/logs/{name}").status_code == code


def test_log_of_unknown_run(client):
    assert client.get("/api/runs/run-nope000000/logs").status_code == 404
    assert client.get("/api/runs/run-nope000000/logs/a.jsonl").status_code == 404


def test_log_tail_truncates(client, run_id, workspaces):
    big = workspaces / run_id / "_turn_logs" / "big.jsonl"
    big.write_text("x" * 300 + "\n" + ('{"type":"result"}\n' * 900), encoding="utf-8")
    d = client.get(f"/api/runs/{run_id}/logs/big.jsonl?lines=50").json()
    assert len(d["lines"]) <= 50
    assert d["dropped"] > 0
    assert d["truncated"] is False          # 300B 远不到截断阈值


def test_list_workspace_hides_internals(client, run_id):
    files = client.get(f"/api/runs/{run_id}/files").json()["files"]
    paths = [f["path"] for f in files]
    assert "out.md" in paths
    assert not any(p.startswith("_") for p in paths), f"内部文件漏进产物清单：{paths}"


# ---------------- 工作区实时预览 ----------------

def test_list_workspace_carries_mtime_and_kind(client, run_id):
    """前端靠 mtime 排"刚写入"、靠 kind 决定就地渲染还是给下载，
    少一个字段面板就静默退化，所以钉住形状。"""
    f = client.get(f"/api/runs/{run_id}/files").json()["files"][0]
    assert set(f) == {"path", "bytes", "mtime", "kind"}, sorted(f)
    assert isinstance(f["mtime"], int) and f["mtime"] > 0
    assert f["kind"] == "text"


def test_file_preview_returns_text(client, run_id):
    d = client.get(f"/api/runs/{run_id}/files/out.md").json()
    assert d["kind"] == "text" and d["truncated"] is False
    assert "产物" in d["text"]


def test_file_preview_classifies_by_extension(client, run_id, workspaces):
    ws = workspaces / run_id
    (ws / "fig.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 40)
    (ws / "paper.docx").write_bytes(b"PK\x03\x04" + b"0" * 40)
    (ws / "data.xlsx").write_bytes(b"PK\x03\x04" + b"0" * 40)
    kinds = {f["path"]: f["kind"] for f in client.get(f"/api/runs/{run_id}/files").json()["files"]}
    assert kinds["fig.png"] == "image" and kinds["paper.docx"] == "office"
    assert kinds["data.xlsx"] == "binary"
    # office 走分镜预览，但原始正文一律不给；这枚假 docx 不是有效包，只报错不报内容
    d = client.get(f"/api/runs/{run_id}/files/paper.docx").json()
    assert d["kind"] == "office" and d["text"] == "" and d["bytes"] > 0
    assert d["office"]["error"] and d["office"]["slides"] == []
    for p in ("fig.png", "paper.docx", "data.xlsx"):
        (ws / p).unlink()


@pytest.mark.parametrize("rel", [
    "../../db/flowforge.db", "..%2F..%2Fsettings", "/etc/passwd", "C:/Windows/win.ini",
    "nope.md", "_turn_logs/01_a_120000.jsonl",
])
def test_file_preview_cannot_reach_outside(client, run_id, rel):
    """内部转录不在清单里，直接点名也不该给 —— 面板只给清单上有的东西。"""
    r = client.get(f"/api/runs/{run_id}/files/{rel}")
    assert r.status_code in (400, 404), f"{rel} 居然 {r.status_code}"
    assert b"SQLite format" not in r.content


def test_preview_truncation_flag(client, run_id, workspaces):
    from app import runner
    p = workspaces / run_id / "big.md"
    p.write_text("字" * 300_000, encoding="utf-8")
    d = runner.read_workspace_file(run_id, "big.md", max_bytes=1000)
    assert d["truncated"] is True
    assert len(d["text"].encode("utf-8")) <= 1000
    p.unlink()


def test_artifacts_are_served_inline(client, run_id):
    """图片 / PDF 要能在预览面板里直接显示；下载靠 <a download>，不靠 attachment。"""
    cd = client.get(f"/api/runs/{run_id}/artifacts/out.md").headers["content-disposition"]
    assert cd.startswith("inline"), cd


def test_reveal_only_opens_a_real_run(client, run_id):
    assert client.post("/api/reveal", params={"which": "run", "run_id": "run-nope000000"}).status_code == 404
    assert client.post("/api/reveal", params={"which": "run", "run_id": run_id,
                                              "file": "../../db"}).status_code == 404
