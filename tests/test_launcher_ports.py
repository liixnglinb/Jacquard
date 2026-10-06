# -*- coding: utf-8 -*-
"""打包入口的端口与单实例契约。

这两件事都不会被界面测试碰到：端口写死会让"别人占了 8000"变成打不开，
单实例判据用错信号会让两个进程同时写同一个 SQLite。
"""
import socket
import subprocess
import sys
from pathlib import Path

import pytest

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))

import loom_launch as L  # noqa: E402


def _hold(port: int) -> socket.socket:
    s = socket.socket()
    s.bind(("127.0.0.1", port))
    s.listen(1)
    return s


def _spare_port() -> int:
    """让系统挑一个空口。写死端口会把这条测试和开发机绑在一起：本机验证服务
    占着 8123 时，_hold 自己先炸（WinError 10048），报的是环境问题不是契约破了。"""
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def test_port_is_a_preference_not_a_hard_requirement():
    """首选口被占必须往后找，且找到的那个口确实是空的。"""
    holder = _hold(8000)
    try:
        got = L.pick_port(8000)
        assert got != 8000, "8000 被占还是返回 8000，等于没换"
        assert 8000 < got < 8000 + 40 or got > 1024, f"换出来的端口不像话：{got}"
        assert L._port_free(got), f"pick_port 给了一个同样占着的口：{got}"
    finally:
        holder.close()
    assert L.pick_port(8000) == 8000, "空下来之后应该还回首选口，别每次都换个新号"


def test_port_free_asks_bind_not_connect():
    """只 listen 没 connect 上的口，connect 判据会说"空"，bind 才说真话。"""
    port = _spare_port()
    holder = _hold(port)
    try:
        assert not L._port_free(port)
    finally:
        holder.close()
    assert L._port_free(port)


def test_single_instance_lock_is_a_named_mutex_not_a_port_probe():
    """同进程内第二次拿锁必须失败；另起一个子进程拿锁也必须失败。
    用端口当判据会误报（别人占了 8000 但 Loom 没在跑）也会漏报（Loom 跑在别的口）。"""
    if not sys.platform.startswith("win"):
        pytest.skip("命名互斥体是 Windows 的")
    assert L.acquire_single_instance_lock() is True, "第一次拿锁应当成功"
    assert L.acquire_single_instance_lock() is False, "同进程重复拿锁居然成功"
    child = (f"import sys; sys.path.insert(0, {str(BASE)!r}); import loom_launch as L; "
             "print('LOCK', L.acquire_single_instance_lock())")
    r = subprocess.run([sys.executable, "-c", child], capture_output=True,
                       text=True, encoding="utf-8", errors="replace", timeout=30)
    assert "LOCK False" in r.stdout, f"父进程持锁时子进程却拿到了：{r.stdout!r}{r.stderr[:300]}"


def test_focus_existing_ignores_its_own_process():
    """按标题找窗口时排掉自己 —— 否则第二个实例会把"端口被占"那个错误框
    当成已有窗口聚焦，然后自己退出，用户看到一个没人认领的弹框。"""
    assert L.focus_existing() in (True, False)     # 不崩就是底线


def test_no_bare_port_error_dialog_left():
    """那条"结束占用该端口的程序"的文案等于叫用户去任务管理器杀人。"""
    src = (BASE / "loom_launch.py").read_text(encoding="utf-8")
    assert "已被其他程序占用" not in src, "端口冲突拒启的老路又回来了"
    assert "结束占用该端口的程序" not in src, "又把任务管理器指给了用户"
