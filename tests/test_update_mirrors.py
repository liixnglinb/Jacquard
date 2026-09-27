# -*- coding: utf-8 -*-
"""双源下载：清单给出镜像列表，软件测速选快的那个，但**装什么由清单的 sha256 说了算**。

选源只影响速度，绝不影响"装的是哪个包" —— 这条是这一组测试真正在守的东西：
如果选源能改变结果，"哪边快用哪边"就等价于"哪边给了旧包用哪边"。
"""
import hashlib

import pytest

from app import db, updater


@pytest.fixture(autouse=True)
def _clean():
    db.set_setting("update_url", "")
    updater._set(phase="idle", latest="", url="", asset="", sha256="", size=0,
                 got=0, path="", error="", notes="", mirrors=[], checked_at="")
    yield
    db.set_setting("update_url", "")
    updater._set(phase="idle", latest="", url="", asset="", sha256="", size=0,
                 got=0, path="", error="", notes="", mirrors=[], checked_at="")


def test_mirrors_must_be_https_and_the_same_file():
    """镜像列表是清单里的外部输入：非 https、指向别的文件名、重复、把主地址也塞进来 ——
    这些都必须被剔掉。带 `..` 或另一个 exe 名字的镜像能把包写到别处去。"""
    base = "https://cos.example.com/Loom-1.2.8-setup.exe"
    got = updater._manifest_mirrors({
        "mirrors": [
            "https://github.com/o/r/releases/download/v1.2.8/Loom-1.2.8-setup.exe",
            "http://plain.example.com/Loom-1.2.8-setup.exe",     # 不是 https
            "https://evil.example.com/other.exe",                # 文件名对不上
            "https://github.com/o/r/releases/download/v1.2.8/Loom-1.2.8-setup.exe",  # 重复
            base,                                                # 主地址自己
            "  https://mirror.example.com/Loom-1.2.8-setup.exe  ",
            None, 42,                                            # 脏数据
        ]}, base, "Loom-1.2.8-setup.exe")
    assert got == [
        "https://github.com/o/r/releases/download/v1.2.8/Loom-1.2.8-setup.exe",
        "https://mirror.example.com/Loom-1.2.8-setup.exe",
    ]


def test_manifest_without_mirrors_is_still_fine():
    """老清单没有这个字段 —— 必须照旧能用，否则所有已装机器的更新会在发版那一刻集体失灵。"""
    assert updater._manifest_mirrors({}, "https://a/x.exe", "x.exe") == []


def test_sources_are_ordered_by_speed_and_dead_ones_go_last(monkeypatch):
    primary = "https://cos/x.exe"
    fast = "https://gh/x.exe"
    slow = "https://mirror/x.exe"
    dead = "https://gone/x.exe"
    speed = {primary: 1.0, fast: 9.0, slow: 0.5, dead: -1.0}
    calls = []
    monkeypatch.setattr(updater, "_probe", lambda u, **k: calls.append(u) or speed[u])
    order = updater._order_sources([primary, slow, fast, dead])
    assert order == [fast, primary, slow, dead], order
    assert sorted(calls) == sorted([primary, slow, fast, dead]), "每个源都要探一次"


def test_single_source_is_not_probed_at_all(monkeypatch):
    """只有一个源就没有"选"这回事，别为了它多花一次往返。"""
    def boom(*a, **k):
        raise AssertionError("不该探速")
    monkeypatch.setattr(updater, "_probe", boom)
    assert updater._order_sources(["https://cos/x.exe"]) == ["https://cos/x.exe"]


def test_download_falls_back_to_the_next_source(monkeypatch, tmp_path):
    """主源连不上就换镜像 —— 但换完还是要过 sha256 那一关。"""
    blob = b"installer" * 500
    sha = hashlib.sha256(blob).hexdigest()
    dest = tmp_path / "p.exe"

    class _Resp:
        status_code = 200
        def __init__(self, chunks): self._c = list(chunks)
        def raise_for_status(self): pass
        def iter_content(self, chunk_size=0): return iter(self._c)
        def __enter__(self): return self
        def __exit__(self, *a): return False

    def fake_get(url, **kw):
        if url.endswith("/dead.exe"):
            raise ConnectionError("连不上")
        return _Resp([blob])

    monkeypatch.setattr(updater.requests, "get", fake_get)
    updater._set(phase="downloading")
    updater._download_any(["https://a/dead.exe", "https://b/p.exe"], dest, len(blob), sha)
    assert updater.STATE["phase"] == "ready", updater.STATE["error"]
    assert dest.read_bytes() == blob


def test_a_mirror_serving_the_wrong_build_is_rejected(monkeypatch, tmp_path):
    """镜像给了个 sha 对不上的包 —— 必须丢掉、换下一个，而不是装上。
    这一条是"选快"能成立的前提：快不快只决定顺序，装什么永远由清单决定。"""
    good = b"the real installer" * 200
    sha = hashlib.sha256(good).hexdigest()
    dest = tmp_path / "p.exe"

    class _Resp:
        status_code = 200
        def __init__(self, chunks): self._c = list(chunks)
        def raise_for_status(self): pass
        def iter_content(self, chunk_size=0): return iter(self._c)
        def __enter__(self): return self
        def __exit__(self, *a): return False

    def fake_get(url, **kw):
        return _Resp([b"tampered" * 40] if url.endswith("/bad.exe") else [good])

    monkeypatch.setattr(updater.requests, "get", fake_get)
    updater._set(phase="downloading")
    updater._download_any(["https://fast/bad.exe", "https://slow/p.exe"],
                          dest, len(good), sha)
    assert updater.STATE["phase"] == "ready", updater.STATE["error"]
    assert dest.read_bytes() == good, "装上的必须是清单里那个包"


def test_all_sources_failing_reports_one_error(monkeypatch, tmp_path):
    monkeypatch.setattr(updater.requests, "get",
                        lambda url, **kw: (_ for _ in ()).throw(ConnectionError("连不上")))
    updater._set(phase="downloading")
    updater._download_any(["https://a/x.exe", "https://b/x.exe"],
                          tmp_path / "p.exe", 10, "0" * 64)
    assert updater.STATE["phase"] == "error"
    assert "连不上" in updater.STATE["error"]
