# -*- coding: utf-8 -*-
"""SQLite 数据层：流程模板 / API 预设 / 设置。

配置驱动核心：流程模板(pipeline_definitions)存「有序步骤清单」，每步含
(key, label, skill, model, out, checkpoint, role)。无工作流实例 ——
本软件只负责「编排流程 + 管理 skill」，执行交给外部 CLI。
"""
import sqlite3, json, time
from pathlib import Path
from . import paths

DB_DIR = paths.DB_DIR
DB_DIR.mkdir(exist_ok=True)
DB_PATH = DB_DIR / "flowforge.db"

# 功能下线后**必须**留在这里的键名：init_db() 每次启动都会把它们从 settings 表里删掉。
# 四条各是谁：
#   update_repo / update_asset —— 早期"从 GitHub releases/latest 找包"的仓库与资产名筛选串，
#     换成读 COS latest.json 之后代码一行都不读了（真源见 app/updater.py 的清单地址）；
#   library_version —— 随 app/presets_library.py（出厂流程/技能播种）一起删掉；
#   ui_accent —— 「可换强调色」设置整体删除后留下的残值，品牌位改成黑白反转之后
#     它没有可换的东西了（守卫测试 test_accent_setting_is_gone_for_good 管的是前端四处，
#     管不到已经躺在用户库里的那一行，所以清它得在这儿做）。
# 新增功能下线时把键名加进来，别只删读它的那行代码。
RETIRED_SETTINGS = ("update_repo", "update_asset", "library_version", "ui_accent")


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    # WAL：写任务的那条线程一步要写好几回落库，而页面每 400ms 轮询一次事件、
    # 设置页随时在读 runs。默认的回滚日志模式下读者会把写者堵死（反之也一样），
    # 表现就是偶发 "database is locked" 的 500。busy_timeout 兜同一件事的另一半：
    # 真撞上锁时等 5 秒而不是立刻抛。synchronous=NORMAL 是 WAL 下的常规配对 ——
    # 仍然只在本机断电时才可能丢最后几条，进程崩溃不丢已提交事务。
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def _now():
    return time.strftime("%Y-%m-%d %H:%M:%S")


def _add_column(c, table, col, ddl):
    """轻量列迁移：老库缺列时补上。"""
    cols = {r[1] for r in c.execute(f"PRAGMA table_info({table})")}
    if col not in cols:
        c.execute(f"ALTER TABLE {table} ADD COLUMN {ddl}")


def init_db():
    conn = get_conn()
    c = conn.cursor()
    # 流程模板定义：配置驱动核心
    c.execute("""CREATE TABLE IF NOT EXISTS pipeline_definitions(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,             -- 模板唯一名（小写短横线）
        label TEXT NOT NULL DEFAULT '',        -- 展示名
        desc TEXT NOT NULL DEFAULT '',
        emoji TEXT NOT NULL DEFAULT '',
        g TEXT NOT NULL DEFAULT 'custom',      -- 分组（built-in / custom / …）
        steps TEXT NOT NULL DEFAULT '[]',      -- 有序步骤清单 JSON 数组
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )""")
    _add_column(c, "pipeline_definitions", "builtin",
                "builtin INTEGER NOT NULL DEFAULT 0")  # 1=出厂内置（可恢复出厂）
    _add_column(c, "pipeline_definitions", "archived",
                "archived INTEGER NOT NULL DEFAULT 0")  # 1=归档：侧栏不摊开，东西一样不删
    c.execute("""CREATE TABLE IF NOT EXISTS settings(
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    )""")
    # API 预设库（Provider / Config）
    c.execute("""CREATE TABLE IF NOT EXISTS api_presets(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        provider TEXT NOT NULL DEFAULT 'openai',  -- openai | anthropic
        api_base TEXT NOT NULL DEFAULT '',
        api_key TEXT NOT NULL DEFAULT '',
        model TEXT NOT NULL DEFAULT '',
        is_default INTEGER NOT NULL DEFAULT 0,
        extra TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )""")
    # 流程运行实例：一次运行 = {pipeline, workspace, steps快照, 状态, 当前步骤, 挂起原因}
    c.execute("""CREATE TABLE IF NOT EXISTS runs(
        id TEXT PRIMARY KEY,                    -- run-<时间戳随机>
        pipeline TEXT NOT NULL,
        label TEXT NOT NULL DEFAULT '',
        workspace TEXT NOT NULL DEFAULT '',
        status TEXT NOT NULL DEFAULT 'pending', -- pending|running|waiting|done|failed|cancelled
        cur_step INTEGER NOT NULL DEFAULT 0,
        waiting_reason TEXT NOT NULL DEFAULT '',-- checkpoint|revision
        steps TEXT NOT NULL DEFAULT '[]',       -- 运行时步骤快照 [{key,label,skill,model,out,checkpoint,role,status,delta?}]
        error TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )""")
    _add_column(c, "runs", "brief", "brief TEXT NOT NULL DEFAULT ''")  # 任务说明
    # 下任务时选的工作文件夹（只当智能体的 cwd）。空串=没选，沿用派生工作区。
    _add_column(c, "runs", "workdir", "workdir TEXT NOT NULL DEFAULT ''")
    # 两条索引都是给 runs 那张列表用的：list_runs 永远按 (created_at, id) 倒着取，
    # 侧栏按流程筛一遍。没索引时这是每次打开页面一次全表扫 + 排序，跑到几百条
    # 就能看出卡顿；(pipeline, created_at, id) 那条顺带把筛选和排序一起 cover 了。
    # DESC 不用写：SQLite 倒着扫普通索引就是 created_at DESC, id DESC。
    c.execute("CREATE INDEX IF NOT EXISTS idx_runs_created ON runs(created_at, id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_runs_pipeline ON runs(pipeline, created_at, id)")
    # 退役设置键的清理。这几把键的**代码**已经删了，但行还留在每台机器的 settings 表里，
    # 而 /api/settings 是整表吐出去的 —— 结果是界面看不见、接口里却一直回一个没人读的值。
    # 以前这类东西踩过好几回（HANDOFF §2 的 update_repo / update_asset 那条），
    # 所以清键必须跟功能下线同一次做，不能"先删代码，回头再清库"，回头就没有了。
    # 只清这一张具名单，不做"未知键一律删"：新版本加的键不该被旧版本删掉。
    for _retired in RETIRED_SETTINGS:
        c.execute("DELETE FROM settings WHERE key=?", (_retired,))
    conn.commit(); conn.close()


# ==================== 流程模板定义（配置驱动） ====================
def list_pipelines():
    conn = get_conn()
    rows = [dict(r) for r in conn.execute(
        "SELECT * FROM pipeline_definitions ORDER BY id ASC")]
    conn.close()
    for r in rows:
        try:
            r["steps"] = json.loads(r["steps"] or "[]")
        except Exception:
            r["steps"] = []
    return rows


def run_counts():
    """每条流程被跑过几次。侧栏「项目」只列真跑过的，靠这个判定。"""
    conn = get_conn()
    rows = conn.execute("SELECT pipeline, COUNT(*) c FROM runs GROUP BY pipeline").fetchall()
    conn.close()
    return {r["pipeline"]: r["c"] for r in rows}


def run_status_counts():
    """全表按状态计数。统计页的总次数/状态分布不能用 list_runs 的窗口来算 ——
    窗口只有最近 500 条，跑够 501 次之后页面上的"总计"就永远停在 500。"""
    conn = get_conn()
    rows = conn.execute("SELECT status, COUNT(*) c FROM runs GROUP BY status").fetchall()
    conn.close()
    return {r["status"]: r["c"] for r in rows}


def all_run_ids():
    """全部运行 id。孤儿工作区判定要看全表：按 list_runs 的前 500 条比，
    第 501 条的工作区会被当成孤儿报出来，那是别人还没删的现场。"""
    conn = get_conn()
    ids = {r["id"] for r in conn.execute("SELECT id FROM runs").fetchall()}
    conn.close()
    return ids


def get_pipeline(name):
    conn = get_conn()
    r = conn.execute("SELECT * FROM pipeline_definitions WHERE name=?", (name,)).fetchone()
    conn.close()
    if not r:
        return None
    d = dict(r)
    try:
        d["steps"] = json.loads(d["steps"] or "[]")
    except Exception:
        d["steps"] = []
    return d


def create_pipeline(name, label="", desc="", emoji="", g="custom", steps=None,
                    builtin=0):
    now = _now()
    conn = get_conn(); c = conn.cursor()
    c.execute("""INSERT INTO pipeline_definitions(name,label,desc,emoji,g,steps,builtin,created_at,updated_at)
                 VALUES(?,?,?,?,?,?,?,?,?)""",
              (name, label, desc, emoji, g,
               json.dumps(steps or [], ensure_ascii=False), int(bool(builtin)), now, now))
    pid = c.lastrowid; conn.commit(); conn.close()
    return pid


def update_pipeline(name, label=None, desc=None, emoji=None, g=None, steps=None,
                    builtin=None):
    p = get_pipeline(name)
    if not p: return False
    conn = get_conn(); c = conn.cursor()
    nlabel = label if label is not None else p["label"]
    ndesc = desc if desc is not None else p["desc"]
    nemoji = emoji if emoji is not None else p["emoji"]
    ng = g if g is not None else p["g"]
    nbuiltin = int(bool(builtin)) if builtin is not None else int(p.get("builtin") or 0)
    nsteps = json.dumps(steps if steps is not None else p["steps"], ensure_ascii=False)
    c.execute("""UPDATE pipeline_definitions SET label=?, desc=?, emoji=?, g=?, steps=?,
                 builtin=?, updated_at=? WHERE name=?""",
              (nlabel, ndesc, nemoji, ng, nsteps, nbuiltin, _now(), name))
    conn.commit(); conn.close()
    return True


def delete_pipeline(name):
    conn = get_conn(); c = conn.cursor()
    c.execute("DELETE FROM pipeline_definitions WHERE name=?", (name,))
    conn.commit(); conn.close()
    return True


# ==================== 设置 ====================
_SETTING_CACHE: dict = {}


def set_setting(key, value):
    _SETTING_CACHE.pop(key, None)
    conn = get_conn(); c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)", (key, value))
    conn.commit(); conn.close()


def get_setting(key, default=""):
    v = _SETTING_CACHE.get(key)
    if v is not None:
        return v
    conn = get_conn()
    r = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    conn.close()
    v = r["value"] if r else default
    _SETTING_CACHE[key] = v
    return v


def get_all_settings():
    conn = get_conn()
    rows = [dict(r) for r in conn.execute("SELECT key,value FROM settings")]
    conn.close()
    d = {r["key"]: r["value"] for r in rows}
    _SETTING_CACHE.update(d)
    return d


# ==================== API 预设库 ====================
def preset_to_dict(r):
    if r is None: return None
    d = dict(r)
    d["is_default"] = bool(d.get("is_default"))
    try:
        d["extra"] = json.loads(d.get("extra") or "{}")
    except Exception:
        d["extra"] = {}
    return d


def list_presets():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM api_presets ORDER BY is_default DESC, id ASC").fetchall()
    conn.close()
    return [preset_to_dict(r) for r in rows]


def get_preset(pid):
    conn = get_conn()
    r = conn.execute("SELECT * FROM api_presets WHERE id=?", (pid,)).fetchone()
    conn.close()
    return preset_to_dict(r)


def get_preset_by_name(name):
    conn = get_conn()
    r = conn.execute("SELECT * FROM api_presets WHERE name=?", (name,)).fetchone()
    conn.close()
    return preset_to_dict(r)


def get_default_preset():
    conn = get_conn()
    r = conn.execute("SELECT * FROM api_presets WHERE is_default=1 ORDER BY id ASC LIMIT 1").fetchone()
    conn.close()
    return preset_to_dict(r)


def add_preset(name, provider="openai", api_base="", api_key="", model="", extra=None):
    now = _now()
    extra_json = json.dumps(extra or {}, ensure_ascii=False)
    conn = get_conn(); c = conn.cursor()
    c.execute("""INSERT INTO api_presets(name,provider,api_base,api_key,model,extra,is_default,created_at,updated_at)
                 VALUES(?,?,?,?,?,?,0,?,?)""",
              (name, provider, api_base, api_key, model, extra_json, now, now))
    pid = c.lastrowid
    if not c.execute("SELECT id FROM api_presets WHERE is_default=1 LIMIT 1").fetchone():
        c.execute("UPDATE api_presets SET is_default=1, updated_at=? WHERE id=?", (now, pid))
    conn.commit(); conn.close()
    return pid


def update_preset(pid, name=None, provider=None, api_base=None, api_key=None,
                  model=None, extra=None):
    p = get_preset(pid)
    if not p: return False
    fields = {
        "name": name if name is not None else p["name"],
        "provider": provider if provider is not None else p["provider"],
        "api_base": api_base if api_base is not None else p["api_base"],
        "api_key": api_key if api_key is not None else p["api_key"],
        "model": model if model is not None else p["model"],
    }
    conn = get_conn(); c = conn.cursor()
    c.execute("""UPDATE api_presets SET name=?, provider=?, api_base=?, api_key=?, model=?, updated_at=? WHERE id=?""",
              (fields["name"], fields["provider"], fields["api_base"], fields["api_key"],
               fields["model"], _now(), pid))
    if extra is not None:
        c.execute("UPDATE api_presets SET extra=?, updated_at=? WHERE id=?",
                  (json.dumps(extra, ensure_ascii=False), _now(), pid))
    conn.commit(); conn.close()
    return True


def set_default_preset(pid):
    conn = get_conn(); c = conn.cursor()
    c.execute("UPDATE api_presets SET is_default=0")
    c.execute("UPDATE api_presets SET is_default=1, updated_at=? WHERE id=?", (_now(), pid))
    conn.commit(); conn.close()


def delete_preset(pid):
    conn = get_conn(); c = conn.cursor()
    row = c.execute("SELECT is_default FROM api_presets WHERE id=?", (pid,)).fetchone()
    was_default = bool(row and row[0])
    c.execute("DELETE FROM api_presets WHERE id=?", (pid,))
    if was_default and not c.execute(
            "SELECT id FROM api_presets WHERE is_default=1 LIMIT 1").fetchone():
        # 删掉的正好是「默认」那一张：库里从此一个默认都没有，
        # get_default_preset() 回 None，于是所有没显式挑端点的步骤从此静默不注入
        # 端点 —— 整套 API 接入配置不再起作用，而界面上没有任何一处说它没了。
        # 补一个上去（取最早那张，和 add_preset 挑第一张的规则同一套）。
        nxt = c.execute("SELECT id FROM api_presets ORDER BY id ASC LIMIT 1").fetchone()
        if nxt:
            c.execute("UPDATE api_presets SET is_default=1, updated_at=? WHERE id=?",
                      (_now(), nxt[0]))
    conn.commit(); conn.close()


# ==================== 流程运行实例 ====================
def _run_row(r):
    d = dict(r)
    try:
        d["steps"] = json.loads(d.get("steps") or "[]")
    except Exception:
        d["steps"] = []
    return d


def ws_dir_name(run_id: str) -> str:
    """派生工作区的目录名。规则只这一份：id 已经带 run- 前缀就别再加，
    否则 runner._ws_path 算出 run-abc、这行写的却是 run-run-abc —— 库里的路径
    在磁盘上根本不存在（原先就是这个状态，没人读所以没暴露）。"""
    s = str(run_id)
    return s if s.startswith("run-") else f"run-{s}"


def create_run(run_id, pipeline, label="", steps=None, brief="", workdir=""):
    now = _now()
    conn = get_conn(); c = conn.cursor()
    c.execute("""INSERT INTO runs(id,pipeline,label,workspace,status,cur_step,waiting_reason,steps,brief,error,created_at,updated_at,workdir)
                 VALUES(?,?,?,?,?,0,'',?,?, '', ?, ?,?)""",
              (run_id, pipeline, label, ws_dir_name(run_id), "pending",
               json.dumps(steps or [], ensure_ascii=False), brief or "", now, now,
               (workdir or "").strip()))
    conn.commit(); conn.close()
    return get_run(run_id)


def get_run(run_id):
    conn = get_conn()
    r = conn.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
    conn.close()
    return _run_row(r) if r else None


def count_active_runs():
    """还在跑 / 停在检查点等人 的运行数。更新前拿它决定要不要弹提示。"""
    conn = get_conn()
    n = conn.execute(
        "SELECT COUNT(*) FROM runs WHERE status IN ('running','revising','waiting')"
    ).fetchone()[0]
    conn.close()
    return int(n or 0)


def set_pipeline_archived(name, flag):
    """只翻归档那一位。删除是另一条路（delete_pipeline），这里碰不到它。"""
    conn = get_conn()
    c = conn.execute("UPDATE pipeline_definitions SET archived=?, updated_at=? WHERE name=?",
                     (1 if flag else 0, _now(), name))
    conn.commit()
    n = c.rowcount
    conn.close()
    return n > 0


def last_runs():
    """每条流程最近一次运行（id + 时间）。侧栏「查看文件」要打开的就是这个工作区。

    取 rowid 最大那条：runs 是按插入顺序自增的，created_at 也是插入时写的，
    所以"最后插入"与"最新"在这里等价 —— 比按 created_at 排序省一次全表扫。
    """
    conn = get_conn()
    rows = conn.execute("""SELECT r.pipeline AS pipeline, r.id AS id, r.created_at AS created_at
        FROM runs r JOIN (SELECT pipeline, MAX(rowid) m FROM runs GROUP BY pipeline) t
          ON r.rowid = t.m""").fetchall()
    conn.close()
    return {r["pipeline"]: {"id": r["id"], "created_at": r["created_at"]} for r in rows}


def list_runs(pipeline=None, limit=50):
    conn = get_conn()
    if pipeline:
        rows = conn.execute("SELECT * FROM runs WHERE pipeline=? ORDER BY created_at DESC, id DESC LIMIT ?",
                            (pipeline, limit)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM runs ORDER BY created_at DESC, id DESC LIMIT ?",
                            (limit,)).fetchall()
    conn.close()
    return [_run_row(r) for r in rows]


_RUN_COLS = ("status", "waiting_reason", "error", "cur_step", "steps", "created_at")


def update_run(run_id, **fields):
    """部分更新运行记录；steps 传 list 则自动序列化。

    列名进白名单：这层 f-string 拼的是列名（值全部走 ? 参数化），今天的调用面
    只有 runner.py 那 12 处、传的都是这五列；但 update_run 是公开函数，将来谁
    手滑把用户输入当列名传进来，这里就是唯一能拦住的闸。"""
    unknown = [k for k in fields if k not in _RUN_COLS]
    if unknown:
        raise ValueError(f"update_run 不认识的列：{unknown}（合法列 {_RUN_COLS}）")
    if not get_run(run_id):
        return False
    sets, vals = [], []
    for k, v in fields.items():
        if k == "steps" and isinstance(v, list):
            v = json.dumps(v, ensure_ascii=False)
        sets.append(f"{k}=?")
        vals.append(v)
    sets.append("updated_at=?")
    vals.append(_now())
    vals.append(run_id)
    conn = get_conn(); c = conn.cursor()
    c.execute(f"UPDATE runs SET {', '.join(sets)} WHERE id=?", vals)
    conn.commit(); conn.close()
    return True


def delete_run(run_id):
    conn = get_conn(); c = conn.cursor()
    c.execute("DELETE FROM runs WHERE id=?", (run_id,))
    conn.commit(); conn.close()
    return True


def reconcile_interrupted_runs():
    """把上一世留下的"正在跑"归成 failed，返回处理条数。

    `running` / `revising` 是**线程持有型**状态：只有那个跑任务的线程会把它改成终态。
    进程被杀 / 断电 / 更新器 os._exit(0) 之后，这一行永远停在 running，而重启后
    没有任何线程会来救它，于是四件事同时坏掉：侧栏永远转圈、"停止"按钮改了库也
    没人读（cancel_run 只往内存 _CANCEL 里塞 id）、重跑被"运行中不能重跑"挡住、
    而 count_active_runs() 把它一直算成活跃 —— **应用内更新从此永久 409**。
    `waiting` 不在其列：停在检查点等人本来就是跨重启可恢复的状态。
    """
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT id FROM runs WHERE status IN ('running','revising')")
    ids = [r["id"] for r in c.fetchall()]
    if ids:
        c.execute(
            "UPDATE runs SET status='failed', error=?, updated_at=? "
            "WHERE status IN ('running','revising')",
            ("应用退出时这条还在跑，已按中断处理（现场仍在，可重跑）", _now()))
        conn.commit()
    conn.close()
    return len(ids)


# 模块加载即建表（保证任何模块 import db 后立即可查询）
init_db()
# 紧接着对账一次：必须在任何读 status 的地方之前，否则侧栏/更新检查会先看到僵尸。
reconcile_interrupted_runs()
