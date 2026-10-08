# -*- coding: utf-8 -*-
"""自动更新：读 COS 上的 latest.json 清单，流式下载安装包、核对 sha256，再静默装上。

清单地址写在 settings 的 update_url，留空走 DEFAULT_UPDATE_URL。
下载页和软件内更新器读的是同一份 latest.json —— 页面下到的版本
和软件里报的版本必须永远一致，所以只留这一个源。

装自身的做法：把 setup.exe 交给一个脱离本进程的批处理去跑，
安装器会自己关掉正在运行的 Loom，装完再由用户重启。源码运行时
没有"自身"可换，这条路直接明确报错，不假装成功。
"""
import atexit
import hashlib
import os
import re
import subprocess
import sys
import threading
import time
from pathlib import Path
from urllib.parse import urlparse

import requests

from . import db, paths
from .version import APP_VERSION

DEFAULT_UPDATE_URL = "https://modelflow-1447874637.cos.ap-guangzhou.myqcloud.com/latest.json"

_LOCK = threading.Lock()
_DL = {}          # 下载线程句柄，防重入
STATE = {
    "phase": "idle",        # idle|checking|available|current|error|downloading|ready
    "local": APP_VERSION,
    "latest": "",
    "notes": "",
    "url": "",
    "asset": "",
    "mirrors": [],          # 清单给的同包镜像，下载时按实测速度排序
    "sha256": "",
    "size": 0,
    "got": 0,
    "path": "",
    "error": "",
    "checked_at": "",
    "frozen": bool(getattr(sys, "frozen", False)),
}


def update_url() -> str:
    return (db.get_setting("update_url") or "").strip() or DEFAULT_UPDATE_URL


def manifest_url() -> str:
    """清单地址。STATE["url"] 存的是安装包地址，两个别混。"""
    return update_url()


def updates_dir() -> Path:
    d = paths.DATA_DIR / "updates"
    d.mkdir(parents=True, exist_ok=True)
    return d


def sweep_leftovers() -> int:
    """开机清掉 data/updates 里上一次装完留下的安装包和批处理，返回删掉的个数。

    以前只删自己（update.bat 装成功后 del "%~f0"），那个 60MB 的 setup.exe 永远留在
    那儿；每升一级多一个，而这个目录没有任何界面入口，没人知道它在那儿。
    只在启动时扫：那时候不可能有下载在飞（STATE 从 idle 起），也不会碰到刚下好
    还没点的包 —— 那个是本轮要用的，留着。
    """
    root = updates_dir()
    kept = snapshot().get("path") or ""
    keep = str(Path(kept).resolve()) if kept else ""
    n = 0
    for f in root.iterdir():
        try:
            # iterdir 只看这一层，is_file 挡掉子目录：不递归、不跟别人放的目录较劲
            if not f.is_file():
                continue
            if keep and str(f.resolve()) == keep:
                continue        # 已经下好、等着被装的那一个不动它
            if f.suffix.lower() not in (".exe", ".bat", ".tmp", ".flag"):
                continue
            f.unlink()
            n += 1
        except OSError:
            continue        # 被占用（杀软还在扫它）就下一轮再说，别为了清理卡住启动
    return n


_VER_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.-]+))?(?:\+.*)?$")


def _loose(s: str):
    """认不出的形状退回"把数字全拽出来比"：老清单、手改过的地址、带前缀的标签，
    都不该让一次检查更新整个报错。"""
    nums = tuple(int(n) for n in re.findall(r"\d+", (s or "").split("+")[0])[:4])
    return nums or (0,)


def _pre_key(pre: str):
    """预发布段按 semver 的规则比：点号切开，纯数字段按数值、其余按字符串，
    数字段排在字母段前面。"""
    return [(0, int(p), "") if p.isdigit() else (1, 0, p) for p in pre.split(".")]


def cmp_ver(a: str, b: str) -> int:
    """a 比 b：>0 表示 a 更新。两边都先过 norm_tag（v1.2.3 → 1.2.3）。

    以前直接把整串里的数字拽出来比，于是 1.3.0-rc1 变成 (1,3,0,1) —— 比正式版
    1.3.0 的 (1,3,0) **大**：正式版发出去之后，已在 1.3.0 的人会被推荐回那个 rc，
    点下去就是一次降级安装。semver 的规则正好相反：同号时带预发布段的那一边更旧。
    """
    na, nb = norm_tag(a), norm_tag(b)
    ma, mb = _VER_RE.match(na), _VER_RE.match(nb)
    if not ma or not mb:
        ta, tb = _loose(na), _loose(nb)
        return (ta > tb) - (ta < tb)
    core_a = tuple(int(x) for x in ma.groups()[:3])
    core_b = tuple(int(x) for x in mb.groups()[:3])
    if core_a != core_b:
        return 1 if core_a > core_b else -1
    pa, pb = ma.group(4), mb.group(4)
    if pa and not pb:
        return -1          # 1.3.0-rc1 < 1.3.0
    if pb and not pa:
        return 1
    if not pa and not pb:
        return 0
    ka, kb = _pre_key(pa), _pre_key(pb)
    if ka != kb:
        return 1 if ka > kb else -1
    # 前缀相同、一边更长的那条更新（semver 的 1.0.0-alpha < 1.0.0-alpha.1）
    return (len(ka) > len(kb)) - (len(ka) < len(kb))


def is_newer(latest: str, local: str = APP_VERSION) -> bool:
    return cmp_ver(latest, local) > 0


def snapshot() -> dict:
    with _LOCK:
        out = dict(STATE)
    out["update_url"] = update_url()
    out["configured"] = True
    out["default_url"] = DEFAULT_UPDATE_URL
    return out


def _set(**kw):
    with _LOCK:
        STATE.update(kw)


def norm_tag(s: str) -> str:
    """去掉版本号前的 v。只认 v+数字（v1.2.3），否则 vault-client 会被削成 ault-client。"""
    return re.sub(r"^[vV](?=\d)", "", (s or "").strip())


def check(force: bool = False) -> dict:
    """问一次清单。已经拿到结果且不是 force 就直接回缓存，避免每次轮询打网络。

    下载正在飞的时候连 force 也不问：一次检查会把 phase 改成 checking、
    再把进度 got 清成 0、把正在写的包路径 path 抹掉，进度条当场跳回原点，
    而后台那个线程还在往原路径里写 —— 看着像卡住，其实是状态被踩了。"""
    with _LOCK:
        # _LOCK 不是可重入的：绝不能在 with 里 return snapshot()，那自己等自己。
        downloading = STATE["phase"] == "downloading"
        cached = (not downloading and STATE["phase"] in ("available", "current")
                  and STATE["url"] and not force)
    if downloading or cached:
        return snapshot()
    _set(phase="checking", error="")
    try:
        resp = requests.get(update_url(), timeout=(8, 15),
                            headers={"User-Agent": "loom-updater"})
        if resp.status_code != 200:
            raise RuntimeError(f"更新清单返回 {resp.status_code}")
        m = resp.json()
        latest = norm_tag(str(m.get("version") or ""))
        if not latest:
            raise RuntimeError("清单里没有 version 字段")
        url = str(m.get("url") or "")
        if not url.startswith("https://"):
            raise RuntimeError("清单里的下载地址不是 https")
        newer = is_newer(latest)
        sha = str(m.get("sha256") or "").strip().lower()
        try:
            size = int(m.get("size") or 0)
        except (TypeError, ValueError):
            size = 0
        asset = Path(str(m.get("file") or "")).name or Path(url).name
        if newer:
            # 校验值缺失就不能进 available。清单地址是用户可改的（main.py 只拦协议、
            # 不锁域名），而 sha256 与 file 出自同一份清单 —— "有才校"等于没有校验，
            # 一个不写 sha256 的清单就能把任意 exe 标成"已下载可安装"。
            if len(sha) != 64 or any(c not in "0123456789abcdef" for c in sha):
                raise RuntimeError("更新清单没有给出有效的 sha256，拒绝下载")
            if size <= 0:
                raise RuntimeError("更新清单没有给出安装包大小，拒绝下载")
            # asset 只准是一个纯文件名，且必须与下载地址的末段一致：
            # 它会被拼进 updates_dir()，带 `..` 或绝对路径的清单能把包写到启动目录。
            if not asset.lower().endswith(".exe") or asset != Path(url).name:
                raise RuntimeError("更新清单里的文件名与下载地址对不上，拒绝下载")
        _set(phase="available" if newer else "current",
             latest=latest, notes=str(m.get("notes") or "")[:2000],
             url=url if newer else "",
             asset=asset if newer else "",
             mirrors=_manifest_mirrors(m, url, asset) if newer else [],
             sha256=sha if newer else "",
             size=size if newer else 0, got=0, path="",
             checked_at=time.strftime("%Y-%m-%d %H:%M:%S"))
    except Exception as e:
        _set(phase="error", error=str(e)[:300])
    return snapshot()


def _manifest_mirrors(m: dict, url: str, asset: str) -> list:
    """清单里的镜像列表 → 可用的候选。镜像只是"同一个包的另一个地址"，
    所以只收 https、且**文件名必须与主地址一致** —— 否则它就能把包换成别的东西、
    或者借路径把我们写到别处去。主地址自己、重复项、非字符串一律剔掉。
    上限 4 个：每多一个就多一次测速往返，收益早就没了。"""
    out = []
    for u in (m.get("mirrors") or []):
        if not isinstance(u, str):
            continue
        u = u.strip()
        if not u.startswith("https://") or u == url or u in out:
            continue
        if Path(urlparse(u).path).name != asset:
            continue
        out.append(u)
    return out[:4]


def _probe(url: str, timeout: float = 4.0, sample: int = 128 * 1024) -> float:
    """给一个源打分：拉一小段量吞吐（字节/秒）。失败返回 -1（排到最后，但仍会试）。

    只拉 128KB 就断开：目的是排序不是下载。有的源不认 Range、直接从头开始推整包，
    所以必须 stream=True + 及时 close，否则测一次速就把 36MB 都拉下来了。"""
    try:
        t0 = time.perf_counter()
        with requests.get(url, stream=True, timeout=(timeout, timeout),
                          headers={"User-Agent": "loom-updater",
                                   "Range": f"bytes=0-{sample - 1}"}) as r:
            if r.status_code not in (200, 206):
                return -1.0
            got = 0
            for chunk in r.iter_content(chunk_size=32 * 1024):
                got += len(chunk)
                if got >= sample:
                    break
        dt = max(time.perf_counter() - t0, 1e-3)
        return got / dt if got else -1.0
    except Exception:
        return -1.0


def _order_sources(urls: list) -> list:
    """按实测速度排序。只有一个源就直接返回 —— 没有"选"这回事，别多花一次往返。
    Python 的排序是稳定的，所以同样失败（-1）的那些保持原有顺序，等于退回清单顺序。"""
    urls = [u for u in urls if u]
    if len(urls) <= 1:
        return urls
    scored = [(u, _probe(u)) for u in urls]
    scored.sort(key=lambda t: t[1], reverse=True)
    return [u for u, _ in scored]


def _download_any(cands: list, dest: Path, expect: int, want_sha: str) -> None:
    """挨个源试，直到有一个下下来且**过了 sha256**。全试完还是不行就报最后一次的错。

    选源只决定顺序，不决定装什么：每个源下的东西都要过同一份 sha256，
    所以"哪边快用哪边"不会退化成"哪边给旧包用哪边"。"""
    last = ""
    for u in cands:
        _download(u, dest, expect, want_sha)
        if STATE.get("phase") == "ready":
            if len(cands) > 1:
                _set(error="")
            return
        last = STATE.get("error") or last
    _set(phase="error", error=(last or "下载失败")[:300], got=0)


def _download(url: str, dest: Path, expect: int, want_sha: str):
    got = 0
    h = hashlib.sha256()
    try:
        with requests.get(url, stream=True, timeout=(15, 120),
                          headers={"User-Agent": "loom-updater"}) as r:
            r.raise_for_status()
            with open(dest, "wb") as f:
                for chunk in r.iter_content(chunk_size=64 * 1024):
                    if not chunk:
                        continue
                    f.write(chunk)
                    h.update(chunk)
                    got += len(chunk)
                    _set(got=got)
        if expect and got != expect:
            raise RuntimeError(f"字节数对不上：收到 {got}，应为 {expect}")
        if want_sha and h.hexdigest().lower() != want_sha.lower():
            raise RuntimeError("sha256 校验不通过，安装包可能不完整")
        _set(phase="ready", got=got, path=str(dest))
    except Exception as e:
        try:
            dest.unlink(missing_ok=True)
        except Exception:
            pass
        _set(phase="error", error=str(e)[:300], got=0)


def start_download() -> dict:
    s = snapshot()
    if s["phase"] == "ready":
        return s
    if not s["url"]:
        _set(phase="error", error="没有可下载的更新，先检查版本")
        return snapshot()
    with _LOCK:
        alive = _DL.get("t")
        if alive and alive.is_alive():
            return dict(STATE)
    dest = updates_dir() / (s["asset"] or "update.exe")
    # check() 已经把 asset 收成纯文件名了，这里再兜一道：落点必须在 updates 目录内。
    # 两处都写是因为这两条路可以分开长 —— 只留一处，将来加个新入口就把它绕过去了。
    root = updates_dir().resolve()
    if not dest.resolve().is_relative_to(root):
        _set(phase="error", error="更新包目标路径不在更新目录内，已拒绝")
        return snapshot()
    _set(phase="downloading", got=0, error="", path=str(dest))
    # 主地址 + 清单给的镜像，按实测速度排；只有一个源时 _order_sources 直接返回，不测速。
    # 排序放在下载线程里做，免得测速那一两秒把 HTTP 请求卡住。
    def _run():
        c = _order_sources([s["url"]] + list(s.get("mirrors") or []))
        _download_any(c, dest, s["size"], s["sha256"])

    t = threading.Thread(target=_run, daemon=True, name="loom-update")
    _DL["t"] = t
    t.start()
    return snapshot()


BAT_TMPL = """@echo off
rem 更新脚本：等主进程真的收尾完成 -> 弹出安装向导 -> 装完把安装包和自己也删掉
rem 等的是"那个标记文件出现了"，不是"过了 N 秒"。以前是 ping 盲睡三秒，两头都不对：
rem 睡少了安装器撞上还没退出的程序，只能让 Inno 去请系统关应用（用户看到的弹窗）；
rem 睡多了进程早就没了还白等。
rem 为什么不是按 PID 轮询：tasklist 的输出要在批处理里解析，而这台机器上 PATH 里的
rem find 是 Git Bash 的 coreutils 版（实测直接把整段等待判成"进程已不在"）——
rem 一个装更新的东西不该把正确性押在 PATH 顺序和地区设置上。
rem 上限 20 次是防主进程压根没走到收尾（崩在退出路上）时永远卡住。
set "FLAG={flag}"
set /a tries=0
:wait
if exist "%FLAG%" goto :go
set /a tries+=1
if %tries% geq 20 goto :go
ping -n 2 127.0.0.1 >nul 2>&1
goto :wait
:go
del "%FLAG%" >nul 2>&1
rem 不再传那个"关应用"的开关：安装器不该伸手关别人的进程，我们自己已经退干净了。
rem 安装器直接当子进程调用，不用 start /wait：cmd 等子进程结束、退出码照实传回来。
rem 换这个不是因为它坏了（真 PE 桩下两种写法删/留都对），是少一个会骗人的环节：
rem start /wait 对批处理桩根本不返回，errorlevel 留空，判错那行当场语法错 ——
rem 哪天有人把这里指向一个 .cmd，它就是静默的错。
rem 不再静默：安装这一步交回给用户，弹出安装向导由他自己点「下一步」。
rem 以前带 /SILENT，用户全程看不到安装界面，也不知道装到哪一步。
rem 保留 /NORESTART 只是禁止安装器顺手重启系统；程序是否在装完自动启动由 iss 决定。
"{setup}" /NORESTART
if errorlevel 1 goto :keep
rem 只有装成功才删。这两行以前没有：以前只删脚本自己，那个 60MB 的 setup.exe
rem 一直躺在 data\\updates 里，每升一级多一个，而没有任何界面看得见它。
del "{setup}" >nul 2>&1
del "%~f0" >nul 2>&1
:keep
"""


_APPLY_STARTED = False
_QUIT_HOOK = None


def quit_flag_path() -> Path:
    return updates_dir() / "quit.flag"


def set_quit_hook(fn) -> None:
    """打包壳把"怎么干净退出"注册进来（销毁窗口 → webview.start() 返回 → 正常收尾）。

    没有这一步就只能 `os._exit`，那是跳过一切清理：WebView2 的子进程和本地服务
    都没被告知要收，安装目录里的文件锁就这么留着了。"""
    global _QUIT_HOOK
    _QUIT_HOOK = fn


def _signal_done() -> None:
    """告诉那个还在等的批处理："我这边收完了，可以换了"。"""
    try:
        p = quit_flag_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("done", encoding="ascii")
    except OSError:
        pass


def _quit() -> None:
    fn = _QUIT_HOOK
    if fn is None:
        # 退回浏览器那条路没有窗口可销毁，只能硬退。此时进程里没有 WebView2 子进程，
        # 残留的锁只有解释器自己加载的那几个，比有壳的情况轻得多。
        _signal_done()
        os._exit(0)
        return
    try:
        fn()
    except Exception:
        _signal_done()
        os._exit(0)


def _sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def apply_update() -> dict:
    """交给一个脱离本进程的批处理去跑安装器，然后我们自己退出。

    只在打包态可用：源码运行没有"被替换的 exe"，这里返回错误而不是演一遍。
    """
    global _APPLY_STARTED
    s = snapshot()
    if not s["frozen"]:
        return {"ok": False, "detail": "源码运行没有可替换的程序，请用安装包装新版本"}
    if _APPLY_STARTED:
        # 点两下不该起两个 BAT：第二个会去删第一个正在用的那个包。
        return {"ok": True, "message": "已经在装了，程序马上退出"}
    if s["phase"] != "ready" or not s["path"] or not Path(s["path"]).is_file():
        return {"ok": False, "detail": "还没有下载完成的安装包"}
    # ready 只是内存里的一个标志：从"校验通过"到"点安装"之间可以隔任意久，
    # 期间那个文件被截断、被换掉、或上次异常退出留下的同名残包，光判 is_file() 是发现不了的。
    # 所以执行前按清单里那份 sha256 重算一次 —— 这是这条链上唯一的落地前防线。
    want = str(s["sha256"] or "").lower()
    if not want:
        return {"ok": False, "detail": "缺少校验值，请重新检查更新"}
    try:
        if _sha256_of(Path(s["path"])) != want:
            try:
                Path(s["path"]).unlink(missing_ok=True)
            except OSError:
                pass
            _set(phase="error", error="安装包校验值已不匹配，已删除并停止安装")
            return {"ok": False, "detail": "安装包校验失败，请重新下载"}
    except OSError as e:
        return {"ok": False, "detail": f"读不到安装包：{e}"}
    exe = Path(sys.executable)
    bat = updates_dir() / "update.bat"
    flag = quit_flag_path()
    try:
        flag.unlink(missing_ok=True)      # 上一次没走到收尾留下的残旗，会把这一次直接放行
    except OSError:
        pass
    bat.write_text(BAT_TMPL.format(setup=str(s["path"]).replace('"', ""),
                                   flag=str(flag)), encoding="mbcs")
    flags = 0
    if os.name == "nt":
        # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW
        flags = 0x00000008 | 0x00000200 | 0x08000000
    _APPLY_STARTED = True
    # 进程真正要没了的最后一刻才举旗：atexit 跑在 webview.start() 返回、main() 走完
    # 之后，那时 WebView2 的子进程已经被拆掉，文件锁才是真的放了。
    atexit.register(_signal_done)
    try:
        subprocess.Popen(["cmd", "/C", str(bat)], creationflags=flags,
                         close_fds=True, cwd=str(paths.DATA_DIR))
    except Exception as e:
        _APPLY_STARTED = False
        return {"ok": False, "detail": f"启动安装程序失败：{e}"}
    # 延后一拍再退：这句要先进 HTTP 响应、前端要先把"正在安装"画出来，
    # 而销毁窗口必须在 UI 那条循环上跑，不能在请求线程里直接拆。
    threading.Timer(0.4, _quit).start()
    # detail 在这个应用里就是"出错"的键（前端一律 if(r.detail) 弹红条），
    # 成功那句话要是也放这儿，装上之后会看到一条红色报错。
    return {"ok": True, "message": f"正在安装并退出，稍后从 {exe.name} 重新启动即可"}
