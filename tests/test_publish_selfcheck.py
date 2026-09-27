# -*- coding: utf-8 -*-
"""发布脚本的自检：上传之前，清单必须和真正要传的那个文件对得上。

更新器现在完全信任 latest.json 做安全判定（sha256 不符就拒装、file 与 url
对不上就拒下）。所以一份手改过或忘了重新生成的清单传上去，代价是所有人
「检查更新通过、点安装就报错」，而且只有已装过旧版的人才会碰到 —— 本地测不出来。
"""
import importlib.util
import sys
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "upload_cos", Path(__file__).resolve().parent.parent / "upload_cos.py")
upload_cos = importlib.util.module_from_spec(_spec)
sys.modules["upload_cos"] = upload_cos
_spec.loader.exec_module(upload_cos)

SHA = "a" * 64
BASE = "https://modelflow-1447874637.cos.ap-guangzhou.myqcloud.com"
GOOD = {
    "version": "1.2.4",
    "file": "Loom-1.2.4-setup.exe",
    "url": BASE + "/Loom-1.2.4-setup.exe",
    "sha256": SHA,
    "size": 78643210,
    "notes": "修了 X，加了 Y",
}


def _errs(m=None, sha=SHA, size=78643210):
    return upload_cos.consistency_errors(dict(m or GOOD), sha, size, BASE)


def test_a_matching_manifest_passes():
    assert _errs() == []


def test_stale_sha_is_caught_before_upload():
    """清单没跟着新包重新生成，是最常见的一种错。"""
    e = _errs(sha="b" * 64)
    assert any("sha256" in x for x in e), e


def test_size_mismatch_is_caught():
    e = _errs(size=123)
    assert any("size" in x for x in e), e


def test_file_and_version_must_agree():
    """make_release 按版本号命名；这两个不一致就说明有人在中间手动改过清单。"""
    e = _errs({**GOOD, "file": "Loom-1.2.3-setup.exe"})
    assert any("version" in x for x in e), e


def test_url_must_point_at_the_file_and_the_bucket():
    e = _errs({**GOOD, "url": BASE + "/Loom-9.9.9-setup.exe"})
    assert any("不是 file" in x or "指向" in x for x in e), e
    e = _errs({**GOOD, "url": "https://elsewhere.test/Loom-1.2.4-setup.exe"})
    assert any("不在我们要传的桶" in x for x in e), e
    assert not any(x.startswith("url 必须") for x in e), e     # https 那关是过的
    e = _errs({**GOOD, "url": "http://x/Loom-1.2.4-setup.exe"})
    assert any("https" in x for x in e), e


def test_path_traversal_in_file_is_caught():
    e = _errs({**GOOD, "file": "../Loom-1.2.4-setup.exe",
               "url": BASE + "/../Loom-1.2.4-setup.exe"})
    assert any("纯文件名" in x for x in e), e


def test_empty_notes_is_caught():
    """notes 会渲染进更新浮层：空的就是一块白，而发版时 --notes 忘写太常见了。"""
    assert any("notes" in x for x in _errs({**GOOD, "notes": "   "}))


def test_missing_version_is_caught():
    assert any("version" in x for x in _errs({**GOOD, "version": ""}))


def test_the_sha_helper_hashes_a_real_file(tmp_path):
    f = tmp_path / "x.bin"
    f.write_bytes(b"hello")
    assert upload_cos.sha256_of(f) == \
        "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"


# ---------------- GitHub 镜像（第二下载源） ----------------

_pg_spec = importlib.util.spec_from_file_location(
    "publish_github", Path(__file__).resolve().parent.parent / "publish_github.py")
publish_github = importlib.util.module_from_spec(_pg_spec)
sys.modules["publish_github"] = publish_github
_pg_spec.loader.exec_module(publish_github)


def _fake_release_dir(tmp_path, size=1234):
    import json
    man = {"version": "9.9.9", "url": f"{BASE}/Loom-9.9.9-setup.exe",
           "file": "Loom-9.9.9-setup.exe", "sha256": "b" * 64, "size": size,
           "notes": "说明"}
    (tmp_path / "latest.json").write_text(json.dumps(man, ensure_ascii=False), encoding="utf-8")
    (tmp_path / "Loom-9.9.9-setup.exe").write_bytes(b"x" * 8)
    return tmp_path / "latest.json"


def test_make_release_leaves_a_mirrors_slot():
    """清单里得先有这个字段，回填才有地方写。老清单没有它时软件按单源跑（有测试钉着）。"""
    src = (Path(__file__).resolve().parent.parent / "make_release.py").read_text(encoding="utf-8")
    assert '"mirrors"' in src


def test_mirror_url_is_the_release_asset():
    assert publish_github.mirror_url("1.2.8", "Loom-1.2.8-setup.exe") == \
        "https://github.com/liixnglinb/Jacquard/releases/download/v1.2.8/Loom-1.2.8-setup.exe"


def test_a_mirror_that_cannot_be_read_back_is_not_written(tmp_path, monkeypatch):
    """回读不通过就别写进清单 —— 写了等于告诉所有已装机器"这个源有包"，
    而它可能 404。前端是拿它去测速的，一个死源会白等一轮超时。"""
    import pytest
    man_path = _fake_release_dir(tmp_path)
    before = man_path.read_text(encoding="utf-8")
    monkeypatch.setattr(publish_github, "REL", tmp_path)
    monkeypatch.setattr(publish_github, "verify", lambda *a, **k: False)
    monkeypatch.setattr(sys, "argv", ["publish_github.py", "--skip-upload"])
    with pytest.raises(SystemExit) as ei:      # 失败是 sys.exit(非零)，不是返回码
        publish_github.main()
    assert ei.value.code not in (0, None)
    assert man_path.read_text(encoding="utf-8") == before, "回读没过却把镜像写进了清单"


def test_a_verified_mirror_lands_in_the_manifest(tmp_path, monkeypatch):
    import json
    man_path = _fake_release_dir(tmp_path)
    monkeypatch.setattr(publish_github, "REL", tmp_path)
    monkeypatch.setattr(publish_github, "verify", lambda *a, **k: True)
    monkeypatch.setattr(sys, "argv", ["publish_github.py", "--skip-upload"])
    assert publish_github.main() == 0
    man = json.loads(man_path.read_text(encoding="utf-8"))
    assert man["mirrors"] == [publish_github.mirror_url("9.9.9", "Loom-9.9.9-setup.exe")]
    assert man["sha256"] == "b" * 64 and man["size"] == 1234, "回填不该动到别的主字段"
