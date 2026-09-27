# -*- coding: utf-8 -*-
"""Loom 织流 启动脚本（端口自愈 + 中文诊断）。

用法: python run.py [--port 8000] [--auto-kill]
"""
import os
import re
import socket
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

DEFAULT_PORT = 8000


def is_port_busy(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.4)
        return s.connect_ex((host, port)) == 0


def find_pid_by_port(port: int):
    try:
        r = subprocess.run(
            ["netstat", "-ano"], capture_output=True, text=True, timeout=10,
            encoding="utf-8", errors="replace")
        pids = set()
        pat = re.compile(rf":{port}\s+.*LISTENING\s+(\d+)", re.IGNORECASE)
        for line in r.stdout.splitlines():
            m = pat.search(line)
            if m:
                pids.add(m.group(1))
        return list(pids)
    except Exception:
        return []


def try_kill_pids(pids):
    killed = []
    for pid in pids:
        try:
            subprocess.run(["taskkill", "/F", "/PID", str(pid)],
                           capture_output=True, timeout=10)
            killed.append(pid)
        except Exception:
            pass
    return killed


def diagnose_start_error(err) -> str:
    s = str(err)
    if "10048" in s.lower() or "address already in use" in s.lower() or "bind" in s.lower():
        return ("端口被其他程序占用。可：① 运行 python run.py --auto-kill 自动释放；"
                "② 或 python run.py --port 8001 换端口启动。")
    if "module" in s.lower() and "not found" in s.lower():
        m = re.search(r"No module named '([^']+)'", s)
        name = m.group(1) if m else "?"
        return f"缺少 Python 依赖模块：{name}。请运行：pip install {name}"
    if "permission" in s.lower() or "access is denied" in s.lower():
        return "权限不足，请以管理员身份运行，或更换大于 1024 的端口。"
    if "syntaxerror" in s.lower():
        return "后端代码存在语法错误，请检查 app/ 下各 .py 文件。"
    return f"启动失败：{s}"


STALE_HINT = "检测到旧 Jacquard 进程仍占用端口，正在自动结束并重启…"


def main():
    port = DEFAULT_PORT
    auto_kill = False
    argv = sys.argv[1:]
    for i, a in enumerate(argv):
        if a == "--auto-kill":
            auto_kill = True
        elif a in ("--port", "-p") or a.startswith("--port="):
            raw = a.split("=", 1)[1] if "=" in a else (argv[i + 1] if i + 1 < len(argv) else "")
            try:
                port = int(raw)
            except ValueError:
                print(f"ERROR: --port 需要数字端口，收到「{raw}」")
                sys.exit(1)
    import importlib.util
    if not importlib.util.find_spec("uvicorn"):
        print("ERROR: 未安装 uvicorn。请运行: pip install fastapi uvicorn python-multipart")
        sys.exit(1)

    if is_port_busy("127.0.0.1", port):
        pids = find_pid_by_port(port)
        if pids:
            if auto_kill:
                print(STALE_HINT)
                try_kill_pids(pids)
                import time
                time.sleep(1)
            else:
                print(f"⚠ 端口 {port} 已被占用 (PID: {', '.join(pids)})")
                print("   自动释放： python run.py --auto-kill")
                print("   换端口：   python run.py --port <新端口>")
                ans = input("   是否自动结束这些进程并继续？[Y/n]: ").strip().lower()
                if ans not in ("n", "no"):
                    print(STALE_HINT)
                    try_kill_pids(pids)
                    import time
                    time.sleep(1)
                else:
                    sys.exit(1)
        else:
            print(f"⚠ 端口 {port} 被非进程程序占用（可能需关闭其它软件）。")
            print("   换端口启动： python run.py --port <新端口>")
            sys.exit(1)

    import uvicorn
    print(f"Jacquard 织流 启动: http://127.0.0.1:{port}")
    try:
        uvicorn.run("app.main:app", host="127.0.0.1", port=port, reload=False)
    except Exception as e:
        print("=" * 56)
        print("⚠ " + diagnose_start_error(e))
        print("=" * 56)
        sys.exit(1)


if __name__ == "__main__":
    main()
