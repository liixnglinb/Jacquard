# -*- coding: utf-8 -*-
"""智能体执行引擎：流程步骤一律交给本机 CLI 智能体执行（Claude Code / Codex）。

约定：API 端点/密钥/模型属于「智能体的接入配置」，本模块不直连 HTTP 跑正文。
预设里填了值就注入为 CLI 的环境变量或启动参数；留空则沿用该 CLI 在本机的
既有登录/代理配置（多数用户就是这种情形）。

统一事件流（回调 emit 收到 dict）：
  {"type":"status","text":...}   生命周期（启动/会话结束）
  {"type":"tool","name":...,"preview":...} 智能体调用工具
  {"type":"delta","text":...}    正文增量
  {"type":"note","text":...}     思考/命令输出等辅助信息
返回：{"text","ok","rc","turns","duration_ms","cost_usd","tools","engine","error"}
"""
import json
import os
import queue
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

ENGINES = ("claude", "codex")
DEFAULT_TIMEOUT = int(os.environ.get("FLOWFORGE_AGENT_TIMEOUT", "2700"))
SANDBOXES = ("read-only", "workspace-write", "danger-full-access")
# 打包版是 loom.spec 的 console=False，也就是一个没有控制台的 GUI 进程。GUI 进程去起
# 控制台子进程（npm 的 .cmd 垫片会被 _argv 包成 `cmd.exe /c …`），Windows 就新建一个
# 控制台窗口 —— 那就是"每次开软件都弹黑窗"。capture_output=True 只接管管道，
# **不抑制控制台分配**，所以它给不了保护。0 是非 Windows 上的无害默认值。
NO_WINDOW = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0


def _tok_add(dst: dict, usage: dict) -> dict:
    """把两家 CLI 的 usage 归到一套互不重叠的键上，缺哪个跳过哪个。

    字段名和包含关系是从本机装好的 CLI 里抠出来的，不是照文档猜的：
      codex  TokenUsage = input_tokens, cached_input_tokens, cache_write_input_tokens,
             output_tokens, reasoning_output_tokens, total_tokens
             —— input_tokens 已经含 cached，另有一个 net_new_input_tokens 表示净增。
      claude result.usage = input_tokens, output_tokens, cache_read_input_tokens,
             cache_creation_input_tokens —— 这四段彼此不相交，事件里没有 total。
    所以只有 codex 要把缓存从输入里减掉，否则 total 会把缓存算两遍。
    reason 永远是 output 的一段，只做明细，不进 total。
    """
    u = usage or {}

    def num(key: str) -> int:
        v = u.get(key)
        return int(v) if isinstance(v, (int, float)) else 0

    cached = num("cached_input_tokens") or num("cache_read_input_tokens")
    write = num("cache_write_input_tokens") or num("cache_creation_input_tokens")
    inp = num("input_tokens")
    if "cached_input_tokens" in u:
        # codex 的 input_tokens 把读缓存和写缓存都含在里面（所以才另有
        # net_new_input_tokens 表示净增）。两头都要减，只减一头的话 total 会
        # 比 CLI 自报的 total_tokens 多出写缓存那一截。
        inp = max(0, inp - cached - write)
    parts = {
        "in": inp,
        "out": num("output_tokens"),
        "cache_read": cached,
        "cache_write": write,
        "reason": num("reasoning_output_tokens"),
    }
    for k, v in parts.items():
        if v:
            dst[k] = dst.get(k, 0) + v
    dst["total"] = (dst.get("in", 0) + dst.get("out", 0)
                    + dst.get("cache_read", 0) + dst.get("cache_write", 0))
    return dst


def _setting(key: str, default: str = "") -> str:
    try:
        from . import db
        v = (db.get_setting(key) or "").strip()
        return v or default
    except Exception:
        return default


def step_timeout() -> int:
    """单步超时（秒）：设置页可改，非法值回落到默认。"""
    try:
        v = int(_setting("agent_timeout") or DEFAULT_TIMEOUT)
        return v if 60 <= v <= 21600 else DEFAULT_TIMEOUT
    except (TypeError, ValueError):
        return DEFAULT_TIMEOUT


def codex_sandbox() -> str:
    v = _setting("codex_sandbox") or os.environ.get("FLOWFORGE_CODEX_SANDBOX") or "workspace-write"
    return v if v in SANDBOXES else "workspace-write"


# 输入台那三档权限模式。取值直接沿用 claude --permission-mode 的枚举名，
# 到 codex 再翻译成沙箱档 —— 少造一层词就少一处会写错的地方。
# claude 其实还认 manual / dontAsk / auto：manual 要我们提供"回答提问"的回调工具，
# 而 codex 的 exec 模式压根没有回通道，所以这三档刻意不开（宁可不给，不给假的）。
PERM_MODES = ("plan", "acceptEdits", "bypassPermissions")
_PERM_TO_SANDBOX = {"plan": "read-only",
                    "acceptEdits": "workspace-write",
                    "bypassPermissions": "danger-full-access"}


def permission_mode() -> str:
    """'' = 没选，两家沿用各自现状。非法值同样退回 ''，绝不拼半截参数出去噎住 CLI。"""
    v = _setting("permission_mode") or ""
    return v if v in PERM_MODES else ""


EFFORTS = ("minimal", "low", "medium", "high")


def reasoning_effort() -> str:
    """codex 的推理力度；设置里 auto 表示不干预 CLI 自身默认。"""
    v = _setting("reasoning_effort") or "auto"
    return v if v in EFFORTS else "auto"


def step_retry() -> int:
    """单步失败后的自动重试次数。"""
    try:
        v = int(_setting("step_retry") or 0)
        return v if 0 <= v <= 3 else 0
    except (TypeError, ValueError):
        return 0


def auto_continue() -> bool:
    """全自动：过了检查点不停顿，把整条流程一次推到底。"""
    return (_setting("auto_continue") or "0") == "1"


# Anthropic 兼容端点特征串：claude 引擎只认这类地址
_ANTHROPIC_HINTS = ("/anthropic", "/apps/anthropic", "/claudecode", "/api/coding",
                    "/api/anthropic", "/coding", "/tokenplan/personal")

_BIN_CACHE: dict = {}
_VER_CACHE: dict = {}


def protocol_ok(engine: str, provider: str = "", api_base: str = "") -> bool:
    """该预设的协议能不能喂给这个引擎。留空端点一律放行（用 CLI 自身配置）。"""
    base = (api_base or "").strip().lower()
    prov = (provider or "").strip().lower()
    if not base and not prov:
        return True
    if engine == "claude":
        if prov and prov != "anthropic":
            return any(h in base for h in _ANTHROPIC_HINTS)
        return True
    # codex 只会说 OpenAI 的 responses/chat 协议
    return prov in ("", "openai")


def resolve_binary(engine: str) -> str:
    """定位 CLI 可执行文件（Windows 下 npm 分发的是 .cmd，必须走 which）。"""
    if engine in _BIN_CACHE:
        return _BIN_CACHE[engine]
    settings_name = {"claude": "claude_cli", "codex": "codex_cli"}.get(engine, "")
    raw = ""
    if settings_name:
        try:
            from . import db
            raw = (db.get_setting(settings_name) or "").strip()
        except Exception:
            raw = ""
    found = ""
    if raw and Path(raw).is_file():
        found = raw
    else:
        found = shutil.which(raw or engine) or ""
    _BIN_CACHE[engine] = found
    return found


def clear_bin_cache():
    _BIN_CACHE.clear()
    _VER_CACHE.clear()


def _argv(engine_bin: str, args: list) -> list:
    """npm 的 .cmd/.bat 垫片不能直接 CreateProcess，统一用 cmd.exe /c 包一层。"""
    low = engine_bin.lower()
    if os.name == "nt" and low.endswith((".cmd", ".bat")):
        return ["cmd.exe", "/c", engine_bin, *args]
    return [engine_bin, *args]


def _probe_version(engine: str) -> str:
    if engine in _VER_CACHE:
        return _VER_CACHE[engine]
    b = resolve_binary(engine)
    if not b:
        return ""
    try:
        r = subprocess.run(_argv(b, ["--version"]), capture_output=True, text=True,
                           timeout=25, encoding="utf-8", errors="replace",
                           creationflags=NO_WINDOW)
        ver = (r.stdout or r.stderr or "").strip().splitlines()
        _VER_CACHE[engine] = ver[0][:60] if ver else ""
    except Exception as e:
        _VER_CACHE[engine] = f"err:{e}"
    return _VER_CACHE[engine]


def agents_status() -> list:
    """设置页/编排器用：每个引擎是否可用、路径、版本、协议要求。"""
    out = []
    for eng in ENGINES:
        b = resolve_binary(eng)
        info = {"engine": eng, "bin": b, "found": bool(b), "version": "",
                "needs": ("Anthropic 兼容端点（留空则用 CLI 自身登录）" if eng == "claude"
                          else "OpenAI 兼容端点 /v1（留空则用 CLI 自身登录）")}
        if b:
            info["version"] = _probe_version(eng)
        out.append(info)
    return out


class AgentError(Exception):
    """执行失败。log 指向已经落盘的那份现场转录（如果有），供 UI 诊断用。"""

    def __init__(self, msg: str, log: str = ""):
        super().__init__(msg)
        self.log = log


class AgentCancelled(Exception):
    """调用方（runner）请求中止；必须原样穿透，不能被当成执行失败。"""
    pass


def _kill_tree(proc):
    if proc is None or proc.poll() is not None:
        return
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                           capture_output=True, timeout=20, creationflags=NO_WINDOW)
        else:
            proc.kill()
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


def _stdout_reader(proc, q):
    try:
        for line in proc.stdout:
            q.put(line)
    except Exception as e:
        q.put(f"__READ_ERR__ {e}")
    finally:
        q.put(None)


def _pump(q, deadline):
    """取一行 stdout；到点返回 None（由调用方判超时）。"""
    while True:
        left = deadline - time.time()
        if left <= 0:
            return "__TIMEOUT__"
        try:
            item = q.get(timeout=min(2.0, left))
        except queue.Empty:
            continue
        return item


def _emit(emit, ev: dict):
    if emit is None:
        return
    try:
        emit(ev)
    except AgentCancelled:
        raise
    except Exception:
        pass


# ==================== Claude Code CLI ====================
def _claude_args(ws: Path, system_file: Path | None, model: str, isolated: bool) -> list:
    mode = permission_mode()
    args = ["-p", "--output-format", "stream-json", "--verbose"]
    if mode:
        args += ["--permission-mode", mode]
    else:
        args += ["--dangerously-skip-permissions"]
    if isolated:
        # 只有我们自己注入端点时才隔离用户配置；否则用户的 settings.json 里
        # 存着 ANTHROPIC_BASE_URL / 登录态，剥掉会直接「Not logged in」。
        args += ["--setting-sources", "project"]
    if system_file:
        args += ["--append-system-prompt-file", str(system_file)]
    if model:
        args += ["--model", model]
    return args


def _claude_env(api_base: str, api_key: str) -> dict:
    env = dict(os.environ)
    base = (api_base or "").strip()
    key = (api_key or "").strip()
    if base:
        low = base.lower()
        if not (any(h in low for h in _ANTHROPIC_HINTS) or low.endswith("/messages")
                or "127.0.0.1" in low or "localhost" in low):
            raise AgentError(
                f"claude 引擎只接受 Anthropic 兼容端点，当前填的是「{base}」。"
                "请改用 …/anthropic 形式的地址，或把该步切到 codex 引擎。")
        env["ANTHROPIC_BASE_URL"] = base
    if key:
        env["ANTHROPIC_API_KEY"] = key
        env["ANTHROPIC_AUTH_TOKEN"] = key
    return env


def _claude_events(ev: dict, emit, state: dict):
    kind = ev.get("type")
    if kind == "system":
        sub = ev.get("subtype")
        if sub == "init":
            _emit(emit, {"type": "status",
                         "text": f"Claude 会话启动 · model={ev.get('model', '?')}"})
        elif sub == "api_retry":
            n = ev.get("attempt")
            _emit(emit, {"type": "status",
                         "text": f"端点重试 {n}/{ev.get('max_retries', '?')} · "
                                 f"{str(ev.get('error') or '')[:60]} · "
                                 f"{round((ev.get('retry_delay_ms') or 0)/1000)} 秒后再试"})
        return
    if kind == "assistant":
        for blk in (ev.get("message") or {}).get("content") or []:
            btype = blk.get("type")
            if btype == "text":
                text = (blk.get("text") or "").strip()
                if text:
                    state["texts"].append(text)
                    _emit(emit, {"type": "delta", "text": text + "\n\n"})
            elif btype == "tool_use":
                state["tools"] += 1
                _emit(emit, {"type": "tool", "name": blk.get("name") or "tool",
                             "preview": _arg_preview(blk.get("input"))})
        msg = ev.get("message") or {}
        if msg.get("error"):
            state["error"] = str(msg.get("error"))[:200]
        return
    if kind == "result":
        state["final"] = ev.get("result") or state["final"]
        state["is_error"] = bool(ev.get("is_error"))
        state["turns"] = ev.get("num_turns") or state["turns"]
        state["duration_ms"] = ev.get("duration_ms")
        state["cost_usd"] = ev.get("total_cost_usd")
        if isinstance(ev.get("usage"), dict):
            state["tok_total"] = _tok_add({}, ev["usage"])
        if state["is_error"]:
            state["error"] = (str(ev.get("result") or "").strip()
                              or str(ev.get("terminal_reason") or "")
                              or state["error"] or "claude 返回失败")[:300]
        tail = (f"会话结束：{state['turns'] or 0} 轮 · "
                f"{round((state['duration_ms'] or 0) / 1000)} 秒 · "
                f"{'失败' if state['is_error'] else '成功'}")
        if state["is_error"] and state["error"]:
            tail += f" · {state['error'][:120]}"
        elif state.get("cost_usd"):
            tail += f" · ${state['cost_usd']:.4f}"
        _emit(emit, {"type": "status", "text": tail})


# ==================== Codex CLI ====================
_CODEX_PROVIDER = "flowforge"


def _codex_args(ws: Path, system_file: Path | None, model: str,
                api_base: str, api_key: str, wire_api: str) -> list:
    # 选了模式就以它为准；没选才退回旧的 codex_sandbox 存值（默认 workspace-write，即今天的行为）。
    mode = permission_mode()
    sandbox = _PERM_TO_SANDBOX[mode] if mode else codex_sandbox()
    args = ["exec", "--json", "--skip-git-repo-check", "--cd", str(ws), "-s", sandbox]
    if sandbox == "workspace-write":
        # workspace-write 沙箱默认掐断网络，调研类步骤会整步废掉
        args += ["-c", "sandbox_workspace_write.network_access=true"]
    if api_base.strip():
        base = api_base.strip().rstrip("/")
        if not base.endswith("/v1"):
            base += "/v1"
        args += [
            "-c", f'model_provider="{_CODEX_PROVIDER}"',
            "-c", f'model_providers.{_CODEX_PROVIDER}.name="Jacquard"',
            "-c", f'model_providers.{_CODEX_PROVIDER}.base_url="{base}"',
            "-c", f'model_providers.{_CODEX_PROVIDER}.env_key="FLOWFORGE_API_KEY"',
            # 0.154 的 codex 直接拒绝 chat：二进制里写着
            # `wire_api = "chat"` is no longer supported / set `wire_api = "responses"`。
            # 用户在预设里显式填了别的值就以他的为准（错误会原样出现在运行日志里）。
            "-c", f'model_providers.{_CODEX_PROVIDER}.wire_api="{wire_api or "responses"}"',
        ]
    if model.strip():
        args += ["-c", f'model="{model.strip()}"']
    effort = reasoning_effort()
    if effort != "auto":
        args += ["-c", f'model_reasoning_effort="{effort}"']
    return args


def _codex_env(api_base: str, api_key: str) -> dict:
    env = dict(os.environ)
    if api_base.strip() and api_key.strip():
        env["FLOWFORGE_API_KEY"] = api_key.strip()
    return env


def _codex_events(ev: dict, emit, state: dict):
    kind = ev.get("type")
    if kind == "thread.started":
        _emit(emit, {"type": "status", "text": "Codex 会话启动"})
        return
    if kind == "item.completed":
        item = ev.get("item") or {}
        itype = item.get("type")
        if itype == "agent_message":
            text = (item.get("text") or "").strip()
            if text:
                state["texts"].append(text)
                state["final"] = text
                _emit(emit, {"type": "delta", "text": text + "\n\n"})
        elif itype == "command_execution":
            state["tools"] += 1
            _emit(emit, {"type": "tool", "name": "shell",
                         "preview": (item.get("command") or "")[:200]})
        elif itype == "file_change":
            chs = item.get("changes") or []
            names = ", ".join((c.get("path") or c.get("path", "")) for c in chs[:4])
            state["tools"] += 1
            _emit(emit, {"type": "tool", "name": "files", "preview": names[:200]})
        elif itype == "reasoning":
            txt = (item.get("text") or "").strip().replace("\n", " ")
            if txt:
                _emit(emit, {"type": "note", "text": txt[:300]})
        return
    if kind == "token_count":
        info = ev.get("info") or {}
        tot = info.get("total_token_usage")
        if isinstance(tot, dict):
            state["tok_total"] = _tok_add({}, tot)
        return
    if kind == "turn.completed":
        usage = ev.get("usage") or {}
        _tok_add(state["tok"], usage)
        state["turns"] = (state["turns"] or 0) + 1
        _emit(emit, {"type": "status",
                     "text": f"Codex 回合结束 · in={usage.get('input_tokens', 0)} "
                             f"out={usage.get('output_tokens', 0)}"})
    elif kind == "turn.failed":
        state["is_error"] = True
        state["error"] = ((ev.get("error") or {}).get("message") or "turn failed")[:300]
        _emit(emit, {"type": "status", "text": "Codex 回合失败：" + state["error"]})
    elif kind == "error":
        msg = str(ev.get("message") or ev)[:200]
        state["errors"] = state.get("errors", 0) + 1
        _emit(emit, {"type": "status", "text": f"Codex 连接异常：{msg}"})
        state["error"] = msg
        if state["errors"] >= 20:
            # CLI 自己会无限重连，不能让流程挂到超时才醒
            state["abort"] = True
            state["is_error"] = True
            state["error"] = f"端点连续 {state['errors']} 次连接失败：{msg}"


def _arg_preview(inp) -> str:
    if not isinstance(inp, dict):
        return str(inp or "")[:200]
    for k in ("command", "file_path", "path", "pattern", "prompt", "description", "url"):
        if inp.get(k):
            return f"{k}: {str(inp[k])[:180]}"
    return json.dumps(inp, ensure_ascii=False)[:180]


# ==================== 统一入口 ====================
def run_agent(engine: str, prompt: str, *, ws: Path, system_text: str = "",
              cwd: Path | None = None,
              model: str = "", api_base: str = "", api_key: str = "",
              wire_api: str = "", timeout: int = 0,
              emit=None, label: str = "", cancel_check=None) -> dict:
    """跑一个智能体回合。prompt 一律走 stdin（argv 传多行在 Windows 上不可靠）。

    timeout<=0 时取设置页的单步超时。cancel_check: 可选回调，返回 True 即请求
    中止，抛 AgentCancelled。

    ws 和 cwd 是两件事：ws 是 Loom 自己的落盘处（转录、给 claude 的系统提示文件），
    cwd 只是智能体在哪个目录里干活（下任务时选的文件夹）。合并成一个的话，
    "选文件夹"就会连带把我们的文件灌进用户的仓库，而 delete_run 那句 rmtree
    也跟着吃掉它。
    """
    if timeout <= 0:
        timeout = step_timeout()
    engine = (engine or "").strip().lower()
    if engine not in ENGINES:
        raise AgentError(f"未知引擎「{engine}」，可选：{ ' / '.join(ENGINES) }")
    b = resolve_binary(engine)
    if not b:
        raise AgentError(
            f"未找到 {engine} CLI。请安装后在设置页填写可执行文件路径，"
            "或把该步骤的引擎改成已就绪的那个。")
    ws = Path(ws)
    ws.mkdir(parents=True, exist_ok=True)
    run_cwd = Path(cwd) if cwd else ws
    system_file = None
    if (system_text or "").strip():
        system_file = ws / "_step_system.txt"
        system_file.write_text(system_text, encoding="utf-8")

    isolated = bool((api_base or "").strip() or (api_key or "").strip())
    if engine == "claude":
        args = _claude_args(run_cwd, system_file, model, isolated)
        env = _claude_env(api_base, api_key)
        parse = _claude_events
    else:
        args = _codex_args(run_cwd, system_file, model, api_base, api_key, wire_api)
        env = _codex_env(api_base, api_key)
        parse = _codex_events

    state = {"texts": [], "final": "", "tools": 0, "turns": 0, "is_error": False,
             "duration_ms": None, "cost_usd": None, "error": "", "errors": 0,
             "abort": False, "tok": {}, "tok_total": None}
    t_start = time.time()   # claude 的 result 自带 duration_ms，codex 不给 ——
                            # 不兜这一下墙钟，统计里全部 codex 步骤的时长都是 None。
    log_dir = ws / "_turn_logs"
    log_dir.mkdir(exist_ok=True)
    log_path = log_dir / f"{(label or engine)}_{time.strftime('%H%M%S')}.jsonl"

    try:
        proc = subprocess.Popen(_argv(b, args), cwd=str(run_cwd), env=env,
                                stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True,
                                encoding="utf-8", errors="replace", bufsize=1,
                                creationflags=NO_WINDOW)
    except Exception as e:
        raise AgentError(f"启动 {engine} 失败：{e}")
    # Windows 的文本模式会把 \n 翻成 \r\n，提示词按 LF 送出去更稳定
    try:
        proc.stdin.reconfigure(newline="\n")
    except Exception:
        pass

    q: queue.Queue = queue.Queue()
    threading.Thread(target=_stdout_reader, args=(proc, q), daemon=True).start()
    err_lines: list = []

    def _read_err():
        try:
            for ln in proc.stderr:
                if ln.strip():
                    err_lines.append(ln.rstrip())
                    if len(err_lines) > 400:
                        del err_lines[:200]
        except Exception:
            pass
    threading.Thread(target=_read_err, daemon=True).start()

    deadline = time.time() + timeout
    _emit(emit, {"type": "status", "text": f"启动 {engine} · {b}"})
    timed_out = False
    rc = None

    def _ck():
        if cancel_check is not None and cancel_check():
            _kill_tree(proc)
            raise AgentCancelled()

    try:
        try:
            proc.stdin.write(prompt)
            proc.stdin.close()
        except Exception as e:
            _kill_tree(proc)
            raise AgentError(f"写入提示词失败：{e}", str(log_path))

        with open(log_path, "w", encoding="utf-8") as lf:
            while True:
                _ck()
                line = _pump(q, deadline)
                if line == "__TIMEOUT__":
                    timed_out = True
                    _emit(emit, {"type": "status", "text": f"超过 {timeout} 秒，强制终止"})
                    _kill_tree(proc)
                    break
                if line is None:
                    break
                if isinstance(line, str) and line.startswith("__READ_ERR__"):
                    continue
                lf.write(line if line.endswith("\n") else line + "\n")
                raw = line.strip()
                if not raw or not raw.startswith("{"):
                    if raw:
                        _emit(emit, {"type": "note", "text": raw[:300]})
                    continue
                try:
                    ev = json.loads(raw)
                except Exception:
                    continue
                try:
                    parse(ev, emit, state)
                except AgentCancelled:
                    raise
                except Exception:
                    pass
                if state.get("abort"):
                    _emit(emit, {"type": "status", "text": "连续连接失败，终止本步"})
                    _kill_tree(proc)
                    break
        _ck()
        rc = proc.wait(timeout=60)
    except AgentCancelled:
        _kill_tree(proc)
        raise
    except Exception as e:
        _kill_tree(proc)
        raise AgentError(f"{engine} 执行异常：{e}", str(log_path))
    finally:
        try:
            if proc.stdin and not proc.stdin.closed:
                proc.stdin.close()
        except Exception:
            pass

    text = (state["final"] or "").strip() or "\n\n".join(state["texts"]).strip()
    if state["duration_ms"] is None:
        state["duration_ms"] = max(0, int((time.time() - t_start) * 1000))
    result = {"text": text, "engine": engine, "rc": rc, "tools": state["tools"],
              "turns": state["turns"], "duration_ms": state["duration_ms"],
              "cost_usd": state["cost_usd"], "log": str(log_path),
              "tokens": state["tok_total"] or state["tok"],
              "is_error": state["is_error"] or timed_out,
              "error": state["error"] or ""}
    if timed_out:
        result["error"] = f"执行超时（{timeout}s）"
    elif rc not in (0, None) or state["is_error"]:
        if not result["error"]:
            tail = " / ".join(err_lines[-3:])[:400]
            result["error"] = (tail or f"{engine} 退出码 {rc}")
    if not text and not result["tools"]:
        result["is_error"] = True
        result["error"] = result["error"] or f"{engine} 无任何产出，也未调用工具"
    return result
