# -*- coding: utf-8 -*-
"""一次运行的产物打包下载。

这条链的底线是"打包不能比逐个下载更松"：内部文件（引擎原始转录、本次注入的系统
提示词）在 /artifacts 清单里就没有，直接点名也取不到，那打包时同样一个字都不许进。
"""
import io
import os
import zipfile

import pytest

from app import db, paths, runner

RID = "run-bundle-test"


@pytest.fixture
def ws(client):
    db.delete_run(RID)
    db.create_run(RID, "测试流程", "产物打包", steps=[{"key": "s1", "label": "步骤一"}])
    d = runner.workspace_dir(RID)
    (d / "out").mkdir(parents=True, exist_ok=True)
    (d / "out" / "a.md").write_text("第一份产物", encoding="utf-8")
    (d / "out" / "b.txt").write_bytes(b"x" * 500)
    (d / "sub").mkdir(parents=True, exist_ok=True)
    (d / "sub" / "c.md").write_text("嵌套目录里的一份", encoding="utf-8")
    (d / "_turn_logs").mkdir(parents=True, exist_ok=True)
    (d / "_turn_logs" / "01_a_120000.jsonl").write_text("原始转录，不许进包", encoding="utf-8")
    (d / "_step_system.txt").write_text("注入的系统提示词，也不许进包", encoding="utf-8")
    yield d
    db.delete_run(RID)
    import shutil
    shutil.rmtree(d, ignore_errors=True)


def _names(data):
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        return set(z.namelist())


def test_builder_packs_visible_files_only(tmp_path, ws):
    dest = tmp_path / "b.zip"
    n, total = runner.build_workspace_bundle(RID, dest)
    assert n == 3 and total > 500
    assert _names(dest.read_bytes()) == {"out/a.md", "out/b.txt", "sub/c.md"}


def test_builder_reports_bytes_that_match_the_zip(tmp_path, ws):
    dest = tmp_path / "b.zip"
    _, total = runner.build_workspace_bundle(RID, dest)
    with zipfile.ZipFile(io.BytesIO(dest.read_bytes())) as z:
        assert sum(i.file_size for i in z.infolist()) == total


def test_endpoint_downloads_an_attachment(client, ws):
    r = client.get(f"/api/runs/{RID}/artifacts-bundle")
    assert r.status_code == 200, r.text
    assert "attachment" in r.headers.get("content-disposition", "")
    assert _names(r.content) == {"out/a.md", "out/b.txt", "sub/c.md"}


def test_temp_zip_is_cleaned_up_after_the_response(client, ws):
    before = set(paths.EXPORT_DIR.glob("*.zip"))
    assert client.get(f"/api/runs/{RID}/artifacts-bundle").status_code == 200
    assert set(paths.EXPORT_DIR.glob("*.zip")) == before


def test_endpoint_404s_for_unknown_run(client, ws):
    r = client.get("/api/runs/run-never-existed/artifacts-bundle")
    assert r.status_code == 404


def test_endpoint_404s_when_there_is_nothing_to_pack(client, ws):
    for f in (ws / "out" / "a.md", ws / "out" / "b.txt", ws / "sub" / "c.md"):
        f.unlink()
    r = client.get(f"/api/runs/{RID}/artifacts-bundle")
    assert r.status_code == 404 and "产物" in r.json()["detail"]


def test_file_cap_refuses_before_writing(client, ws, monkeypatch):
    monkeypatch.setattr(runner, "_WS_BUNDLE_MAX_FILES", 2)
    r = client.get(f"/api/runs/{RID}/artifacts-bundle")
    assert r.status_code == 400 and "文件过多" in r.json()["detail"]
    assert list(paths.EXPORT_DIR.glob("*.zip")) == []


def test_size_cap_refuses_and_leaves_no_temp_file(client, ws, monkeypatch):
    monkeypatch.setattr(runner, "_WS_BUNDLE_MAX_BYTES", 400)   # 三份产物合计 ~560 字节
    r = client.get(f"/api/runs/{RID}/artifacts-bundle")
    assert r.status_code == 400 and "上限" in r.json()["detail"]
    assert list(paths.EXPORT_DIR.glob("*.zip")) == []


def test_missing_workspace_is_a_404_not_a_500(client):
    rid = "run-bundle-no-ws"
    db.delete_run(rid)
    db.create_run(rid, "测试流程", "没有工作区")
    try:
        r = client.get(f"/api/runs/{rid}/artifacts-bundle")
        assert r.status_code == 404
    finally:
        db.delete_run(rid)


def test_symlinked_file_outside_the_workspace_is_skipped(client, ws):
    """Windows 上没开开发者模式时建不了符号链接 —— 建不出来就跳过，不假装通过。"""
    outside = paths.DATA_DIR / "outside-target.md"
    outside.write_text("工作区外面的文件", encoding="utf-8")
    link = ws / "out" / "leak.md"
    try:
        os.symlink(outside, link)
    except (OSError, NotImplementedError):
        pytest.skip("这台机器不允许创建符号链接")
    try:
        names = _names(client.get(f"/api/runs/{RID}/artifacts-bundle").content)
        assert "out/leak.md" not in names
    finally:
        link.unlink(missing_ok=True)
        outside.unlink(missing_ok=True)
