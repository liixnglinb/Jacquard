# -*- coding: utf-8 -*-
"""流程 + 技能打包导出 / 导入。

存在的理由：`/export` 那份 JSON 只带技能**名字**，别人导进去建得成、跑到那一步
才发现无正文可用。这一对端点要守住的正是"分享出去的东西必须跑得起来"，
同时不能把外部（claude / codex 目录里的）技能抄成我们的快照。
"""
import io
import json
import zipfile

import pytest

from app import db, paths

BODY = "---\nname: {n}\n---\n\n# {t}\n\n正文一段。"


def _mk_skill(name, text=None, attachment=None):
    d = paths.USER_SKILLS_DIR / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "SKILL.md").write_text(text if text is not None else BODY.format(n=name, t=name),
                                encoding="utf-8")
    if attachment:
        (d / "ref.md").write_text(attachment, encoding="utf-8")
    return d


def _rm_skill(name):
    import shutil
    shutil.rmtree(paths.USER_SKILLS_DIR / name, ignore_errors=True)


def _mk_pipeline(client, name, steps):
    r = client.post("/api/pipelines", json={"name": name, "label": name, "steps": steps})
    assert r.status_code == 200, r.text
    return r.json()


def _step(key, skill, src=""):
    return {"key": key, "label": key, "skill": skill, "skill_src": src,
            "out": key + ".md", "role": "executor"}


def _bundle(client, name):
    r = client.get(f"/api/pipelines/{name}/bundle")
    assert r.status_code == 200, r.text
    return r.content


def _unzip(data):
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        return {i.filename: z.read(i.filename) for i in z.infolist() if not i.is_dir()}


@pytest.fixture
def scene(client):
    _mk_skill("bundle-alpha", attachment="附表")
    _mk_skill("bundle-beta")
    _mk_pipeline(client, "bundle-flow", [_step("s1", "bundle-alpha"),
                                         _step("s2", "bundle-beta")])
    yield
    client.delete("/api/pipelines/bundle-flow")
    client.delete("/api/pipelines/bundle-flow-copy")
    _rm_skill("bundle-alpha")
    _rm_skill("bundle-beta")


def test_bundle_carries_the_flow_and_its_own_skills(client, scene):
    members = _unzip(_bundle(client, "bundle-flow"))
    assert "loom-pipeline.json" in members
    assert b"bundle-alpha" in members["skills/bundle-alpha/SKILL.md"]
    assert members["skills/bundle-alpha/ref.md"] == "附表".encode("utf-8")
    assert "skills/bundle-beta/SKILL.md" in members
    j = json.loads(members["loom-pipeline.json"])
    assert [s["key"] for s in j["steps"]] == ["s1", "s2"]
    assert "id" not in j and "created_at" not in j


def test_external_skill_is_referenced_not_copied(client, scene):
    """skill_src=claude 的那步引用的是 CLI 自己目录里的技能，抄进包=冻成快照。"""
    _mk_pipeline(client, "bundle-ext", [_step("s1", "claude-native-skill", src="claude"),
                                        _step("s2", "bundle-beta")])
    members = _unzip(_bundle(client, "bundle-ext"))
    assert not any(k.startswith("skills/claude-native-skill") for k in members)
    assert "skills/bundle-beta/SKILL.md" in members
    client.delete("/api/pipelines/bundle-ext")


def test_space_separated_extra_skills_all_get_packed(client, scene):
    _mk_skill("bundle-gamma")
    _mk_pipeline(client, "bundle-multi", [_step("s1", "bundle-alpha bundle-gamma")])
    members = _unzip(_bundle(client, "bundle-multi"))
    assert "skills/bundle-alpha/SKILL.md" in members
    assert "skills/bundle-gamma/SKILL.md" in members
    client.delete("/api/pipelines/bundle-multi")
    _rm_skill("bundle-gamma")


def test_roundtrip_rebuilds_a_deleted_flow(client, scene):
    data = _bundle(client, "bundle-flow")
    client.delete("/api/pipelines/bundle-flow")
    _rm_skill("bundle-alpha")
    _rm_skill("bundle-beta")
    assert db.get_pipeline("bundle-flow") is None
    r = client.post("/api/pipelines/import-bundle",
                    files={"file": ("loom-bundle-flow-bundle.zip", data, "application/zip")})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["name"] == "bundle-flow" and d["steps"] == 2
    assert sorted(d["skills_added"]) == ["bundle-alpha", "bundle-beta"]
    p = db.get_pipeline("bundle-flow")
    assert [s["key"] for s in p["steps"]] == ["s1", "s2"]
    assert (paths.USER_SKILLS_DIR / "bundle-alpha" / "ref.md").read_text(
        encoding="utf-8") == "附表"
    client.delete("/api/pipelines/bundle-flow")


def test_existing_skill_is_never_overwritten(client, scene):
    data = _bundle(client, "bundle-flow")
    mine = BODY.format(n="bundle-alpha", t="我自己改过的")
    (paths.USER_SKILLS_DIR / "bundle-alpha" / "SKILL.md").write_text(mine, encoding="utf-8")
    _rm_skill("bundle-beta")      # 只缺一个：另一个（我改过的）必须原样留着
    client.delete("/api/pipelines/bundle-flow")
    r = client.post("/api/pipelines/import-bundle",
                    files={"file": ("x.zip", data, "application/zip")})
    d = r.json()
    assert d["skills_added"] == ["bundle-beta"]
    assert d["skills_skipped"] == ["bundle-alpha"]
    assert (paths.USER_SKILLS_DIR / "bundle-alpha" / "SKILL.md").read_text(
        encoding="utf-8") == mine
    client.delete("/api/pipelines/bundle-flow")


def test_name_clash_renames_instead_of_touching_the_original(client, scene):
    data = _bundle(client, "bundle-flow")
    r = client.post("/api/pipelines/import-bundle",
                    files={"file": ("x.zip", data, "application/zip")})
    d = r.json()
    assert d["name"] == "bundle-flow-copy"
    assert db.get_pipeline("bundle-flow")["label"] == "bundle-flow"
    assert db.get_pipeline("bundle-flow-copy")["label"] == "bundle-flow copy"


def test_second_clash_bumps_the_suffix(client, scene):
    data = _bundle(client, "bundle-flow")
    client.post("/api/pipelines/import-bundle", files={"file": ("x.zip", data, "application/zip")})
    r = client.post("/api/pipelines/import-bundle",
                    files={"file": ("x.zip", data, "application/zip")})
    assert r.json()["name"] == "bundle-flow-copy2"
    client.delete("/api/pipelines/bundle-flow-copy")
    client.delete("/api/pipelines/bundle-flow-copy2")


def test_rejects_non_zip_and_missing_manifest(client, scene):
    r = client.post("/api/pipelines/import-bundle",
                    files={"file": ("x.zip", b"not a zip at all", "application/zip")})
    assert r.status_code == 400 and "zip" in r.json()["detail"]
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("readme.txt", "空包")
    r = client.post("/api/pipelines/import-bundle",
                    files={"file": ("y.zip", buf.getvalue(), "application/zip")})
    assert r.status_code == 400 and "loom-pipeline.json" in r.json()["detail"]


def test_rejects_a_flow_without_valid_steps(client, scene):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("loom-pipeline.json", json.dumps({"name": "bundle-bad", "steps": []}))
    r = client.post("/api/pipelines/import-bundle",
                    files={"file": ("z.zip", buf.getvalue(), "application/zip")})
    assert r.status_code == 400


def test_traversal_member_never_lands_on_disk(client, scene):
    """包里塞 skills/x/../../evil.txt：只能被丢掉，不能写到技能目录外面。"""
    buf = io.BytesIO()
    body = {"name": "bundle-evil", "steps": [_step("s1", "bundle-evil")] }
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("loom-pipeline.json", json.dumps(body))
        z.writestr("skills/bundle-evil/SKILL.md", BODY.format(n="bundle-evil", t=" evil"))
        z.writestr("skills/bundle-evil/../../evil.txt", "越界")
    data = buf.getvalue()
    r = client.post("/api/pipelines/import-bundle",
                    files={"file": ("e.zip", data, "application/zip")})
    assert r.status_code == 200, r.text
    assert (paths.USER_SKILLS_DIR / "bundle-evil" / "SKILL.md").exists()
    assert not (paths.DATA_DIR / "evil.txt").exists()
    assert not (paths.USER_SKILLS_DIR.parent / "evil.txt").exists()
    client.delete("/api/pipelines/bundle-evil")
    _rm_skill("bundle-evil")


def test_bundle_export_is_a_download_attachment(client, scene):
    r = client.get("/api/pipelines/bundle-flow/bundle")
    assert "attachment" in r.headers.get("content-disposition", "")
    assert r.headers.get("content-type", "").startswith("application/zip")
    assert r.status_code == 200


def test_missing_skill_still_exports_the_flow(client, scene):
    """步骤引用的技能被删过：包照发（分享的是流程，收件人不该因为你这边的洞收不到）。"""
    _mk_pipeline(client, "bundle-hole", [_step("s1", "no-such-skill")])
    members = _unzip(_bundle(client, "bundle-hole"))
    assert "loom-pipeline.json" in members
    assert not any(k.startswith("skills/") for k in members)
    client.delete("/api/pipelines/bundle-hole")
