# -*- coding: utf-8 -*-
"""data/updates 的清理：装完留下的 60MB 安装包要有一个人删它。"""
import os
from pathlib import Path

import pytest

from app import paths, updater


def _touch(root: Path, rel: str, data: bytes = b"x"):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)
    return p


@pytest.fixture
def udir(tmp_path, monkeypatch):
    root = tmp_path / "updates"
    root.mkdir()
    monkeypatch.setattr(updater, "updates_dir", lambda: root)
    return root


def test_sweep_removes_leftover_packages_and_the_bat(udir):
    old = _touch(udir, "Loom-1.2.0-setup.exe", b"meh")
    bat = _touch(udir, "update.bat", b"@echo off")
    part = _touch(udir, "Loom-1.2.1-setup.exe.tmp", b"half")
    flag = _touch(udir, "quit.flag", b"done")
    assert updater.sweep_leftovers() == 4
    assert not old.exists() and not bat.exists() and not part.exists()
    assert not flag.exists(), "上一次没走到收尾留下的残旗会让下一次完全不等"


def test_sweep_keeps_the_package_that_is_waiting_to_be_installed(udir, monkeypatch):
    """已下好、还没点安装的那一个不能删 —— 用户重启后还得能装上，
    而且 check() 之后 STATE["path"] 指的是它。"""
    keep = _touch(udir, "Loom-1.3.0-setup.exe", b"genuine")
    _touch(udir, "Loom-1.2.9-setup.exe", b"old")
    monkeypatch.setattr(updater, "snapshot",
                        lambda: {"path": str(keep), "phase": "ready"})
    assert updater.sweep_leftovers() == 1
    assert keep.is_file()


def test_sweep_leaves_unrelated_files_and_subdirectories_alone(udir):
    """这个目录今天只有包和脚本，将来未必。删只按后缀删、且不递归 ——
    一次"顺手清理"扫进子目录，删掉的可能是别人放的东西。"""
    note = _touch(udir, "README.txt", b"keep me")
    sub = _touch(udir, "sub/inner.exe", b"not mine")
    assert updater.sweep_leftovers() == 0
    assert note.is_file() and sub.is_file()


def test_sweep_survives_a_locked_file(udir, monkeypatch):
    """杀软还在扫那个 exe 时会撞 sharing violation。启动路径上不能因为清不干净
    就抛出来 —— 弹个框只会让人以为软件坏了，而这件事本来就该静默。"""
    left = _touch(udir, "Loom-1.2.0-setup.exe")

    def boom(self, *a, **k):
        raise OSError("being used by another process")

    monkeypatch.setattr(Path, "unlink", boom)
    assert updater.sweep_leftovers() == 0
    assert left.is_file(), "删不掉也要留在原地，别先把记账删了"


def test_apply_batch_deletes_the_package_after_a_good_install():
    """批处理以前只 del 自己，安装包留在原地。
    只看真执行的行：模板的注释里就写着旧写法（timeout / start /wait / neq 0），
    整段扫字符串等于测了段散文 —— 这个坑这轮已经踩过三次了。"""
    lines = [l for l in updater.BAT_TMPL.format(setup="S", flag="F").splitlines()
             if l.strip() and not l.strip().startswith("rem")]
    code = "\n".join(lines)
    assert 'del "S"' in code
    assert "%~f0" in code, "脚本自己也要删掉"
    # 装失败（退出码非 0）时必须留着现场：那是用户唯一还能重装一次的东西
    assert "if errorlevel 1 goto :keep" in code, code
    assert "timeout" not in code, "timeout 在标准输入被重定向时不睡，等主进程退场是假的"
    assert "start " not in code, "别回到 start /wait：它不返回时退出码是空的"
    # 等待的条件是"主进程举了旗"，不是"睡满几秒"；ping 只当那一秒的节拍用
    assert 'if exist "%FLAG%" goto :go' in code, "没在等举旗，还是在盲睡"
    assert "ping -n 4" not in code, "盲睡三秒那一支回来了"
    assert "geq" in code, "没有等待上限：主进程崩在退出路上就会把安装永远卡住"


# ==================== 那段安装批处理：真的跑一遍 ====================
# 1.2.4 刚发出去就拿当前模板实测过一轮。真 PE 桩下"删/留"两支其实都对，
# 量出来的真问题是**等待没发生**：timeout /t 3 在标准输入被重定向时（我们用
# DETACHED_PROCESS 起，正是这种）直接报错返回，整段脚本 0.69 秒就往下走，
# 而主进程 0.8 秒后才 os._exit —— 安装器是在换一个还没退出的程序。
# 现在换成 ping 计时 + 安装器直接当子进程调用（少一个会骗人的环节：
# start /wait 对批处理桩根本不返回，%errorlevel% 留空，那行 if 当场语法错）。
# 桩必须是**真 PE**：拿 .cmd 当桩测出来的"没删"是仪器的锅 —— 批处理里直接写
# foo.cmd（不带 call）是交出控制权、永不返回，而真安装器是 exe。

import subprocess
import threading
import time


def _coreutils(label):
    import shutil
    return shutil.which(label)


_needs = (_coreutils("true"), _coreutils("false"))
pytestmark_stub = pytest.mark.skipif(
    os.name != "nt" or not all(_needs),
    reason="要在 Windows 上跑 cmd，且得有 true/false 两个真 PE 当桩")


def _run_bat(tmp_path, stub_src, flag_after=0.0):
    """跑真批处理。flag_after>0 时另起一个线程在那么久之后举旗，
    用来验"等的是举旗这个事实"，不是"睡了一个固定时长"。"""
    setup = tmp_path / "Loom-9.9.9-setup.exe"
    setup.write_bytes(Path(stub_src).read_bytes())
    flag = tmp_path / "quit.flag"
    if flag_after <= 0:
        flag.write_text("done", encoding="ascii")     # 主进程已经收完
    else:
        threading.Timer(flag_after, lambda: flag.write_text("done", encoding="ascii")).start()
    bat = tmp_path / "update.bat"
    bat.write_text(updater.BAT_TMPL.format(setup=str(setup), flag=str(flag)),
                   encoding="mbcs")
    flags = 0x00000008 | 0x00000200 | 0x08000000
    devnull = subprocess.DEVNULL
    t0 = time.perf_counter()
    subprocess.run(["cmd", "/C", str(bat)], creationflags=flags, cwd=str(tmp_path),
                   stdin=devnull, stdout=devnull, stderr=devnull, timeout=90)
    for _ in range(25):      # 复制来的真 exe 可能被杀软短暂占用，多等一会儿再判
        if not setup.exists():
            break
        time.sleep(0.2)
    return setup.exists(), bat.exists(), time.perf_counter() - t0


@pytest.mark.skipif(os.name != "nt" or not all(_needs),
                    reason="要在 Windows 上跑 cmd，且得有 true/false 两个真 PE 当桩")
def test_batch_deletes_the_package_after_a_successful_install(tmp_path):
    gone_setup, gone_bat, _ = _run_bat(tmp_path, _coreutils("true"))
    assert not gone_setup, "装成功了，那个 36MB 的包还留在 data/updates 里"
    assert not gone_bat, "装成功了，批处理自己该跟着删掉"


@pytest.mark.skipif(os.name != "nt" or not all(_needs),
                    reason="要在 Windows 上跑 cmd，且得有 true/false 两个真 PE 当桩")
def test_batch_keeps_everything_when_the_install_fails(tmp_path):
    """装失败不能把现场一起删了 —— 那是用户唯一还能重装一次的东西。"""
    gone_setup, gone_bat, _ = _run_bat(tmp_path, _coreutils("false"))
    assert gone_setup, "装失败了还把安装包删了"
    assert gone_bat, "装失败了还把脚本删了（虽然它自己没跑到删那行）"


@pytest.mark.skipif(os.name != "nt" or not all(_needs),
                    reason="要在 Windows 上跑 cmd，且得有 true/false 两个真 PE 当桩")
def test_batch_waits_for_the_app_to_signal_it_is_done(tmp_path):
    """等的是"主进程举旗说收完了"这个事实，不是"过了三秒"。

    举旗之前就开始换文件，换的是一个还没退出的程序 —— 那正是当初要靠系统去"关应用"
    的起因，而且那时 WebView2 的子进程还占着安装目录里的东西。"""
    gone_setup, _, dt = _run_bat(tmp_path, _coreutils("true"), flag_after=3.0)
    assert dt >= 2.5, f"没等举旗就开装了（整段 {dt:.2f}s，替身 3s 后才举旗）"
    assert not gone_setup, "安装桩是成功的，包该删掉"


def test_batch_does_not_blind_sleep_when_the_app_is_already_gone(tmp_path):
    """旗已经在了就别再白等 —— 上一版的毛病正是"睡一个和事实无关的固定时长"。"""
    _, _, dt = _run_bat(tmp_path, _coreutils("true"))
    assert dt < 2.0, f"主进程早就收完了，却还是等了 {dt:.2f}s"


def test_batch_gives_up_waiting_after_a_bound(tmp_path):
    """主进程崩在退出路上、旗永远不举，也不能把安装永远卡住 ——
    那正是参考实现记过的坑："应用关闭了但版本没变"。等满上限要照常装。"""
    setup = tmp_path / "Loom-9.9.9-setup.exe"
    setup.write_bytes(Path(_coreutils("true")).read_bytes())
    bat = tmp_path / "update.bat"
    bat.write_text(updater.BAT_TMPL.format(setup=str(setup),
                                           flag=str(tmp_path / "never.flag")),
                   encoding="mbcs")
    t0 = time.perf_counter()
    subprocess.run(["cmd", "/C", str(bat)], stdin=subprocess.DEVNULL,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120)
    dt = time.perf_counter() - t0
    assert dt >= 15.0, f"没等到上限就放行（{dt:.1f}s），那 20 次是假的"
    assert not setup.exists(), "等满上限之后该照常安装，装成功的包要删掉"


@pytest.mark.skipif(os.name != "nt" or not all(_needs),
                    reason="要在 Windows 上跑 cmd，且得有 true 这个真 PE 当桩")
def test_batch_does_not_blind_sleep_when_the_app_is_already_gone(tmp_path):
    """主进程早就收完了就别再白等 —— 上一版的毛病正是"睡一个和事实无关的固定时长"。"""
    _, _, dt = _run_bat(tmp_path, _coreutils("true"))
    assert dt < 2.0, f"旗早就举了，却还是等了 {dt:.2f}s"


def test_installer_never_asks_windows_to_close_applications():
    """让 Inno 请系统的 RestartManager 去关"占着文件的程序"，用户看到的就是那种
    "正在关闭应用 / 结束任务"的弹窗（2026-09-27 装机实测：事件日志里一次会话
    18:58:02 开、18:58:15 才结束，13 秒）。退出是程序自己的事。

    钉的是**那一行真正的调用**，不是整段文本 —— 拿子串判会被自己写的注释判红，
    这一轮已经被自己的注释绊过好几回了。"""
    call = [ln for ln in updater.BAT_TMPL.splitlines() if ln.strip().startswith('"{setup}"')]
    assert len(call) == 1, f"调用行该只有一条，实际 {len(call)}"
    assert call[0].strip() == '"{setup}" /SILENT /NORESTART /SUPPRESSMSGBOXES', call[0].strip()
    iss = (Path(__file__).resolve().parent.parent / "installer.iss").read_text(encoding="utf-8")
    assert "CloseApplications=no" in iss, "安装器还是会让 Windows 去关应用"


class _ImmediateTimer:
    """把 apply_update 里那一拍延后退出改成同步执行。

    不这么做的话：monkeypatch 在测试结束时就把 `_QUIT_HOOK` 还原成 None，
    而定时器 0.4 秒后才响 —— `_quit()` 走到 os._exit 兜底，整个 pytest 进程被杀掉，
    退出码还是 0。实测症状是汇总行凭空消失、进度停在 76%，看着像全绿。"""

    def __init__(self, _delay, fn):
        self._fn = fn

    def start(self):
        self._fn()


def _apply_env(monkeypatch, updater, udir):
    """把 apply_update 需要的现场搭起来：一个校验得过、已经下好的包 + 打包态快照。"""
    pkg = udir / "Loom-9.9.9-setup.exe"
    pkg.write_bytes(b"x" * 4096)
    want = updater._sha256_of(pkg)
    monkeypatch.setattr(updater, "snapshot", lambda: {
        "frozen": True, "phase": "ready", "path": str(pkg), "sha256": want,
        "size": pkg.stat().st_size, "latest": "9.9.9", "url": "", "file": pkg.name,
        "notes": "", "error": "", "got": 0, "active_runs": 0, "configured": True,
        "local": "1.2.6", "update_url": "", "default_url": ""})
    monkeypatch.setattr(updater, "_APPLY_STARTED", False)
    monkeypatch.setattr(updater.threading, "Timer", _ImmediateTimer)
    return pkg


def test_apply_exits_through_the_registered_hook(monkeypatch, udir):
    """os._exit(0) 跳过一切清理：WebView2 的子进程和本地服务都没被告知要收，
    文件锁就这么留着了 —— 那正是后面要 Windows 去"关应用"的起因。
    改成走壳注册进来的退出钩子（销毁窗口 → webview.start() 返回 → 正常收尾）。"""
    src = Path(updater.__file__).read_text(encoding="utf-8")
    assert "os._exit" not in src.split("def apply_update")[1], "apply 里还在硬退"
    calls = []
    monkeypatch.setattr(updater, "_QUIT_HOOK", lambda: calls.append("quit"))
    spawned = []
    monkeypatch.setattr(updater.subprocess, "Popen", lambda *a, **k: spawned.append(a))
    _apply_env(monkeypatch, updater, udir)
    r = updater.apply_update()
    assert r.get("ok"), r
    assert spawned, "没起安装器"
    assert "quit" in calls, "没走退出钩子"
    assert not updater.quit_flag_path().exists(), "起安装器之前要先把上一次的残旗清掉"


def test_apply_is_one_shot(monkeypatch, udir):
    """点两下不该起两个安装器：第二个 BAT 会去删第一个正在用的那个包。"""
    spawned = []
    monkeypatch.setattr(updater.subprocess, "Popen", lambda *a, **k: spawned.append(a))
    monkeypatch.setattr(updater, "_QUIT_HOOK", lambda: None)
    _apply_env(monkeypatch, updater, udir)
    assert updater.apply_update().get("ok")
    second = updater.apply_update()
    assert second.get("ok"), second
    assert len(spawned) == 1, f"起了 {len(spawned)} 个安装器"


def test_uninstall_only_deletes_data_after_explicit_confirmation():
    """卸载页的"连数据一起删"必须显式点头，且删除动作被三道闸围住。

    数据目录里是用户的流程、产物与自建技能——默认路径（一路点下一步）永远保留。
    措辞必须把"不可恢复"说在前面；DelTree 只允许出现一次、只允许指向 {app}\data，
    且必须 (a) 在 KillApp 之后（SQLite/WAL 被进程占着会留下残骸）、
    (b) 在 if RemoveData then 的确认分支里。[UninstallDelete] 段不许碰 data。"""
    iss = (Path(__file__).resolve().parent.parent / "installer.iss").read_text(encoding="utf-8")
    assert iss.count("DelTree(") == 1, "DelTree 只许出现一次（删数据只有这一个口子）"
    tree_line = [ln for ln in iss.splitlines() if "DelTree(" in ln][0]
    assert "{app}\data" in tree_line, f"DelTree 的目标不是 data 目录：{tree_line.strip()}"
    # (a) 顺序：KillApp 调用先于 DelTree
    assert iss.index("KillApp();") < iss.index("DelTree("), \
        "删除数据前没有先关程序——SQLite/WAL 被占用会删不干净"
    # (b) 确认分支：RemoveData 默认 False，只有 MB_YESNO 的 IDYES 分支置 True
    assert "RemoveData: Boolean;" in iss
    assert iss.count("RemoveData := True") == 1
    guard = iss.split("if RemoveData then")
    assert len(guard) == 2 and "DelTree(" in guard[1], "DelTree 不在确认分支里"
    ask = iss.split("mbConfirmation, MB_YESNO")[0]
    assert "不可恢复" in ask, "确认框没把'删除后不可恢复'说在前面"
    # 默认路径的提示文案必须还在（保留数据是默认承诺）
    assert "重装后会自动继续读取" in iss
    # [UninstallDelete] 段不许删数据目录本身（清一枚 boot-error 日志文件是既有的、无害的）
    ud = [ln for ln in iss.split("[UninstallDelete]")[1].split("[Code]")[0].splitlines()
          if ln.strip() and not ln.strip().startswith(";")]
    ud_text = "\n".join(ud)
    assert "DelTree" not in ud_text and 'Name: "{app}\\data"' not in ud_text, \
        f"[UninstallDelete] 又去删数据目录了：{ud}"
