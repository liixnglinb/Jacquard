# -*- coding: utf-8 -*-
"""E2E 冒烟的 pytest 包装：真起服务（临时数据沙箱）→ node 起 Edge 跑 → 断言全过。

依赖两样可选的东西，缺了就 **跳过**（给出接法），不挂红：
  1. node 在 PATH；
  2. node_modules/playwright-core 可解析（一次性接法见 README「端到端测试」）。
数据目录走 FF_DATA_DIR 指进 pytest 的 tmp_path —— E2E 真增真删，绝不碰开发机数据。
"""
import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SMOKE = ROOT / "tests" / "e2e_smoke.mjs"


def _node_ok() -> bool:
    try:
        subprocess.run(["node", "--version"], capture_output=True, timeout=15)
        return True
    except Exception:
        return False


def _pw_ok() -> bool:
    return (ROOT / "node_modules" / "playwright-core" / "package.json").is_file() or \
           bool(os.environ.get("FF_PW_DIR")) and \
           (Path(os.environ["FF_PW_DIR"]) / "playwright-core" / "package.json").is_file()


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _wait_health(base: str, timeout: float = 40.0) -> None:
    dead = time.time() + timeout
    while time.time() < dead:
        try:
            with urllib.request.urlopen(base + "/api/health", timeout=2) as r:
                if r.status == 200:
                    return
        except Exception:
            time.sleep(0.4)
    raise RuntimeError("服务 40 秒内没起来")


@pytest.mark.skipif(not SMOKE.is_file(), reason="tests/e2e_smoke.mjs 不在")
@pytest.mark.skipif(not _node_ok(), reason="PATH 上没有 node —— E2E 跳过（接法见 README「端到端测试」）")
@pytest.mark.skipif(not _pw_ok(), reason="node_modules/playwright-core 不可解析 —— E2E 跳过（接法见 README「端到端测试」）")
def test_e2e_smoke(tmp_path):
    port = _free_port()
    base = f"http://127.0.0.1:{port}"
    env = {**os.environ,
           "FF_DATA_DIR": str(tmp_path / "data"),
           "PYTHONIOENCODING": "utf-8"}
    if os.environ.get("FF_PW_DIR"):
        env["FF_PW_DIR"] = os.environ["FF_PW_DIR"]
    proc = subprocess.Popen([sys.executable, str(ROOT / "run.py"), "--port", str(port)],
                            cwd=str(ROOT), env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        _wait_health(base)
        r = subprocess.run(["node", str(SMOKE), "--base", base],
                           cwd=str(ROOT), env=env, capture_output=True,
                           text=True, encoding="utf-8", timeout=240)
        tail = (r.stdout or "")[-1500:]
        assert r.returncode == 0, f"E2E 冒烟失败（exit {r.returncode}）：\n{tail}\n{r.stderr[-400:]}"
        line = [ln for ln in (r.stdout or "").splitlines() if ln.strip().startswith("{")]
        data = json.loads(line[-1]) if line else {}
        assert data.get("pass") is True, f"E2E 冒烟未全过：{json.dumps(data, ensure_ascii=False)[:1200]}"
    finally:
        subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                       capture_output=True, timeout=30)
