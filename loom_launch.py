# -*- coding: utf-8 -*-
"""Jacquard 织流 · 打包后的桌面入口（源码运行仍用 python run.py）。

形态：后台线程跑 uvicorn，前台优先开 pywebview 原生窗口（Win10/11 的 WebView2）。
**开不出原生窗口就退回默认浏览器** —— 软件本体是个本地 Web 应用，
窗口壳只是体验差异，不该成为启动失败的理由。

其他行为：
  - 单实例：靠一个命名互斥体判定，**不是**靠端口占用 —— 端口占用只能说明
    "有人在这个口上"，说明不了那是不是 Jacquard（一台跑着开发服务的机器上，
    前者天天成立、后者未必）。已有实例时把它的窗口拉到前台并退出。
  - 冻结态 console=False 时 stdout/stderr 是 None：先重定向到内存流，
    否则任何一句 print 都会 AttributeError 把启动打断。
  - 启动异常弹原生消息框并落盘 data/boot-error.log，用户看得见、你查得到。

端口：LOOM_PORT（或默认 8000）只是**首选**，被占就往后找空闲的，找到才开。
桌面软件没有理由因为别人占了 8000 就打不开 —— 端口是实现细节，不是用户
要关心的东西。int 强校验后才拼进 URL。
"""
import io
import os
import socket
import sys
import threading
import time

WINDOW_TITLE = "织流 Jacquard"
DEFAULT_PORT = 8000


def _fix_streams():
    try:
        if sys.stdout is None:
            sys.stdout = io.StringIO()
        if sys.stderr is None:
            sys.stderr = io.StringIO()
    except Exception:
        pass


def _alert(msg: str):
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, msg, WINDOW_TITLE, 0x10)
    except Exception:
        pass


def _log_exc(kind, exc):
    try:
        import traceback
        from app import paths
        (paths.DATA_DIR / "boot-error.log").write_text(
            f"[{kind}] {exc}\n\n{traceback.format_exc()}", encoding="utf-8")
    except Exception:
        pass


def _port_busy(port: int) -> bool:
    s = socket.socket()
    s.settimeout(0.4)
    busy = s.connect_ex(("127.0.0.1", port)) == 0
    s.close()
    return busy


MUTEX_NAME = "Local\\LoomZhiLiu.SingleInstance"
_MUTEX_HANDLE = None      # 必须一直攥在手里：句柄一被回收，锁就散了，第二个实例会当成没人跑


def acquire_single_instance_lock() -> bool:
    """True = 这个进程是唯一的实例；False = 已经有 Jacquard 在跑。

    拿"端口能不能连"当单实例判据是错的：它既会误报（别的程序占了 8000，
    其实 Jacquard 没在跑），也会漏报（Jacquard 跑在 8001，端口判据看不见）。"""
    global _MUTEX_HANDLE
    try:
        import ctypes
        ERROR_ALREADY_EXISTS = 183
        ctypes.windll.kernel32.CreateMutexW.restype = wintypes_handle()
        handle = ctypes.windll.kernel32.CreateMutexW(None, False, MUTEX_NAME)
        if not handle:
            return True                      # 拿不到句柄就别拦人，照常启动
        _MUTEX_HANDLE = handle
        return ctypes.windll.kernel32.GetLastError() != ERROR_ALREADY_EXISTS
    except Exception:
        return True


def wintypes_handle():
    import ctypes
    return ctypes.c_void_p


def focus_existing() -> bool:
    """把已经在跑的那个实例的窗口带到前台。

    按标题找是对的，但必须排掉自己 —— 而且不能用 FindWindowW：它连不可见的
    窗口一起找，也会撞上另一个实例弹出来的错误框（那个框的标题就是同一串字）。
    所以自己枚举：只认「可见 + 标题匹配 + 不是本进程」。"""
    try:
        import ctypes
        user32 = ctypes.windll.user32
        found = []
        me = os.getpid()
        Proc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

        @Proc
        def cb(hwnd, _lparam):
            if not user32.IsWindowVisible(hwnd):
                return True
            n = user32.GetWindowTextLengthW(hwnd)
            if not n:
                return True
            buf = ctypes.create_unicode_buffer(n + 1)
            user32.GetWindowTextW(hwnd, buf, n + 1)
            if buf.value != WINDOW_TITLE:
                return True
            pid = ctypes.c_ulong()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value != me:
                found.append(hwnd)
            return True

        user32.EnumWindows(cb, 0)
        if not found:
            return False
        hwnd = found[0]
        SW_RESTORE = 9
        user32.ShowWindow(hwnd, SW_RESTORE)
        user32.SetForegroundWindow(hwnd)
        return True
    except Exception:
        return False


def _port_free(port: int) -> bool:
    """用 bind 而不是 connect：connect 只问"有没有人在监听"，bind 才问
    "这个口我现在能不能拿到"，后者才是我们要的。"""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", port))
        return True
    except OSError:
        return False
    finally:
        s.close()


def pick_port(preferred: int, tries: int = 24) -> int:
    """首选口被占就往后找；连找 24 个都不空就交给系统随机发一个（0 = 让内核挑）。
    走到最后一步仍然能开起来，只是端口不再好看。"""
    for port in range(preferred, preferred + tries):
        if _port_free(port):
            return port
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]
    finally:
        s.close()


def _validated_port() -> int:
    raw = os.environ.get("LOOM_PORT") or str(DEFAULT_PORT)
    port = int(raw)
    if not 0 < port < 65536:
        raise ValueError("LOOM_PORT 取值非法（1-65535）")
    return port


def _serve(port: int):
    import uvicorn
    from app.main import app
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


def _wait_ready(port: int, timeout: float = 40.0) -> bool:
    t0 = time.time()
    while time.time() - t0 < timeout:
        if _port_busy(port):
            return True
        time.sleep(0.4)
    return False


def _open_in_browser(port: int):
    import webbrowser
    webbrowser.open(f"http://127.0.0.1:{int(port)}")


# 无边框窗口：页面上能碰窗口的只有这一个对象、六个动作。它不读磁盘、不起进程、
# 不碰任何业务数据 —— 窗口控制被放进 Web 页面时，这条面必须小到能一眼看完。
def _anchor(edge: str, FixPoint):
    """拖哪条边，就把对侧那个角钉住。"""
    return {
        "e": FixPoint.NORTH | FixPoint.WEST,
        "s": FixPoint.NORTH | FixPoint.WEST,
        "se": FixPoint.NORTH | FixPoint.WEST,
        "w": FixPoint.NORTH | FixPoint.EAST,
        "n": FixPoint.SOUTH | FixPoint.WEST,
        "ne": FixPoint.SOUTH | FixPoint.WEST,
        "nw": FixPoint.SOUTH | FixPoint.EAST,
        "sw": FixPoint.NORTH | FixPoint.EAST,
    }.get((edge or "se").strip().lower(), FixPoint.NORTH | FixPoint.WEST)


class ShellApi:
    """只给页面挂这五枚方法。

    成员一律以下划线开头：pywebview 扫 js_api 时按 `dir()` 走，非下划线的属性若是
    对象就**递归进去**（webview/util.py 的 get_functions）。以前那个公开的
    `self.window` 因此被一路递归进 WinForms 的 .NET 对象图，日志刷出 4.2 MB
    `Error while processing window.native.DefaultFont.FontFamily...`，最后
    `logger.error` 自己在还栈没恢复时又炸，注入给页面的 api 直接变成空对象 ——
    三枚窗控按不动，而且没有任何一处显式报错。
    """

    def __init__(self):
        self._window = None
        # Window.maximized 是 create_window 的那个入参，winforms 后端从不回写它。
        # 打包态用 CDP 连点两次最大化实测：状态位恒为 False，第二次不还原、图标也
        # 永远停在"最大化"。真状态只在 events.maximized / restored 里，得自己接。
        self._max = False

    def _attach(self, win):
        self._window = win
        win.events.maximized += lambda: setattr(self, "_max", True)
        win.events.restored += lambda: setattr(self, "_max", False)

    def win_minimize(self):
        self._window.minimize()

    def win_maximize_toggle(self):
        # 这里必须自己判：WinForms 的 maximize 再调一次不会还原。
        if self._max:
            self._window.restore()
        else:
            self._window.maximize()

    def win_close(self):
        self._window.destroy()

    def win_resize(self, w, h, edge="se"):
        from webview.window import FixPoint
        self._window.resize(int(w), int(h), _anchor(edge, FixPoint))

    def win_state(self):
        return {"shell": "pywebview", "maximized": self._max}


def _run_window(port: int) -> bool:
    """开原生窗口；返回 False 表示这条路口前不可用，调用方退回浏览器。

    frameless 之后系统标题栏没了，最小化/最大化/关闭由页面顶部那一条画 ——
    所以窗口控制走 js_api。原生壳起不来就退回浏览器，那条路上没有 bridge，
    页面自己会把那三枚按钮藏掉（不给按不动的假按钮）。"""
    try:
        import webview
        api = ShellApi()
        win = webview.create_window(WINDOW_TITLE, f"http://127.0.0.1:{int(port)}",
                                    width=1440, height=900, min_size=(980, 620),
                                    frameless=True, easy_drag=True, js_api=api)
        api._attach(win)
        webview.start()
        return True
    except Exception as e:
        _log_exc("webview", e)
        return False


def main():
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    _fix_streams()
    try:
        preferred = _validated_port()
    except ValueError as e:
        _alert(str(e))
        return 2

    if not acquire_single_instance_lock():
        # 已经有实例在跑：把它的窗口带回来，本进程退出。拉不到窗口也照样退出 ——
        # 再起一份就是两个进程写同一个 SQLite，那比"双击没反应"难查得多。
        focus_existing()
        return 0

    port = pick_port(preferred)

    # 建表 / 补列 / 收上一世留下的"正在跑"，必须在主线程、且在这儿就发生。
    # 以前它是 _serve 那条线程 import app.main 时顺带做的，于是数据库起不来时
    # 异常死在线程里：主线程只看见端口一直没通，40 秒后弹"启动超时"，
    # boot-error.log 一个字都没写 —— 真实原因（磁盘满、目录没权限、一次失败的
    # 列迁移）就这么被吞了。init_db 是幂等的，显式叫一次不是多余动作。
    try:
        from app import db, updater
        db.init_db()
        updater.sweep_leftovers()
    except Exception as e:
        _log_exc("db", e)
        _alert(f"数据目录打不开：{e}\n\n详情见安装目录 data\\boot-error.log")
        return 3

    url = f"http://127.0.0.1:{port}"
    print(f"Jacquard 织流 启动 {url}")
    try:
        threading.Thread(target=_serve, args=(port,), daemon=True).start()
    except Exception as e:
        _log_exc("serve", e)
        _alert("本地服务线程启动失败。\n\n详情见安装目录 data\\boot-error.log")
        return 1

    if not _wait_ready(port):
        _alert("本地服务启动超时（40 秒）。\n\n详情见安装目录 data\\boot-error.log")
        return 1
    time.sleep(0.6)                      # 端口通了再留一拍给应用完成初始化

    if _run_window(port):
        return 0
    # 原生窗口不可用：开浏览器，主线程挂住不让守护线程随进程退出
    _open_in_browser(port)
    threading.Event().wait()


if __name__ == "__main__":
    sys.exit(main())
