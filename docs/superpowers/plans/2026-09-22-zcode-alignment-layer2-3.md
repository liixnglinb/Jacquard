# Loom 织流 · 照 ZCode 深度对齐（层 2 收尾 + 层 3）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把侧栏导航、键位、项目行、首页输入台、更新浮层、圆角节奏这六处，从"看起来像 ZCode"改成"按 ZCode 的规则实现"，并让每条规则都有一条契约测试钉住。

**Architecture:** 仍然是 FastAPI + 无构建步骤的原生 JS（`static/app.js` 单文件外壳 + `ui.js` i18n/外观 + `editor.js`/`run.js` 视图）。所有改动都落在前端；后端只在需要确认"这个控件有没有真能力"时被读，不改。每个改动配一条 pytest 契约测试（源码级正则/静态断言，可选 node 子进程真跑一段 JS），不发版即全绿。

**Tech Stack:** Python 3.12（`C:\Users\李星历\AppData\Local\Programs\Python\Python312\python.exe`，`python` 不在 PATH）、pytest、原生 HTML/CSS/JS、pywebview 壳、无框架。

**Spec:** 没有单独的 spec 文件 —— 这轮的"设计文档"就是下面这张「参考实现的原文位置」表（brainstorming 阶段在对话里逐段过完并获批，未另立文档）。执行时以该表为准，每条改动都能追溯到一行参考代码或 `DESIGN.md` 的一条规则。

**任务依赖：** Task 2 → Task 3（Task 3 的和弦标签读 Task 2 的 `KEYMAP`）；Task 1 → Task 5/6（新写的 `.tk-bar` / `.up-card` 用的是重排后的档位）。Task 4、Task 7 各自独立，但 Task 7 要等 2/3/5 落地才能照抄最终结构。

**参考实现的原文位置**（只读克隆 `D:\AI-Tools-Data\ref\ZCode`，Apache-2.0。**这些是本计划所有断言的来源，不要凭印象改**）：

| 事实 | 出处 |
| --- | --- |
| 键位唯一事实来源是一张命令表 | `packages/shared/src/shortcutCommands.ts:57-100` |
| `newTask` = `CmdOrCtrl+N`；`openCommandCenter` = `CmdOrCtrl+K`（双默认 `Ctrl+Shift+P`）；`openSettings` = `Ctrl+,`；`toggleSidebar` = `Ctrl+B`；`switchTheme` = `Ctrl+Shift+L`；`findInTask` = `Ctrl+F` | 同上 :63-83 |
| 输入框作用域：`composerSend` = `Enter`，`composerInsertNewline` = `Shift+Enter`（"杀伤半径被限制在输入框内"） | 同上 :40-45, :91-97 |
| 输入台是三段：上=contextHeader（工作区/分支）、中=textarea、下=`group/toolbar` | `packages/ui/src/prompt-editor/ChatPromptEditor.tsx:347, 388`；`ConversationComposer.tsx:2236` |
| 工具条左 cluster 第一个是 `+` 动作菜单（:406 注释明确"必须排第一"），右 cluster `ml-auto` 依次 上下文用量 → 模型 → 思考等级 → 发送 | `ChatPromptEditor.tsx:259, 388-415`；`ConversationComposer.tsx:2038-2099` |
| 发送是 `type="submit"`、`rounded-lg bg-brand text-foreground-inverse`、`ArrowUpIcon`，**在工具条右下角**，不是通栏按钮 | `ConversationComposer.tsx:2038-2099` |
| 圆角跟"可见圆角容器的嵌套层数"走，不跟组件重要性走：第一个圆角容器 `rounded-xl`，往里 `lg → md → sm`，`sm` 是底线 | `DESIGN.md:285-293` |
| `rounded-2xl` 只有四个批准例外：主输入台壳、会话状态浮层、**toast**、品牌图标底板 | `DESIGN.md:295-302` |
| 控件圆角看最近的圆角父容器：父 ≥ `xl` → 控件 `lg`；父 `lg` → `md`；父 `md/sm` → `sm` | `DESIGN.md:308-318` |
| 对话框壳 `rounded-2xl`，壳不计入内容层级，内容从 `xl` 重新开始 | `DESIGN.md:320-325` |
| 菜单/浮层壳 `rounded-lg`，菜单项 `rounded-md`，项里再嵌圆角用 `rounded-sm` | `DESIGN.md:327-333` |
| `rounded-full` 只留给**故意做成胶囊/正圆**的东西；按钮、标签、计数器、图标按钮不因类型而获得 | `DESIGN.md:336-341` |
| 图标按钮保持方正（"Keep icon-only buttons square"） | `DESIGN.md:384` |
| 间距基线 4px，节奏 4 / 8 / 12 / 16 / 20-24 | `DESIGN.md:265-273` |
| 侧栏分组嵌套用**一条左边框轨道**（`ml-4 border-l py-px pl-2`），不是加 padding | `packages/ui/src/workspace-grouped-tasks/types.ts:35-47` |
| 次行是一个 `ml-auto` 的紧凑槽：状态点 → 可选时钟 → **相对时间放最后**；计数徽章只在分组标题上 | `task-row.tsx:186-232`；`types.ts:35-47` |
| 相对时间四档、**紧凑写法**、没有月/年档：`<1min 刚刚` / `<60min {n}分` / `<24h {n}小时` / 否则 `{n}天` | `packages/ui/src/lib/taskListItemPresentation.ts:33-53`；文案 `i18n/locales/zh-CN.ts:1474-1477` |
| 更新是"胶囊 + 居中对话框"两件套，胶囊确实 `rounded-full` | `UpdateStatusButton.tsx:127-136` |
| 对话框三态标题：`New version v{version}` / `Downloading v{version}` / `v{version} is ready`；进度条 `h-2`；重启按钮 `size="lg"` 文案 "Restart to update"，**无二次确认** | `UpdateStatusDialog.tsx:91, 143-147, 221-231`；`updateStatusModel.ts:7, 82`；`i18n/locales/en-US.ts:1240-1242` |
| 顶层浮层里元素顺序：侧栏开关 → 导航 → 新建任务 → 更新胶囊 | `DesktopTopOverlay.tsx:211-217` |

**明确读不到的**：`rounded-sm/md/lg/xl` 的绝对像素。该仓库 Tailwind v4 是 CSS-first，`@theme`（`packages/ui/src/styles.css:137`）没定义任何 `--radius-*`，值来自没被 sparse-checkout 的 `shadcn/tailwind.css` 预设。**所以本计划只锁"相对层级"这条被文档化的规则，不假装量到了绝对值。** 我们能钉的绝对值只有一处旁证：`DESIGN.md:179` 的"16px 外壳 / 12px 面板 / 4px 内缩"。

## Global Constraints

- **产品红线**：正文只能由本机 CLI 智能体（claude / codex）产出，Loom 不直连任何大模型接口。本计划不新增任何直连通道。
- **后端不支持的控件一律不放。** 判断标准是"这个字段后端真读"。本计划唯一新增的控件（引擎选择器）已核过：`RunStartIn.engine: str = ""`（`app/main.py:490-493`）→ `start_run(..., engine)`（`app/runner.py:841-856`）用 `agents.ENGINES = ("claude","codex")` 校验后覆盖每一步。**"每条 run 选模型"后端没有参数，所以不做模型选择器。**
- **一个功能只留一个入口。** 删掉的重复入口要在同一次提交里删干净（CSS 规则、i18n key、`RAIL_HIDDEN` 条目一起走），不留兼容分支。
- 本文**不含任何密钥**，只写路径。密钥在 `..\个人开发信息\个人网站信息\Voyra个人网站说明.md`（严禁入库）。
- 动 GitHub Actions / secret 前先 `unset GITHUB_TOKEN GH_TOKEN`。**别改系统 hosts。**
- `upload_cos.py` 现在**只列不删**。孤儿工作区只能看不能清。
- **不跑真的 claude / codex CLI**（烧配额，且走用户本机中转）。任何要"真跑一次"的验证都停下来问人。
- **未获确认不打包、不发版。** Task 6 的"重启并更新"会第一次真正走打包态 `apply_update()` —— 那条路径至今没在真包里验过（见 [[loom-updater-status]]），必须单独获准。
- rem **只准出现在 `--fs-*`**（几何一律 px）。见 `test_geometry_never_uses_rem`。
- 改了 `static/` 就要升 `static/index.html` 里的 `?v=` 令牌（10 处同一个值），否则浏览器侧缓存骗你"没生效"。
- 验证一律用**临时库**，不许碰真 SQLite。配方见 `HANDOFF.md` 与 [[loom-dev-verify-loop]]：先 patch `app.paths.DATA_DIR/DB_DIR/USER_SKILLS_DIR/EXPORT_DIR/WORKSPACES_DIR`，再 `app.db.DB_PATH`，**然后**才 `from app.main import app`。
- 截图能力本会话不可用（`NATIVE_BROWSER_VIEWPORT_UNAVAILABLE`）。**能算就算，别声称"我看过了"**；只能数值验证的地方在汇报里写清楚。

**每条任务通用的两个命令：**

```bash
# 跑全量契约测试（不需要网络，全绿即可）
PYTHONUTF8=1 "/c/Users/李星历/AppData/Local/Programs/Python/Python312/python.exe" -m pytest -q

# 升缓存令牌（改过 static/ 的任何一条任务末尾都要做）
OLD=$(grep -o 'v=[0-9a-f]\{8\}' static/index.html | head -1 | cut -d= -f2)
NEW=$(git rev-parse --short=8 HEAD)
sed -i "s/?v=$OLD/?v=$NEW/g" static/index.html
grep -c "?v=$NEW" static/index.html    # 期望 10
```

---

### Task 1: 圆角按嵌套层数重排（先把梯子摆正，后面几条任务才有的谈）

**Files:**
- Modify: `static/style.css:70-72`（梯子定义）、`:821`（`.cp-send`）、`:952`（`.toast`）、`:507`（`.sb-pop`）、`:990-991`（`.ff-menu`）。另需知道：运行台主输入壳 `.composer-inner` 在 `:811`，档位已是 `--r-5`，本任务不动它的规则
- Test: `tests/test_static_contract.py`（`RADIUS_SCALE` 在 :131，`test_border_radius_only_uses_the_scale` 在 :276-284）
- Modify（另一个仓库、另一次提交）: `D:\Voyra 个人网站\public\modelflow\index.html:41`（下载页自己抄了一份圆角梯子，软件改档它必须跟）

**Interfaces:**
- Consumes: 无
- Produces: 圆角梯子 `--r-1..--r-5` = `4/6/8/12/16px`；契约测试 `NESTED_RADIUS` 表（后续任务新写的类要往这张表里加一行）

- [ ] **Step 1: 写失败的测试**

追加到 `tests/test_static_contract.py` 末尾：

```python
# ---------------- 圆角跟嵌套层数走（DESIGN.md:285-341） ----------------

LADDER = ["--r-1", "--r-2", "--r-3", "--r-4", "--r-5"]
# 相对层级是参考实现写进文档的；绝对像素只有一处旁证（DESIGN.md:179 的 16/12/4px），
# 所以这里锁"四档递减 + 顶层 16px"，不去假装量到了 Tailwind 的预设值。
LADDER_PX = ["4px", "6px", "8px", "12px", "16px"]

# 类名 -> 它「应该」用的那一档。父壳和壳内控件成对写，改了一头另一头不许偷偷漂。
NESTED_RADIUS = {
    ".tk-card":   "--r-5",   # 主输入台壳 = 参考实现的四个 2xl 批准例外之一
    ".tk-input":  "--r-3",   # 父壳 ≥ xl → 控件取 lg
    ".cp-send":   "--r-3",   # 图标按钮：方正 + 同上（参考实现 "keep icon-only buttons square"）
    ".composer-inner": "--r-5", # 运行台底部那个也是主输入壳（style.css:811）
    ".modal-box": "--r-5",   # 对话框壳 = 2xl，且不计入内容层级
    ".card":      "--r-4",   # 第一层圆角容器 = xl
    ".sc-card":   "--r-4",
    ".st-panel":  "--r-4",
    ".sb-pop":    "--r-3",   # 浮层菜单壳 = lg（不是容器 xl）
    ".ff-menu":   "--r-3",
    ".ff-tip":    "--r-3",   # 提示也是浮层，跟菜单壳同档
    ".sb-fi":     "--r-2",   # 菜单项 = md
    ".ff-mi":     "--r-2",
}


def _radius_of(sel):
    """取某个选择器那条规则里的圆角档位；没有规则或非 var() 就返回原文。
    一个类若有多条规则，取第一条 —— 所以表里的类必须保持单一圆角来源。"""
    m = re.search(r"(?<![\w.-])" + re.escape(sel) + r"\s*\{([^}]*)\}", CSS)
    assert m, f"找不到 {sel} 的规则，NESTED_RADIUS 表该更新了"
    v = re.search(r"border-radius:\s*([^;}]+)", m.group(1))
    assert v, f"{sel} 没有 border-radius，表里却写着它"
    got = v.group(1).strip()
    return (re.match(r"var\((--[\w-]+)\)", got) or [None, got])[1]


def test_radius_ladder_is_a_four_step_nesting_ladder():
    m = re.search(r"--r-1:([\d.]+px); --r-2:([\d.]+px); --r-3:([\d.]+px);"
                  r" --r-4:([\d.]+px); --r-5:([\d.]+px)", CSS)
    assert m, "圆角梯子不再是五个命名档，请连同本测试一起想清楚"
    assert list(m.groups()) == LADDER_PX, f"梯子漂了：{dict(zip(LADDER, m.groups()))}"


def test_radius_follows_the_container_nesting():
    got = {s: _radius_of(s) for s in NESTED_RADIUS}
    bad = {k: (v, NESTED_RADIUS[k]) for k, v in got.items() if v != NESTED_RADIUS[k]}
    assert not bad, f"圆角档位不对（值, 期望）：{bad}"


def test_pill_is_reserved_for_deliberate_pills():
    """"按钮、标签、计数器不因类型而获得 rounded-full"（DESIGN.md:336-341）。
    toast 是 2xl 例外之一，不是胶囊。正圆 50% 也不该出现在图标按钮上。"""
    assert "border-radius:50%" not in CSS, "图标按钮做成了正圆，参考实现要求方正"
    assert _radius_of(".toast") == "--r-5", "toast 属于 2xl 例外，不是胶囊"
    assert _radius_of(".cp-send") != "--r-pill", "发送键是图标按钮，不是胶囊"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `PYTHONUTF8=1 "<python>" -m pytest tests/test_static_contract.py -q -k "radius or pill or nesting"`
Expected: `test_radius_ladder_is_a_four_step_nesting_ladder` FAIL（现在是 `6/8/10/14/18px`）；`test_radius_follows_the_container_nesting` FAIL（`.sb-pop` / `.ff-menu` 是 `--r-4`）；`test_pill_is_reserved_for_deliberate_pills` FAIL（`50%` 与 `.toast` 都命中）

- [ ] **Step 3: 改梯子与那几处越档**

`static/style.css:70-72`：

```css
     r-5 大面（输入台 / 对话框） r-pill 胶囊
     ========================================================================== */
  --r-1:4px; --r-2:6px; --r-3:8px; --r-4:12px; --r-5:16px; --r-pill:999px;
```

`.cp-send`（:821）与 `.toast`（:952）、`.sb-pop`（:507）、`.ff-menu`（:991）按 `NESTED_RADIUS` 改档位：

```css
.cp-send{width:32px;height:32px;border-radius:var(--r-3);border:none;background:var(--btn-ink);color:var(--ink-inv);
.toast{...;border-radius:var(--r-5);background:var(--btn-ink);...}
.sb-pop{...;padding:6px;border-radius:var(--r-3);...}
.ff-menu{...;padding:5px;border-radius:var(--r-3);background:var(--bg-float);...}
```

`.composer-inner`（:811）就是运行台底部那个主输入壳，它已经在 `--r-5` 上，改梯子时**不用动它的规则**，只靠档位变化从 18px 收到 16px。

- [ ] **Step 4: 跑全量测试**

Run: `PYTHONUTF8=1 "<python>" -m pytest -q`
Expected: 全绿。**特别注意** `test_border_radius_only_uses_the_scale`（:276）与新表同时通过 —— 它只查"用了刻度内的档"，不查层级，两件事互补。

- [ ] **Step 5: 数值复核（不是目测）**

起一个临时库探针服务（配方在 `HANDOFF.md`），用 `chrome-devtools` 的 `evaluate_script` 读回计算值：

```js
JSON.stringify(['.tk-card','.tk-input','.cp-send','.toast','.sb-pop','.ff-menu','.ff-mi']
  .map(s=>[s, getComputedStyle(document.querySelector(s)).borderTopLeftRadius]))
```

Expected: `16px / 8px / 8px / 16px / 8px / 8px / 6px`。`.ff-mi` 需要先点开任一菜单才会存在；`.composer-inner` 只在运行页有。
若某条读不到 DOM，就在汇报里点名说"这条没实测"，别写"已验证"。

- [ ] **Step 6: 同步下载页那份梯子（另一个仓库、另一次提交）**

下载页把圆角梯子抄了一份自己的（`D:\Voyra 个人网站\public\modelflow\index.html:41`：`--r-1:6px;--r-2:8px;--r-3:10px;--r-4:14px;--r-5:18px`），页内 `.m-*` 全走这些 var()，所以软件改档后**这张 mock 会静默变旧**。改法只有那一行：

```bash
cd "D:/Voyra 个人网站/public/modelflow"
sed -i 's/--r-1:6px;--r-2:8px;--r-3:10px;--r-4:14px;--r-5:18px/--r-1:4px;--r-2:6px;--r-3:8px;--r-4:12px;--r-5:16px/' index.html
grep -c -- "--r-1:4px" index.html        # 期望 1
grep -n "border-radius:[0-9]" index.html | grep -v "9999\|50%" | head   # 期望空：页里也不该有硬写字号以外的圆角
```

配色那批 `--d-*` 上次已经逐值对齐过（[[flowforge-surface-color-policy]]），本次**不动颜色**。

```bash
cd "D:/Voyra 个人网站" && git add public/modelflow/index.html
git commit -m "modelflow: 圆角梯子跟软件同步（4/6/8/12/16）"
```

**不推送** —— 推送即上线，要单独授权。

- [ ] **Step 7: 升令牌 + 提交**

```bash
# 通用两步：升 ?v= 令牌（见 Global Constraints），然后
git add static/style.css tests/test_static_contract.py static/index.html
git commit -m "refactor(ui): 圆角按嵌套层数重排成 4/6/8/12/16，图标按钮和 toast 退出胶囊档"
```

---

### Task 2: 键位改成一张表，并按参考实现改绑

现状：绑定写死在 `static/app.js:1948-1950` 的 `if(k===...)` 里，文档又独立写在 `secShortcuts()`（:931-937）的字面数组里，靠一条正则测试两边对齐。参考实现是一张 `SHORTCUT_COMMANDS` 表（`shortcutCommands.ts:61`，注释原话"快捷键命令的唯一事实来源"）。**深度模仿 = 把表搬过来，而不是只改两个字母。**

改绑：新建任务 `Ctrl+K → Ctrl+N`；搜索 `Ctrl+N 位置（现在搜索只在 `.sb-acts` 有个图标钮）→ Ctrl+K`；新增 `Ctrl+Shift+L` 切主题。`Ctrl+,` / `Ctrl+B` / `Enter` / `Shift+Enter` 本来就对得上，进表即可。

**Files:**
- Modify: `static/app.js:1936-1970`（keydown 处理）、`:927-957`（`secShortcuts`）、`:931-937`（rows）、`:80`（`#sbNew` 上的 `Ctrl K` 字样）、`:355-365` 附近（复用现成的 `setAppearance` 切换写法）
- Modify: `static/ui.js:212-218` 与 `:475-481`（`sc.*` 两份字典）
- Test: `tests/test_static_contract.py:375-385`（`test_rail_toggle_is_reachable_and_documented` 的两条正则）

**Interfaces:**
- Consumes: `window.taskModal()`、`window.sbSearch(e)`（`app.js:252`，开头是 `if(e) e.stopPropagation()`，所以无参调用安全）、`window.sbToggle()`、`nav.go('settings')`、`window.setAppearance({theme})`（`ui.js:781`）、`document.documentElement.dataset.theme`（`ui.js:662`）
- Produces: `const KEYMAP`（`{id, chord, key, mod, scope}`）、`const KEY_ACTION`（`id -> fn`）、`window.relTime`（**不是**本任务，见 Task 4）；`secShortcuts()` 改为从 `KEYMAP` 渲染

- [ ] **Step 1: 写失败的测试（替掉现有那条）**

把 `tests/test_static_contract.py:375-385` 的 `test_rail_toggle_is_reachable_and_documented` 整体换成：

```python
def test_keybindings_come_from_one_table_and_are_all_documented():
    """参考实现把键位当"唯一事实来源"（shortcutCommands.ts:57）。
    我们以前是绑定一处、说明一处，靠正则比对 —— 表化之后两边同源，
    这条测试改查三件真的会出事的事：全局条目没处理函数、处理函数没人绑、
    以及品牌位不再是可聚焦的开关。"""
    brand = re.search(r"<(button|a) class=\"sb-brand\"[^>]*>", INDEX_HTML)
    assert brand, "找不到品牌元素"
    assert brand.group(1) == "button", "品牌位用 <a> 没 href，键盘 Tab 到不了"
    assert 'onclick="sbToggle()"' in brand.group(0), "品牌位不再是侧栏开关"

    rows = re.findall(r"\{id:'([A-Za-z]+)', chord:'([^']+)', key:'([^']*)', mod:'([^']*)', scope:'(\w)'", APP_JS)
    assert rows, "KEYMAP 表不见了或字段顺序变了"
    ids = [r[0] for r in rows]
    assert len(ids) == len(set(ids)), "键位表里有重复 id"
    chords = {r[1] for r in rows}
    assert len(chords) == len(rows), "两条键位撞在同一个和弦上"

    body = APP_JS.split('const KEY_ACTION = {')[1].split('\n};')[0]
    glob = [r[0] for r in rows if r[4] == 'g']
    assert set(glob) == {'newTask', 'search', 'toggleSb', 'settings', 'switchTheme', 'close'}
    for i in glob:
        if i == 'close':
            continue                      # close 走 Escape 专用分支（多层浮层要逐个关，不是一句 ACTION）
        assert re.search(r"\b" + i + r"\s*:", body), f"{i} 声明成全局键位却没有处理函数"
    assert "KEYMAP.find(" in APP_JS, "keydown 还在写死的 if 链里，没走表"
    assert "if(k==='k')" not in APP_JS and "if(k==='n')" not in APP_JS, "残留写死的 Ctrl 分支"

    # 表就是文档源：设置页不能再自己抄一份字面量
    assert "KEYMAP.filter" in APP_JS or "KEYMAP.map" in APP_JS, "键位说明页没从表里渲染"


def test_the_reference_chord_map_is_preserved():
    """逐条对着参考实现的表核一遍（shortcutCommands.ts:63-83）。
    键位这种东西改一次就固化了，不写死断言下次会被人顺手改回去。"""
    want = {'newTask': 'Ctrl N', 'search': 'Ctrl K', 'toggleSb': 'Ctrl B',
            'settings': 'Ctrl ,', 'switchTheme': 'Ctrl Shift L', 'close': 'Esc'}
    rows = {i: c for (i, c, _k, _m) in
            re.findall(r"\{id:'([A-Za-z]+)', chord:'([^']+)', key:'([^']*)', mod:'([^']*)'", APP_JS)}
    assert want.items() <= rows.items(), f"和参考实现对不上了：{ {k: (rows.get(k), v) for k, v in want.items() if rows.get(k) != v} }"


def test_every_keybind_id_has_both_i18n_strings():
    """表里的每个 id 都要有 sc.<id> 和 sc.<id>D 两份文案（中英各一），
    否则设置页那栏会印出 key 本身 —— t() 是 || 取字典。"""
    ids = re.findall(r"\{id:'([A-Za-z]+)', chord:'[^']+'", APP_JS)
    for i in ids:
        for suffix in ('', 'D'):
            k = f"'sc.{i}{suffix}'"
            assert UI_JS.count(k) == 2, f"{k} 应该中英各一份，实际 {UI_JS.count(k)} 份"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `PYTHONUTF8=1 "<python>" -m pytest tests/test_static_contract.py -q -k "keybind or chord or reference_chord"`
Expected: 三条全 FAIL（`KEYMAP` 还不存在）

- [ ] **Step 3: 写表 + 改分发**

`static/app.js`，把 :1936-1970 整段替换：

```js
/* ---------------- 全局快捷键 ----------------
   一张表当唯一事实来源：设置页的「键位」说明和这里的分发读同一份数据，
   所以不存在"说明里写了没绑 / 绑了没写说明"。参考实现同思路
   （ZCode packages/shared/src/shortcutCommands.ts:57-100）。
   scope: g = 全局；s = 只在设置页生效（由设置页自己消费）；i = 输入框内（Enter 族）。
   浏览器形态下 Ctrl+N / Ctrl+K 会被 Chrome/Edge 抢走（新窗口、地址栏），preventDefault
   拦不住 —— 所以不要求 Shift 的条目两种按法都认（Ctrl+Shift+N 那条是留给浏览器的）。 */
const isTyping = (el) => !!el && (el.tagName==='INPUT' || el.tagName==='TEXTAREA' || el.isContentEditable);

const KEYMAP = [
  {id:'newTask',     chord:'Ctrl N',       key:'n',      mod:'ctrl',       scope:'g'},
  {id:'search',      chord:'Ctrl K',       key:'k',      mod:'ctrl',       scope:'g'},
  {id:'toggleSb',    chord:'Ctrl B',       key:'b',      mod:'ctrl',       scope:'g'},
  {id:'settings',    chord:'Ctrl ,',       key:',',      mod:'ctrl',       scope:'g'},
  {id:'switchTheme', chord:'Ctrl Shift L', key:'l',      mod:'ctrl+shift', scope:'g'},
  {id:'close',       chord:'Esc',          key:'escape', mod:'',           scope:'g'},
  {id:'searchSettings', chord:'/',         key:'/',      mod:'',           scope:'s'},
  {id:'send',        chord:'Enter',        key:'enter',  mod:'',           scope:'i'},
];

function keyMatches(r, e){
  const ctrl = !!(e.ctrlKey || e.metaKey);
  if(r.mod.includes('ctrl') !== ctrl) return false;
  if(r.mod.includes('shift') && !e.shiftKey) return false;  // 不要求 Shift 的两可，见上面注释
  if(!r.mod.includes('ctrl') && e.altKey) return false;
  return r.key === (e.key||'').toLowerCase();
}

const KEY_ACTION = {
  newTask:    () => window.taskModal(),
  search:     () => window.sbSearch(),
  toggleSb:   () => window.sbToggle(),
  settings:   () => nav.go('settings'),
  switchTheme: async () => {
    const next = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
    await window.setAppearance({theme: next});
    toast(t('sc.themeNow.'+next));
  },
};

document.addEventListener('keydown', (e)=>{
  if(e.repeat) return;   // 长按会一路连发，每次都打一次 setAppearance POST
  const hit = KEYMAP.find(r => r.scope==='g' && keyMatches(r, e));
  if(hit && hit.id !== 'close'){ e.preventDefault(); KEY_ACTION[hit.id](); return; }
  if(e.key==='Escape'){
    /* 从最上层往下逐个关：ff-menu 压在别的浮层之上，不先关就会一路 Esc 把底下的弹窗也带走。 */
    const fm = document.getElementById('ffMenu');
    if(fm && !fm.hidden){ e.preventDefault(); ffClose(); return; }
    const fd = document.getElementById('sbFind');
    if(fd && !fd.hidden){ e.preventDefault(); fd.hidden = true; return; }
    const pop = document.getElementById('sbPop');
    if(pop && !pop.hidden){ e.preventDefault(); closeFootMenu(); return; }
    const m = document.querySelector('.modal.open');
    if(m){ const x = m.querySelector('.modal-x'); if(x){ e.preventDefault(); x.click(); } return; }
    const a = document.getElementById('app');
    if(a && a.dataset.shell==='settings'){ e.preventDefault(); window.setExit(); }
  }
});
```

`secShortcuts()`（:927-957）的 `rows` 改成从表里出：

```js
function secShortcuts(){
  /* 键位说明不再手抄一份：表里有什么，这里就有什么（见 KEYMAP）。
     作用域是真实差异不是装饰 —— g 全局、s 只在设置页、i 只在输入框里。 */
  const rows = KEYMAP.map(r =>
    [r.chord, t('sc.'+r.id), t('sc.'+r.id+'D'), r.scope, 'shortcut '+r.id]
  ).map(([k,tt,d,sc,x])=>`<div class="sc-tr" data-k="${kAttr(tt+' '+k+' '+x+' '+t('sc.scope.'+sc))}">
      <div class="sc-td"><span class="sc-name">${esc(tt)}</span>
        <span class="sc-desc">${esc(d)}</span></div>
      <div class="sc-td sc-td-k"><span class="st-keys">${k.split(' ').map(skey).join('')}</span></div>
      <div class="sc-td sc-td-s"><span class="sc-scope sc-scope-${sc}">${esc(t('sc.scope.'+sc))}</span></div>
    </div>`).join('');
```

（注意：`sc.scope.i` 现在会被 `send` 这条用到，`Enter` 本来就是 `i`，不用新增档位。）

同任务里把侧栏那个已经说谎的标签改掉 —— `app.js:80`：

```js
        <span class="sb-kbd">Ctrl N</span>`;
```

- [ ] **Step 4: 补两份字典**

`static/ui.js` 中文块（:212-218）与英文块（:475-481），键名必须和 `KEYMAP` 的 `id` 逐字一致：

```js
    'sc.newTask': '新建任务', 'sc.newTaskD': '开一条新流程。用浏览器打开时 Ctrl+N 会被新窗口抢走，改用 Ctrl+Shift+N。',
    'sc.search': '搜索流程与运行', 'sc.searchD': '在侧栏里按名字找流程或运行；用浏览器打开时改用 Ctrl+Shift+K。',
    'sc.toggleSb': '折叠 / 展开侧边栏', 'sc.toggleSbD': '折叠态会记住，重启后还是那样；用浏览器打开时改用 Ctrl+Shift+B。',
    'sc.settings': '打开设置', 'sc.settingsD': '从任意页面跳到设置。',
    'sc.switchTheme': '切换明暗主题', 'sc.switchThemeD': '和设置里的「主题」是同一个开关，只是手快一点。',
    'sc.close': '关闭弹窗 / 退出设置', 'sc.closeD': '弹窗打开时优先关弹窗，一层一层来。',
    'sc.searchSettings': '聚焦设置搜索框', 'sc.searchSettingsD': '只在设置页生效。',
    'sc.send': '运行台发送修订', 'sc.sendD': 'Shift+Enter 换行。',
    'sc.themeNow.dark': '已切到深色', 'sc.themeNow.light': '已切到浅色',
```

英文对应（`sc.themeNow.*` 也要两份，`test_every_keybind_id_has_both_i18n_strings` 只查 `sc.<id>`/`sc.<id>D`，`sc.themeNow.*` 由既有的"字典一一对应 + 不能有没人用的 key"两条测试兜住）。

**键名要跟着表走，别留孤儿**：旧的 `'sc.search'/'sc.searchD'` 讲的是 `/`（聚焦设置搜索框），而表里 `sc.search` 现在是 `Ctrl+K` 那条 —— **保留这两个 key 但把文案换成"搜索流程与运行"，`/` 那条改名成 `sc.searchSettings`**。`sc.searchPh` 是键位页搜索框的 placeholder，仍在用，别动。
最后跑一次全量：既有的「字典一一对应 + 不能有没人用的 key」两条测试会当场抓住漏删或多删的 key（`t()` 是 `||` 取字典，多个 key 不会报错、只会安静地不出现）。

- [ ] **Step 5: 跑全量测试**

Run: `PYTHONUTF8=1 "<python>" -m pytest -q`
Expected: 全绿。若 `test_no_unused_i18n_key` 类断言报 `sc.search`，说明 Step 4 的删除没做干净。

- [ ] **Step 6: 真按一次键盘**

探针服务起来后，用 `chrome-devtools___press_key` 依次发 `Control+n` / `Control+k` / `Control+Shift+l`，每步断言状态：

```js
JSON.stringify({hash:location.hash, find:!document.getElementById('sbFind').hidden,
                theme:document.documentElement.dataset.theme})
```

Expected: 第一条让 `#tkBrief` 拿到焦点且在 `#/home`；第二条让 `#sbFind` 可见；第三条 `theme` 在 `dark`/`light` 之间翻一次。
再打开设置 → 键位分区，断言 8 行全在、`Ctrl N` 那行文案不是 key 本身。

- [ ] **Step 7: 升令牌 + 提交**

```bash
git add static/app.js static/ui.js tests/test_static_contract.py static/index.html
git commit -m "feat(keys): 键位收成一张 KEYMAP（照参考实现），新建任务挪到 Ctrl+N、Ctrl+K 给搜索、新增 Ctrl+Shift+L 切主题"
```

---

### Task 3: 侧栏导航行化（新建任务 / 搜索 进主导航，删掉重复入口）

现状：`.sb-top` 里有 `#sbSearchBtn` + `#sbActBtn` 两个图标钮，`.sb-scroll` 顶部另有一个通栏 `#sbNew`。参考实现的顶层顺序是 开关 → 导航 → 新建任务 → 更新胶囊（`DesktopTopOverlay.tsx:211-217`），且"新建任务/搜索"就是导航里的两行。我们这里是三个不同形状的入口管两件事。

改后：`#mainNav` 五行 —— 新建任务(`Ctrl N`) / 搜索(`Ctrl K`) / 工作流 / 技能库 / 运行记录；设置仍在左下角 `.sb-foot`，不动。删 `#sbNew`、`#sbSearchBtn`、`.sb-new` 规则。`#sbActBtn`（进程铃铛）保留：它是状态指示器不是入口。

**Files:**
- Modify: `static/index.html:33-51`（删两处、`#mainNav` 保留）
- Modify: `static/app.js:76-104`（`renderNav`）、`:180-245`（`renderSidebarLists` 里 `#sbActBtn` 之外不动）、`:275-285`（`sbSearch` 定位取 `#sbSearchBtn` 的 rect）
- Modify: `static/style.css:393-399`（`.sb-new` 整条删）、`:401`（`.sb-item`）、折叠轨道段 `@media (min-width:861px){...}`
- Test: `tests/test_static_contract.py` 的 `RAIL_HIDDEN`（:330-340）与侧栏结构相关断言（:272 附近 `assert "sbUpdate" in html`）

**Interfaces:**
- Consumes: `window.taskModal()`、`window.sbSearch()`（Task 2 已保证无参可调）、`t('nav.newTask')`、`t('sb.search')`、`ico('plus')`、`ico('search')`、`KEYMAP`（拿和弦字面量，别再手写 `Ctrl K`）
- Produces: `#mainNav` 里 `.sb-item` 五行；带 `id="sbSearchRow"` 的那一行是 `#sbFind` 浮层的定位锚

- [ ] **Step 1: 写失败的测试**

```python
def test_the_sidebar_has_one_row_per_entry_point():
    """一个功能只留一个入口。侧栏顶部两个图标钮 + 一个通栏「新建任务」是三个入口管两件事；
    参考实现把它们收进主导航（DesktopTopOverlay.tsx:211-217）。"""
    assert 'id="sbNew"' not in INDEX_HTML, "通栏新建任务按钮还在，和主导航第一行重复"
    assert 'id="sbSearchBtn"' not in INDEX_HTML, "搜索图标钮还在，和主导航第二行重复"
    assert '.sb-new{' not in CSS, ".sb-new 的规则该跟着 DOM 一起删掉"
    for key in ('nav.newTask', 'sb.search'):
        assert f"t('{key}')" in APP_JS, f"{key} 得出现在主导航某一行的文案里"
    assert 'id="sbSearchRow"' in APP_JS, "搜索行要有 id，#sbFind 浮层靠它定位"
    assert "getElementById('sbSearchBtn')" not in APP_JS, "浮层定位还指着已删掉的图标钮"
    # 导航行里的和弦来自 KEYMAP，不再手抄
    assert "chordOf('newTask')" in APP_JS and "chordOf('search')" in APP_JS, "kbd 标签没从键位表取"


def test_nav_rows_that_are_actions_are_buttons_and_routes_are_links():
    """折叠轨道里点得着不算完，Tab 到不了就是坏的：
    路由行用 <a href>，动作行用 <button>，两者都可聚焦；不许出现没 href 的 <a>。"""
    seg = APP_JS.split('const items = [')[1].split('];')[0]
    assert "act:'taskModal()'" in seg and "act:'sbSearch()'" in seg, "前两行要声明自己是动作"
    assert 'href="#/${n.id}"' in APP_JS, "路由行必须带真 href，否则 Tab 到不了"
    body = APP_JS.split('function renderNav(')[1].split('\n}\n')[0]
    assert "if(n.act)" in body, "动作行没按 act 分支渲染成 <button>"
    assert "</button>`" in body and "</a>`" in body, "两种行都得有收尾标签"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `PYTHONUTF8=1 "<python>" -m pytest tests/test_static_contract.py -q -k "entry_point or entrypoint or nav_rows"`
Expected: 两条 FAIL（`id="sbNew"` 还在 / 没有 `act:` 字段）

- [ ] **Step 3: 改骨架**

`static/index.html` 的 `.sb-top` / `.sb-scroll`：

```html
    <div class="sb-top">
      <button class="sb-brand" id="sbBrand" data-tip-any="1" data-tip=""
        aria-expanded="true" onclick="sbToggle()">
        <img class="sb-logo" src="/static/logo-sm.svg?v=XXXX" alt="">
        <span class="sb-name" id="brandName">织流</span>
      </button>
      <div class="sb-acts">
        <button class="ic-btn" id="sbActBtn" data-tip-any="1" onclick="sbActivity(event)"></button>
      </div>
    </div>
    <div class="sb-scroll">
      <nav class="sb-nav" id="mainNav"></nav>
      <div id="sbLists"></div>
    </div>
```

- [ ] **Step 4: 改 `renderNav`**

```js
const chordOf = (id) => (KEYMAP.find(r=>r.id===id) || {}).chord || '';

function renderNav(active){
  /* 五行：两行动作（新建任务 / 搜索）+ 三条路由 + 设置走左下角。
     路由行必须是带 href 的 <a>，动作行必须是 <button> —— 没 href 的 <a> 拿不到键盘焦点。
     aria-label 是因为折叠轨道会把 <span> 整个 display:none 掉，折上就没了可访问名。 */
  const items = [
    {id:'newTask',   icon:'plus',   label:t('nav.newTask'),  chord:chordOf('newTask'), act:'taskModal()'},
    {id:'search',    icon:'search', label:t('sb.search'),    chord:chordOf('search'),  act:'sbSearch()', row:'sbSearchRow'},
    {id:'pipelines', icon:'flow',   label:t('nav.workflows')},
    {id:'skills',    icon:'skill',  label:t('nav.skills')},
    {id:'runs',      icon:'runs',   label:t('nav.runs')},
  ];
  const html = items.map(n=>{
    const inner = `${ico(n.icon)}<span>${esc(n.label)}</span>`
      + (n.chord ? `<span class="sb-kbd">${esc(n.chord)}</span>` : '');
    const tip = `data-tip-any="1" data-tip="${esc(n.label)}" aria-label="${esc(n.label)}"`;
    if(n.act) return `<button class="sb-item" type="button" ${tip}
        ${n.row?`id="${n.row}"`:''} onclick="${n.act}()">${inner}</button>`;
    return `<a class="sb-item ${n.id===active?'active':''}" href="#/${n.id}" data-v="${n.id}" ${tip}
      ${n.id===active?'aria-current="page"':''}>${inner}</a>`;
  }).join('');
  const box = $('#mainNav');
  if(box && box.dataset.sig !== html){ box.innerHTML = html; box.dataset.sig = html; }
  paintBrand();
  /* 换语言时这两处的文案没人刷：它们不在 renderNav 的重绘链上，只在启动 / 轮询里写 */
  paintFootMe(); paintUpdate();
}
```

`sbSearch` 的定位（:275-285）：

```js
  const src = document.getElementById('sbSearchRow') || document.querySelector('.sb-nav');
  const r = src.getBoundingClientRect();
```

- [ ] **Step 5: 清 CSS 与轨道清单**

- 删 `static/style.css:393-399` 的 `.sb-new` 整段（含 `.sb-new:hover` / `.sb-new .ic` 等派生规则）。
- `.sb-kbd` 原来只在 `#sbNew` 里出现，确认 `.sb-item .sb-kbd{margin-left:auto}` 这条选择器仍然命中（现在它是 `.sb-item` 的孙子）；原来若有 `.sb-new .sb-kbd` 这种前缀，改成 `.sb-item .sb-kbd`。
- `tests/test_static_contract.py:330-340` 的 `RAIL_HIDDEN`：删掉 `".sb-new span": "新建任务"`。**不要**加 `.sb-kbd` —— 轨道里它已被 `.sb-item span` 同级的 `display:none` 覆盖不到（kbd 不是 `span` 的直接子代而是自身是 span），所以要在折叠段里显式写一条 `html[data-sidebar="collapsed"] .sb-kbd{display:none}`，并把 `".sb-kbd": "键位提示（56px 轨道里放不下两个字）"` 加进 `RAIL_HIDDEN`。**两边一起改，`test_rail_hides_every_text_label` 的双向锁会当场抓住只改一头的。**

- [ ] **Step 6: 跑全量测试**

Run: `PYTHONUTF8=1 "<python>" -m pytest -q`
Expected: 全绿（`test_rail_hides_every_text_label` 若报"藏多了"，说明 `.sb-new span` 那条规则还在 CSS 里）

- [ ] **Step 7: 实测两种宽度**

探针服务起来后：

```js
JSON.stringify({rail: document.querySelector('.sidebar').getBoundingClientRect().width,
  rows: document.querySelectorAll('#mainNav .sb-item').length,
  focusable: [...document.querySelectorAll('#mainNav .sb-item')].every(el=>el.tagName==='A'?!!el.href:true)})
```

Expected: 展开时 `rows === 5`、`focusable === true`；按 `Ctrl+B` 折叠后 `rail === 56`（轨道宽度以 CSS 现值为准，改之前先读一次真值再断言，别写记忆里的数）。

- [ ] **Step 8: 升令牌 + 提交**

```bash
git add static/index.html static/app.js static/style.css tests/test_static_contract.py static/index.html
git commit -m "feat(sidebar): 新建任务/搜索收进主导航，删掉两个重复入口（一个功能只留一个入口）"
```

---

### Task 4: 项目行嵌套"最近运行"+ 相对时间

现状：侧栏分两组 —— 「项目」（跑过的流程）和「最近运行」（runs 平铺），同一个 run 在两处都有脸。参考实现是按工作空间分组、run 嵌在项目下面，用**一条左边框轨道**缩进（`workspace-grouped-tasks/types.ts`），次行右槽是 `状态点 + 相对时间`，相对时间只有四档紧凑写法（`taskListItemPresentation.ts:33-53`），**没有月/年档**。

数据不用新接口：`/api/pipelines` 每条已经带 `last_run: {id, created_at}`（`app/main.py:93`，来自 `db.last_runs()`），`/api/runs?limit=8` 每条带 `pipeline / label / status / created_at / updated_at`（`_run_row` 返回整行）。**所以嵌套在前端分组就够，不新增端点。**

**Files:**
- Modify: `static/app.js:182-245`（`renderSidebarLists`）
- Modify: `static/style.css:415-447`（`.sb-group` / `.sb-run` / `.sb-rtag` 附近，新增 `.sb-runlist` / `.sb-sub`）
- Modify: `static/ui.js`（`sb.*` 两份字典：删 `sb.recent` 的用法、加 `time.*` 四条）
- Test: `tests/test_static_contract.py`

**Interfaces:**
- Consumes: `ST.sbRuns`（现有）、`RUN_ICON` / `RUN_ST()`（现有）
- Produces: `window.relTime(iso, now)` → `{s: 数字, u: 'now'|'m'|'h'|'d'}`；渲染时再 `t('time.'+u,{n:s})`。**拆成"算"和"说"两步是为了能被 node 真跑一遍**（和 `pyInit` 同一套验证思路）。

- [ ] **Step 1: 写失败的测试**

```python
def test_relative_time_uses_the_reference_four_tiers():
    """参考实现：刚刚 / {n}分 / {n}小时 / {n}天，没有月年档
    （taskListItemPresentation.ts:33-53）。阈值差一档，侧栏上就是"7 天前"和"0 天前"的区别。
    纯字符串断言骗不了自己，所以让 node 真把函数跑一遍。"""
    import subprocess
    js = ("const s=require('fs').readFileSync(process.argv[1],'utf8');"
          "const grab=(n)=>s.match(new RegExp('function '+n+'\\\\([\\\\s\\\\S]*?\\\\n\\\\}'))[0];"
          "eval(grab('parseLdb')); eval(grab('relUnit'));"     # relUnit 调 parseLdb，两个都要取出来
          "const q=JSON.parse(process.argv[2]);"
          "console.log(JSON.stringify(q.map(([a,b])=>relUnit(a,b))));")
    # 库里的时间串是**本地**时间（db._now 用 time.strftime），parseLdb 也按本地解释，
    # 所以两个端点都用 localtime 格式化才不会因机器时区而漂；别写成 gmtime±8。
    fmt = lambda ms: time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ms/1000))
    NOW = 1777000000000                        # 定死一个"现在"，别用 Date.now
    cases = [((NOW - 30_000),   {'s':0,'u':'now'}),
             ((NOW - 59_000),   {'s':0,'u':'now'}),
             ((NOW - 60_000),   {'s':1,'u':'m'}),
             ((NOW - 59*60e3),  {'s':59,'u':'m'}),
             ((NOW - 60*60e3),  {'s':1,'u':'h'}),
             ((NOW - 23.9*3600e3), {'s':23,'u':'h'}),
             ((NOW - 24*3600e3),{'s':1,'u':'d'}),
             ((NOW - 40*86400e3), {'s':40,'u':'d'})]   # 40 天仍然是「天」，不给月档
    payload = json.dumps([[fmt(ms), fmt(NOW)] for ms, _ in cases])
    r = subprocess.run(["node", "-e", js, str(STATIC_DIR / "app.js"), payload],
                       capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, r.stderr[:400]
    assert json.loads(r.stdout) == [w for _, w in cases], r.stdout[:300]


def test_recent_runs_are_nested_under_their_project_not_listed_twice():
    """同一个 run 在侧栏出现两次 = 两个入口管一件事。
    参考实现是嵌在项目行下面，用一条左边框轨道缩进。"""
    seg = APP_JS.split('async function renderSidebarLists(')[1].split('\n}\n')[0]
    assert 'class="sb-run sb-sub"' in seg, "run 没嵌进项目行"
    assert ".sb-runlist" in CSS and "border-left" in CSS.split(".sb-runlist")[1][:200], \
        "缩进要用左边框轨道，不是加 padding（参考实现同）"
    assert "t('sb.recent')" not in seg, "「最近运行」那一组还在 —— 现在它是重复入口"
    assert "relTime(" in seg, "次行没打相对时间"
    assert "sb-gcount" in seg and "live" in seg, "在跑计数要挂在分组标题上，别挂每行"
```

（`tests/test_static_contract.py` 顶部现在只 import 了 `json / re / pathlib / pytest / conftest.STATIC_DIR`，这条测试要用 `time` —— 在 `import re` 旁边补一行 `import time`。）

- [ ] **Step 2: 跑测试确认失败**

Run: `PYTHONUTF8=1 "<python>" -m pytest tests/test_static_contract.py -q -k "relative_time or nested"`
Expected: 两条 FAIL（`relUnit` 不存在 / `sb.recent` 还在）

- [ ] **Step 3: 写"算"与"说"**

`static/app.js`（放在 `RUN_ICON` 上面，`renderSidebarLists` 之前）：

```js
/* 数据库存的是 "%Y-%m-%d %H:%M:%S" 本地时间（app/db.py:23），没有时区，
   所以 new Date("2026-09-22 11:04:03") 这种写法不能依赖 —— 手工拆字段。
   四档阈值抄参考实现（taskListItemPresentation.ts:33-53）：不给月/年档。 */
function parseLdb(iso){
  const m = /^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2}):(\d{2})/.exec(iso||'');
  return m ? new Date(+m[1], +m[2]-1, +m[3], +m[4], +m[5], +m[6]).getTime() : NaN;
}
function relUnit(iso, now){
  const mins = Math.floor(((now==null ? Date.now() : now) - parseLdb(iso)) / 60000);
  if(!(mins >= 0)) return {s:0, u:'now'};          // 时间戳在未来（时钟没同步）也当"刚刚"，别印 -3 分
  if(mins < 1)  return {s:0,  u:'now'};
  if(mins < 60) return {s:mins, u:'m'};
  const hrs = Math.floor(mins/60);
  if(hrs < 24)  return {s:hrs, u:'h'};
  return {s:Math.floor(hrs/24), u:'d'};
}
window.relTime = (iso, now) => {
  const r = relUnit(iso, now);
  return r.u === 'now' ? t('time.now') : t('time.'+r.u, {n:r.s});
};
```

- [ ] **Step 4: 改渲染**

`renderSidebarLists` 里，把两组结构换成一组 + 嵌套：

```js
  const proj = flows.filter(p=>!p.archived);
  const byFlow = {};
  runs.forEach(u => { (byFlow[u.pipeline] = byFlow[u.pipeline] || []).push(u); });
  const row = (p) => {
    const kids = (byFlow[p.name] || []).slice(0, 2);   // 两条封顶：侧栏是入口不是清单
    return `<div class="sb-row">
      <a class="sb-run ${('pipeline-edit/'+p.name)===cur?'active':''}"
        href="#/pipeline-edit/${esc(p.name)}" data-tip="${esc(p.label||p.name)}"
        aria-label="${esc(p.label||p.name)}"
        ${('pipeline-edit/'+p.name)===cur?'aria-current="page"':''}>
        <span class="sb-rico">${ico('flow')}</span>
        <span class="sb-rname">${esc(p.label||p.name)}</span></a>
      <button class="sb-more" data-tip-any="1" data-tip="${esc(t('sb.rowMore'))}"
          aria-label="${esc(t('sb.rowMore'))}"
          onclick="sbRowMore(event,'${jsq(p.name)}')">${ico('more')}</button>
    </div>` + (kids.length ? `<div class="sb-runlist">` + kids.map(u=>{
        const m = RUN_ICON[u.status] || RUN_ICON.pending;
        return `<a class="sb-run sb-sub ${u.id===cur?'active':''}" href="#/run/${esc(u.id)}"
          data-tip="${esc(u.label||u.pipeline)}" aria-label="${esc(u.label||u.pipeline)}"
          ${u.id===cur?'aria-current="page"':''}>
          <span class="sb-rico ${m.cls}">${m.ic?(m.sp?ico(m.ic,'sp'):ico(m.ic)):'&nbsp;'}</span>
          <span class="sb-rname">${esc(u.label||u.pipeline)}</span>
          <span class="sb-rtag">${esc(relTime(u.created_at))}</span></a>`;
      }).join('') + `</div>` : '');
  };
```

分组标题那行改成带在跑计数、并**删掉整段「最近运行」组**（:227-238）：

```js
  let html = `<div class="sb-group"><span>${esc(SB_ARCH ? t('sb.archived') : t('sb.flows'))}</span>
      ${live?`<span class="sb-gcount">${live}</span>`:''}
      ${garch}
      <button class="sb-gadd" ... >${ico('plus')}</button></div>`
    + (SB_ARCH ? (...) : (...));
  if(box.dataset.sig !== html){ box.innerHTML = html; box.dataset.sig = html; }
```

`home.recentEmpty` 这个 key 若因此不再被引用，必须删（i18n"不能有没人用的 key"那条测试会抓）。

- [ ] **Step 5: CSS**

```css
/* 参考实现的嵌套轨道：一条左边框 + 8px 左内缩，不是再加一层 padding
   （workspace-grouped-tasks/types.ts:35-47 的 ml-4 border-l pl-2） */
.sb-runlist{margin-left:12px;padding-left:8px;border-left:1px solid var(--line);}
.sb-sub{padding:4px 8px;font-size:var(--fs-sub)}
```

`.sb-rtag` 现在装的是状态词，改装相对时间；字号档若需要更弱就用现成的 `--fs-micro`，**不要新增刻度档**。
状态词从行里消失是有意的：参考实现的次行是"状态点 + 时间"，状态由 `.sb-rico` 的类（`sb-live` / `sb-wait` / `sb-bad`）承载。**改完必须确认那三个类在 `.sb-sub` 上仍然生效**（Step 7 里连 icon 的 computed color 一起读回来）。
一个真实的取舍：嵌进项目行之后，**已归档流程的 run 在默认视图里就不出现了**（归档组本身被 `SB_ARCH` 挡着）。运行记录页仍然列全部，所以信息没丢 —— 收尾汇报时要把这句原样说给用户听，别让它变成"我没注意到的回归"。

- [ ] **Step 6: 跑全量测试**

Run: `PYTHONUTF8=1 "<python>" -m pytest -q`
Expected: 全绿

- [ ] **Step 7: 用造出来的数据实测**

临时库里造 3 条流程 × 若干 run，把 `created_at` 分别改成 30 秒前 / 5 分前 / 30 分前 / 5 小时前 / 3 天前（`UPDATE runs SET created_at=...`，只改临时库），起探针服务后读回：

```js
[...document.querySelectorAll('.sb-sub .sb-rtag')].map(e=>e.textContent)
```

Expected: 形如 `刚刚 / 5 分 / 30 分 / 5 小时 / 3 天`（具体字面看 `time.*` 文案）。
**做完确认那句还在**：`SELECT archived FROM pipelines` 与真库无关 —— 探针用的是临时库；收尾时打印一次真库文件 mtime，证明没碰过。

- [ ] **Step 8: 升令牌 + 提交**

```bash
git add static/app.js static/style.css static/ui.js tests/test_static_contract.py static/index.html
git commit -m "feat(sidebar): 最近运行嵌进项目行 + 相对时间四档（照参考实现），删掉重复的那一组"
```

---

### Task 5: 输入台改成三段式，右下工具条加**引擎**选择器

现状 `tkStageHtml`（`static/app.js:532-560`）只有两段：上=流程选择器+检查点提示，下=任务名+发送。参考实现是三段，且**发送在右下角工具条里**、是 `rounded-lg bg-brand text-foreground-inverse` 的方正图标按钮配 `ArrowUpIcon`（`ConversationComposer.tsx:2038-2099`）。

**只加引擎，不加模型。** `start_run(pipeline_name, label, brief, engine)` 没有 model 参数（`app/runner.py:841`），加了就是放假控件。引擎这一层是真空缺：设置里的引擎是**全局默认**（`/api/settings/bulk` 只管 `ui_` 前缀），运行台只显示 `engine_used` 不给切（`static/run.js:234`），所以下任务时选一次是这条链上唯一的入口。选择器首项是「跟随默认」，对应 `engine=""` 沿用步骤/全局默认。

**Files:**
- Modify: `static/app.js:532-560`（`tkStageHtml`）、`:607-619`（`tkHint`）、`taskStart`（同文件）、`:620-622`（加 `let TK_ENG=''`）
- Modify: `static/style.css:183-213`（`.tk-*`）
- Modify: `static/ui.js`（`tk.*` 两份字典加引擎相关键）
- Test: `tests/test_static_contract.py`

**Interfaces:**
- Consumes: `ffSelect(opts, cur, cfg)`（`app.js:1832`）、`window.ENGINE_LABEL`（`app.js:71`）、`t('eng.claude')` / `t('eng.codex')`（已存在）、`ico('arrowUp')`（已存在，`ui.js:566`）、`post('/api/pipelines/<name>/run', {brief,label,engine})`（后端 `RunStartIn.engine` 已支持）
- Produces: `#tkEngine`（隐藏 input 的值为 `''|'claude'|'codex'`）、`window.tkEngineSet(v)`、`.tk-bar` 类
- 已核实（不用再去猜）：`ffSelect` 的 `onChange` 在**写完隐藏 input、刷完按钮文字、关掉菜单之后**才被调，并且会把选中值当第一个实参传进来（`app.js:1890-1901`），所以 `tkEngineSet(v)` 可以直接收值；图标表里没有 `cpu`，引擎已有的图标是 `agent`（`app.js:328` 在用）；「不指定引擎」这个语义已有现成文案 `ed.engineDefault`（`ui.js:108` = "默认"、`:372` = "Default"，`ENGINE_LABEL` 空值时就显示它），**复用，不新增 key**。

- [ ] **Step 1: 写失败的测试**

```python
def test_composer_is_the_three_band_reference_shape_with_an_engine_picker():
    """三段：上=流程（上下文）、中=textarea、下=工具条（左动作、右提交）。
    引擎选择器是真的后端能力（start_run 的 engine 形参 + RunStartIn.engine），
    所以这里可以放；**模型**没有对应参数，放了就是假控件。"""
    seg = APP_JS.split('function tkStageHtml(')[1].split('\n}\n')[0]
    assert seg.count('class="tk-') >= 3, "输入台不是三段"
    assert "id:'tkEngine'" in seg, "工具条里没有引擎选择器"
    assert "class=\"tk-bar\"" in seg and "tk-bar" in CSS, "下段要有自己的规则"
    assert "taskStart()" in seg and "${ico('arrowUp')}" in seg, "发送仍指着已存在的图标"
    assert "model" not in seg.lower().replace("models", ""), \
        "输入台里出现了 model —— 后端没有这个参数，这是假控件"


def test_start_run_actually_sends_the_engine_it_picked():
    """选择器写了却不发出去，就是个装饰。"""
    seg = APP_JS.split('window.taskStart = async function()')[1].split('\n};')[0]
    assert "TK_ENG" in seg, "taskStart 没读引擎选择器"
    assert "engine:" in seg, "请求体里没有 engine 字段"


def test_engine_picker_defaults_to_the_inherited_choice():
    """空串 = 沿用步骤/全局默认（app/runner.py:846 的注释），
    所以首项必须是"默认"，且 TK_ENG 初值是 ''。
    「不指定引擎」的文案早就有了（ENGINE_LABEL 空值时用它），别再造一份近似 key。"""
    assert "let TK_ENG = ''" in APP_JS, "初值不是空串，会覆盖掉步骤自带的引擎"
    assert "t('ed.engineDefault')" in APP_JS, "首项要复用现成的『默认』文案"
    assert "tk.engineDefault" not in APP_JS and "tk.engineDefault" not in UI_JS, \
        "新造了近似 key —— ed.engineDefault 就是这条语义，多一份就会漂"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `PYTHONUTF8=1 "<python>" -m pytest tests/test_static_contract.py -q -k "composer or engine_picker"`
Expected: 三条 FAIL

- [ ] **Step 3: 改 markup**

```js
function tkStageHtml(tpls, flow){
  const cps = TK_CPS[flow] || 0;
  const ENGS = [{v:'', label:t('ed.engineDefault')},
                {v:'claude', label:t('eng.claude')}, {v:'codex', label:t('eng.codex')}];
  return `<div class="home-stage">
    <h1 class="tk-greet">${esc(t('tk.greet'))}</h1>
    <div class="tk-card">
      <div class="tk-top">
        ${ffSelect(tpls.map(p=>({v:p.name, label:(p.label||p.name),
                                 note:p.steps.length+' '+t('c.steps')})),
                   flow, {id:'tkFlow', icon:'flow', onChange:'tkHint'})}
        <span class="tk-meta" id="tkMeta">${cps ? esc(t('tk.cps',{n:cps})) : esc(t('tk.noCp'))}</span>
      </div>
      <div class="tk-field">
        <textarea class="tk-input" id="tkBrief" rows="4" placeholder="${esc(t('task.briefPh'))}"
          oninput="tkHint()"></textarea>
      </div>
      <div class="tk-bar">
        ${ffSelect(ENGS, TK_ENG, {id:'tkEngine', icon:'agent', onChange:'tkEngineSet'})}
        <input class="tk-name" id="tkLabel" placeholder="${esc(t('task.labelPh'))}">
        <button class="cp-send" onclick="taskStart()" aria-label="${esc(t('task.start'))}"
          title="${esc(t('task.start'))}">${ico('arrowUp')}</button>
      </div>
    </div>
    <div class="tk-hint" id="tkHintBox">${esc(t('task.briefHint'))}</div>
    <div class="tk-sugs" id="tkSugs">
      <div class="tk-sug-head"><span>${esc(t('tk.tryThese'))}</span><span class="spacer"></span>
        <button class="tk-op" onclick="tkShuffle()">${esc(t('tk.shuffle'))}</button></div>
      <div id="tkSugList"></div>
    </div>
  </div>`;
}
window.tkEngineSet = function(v){ TK_ENG = v || ''; };
```

`onChange` 由 `ffOpen` 在写完隐藏 input、刷完按钮文字、`ffClose()` 之后调用，并把选中值当第一个实参传进来（`app.js:1890-1901`）—— 所以 `tkEngineSet(v)` 直接收值，不必回读 DOM。图标用 `agent`（图标表里没有 `cpu`，`agent` 是侧栏引擎那一行已经在用的图标）。

`taskStart`：

```js
  const r = await post('/api/pipelines/'+encodeURIComponent(flow)+'/run',
                       {brief, label, engine: TK_ENG})
    .catch(e=>({detail:String(e)}));
```

起跑后清草稿时把 `TK_ENG` 留着（人往往连着下几条同引擎的任务），**不清**。

- [ ] **Step 4: CSS**

```css
.tk-top > .ff-selw{flex:0 1 auto;min-width:0}
.tk-bar{display:flex;align-items:center;gap:8px;padding:8px 12px 12px}
.tk-bar .ff-selw{flex:none}
.tk-bar .tk-name{flex:1}
.tk-bar .cp-send{margin-left:auto;flex:none}
```

`.tk-foot` 整条规则删掉（`test_no_unused_css` 类断言若有会抓；没有就靠 `grep -c '\.tk-foot' static/style.css` 自己确认归零）。

- [ ] **Step 5: i18n（这一步不该有新 key）**

首项文案复用现成的 `ed.engineDefault`（"默认" / "Default"，`ui.js:108` 与 `:372`），引擎名复用 `eng.claude` / `eng.codex`。**如果你发现自己在往 `ui.js` 里加 `tk.engine*`，说明第一步的断言在拦你这件事 —— 停下来改用现成 key。**

- [ ] **Step 6: 跑全量测试**

Run: `PYTHONUTF8=1 "<python>" -m pytest -q`
Expected: 全绿

- [ ] **Step 7: 实测（不真跑 CLI）**

探针服务里：选「跟随默认」发一条、选 `codex` 发一条，然后**只查库不发引擎线程** —— 直接读 `runs.steps` 快照里每步的 `engine` 字段：
- `engine:''` 时 → 每步保留模板自带值；
- `engine:'codex'` 时 → 每步变成 `codex`（对应 `app/runner.py:846-849`）。
读回 `JSON.stringify(steps.map(s=>s.engine))` 两边对比。
**任务一起来就会真调 CLI**，所以这一步用"建 run 但不启动"的等价路径：直接 POST 后**立刻** `DELETE`/`cancel`，或者更好的做法是绕过 HTTP、在 Python REPL 里调 `runner.start_run` 的校验分支（把 `_run_thread` 打桩）。做不到不打桩的验证，就在汇报里写明"这一条没实测"。

- [ ] **Step 8: 升令牌 + 提交**

```bash
git add static/app.js static/style.css static/ui.js tests/test_static_contract.py static/index.html
git commit -m "feat(composer): 输入台改三段，右下工具条加引擎选择器（后端有 engine 参数才放这个控件）"
```

---

### Task 6: 更新胶囊点开改成居中三态浮层

现状：更新全程挤在左下角 `.sb-update` 胶囊里（`app.js:392-405`），下载中靠一条 `--p` 进度；点一下 `sbUpdateClick`（:418-）直接开始下载，装的时候 `confirm()`。参考实现是**胶囊 + 居中对话框**两件套：三态标题（`New version v{v}` / `Downloading v{v}` / `v{v} is ready`）、`h-2` 进度条、下方 `已传 X / 共 Y`、按钮「下载更新 / 稍后」→「重启以更新」，且**重启不做二次确认**（`UpdateStatusDialog.tsx:91-231`）。

**能放的按钮以现有端点为限**：`GET /api/update`、`POST /api/update/check|download|apply|url`（`app/main.py:843-881`）。**参考实现里的「取消下载」「跳过此版本」「自动下载并安装」后端没有对应能力，一律不做。**

**这一步会第一次真正走打包态 `apply_update()`（[[loom-updater-status]]：至今没在真包里验过），所以执行前必须单独找人确认。**

**Files:**
- Modify: `static/app.js:392-440`（`paintUpdate` 保留胶囊，`sbUpdateClick` 改为开浮层）、`upView`（:373-390）、新增 `upDialog()`
- Modify: `static/style.css`（新增 `.up-card` 一族；`.sb-update` 不动）
- Modify: `static/ui.js`（`up.*` 两份字典）
- Test: `tests/test_static_contract.py`

**Interfaces:**
- Consumes: `UP`（`{configured, phase, local, latest, size, got, path, error, frozen, active_runs}`）、`api()`/`post()`、`t()`、`ico('x'/'download'/'checkCircle'/'warn')`、`z-index: var(--z-modal)`（Task 已在的刻度）、`mb()`（字节格式化，`app.js` 里已有）
- Produces: `#upCard`（`hidden` 控制）、`window.upOpen()` / `window.upClose()` / `window.upDownload()` / `window.upApply()`；`--z-modal` 之下的遮罩 `.up-mask`

- [ ] **Step 1: 写失败的测试**

```python
def test_update_offers_a_centered_dialog_not_just_a_capsule():
    """胶囊留着当状态；三态标题 / 进度条 / MB 读数 / 重启按钮在居中浮层里。"""
    for k in ('upOpen', 'upClose', 'upDownload', 'upApply'):
        assert f"window.{k}" in APP_JS, f"缺 {k}"
    assert 'id="upCard"' in APP_JS and 'class="up-mask"' in APP_JS
    assert "z-index:var(--z-modal)" in CSS.split(".up-mask")[1][:200], "遮罩要走刻度"
    for key in ("up.tAvailable", "up.tDownloading", "up.tReady"):
        assert APP_JS.count(f"t('{key}'") >= 1, f"三态标题缺 {key}"


def test_update_dialog_shows_a_real_progress_bar_and_no_fake_buttons():
    """进度条刻度来自 got/size，不是装饰；后端没有取消/跳过端点，所以按钮只有四条。"""
    seg = APP_JS.split('function upCardHtml(')[1].split('\n}\n')[0]
    assert "up-fill" in seg and "--p" in seg, "进度条没接 got/size"
    assert "mb(UP.got" in seg and "mb(UP.size" in seg, "缺「已传 / 共」读数"
    for fake in ("取消下载", "跳过此版本", "skipVersion", "cancelDownload"):
        assert fake not in seg, f"{fake} 是假按钮：后端没有这个端点"
    assert "active_runs" in seg or "busyConfirm" in APP_JS, "重启前还得拦住正在跑的任务"


def test_update_dialog_is_closable_by_escape_and_backdrop():
    """居中浮层必须能被关掉。它压在最上面，所以 Escape 链里它要在 ff-menu 之前 ——
    顺序反了就会先关掉底下的菜单，浮层却还赖在屏上。"""
    seg = APP_JS.split("if(e.key==='Escape')")[1][:900]
    assert "upCard" in seg, "Escape 没关更新浮层"
    assert seg.index("upCard") < seg.index("ffMenu"), "关闭顺序倒了：先关浮层再关菜单"
    assert 'id="upMask" onclick="upClose()"' in INDEX_HTML, "点遮罩要能关"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `PYTHONUTF8=1 "<python>" -m pytest tests/test_static_contract.py -q -k "update_dialog or update_offers or progress_bar"`
Expected: 三条 FAIL

- [ ] **Step 3: 写浮层**

```js
function upTitle(u){
  if(u.phase === 'downloading') return t('up.tDownloading', {v:u.latest||''});
  if(u.phase === 'ready')       return t('up.tReady', {v:u.latest||''});
  if(u.phase === 'error')       return t('up.tFailed');
  return t('up.tAvailable', {v:u.latest||''});
}

function upCardHtml(){
  const u = UP || {};
  const pct = u.phase==='ready' ? 100
            : (u.size ? Math.min(99, Math.floor((u.got||0)*100/u.size)) : 0);
  const bar = (u.phase==='downloading' || u.phase==='ready')
    ? `<div class="up-bar"><i class="up-fill" style="width:${pct}%"></i></div>
       <div class="up-mb">${esc(mb(u.got||0))} / ${esc(mb(u.size||0))}</div>` : '';
  const err = u.phase==='error' ? `<div class="up-err">${esc(u.error||t('up.unknown'))}</div>` : '';
  let btns = '';
  if(u.phase === 'available')
    btns = `<button class="st-btn primary" onclick="upDownload()">${esc(t('up.downloadNow'))}</button>
            <button class="st-btn" onclick="upClose()">${esc(t('up.later'))}</button>`;
  else if(u.phase === 'downloading')
    btns = `<button class="st-btn" onclick="upClose()">${esc(t('up.later'))}</button>`;
  else if(u.phase === 'ready')
    btns = `<button class="st-btn primary" ${u.frozen?'':'disabled'}
              onclick="upApply()">${esc(t('up.apply'))}</button>
            <button class="st-btn" onclick="upClose()">${esc(t('up.later'))}</button>`;
  else
    btns = `<button class="st-btn primary" onclick="upCheckNow()">${esc(t('up.recheck'))}</button>
            <button class="st-btn" onclick="upClose()">${esc(t('up.later'))}</button>`;
  return `<div class="up-head"><b>${esc(upTitle(u))}</b>
      <button class="up-x ic-btn" onclick="upClose()" data-tip-any="1"
        data-tip="${esc(t('up.close'))}" aria-label="${esc(t('up.close'))}">${ico('close')}</button></div>
    <div class="up-ver">${esc(t('up.nowOn', {v:u.local||''}))}</div>
    ${bar}${err}
    <div class="up-btns">${btns}</div>`;
}

window.upOpen = function(){
  const c = document.getElementById('upCard'); if(!c) return;
  c.hidden = false; document.body.classList.add('up-on');
  c.innerHTML = upCardHtml();
  const b = c.querySelector('.up-x'); if(b) b.focus();
};
window.upClose = function(){
  const c = document.getElementById('upCard'); if(c) c.hidden = true;
  document.body.classList.remove('up-on');
};
window.upRepaintDialog = function(){
  const c = document.getElementById('upCard');
  if(c && !c.hidden) c.innerHTML = upCardHtml();
};
window.upDownload = async function(){
  UP = await post('/api/update/download').catch(()=>({phase:'error', error:t('up.reqFail')}));
  paintUpdate(); window.upRepaintDialog(); upPoll();
};
window.upApply = async function(){
  const n = (UP && UP.active_runs) || 0;
  if(n > 0 && !confirm(t('up.busyConfirm', {n}))) return;
  const r = await post('/api/update/apply').catch(e=>({detail:String(e)}));
  if(r && r.detail) toast(r.detail);          /* 后端在跑任务时返 409，这里只兜错误 */
};
window.upCheckNow = async function(){
  UP = await post('/api/update/check').catch(()=>UP);
  paintUpdate(); window.upRepaintDialog();
};
```

`paintUpdate()` 末尾加一行让浮层跟着轮询刷新（`upPoll` 与 `upInit` 都会走 `paintUpdate`）：

```js
  window.upRepaintDialog();
```

`sbUpdateClick` 改成只开层：

```js
window.sbUpdateClick = function(e){ if(e) e.stopPropagation(); window.upOpen(); };
```

`index.html` 里在 `<div class="sb-pop" id="sbFind" ...>` 旁边加骨架（`?v=` 令牌这一步顺带升）：

```html
  <div class="up-mask" id="upMask" onclick="upClose()"></div>
  <div class="up-card" id="upCard" role="dialog" aria-modal="true" hidden></div>
```

Escape 链里插在最前（它压在最上面）：

```js
  if(e.key==='Escape'){
    const uc = document.getElementById('upCard');
    if(uc && !uc.hidden){ e.preventDefault(); window.upClose(); return; }
```

CSS（`.up-fill` 用 Task 1 之后的档位；`h-2` = 8px 对齐参考实现）：

```css
.up-mask{position:fixed;inset:0;background:color-mix(in oklab, var(--ink) 32%, transparent);
  z-index:var(--z-modal);opacity:0;transition:opacity .16s var(--ease)}
body.up-on .up-mask{opacity:1}
.up-card{position:fixed;left:50%;top:50%;transform:translate(-50%,-50%);width:min(420px,92vw);
  z-index:calc(var(--z-modal) + 1);background:var(--bg-float);border:1px solid var(--line-strong);
  border-radius:var(--r-5);box-shadow:var(--shadow-pop);padding:16px}
body:not(.up-on) .up-card{display:none}
.up-head{display:flex;align-items:center;gap:8px}
.up-head b{font-size:var(--fs-sub);font-weight:600;color:var(--ink);min-width:0}
.up-x{margin-left:auto}
.up-ver{font-size:var(--fs-meta);color:var(--ink-3);margin-top:4px}
.up-bar{height:8px;margin-top:12px;border-radius:var(--r-pill);background:var(--bg-sunken);overflow:hidden}
.up-fill{display:block;height:100%;background:var(--accent);border-radius:var(--r-pill);
  transition:width .28s var(--ease)}
.up-mb{font-family:var(--font-mono);font-size:var(--fs-meta);color:var(--ink-3);margin-top:4px}
.up-err{font-size:var(--fs-meta);color:var(--bad);margin-top:8px}
.up-btns{display:flex;gap:8px;margin-top:16px}
```

（`calc(var(--z-modal) + 1)` 若被 `test_z_index_goes_through_the_scale` 判成"绕过刻度"，就把 `.up-card` 也写成 `z-index:var(--z-modal)` 并保证 DOM 顺序在遮罩之后 —— **改测试来配合新写法之前，先看那条测试原本在防什么**。）

- [ ] **Step 4: i18n**

两份字典加：`up.tAvailable`（`发现新版本 v{v}` / `New version v{v}`）、`up.tDownloading`（`正在下载 v{v}`）、`up.tReady`（`v{v} 已就绪`）、`up.tFailed`、`up.nowOn`（`当前版本 {v}`）、`up.downloadNow`（`下载更新`）、`up.later`（`稍后`）、`up.recheck`（`重新检查`）、`up.close`（`关闭`）。
`up.apply` 文案确认已经是「重启并更新」这一类；不是就改，别新增第二个近似 key。

- [ ] **Step 5: 跑全量测试**

Run: `PYTHONUTF8=1 "<python>" -m pytest -q`
Expected: 全绿

- [ ] **Step 6: 三态实测（不起真包）**

探针服务把 `app/updater.py` 的清单地址指到一个本地假 manifest，依次造 `available → downloading → ready` 三态（下载可以直接指一个本机 HTTP 服务上的 2MB 文件），每态截图不能截（本会话没有 viewport），所以用数值断言：

```js
(()=>{const c=document.getElementById('upCard');c.hidden=false;c.innerHTML=upCardHtml();
 return JSON.stringify({title:c.querySelector('b').textContent,
   w:getComputedStyle(c.querySelector('.up-fill')).width,
   mb:c.querySelector('.up-mb')?.textContent, btns:[...c.querySelectorAll('button')].map(b=>b.textContent)});})()
```

Expected: 标题随 phase 变；`.up-fill` 宽度按 `got/size` 变；按钮集合里没有「取消下载」「跳过此版本」。
**`upApply()` 不要真点** —— 它打的是 `/api/update/apply`，打包态会真的拉起安装器并退出进程；源码态 `frozen` 为假所以按钮 `disabled`，这条正好印证"打包态才第一次验"的风险，汇报时要写清楚。

- [ ] **Step 7: 升令牌 + 提交**

```bash
git add static/app.js static/index.html static/style.css static/ui.js tests/test_static_contract.py
git commit -m "feat(update): 更新浮层改居中三态卡（照参考实现），只放后端真支持的四个按钮"
```

---

### Task 7: 下载页的界面 mock 跟到首页输入台

现状：`D:\Voyra 个人网站\public\modelflow\index.html:747-813` 的 mock 画的还是运行台（日志 + 进程面板），侧栏里也还写着 `新建任务 Ctrl K`（:754）。软件首屏已经换成首页输入台（1.1.0 起），mock 就在介绍一个已经不存在的入口。配色上次已逐值对齐过（`--d-*` ↔ `:root`），这次只动**结构与文案**，别动色。

**Files:**
- Modify: `D:\Voyra 个人网站\public\modelflow\index.html`（`.mock-body` 内 `<aside class="m-side">` 与 `<div class="m-main">` 两块，约 :751-812；以及 `.mock` 的 CSS 块 :184-215）
- 该仓库另有 6 处版本号 + 3 处体积的兜底文案，**本任务不改版本号**，所以不用跑 `sync_landing.py`

**Interfaces:**
- Consumes: 软件端 Task 2/3/5 的最终结构（五行导航、嵌套 run + 相对时间、三段输入台）
- Produces: 无（终点页）

- [ ] **Step 1: 先确认要抄的到底是哪一版**

```bash
cd "../FlowForge 数模流水线"
grep -n "const items = \[" -A 12 static/app.js          # 导航行顺序
grep -n "sb-runlist\|sb-sub\|tk-bar\|tk-top\|tk-field" static/style.css   # 新结构的关键类
```

Expected: 拿到"五行导航（含两行动作）+ 项目行下挂两条 run + 三段卡"这三件事实，别凭记忆画。

- [ ] **Step 2: 改 mock 侧栏**

页里现成有五条 svg 可以直接搬，**别重画**：plus 在 `index.html:754`（`.m-new` 里那条，删按钮留图）、flow/skill/runs 在 `:756-758`、search 用软件侧 `static/ui.js` 里 `search:` 那条 path。改完的 `.m-nav`：

```html
            <nav class="m-nav">
              <div class="m-i"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width:14px;height:14px"><path d="M12 5v14M5 12h14"/></svg><span>新建任务</span><em>Ctrl N</em></div>
              <div class="m-i"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9"><circle cx="10.6" cy="10.6" r="6.1"/><path d="M15.2 15.2 20 20"/></svg><span>搜索流程与运行</span><em>Ctrl K</em></div>
              <div class="m-i on"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><path d="M4 7h6M4 12h10M4 17h5"/><circle cx="18" cy="7" r="2.2"/><circle cx="19" cy="17" r="2.2"/></svg><span>工作流</span></div>
              <div class="m-i"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><path d="M7.2 3.6h9.6a1.6 1.6 0 0 1 1.6 1.6v15.2l-6.4-3.9-6.4 3.9V5.2a1.6 1.6 0 0 1 1.6-1.6z"/></svg><span>技能库</span></div>
              <div class="m-i"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><circle cx="12" cy="12" r="8.5"/><path d="M12 7v5.2l3.4 2"/></svg><span>运行记录</span></div>
            </nav>
            <div class="m-g">项目<em>3 个在跑</em></div>
            <div class="m-r">数模求解主线</div>
            <div class="m-sub"><span class="m-live"></span><span>板凳腿缠绕结构优化</span><i>3 分</i></div>
            <div class="m-sub"><span>混凝土梁裂缝等级判定</span><i>5 小时</i></div>
            <div class="m-r">文献综述快跑</div>
            <div class="m-sub"><span>桥梁检测报告文献综述</span><i>1 天</i></div>
            <div class="m-r">参数优化流水线</div>
            <div class="m-sub"><span class="m-live"></span><span>支架拓扑优化第二轮</span><i>刚刚</i></div>
```

相对时间只能出现四种写法：`刚刚 / N 分 / N 小时 / N 天`（参考实现没有"昨天"、也没有"周/月"，`taskListItemPresentation.ts:33-53`）。上面的示例值就是照着这四档写的。
`.m-new`（:754）整条删掉；`<em>` 在 `.m-g` 里已经被样式占用，所以给 `.m-nav em` 单独一条 `margin-left:auto` 规则。
新增 CSS：`.m-sub{margin-left:12px;padding-left:8px;border-left:1px solid var(--d-line);display:flex;align-items:center;gap:6px;font-size:11px;color:var(--d-ink-3)}`、`.m-nav em{margin-left:auto;font-family:var(--d-mono);font-size:10px}`（**颜色一律用页内已有的 `--d-*` 变量，别写新色值**：页里派生的是 `--d-ink` / `--d-ink-2` / `--d-ink-3` / `--d-ink-4`，定义在 `index.html:186-188`，用 oklab alpha；次行文字取 `--d-ink-3`）。

- [ ] **Step 3: 改 mock 主区成输入台**

发送键的箭头用软件同一份 path（`static/ui.js:565` 的 `arrowUp`）：

```html
          <div class="m-main m-home">
            <h2>今天要跑哪条流程？</h2>
            <div class="m-card">
              <div class="m-row"><span class="m-chip">数模求解主线 · 7 步</span><i>含 2 个检查点</i></div>
              <div class="m-ta">把这份赛题拆成可执行的子问题，跑一遍并出图…</div>
              <div class="m-bar"><span class="m-chip ghost">默认</span>
                <span class="m-lbl">任务名（可留空）</span>
                <span class="m-send"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width:14px;height:14px"><path d="M12 19.4V5.2M6.2 11 12 5.2 17.8 11"/></svg></span></div>
            </div>
            <div class="m-try"><b>试试这些任务</b><span>换一批</span></div>
            <div class="m-sug">帮我复核这一版里的逻辑漏洞</div>
          </div>
```

（芯片写"默认"而不是"跟随默认引擎" —— 软件里那个选项的文案就是 `ed.engineDefault` = "默认"，页里别写一个软件里没有的说法。）

`.m-main` 原有的运行台规则（`.m-rpbar` / `.m-scroll` / `.m-composer` / `.m-proc`）如果在别处不再被引用，**整段删掉**，包括 `:1161` 起那段往 `mockLog` 追加行的脚本和 `mockCount`、`#mProc` 的交互脚本 —— 留着就是给一个不存在的 DOM 绑事件。
（若首页想同时展示运行中的样子，做法是把日志那屏放到下面某一节，**hero 里只留一屏**。）

- [ ] **Step 4: 自查有没有把已做好的细节做没**

```bash
cd "D:/Voyra 个人网站/public/modelflow"
grep -c "mockLog\|mockCount\|mProc\|m-proc\|m-rpbar\|m-composer" index.html   # 期望 0
grep -c "Ctrl N" index.html    # 期望 >= 1
grep -n "1\.1\.1" index.html | wc -l   # 版本号 6 处保持不动
```

Expected: 前两项归零/到位；**`2.4 MB`（日志里那条截图体积）和 `约 200 MB 磁盘` 两处不能被顺手改掉** —— 它们不是安装包体积。

- [ ] **Step 5: 数值复核（本地静态站，别部署）**

```bash
cd "D:/Voyra 个人网站" && npx --yes serve -l 4123 public >/dev/null 2>&1 &
```

用 `chrome-devtools__navigate_page` 打开 `http://localhost:4123/modelflow/`，然后：

```js
JSON.stringify(['.mock-body','.m-side','.m-card','.m-send','.m-sub'].map(s=>{
  const e=document.querySelector(s), r=e.getBoundingClientRect(), c=getComputedStyle(e);
  return [s, Math.round(r.width), Math.round(r.height), c.backgroundColor, c.borderTopLeftRadius]}))
```

Expected: 三张面（`.m-card` / `.m-send` / `.m-sub`）都渲染出非零尺寸、圆角与软件侧一致（16 / 8 / 12px 量级）。
截图不可用就如实写"只量了数值，没看到画面"。
**读完就收掉那个静态服务器**（`4123` 挂着不动会占端口）：`kill $(lsof -ti :4123)` 或 `netstat -ano | grep 4123` 找到 PID 再 `taskkill //PID <pid> //F`。收尾时确认 `netstat -ano | grep -E "4123|89"` 为空。

- [ ] **Step 6: 提交（下载页仓库，不推送）**

```bash
cd "D:/Voyra 个人网站" && git add public/modelflow/index.html
git commit -m "modelflow: hero mock 跟到软件首页输入台（侧栏五行 + 嵌套最近运行 + 三段输入卡）"
```

**推送与部署不在本计划默认动作里**（[[reference-voyra-deploy]]：push main 即上线，需要单独授权）。

---

## 收尾（全部任务完成后）

- [ ] 全量测试：`PYTHONUTF8=1 "<python>" -m pytest -q`（当前基线 237 passed，本计划新增约 14 条）
- [ ] `git status` 确认工作树只剩预期文件；`netstat -ano | grep 89` 确认探针服务都关了
- [ ] 更新 `HANDOFF.md` 的契约清单：加"圆角跟嵌套层数"「键位是一张表」「侧栏一个入口一件事」三条
- [ ] 更新项目记忆 [[flowforge-ui-direction]]：键位表化、导航五行、输入台三段、更新浮层已落地
- [ ] 发版要单独批准（`HANDOFF.md` §5 的 SOP：`make_release.py` → 推源码 → `upload_cos.py` → `sync_landing.py` → `npm run build` → 推 Voyra → 线上核对）。**发版第 6 步之前，先把 Task 6 的"打包态 apply_update 从未验过"这条风险告诉人。**

## 不在本计划内（遗留清单，按建议顺序）

1. **流程「分组」的 UI** —— 等你那两张参考图。数据结构侧 `p.g` 字段已经有了，缺的是呈现层级，猜不得。
2. **打包态自更新** —— 需要在真包里跑一次 `apply_update()`（会退出进程、拉起安装器），属于要你点头的动作，不适合塞进前端任务。
3. **代码签名** —— 花钱的决定，不是技术决定。
4. **工作区文件浏览器** —— 现在只有「查看文件」跳系统资源管理器；做一个内置浏览器是新子系统，该走一遍 brainstorming 而不是塞进这份计划。
5. **拉丁字体面**（`--font-ui` 目前只配了中文字栈）—— 提案：加 `ui-sans` 一档试英文界面观感。需要你看两种渲染再定，纯数值测不出来。
6. **`--r-pill` 的全面清点** —— 现在有 24 条规则在用胶囊档（实测数：`.sb-badge` / `.sb-gcount` / `.badge,.run-badge,.sk-badge,.ff-tag` / `.pp-act` / `.st-seg` 一族按参考实现该降级 —— 计数器与标签不因类型获得胶囊，`DESIGN.md:336-341`）。Task 1 只处理了最刺眼的两条（`.cp-send` 正圆、`.toast` 胶囊），剩下的是一次独立的审美清点。
7. **4px 间距节奏清点** —— 参考实现基线是 4px，节奏 4/8/12/16/20-24（`DESIGN.md:265-273`）。实测：`static/style.css` 里 **248 条**规则的 padding/gap/margin 含非 4 倍数值，出现的取值有 1/2/3/5/6/7/9/10/11/13/14/15/18/19/22/26/29/30/38px。这不是"改一行梯子"的量级，也不该塞进本计划（会把七条任务的评审全冲掉）。建议做法：按面（侧栏 / 卡片 / 输入台 / 浮层 / 运行台）分五轮，每轮一条测试钉死那一面的取值集合，像 `RAIL_HIDDEN` 那样双向锁。
8. **键位可重绑** —— 参考实现有一整套（`settings/useShortcutRecording.ts`）。我们现在只有一张表，还没到"用户能改"。做之前先问要不要这个功能。
