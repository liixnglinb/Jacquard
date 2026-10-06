# -*- coding: utf-8 -*-
"""Office 分镜预览（纯标准库拆 OOXML）与孤儿工作区清理。

预览的输入是智能体产物 = 不可信 zip/XML，所以除了"抽得对"，还必须测
"拒得对"：坏包、炸弹包、带 DTD 的包都要落成可读错误，不能抛穿到端点。
清理那一半只碰 conftest 的临时数据目录，绝不碰用户真实工作区。
"""
import base64
import io
import shutil
import zipfile

import pytest

from app import db, paths, runner

# 1x1 透明 PNG：预览层只看字节数和后缀，不需要能解码
_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")
_A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
_P_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"
_W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_R_NS = "http://schemas.openxmlformats.org/package/2006/relationships"


def _zip(members):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in members:
            z.writestr(name, data)
    return buf.getvalue()


def _slide_xml(paras):
    body = "".join("<a:p><a:r><a:t>%s</a:t></a:r></a:p>" % p for p in paras)
    return ('<?xml version="1.0" encoding="UTF-8"?>'
            '<p:sld xmlns:a="%s" xmlns:p="%s">%s</p:sld>' % (_A_NS, _P_NS, body))


def _rels(targets):
    inner = "".join('<Relationship Id="rId%d" Type="image" Target="%s"/>' % (i, t)
                    for i, t in enumerate(targets, 1))
    return ('<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="%s">%s</Relationships>'
            % (_R_NS, inner))


def _pptx(slides):
    """slides: [(页码, [段落文字], [图片 target])] —— target 按 pptx 的写法给 ../media/x.png。"""
    members, media = [], []
    for num, paras, targets in slides:
        members.append(("ppt/slides/slide%d.xml" % num, _slide_xml(paras)))
        if targets:
            members.append(("ppt/slides/_rels/slide%d.xml.rels" % num, _rels(targets)))
            for t in targets:
                member = "ppt/" + t.replace("../", "")
                media.append((member, _PNG if "big" not in member else _PNG + b"0" * 2_000_000))
    return _zip(members + media)


def _docx(paras, images=()):
    body = "".join("<w:p><w:r><w:t>%s</w:t></w:r></w:p>" % p for p in paras)
    members = [("word/document.xml",
                '<?xml version="1.0" encoding="UTF-8"?><w:document xmlns:w="%s">%s</w:document>'
                % (_W_NS, body))]
    if images:
        members.append(("word/_rels/document.xml.rels",
                        _rels(["media/" + n for n in images])))
        members += [("word/media/" + n, _PNG) for n in images]
    return _zip(members)


@pytest.fixture
def office_run():
    rid = "run-office-preview"
    db.delete_run(rid)
    db.create_run(rid, "测试流程", "office 预览")
    ws = runner.workspace_dir(rid)
    yield rid, ws
    db.delete_run(rid)
    shutil.rmtree(ws, ignore_errors=True)


def _put(ws, name, data):
    (ws / name).parent.mkdir(parents=True, exist_ok=True)
    (ws / name).write_bytes(data)
    return name


# ---------------------------------------------------------------- 预览：抽得对

def test_office_extensions_are_a_distinct_kind():
    assert runner.file_kind("deck.pptx") == "office"
    assert runner.file_kind("paper.DOCX") == "office"
    assert runner.file_kind("archive.zip") == "binary"


def test_pptx_preview_extracts_text_per_slide(office_run):
    rid, ws = office_run
    name = _put(ws, "out/deck.pptx", _pptx([(1, ["研究背景", "数据口径"], []),
                                           (2, ["模型建立"], [])]))
    d = runner.read_workspace_file(rid, name)
    assert d["kind"] == "office"
    assert d["office"]["type"] == "pptx"
    assert d["text"] == ""
    assert [s["n"] for s in d["office"]["slides"]] == [1, 2]
    assert d["office"]["slides"][0]["text"] == "研究背景\n数据口径"
    assert d["office"]["slides"][1]["text"] == "模型建立"


def test_pptx_slides_sort_numerically_not_lexically(office_run):
    rid, ws = office_run
    slides = [(n, ["第%d页" % n], []) for n in (1, 2, 10)]
    name = _put(ws, "deck.pptx", _pptx(slides))
    d = runner.read_workspace_file(rid, name)
    # 成员名是集合来的，不排序会得到 1,10,2 —— 分镜顺序错乱比预览缺失更糟
    assert [s["n"] for s in d["office"]["slides"]] == [1, 2, 10]


def test_pptx_inlines_small_images_and_counts_the_rest(office_run):
    rid, ws = office_run
    name = _put(ws, "deck.pptx", _pptx([(1, ["图页"], ["../media/a.png", "../media/big.png"])]))
    d = runner.read_workspace_file(rid, name)
    s = d["office"]["slides"][0]
    assert len(s["images"]) == 1
    assert s["images"][0].startswith("data:image/png;base64,")
    assert s["omitted"] == 1
    assert d["office"]["mediaInlined"] == 2


def test_pptx_caps_how_many_images_are_inlined(office_run):
    rid, ws = office_run
    many = ["../media/i%02d.png" % i for i in range(runner._OFFICE_IMG_INLINE_MAX + 2)]
    name = _put(ws, "deck.pptx", _pptx([(1, ["多图"], many)]))
    s = runner.read_workspace_file(rid, name)["office"]["slides"][0]
    assert len(s["images"]) == runner._OFFICE_IMG_INLINE_MAX
    assert s["omitted"] == 2


def test_docx_preview_joins_paragraphs_and_pulls_its_images(office_run):
    rid, ws = office_run
    name = _put(ws, "paper.docx", _docx(["摘要", "第一章 引言"], ["fig1.png"]))
    d = runner.read_workspace_file(rid, name)
    assert d["office"]["type"] == "docx"
    assert d["office"]["slides"][0]["text"] == "摘要\n第一章 引言"
    assert len(d["office"]["slides"][0]["images"]) == 1


def test_docx_without_body_text_says_so(office_run):
    rid, ws = office_run
    name = _put(ws, "blank.docx", _docx([]))
    d = runner.read_workspace_file(rid, name)
    assert "正文" in d["office"]["error"]
    assert d["office"]["slides"] == []


# ---------------------------------------------------------------- 预览：拒得对

def test_oversized_package_members_are_truncated_not_dropped(office_run):
    rid, ws = office_run
    long_para = "长" * (runner._OFFICE_TEXT_MAX + 100)
    name = _put(ws, "huge.pptx", _pptx([(1, [long_para], [])]))
    d = runner.read_workspace_file(rid, name)
    assert len(d["office"]["slides"][0]["text"]) == runner._OFFICE_TEXT_MAX


def test_bad_zip_becomes_a_readable_error(office_run):
    rid, ws = office_run
    name = _put(ws, "broken.pptx", b"this is not a zip file at all")
    d = runner.read_workspace_file(rid, name)
    assert "Office" in d["office"]["error"]
    assert d["office"]["slides"] == []


def test_pptx_without_slides_becomes_a_readable_error(office_run):
    rid, ws = office_run
    name = _put(ws, "empty.pptx", _zip([("[Content_Types].xml", "<Types/>")]))
    d = runner.read_workspace_file(rid, name)
    assert "没有幻灯片" in d["office"]["error"]


def test_member_count_cap_refuses_the_package(office_run):
    rid, ws = office_run
    members = [("ppt/slides/slide%d.xml" % i, _slide_xml(["x"]))
               for i in range(1, runner._ZIP_MEMBERS_MAX + 2)]
    name = _put(ws, "many.pptx", _zip(members))
    d = runner.read_workspace_file(rid, name)
    assert "成员过多" in d["office"]["error"]


def test_uncompressed_size_cap_refuses_the_package(office_run):
    rid, ws = office_run
    # 70 个 1MB 的空成员：压缩包很小，解压后 70MB > 上限 —— 典型压缩炸弹形状
    blob = b"\0" * (1024 * 1024)
    members = [("ppt/slides/slide%d.xml" % i, _slide_xml(["x"])) for i in range(1, 6)]
    members += [("junk/pad%d" % i, blob) for i in range(70)]
    name = _put(ws, "bomb.pptx", _zip(members))
    d = runner.read_workspace_file(rid, name)
    assert "64MB" in d["office"]["error"]


def test_dtd_or_entity_declaration_is_refused(office_run):
    rid, ws = office_run
    evil = ('<?xml version="1.0"?><!DOCTYPE p:sld [<!ENTITY x SYSTEM "file:///etc/passwd">]>'
            '<p:sld xmlns:a="%s" xmlns:p="%s"><a:p><a:r><a:t>&x;</a:t></a:r></a:p></p:sld>'
            % (_A_NS, _P_NS))
    name = _put(ws, "evil.pptx", _zip([("ppt/slides/slide1.xml", evil)]))
    d = runner.read_workspace_file(rid, name)
    assert "DTD" in d["office"]["error"]
    assert d["office"]["slides"] == []


def test_dtd_in_rels_is_refused_too(office_run):
    rid, ws = office_run
    evil = ('<?xml version="1.0"?><!DOCTYPE Relationships [<!ENTITY e "x">]>'
            '<Relationships xmlns="%s"><Relationship Id="rId1" Type="image" '
            'Target="../media/&e;.png"/></Relationships></Relationships>' % _R_NS)
    name = _put(ws, "evil2.pptx", _zip([("ppt/slides/slide1.xml", _slide_xml(["正文"])),
                                        ("ppt/slides/_rels/slide1.xml.rels", evil)]))
    d = runner.read_workspace_file(rid, name)
    assert "DTD" in d["office"]["error"]


def test_corrupt_inner_xml_is_caught(office_run):
    rid, ws = office_run
    name = _put(ws, "junk.pptx", _zip([("ppt/slides/slide1.xml", "<a:p>not closed")]))
    d = runner.read_workspace_file(rid, name)
    assert d["office"]["error"]
    assert d["office"]["slides"] == []


def test_office_preview_through_the_endpoint(client, office_run):
    rid, ws = office_run
    name = _put(ws, "out/deck.pptx", _pptx([(1, ["接口页"], [])]))
    r = client.get("/api/runs/%s/files/%s" % (rid, name))
    assert r.status_code == 200
    body = r.json()
    assert body["kind"] == "office"
    assert body["office"]["slides"][0]["text"] == "接口页"


def test_internal_office_file_is_not_previewable(office_run):
    rid, ws = office_run
    name = _put(ws, "_turn_logs/deck.pptx", _pptx([(1, ["不该被读到"], [])]))
    with pytest.raises(FileNotFoundError):
        runner.read_workspace_file(rid, name)


# ---------------------------------------------------------------- 清理孤儿

def _make_orphan(name, bytes_):
    d = paths.WORKSPACES_DIR / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "f.txt").write_bytes(b"x" * bytes_)
    return d


@pytest.fixture
def orphan_scene(office_run):
    """一条有记录的工作区 + 两条没记录的孤儿。"""
    rid, ws = office_run
    (ws / "keep.txt").write_bytes(b"y" * 10)
    a = _make_orphan("run-gone-a", 100)
    b = _make_orphan("run-gone-b", 200)
    yield rid, ws, a, b
    shutil.rmtree(a, ignore_errors=True)
    shutil.rmtree(b, ignore_errors=True)


def test_orphan_report_leaves_recorded_dirs_alone(orphan_scene):
    rid, ws, a, b = orphan_scene
    names = {o["name"] for o in runner.orphan_workspaces()}
    assert a.name in names and b.name in names
    assert ws.name not in names


def test_cleanup_removes_orphans_and_reports_freed_bytes(orphan_scene):
    rid, ws, a, b = orphan_scene
    before = runner.orphan_workspaces()
    expected = sum(o["bytes"] for o in before)
    r = runner.cleanup_orphan_workspaces()
    assert r["failed"] == []
    assert set([a.name, b.name]) <= set(r["removed"])
    assert r["bytes"] == expected
    assert not a.exists() and not b.exists()
    assert ws.is_dir() and (ws / "keep.txt").read_bytes() == b"y" * 10
    left = {o["name"] for o in runner.orphan_workspaces()}
    assert a.name not in left and b.name not in left


def test_cleanup_is_idempotent(orphan_scene):
    rid, ws, a, b = orphan_scene
    runner.cleanup_orphan_workspaces()
    r = runner.cleanup_orphan_workspaces()
    assert a.name not in r["removed"] and b.name not in r["removed"]
    assert not a.exists() and not b.exists()


def test_one_failure_does_not_abort_the_rest(orphan_scene, monkeypatch):
    rid, ws, a, b = orphan_scene
    real = shutil.rmtree
    def flaky(path, *args, **kw):
        if str(path).endswith(b.name):
            raise OSError("被别的进程占着")
        real(path)
    monkeypatch.setattr(runner.shutil, "rmtree", flaky)
    r = runner.cleanup_orphan_workspaces()
    assert a.name in r["removed"]
    assert r["failed"] == [{"name": b.name, "err": "被别的进程占着"}]


def test_cleanup_endpoint_refuses_while_runs_are_active(client, orphan_scene):
    rid, ws, a, b = orphan_scene
    db.update_run(rid, status="running")
    r = client.post("/api/workspaces/cleanup-orphans", json={})
    assert r.status_code == 409
    assert a.exists()
    db.update_run(rid, status="done")
    r = client.post("/api/workspaces/cleanup-orphans", json={})
    assert r.status_code == 200
    assert a.name in r.json()["removed"]
