# 交接文档（给下一个 agent）

> 更新时间：2026-09-25 · 上一任：Qoder agent 会话
> 本文**不含任何密钥**，只写路径。密钥与站点全局信息在同目录之外的私人文档
> `C:\Users\李星历\Desktop\个人开发信息\个人网站信息\Voyra个人网站说明.md`（含全部密钥，严禁入库）。
> 读那一份的 0 节 + 2.6 节 + 5 节，再回来看这里。

---

## 0. 30 秒自检：现在线上是什么样

| 项 | 状态 | 怎么复核 |
|---|---|---|
| 源码仓库 | `liixnglinb/Jacquard`（**公开**，main；2026-09-27 由 `Loom` 改名） | `gh api repos/liixnglinb/Jacquard/commits/main --jq .sha` |
| 旧 ModelFlow | 保留在同仓库 `modelflow-legacy` 分支 + `v0.8.8-legacy` 标签 | `gh api repos/liixnglinb/Jacquard/branches --jq '.[].name'` |
| 安装包 | `https://modelflow-1447874637.cos.ap-guangzhou.myqcloud.com/<清单里那个 file>`（公有读；**别在这里写死版本**，照着 latest.json 读） | `curl -sI <url> \| grep -i content-length` |
| 版本清单 | 同桶 `latest.json`（公有读，含 version/url/file/sha256/size/notes）—— 真源只有这一份 | `curl -s .../latest.json` |
| 下载页 | `https://lxlrwxs.top/modelflow/`（**URL 沿用 modelflow**，内容已是 Jacquard（原名 Loom），无授权码） | 带浏览器 UA 抓页面，`grep -c 授权码` 应为 0 |
| 软件内更新 | 读同一份 `latest.json`；打包态可静默装上 | `curl -s localhost:8000/api/update` |

```bash
# 一把梭验证（任何一条不对就是分发链断了）。文件名从清单里读，不写死版本：
# 这一节以前写死过 Loom-1.0.0，发三版之后整段就是假的，照着复核的人会以为分发链断了。
M=https://modelflow-1447874637.cos.ap-guangzhou.myqcloud.com/latest.json
curl -s $M
curl -sI "$(curl -s $M | sed -n 's/.*"url": "\([^"]*\)".*/\1/p')" | head -3
curl -s -A "Mozilla/5.0" https://lxlrwxs.top/modelflow/ | grep -o "Loom-[0-9.]*-setup.exe" | head -1
```

---

## 0.5 交接这一刻的仓库状态

| 项 | 值 | 怎么复核 |
|---|---|---|
| 线上 main | 每次发版都推到当轮 HEAD（不写死 sha，改它自己就多一个提交） | `gh api repos/liixnglinb/Jacquard/commits/main --jq .sha[0:7]` |
| 未推提交 | 以 `git log --oneline origin/main..HEAD` 为准；发版 SOP 第 3 步就是推它 | 同左 |
| 工作区 | 测试全过（条数以 `pytest -q` 末行为准，别抄这里） | `git status --short` |
| 本地服务 | 8000 端口有一个源码态实例在跑（数据在 `modex-data/`） | `curl -s localhost:8000/api/health` |

要推：`unset GITHUB_TOKEN GH_TOKEN`，再走第 3 节那条 `http.curloptResolve` 命令。推完再跑一次上面
那条 `gh api`，**线上 sha 真变了才算上去**（本地 `origin/main` 引用会滞后，别拿它当线上状态；
本文档也故意不写死本地 HEAD 的 sha —— 改它自己就会多出一个提交）。

**1.2.5（2026-09-26 当天补发）带的是两条"发完之后自己实测自己"抓到的修复**：
① 更新安装脚本那三秒等待其实一秒都没睡（`timeout` 在标准输入被重定向时直接报错返回，
实测整段 0.69s，而主程序 0.8s 才 `os._exit`）—— 换 `ping -n 4` 后实测 3.7s；
② 「检测连通」遇到**先思考再回答**的模型（拿真 key 实测百炼 `qwen3.8-flash`：
16 token 的预算全花在 `thinking` 上，`stop_reason=max_tokens`，一个 `text` 块都没有）
会显示成功而回显空白，看着就是"点了没反应" —— 探测预算提到 64（`chat()` 那道硬顶不动），
没有 text 块时回退显示 thinking 并打头标 `（思考）`。
③ 顺带把 `sync_landing.py` 重做了：页里带版本号的位置从"硬写预期 6 处"改成**逐处登记 +
残留必须能被解释**（产品图加了浮层之后变成 8 处，其中一处是 CSS 注释里的历史说明，
本来就不该漂）。写它的测试时这条脚本自己挨了两个 bug，都是测试先红出来的。

**这一轮（2026-09-26，发 1.2.4）是"六路对抗复核"查出来的东西全修完**。用户只说了两个字：全部修。
按严重度分三批，每条各钉一条会红的测试，改完一条就去掉那段代码确认它真会红：

- **P0（`e351efb`）**：符号链接能把两家 CLI 的密钥文件读进接口（`_outside_root` + 名字黑名单 +
  写盘 tmp 用 `O_EXCL|O_NOFOLLOW`）；进程被杀后 `running` 那行永远留在库里 → 侧栏转圈、停止按钮失效、
  重跑被挡、`count_active_runs()` 恒算它活跃，**应用内更新从此永久 409**（`reconcile_interrupted_runs`）；
  僵尸行的 cancel；更新器开始下载前不核对目标目录（`asset` 带 `..` 就能把包写到启动目录）；
  `/api/providers/test` 会把库里存的密钥发去调用方指定的 base（改成只连 127.0.0.1）；
  关窗口时那个"有任务在跑"的确认恒不触发（读了一个从没被赋值过的 `ST.activeRuns`，现全局禁用那个拼法）。
- **P1（`b31d8d4`）**：markdown 渲染只转 `& < >`，一个带双引号的 URL 就能逃出 `href` 属性挂上任意事件
  处理器（全站没 CSP，产物面板和记忆预览同一个 sink）；八处内联 `onclick` 里误用 `esc()`（那是 HTML
  文本用的，放进 JS 字符串少转一层）；两次导航并发会把 `dataset.shell` 留在错的页上（侧栏顶栏一起消失），
  串成一条链之后**必须给链尾挂 catch**，否则一轮抛异常整个应用再也翻不了页；按停止把已经流出来的正文
  连着调用栈一起扔（现在落 `partial-*.md`，产物列表里点得开）；`postAgents` 失败也返回真值，
  四道 `if(!await postAgents(...))` 守卫一次也没生效过；最大化时八个拉边手柄不藏；
  输入台的引擎候选写死两家（现在读实测盘点）。
- **P2（`d63eaae`）**：SQLite 开 WAL + `busy_timeout`（读写互相堵死会冒成接口 500，三个线程的测试
  在 DELETE 模式下立刻红）；`runs` 两条索引；**统计口径脱离 500 行窗口**（见第 2 节那条，改成
  一条 `json_each` 全表聚合，并和旧实现做过逐字段等价比对）；semver 正式比较（以前 `1.3.0-rc1`
  被读成 `(1,3,0,1)`，比正式版 `1.3.0` **大** —— 正式版发出去之后还会推荐已在 1.3.0 的人降回 rc）；
  装完把 60MB 安装包留在 `data/updates`（批处理删 + 开机扫）；建表/补列挪回主线程包进 try
  （以前它死在服务线程里，用户只看到"启动超时"，`boot-error.log` 一个字都没写）；
  选了工作文件夹就把引擎钉进快照（否则跑到一半换默认引擎，后半条 run 带着用户目录跑 codex，
  正是起跑前拒掉的那个组合）；删掉「默认」预设时补位；技能正文 512KB 上限 + 导入改成边读边判；
  `upload_cos.py` 发布前自检（sha256/size 对着真包重算、file/version/url/桶四者互核、不过一个字节
  都不传，传完再匿名回读比版本比 sha、对 HEAD 状态码和大小）；更新浮层渲染 `notes`（发版说明写了
  这么多次，软件里从来没显示过）；`FF_SEL` 回收。

**这一轮的方法论收获，四条别丢**（都在第 3 节有对应条目）：
① **自己写的注释会撞红自己的静态契约测试** —— 测试用正则扫源码，看不出那是注释。
`onmouseover="alert(1)`、`ST.activeRuns`、`await file.read()` 三次都是这么炸的。写"以前这里错在 X"
的注释时，别把 X 的原文写成可被扫到的形状。
② **库是会话级共享的**：一条 `status='running'` 留在库里，后面更新器那条测试就随机红，
红不红只看文件顺序。跨文件要么自己 `finally` 删干净，要么把断言写成增量（`>= 2` / `<= before - 2`）。
③ **验证仪器要先验**：Node 24 的全局 `WebSocket` 跟 WebView2 的 CDP 端点握不上手（同一 URL
`curl` 能拿到 101），得用 stdlib socket 自己写帧解析；帧头那两个 `self._rd(2)[0], self._rd(1)[0]`
是**顺序消费 3 个字节**，解出来的全是碎帧。
④ **系统途径要真走系统途径**：`ctypes.ShowWindow(hwnd, SW_MAXIMIZE)` 才等价于 Win+↑，
在页面里调我们自己的按钮测不到 `resize`/`focus` 那条 —— 而那正是这批要修的东西。

**这一轮（2026-09-25，发 1.2.0）做完的**：权限模式收成三档并让模式接管沙箱（第四档用检查点代替）、
运行级模型覆盖（候选只列真存在的端点预设）、工作文件夹（**只换智能体的 cwd，Jacquard 自己的写入仍留在
工作区**）、记忆文件在这台机器上可写（路径仍只从盘点清单里算）、字号基准 13→14 按参考图重标定八档、
暗色侧栏抬到卡片同色（分栏靠色差不靠线）、无边框窗口 + 自绘三枚窗控。

**发完 1.2.0 之后回头逐条对要求，查出三处不足，已在 1.2.1 修掉**（每处各钉了一条会红的测试）：
① 用户说"点输入框不要那种白色光晕"，当时只改了输入台 —— 设置页 `.pv-input` / `.st-search` /
`.st-input` 三条还挂着 `box-shadow:0 0 0 3px color-mix(--accent 22%)`，而暗色 `--accent` 就是
`#FFFFFF`，那正是同一圈白晕。**`outline` 必须无条件撤**：实测文本框（含 textarea）连鼠标点进去都算
`:focus-visible`，写成 `:not(:focus-visible)` 等于没撤（我先那样写了一遍，是靠量才发現的）。
② "两侧颜色不一样"当时只在暗色兑现（ΔL\* 10.3），亮色 `#F8F8F8` / `#F0F0F0` 只差 ΔL\* 2.8，
肉眼基本分不出分栏 → 亮色 `--bg-shell` 抬到 `#E4E4E4`（ΔL\* 7.0，顺带把侧栏文字对比从 10.8 抬到 11.9）。
③ 字重这一维一直没对过。参考图逐行量竖笔：侧栏静止行 1.33 CSS、唯一更重的一行 2.00（就是选中行），
所以 `.sb-item` 400 / `.active` 600 本来就是对的；真正错的是 `.ws-md h3-h6` 四条一起挂 600 ——
`DESIGN.md:229` 明写 h3-h4 semibold / **h5 medium / h6 normal**，已按条款分档（字号那一维保留实测刻度）。

**图标这一轮（发 1.2.2）只加了一样东西**：砖面上一团偏心柔光（`make_icon.py` 的 `SHEEN_*`，
光心 `.30/.16`、半径 `.92` 个画布、衰减 `(1-d²/r²)²`）。"单调"的成因不是缺图案，是整块砖只有
竖向渐变、没有受光方向。**三条别退回**：① 柔光只走 `build()`（48 及以上），`SMALL` 那五档
16/20/24/32/40 继续平涂 —— 给 16px 也加就是几列脏灰先弄脏竖笔（当时逐档比对过 ico 帧，这五档
与加光前逐字节相同；字标后来镜像成 J，几何重排过，**"这五档平涂"这条规则本身没变**）；② **内缘描边式 bevel 已被否**（圆角处绕成一圈灰边，像贴纸白边）；
③ **字标走白→`#E2E2E2` 已被否**（字标下半截发脏），字标保持纯白。另外 `static/logo.svg` 现在
由 `make_icon.py` 生成，别再手写回去 —— 它以前不在流水线里，柔光第一轮就只落在 PNG 上。

**新查出来、还没做的一条（不是回归）**：亮色 `.sb-run`（项目行，`--ink-3` = 60% 墨）压在 `--bg-shell`
上实测 **3.79:1**，低于正文 4.5 那条线；抬侧栏之前是 3.96，本来就不达标，这一改只动了 0.17。
要修得连 `.sb-kbd` / `.sb-group` 那一族"暗字压浅底"一起看，属于一次独立的亮色对比度专项。

**改名（2026-09-27）：织流 Loom → 织流 Jacquard，仓库 `liixnglinb/Loom` → `liixnglinb/Jacquard`。**
为什么换：拉丁名 Loom 撞得厉害（loom.com 是视频大厂，GitHub 上 `tokio-rs/loom` 2828★、同名仓库 12165 个），
公开仓库和搜索长期吃亏；而"数模流水线"这半截把一个通用编排器钉死在一个场景上（代码里没有任何数模专属东西）。
中文名「织流」保留 —— 织机正是"把有序步骤织成交付物"这回事。**Jacquard = 提花机**：1804 年用打孔卡片
编程控制织机，是"把一套有序指令交给一台机器去执行"的祖师爷，语义最贴；实测 GitHub 只有 184 个同名仓库、
最亮 234★ 且不相关（候选里 `weft` 被 AI 领域一个 1980★ 项目占住、`shuttle`/`weaver`/`conduit` 都有 2000★+）。

**这一轮只改显示层**，下面四样**刻意没动**，别顺手改：
① 安装包产物名仍是 `Loom-<版本>-setup.exe`、COS key 同、`latest.json` 的 `file`/`url` 同 ——
  改了已装 1.2.5 的人点「安装并重启」会装上**另一个名字**的程序（旧那份不会被替换，
  「添加或删除程序」里留两个条目），并且自动更新链会断在一次需要手动重装的跳转上；
② `installer.iss` 的安装目录 `{localappdata}\Programs\Loom` 同理由不动；
③ 命名互斥体 `Local\LoomZhiLiu.SingleInstance` **不能改** —— 它的唯一作用就是拦住"两份程序写同一个
  SQLite"，改了名以后旧版 Loom 和新版 Jacquard 会同时起来，那正是它要防的事；
④ 技能来源的**取值白名单** `("", "claude", "codex")` 不动（`app/pipelines.py`）—— 自家那份技能
  在流程 JSON 里一直是**空串**，从来不是 `'loom'`，所以这个字段跟改名无关；换的只是翻译键
  `ed.src.loom` 的**标签**（值已经是 Jacquard）。别为了"配合新名字"往白名单里塞 `'jacquard'`，
  那会让存量流程的技能引用落空。
**这一轮漏过、后来补上的五处**（都是显示层，当时没测钉着所以扫不出来）：codex 的 provider
显示名 `name="Loom"`、`FastAPI(title=...)`（`/docs` 页头就是它）、`make_release.py` 的兜底
`notes`（会进 latest.json，软件里的更新卡片和下载页都读那份）、源码启动横幅、端口占用提示。
现在 `tests/test_brand_surface.py` 五档齐钉：译文全量扫（zh+en 要**分开取**，合并成字典会让 en
悄悄盖掉 zh）+ 这五处逐个断言 + 上面三样刻意不动的反向钉。
**图标字标同一轮已经跟着换成 J 了**（`make_icon.py`，2026-09-27）：竖笔靠右、底钩向左、
钩尖再起一小段 —— 也就是"镜像 L + 钩"。以前我目测说"小尺寸会糊"，量下来不成立：16px 上钩尖
留出的负空间有 5 列，而糊掉的阈值是 2 列，最小构件仍是 2px。口径没变：16/20/24/32/40 五档手工
整数对齐（`SMALL` 表，现在每档多一个 `hook`），柔光只走 48 及以上，`tests/test_icon_assets.py`
按"右端对齐 + 钩真的在 + 负空间 ≥2 列"三件事栅格化实测。
**注意 1.2.5 那个包里装的还是 L** —— 图标在 `assets/loom.ico`，只有下一次 `make_release.py`
才会把它打进 exe，中途别拿已装版本比对图标。
**下一次大版本要切的**：产物名 + 安装目录 + 数据目录 `modex-data` / `flowforge.db` 这些
ModelFlow 时代的残留。

**仍然没验的两条，别当成已验**：① 打包态 `apply_update()`（替换自身）到今天为止没人真跑过。
1.2.4 加的两件事（装成功后 `del` 那个 setup.exe、开机再扫一遍 `data/updates`）发完之后拿**真 PE 桩**
（Git 自带的 `true.exe`/`false.exe` 改名成 `Loom-9.9.9-setup.exe`）在临时目录里把那段 BAT 真跑了四遍：
删/留两支控制流**是对的**，但顺带量出 **`timeout /t 3` 在标准输入被重定向时（我们是 `DETACHED_PROCESS`
起的）根本不睡** —— 整段脚本 0.69 秒就往下走，而我们自己 0.8 秒才 `os._exit`，那三秒"等主进程退场"
是 0 秒，安装器一上来就在换一个还没退出的程序（能装上靠的是 `/CLOSEAPPLICATIONS` 兜底，不是设计）。
**这条已由 1.2.5 发出去**：换成 `ping -n 4 127.0.0.1` + 安装器直接当子进程调用，实测 3.7 秒，
`tests/test_update_cleanup.py` 里三条真跑的测试钉着（含"至少睡 2 秒"）。
**但"真装机"这一步仍然没验** —— 安装器 `/SILENT` 返回后那个文件还被不被占用，只有装一次才知道；
最坏结果也只是包留在那儿没删掉，下次开机那一扫会收走。② 安装包仍无代码签名，SmartScreen 照拦。
（原来第三条"无边框窗控拿不到桥"**已经验掉了**：`webview.start(func,args)` 那条路确实不返回，
但启动前设 `WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS=--remote-debugging-port=92xx`，再从
`/json/list` 拿 page 目标的 ws 连 CDP `Runtime.evaluate`，就能在真窗口里量。实测结果见第 2 节
那两条 ShellApi 的坑。）

**上一轮（2026-09-21）做完并已验，别重复做**：六路分区子智能体把"页面上写着的功能到底实现了没有"
逐条对过一遍，确认的缺陷已修完 ——
`llm.chat` 两个分支各引用不存在的名字（"检测连通"在生产里恒红）、产物下载口能取到内部引擎转录、
更新器在下载飞行中被强制检查踩掉进度、统计页"总次数"跟着 500 条窗口一起卡死、
孤儿判定按窗口比会把正常现场报成孤儿、产出面板「刷新」按钮点一下 ReferenceError、
设置页搜索"敲任意乱码都算命中"、技能读口比写口松。
另外两件事改的是约定，别退回去：codex 0.154 的默认 `wire_api` 必须是 `responses`；
出厂技能的 `BASE/skills` 扫描四支全撤（旧安装目录里那份只读副本会复活）。
新钉住的契约见第 6 节，两条断言的实测出处见第 2 节末尾。

**再上一轮（2026-09-20）**：设置页换成 Codex 那套形态 ——
明暗预览磁贴、字号/缩放/内容宽度三条带数字读数的滑块、卡片头部动作位（挂「恢复默认外观」）、
键位页内搜索 + 双键帽；强调色换成色板芯片；更新页下载中加真刻度条。
深浅两套主题都用 `getComputedStyle` 量过，用户外观偏好已逐项还原。
新骨架的用法见第 4 节，新钉住的契约见第 6 节。

---

## 1. 等用户点头才能动的（别自己拍板）

1. **PPT / Word 的真渲染**。浏览器画不出 pptx/docx 版式，这是硬限制。三条路已摆给用户：
   - A LibreOffice headless 转 PDF 再预览（保真最高，代价几百 MB 外部依赖）；
   - B 纯 Python 拆 OOXML 做"分镜预览"（读 `ppt/slides/slideN.xml` 的文字 + `ppt/media/` 的图，按页出卡片；零新依赖，约 150–200 行 + 测试）；
   - C 让智能体产出 markdown/HTML 源，最后一步再转 pptx（实时预览直接复用现成的 markdown 渲染器）。
   **推荐 B + C**。B 点头就能做；C 动的是流程和技能提示词，要用户定（软件已经不随包带任何流程模板和技能，
   改的是用户自己建的那些）。
2. **要不要下线旧授权后端**。`functions/modelflow/*`、D1 `mflic`、`/modelflow/admin/` 还在部署、还能打开，但已无任何页面引用。下线不可逆（历史授权码数据会没）。
3. **COS 保留策略**。`upload_cos.py` 现在**只列不删**（桶刚被清空过一次，删线上包必须是显式动作）。攒到两个版本以上再谈"留最近两个"。
4. **代码签名**。安装包没签名（`installer.iss` 里没有 SignTool），Windows SmartScreen 会拦"未知发布者"。买证书是花钱的决定，要用户定。
5. **软件侧要不要跟 tabbit 的工艺（不含配色）**。2026-09-20 用户拍的是"不改软件里面的配色"，所以下面这些**只提了没做**，要做得排进一次发版（改了源码但不出包，就和线上 1.0.0 漂移）：
   圆角按 tabbit 节奏抬（`--r-4` 14→16、`--r-5` 18→24）、阴影改大模糊低透明度分层 + 同色投影、`--ease` 换成实测主控曲线
   `cubic-bezier(.4,0,.2,1)`、以及**离线打包 Montserrat 给西文用**（用户当时点了这条，但和上面一起冻住了；
   注意 `test_font_faces_declare_one_standard_weight_each` 要求全站 @font-face 的字重集合**正好**是 400/500/600/700，
   可变字体轴 `100 900` 会直接判失败）。
6. **站点侧的改名没做**（2026-09-27 核对，本轮刻意留着）。产品端显示层已经全是 Jacquard，
   站上有两处仍是前身名，都在 `D:\Voyra 个人网站`：`src/pages/Dashboard.jsx:27` 的下载卡
   `name: '织流 Loom'`、`:422` 预览条「织流 Loom 流程」，以及 `public/modelflow/index.html`
   整页（2026-09-27 抓线上实测：`Loom` 11 处 + `织流 Loom` 5 处），页内图标资源
   `logo.svg` / `logo-64.png` / `favicon-{16,32}.png` 也还是**旧字标 L**（新 J 图标只在产品仓库的
   `assets/`、`static/` 里，还没进任何一个包）。**要动就得走一次 `liixnglinb/Voyra` 的 main 推送 ——
   Cloudflare 自动部署、直接影响线上**，所以先问。改之前记得那份页内 mock 是逐值对齐软件的，
   只换字样不换几何。
7. **要不要现在发 1.2.6**。字标换 J、补上的那五处显示串、`FastAPI(title=...)` 全部只在**新包**里生效；
   不发版它们就只躺在源码里。发版 = `make_release.py` → 推源码 → `upload_cos.py` → `sync_landing.py`
   → Cloudflare 上线 → 所有已装用户会在软件里看到更新，这是往线上推的动作，按第 5 节 SOP 得一步步看着走。

---

## 2. 已知缺口 / 没做完的事（按重要性）

- **两条对引擎的断言是在本机二进制里量出来的，不是查文档查来的。**
  `D:\npm-global\node_modules\@openai\codex\node_modules\@openai\codex-win32-x64\vendor\x86_64-pc-windows-msvc\bin\codex.exe`（0.154.0）里
  写着 `` `wire_api = "chat"` is no longer supported / How to fix: set `wire_api = "responses"` `` —— 所以 `agents._codex_args`
  的默认值不能是 chat，配了端点的 codex 步骤否则会在启动那一刻就死。同一份二进制里 EventMsg 枚举明确带
  `TokenCount` / `token_count`，所以"codex 没有 token_count 事件"那条断言是**假的**，别照它改解析。
  核对方法：mmap + 字符串搜，别执行 CLI（费配额、还会动用户本机 relay）。
- **供应商目录的 api_base 要实测，别从别家工具的示例抄。** 2026-09-21 拿不带密钥的 POST 逐条探过 9 条
  anthropic 条目（判读：404 = 路径不存在，401/403/429 = 路径在、只是要鉴权）：月之暗面 `/v1/messages` 与
  百度千帆 `/v2/tokenplan/personal/v1/messages` 都是 404，两家的 anthropic 路其实各自在 `/anthropic`，已改；
  硅基流动的 `/v1/messages` 返回 401，是唯一一条以 `/v1` 结尾还成立的，所以它在
  `test_anthropic_catalog_bases_are_not_openai_paths` 的名单里。**新增条目按同一办法探，别照文档抄。**
- **阿里云百炼这一条是拿真 key 验过的（2026-09-26），两个协议都通**：目录里的
  `https://dashscope.aliyuncs.com/apps/anthropic` 返回 200 且是真 Anthropic 结构；
  OpenAI 兼容路 `https://dashscope.aliyuncs.com/compatible-mode/v1` 也通，业务空间自己的
  `https://ws-<id>.cn-beijing.maas.aliyuncs.com/compatible-mode/v1`（和 `.../apps/anthropic`）同样通。
  踩到的一件事：**`/api/providers/test` 不传 `provider` 时默认走 openai 分支**，拿它去打 anthropic 地址
  会得到一个长得像"路径 404"的错（报错格式是 openai SDK 的 `Error code: 404`）—— 我第一遍就这么误判过，
  以为目录项坏了。判读探路结果前先确认自己传的是哪个协议。
- **思考型模型会把小预算整个吃光，「检测连通」因此绿灯空白。** 百炼 `qwen3.8-flash` 实测：
  `max_tokens=16` 时它只回一个 `thinking` 块、`stop_reason=max_tokens`，一个 `text` 块都没有 ——
  `_chat_anthropic` 只收 `type=="text"`，于是 `ok=True` 而回文空串，界面上就是"点了没反应"。
  探测预算已提到 64（`chat()` 那道硬顶不变，那是产品红线的守门人），并且没有 text 块时回退去显示
  thinking 的开头（打头标 `（思考）`）。接新模型测这条时按同一形状看：`content[]` 里有哪些 type。
- **`app/cli_inventory.py` 只许回名字、条数、路径 —— 值一个字节都不许进接口。** 它扫的是两家 CLI
  自己的配置面，那些文件里就是真密钥：本机 `~/.claude/settings.json` 的 `env` 里有
  `ANTHROPIC_AUTH_TOKEN`、`~/.claude.json` 里有 `oauthAccount`、`~/.codex/config.toml` 里有
  `experimental_bearer_token`。所以预览口只开给四类"用户自己写的 markdown"
  （记忆 / 技能 / 命令 / 子智能体），mcp / hooks / plugins 连预览都没有。
  别顺手加"编辑"：schema 不归我们（同一轮里 codex 一次升级就把 `wire_api="chat"` 判死了），
  写坏的是用户 CLI 本体，而且 Jacquard 自己也跑不了 —— 它靠那两个 CLI 出正文。
  真机上踩到过两处误判（假数据里没有的形状）：`officialMarketplaceAutoInstalled` 这类记账布尔
  被当成插件、`[mcp_servers.node_repl.env]` 子段被当成第二台 MCP 服务器。
- **步骤的 `skill_src` 是"引用哪一家的技能目录"，不是路径。** 三家技能同格式（`<name>/SKILL.md`），
  所以能并列选择；但外部技能只往提示词里放一句"按你原生机制加载并遵守「x」"，
  **不读文件、不抄正文** —— 抄一份进工作区等于把别人会升级的东西冻成我们的快照。
  `skill_src` 只有一个字段，所以一步的主技能与叠加技能必须同源。引擎与来源不匹配时
  只在轨迹里留原因，不禁用。导出/导入必须带上它（`test_the_skill_source_survives_the_roundtrip`）。
- **统计页的两个开关（每日/每周/累计、近 7/近 30）刻意不落库。** 它们是这一屏的视图，
  不是外观偏好；写进 `ui_*` 那套通道就要多一个设置键、多一处白名单，
  而 `test_appearance_bulk_cannot_touch_engine_keys` 那类边界也会被拖进来。
  热力图列数恒定 52（锚点是"今天那一周的周日往回数 51 周"）—— 按天数换算再补一周的写法
  会在非周日收尾时多出第 53 列，把网格顶出卡片。
- **统计口径已经统一成全表，别再往回改。** 2026-09-26 之前这里有两套口径：逐条累计（token / 时长 / 步骤 /
  成本 / 极值 / 热力图）只扫最近 500 条，而"总次数"和状态分布走 `db.run_status_counts()`（COUNT(*)）、
  孤儿工作区判定走 `db.all_run_ids()`（全表）。窗口那半套的代价是**第 501 条连格子都画不出来**：
  实测 4000 条数据下一年热力图少 94 天、"最长一步"偏低。现在逐条累计走 `runner._STATS_SQL`
  （一条 `json_each` 全表聚合，4000 条 ×7 步实测 188ms），三套口径并成一套。
  回到窗口的写法以前出现过两次，这次由 `test_step_totals_and_extremes_cover_every_run` 钉住
  （造 501 条，最旧那条带着全表极大值和只有它才有的日期）。
- **删端点预设时为什么不弹"还有 N 个步骤在用"**：步骤的 `model` 字段有两种合法身份 —— 预设名，
  或者**裸模型 id**（那套阶梯里明写着"挂到默认预设上"）。删预设时手上只有一个字符串，
  认不出来的那些既可能是被删的预设也可能是用户手打的模型名，一报警就全是假警报。
  要区分必须给步骤快照加一个来源标记（`preset:` 前缀之类），那是改 schema + 迁老数据的事。
  删掉「默认」那一张会静默把整套端点配置弄没，这条已经修了（`db.delete_preset` 补位）。
- **软件只剩一个技能目录。** `paths.BASE / "skills"` 那四支扫描（列表 / 详情 / 另存源 / 提示词装载）已全撤：
  装过 1.0.0 的目录里还留着 `skills/ff-*`，扫它等于让出厂技能悄悄复活。随之 `editable`/`source` 恒为真，
  技能徽标、只读提示、编辑器 readonly 与 `sk.viewTitle`/`sk.readonly`/`sk.badgeUser`/`c.user` 一并删掉；
  「另存副本」从"只读才能按"改成常驻，否则这条功能就没入口了。
- **`extra.model_map` / `extra.fallback_model` / `extra.wire_api` 是活的但没有界面。** 它们由
  `runner.resolve_agent_config` 读，界面上既看不见也改不了，唯一会碰它们的是「编辑供应商」——
  而 `pfSave` 以前把 `extra` 整列覆盖写，等于改一次名字就把模型阶梯抹平了。现在表单只拥有自己那两个键。
  真要做界面，先和用户确认这三个键的语义再摆控件。
- **`apply_update()` 的打包态分支没真跑过。** 只验证了源码态明确拒绝、以及有任务在跑时返回 409。真自装要装两个版本互演，且会改本机程序 —— 上一任没敢擅自做。改这块时注意：批处理用 `encoding="mbcs"` 写（中文用户名路径 + cmd 代码页），以及 `DETACHED_PROCESS` 起 cmd 后 `os._exit(0)` 的时序。
- **下载页的兜底版本号要人工同步，而且位置会长。** 页面正常运行时从 `latest.json` 现拉，拉不到才用写死的值。2026-09-26 起 `sync_landing.py` 把每一处**按名字登记**（`SPOTS` 七条：`navVer`/`heroVer`/`btnVer`/`ftVer` 四枚 span + 下载直链文件名 + 侧栏胶囊那句「更新至」+更新浮层标题「vX 已下载好」），逐条断言命中一次，再把没被任何登记位解释掉的残留挑出来 —— 只允许它是 CSS 注释里的历史说明（比如「1.2.4 开始浮层会显示发版说明」，那句**不该跟着漂**），多一处直接失败。另有一条独立规则：浮层里「当前 v…」填的是**上一版**，不是最新版。体积三处（`heroSize`/`btnSize`/「安装包约 N MB」）单独走 `sync_size`，页里还有 2.4 MB 的 mock 日志和「约 200 MB 磁盘」，宽匹配会把它们一起改掉。以前这里写的是「预期 6 处」，加了居中浮层之后变成 8 处 —— 硬写数字的脚本就是这么开始说谎的。**改法只能用脚本 + 计数断言**（这文件用 Edit/Write 会 Native execution failed），因为漏一处不会报错，只会在 fetch 失败时给用户看一个说谎的兜底值。契约测试在 `tests/test_landing_sync.py`，其中一条直接拿真页跑计数。想彻底根治：让按钮在 fetch 成功前禁用，而不是显示兜底值。
- 下载页 FAQ 里以前写死过测试条数，几天里飘了三次（122→130→145）。2026-09-20 改成不报数、只说"看守哪些契约"，这条同步义务到此为止 —— 别再往页里塞具体条数。
- **下载页的配色基准是软件，不是任何外部参考站。** 那张页的令牌逐值等于本仓库 `static/style.css`：页面 chrome 对 `:root`（浅色），页内那张产品图对 `html[data-theme="dark"]`（页面 `#161616`、侧栏 = 卡片 = 浮层 `#2b2b2b`、内凹面板 `#202020`、条带 `rgba(13,13,13,.19)`、描边 `rgba(255,255,255,.1/.065/.15)`、输入台圆角 `--r-4` 12px、mock 外壳 `--r-5` 16px）。**改软件配色 = 要同步改它**；反过来照抄第三方站的色相是明确不要的（用户 2026-09-20 纠正过一次）。它仿 tabbit.com 仿的是**工艺**：滚动揭示、`perspective` + `rotateX` 的 hero 抬起、大模糊低透明度阴影、圆角节奏、字距纪律。
- **那张产品图会随软件过期，而且过期点很隐蔽。** 2026-09-26 这一轮补了一处：页里以前只画左下角那枚更新
  胶囊，而软件 1.2.x 起是"胶囊 + 居中对话框"两件套、1.2.4 起浮层里还有发版说明 —— 现在页内也画了那张
  浮层（`.m-mask` / `.m-upd`，逐值对软件暗色：遮罩 `color-mix(--ink 34%)`、卡片 `#2b2b2b` +
  `rgba(255,255,255,.15)` 描边 + 16px 圆角 + `--shadow-pop`、进度条 8px 胶囊）。真浏览器量过
  401×187 完整落在 mock 内、水平居中偏差 0、横向无溢出。
  2026-09-25 那一轮对出来的四处漂移：mac 的三枚 traffic-light（软件已换自绘窗控的无边框窗口）、侧栏那条 `border-right`（软件删了，分栏只靠色差）、进度行的 `--d-panel` 底带（软件的 `.rp-bar` 不铺底）、"刚写入"推到行尾（被浮在右上角的进程卡压住半截）。**逐值比 `getComputedStyle`，别目测像不像** —— 这四条里没有一条是"看一眼能发现"的。
- **这张页被砍过一次，别再砍。** `9c53b61`（2026-09-19）把它从 64KB 删到 25.8KB，交互动效、区块、mock 窗口的精细度全没了；`a28065e`（2026-09-20）按软件真实结构重做到 63.7KB。改它之前先 `git show` 对比一下字节数，掉一档就是又在删东西。
- **没有 CI。** `liixnglinb/Jacquard` 里连 `.github/` 都没有，测试只在本地跑。公开仓库加一条 `python -m pytest -q` 的 workflow 成本很低，但会引入"CI 绿了才发版"的新约定，先问。
- **`update_repo` / `update_asset` 是废弃设置项**，值还留在用户机器的 settings 表里、`/api/settings` 也还回得出来。代码已不读它们。清理要连带迁移，别顺手删一半。
- **只有 Windows 安装包。** macOS/Linux 靠源码跑（README 里这么写的，没撒谎）。
- **组件图鉴里有一行 mock 数据写着 `modelflow`**（`src/pages/UIKit.jsx` 的演示表格）。是组件示例不是产品入口，上一任故意没改。
- **工作区面板是 3 秒轮询**，不是文件事件订阅（子进程直接写盘，没有可订阅的事件，Windows 上也不想在包里塞 watchdog）。一步里连写多个文件时面板最多滞后 3 秒 —— 设计取舍，不是 bug。
- **侧栏折叠（图标轨道）在 ≤860px 不生效**，因为那个宽度下侧栏本来就横过来了。有意为之，见 `style.css` 里 `@media (min-width:861px)` 那一段。
- **孤儿工作区只能看不能清。** 「使用统计」报得出孤儿数量和体积，但没有任何删文件的端点 —— 破坏性动作宁可先不给人按。要做「一键清理」得先和用户确认保留策略（第 1 节第 3 条）。
- **设置页刻意没跟的 Codex 形态**：侧栏折叠没做设置项（品牌位点击 + Ctrl B 已经是两个入口，再加第三个违反「一个功能只留一个入口」）；明暗磁贴里那个小窗口是纯 CSS 假预览，不是真缩略图 —— 别为它去截图。

---

## 3. 这台机器的坑（不知道会白白耗掉一小时）

- **`github.com` 被 DNS 指到一个不响应的加速 IP**（`101.198.198.198`），`git push` / `curl https://github.com` 一律超时；`api.github.com` 正常。绕过办法（**别改系统 hosts**）：
  ```bash
  git -c http.curloptResolve=github.com:443:140.82.113.3 push origin main
  ```
  真 IP 会轮换，一个不行就换 `140.82.112.3` / `20.205.243.166` 多试几轮。推完用
  `gh api repos/<o>/<r>/commits/main --jq .sha` 确认线上真状态（本地 `origin/main` 引用可能滞后）。
- **动 GitHub Actions / secret 前先 `unset GITHUB_TOKEN GH_TOKEN`**，本机那个环境变量会劫持凭据且无 workflow 权限。
- `python` 不在 PATH（中文用户名把路径搞坏了）。用绝对路径：
  `C:\Users\李星历\AppData\Local\Programs\Python\Python312\python.exe`，并且带 `PYTHONUTF8=1`。
- **uvicorn 没有热重载**：改了 `app/*.py` 必须重启服务，否则你验的是旧代码（上一任在这上面被骗过两次）。
  静态文件不用重启，但浏览器侧还有一层缓存 —— 改 `static/` 后要升 `index.html` 里的 `?v=` 令牌。
  令牌算法（**别把 `index.html` 算进去**，否则改令牌会改哈希，永远追不上）：
  `md5(relpath + bytes)` 累加 `static/**` 里的 `.js/.css/.svg/.png`，取前 8 位。
- `db.get_setting` 有**进程内缓存**：绕过 API 直接改库，正在跑的服务看不见。
- Git Bash 里 `taskkill` 要写 `taskkill //PID xxx //F`（双斜杠）。
- **D 盘那些仍是单行压缩的 HTML（部分下载页）用 Edit/Write 工具会 Native execution failed**，必须用 Python 脚本做字符串替换 + **计数断言**（不断言就会静默漏替换）。
  `public/modelflow/index.html` 现在已经换成多行可读版，Edit/Write 正常 —— 但批量改色值/文案时照样推荐脚本 + `assert s.count(old) == n`，
  2026-09-20 就是这么抓到"以为只有一处、实际有两处"的。普通 `.jsx` / `.css` 文件不受影响。
- 内嵌的 in-app 浏览器经常 `visibilityState: hidden`，CSS `:hover` 的 computed style 量不到；JS 驱动的提示（`data-tip`）可以用 `dispatchEvent(new PointerEvent('pointerover'))` 触发。截图工具基本用不了（`NATIVE_BROWSER_VIEWPORT_UNAVAILABLE`）。
- **隐藏标签页里 CSS transition 不走**：切完主题立刻 `getComputedStyle` 会量到上一套主题的颜色，看起来像暗色令牌漏进浅色。多等两秒或先重渲染再量，别急着改 CSS。
- 想在浏览器里验一个只有真下载才会出现的状态：临时 `window.fetch = (u,o)=> String(u).includes('/api/update')&&… ? Promise.resolve(new Response(JSON.stringify(假状态))) : real(u,o)`，再 `await renderSettings('update')`。**验完必须把 fetch 换回去并重渲染**，否则页面留着一个不存在的下载进度。
- **静态契约测试是正则扫源码的，看不出那是注释。** 三次自己撞红自己：在 `ui.js` 注释里写了一行
  `onmouseover="alert(1)` 当反例（`test_inline_handlers_only_call_exported_globals` 扫 `on\w+="..."`
  把它当真处理器）、在 `app.js` 注释里提了一句 `ST.activeRuns`（全局禁那个拼法的那条断言当场红）、
  在 `main.py` 注释里写 `raw = await file.read()`（`test_import_reads_in_chunks_not_all_at_once`
  扫源码，把旧写法当新代码）。**描述错误用法时别写成可被扫到的形状**，或者让测试先剔掉注释行。
- **测试库是会话级共享的，`runs` 表不会自动清。** 一条 `status='running'` 留在库里，后面
  `test_updater` 那条"源码态拒绝安装"就会被 `count_active_runs()` 顶成 409 —— 红不红只看文件顺序，
  全量跑绿、单跑两文件红。造脏状态的那条要么 `finally: delete_run(...)`，要么把断言写成增量
  （`>= 2` / `<= before - 2`）。（settings 有 `conftest._restore_settings` 自动还原，`runs` /
  `api_presets` 没有 —— 预设那几条因此只能断言不变量，不能断言"表里只剩我这一条"。）
- **验仪器本身**：Node 24 的全局 `WebSocket` 跟 WebView2 的 CDP 端点握不上手（同一个 URL
  `curl` 能拿到 101，Node 连不上），只能用 stdlib socket 自己写帧解析。写帧解析时注意
  Python 元组赋值是**从左到右顺序消费**的 —— `b0, b1 = self._rd(2)[0], self._rd(1)[0]`
  读掉的是 3 个字节，`b1` 其实是帧的第三字节，解出来的消息全是碎的。CDP 还会把一条消息拆成多帧
  （FIN=0），要收齐再 `json.loads`。
- **测安装批处理，桩必须是真 PE。** 拿一个 `.cmd` 当"假安装器"测出来的结论是假的，而且假得很像真的：
  批处理里直接写 `foo.cmd`（不带 `call`）是**交出控制权、永不返回**，而 `start "" /wait foo.cmd`
  也不等 —— 两种写法都让我得出"那两行 del 根本没执行"，实际换成真 exe 桩后删/留两支全对。
  本机随手可得的真 PE 桩：`D:\Git\Git\usr\bin\true.exe`（退 0）/ `false.exe`（退 1），改名成
  `Loom-x.y.z-setup.exe` 用即可，它们会忽略 `/SILENT` 那串参数。
- **`timeout /t N` 在标准输入被重定向时不睡**（`DETACHED_PROCESS` / `stdin=DEVNULL` 都算），
  它直接报错返回，脚本照往下走 —— 想要真等待用 `ping -n N+1 127.0.0.1 >nul`。
  这个坑的隐蔽之处在于：不睡不报错，只会让"等三秒"变成"等 0.02 秒"，而那段脚本等的是自己进程的退场。
- **系统途径的窗口状态要用系统途径测**：`ctypes.windll.user32.ShowWindowW(hwnd, 3)`（SW_MAXIMIZE）
  才等价于 Win+↑ / 贴边快照；在页面里调我们自己的 `winMaxToggle()` 走的是"按钮自己同步"那条路，
  永远测不到 `resize`/`focus` 监听。真窗口里的取数口：`WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS=--remote-debugging-port=92xx`
  + `/json/list` 拿 `webSocketDebuggerUrl`（Git Bash 会把 `/devtools/page/x` 这种参数改写成本地路径，
  路径要在脚本里从 `/json/list` 现取）。
- **SQLite 开了 WAL 之后数据目录会多 `flowforge.db-wal` / `-shm` 两个影子文件**，`modex-data/` 整目录
  已在 `.gitignore` 里，别单独给它们加例外；安装包不碰数据目录，升级不受影响。

---

## 4. 文件地图（谁负责什么）

```
app/main.py            全部 /api 路由。注意 /api/settings/bulk 只收 ui_ 前缀
                       技能只有一个目录（paths.USER_SKILLS_DIR），读写四条口共用 _skill_dir_safe
app/runner.py          执行引擎：工作区、SSE 事件、检查点、日志读取、使用统计
  ├ _is_internal()     整条相对路径任一段以下划线开头 = 内部文件，别泄漏进清单
  ├ ws_file()          工作区路径校验只写这一处（预览和下载共用）
  └ read_workspace_file()  预览单文件；内部文件与二进制不给正文
app/agents.py          Claude / Codex CLI 适配（参数拼装 + 流式解析）
app/cli_inventory.py   两家 CLI 配置面的只读盘点：只回名字/条数/路径，值不进接口
                       ├ scan()          设置页「Agent 能力」的数据源
                       ├ preview_text()  只放四类用户写的 markdown
                       └ reveal_path()   /api/reveal 的 agent 分支，绝不 mkdir
app/updater.py         读 COS latest.json → 下载 → 核对 sha256 → 打包态静默装上
app/paths.py           FROZEN 分支：打包态数据在 exe 同级 data/
static/ui.js           中英双字典 + ICONS + 外观通道 + mdToHtml
static/app.js          路由、侧栏（含折叠轨道）、tooltip、设置页各分区、更新胶囊
  ├ stSeg/secRepaint   分段控件与"只重渲染当前分区"；页头 chip 也要一起补，否则切引擎后还写着旧引擎
  └ tokenHeat/hmValues 一年热力图三档读数共用一套格子；悬停是两行 data-tip（&#10; 分隔，裸换行会被归一化成空格）
  ├ spanel/srow/sblk  设置页三种骨架：卡片（可带头部动作）、右侧控件行、整块控件行
  ├ apTiles/apSwatches 明暗磁贴与强调色板，档位取 window.AP_OPTS，点击只改类不重渲染
  └ sslider/slPick    字号/缩放/内容宽度三条滑块：oninput 只 previewAppearance，onchange 才落盘
static/run.js          运行台：转录、进程卡、工作区实时面板、日志查看
static/style.css       设计令牌。圆角只准 --r-1…--r-5/--r-pill；字号只准 --fs-* 七档
  └ --sw-lite-*/--sw-dark-*/--sw-acc-*  明暗磁贴与色板要显示「另一个主题长什么样」，
     故意固定在 :root 里，不随 html[data-theme] 走 —— 别顺手把它们搬进主题块
tests/                 契约与回归（条数以 pytest -q 为准）。test_static_contract.py 是静态资产契约（见第 6 节）
loom_launch.py         打包态入口（pywebview 窗口 → 失败退回浏览器）
loom.spec              PyInstaller。**excludes 里那串重库别删**，见 make_release 注释
installer.iss          Inno。装 {localappdata}\Programs\Loom，卸载保留 data\
make_release.py        一键出 setup.exe + latest.json；拒绝把开发机 data/ 打进包
upload_cos.py          传之前先自检清单与真包（sha256/size/file/version/url/桶互核，不过就一个字节都不传），再上传 + 设公有读 + 匿名回读验证（签名成功 ≠ 公网能下）
sync_landing.py        发版第 5 步：下载页兜底版本号/体积，锚点 + 计数断言都写死在里面
make_icon.py           PIL 画图标（本机无 SVG 渲染器）。大档走矢量几何，16/20/24/32/40
                       走 SMALL 表按目标像素网格各画一遍 —— 别改回"画 1024 再缩放"，
                       眼距 9/120 缩到 16px 只剩 1 列，任务栏上就是一团糊的。
                       产物除 assets/（ico + 各档 PNG）外还写 static/logo-sm.svg 与
                       static/favicon-{16,32}.png，侧边栏和标签页用的是这两份小尺寸变体。
```

---

## 5. 发版 SOP（照做）

```bash
cd "C:/Users/李星历/Desktop/FlowForge 数模流水线"
PY="/c/Users/李星历/AppData/Local/Programs/Python/Python312/python.exe"

# 1. 版本号 + 全量测试
#    改 app/version.py，然后：
#    别加第二个 -q：pytest.ini 的 addopts 已经带 -q，再叠一个就是 -qq，
#    汇总行（"367 passed in 45s"）会被吞掉，你会以为自己没跑到。
PYTHONUTF8=1 "$PY" -m pytest

# 2. 图标/字标动过时先重新生成全套落点（一次写 assets/ ico+PNG 与 static/ 那几份小尺寸变体）
PYTHONUTF8=1 "$PY" make_icon.py

# 2b. 只要 static/ 下的文件内容变过，就得 bump 缓存令牌，否则装好的人端的是旧缓存
#     （改图标这一轮就是这么差点没生效：logo-sm.svg 换了字标，?v= 还是旧的）
sed -i "s/?v=<旧令牌>/?v=$(git rev-parse --short=8 HEAD)/g" static/index.html
grep -c "?v=$(git rev-parse --short=8 HEAD)" static/index.html   # 应为 10

# 2c. 打包
PYTHONUTF8=1 "$PY" make_release.py --notes "这一版改了什么"

# 3. 提交源码（别先传包，失败了好回退）
git add -A && git commit -m "release: X.Y.Z —— …"
unset GITHUB_TOKEN GH_TOKEN
git -c http.curloptResolve=github.com:443:140.82.113.3 push origin main

# 4. 上传 COS（公有读 + 匿名回读验证）
PYTHONUTF8=1 "$PY" upload_cos.py

# 5. 同步下载页的兜底版本号与体积（fetch 失败时用户看到的就是这些值）
#    python sync_landing.py <旧版本> <新版本> [新体积MB]   ← 7 处显示位逐条登记 + 浮层
#    「当前 v」填上一版 + 3 处体积，注释里的历史说明故意不动，漏一处直接失败，
#    锚点写死在脚本里（heroSize / btnSize / "安装包约 N MB"），带计数断言。
#    体积没变就不传第三个参数。别按"约 N MB"宽匹配 —— 页里还有 2.4 MB 的 mock
#    日志和"约 200 MB 磁盘"，宽匹配会把它们一起改掉。
#    文件在 D:\Voyra 个人网站\public\modelflow\index.html，用 Edit/Write 会
#    Native execution failed，只能脚本改。
#    改完 npm run build → commit → push（Cloudflare 1~2 分钟上线）

# 6. 线上验证：第 0 节那三条 curl + 装一次新机看「检查更新」
```

---

## 6. 每次改完跑什么

```bash
PYTHONUTF8=1 "<python>" -m pytest -q          # 全绿即可，不需网络
```

契约测试会替你看住这些事，报错时**先怀疑自己改错了，别急着放宽断言**：

- 中英字典必须一一对应，且**不能有没人用的 key**（`t()` 用 `||` 取字典会把空文案印成 key 本身）。
- CSS 变量必须有定义；圆角/字号只能取刻度里的档位；`--fs-*` 八档每档都得有人用。
- **`rem` 只准出现在 `--fs-*` 那八档，几何一律 px**（2026-09-22 定的）。根字号是
  `html{font-size:calc(14px * var(--text-scale))}`，也就是「文字大小」设置在动的东西 ——
  图标/内边距/行高一旦用 rem，选「特大」就等于把整个界面放大 26%，跟「界面缩放」
  （`body{zoom}`）职责重叠，而且这几轮量出来的像素节奏只在默认档成立。
  改前实测：图标 16.25px → 20.47px；改后两个档位都是 16.25px，字号照常 13 → 16.38px。
- 挂到 `window` 上的处理函数必须有调用方 —— 内联 `onclick` 只能调它们，但反方向没人管：
  把弹层改成首页时 ✕ 按钮没了，`tkHideSugs` 就成了孤儿，几百条测试一条不红。
- 模板里写了 `class="xxx"` 而 style.css 没这条规则 → 直接失败（上一任就是这么写出过一个 `.pl-row-sub`，量出来字号还是正文 14px）。
- 静态 `style="font-size:…/padding:…"` 禁止（绕过刻度）；动态宽度不算。
- 侧栏折叠轨道：清单里每个文字类都必须有 `display:none` 规则，**多藏一个也算漂移**。
- 键位是一张表（`app.js` 的 `KEYMAP`）：绑定和设置页的「键位」说明同源。加一行就必须有 `sc.<id>` / `sc.<id>D` 两份文案，全局那几行还得有 `KEY_ACTION` 里的处理函数 —— 别再写 `if(k===...)`。
- 圆角跟**嵌套层数**走：第一个圆角容器 `--r-4`，往里 `--r-3 → --r-2 → --r-1`；`--r-5` 只有四个批准例外（主输入台壳 / 对话框壳 / toast / 品牌底板）；胶囊档只给故意的胶囊和正圆（清单是 `NESTED_RADIUS` + `CIRCLE_50`，双向锁）。
- 侧栏一个入口一件事：同一次运行不在「项目」和另一组「最近」里各出现一次；run 嵌在自己的流程下面。
- 居中的浮层收起时必须 `pointer-events:none`（`inset:0` 的遮罩只用 opacity 收 = 全屏点不动）。
- **`ws` 和 `cwd` 是两件事，不许合并。** `ws` 是 Jacquard 自己的落盘处（派生工作区 `run-<id>`：转录、给 claude 的系统提示文件、步骤产物），`cwd` 只是智能体在哪个目录干活（下任务时选的文件夹）。合成一个的后果是具体的：`delete_run` 里那句 `rmtree(workspace_dir(...))` 会去删用户的工程目录，而 codex 那路会往里面写 `AGENTS.md` 覆盖人家的项目记忆 —— 所以 codex + 自定义文件夹在 `start_run` 就直接拒（按 `resolve_engine` 判，和实际跑的那套同源）。
- 派生工作区的目录名只有一份规则：`db.ws_dir_name(run_id)`。`runner._ws_path` 和 `create_run` 写进库的那个名字都必须走它 —— 从前是两份各写各的，库里存着 `run-run-<id>` 这种磁盘上根本不存在的名字。
- 滑块读数说「14px」：`ROOT_PX`（app.js）必须等于 CSS 里 `html{font-size:calc(14px * …)}` 的那个 14，测试钉着。
- 设置页外观的档位表只有一处真相：`ui.js` 的 `TEXT_SIZES/ZOOMS/WIDTHS/THEMES/ACCENTS`，`APP` 里的键名和
  `loadAppearance` 白名单必须同名（测试钉着），否则滑块会静默停在 0 档。
- **`node --check` 过一遍每个 `static/*.js`。** 其余契约全靠正则扫源码，看不见语法错误：
  这一轮把 Python 的"相邻字符串自动相连"当成 JS 写进字典，设置页整个白屏
  （`t is not a function`），200 条测试一条不红。
- 「检测连通」那两条路都要重新看：`/api/providers/test` 现在**只准连 127.0.0.1**，且库里存的密钥
  永远不会被发去调用方指定的 base（改 base 不重打 key 就报错，不静默外送）。
- **数据层三条别退回**（`tests/test_db_concurrency.py`）：连接必须开 WAL + `busy_timeout>=5000`
  + `synchronous=NORMAL`（只设在一个新连接上不算， pragma 是**每连接**的，journal_mode 才是库级持久的）；
  `runs` 上那两条索引必须还在，且 `EXPLAIN QUERY PLAN` 里不许出现 `TEMP B-TREE`；
  三线程同读同写那条在 DELETE 模式下会当场红 —— 它就是为盯这个而写的。
- **统计口径不许再退回扫描窗口**：`test_step_totals_and_extremes_cover_every_run` 造 501 条，
  最旧那条带着全表最大 `duration_ms` 和只有它才有的日期；窗口一回来三条断言全红。
- **版本号比较是 semver**，不是抠数字。反向断言也要跑（`test_version_compare_is_antisymmetric`）：
  只在单向挑几个数，很容易两个方向都返回「更新」。
- **发布脚本必须在传之前自检**（`tests/test_publish_selfcheck.py`）：`consistency_errors` 覆盖
  sha256/size 与真包、file↔version、url↔file↔桶、notes 非空。更新器现在完全信任 `latest.json`
  做安全判定，所以一份对不上的清单传上去 = 所有人「检查通过、点安装就报错」。
- 引擎归属是**起跑那一刻定死的**：选了工作文件夹就把 `resolve_engine` 的结果钉进步骤快照
  （`test_a_run_with_a_workdir_pins_the_engine_it_started_with`）。步级 engine 留空 = 每一步重读全局默认，
  跑到一半改设置会把后半条 run 拐去 codex —— 而 codex + 用户目录正是起跑前拒掉的那个组合。
- 技能正文有 512KB 上限（新建 / 编辑 / 导入三条路都判），那份正文是**整篇**进每一步提示词的。
  导入的 200MB 上限是边读边判，不许回到 `await file.read()` 之后才看 `len`。
- 更新浮层要渲染清单里的 `notes`（转义 + 带滚动上限），`FF_SEL` 的修剪只准挂在 `ffOpen` 上。
- 路径越界用例是参数化的一整套（`../../db`、`%2e%2e`、绝对路径…），新加读文件的端点要接进同一套校验。
- **内联 `onclick="x()"` 里的名字必须在 `window` 上找得到。** 四个脚本各自是 IIFE，没导出的函数在全局作用域里
  不存在 —— 产出面板那个「刷新」就是这么死的（按钮照画，点一下 ReferenceError，而几百条测试一条都不会红）。
  `test_inline_handlers_only_call_exported_globals` 现在盯着；它的兜底名单 `HOST_GLOBALS` 只有三个词，
  另有一条反向测试盯着这个名单别烂掉。
- 「检测连通」这条直连路有两道锁：`llm.chat` 的 64 token 硬顶，和 `test_llm_probe.py` 那组只桩到 HTTP
  一层的用例（路由侧的测试直接 monkeypatch `test_connection`，是**看不出** chat 内部引用了不存在的名字的）。

改完**在浏览器里量一遍**再收工：`getComputedStyle` 拿真实值，别凭眼睛看。
上一任靠这个抓到过：轨道被两个图标按钮撑破 4px、图标按钮漏 `data-tip-any`、
换语言时两处文案不刷新。
