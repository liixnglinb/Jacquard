# -*- coding: utf-8 -*-
"""Loom 织流 —— 主入口。

核心能力：
  1. 创建流程：可视化编排流程模板（步骤清单，每步绑定技能 / 引擎 / 产物 / 检查点）
  2. 创建 skill：技能库管理（新建 / 编辑 / 另存副本 / 删除 / 导入标准 skill 包）
  3. 运行流程：把每步交给本机智能体 CLI（claude / codex）执行，SSE 实时推送
     工具调用与产出，检查点暂停，支持对话式局部修订与「从此步重跑」
  4. 内置库：出厂自带一条通用全自动工作流 + 一条轻量流，全部可编辑、可恢复出厂

外加设置页（智能体引擎接入 / API 预设 / 连通检测）与 GitHub Releases 检查更新。无授权墙。
"""
import re
from pathlib import Path
from fastapi import FastAPI, UploadFile, File
from fastapi.exceptions import RequestValidationError
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel
from . import agents, cli_inventory, db, llm, paths, pipelines, runner, updater

app = FastAPI(title="Jacquard 织流")

STATIC = paths.STATIC_DIR
app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")


@app.exception_handler(RequestValidationError)
async def _validation_error(request, exc):
    """pydantic 的 422 默认把 detail 吐成一个**数组**，而前端所有调用点都是
    `if (r.detail) toast(r.detail)` —— 于是界面上印 `[object Object]`。
    摊成一句人话；状态码仍按 FastAPI 的 422，不假装是业务校验的 400。
    """
    errs = getattr(exc, "errors", lambda: [])()
    parts = [f"{'.'.join(str(x) for x in (e.get('loc') or [])[1:]) or '请求体'}：{e.get('msg')}"
             for e in errs]
    return JSONResponse({"detail": "；".join(parts) or "请求参数不合法"}, 422)


@app.middleware("http")
async def _static_cache_policy(request, call_next):
    """全站 no-cache：升级后 WebView 一律拿到最新代码（ETag 304 时不重传，开销可忽略）。"""
    resp = await call_next(request)
    try:
        resp.headers["Cache-Control"] = "no-cache"
    except Exception:
        pass
    return resp


# ---------- 页面（单页 SPA：所有路由返回同一入口，前端 hash 路由切换视图） ----------
_SPA = str(STATIC / "index.html")

@app.get("/")
def index(): return FileResponse(_SPA)
@app.get("/pipelines")
def pipelines_page(): return FileResponse(_SPA)
@app.get("/pipeline-edit")
def pipeline_edit_page(): return FileResponse(_SPA)
@app.get("/pipeline-edit/{name}")
def pipeline_edit_name(name: str): return FileResponse(_SPA)
@app.get("/skills")
def skills_page(): return FileResponse(_SPA)
@app.get("/skill-edit")
def skill_edit_page(): return FileResponse(_SPA)
@app.get("/skill-edit/{name}")
def skill_edit_name(name: str): return FileResponse(_SPA)
@app.get("/settings")
def settings_page(): return FileResponse(_SPA)


# ---------- 健康检查 ----------
@app.get("/api/health")
def health():
    from .version import APP_VERSION
    return {"ok": True, "version": APP_VERSION}


# ---------- 流程模板（配置驱动：模板存数据库，全部用户自建） ----------
class PipelineIn(BaseModel):
    name: str
    label: str = ""
    desc: str = ""
    emoji: str = ""
    g: str = "custom"
    steps: list = []

class PipelineUpdate(BaseModel):
    label: str = ""
    desc: str = ""
    emoji: str = ""
    g: str = ""
    steps: list = None


@app.get("/api/pipelines")
def list_pipelines():
    """返回全部流程模板（步骤清单完整返回，供编排器/新建页展示）。
    runs = 被跑过的次数，侧栏「项目」用它筛掉从没开工的流程。"""
    counts = db.run_counts()
    last = db.last_runs()
    out = []
    for p in db.list_pipelines():
        out.append({"template": p["name"], "name": p["name"], "label": p["label"],
                    "desc": p["desc"], "emoji": p["emoji"], "g": p["g"],
                    "archived": int(p.get("archived") or 0),
                    "runs": int(counts.get(p["name"], 0)),
                    "last_run": last.get(p["name"]),
                    "steps": p.get("steps") or []})
    return {"pipelines": out}


@app.post("/api/pipelines")
def create_pipeline(p: PipelineIn):
    name, ok = pipelines.normalize_name(p.name)
    if not ok:
        return JSONResponse({"detail": "模板名只能含小写字母/数字/连字符/下划线"}, 400)
    if db.get_pipeline(name):
        return JSONResponse({"detail": f"模板名「{name}」已存在"}, 400)
    steps = pipelines.normalize_steps(p.steps)
    okv, err = pipelines.validate_steps(steps)
    if not okv:
        return JSONResponse({"detail": err}, 400)
    db.create_pipeline(name, p.label or name, p.desc, p.emoji, p.g or "custom",
                       steps=steps)
    return {"ok": True, "name": name}


@app.put("/api/pipelines/{name}")
def update_pipeline(name: str, u: PipelineUpdate):
    p = db.get_pipeline(name)
    if not p:
        return JSONResponse({"detail": "not found"}, 404)
    steps = None
    if u.steps is not None:
        steps = pipelines.normalize_steps(u.steps)
        okv, err = pipelines.validate_steps(steps)
        if not okv:
            return JSONResponse({"detail": err}, 400)
    db.update_pipeline(name, label=u.label or None, desc=u.desc or None,
                       emoji=u.emoji or None, g=u.g or None, steps=steps)
    return {"ok": True}


@app.delete("/api/pipelines/{name}")
def delete_pipeline(name: str):
    if not db.get_pipeline(name):
        return JSONResponse({"detail": "not found"}, 404)
    db.delete_pipeline(name)
    return {"ok": True}


class ArchiveIn(BaseModel):
    archived: bool = True


@app.post("/api/pipelines/{name}/archive")
def archive_pipeline(name: str, a: ArchiveIn):
    """归档 = 从侧栏「项目」里收起来，不删任何东西：步骤、运行记录、工作区全留着。
    真删是 DELETE /api/pipelines/{name} 那一条，走的是另一个确认框。"""
    if not db.get_pipeline(name):
        return JSONResponse({"detail": "not found"}, 404)
    if not db.set_pipeline_archived(name, bool(a.archived)):
        return JSONResponse({"detail": "not found"}, 404)
    return {"ok": True, "name": name, "archived": 1 if a.archived else 0}


@app.post("/api/pipelines/{name}/duplicate")
def duplicate_pipeline(name: str, p: PipelineIn):
    """把现有模板另存为副本（用于复制一份改造）。"""
    src = db.get_pipeline(name)
    if not src:
        return JSONResponse({"detail": "not found"}, 404)
    newname, ok = pipelines.normalize_name(p.name)
    if not ok:
        return JSONResponse({"detail": "模板名只能含小写字母/数字/连字符/下划线"}, 400)
    if db.get_pipeline(newname):
        return JSONResponse({"detail": f"模板名「{newname}」已存在"}, 400)
    # create / update 都先过 normalize_steps，唯独 duplicate 直接把调用方给的
    # steps 原样落库。脏字段会被 _snapshot_steps 整份拷进 runs.steps，之后
    # usage_stats 里 `m = s.get("meta") or {}` 拿到一个字符串再 .get() 就抛，
    # 而 /api/stats 没有兜异常 —— 开设置页就 500，且这条流程永久毒着统计。
    steps = pipelines.normalize_steps(p.steps if p.steps else (src.get("steps") or []))
    okv, err = pipelines.validate_steps(steps)
    if not okv:
        return JSONResponse({"detail": err}, 400)
    db.create_pipeline(newname, p.label or (src["label"] + " 副本"), p.desc or src["desc"],
                       p.emoji or src["emoji"], p.g or src["g"], steps=steps)
    return {"ok": True, "name": newname}


@app.get("/api/pipelines/{name}/export")
def export_pipeline(name: str):
    """导出模板为 JSON 文件（备份 / 分享）。字段和 POST /api/pipelines 收的对齐，
    导出的文件要能原样导回来，所以不带 id / builtin / 时间戳这些库内字段。"""
    p = db.get_pipeline(name)
    if not p:
        return JSONResponse({"detail": "not found"}, 404)
    body = {k: p.get(k) for k in ("name", "label", "desc", "emoji", "g")}
    body["steps"] = p.get("steps") or []
    return JSONResponse(body, headers={
        "Content-Disposition": f'attachment; filename="loom-{name}.json"'})


@app.get("/api/pipelines/{name}/preview/{index}")
def preview_pipeline_step(name: str, index: int, brief: str = ""):
    """预览第 index 步实际发给智能体的提示词（系统规范 + 用户指令）。"""
    try:
        return runner.preview_step_prompt(name, index, brief)
    except ValueError as e:
        return JSONResponse({"detail": str(e)}, 404)
    except IndexError as e:
        # 序号越界是调用方的错，不是服务端故障；以前落到 500 分支，
        # detail 里还印着 "list index out of range" 这种内部实现。
        return JSONResponse({"detail": str(e)}, 400)
    except Exception as e:
        return JSONResponse({"detail": f"预览失败: {e}"}, 500)


# ---------- Skill 库（自建 + 随包内置只读） ----------
def _skill_desc(text: str) -> str:
    """技能简介：优先 YAML frontmatter 的 description，否则取首行正文标题。"""
    import re as _re
    body = text
    m = _re.match(r"^---\s*\n(.*?)\n---\s*\n?", text, _re.S)
    if m:
        body = text[m.end():]
        for line in m.group(1).splitlines():
            km = _re.match(r"^(description|title)\s*:\s*(.+)$", line.strip())
            if km:
                val = km.group(2).strip().strip("'\"").strip()
                if val:
                    return val[:160]
    for line in body.splitlines():
        t = line.strip().lstrip("#").strip()
        if t:
            return t[:160]
    return ""


@app.get("/api/skills")
def list_skills():
    """枚举自建 skill。

    每个 skill 返回：name、desc（frontmatter.description 或首个正文行）、chars（正文长度）。
    只扫可写技能目录：出厂技能已经随包撤掉了，再扫一遍 BASE/skills 等于让
    旧版本装过的目录里那份只读副本悄悄复活。
    """
    seen = {}
    base = paths.USER_SKILLS_DIR
    if base.is_dir():
        for d in sorted(base.iterdir()):
            if not (d.is_dir() and (d / "SKILL.md").exists()):
                continue
            try:
                text = (d / "SKILL.md").read_text(encoding="utf-8")
            except Exception:
                text = ""
            seen[d.name] = {"name": d.name, "desc": _skill_desc(text),
                            "chars": len(text)}
    out = list(seen.values())
    out.sort(key=lambda x: x["name"])
    return {"skills": out}


@app.get("/api/skills/{name}")
def get_skill(name: str):
    """读取单个 skill 的 SKILL.md 全文（用于技能管理页查看/编辑）。"""
    d = _skill_dir_safe(name)
    p = d / "SKILL.md" if d else None
    if p and p.exists():
        try:
            text = p.read_text(encoding="utf-8")
        except Exception:
            return JSONResponse({"detail": "skill 文件读取失败"}, 500)
        return {"name": name, "content": text, "editable": True}
    return JSONResponse({"detail": "skill 不存在"}, 404)


def _skill_dir_safe(name: str) -> Path | None:
    """校验 skill 名（防目录穿越），合法返回自建目录路径。"""
    import re as _re
    if not name or not _re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", name):
        return None
    return paths.USER_SKILLS_DIR / name


class SkillIn(BaseModel):
    name: str
    content: str = ""
    desc: str = ""   # 仅用于新建时若无正文标题则补一行简介头


# 技能正文的大小上限，和记忆文件同一档（cli_inventory.MEMORY_MAX_BYTES）。
# 为什么必须有个上限：这份正文是**整篇**塞进每一步的提示词的
# （runner.compose_skill_prompt），一张 5MB 的表就是一步 5MB 的上下文 ——
# 智能体要么直接报错，要么把这一步的预算全花在复读上。
_SKILL_WRITE_MAX_BYTES = 512 * 1024


def _skill_too_big(content: str):
    """超上限返回 413，没超返回 None。"""
    n = len((content or "").encode("utf-8"))
    if n > _SKILL_WRITE_MAX_BYTES:
        return JSONResponse(
            {"detail": f"技能正文超过 {_SKILL_WRITE_MAX_BYTES // 1024} KB"
                       f"（这份 {n // 1024} KB），没有写入 —— "
                       f"正文会整篇进每一步的提示词"}, 413)
    return None


@app.post("/api/skills")
def create_skill(s: SkillIn):
    """新建自建 skill：写入 modex-data/skills/<name>/SKILL.md（可写目录）。"""
    d = _skill_dir_safe(s.name.strip())
    if not d:
        return JSONResponse({"detail": "skill 名只能含小写字母/数字/连字符/下划线"}, 400)
    if d.exists():
        return JSONResponse({"detail": f"skill「{s.name}」已存在"}, 400)
    content = (s.content or "").strip()
    if not content:
        content = (s.desc or "").strip() or (s.name + " 技能说明")
    over = _skill_too_big(content)
    if over:
        return over
    d.mkdir(parents=True, exist_ok=True)
    (d / "SKILL.md").write_text(content + "\n", encoding="utf-8")
    return {"ok": True, "name": s.name}


@app.put("/api/skills/{name}")
def update_skill(name: str, s: SkillIn):
    """更新自建 skill 内容。"""
    d = _skill_dir_safe(name)
    if not d or not (d / "SKILL.md").exists():
        return JSONResponse({"detail": "skill 不存在"}, 404)
    over = _skill_too_big(s.content or "")
    if over:
        return over
    (d / "SKILL.md").write_text((s.content or "").rstrip() + "\n", encoding="utf-8")
    return {"ok": True, "name": name}


@app.post("/api/skills/{name}/duplicate")
def duplicate_skill(name: str, s: SkillIn):
    """把现有 skill 另存一份副本。"""
    src = _skill_dir_safe(name)
    p = src / "SKILL.md" if src else None
    if not (p and p.exists()):
        return JSONResponse({"detail": "skill 不存在"}, 404)
    src_text = p.read_text(encoding="utf-8")
    newname = (s.name or "").strip()
    d = _skill_dir_safe(newname)
    if not d:
        return JSONResponse({"detail": "skill 名只能含小写字母/数字/连字符/下划线"}, 400)
    if d.exists():
        return JSONResponse({"detail": f"skill「{newname}」已存在"}, 400)
    d.mkdir(parents=True, exist_ok=True)
    (d / "SKILL.md").write_text(src_text, encoding="utf-8")
    return {"ok": True, "name": newname}


@app.delete("/api/skills/{name}")
def delete_skill(name: str):
    """删除一份 skill。"""
    d = _skill_dir_safe(name)
    if not d or not (d / "SKILL.md").exists():
        return JSONResponse({"detail": "skill 不存在"}, 404)
    import shutil
    shutil.rmtree(d, ignore_errors=True)
    return {"ok": True}


# ---------- 导入标准 skill 包（zip / 单个 SKILL.md / SKILL.md+附属文件） ----------
_SKILL_BANNED_PARTS = ("__pycache__", ".git", "node_modules", ".venv", "venv")
_SKILL_MAX_FILES = 500          # 单包文件数上限（防 zip 炸弹）
_SKILL_MAX_BYTES = 200 * 1024 * 1024  # 解压总量上限 200MB


def _skill_name_from_md(md_text: str, fallback: str) -> tuple[str, str]:
    """从 SKILL.md 的 YAML frontmatter 提取 name（有则用），返回 (name, meta_note)。"""
    import re as _re
    m = _re.match(r"^---\s*\n(.*?)\n---\s*\n", md_text, _re.S)
    if not m:
        return fallback, ""
    name = ""
    for line in m.group(1).splitlines():
        lm = _re.match(r"^name\s*:\s*['\"]?([^'\"\n]+?)['\"]?\s*$", line.strip())
        if lm:
            name = lm.group(1).strip()
            break
    return name, ("frontmatter.name" if name else "")


def _norm_skill_name(raw: str) -> str:
    """技能名规范化：小写、空格→短横线、剥非法字符、去首尾连字符。"""
    import re as _re
    s = (raw or "").strip().lower().replace(" ", "-").replace("_", "-")
    s = _re.sub(r"[^a-z0-9-]", "", s).strip("-")
    return s[:64]


def _extract_zip_safe(zf, dest: Path) -> int:
    """安全解 zip 到 dest（防穿越/防炸弹）。返回解出的文件数。"""
    import zipfile
    total = 0
    names = zf.namelist()
    if len(names) > _SKILL_MAX_FILES:
        raise ValueError(f"包内文件过多（{len(names)} > {_SKILL_MAX_FILES}）")
    for info in names:
        if info.endswith("/"):
            continue
        p = (dest / info).resolve()
        if not p.is_relative_to(dest.resolve()):
            raise ValueError(f"zip 内含非法路径：{info}")
        total += 1
    if total == 0:
        raise ValueError("压缩包为空")
    dest.mkdir(parents=True, exist_ok=True)
    count = 0
    for info in names:
        if info.endswith("/"):
            continue
        p = (dest / info).resolve()
        if not p.is_relative_to(dest.resolve()):
            continue
        p.parent.mkdir(parents=True, exist_ok=True)
        with zf.open(info) as src, open(p, "wb") as out:
            while True:
                chunk = src.read(1024 * 1024)
                if not chunk:
                    break
                out.write(chunk)
                total += len(chunk)
                if total > _SKILL_MAX_BYTES:
                    raise ValueError("解压总量超过 200MB 上限")
        count += 1
    return count


def _find_skill_md(root: Path) -> Path | None:
    """在目录里定位 SKILL.md：根目录优先，其次唯一一层子目录（标准 skill 包结构）。"""
    direct = root / "SKILL.md"
    if direct.is_file():
        return direct
    subs = [d for d in root.iterdir() if d.is_dir()] if root.is_dir() else []
    hits = [d / "SKILL.md" for d in subs if (d / "SKILL.md").is_file()]
    if len(hits) == 1:
        return hits[0]
    if len(hits) > 1:
        # 多个同名结构：取与包名一致的子目录
        for h in hits:
            if h.parent.name.lower() == root.name.lower():
                return h
        return hits[0]
    return None


def _install_skill_dir(src: Path, name: str) -> dict:
    """把含 SKILL.md 的目录装进技能库（移动整个目录，保留 references/scripts 等附属文件）。"""
    import shutil
    name = _norm_skill_name(name)
    if not name:
        raise ValueError("无法确定技能名（SKILL.md 缺少 frontmatter.name，且目录名不含合法字符）")
    dest = paths.USER_SKILLS_DIR / name
    if dest.exists():
        raise ValueError(f"技能「{name}」已存在，请先删除或改名")
    paths.USER_SKILLS_DIR.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dest))
    n_files = sum(1 for f in dest.rglob("*") if f.is_file())
    chars = len((dest / "SKILL.md").read_text(encoding="utf-8", errors="replace"))
    return {"name": name, "files": n_files, "chars": chars}


@app.post("/api/skills/import")
async def import_skill(file: UploadFile = File(...)):
    """导入标准 skill 模式的技能包。

    接受三种形态：
      1. zip 压缩包：内含 SKILL.md（根目录或唯一子目录），附属文件随包进入
      2. 单个 SKILL.md 文件（按 frontmatter.name 或文件所在名入库）
    技能名优先取 SKILL.md frontmatter 的 name 字段，否则用 zip 内层目录名 / 文件名。
    """
    import zipfile, tempfile, shutil, io
    # 以前是 raw = await file.read() 再判 len —— 那个 200MB 上限是在**已经把它
    # 全读进内存之后**才生效的，等于没有上限：一个 2GB 的包会先把这个 16GB 的
    # 机器顶到 swapping，然后才被拒。分块读到上限就停手。
    chunks = []
    total = 0
    while True:
        part = await file.read(1 << 20)
        if not part:
            break
        total += len(part)
        if total > _SKILL_MAX_BYTES:
            return JSONResponse({"detail": f"文件超过 "
                                           f"{_SKILL_MAX_BYTES // (1024 * 1024)}MB 上限"}, 413)
        chunks.append(part)
    raw = b"".join(chunks)
    fname = (file.filename or "").strip()
    lower = fname.lower()

    tmp_root = Path(tempfile.mkdtemp(prefix="ff_import_"))
    try:
        if lower.endswith(".zip"):
            try:
                with zipfile.ZipFile(io.BytesIO(raw)) as zf:
                    _extract_zip_safe(zf, tmp_root)
            except zipfile.BadZipFile:
                return JSONResponse({"detail": "不是有效的 zip 压缩包"}, 400)
            except ValueError as e:
                return JSONResponse({"detail": str(e)}, 400)
            md = _find_skill_md(tmp_root)
            if not md:
                return JSONResponse({"detail": "压缩包内未找到 SKILL.md（标准 skill 包需含 SKILL.md）"}, 400)
            pkg_name = md.parent.name if md.parent != tmp_root else (Path(fname).stem or "skill")
            text = md.read_text(encoding="utf-8", errors="replace")
            over = _skill_too_big(text)
            if over:
                return over      # 包里那篇正文超限：整包装进来照样毒着每一步的提示词
            fm_name, _note = _skill_name_from_md(text, pkg_name)
            try:
                result = _install_skill_dir(md.parent, fm_name or pkg_name)
            except ValueError as e:
                return JSONResponse({"detail": str(e)}, 400)
            return {"ok": True, **result}

        if lower.endswith(".md") or fname == "SKILL.md":
            text = raw.decode("utf-8", errors="replace")
            over = _skill_too_big(text)
            if over:
                return over
            stem = Path(fname).stem
            fm_name, _note = _skill_name_from_md(text, stem)
            name = _norm_skill_name(fm_name or stem)
            if not name:
                return JSONResponse({"detail": "无法确定技能名（文件名与 frontmatter.name 均无效）"}, 400)
            dest = paths.USER_SKILLS_DIR / name
            if dest.exists():
                return JSONResponse({"detail": f"技能「{name}」已存在，请先删除或改名"}, 400)
            dest.mkdir(parents=True, exist_ok=True)
            (dest / "SKILL.md").write_text(text, encoding="utf-8")
            return {"ok": True, "name": name, "files": 1, "chars": len(text)}

        return JSONResponse(
            {"detail": "仅支持 .zip（标准 skill 包）或 .md（SKILL.md）文件"}, 400)
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)



# ---------- 流程运行（智能体执行 / SSE 实时 / 检查点 / 修订 / 重跑） ----------
class RunStartIn(BaseModel):
    label: str = ""
    brief: str = ""
    engine: str = ""
    model: str = ""
    workdir: str = ""

class ReviseIn(BaseModel):
    index: int
    instruction: str


def _sse_pack(ev: dict) -> str:
    import json as _json
    return f"data: {_json.dumps(ev, ensure_ascii=False)}\n\n"


@app.post("/api/pipelines/{name}/run")
def start_pipeline_run(name: str, b: RunStartIn):
    """启动一次流程运行：返回 run（含 id），前端跳转运行控制台。"""
    try:
        run = runner.start_run(name, b.label or "", b.brief or "", b.engine or "",
                               b.model or "", b.workdir or "")
    except runner.BadRunRequest as e:
        return JSONResponse({"detail": str(e)}, 400)
    except ValueError as e:
        return JSONResponse({"detail": str(e)}, 404)
    except Exception as e:
        return JSONResponse({"detail": f"启动失败: {e}"}, 500)
    return {"ok": True, "run": run}


@app.get("/api/runs")
def list_runs(pipeline: str = "", limit: int = 50):
    # 只写 min(limit,200) 挡不住负数，而 SQLite 的 LIMIT 为负 = 无上限 ——
    # `?limit=-1` 就能把整表连同每行的 steps blob 一起拉进内存。
    return {"runs": db.list_runs(pipeline or None, max(1, min(limit, 200)))}


@app.get("/api/runs/{run_id}")
def get_run(run_id: str):
    run = db.get_run(run_id)
    if not run:
        return JSONResponse({"detail": "运行不存在"}, 404)
    return {"run": run, "artifacts": runner.read_artifacts(run),
            "logs": runner.list_logs(run_id)}


@app.delete("/api/runs/{run_id}")
def delete_run(run_id: str):
    if not db.get_run(run_id):
        return JSONResponse({"detail": "运行不存在"}, 404)
    runner.cancel_run(run_id)
    runner.drop_bus(run_id)
    import shutil
    shutil.rmtree(runner.workspace_dir(run_id), ignore_errors=True)
    db.delete_run(run_id)
    return {"ok": True}


@app.get("/api/runs/{run_id}/stream")
def stream_run(run_id: str):
    """SSE 实时事件流：快照 state 打底 + 纯实时事件（无历史重放，客户端无重复）。

    不在终态主动关流：运行完成后用户仍可发起局部修订，事件照常推送；
    连接由客户端关闭（离开页面）或运行被删除时结束。
    """
    import asyncio
    if not db.get_run(run_id):
        return JSONResponse({"detail": "运行不存在"}, 404)
    bus = runner.bus_for(run_id)
    q = bus.subscribe()

    async def gen():
        try:
            # 一条当前状态快照打底（step.delta 为权威全文，客户端据此覆盖）
            for ev in bus.snapshot_events():
                yield _sse_pack(ev)
            idle = 0.0
            while True:
                got = False
                while q:
                    ev = q.pop(0)
                    got = True
                    if ev.get("type") == "state":
                        run = db.get_run(run_id)
                        yield _sse_pack({"type": "state", "run": run})
                    else:
                        yield _sse_pack(ev)
                if not got:
                    await asyncio.sleep(0.12)
                    idle += 0.12
                    if idle >= 15:
                        yield ": keepalive\n\n"
                        idle = 0.0
                    run = db.get_run(run_id)
                    if not run:
                        yield _sse_pack({"type": "done"})
                        return
        finally:
            bus.unsubscribe(q)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "X-Accel-Buffering": "no"})


@app.post("/api/runs/{run_id}/continue")
def continue_run(run_id: str):
    """检查点确认后继续执行后续步骤。"""
    try:
        run = runner.resume_run(run_id)
    except ValueError as e:
        return JSONResponse({"detail": str(e)}, 400)
    return {"ok": True, "run": run}


@app.post("/api/runs/{run_id}/cancel")
def cancel_run(run_id: str):
    try:
        run = runner.cancel_run(run_id)
    except ValueError as e:
        return JSONResponse({"detail": str(e)}, 404)
    return {"ok": True, "run": run}


class RerunIn(BaseModel):
    index: int


@app.post("/api/runs/{run_id}/rerun")
def rerun_run(run_id: str, b: RerunIn):
    """从第 index 步（0 基）起重跑，其后步骤一并复位。"""
    try:
        run = runner.rerun_from(run_id, b.index)
    except ValueError as e:
        return JSONResponse({"detail": str(e)}, 400)
    return {"ok": True, "run": run}


@app.post("/api/runs/{run_id}/revise")
def revise_run(run_id: str, b: ReviseIn):
    """对话式局部修订：让智能体就地修改该步产物文件。"""
    if not b.instruction.strip():
        return JSONResponse({"detail": "修改要求不能为空"}, 400)
    try:
        result = runner.revise_step(run_id, b.index, b.instruction)
    except ValueError as e:
        return JSONResponse({"detail": str(e)}, 400)
    return result


@app.get("/api/runs/{run_id}/files")
def run_files(run_id: str):
    if not db.get_run(run_id):
        return JSONResponse({"detail": "运行不存在"}, 404)
    return {"files": runner.list_workspace(run_id)}


@app.get("/api/runs/{run_id}/files/{fpath:path}")
def run_file_detail(run_id: str, fpath: str):
    """预览工作区里的一个文件（运行台的实时面板用）。"""
    if not db.get_run(run_id):
        return JSONResponse({"detail": "运行不存在"}, 404)
    try:
        return runner.read_workspace_file(run_id, fpath)
    except FileNotFoundError:
        return JSONResponse({"detail": "文件不存在"}, 404)
    except Exception as e:
        return JSONResponse({"detail": f"读取失败：{e}"}, 500)


@app.post("/api/workspaces/cleanup-orphans")
def cleanup_orphan_workspaces():
    """删掉统计页报的那些孤儿工作区。**删除不可恢复**：入口先挡活跃运行——
    孤儿=没有运行记录，但记录被人为动过的瞬间"没人用"这个前提会破；
    另外清理与正在跑的智能体绝不能并发。确认框在前端（ffAsk，写明不可恢复）。"""
    if db.count_active_runs() > 0:
        return JSONResponse({"detail": "有任务正在运行，等它们结束再清理"}, 409)
    return runner.cleanup_orphan_workspaces()


@app.get("/api/runs/{run_id}/artifacts")
def run_artifacts(run_id: str):
    run = db.get_run(run_id)
    if not run:
        return JSONResponse({"detail": "运行不存在"}, 404)
    return {"artifacts": runner.read_artifacts(run)}


@app.get("/api/runs/{run_id}/artifacts/{fname:path}")
def download_artifact(run_id: str, fname: str):
    run = db.get_run(run_id)
    if not run:
        return JSONResponse({"detail": "运行不存在"}, 404)
    try:
        f = runner.ws_file(run_id, fname)
    except FileNotFoundError:
        return JSONResponse({"detail": "文件不存在"}, 404)
    # inline：图片 / PDF 要能在预览面板里直接显示，下载靠 <a download>
    return FileResponse(f, filename=f.name, content_disposition_type="inline")


@app.get("/api/runs/{run_id}/logs")
def run_logs(run_id: str):
    if not db.get_run(run_id):
        return JSONResponse({"detail": "运行不存在"}, 404)
    return {"logs": runner.list_logs(run_id)}


@app.get("/api/runs/{run_id}/logs/{name}")
def run_log_detail(run_id: str, name: str, lines: int = 500):
    """读一份转录日志尾部。只接受纯文件名，路径校验在 runner.read_log 里。"""
    if not db.get_run(run_id):
        return JSONResponse({"detail": "运行不存在"}, 404)
    try:
        return runner.read_log(run_id, name, lines)
    except FileNotFoundError as e:
        return JSONResponse({"detail": str(e)}, 404)
    except ValueError as e:
        return JSONResponse({"detail": str(e)}, 400)


# ---------- 智能体引擎与内置库 ----------
class EngineIn(BaseModel):
    default_engine: str | None = None
    claude_cli: str | None = None
    codex_cli: str | None = None
    agent_timeout: str | None = None
    codex_sandbox: str | None = None
    permission_mode: str | None = None
    reasoning_effort: str | None = None
    step_retry: str | None = None
    auto_continue: str | None = None


@app.get("/api/agents")
def get_agents():
    """引擎可用性 + 接入配置（步骤里选引擎、设置页显示就绪状态都用它）。"""
    return {"agents": agents.agents_status(),
            "default_engine": db.get_setting("default_engine"),
            "claude_cli": db.get_setting("claude_cli"),
            "codex_cli": db.get_setting("codex_cli"),
            "agent_timeout": str(agents.step_timeout()),
            "codex_sandbox": agents.codex_sandbox(),
            "sandbox_options": list(agents.SANDBOXES),
            "permission_mode": agents.permission_mode(),
            "permission_modes": list(agents.PERM_MODES),
            "reasoning_effort": agents.reasoning_effort(),
            "effort_options": ["auto"] + list(agents.EFFORTS),
            "step_retry": str(agents.step_retry()),
            "auto_continue": "1" if agents.auto_continue() else "0",
            "paths": {"data": str(paths.DATA_DIR), "skills": str(paths.USER_SKILLS_DIR),
                      "workspaces": str(paths.WORKSPACES_DIR)}}


@app.post("/api/agents")
def save_agents(b: EngineIn):
    """局部更新：字段省略即不动，显式传空串才是清除。

    以前是边校验边写。于是 `{"default_engine":"codex","step_retry":"9"}` 这种
    一条合法、一条越界的请求，会把 default_engine 先落库、再在 step_retry 上回 400 ——
    界面报"保存失败"，服务端其实已经改了一半。现在先全部校验完再一次性写。
    """
    def bad(msg):
        return JSONResponse({"detail": msg}, 400)

    pending: dict[str, str] = {}
    if b.default_engine is not None:
        v = b.default_engine.strip()
        if v and v not in agents.ENGINES:
            return bad("默认引擎无效")
        pending["default_engine"] = v
    for key, val in (("claude_cli", b.claude_cli), ("codex_cli", b.codex_cli)):
        if val is not None:
            pending[key] = val.strip()
    if b.agent_timeout is not None:
        try:
            n = int(b.agent_timeout)
        except ValueError:
            return bad("单步超时要填整数秒")
        if not 60 <= n <= 21600:
            return bad("单步超时范围 60–21600 秒")
        pending["agent_timeout"] = str(n)
    if b.codex_sandbox is not None:
        v = b.codex_sandbox.strip()
        if v and v not in agents.SANDBOXES:
            return bad("沙箱模式无效")
        pending["codex_sandbox"] = v
    if b.permission_mode is not None:
        v = b.permission_mode.strip()
        if v and v not in agents.PERM_MODES:
            return bad("这一档权限模式没有开放")
        pending["permission_mode"] = v
    if b.reasoning_effort is not None:
        v = b.reasoning_effort.strip()
        if v and v not in agents.EFFORTS and v != "auto":
            return bad("推理力度无效")
        pending["reasoning_effort"] = v
    if b.step_retry is not None:
        try:
            n = int(b.step_retry)
        except ValueError:
            return bad("重试次数要填整数")
        if not 0 <= n <= 3:
            return bad("重试次数范围 0–3")
        pending["step_retry"] = str(n)
    if b.auto_continue is not None:
        pending["auto_continue"] = "1" if b.auto_continue.strip() in ("1", "true") else "0"
    for k, v in pending.items():
        db.set_setting(k, v)
    agents.clear_bin_cache()
    return get_agents()


@app.post("/api/reveal")
def reveal_dir(which: str = "data", run_id: str = "", file: str = "",
             engine: str = "", key: str = ""):
    """在资源管理器里打开本机目录。只认白名单键，或数据库里真实存在的一次运行 ——
    路径一律由 runner 拼，绝不接受调用方直接给的目录。"""
    import subprocess
    if which == "run":
        if not db.get_run(run_id):
            return JSONResponse({"detail": "运行不存在"}, 404)
        try:
            target = runner.ws_file(run_id, file) if file else runner.workspace_dir(run_id).resolve()
        except FileNotFoundError:
            return JSONResponse({"detail": "文件不存在"}, 404)
        args = ["explorer", f"/select,{target}"] if file else ["explorer", str(target)]
    elif (which or "").strip() == "agent":
        # 两家 CLI 的目录：路径由 cli_inventory 自己算，调用方只能挑引擎和类目键。
        # 这里绝不 mkdir —— 那是用户机器上别人的配置面，没有就是没有。
        d = cli_inventory.reveal_path(engine, key)
        if not d:
            return JSONResponse({"detail": "这台机器上没有这一项"}, 404)
        args = ["explorer", str(d)]
    else:
        targets = {"data": paths.DATA_DIR, "skills": paths.USER_SKILLS_DIR,
                   "workspaces": paths.WORKSPACES_DIR}
        d = targets.get((which or "").strip())
        if not d:
            return JSONResponse({"detail": "未知目录"}, 400)
        d.mkdir(parents=True, exist_ok=True)
        args = ["explorer", str(d)]
    try:
        subprocess.Popen(args)
    except Exception as e:
        return JSONResponse({"detail": f"打开失败：{e}"}, 500)
    return {"ok": True}


@app.get("/api/agents/capabilities")
def agent_capabilities():
    """两家 CLI 自己的配置面（记忆/技能/命令/子智能体/MCP/钩子/插件）。

    只读，且只回名字、条数和路径 —— 那些文件里就是真密钥
    （~/.claude/settings.json 的 env、~/.codex/config.toml 的 bearer token）。
    要改请走各自的官方入口，Loom 不做第二套配置编辑器。"""
    return cli_inventory.scan()


@app.get("/api/agents/capabilities/{engine}/{key}")
def cap_preview(engine: str, key: str):
    """预览一份用户自己写的 markdown（记忆 / 技能 / 命令 / 子智能体）。"""
    d = cli_inventory.preview_text(engine, key)
    if not d:
        return JSONResponse({"detail": "没有这一项"}, 404)
    return d


@app.get("/api/agents/capabilities/{engine}/{key}/{name}")
def cap_preview_named(engine: str, key: str, name: str):
    d = cli_inventory.preview_text(engine, key, name)
    if not d:
        return JSONResponse({"detail": "没有这一项"}, 404)
    return d


class MemoryIn(BaseModel):
    engine: str = ""
    content: str = ""


@app.put("/api/agents/capabilities/memory")
def cap_write_memory(b: MemoryIn):
    """保存全局记忆文件。请求体里只有引擎名和正文 —— 路径由 cli_inventory 那份
    清单自己算，所以这个接口写不到清单之外的任何文件。"""
    r = cli_inventory.write_memory(b.engine, b.content)
    if not r["ok"]:
        return JSONResponse({"detail": r["detail"]}, 400)
    return {"ok": True, "path": r["path"], "bytes": r["bytes"]}


@app.get("/api/stats")
def usage_stats():
    """设置页「使用统计」：全部由 runs 表的 step.meta 与工作区实际占用算出来。"""
    return runner.usage_stats()


# ---------- 自动更新 ----------
class UpdateUrlIn(BaseModel):
    url: str = ""


@app.get("/api/update")
def update_state():
    s = updater.snapshot()
    s["active_runs"] = db.count_active_runs()
    return s


@app.post("/api/update/url")
def update_set_url(b: UpdateUrlIn):
    """更新清单地址。留空 = 用内置的 COS 地址；填错比不填更糟，所以校验协议。"""
    u = (b.url or "").strip()
    if u and not u.startswith("https://"):
        return JSONResponse({"detail": "更新清单地址必须是 https"}, 400)
    db.set_setting("update_url", u)
    return updater.check(force=True) | {"active_runs": db.count_active_runs()}


@app.post("/api/update/apply")
def update_apply():
    """装上已下载好的安装包并退出。在跑的任务由前端先弹确认，这里再兜一道。"""
    busy = db.count_active_runs()
    if busy:
        return JSONResponse({"detail": f"还有 {busy} 个任务在跑或停在检查点，先处理完再更新"}, 409)
    r = updater.apply_update()
    if not r.get("ok"):
        return JSONResponse({"detail": r.get("detail") or "更新未能开始"}, 400)
    return r


@app.post("/api/update/check")
def update_check():
    return updater.check(force=True) | {"active_runs": db.count_active_runs()}


@app.post("/api/update/download")
def update_download():
    return updater.start_download() | {"active_runs": db.count_active_runs()}


# ---------- 设置（外观 / 键值配置） ----------
@app.post("/api/settings/bulk")
def save_settings_bulk(patch: dict):
    """一次保存多个外观键（语言 / 主题 / 字号…）。只收 ui_ 前缀，
    引擎与端点配置必须走 /api/agents、/api/presets，避免这里绕过去。"""
    for k, v in (patch or {}).items():
        if not isinstance(k, str) or not k.startswith("ui_"):
            continue
        db.set_setting(k.strip(), "" if v is None else str(v))
    return {"ok": True}

@app.get("/api/settings")
def get_settings():
    return db.get_all_settings()


class PresetIn(BaseModel):
    name: str
    provider: str = "openai"
    api_base: str = ""
    api_key: str = ""
    model: str = ""
    extra: dict = {}

class PresetUpdate(BaseModel):
    name: str = ""
    provider: str = ""
    api_base: str = ""
    api_key: str = ""   # 空 = 保留原密钥
    model: str = ""
    extra: dict = None
    clear_key: bool = False

class PresetTestIn(BaseModel):
    id: int = 0
    provider: str = "openai"
    api_base: str = ""
    api_key: str = ""
    model: str = ""


class ModelsListIn(BaseModel):
    id: int = 0
    api_base: str = ""
    api_key: str = ""
    provider: str = "openai"


def _preset_payload():
    """给前端的预设清单。api_key 一律不外泄：以前这些路由把整行 SELECT * 原样返回，
    于是密钥随 GET /api/providers 走一遍网络，前端又把它回传给 /test 和 /models/list。
    现在只回有没有密钥和末四位，测试/拉模型改按 id 由服务端自己取。"""
    out = []
    for p in db.list_presets():
        q = dict(p)
        k = q.pop("api_key", "") or ""
        q["has_key"] = bool(k)
        q["key_hint"] = ("••••" + k[-4:]) if len(k) > 4 else ("•" * min(len(k), 4) if k else "")
        out.append(q)
    d = db.get_default_preset()
    return {"presets": out, "default": (d["id"] if d else None)}


def _preset_creds(pid: int, api_base: str, api_key: str):
    """按 id 让服务端自己去库里取端点与密钥 —— 清单已经不回传 api_key 了，
    测试和拉模型也不能再靠前端把密钥带回来。

    但**库里存的密钥永远不跟着调用方指定的端点走**。编辑已存预设时前端会把 base 连同
    id 一起传来（密钥框是空的，因为清单不外泄密钥），那正好是"把真密钥发去一个前端
    指定的地址"的通道：`api_base or 库里base` 让调用方的 base 赢，而 key 兜底取库里的。
    现在改端点就必须重新填密钥（git credential / gh 都是这个规矩）。
    返回 (base, key, err)；err 非空时调用方直接回 400。
    """
    if not pid:
        return api_base, api_key, ""
    p = db.get_preset(pid)
    if not p:
        return api_base, api_key, ""
    stored_base = (p.get("api_base") or "").strip()
    stored_key = p.get("api_key") or ""
    want_base = (api_base or "").strip()
    if want_base and want_base != stored_base:
        if not (api_key or "").strip():
            return want_base, "", "端点改过了，密钥不会跟着去新地址：请重新填一次密钥"
        return want_base, api_key.strip(), ""
    return (want_base or stored_base), (api_key or stored_key), ""


def _redact(msg: str, key: str) -> str:
    """上游网关的 4xx body 会被原样回吐，里面可能带我们发过去的 Authorization。"""
    s = str(msg or "")
    return s.replace(key, "[REDACTED]") if key else s


@app.get("/api/providers")
def list_providers():
    return _preset_payload()


@app.post("/api/providers")
def add_provider(p: PresetIn):
    name = p.name.strip()
    if not name:
        return JSONResponse({"detail": "预设名不能为空"}, 400)
    if db.get_preset_by_name(name):
        return JSONResponse({"detail": f"预设名「{name}」已存在"}, 400)
    pid = db.add_preset(name, (p.provider or "openai"), p.api_base, p.api_key, p.model,
                        extra=p.extra or {})
    return {"ok": True, "id": pid, **_preset_payload()}


@app.put("/api/providers/{pid}")
def update_provider(pid: int, u: PresetUpdate):
    p = db.get_preset(pid)
    if not p:
        return JSONResponse({"detail": "not found"}, 404)
    new_name = u.name.strip() or p["name"]
    dup = db.get_preset_by_name(new_name)
    if dup and dup["id"] != pid:
        return JSONResponse({"detail": f"预设名「{new_name}」已存在"}, 400)
    api_key = p["api_key"]
    if u.clear_key:
        api_key = ""
    elif u.api_key.strip():
        api_key = u.api_key.strip()
    db.update_preset(pid, name=new_name, provider=u.provider or p["provider"],
                     api_base=u.api_base or p["api_base"], api_key=api_key,
                     model=u.model or p["model"], extra=(u.extra or None))
    return {"ok": True, **_preset_payload()}


@app.delete("/api/providers/{pid}")
def del_provider(pid: int):
    if not db.get_preset(pid):
        return JSONResponse({"detail": "not found"}, 404)
    db.delete_preset(pid)
    return {"ok": True, **_preset_payload()}


@app.post("/api/providers/{pid}/default")
def set_default(pid: int):
    if not db.get_preset(pid):
        return JSONResponse({"detail": "not found"}, 404)
    db.set_default_preset(pid)
    return {"ok": True, **_preset_payload()}


@app.post("/api/providers/test")
def test_provider(t: PresetTestIn):
    base, key, err = _preset_creds(t.id, t.api_base, t.api_key)
    if err:
        return JSONResponse({"detail": err}, 400)
    ok, msg = llm.test_connection(t.provider, base, key, t.model)
    return {"ok": ok, "msg": _redact(msg, key)}


_MODEL_COMPAT_SUFFIXES = (
    "/api/claudecode", "/api/anthropic", "/apps/anthropic", "/api/coding",
    "/claudecode", "/anthropic", "/coding", "/claude",
)


def _model_url_candidates(base: str):
    """从端点推 /models 候选，兼容 Anthropic 子路径。

    以前这里还收一个 `models_url` 覆盖参数和一个 `is_full_url` 开关，前端零引用
    （grep static/ 无命中）、测试零覆盖，唯一作用是把服务端要 GET 的地址整个交给
    调用方 —— 一个没有入口的后端能力，同时是纯攻击面。删掉。
    """
    b = (base or "").strip().rstrip("/")
    if not b:
        return []
    out = []
    last = b.rsplit("/", 1)[-1]
    versioned = len(last) > 1 and last[0] == "v" and last[1:].isdigit()
    if versioned:
        out.append(b + "/models")
        if last != "v1":
            out.append(b + "/v1/models")
    else:
        out.append(b + "/v1/models")
    for suffix in _MODEL_COMPAT_SUFFIXES:
        if b.endswith(suffix):
            root = b[:-len(suffix)].rstrip("/")
            out += [root + "/v1/models", root + "/models"]
            break
    return list(dict.fromkeys(out))


@app.post("/api/models/list")
def models_list(b: ModelsListIn):
    """按候选策略拉取模型列表，支持 OpenAI/Anthropic/Gemini 认证头。"""
    import requests as _requests
    b.api_base, b.api_key, err = _preset_creds(b.id, b.api_base, b.api_key)
    if err:
        return {"ok": False, "models": [], "error": err, "tried": []}
    urls = _model_url_candidates(b.api_base)
    if not urls:
        return {"ok": False, "models": [], "error": "缺少或无法解析模型端点", "tried": []}
    proto = (b.provider or "openai").lower()
    headers = {"Accept": "application/json"}
    if b.api_key:
        if proto in ("anthropic", "anthropic-messages"):
            headers["x-api-key"] = b.api_key
            headers["anthropic-version"] = "2023-06-01"
        elif proto in ("gemini", "google-generative-ai"):
            headers["x-goog-api-key"] = b.api_key
        else:
            headers["Authorization"] = "Bearer " + b.api_key
    errors = []
    for url in urls:
        try:
            resp = _requests.get(url, headers=headers, timeout=15)
            if resp.status_code in (404, 405):
                errors.append(f"{url}: HTTP {resp.status_code}")
                continue
            if resp.status_code in (401, 403) and proto in ("anthropic", "anthropic-messages"):
                # 部分 Anthropic 兼容服务的 /models 仍只接受 Bearer，安全地重试同一候选。
                retry_headers = dict(headers)
                retry_headers.pop("x-api-key", None)
                retry_headers["Authorization"] = "Bearer " + b.api_key
                resp = _requests.get(url, headers=retry_headers, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            raw = data.get("data") or data.get("models") or data.get("items") or []
            if isinstance(raw, dict):
                raw = raw.get("data") or raw.get("items") or []
            models = []
            for item in raw if isinstance(raw, list) else []:
                if isinstance(item, str):
                    models.append({"id": item})
                elif isinstance(item, dict):
                    mid = item.get("id") or item.get("model") or item.get("name")
                    if mid:
                        models.append({**item, "id": mid})
            models.sort(key=lambda x: str(x.get("id", "")))
            return {"ok": True, "models": models, "endpoint": url, "tried": urls}
        except Exception as e:
            msg = str(e).replace(b.api_key, "[REDACTED]") if b.api_key else str(e)
            errors.append(f"{url}: {msg[:180]}")
    return {"ok": False, "models": [], "error": "；".join(errors) or "无法获取模型列表",
            "tried": urls}
