/* ==========================================================================
 * Jacquard 织流 · 界面文案与外观引擎
 *  window.t(key, params)  —— 按当前语言取文案
 *  window.APP             —— 外观状态（语言/明暗/字体/字号/缩放/内容宽度）
 *  window.applyAppearance —— 把状态写到 <html> 的属性与 CSS 变量上
 * 外观存在后端 settings 表，启动时由 index.html 的引导脚本读回来，避免闪白。
 * ========================================================================== */
(function () {
'use strict';

const DICT = {
  zh: {
    'brand.name': '织流', 'brand.sub': '本地智能体流水线工作台', 'brand.full': 'Jacquard 织流',
    'ui.readFailed':'页面内容未能完整读取','ui.keepResults':'已显示的内容保留。空白不表示没有数据，请检查本地服务后重新读取。','ui.retryRead':'重新读取当前页',
    'nav.workflows': '工作流', 'nav.skills': '技能库', 'nav.runs': '运行记录', 'nav.settings': '设置',
    'nav.newTask': '新建任务', 'sb.search': '搜索流程与运行', 'sb.noHit': '没有匹配的流程或运行',
    'sb.liveN': '{n} 个在跑', 'sb.noLive': '当前没有在跑的任务', 'sb.flows': '项目', 'sb.newFlow': '新建项目',
    'time.now': '刚刚', 'time.m': '{n} 分', 'time.h': '{n} 小时', 'time.d': '{n} 天',
    'sb.noProject': '还没开工的项目 —— 去「工作流」挑一条跑起来',
    'sb.rowMore': '更多操作', 'sb.viewFiles': '查看文件', 'sb.newTaskHere': '在此流程新建任务',
    'sb.archive': '归档', 'sb.unarchive': '取消归档', 'sb.archived': '已归档',
    'sb.showArchived': '看已归档', 'sb.backToProjects': '回到项目',
    'sb.archivedEmpty': '没有归档的流程', 'sb.archivedToast': '已归档「{name}」',
    'sb.unarchivedToast': '已把「{name}」放回项目', 'sb.noRunYet': '这条流程还没有运行过，没有产物可看。',
    'sb.stepsN': '{n} 步', 'sb.toggle': '切换侧边栏',
    'win.min': '最小化', 'win.max': '最大化', 'win.restore': '还原', 'win.close': '关闭',
    'win.closeBusy': '还有 {n} 个任务在跑或停在检查点，现在关窗口会把它们一起带走。确定关闭？',
    'foot.theme': '外观', 'foot.lang': '语言', 'foot.engines': '智能体引擎',
    'up.grp': '更新', 'up.url': '更新清单地址', 'up.urlD': '留空即用内置地址（COS 上的 latest.json），下载页读的是同一份',
    'up.urlPh': 'https://…/latest.json', 'up.status': '更新状态', 'up.statusD': '当前版本 v{v}',
    'up.check': '检查更新', 'up.avail': '更新', 'up.ready': '已下载', 'up.failed': '更新失败',
    'up.checking': '正在检查…', 'up.unknown': '未知', 'up.idle': '尚未检查',
    'up.hasNew': '发现新版本 v{v}', 'up.isCurrent': '已是最新 v{v}',
    'up.downloadingPct': '下载中 {p}%', 'up.saved': '已保存，最新版本 v{v}', 'up.checked': '{s}',
    'up.tipAvail': '发现新版本 v{v}（当前 v{cur}），点击开始下载',
    'up.tipDl': '下载中 {got} / {size}', 'up.tipReady': '新版本已下载，点击安装', 'up.tipErr': '更新出错：{e}',
    'up.readyTip': '已下载到 {p}', 'up.errPrefix': '出错：{e}',
    'up.reqFail': '更新请求失败',
    'up.tAvailable': '发现新版本 v{v}', 'up.tDownloading': '正在下载 v{v}',
    'up.tReady': 'v{v} 已下载好', 'up.tFailed': '更新没走通',
    'up.nowOn': '当前 v{v}', 'up.downloadNow': '开始下载', 'up.later': '稍后',
    'up.recheck': '重新检查', 'up.close': '关闭',
    'up.askApply': '现在安装 v{v} 并重启？',
    'up.askDownload': '开始下载 v{v}',
    'up.askBusyQuit': '{n} 个任务在跑或停在检查点 —— 重启会把它们打断',
    'up.askBusyDl': '{n} 个任务在跑，下载会占带宽、可能拖慢它们',
    'up.askGo': '安装并重启',
    'up.apply': '安装并重启',
    'up.applyD': '下载完成后装上安装包并重启，安装器会自己关掉正在运行的 Jacquard',
    'up.applyNo': '当前是源码运行，没有可替换的程序 —— 请直接双击安装包装新版本',
    'up.applyStarted': '正在安装并重启…',

    'c.create': '创建流程', 'c.edit': '编辑', 'c.delete': '删除', 'c.duplicate': '副本',
    'c.save': '保存', 'c.cancel': '取消', 'c.close': '关闭', 'c.back': '返回', 'c.view': '查看',
    'c.import': '导入', 'c.export': '导出', 'c.more': '更多操作', 'c.none': '无', 'c.refresh': '刷新', 'c.steps': '个步骤', 'c.justNow': '刚刚',
    'c.minAgo': '{n} 分钟前', 'c.hourAgo': '{n} 小时前', 'c.dayAgo': '{n} 天前',
    'c.download': '下载',
    'c.words': '{n} 字', 'home.giveTask': '下任务', 'home.mineEmpty': '还没有流程 —— 点右上角「新建」从零编排，或导入别人分享的 JSON',
    'home.recentEmpty': '还没有运行记录', 'home.engineNone': '智能体未就绪',

    /* 工作台（首页） */
    'task.briefPh': '目标、背景、已有材料、想交付成什么样。',
    'tk.greet': '今天要跑哪条流程？',
    'tk.stepsAria': '这条流程的步骤', 'tk.cpMark': '这一步会停下等确认',
    'tk.noSteps': '这条流程还没有步骤',
    'tk.modelAny': '跟随步骤', 'tk.modelAnyD': '不覆盖，每一步沿用它自己挑的端点',
    'task.labelPh': '留空则用流程名', 'task.start': '开始全自动执行',
    'task.needBrief': '任务说明不能为空', 'task.started': '已启动', 'task.noFlow': '还没有流程，先创建一个',
    'task.dirPh': '工作文件夹（留空=默认工作区）',
    'task.dirTip': '只换智能体干活的那个目录：转录、产物、系统提示仍旧落在软件自己的运行工作区。'
      + 'claude 引擎支持；codex 是从运行目录里读 AGENTS.md 拿本步指令的，指定文件夹会在起跑前就被拒。',

    'st.pending': '待执行', 'st.running': '执行中', 'st.waiting': '等待确认', 'st.done': '已完成',
    'st.failed': '失败', 'st.cancelled': '已取消', 'st.revising': '修订中', 'run.stepOf': '已完成 {done} / {total} 步',
    'run.checkpointWait': '· 检查点等待确认', 'run.brief': '任务说明', 'run.briefSub': '每一步提示词的唯一依据',
    'run.artifacts': '工作区文件', 'run.noArtifacts': '还没有文件 —— 智能体一开始写就会出现在这里', 
    'run.wsLive': '实时', 'run.wsOut': '交付物', 'run.wsChg': '刚写入',
    'run.workedIn': '这条运行是在这个目录里干活的，下面列的是软件自己工作区里的产物：',
    'run.wsBinary': '浏览器里看不了这类文件，下载后用对应程序打开。',
    'run.wsReveal': '在文件夹中显示', 'run.wsRevealFail': '打不开文件夹',
    'run.wsRaw': '原文', 'run.wsRendered': '渲染', 'run.wsTrunc': '（只显示前 400 KB）',
    'run.wsLoading': '读取中…', 'run.wsFail': '读不到这个文件',
    'run.continue': '继续执行', 'run.stop': '停止', 'run.rerun': '从头重跑', 'run.rerunFrom': '从此步重跑',
    'run.rerunConfirm': '从第 {n} 步「{label}」起重跑？', 'run.rerunTail': '\n其后 {n} 个步骤也会一并复位重跑。',
    'run.rerunDone': '已重启执行', 'run.send': '发送修改指令',
    'run.reviseEmpty': '请填写修改要求', 'run.reviseDone': '已按要求改写「{label}」',
    'run.reviseFail': '「{label}」这一步没能改完，产物保持原样', 'run.deleted': '已删除',
    'run.delConfirm': '确定删除这次运行？工作区产物一并删除。', 'run.notFound': '运行不存在',
    'run.toolUnit': '次工具', 'run.moreLines': '展开 {n} 条更早的执行记录',
    'run.runningOn': '正在执行：{label}', 'run.composerPh': '输入修改要求，回车发送…',
    'run.log': '日志', 'run.logHint': '打开本步智能体的原始转录',
    'run.proc': '进程', 'run.procToggle': '收起 / 展开进程列表',
    'run.procPolicy': '状态面板展开策略', 'run.procCollapse': '收起为胶囊', 'run.procExpand': '展开状态',
    'run.policy.always': '始终展开', 'run.policy.idle': '跑完收成胶囊', 'run.policy.pill': '始终收成胶囊',
    'run.lgTitle': '智能体转录', 'run.lgLoading': '读取中…', 'run.lgEmpty': '这份日志是空的',
    'run.lgMeta': '尾部', 'run.lgLines': '行', 'run.lgTrunc': '大文件已截断',
    'run.lgCopy': '复制原文', 'run.lgCopied': '原始转录已复制', 'run.lgCopyFail': '复制失败，请手动选择',
    'run.lgSys': '启动', 'run.lgTool': '调用', 'run.lgOut': '产出', 'run.lgRet': '返回',
    'run.lgErr': '报错', 'run.lgEnd': '结束', 'run.lgRaw': '原文',
    'run.lgTools': '个工具', 'run.lgRetry': '端点重试', 'run.lgTurns': '轮',
    'run.lgExit': '退出码', 'run.lgOk': '成功', 'run.lgFailed': '失败',
    'run.durLong': '{m} 分 {s} 秒',

    'list.flows': '工作流', 'list.runned': '运行', 'list.duplicateName': '副本名称', 'list.deleteConfirm': '确定删除流程「{name}」？',
    'list.copied': '已创建副本「{name}」',
    'list.imported': '已导入流程「{name}」', 'list.importBad': '这个文件不是流程 JSON：需要 name 和至少一个步骤',
    'list.importDup': '「{name}」已经存在，作为「{nn}」导入？', 'ed.newTitle': '创建流程', 'ed.editTitle': '编辑流程', 'ed.basic': '基本信息',
    'ed.name': '流程名（英文小写，唯一）', 'ed.label': '显示名称', 'ed.desc': '流程描述',
    'ed.descPh': '写清这套流程适合什么场景', 'ed.namePh': '如 my-pipeline',
    'ed.nameHint': '创建后不可改；显示名称随时可改', 'ed.stepsTitle': '步骤清单',
    'ed.stepsSub': '从上到下依次执行', 'ed.addStep': '添加步骤', 'ed.stepName': '步骤名称',
    'ed.stepKey': '标识 key', 'ed.keyHint': '小写字母 / 数字 / 连字符 / 下划线', 'ed.keyDup': 'key 重复，保存前需修改',
    'ed.role': '角色', 'ed.role.executor': '执行', 'ed.role.reviewer': '审查', 'ed.role.editor': '润色',
    'ed.roleHint.executor': '主执行步骤：产出本步文件', 'ed.roleHint.reviewer': '检查前序产物，挑问题给修正意见',
    'ed.roleHint.editor': '对既有产物做编辑改进', 'ed.mainSkill': '主技能', 'ed.viewSkills': '查看技能库',
    'ed.src.loom': 'Jacquard', 'ed.src.claude': 'Claude', 'ed.src.codex': 'Codex',
    'ed.extHint': '按名字引用，Jacquard 不拷贝也不改写这份技能。',
    'ed.lostSkill': '这份技能在 Jacquard 的目录里已经找不到了。',
    'ed.out': '产物文件', 'ed.outPh': '如 ANALYSIS.md', 'ed.outHint': '写入工作区，后续步骤可引用',
    'ed.advanced': '高级选项', 'ed.engine': '执行引擎', 'ed.engineDefault': '默认',
    'ed.engineHint': '留空=用设置页默认引擎', 'ed.engineNone': '本机未检测到 CLI 智能体，先去设置页确认',
    'ed.engineReady': '已就绪：{list}', 'ed.model': '本步模型', 'ed.modelFollow': '跟随默认预设',
    'ed.modelPreset': '预设：{name}', 'ed.modelRaw': '{model}（裸模型名）',
    'ed.modelHint': '填预设名=整套端点配置换过去；填模型 ID=挂到默认端点上',
    'ed.extraSkills': '叠加技能（可多个）', 'ed.addSkill': '添加…', 'ed.stepExtra': '本步补充要求',
    'ed.stepExtraPh': '只对本步生效、优先级高于技能规范的额外约束',
    'ed.stepExtraHint': '这段会进入本步提示词的「本步补充要求」，不动技能原文',
    'ed.checkpoint': '人工检查点', 'ed.checkpointHint': '本步完成后暂停，等我确认再继续',
    'ed.preview': '预览提示词', 'ed.previewSub': '看这一步实际发给智能体的内容',
    'ed.previewTitle': '第 {n} 步实际发出的提示词', 'ed.previewSystem': '系统规范（技能全文）',
    'ed.previewUser': '用户指令（任务与契约）', 'ed.goSkill': '去改这一步的技能',
    'ed.previewBriefPh': '填一段任务说明用于预览（可留空）：', 'ed.save': '保存流程',
    'ed.saved': '流程已保存', 'ed.unsavedLeave': '这条流程有还没保存的改动，确定离开吗？',
    'ed.needName': '请填写流程名', 'ed.needLabel': '第 {n} 步缺步骤名称',
    'ed.needKey': '第 {n} 步 key「{key}」不合法', 'ed.needSkill': '第 {n} 步「{label}」还没绑定主技能',
    'ed.notFound': '流程不存在', 'ed.unsavedPreview': '先保存流程，才能预览实际提示词',
    'ed.moveUp': '上移', 'ed.moveDown': '下移', 'ed.delStep': '删除步骤', 'ed.newStep': '第 {n} 步',

    'sk.title': '技能库', 'sk.new': '新建技能', 'sk.empty': '还没有技能 —— 新建一份，或导入标准 skill 包（zip / SKILL.md）',
    'sk.importing': '正在导入「{name}」…',
    'sk.imported': '已导入「{name}」', 'sk.importFail': '导入失败：{err}',
    'sk.newTitle': '新建技能', 'sk.editTitle': '编辑技能',
    'sk.nameField': '技能名（英文小写，步骤里引用它）', 'sk.namePh': '如 my-review-checklist',
    'sk.nameHint': '只能小写字母/数字/连字符/下划线', 'sk.content': '技能内容（Markdown）',
    'sk.contentPh': '# 我的技能\n\n## 目标\n这一步要产出什么…\n\n## 硬性规则\n- 必须…',
    'sk.lines': '{n} 行 · 保存后立即生效', 'sk.save': '保存技能', 'sk.saved': '技能已保存',
    'sk.created': '技能已创建', 'sk.needName': '请填写技能名', 'sk.needContent': '技能内容不能为空',
    'sk.dupe': '另存副本',
    'sk.dupeName': '副本名（英文小写）', 'sk.dupeDone': '已创建副本「{name}」',
    'sk.delConfirm': '确定删除技能「{name}」？引用它的步骤会读不到内容。', 'sk.deleted': '已删除',
    'sk.empty2': '空',

    'set.title': '设置', 'set.back': '返回应用', 'set.search': '搜索设置…', 'set.noHit': '没有匹配的设置项',
    'set.hits': '匹配 {n} 个分区',
    'set.grp.pref': '偏好', 'set.grp.exec': '执行', 'set.grp.data': '数据',
    'set.appearance': '外观', 'set.engines': '智能体引擎', 'set.presets': 'API 接入',
    'set.runtime': '执行参数', 'set.dirs': '本地目录', 'set.about': '关于',
    'set.stats': '使用统计', 'set.update': '更新',
    'set.shortcuts': '快捷键',
    'set.appearanceD': '',
    'set.enginesD': '每一步都由本地 CLI 智能体执行，这里管引擎与可执行文件。',
    'set.presetsD': '端点与密钥只注入给智能体，系统内没有直连模型的通道。',
    'set.runtimeD': '一次运行里所有步骤共享的执行策略。',
    'set.dirsD': '全部数据都留在本机，没有云端副本。',
    'set.aboutD': '',
    'set.shortcutsD': '全局键盘操作，输入框聚焦时同样有效。',
    'set.chipEngines': '{n} 个引擎可用', 'set.chipNone': '未检测到可用引擎',
    'set.statsD': '每次运行的耗时、工具调用与累计费用都在这里。',
    'set.updateD': '检查更新、下载安装包，并核对文件的校验和。',

    'ap.language': '语言', 'ap.languageD': '界面文案语言；技能正文与提示词不受影响。',
    'ap.theme': '明暗模式', 'ap.themeD': '跟随系统会实时响应 Windows 的深浅色切换。',
    'ap.theme.light': '浅色', 'ap.theme.dark': '深色', 'ap.theme.auto': '跟随系统',
    'ap.font': '字体风格', 'ap.fontD': '默认中英共用 MiSans；等宽更接近终端观感，衬线适合长文阅读。',
    'ap.font.default': '默认 · MiSans', 'ap.font.os': '系统原生', 'ap.font.mono': '等宽', 'ap.font.serif': '衬线',
    'ap.textSize': '文字大小', 'ap.textSizeD': '只缩放文字，控件尺寸不变。',
    'ap.size.s': '小', 'ap.size.m': '标准', 'ap.size.l': '大', 'ap.size.xl': '特大',
    'ap.zoom': '界面缩放', 'ap.zoomD': '整页等比缩放，含间距与图标。',
    'ap.width': '内容宽度', 'ap.widthD': '正文列最大宽度，窗口变窄时自动让位。',
    'ap.width.narrow': '窄', 'ap.width.medium': '中', 'ap.width.wide': '宽', 'ap.width.full': '全宽',
    'ap.grpLang': '语言', 'ap.grpLook': '观感', 'ap.grpPreview': '实时预览',
    'ap.grpSize': '界面尺寸', 'ap.reset': '恢复默认外观', 'ap.resetDone': '外观已恢复默认',
    'ap.pvTitle': '步骤标题', 'ap.pvBody': '智能体把产物写进本次运行的工作区。',
    'ap.pvCode': 'claude -p --output-format stream-json', 'ap.pvMeta': '03_RESEARCH · 12.4s · 0.0318',

    'eng.claude': 'Claude Code', 'eng.codex': 'Codex',
    'eng.default': '默认引擎', 'eng.defaultD': '步骤没指定引擎时使用它。',
    'eng.setDefault': '设为默认', 'eng.defaultTag': '默认',
    'eng.claudeD': 'Anthropic 兼容端点；stream-json 逐事件回传，技能走 --append-system-prompt-file。',
    'eng.codexD': 'OpenAI 兼容端点；exec --json，技能走工作区 AGENTS.md。',
    'eng.ready': '已就绪', 'eng.missing': '未检测到', 'eng.saved': '引擎配置已保存',
    'eng.ver': '版本 {v}', 'eng.need': '要求：{n}',
    'eng.grpEngines': '引擎', 'eng.grpBinary': '可执行文件',
    'eng.path': '可执行文件路径', 'eng.pathD': '留空则从 PATH 自动查找。',
    'eng.pathFor': '{e} 可执行文件',
    'eng.auto': '自动查找', 'eng.change': '更改', 'eng.pathPh': '填 claude / codex 的完整路径',

    'rt.grpPolicy': '执行策略',
    'rt.timeout': '单步超时', 'rt.timeoutD': '一步跑满这个秒数就终止该智能体进程树。',
    'rt.timeoutMin': '分钟',
    'rt.retry': '失败重试', 'rt.retryD': '某步报错时原地重跑几次再判定整条流程失败。',
    'rt.retryTimes': '{n} 次', 'rt.retryNone': '不重试',
    'rt.effort': '推理力度', 'rt.effortD': 'codex 引擎专用（model_reasoning_effort）；auto 沿用 CLI 自己的默认。',
    'rt.effort.auto': '自动', 'rt.effort.minimal': '最省', 'rt.effort.low': '较低',
    'rt.effort.medium': '中等', 'rt.effort.high': '最高',
    'pm.plan': '计划模式', 'pm.planD': '只出计划，不改文件',
    'pm.acceptEdits': '自动编辑', 'pm.acceptEditsD': '改文件不再逐个问',
    'pm.bypassPermissions': '完全访问', 'pm.bypassPermissionsD': '命令与写文件都不拦',
    'pm.nowGlobal': '权限模式已设为全局默认：{m}',
    'up.tUpToDate': '已经是最新版 v{v}',
    'pm.defaultNote': 'claude 全放行 / codex 沿用沙箱设置',
    'rt.auto': '自动越过检查点', 'rt.autoD': '开启后检查点不再暂停，整条流程一口气跑完；关闭时每到一个检查点等你确认。',

    'pre.desc': '填了就注入给智能体；全部留空则沿用该 CLI 在本机的登录与代理配置。',
    'pre.none': '还没有预设 —— 留空也能跑，智能体会用它自己的登录态。',
    'pre.grpList': '已配置的预设', 'pre.grpGate': '协议门槛',
    'pre.gate': '引擎与协议要配对', 'pre.gateD': 'claude 只吃 Anthropic 兼容端点，codex 只吃 OpenAI 兼容端点；不匹配的预设会被忽略并回落到 CLI 自身配置。',

    'dir.grpFolders': '目录',
    'dir.data': '数据目录', 'dir.dataD': '数据库与全部本机设置。',
    'dir.skills': '技能目录', 'dir.skillsD': '可编辑的技能正文，你自己新建或导入的技能都在这里',
    'dir.workspaces': '工作区目录', 'dir.workspacesD': '每次运行一个子目录，智能体在里面读写产物。',
    'dir.open': '打开',
    'dir.runs': '运行记录', 'dir.runsD': '本机累计 {n} 次运行，删除记录不会影响已生成的产物文件。',

    'sc.searchPh': '搜索键位…', 'sc.noHit': '没有匹配的键位',
    'sc.colKey': '按键绑定', 'sc.colCmd': '命令', 'sc.colScope': '作用域',
    'sc.scope.g': '全局', 'sc.scope.s': '设置页', 'sc.scope.i': '输入框',
    'sc.newTask': '新建任务', 'sc.settings': '打开设置', 'sc.close': '关闭弹窗 / 退出设置',
    'sc.search': '搜索流程与运行', 'sc.send': '运行台发送修订',
    'sc.toggleSb': '折叠 / 展开侧边栏', 'sc.switchTheme': '切换明暗主题',
    'sc.searchSettings': '聚焦设置搜索框',
    'sc.newTaskD': '回到首页输入台，直接开一条新流程。用浏览器打开时 Ctrl+N 和 Ctrl+Shift+N 都被浏览器自己占着（新窗口 / 隐身窗口），拦不下来 —— 那种情况下点侧栏「新建任务」那一行。',
    'sc.settingsD': '从任意页面跳到设置。', 'sc.closeD': '弹窗打开时优先关弹窗，一层一层来。',
    'sc.searchD': '在侧栏里按名字找流程或运行；用浏览器打开时 Ctrl+K 会被地址栏抢走，改用 Ctrl+Shift+K。',
    'sc.sendD': 'Shift+Enter 换行。',
    'sc.toggleSbD': '折叠态会记住，重启后还是那样。用浏览器打开时 Ctrl+B 和 Ctrl+Shift+B 都是浏览器的书签栏开关，拦不下来 —— 那种情况下点左上角的品牌位。',
    'sc.switchThemeD': '和设置里的「主题」是同一个开关，只是手快一点。',
    'sc.searchSettingsD': '只在设置页生效。',
    'sc.themeNow.dark': '已切到深色', 'sc.themeNow.light': '已切到浅色',

    'about.grpInfo': '版本与信息',
    'st.grpUsage': '执行量', 'st.grpFlows': '按工作流', 'st.grpClean': '残留',
    'st.tokTotal': '累计 Token 数', 'st.peakDay': '峰值单日', 'st.peakStep': '最长单步耗时',
    'st.streakNow': '当前连续天数', 'st.streakBest': '最长连续天数',
    'st.modeDay': '每日', 'st.modeWeek': '每周', 'st.modeCum': '累计',
    'st.range': '时间范围', 'st.last7': '近 7 日', 'st.last30': '近 30 日',
    'st.trend': '每日 Token 趋势图', 'st.trendAria': '最近用量柱状图',
    'st.models': '模型用量', 'st.noData': '还没有可展示的数据',
    'st.noDataD': '当前区间暂无可展示的用量数据。',
    'st.msgs': '轮消息', 'st.cumTo': '累计', 'st.noModelInjected': '未注入端点', 'st.others': '其他', 'st.donutAria': '按模型的 token 占比环图',
    'st.reloaded': '用量数据已刷新',
    'set.caps': 'Agent 能力',
    'set.capsD': '本机 claude 与 codex 各自的记忆、技能、命令、子智能体、MCP、钩子与插件 —— 只盘点，不改动。',
    'caps.title': '引擎', 'caps.note': '只读：这里只显示名字和条数。配置值（密钥、钩子命令）不离开那两个文件；要改请走各自的官方入口（claude mcp add / codex mcp add / /plugin）。',
    'caps.memory': '记忆', 'caps.skills': '技能', 'caps.commands': '命令', 'caps.agents': '子智能体',
    'caps.mcp': 'MCP 服务器', 'caps.hooks': '钩子', 'caps.plugins': '插件与市场',
    'caps.none': '这台机器上没有', 'caps.nameOnly': '只显示名字（值里可能就是密钥）',
    'caps.truncated': '文件较大，只显示开头一部分。',
    'caps.unsaved': '这份记忆还没保存，确定关掉吗？',
    'caps.memSaved': '记忆已保存',
    'st.heat': 'Token 活动',
    'st.tokens': '累计 Token', 'st.tokensD': '两个 CLI 自报的用量合计，缓存只算一次；软件不直连模型，拿不到就是 0。',
    'st.tokIO': '输入 / 输出', 'st.tokIOD': '输入是未命中缓存的那部分，输出是智能体真正写出的量。',
    'st.tokCache': '缓存读取', 'st.tokCacheD': '命中缓存的读取量，已从上面的输入里拆出来，不重复计。',
    'st.tokReason': '推理', 'st.tokReasonD': '思考链消耗，含在输出里、不另计进合计；只有支持的引擎才报。',
    'unit.yi': '亿', 'unit.wan': '万', 'unit.day': '天', 'unit.hour': '小时',
    'unit.min': '分钟', 'unit.sec': '秒',
    'mon.0': '1月', 'mon.1': '2月', 'mon.2': '3月', 'mon.3': '4月', 'mon.4': '5月', 'mon.5': '6月',
    'mon.6': '7月', 'mon.7': '8月', 'mon.8': '9月', 'mon.9': '10月', 'mon.10': '11月', 'mon.11': '12月',
    'st.runs': '运行次数', 'st.runsD': '成功 {done} · 失败 {failed} · 在跑 {running} · 等检查点 {waiting} · 已取消 {cancelled}',
    'st.steps': '步骤完成', 'st.stepsD': '{d} / {t} 步跑完',
    'st.tools': '工具调用', 'st.toolsD': '累计 {n} 次调用 · {t} 轮对话',
    'st.time': '智能体累计耗时', 'st.timeD': '所有步骤上报的执行时间之和',
    'st.cost': '累计费用', 'st.costD': '引擎回报的 USD，端点不同口径可能不准',
    'st.disk': '工作区占用', 'st.diskD': '{n} 个工作区目录',
    'st.perFlowD': '这条工作流被跑过的次数',
    'st.orphans': '孤立工作区', 'st.orphansD': '有目录但运行记录已删除，占着磁盘；删记录时工作区本应一起清掉',
    'st.none': '没有残留',
    'about.name': '应用', 'about.api': '本地服务',
    'about.counts': '内容统计', 'about.countsD': '技能 {s} · 流程 {p} · 运行 {r} · 预设 {pre}',
    'about.engines': '已检测引擎', 'about.enginesD': '{n}',
    'about.port': '端口 {p} · 只监听 127.0.0.1',

    'pr.add': '新增预设',
    'pr.editTitle': '编辑预设', 'pr.newTitle': '新增预设', 'pr.displayName': '显示名称',
    'pr.protocol': '协议', 'pr.base': 'API 端点 (Base URL)', 'pr.key': 'API Key',
    'pr.keyKeep': '（留空保留原 Key）', 'pr.model': '模型', 'pr.fetchModels': '获取模型列表',
    'pr.searchVendor': '搜索供应商…', 'pr.custom': '自定义预设', 'pr.inUse': '使用中',
    'pr.test': '检测连通',
    'pr.saveEdit': '保存修改', 'pr.saveNew': '创建预设', 'pr.created': '预设已创建', 'pr.saved': '已保存',
    'pr.deleted': '已删除', 'pr.delConfirm': '确定删除该预设？', 'pr.defaultSet': '已设为默认预设',
    'pr.testing': '正在检测连通…', 'pr.testOk': '连通正常{msg}', 'pr.testFail': '检测失败：{msg}',
    'pr.needName': '请填显示名称', 'pr.needBase': '请填 API 端点', 'pr.modelsLoaded': '已载入 {n} 个模型',
    'pr.modelsEmpty': '端点返回成功，但列表为空', 'pr.modelsFail': '获取失败：{err}',
    'pr.modelsFetching': '正在获取模型列表…', 'pr.baseHint': 'Anthropic 协议填 …/anthropic 形式；OpenAI 兼容填 …/v1 形式。',
    'pr.wireHint': 'codex 引擎用：responses（新）或 chat（兼容旧网关）',
  },
  en: {
    'brand.name': 'Jacquard', 'brand.sub': 'Local agent pipeline', 'brand.full': 'Jacquard',
    'ui.readFailed':'Some page data could not be loaded','ui.keepResults':'Previously displayed content is retained. An empty view does not mean no data. Check the local service and retry.','ui.retryRead':'Reload this page',
    'nav.workflows': 'Workflows', 'nav.skills': 'Skills', 'nav.runs': 'Runs', 'nav.settings': 'Settings',
    'nav.newTask': 'New task', 'sb.search': 'Search workflows and runs', 'sb.noHit': 'No matching workflow or run',
    'sb.liveN': '{n} running', 'sb.noLive': 'Nothing is running', 'sb.flows': 'Projects', 'sb.newFlow': 'New project',
    'time.now': 'now', 'time.m': '{n}m', 'time.h': '{n}h', 'time.d': '{n}d',
    'sb.noProject': 'No projects yet — run a workflow to start one',
    'sb.rowMore': 'More actions', 'sb.viewFiles': 'Show files', 'sb.newTaskHere': 'New task in this workflow',
    'sb.archive': 'Archive', 'sb.unarchive': 'Unarchive', 'sb.archived': 'Archived',
    'sb.showArchived': 'Show archived', 'sb.backToProjects': 'Back to projects',
    'sb.archivedEmpty': 'No archived workflows', 'sb.archivedToast': 'Archived “{name}”',
    'sb.unarchivedToast': 'Moved “{name}” back to projects', 'sb.noRunYet': 'This workflow has not run yet — nothing to show.',
    'sb.stepsN': '{n} steps', 'sb.toggle': 'Toggle sidebar',
    'win.min': 'Minimize', 'win.max': 'Maximize', 'win.restore': 'Restore', 'win.close': 'Close',
    'win.closeBusy': '{n} task(s) are running or paused at a checkpoint; closing the window takes them with it. Close anyway?',
    'foot.theme': 'Theme', 'foot.lang': 'Language', 'foot.engines': 'Agent engines',
    'up.grp': 'Updates', 'up.url': 'Update manifest URL', 'up.urlD': 'Leave empty to use the built-in COS latest.json — the download page reads the same file',
    'up.urlPh': 'https://…/latest.json', 'up.status': 'Update status', 'up.statusD': 'Running v{v}',
    'up.check': 'Check now', 'up.avail': 'Update', 'up.ready': 'Downloaded', 'up.failed': 'Update failed',
    'up.checking': 'Checking…', 'up.unknown': 'Unknown', 'up.idle': 'Not checked yet',
    'up.hasNew': 'New version v{v}', 'up.isCurrent': 'Up to date (v{v})',
    'up.downloadingPct': 'Downloading {p}%', 'up.saved': 'Saved, latest is v{v}', 'up.checked': '{s}',
    'up.tipAvail': 'v{v} available (you have v{cur}) — click to download',
    'up.tipDl': 'Downloading {got} / {size}', 'up.tipReady': 'Update downloaded — click to install', 'up.tipErr': 'Update error: {e}',
    'up.readyTip': 'Downloaded to {p}', 'up.errPrefix': 'Error: {e}',
    'up.reqFail': 'Update request failed',
    'up.tAvailable': 'New version v{v}', 'up.tDownloading': 'Downloading v{v}',
    'up.tReady': 'v{v} is ready', 'up.tFailed': 'Update did not go through',
    'up.nowOn': 'Currently v{v}', 'up.downloadNow': 'Start download', 'up.later': 'Later',
    'up.recheck': 'Check again', 'up.close': 'Close',
    'up.askApply': 'Install v{v} and restart now?',
    'up.askDownload': 'Start downloading v{v}',
    'up.askBusyQuit': '{n} task(s) are running or parked at a checkpoint — the restart interrupts them',
    'up.askBusyDl': '{n} task(s) are running; the download competes for bandwidth',
    'up.askGo': 'Install and restart',
    'up.apply': 'Install and restart',
    'up.applyD': 'Once downloaded the app installs the package and restarts; the installer closes the running Jacquard itself',
    'up.applyNo': 'Running from source — there is no executable to replace. Install the new setup package directly',
    'up.applyStarted': 'Installing and restarting…',

    'c.create': 'New workflow', 'c.edit': 'Edit', 'c.delete': 'Delete', 'c.duplicate': 'Duplicate',
    'c.save': 'Save', 'c.cancel': 'Cancel', 'c.close': 'Close', 'c.back': 'Back', 'c.view': 'View',
    'c.import': 'Import', 'c.export': 'Export', 'c.more': 'More actions', 'c.none': 'none', 'c.refresh': 'Refresh', 'c.steps': 'steps', 'c.justNow': 'just now',
    'c.minAgo': '{n} min ago', 'c.hourAgo': '{n} h ago', 'c.dayAgo': '{n} d ago',
    'c.download': 'Download',
    'c.words': '{n} chars', 'home.giveTask': 'Run task', 'home.mineEmpty': 'No workflow yet — create one from scratch, or import a shared JSON',
    'home.recentEmpty': 'No runs yet', 'home.engineNone': 'No agent engine',

    /* Bench (home) */
    'task.briefPh': 'Goal, context, material you already have, what the deliverable should look like.',
    'tk.greet': 'Which workflow should we run?',
    'tk.stepsAria': 'Steps in this workflow', 'tk.cpMark': 'This step pauses for your confirmation',
    'tk.noSteps': 'This workflow has no steps yet',
    'tk.modelAny': 'Follow steps', 'tk.modelAnyD': "Don't override; each step keeps its own endpoint",
    'task.labelPh': 'defaults to the workflow name', 'task.start': 'Run end to end',
    'task.needBrief': 'Task brief is required', 'task.started': 'Started', 'task.noFlow': 'No workflow yet — create one first',
    'task.dirPh': 'Working folder (blank = default workspace)',
    'task.dirTip': 'Only the agent\'s working directory changes — transcripts, artifacts and the system prompt still land in Jacquard\'s own run workspace. Claude supports it; codex reads AGENTS.md from its run directory to get the step instructions, so a custom folder is refused before the run starts.',

    'st.pending': 'Pending', 'st.running': 'Running', 'st.waiting': 'Awaiting', 'st.done': 'Done',
    'st.failed': 'Failed', 'st.cancelled': 'Cancelled', 'st.revising': 'Revising', 'run.stepOf': '{done} / {total} steps done',
    'run.checkpointWait': '· checkpoint awaiting confirmation', 'run.brief': 'Task brief',
    'run.briefSub': 'the basis of every step prompt',
    'run.artifacts': 'Workspace files', 'run.noArtifacts': 'No files yet — anything the agent writes shows up here', 
    'run.wsLive': 'live', 'run.wsOut': 'Deliverable', 'run.wsChg': 'just written',
    'run.workedIn': 'This run worked inside this folder; the list below is what our own workspace holds:',
    'run.wsBinary': 'This file type cannot be previewed in a browser — download it and open it in its own app.',
    'run.wsReveal': 'Show in folder', 'run.wsRevealFail': 'Could not open the folder',
    'run.wsRaw': 'Source', 'run.wsRendered': 'Preview', 'run.wsTrunc': '(first 400 KB only)',
    'run.wsLoading': 'Loading…', 'run.wsFail': 'Cannot read this file',
    'run.continue': 'Continue', 'run.stop': 'Stop', 'run.rerun': 'Rerun all', 'run.rerunFrom': 'Rerun from here',
    'run.rerunConfirm': 'Rerun from step {n} “{label}”?', 'run.rerunTail': '\nThe {n} following steps reset too.',
    'run.rerunDone': 'Re-running', 'run.send': 'Send change request',
    'run.reviseEmpty': 'Enter a change request', 'run.reviseDone': 'Rewrote “{label}” as requested',
    'run.reviseFail': '“{label}” could not be revised; the artifact was left as it is', 'run.deleted': 'Deleted',
    'run.delConfirm': 'Delete this run? Its workspace artifacts go too.', 'run.notFound': 'Run not found',
    'run.toolUnit': 'tool calls', 'run.moreLines': 'Expand {n} earlier trace lines',
    'run.runningOn': 'Running: {label}', 'run.composerPh': 'Describe the change, Enter to send…',
    'run.log': 'Log', 'run.logHint': 'Open this step’s raw agent transcript',
    'run.proc': 'Progress', 'run.procToggle': 'Collapse / expand the step list',
    'run.procPolicy': 'Panel expansion policy', 'run.procCollapse': 'Collapse to pill', 'run.procExpand': 'Expand',
    'run.policy.always': 'Always expanded', 'run.policy.idle': 'Collapse when the run finishes', 'run.policy.pill': 'Always a pill',
    'run.lgTitle': 'Agent transcript', 'run.lgLoading': 'Loading…', 'run.lgEmpty': 'This log is empty',
    'run.lgMeta': 'Tail', 'run.lgLines': 'lines', 'run.lgTrunc': 'large file truncated',
    'run.lgCopy': 'Copy raw', 'run.lgCopied': 'Raw transcript copied', 'run.lgCopyFail': 'Copy failed — select manually',
    'run.lgSys': 'START', 'run.lgTool': 'CALL', 'run.lgOut': 'SAY', 'run.lgRet': 'RET',
    'run.lgErr': 'ERR', 'run.lgEnd': 'END', 'run.lgRaw': 'RAW',
    'run.lgTools': 'tools', 'run.lgRetry': 'endpoint retry', 'run.lgTurns': 'turns',
    'run.lgExit': 'exit', 'run.lgOk': 'ok', 'run.lgFailed': 'failed',
    'run.durLong': '{m}m {s}s',

    'list.flows': 'Workflows', 'list.runned': 'Run', 'list.duplicateName': 'Copy name', 'list.deleteConfirm': 'Delete workflow “{name}”?',
    'list.copied': 'Created copy “{name}”',
    'list.imported': 'Imported workflow “{name}”', 'list.importBad': 'Not a workflow JSON: needs a name and at least one step',
    'list.importDup': '“{name}” already exists — import it as “{nn}”?', 'ed.newTitle': 'New workflow', 'ed.editTitle': 'Edit workflow', 'ed.basic': 'Basics',
    'ed.name': 'Id (lowercase, unique)', 'ed.label': 'Display name', 'ed.desc': 'Description',
    'ed.descPh': 'What is this workflow good for', 'ed.namePh': 'e.g. my-pipeline',
    'ed.nameHint': 'Immutable after creation; display name can change', 'ed.stepsTitle': 'Steps',
    'ed.stepsSub': 'Executed top to bottom', 'ed.addStep': 'Add step', 'ed.stepName': 'Step name',
    'ed.stepKey': 'Key', 'ed.keyHint': 'lowercase letters / digits / - / _', 'ed.keyDup': 'duplicate key',
    'ed.role': 'Role', 'ed.role.executor': 'Execute', 'ed.role.reviewer': 'Review', 'ed.role.editor': 'Edit',
    'ed.roleHint.executor': 'Main execution step: produces the file', 'ed.roleHint.reviewer': 'Reviews upstream output, lists issues',
    'ed.roleHint.editor': 'Improves an existing artifact', 'ed.mainSkill': 'Main skill', 'ed.viewSkills': 'Browse skills',
    'ed.src.loom': 'Jacquard', 'ed.src.claude': 'Claude', 'ed.src.codex': 'Codex',
    'ed.extHint': 'Referenced by name — Jacquard neither copies nor rewrites this skill.',
    'ed.lostSkill': 'This skill is no longer in Jacquard\'s own folder.',
    'ed.out': 'Artifact file', 'ed.outPh': 'e.g. ANALYSIS.md', 'ed.outHint': 'written to the workspace for later steps',
    'ed.advanced': 'Advanced', 'ed.engine': 'Engine', 'ed.engineDefault': 'Default',
    'ed.engineHint': 'empty = the default engine in Settings', 'ed.engineNone': 'No CLI agent detected — check Settings first',
    'ed.engineReady': 'ready: {list}', 'ed.model': 'Model for this step', 'ed.modelFollow': 'Follow default preset',
    'ed.modelPreset': 'preset: {name}', 'ed.modelRaw': '{model} (raw id)',
    'ed.modelHint': 'A preset name swaps the whole endpoint; a model id rides on the default endpoint',
    'ed.extraSkills': 'Stacked skills', 'ed.addSkill': 'Add…', 'ed.stepExtra': 'Extra requirement',
    'ed.stepExtraPh': 'Constraints for this step only, above the skill spec',
    'ed.stepExtraHint': 'Goes into this step’s prompt; the skill text stays untouched',
    'ed.checkpoint': 'Manual checkpoint', 'ed.checkpointHint': 'Pause after this step until I confirm',
    'ed.preview': 'Preview prompt', 'ed.previewSub': 'See what this step actually sends',
    'ed.previewTitle': 'Prompt actually sent by step {n}', 'ed.previewSystem': 'System spec (full skill)',
    'ed.previewUser': 'User instruction (brief + contract)', 'ed.goSkill': 'Edit this skill',
    'ed.previewBriefPh': 'Type a brief for the preview (optional):', 'ed.save': 'Save workflow',
    'ed.saved': 'Workflow saved', 'ed.unsavedLeave': 'This workflow has unsaved changes. Leave anyway?', 'ed.needName': 'Enter a workflow id', 'ed.needLabel': 'Step {n} has no name',
    'ed.needKey': 'Step {n}: key “{key}” is invalid', 'ed.needSkill': 'Step {n} “{label}” has no main skill',
    'ed.notFound': 'Workflow not found', 'ed.unsavedPreview': 'Save the workflow before previewing',
    'ed.moveUp': 'Up', 'ed.moveDown': 'Down', 'ed.delStep': 'Delete step', 'ed.newStep': 'Step {n}',

    'sk.title': 'Skills', 'sk.new': 'New skill', 'sk.empty': 'No skill yet — create one, or import a standard skill package (zip / SKILL.md)',
    'sk.importing': 'Importing “{name}”…',
    'sk.imported': 'Imported “{name}”', 'sk.importFail': 'Import failed: {err}',
    'sk.newTitle': 'New skill', 'sk.editTitle': 'Edit skill',
    'sk.nameField': 'Skill id (lowercase, referenced by steps)', 'sk.namePh': 'e.g. my-review-checklist',
    'sk.nameHint': 'lowercase letters / digits / - / _', 'sk.content': 'Content (Markdown)',
    'sk.contentPh': '# My skill\n\n## Goal\nwhat this step produces…\n\n## Hard rules\n- must…',
    'sk.lines': '{n} lines · effective on save', 'sk.save': 'Save skill', 'sk.saved': 'Skill saved',
    'sk.created': 'Skill created', 'sk.needName': 'Enter a skill id', 'sk.needContent': 'Content cannot be empty',
    'sk.dupe': 'Save a copy',
    'sk.dupeName': 'Copy id (lowercase)', 'sk.dupeDone': 'Created a copy “{name}”',
    'sk.delConfirm': 'Delete skill “{name}”? Steps referencing it will find nothing.', 'sk.deleted': 'Deleted',
    'sk.empty2': 'empty',

    'set.title': 'Settings', 'set.back': 'Back to app', 'set.search': 'Search settings…', 'set.noHit': 'No matching settings',
    'set.hits': '{n} sections matched',
    'set.grp.pref': 'Preferences', 'set.grp.exec': 'Execution', 'set.grp.data': 'Data',
    'set.appearance': 'Appearance', 'set.engines': 'Agent engines', 'set.presets': 'API access',
    'set.runtime': 'Runtime', 'set.dirs': 'Local folders', 'set.about': 'About',
    'set.stats': 'Usage', 'set.update': 'Updates',
    'set.shortcuts': 'Keyboard',
    'set.appearanceD': '',
    'set.enginesD': 'Every step runs through a local CLI agent — this is where the engines live.',
    'set.presetsD': 'Endpoints and keys are injected into the agent; there is no direct model channel.',
    'set.runtimeD': 'Execution policy shared by every step of a run.',
    'set.dirsD': 'Everything stays on this machine; there is no cloud copy.',
    'set.aboutD': '',
    'set.shortcutsD': 'Global keys, active even while a text field has focus.',
    'set.chipEngines': '{n} engines available', 'set.chipNone': 'No engine detected',
    'set.statsD': 'Time, tool calls and cumulative cost for every run live here.',
    'set.updateD': 'Checks for updates, downloads the installer and verifies its checksum.',

    'ap.language': 'Language', 'ap.languageD': 'UI copy only; skill bodies and prompts stay as written.',
    'ap.theme': 'Theme', 'ap.themeD': 'System follows the Windows light/dark setting live.',
    'ap.theme.light': 'Light', 'ap.theme.dark': 'Dark', 'ap.theme.auto': 'System',
    'ap.font': 'Font style', 'ap.fontD': 'Mono reads more like a terminal; serif suits long reading.',
    'ap.font.default': 'Default · MiSans', 'ap.font.os': 'System native', 'ap.font.mono': 'Mono', 'ap.font.serif': 'Serif',
    'ap.textSize': 'Text size', 'ap.textSizeD': 'Scales text only, controls keep their size.',
    'ap.size.s': 'S', 'ap.size.m': 'M', 'ap.size.l': 'L', 'ap.size.xl': 'XL',
    'ap.zoom': 'UI zoom', 'ap.zoomD': 'Scales the whole page, spacing and icons included.',
    'ap.width': 'Content width', 'ap.widthD': 'Max width of the text column; yields when the window narrows.',
    'ap.width.narrow': 'Narrow', 'ap.width.medium': 'Medium', 'ap.width.wide': 'Wide', 'ap.width.full': 'Full',
    'ap.grpLang': 'Language', 'ap.grpLook': 'Look', 'ap.grpPreview': 'Live preview',
    'ap.grpSize': 'Interface size', 'ap.reset': 'Reset appearance', 'ap.resetDone': 'Appearance restored to defaults',
    'ap.pvTitle': 'Step title', 'ap.pvBody': 'The agent writes artifacts into this run’s workspace.',
    'ap.pvCode': 'claude -p --output-format stream-json', 'ap.pvMeta': '03_RESEARCH · 12.4s · 0.0318',

    'eng.claude': 'Claude Code', 'eng.codex': 'Codex',
    'eng.default': 'Default engine', 'eng.defaultD': 'Used by steps that do not pick one.',
    'eng.setDefault': 'Set default', 'eng.defaultTag': 'Default',
    'eng.claudeD': 'Anthropic-compatible endpoint; stream-json events, skill via --append-system-prompt-file.',
    'eng.codexD': 'OpenAI-compatible endpoint; exec --json, skill via the workspace AGENTS.md.',
    'eng.ready': 'Ready', 'eng.missing': 'Not detected', 'eng.saved': 'Engine config saved',
    'eng.ver': 'version {v}', 'eng.need': 'needs: {n}',
    'eng.grpEngines': 'Engines', 'eng.grpBinary': 'Executables',
    'eng.path': 'Binary path', 'eng.pathD': 'Leave empty to auto-detect from PATH.',
    'eng.pathFor': '{e} binary',
    'eng.auto': 'Auto-detect', 'eng.change': 'Change', 'eng.pathPh': 'full path to claude / codex',

    'rt.grpPolicy': 'Execution policy',
    'rt.timeout': 'Step timeout', 'rt.timeoutD': 'Kill the agent process tree once a step runs this long.',
    'rt.timeoutMin': 'min',
    'rt.retry': 'Retry on failure', 'rt.retryD': 'How many times a failed step is retried before the whole run fails.',
    'rt.retryTimes': '{n}×', 'rt.retryNone': 'No retry',
    'rt.effort': 'Reasoning effort', 'rt.effortD': 'codex only (model_reasoning_effort); auto keeps the CLI default.',
    'rt.effort.auto': 'Auto', 'rt.effort.minimal': 'Minimal', 'rt.effort.low': 'Low',
    'rt.effort.medium': 'Medium', 'rt.effort.high': 'High',
    'pm.plan': 'Plan', 'pm.planD': 'plans only, edits nothing',
    'pm.acceptEdits': 'Auto-edit', 'pm.acceptEditsD': 'edits without asking each time',
    'pm.bypassPermissions': 'Full access', 'pm.bypassPermissionsD': 'no command or write checks',
    'pm.nowGlobal': 'Permission mode set as the global default: {m}',
    'up.tUpToDate': 'Already on the latest version v{v}',
    'pm.defaultNote': 'claude bypasses checks / codex keeps its sandbox setting',
    'rt.auto': 'Skip checkpoints', 'rt.autoD': 'When on, checkpoints never pause and the whole run goes through in one shot; when off each checkpoint waits for you.',

    'pre.desc': 'Values get injected into the agent; leave everything empty to reuse the CLI’s own login.',
    'pre.none': 'No preset yet — leaving it empty still works, the agent uses its own login.',
    'pre.grpList': 'Configured presets', 'pre.grpGate': 'Protocol gate',
    'pre.gate': 'Engine and protocol must match', 'pre.gateD': 'claude takes Anthropic endpoints only, codex takes OpenAI-compatible ones; a mismatched preset is ignored and the CLI falls back to its own config.',

    'dir.grpFolders': 'Folders',
    'dir.data': 'Data folder', 'dir.dataD': 'Database and all local settings.',
    'dir.skills': 'Skills folder', 'dir.skillsD': 'Editable skill bodies — everything you create or import lands here',
    'dir.workspaces': 'Workspace folder', 'dir.workspacesD': 'One subfolder per run; the agent reads and writes artifacts there.',
    'dir.open': 'Open',
    'dir.runs': 'Run history', 'dir.runsD': '{n} runs on this machine; deleting a record never touches its artifacts.',

    'sc.searchPh': 'Search shortcuts…', 'sc.noHit': 'No matching shortcuts',
    'sc.colKey': 'Binding', 'sc.colCmd': 'Command', 'sc.colScope': 'Scope',
    'sc.scope.g': 'Global', 'sc.scope.s': 'Settings', 'sc.scope.i': 'Text field',
    'sc.newTask': 'New task', 'sc.settings': 'Open settings', 'sc.close': 'Close dialog / leave settings',
    'sc.search': 'Search workflows and runs', 'sc.send': 'Send a revision from the run console',
    'sc.toggleSb': 'Collapse / expand the sidebar', 'sc.switchTheme': 'Switch light / dark theme',
    'sc.searchSettings': 'Focus settings search',
    'sc.newTaskD': 'Back to the home composer to start a run. In a browser both Ctrl+N and Ctrl+Shift+N belong to the browser (new window / incognito) and cannot be intercepted — use the New task row in the sidebar instead.',
    'sc.settingsD': 'Jumps to settings from any page.', 'sc.closeD': 'Closes the topmost dialog first.',
    'sc.searchD': 'Finds workflows and runs by name. In a browser the address bar keeps Ctrl+K — use Ctrl+Shift+K.',
    'sc.sendD': 'Shift+Enter inserts a newline.',
    'sc.toggleSbD': 'Remembered across restarts. In a browser Ctrl+B and Ctrl+Shift+B toggle the bookmarks bar and cannot be intercepted — use the brand button at the top left.',
    'sc.switchThemeD': 'The same switch as "Theme" in settings, just one keystroke closer.',
    'sc.searchSettingsD': 'Settings page only.',
    'sc.themeNow.dark': 'Switched to dark', 'sc.themeNow.light': 'Switched to light',

    'about.grpInfo': 'Version and info',
    'st.grpUsage': 'Execution', 'st.grpFlows': 'Per workflow', 'st.grpClean': 'Leftovers',
    'st.tokTotal': 'Total tokens', 'st.peakDay': 'Peak day', 'st.peakStep': 'Longest step',
    'st.streakNow': 'Current streak', 'st.streakBest': 'Best streak',
    'st.modeDay': 'Daily', 'st.modeWeek': 'Weekly', 'st.modeCum': 'Cumulative',
    'st.range': 'Time range', 'st.last7': 'Last 7 days', 'st.last30': 'Last 30 days',
    'st.trend': 'Daily token trend', 'st.trendAria': 'Recent usage bar chart',
    'st.models': 'Model usage', 'st.noData': 'Nothing to show yet',
    'st.noDataD': 'No usage data in this range.',
    'st.msgs': 'messages', 'st.cumTo': 'Cumulative', 'st.noModelInjected': 'no endpoint injected', 'st.others': 'Others',
    'st.donutAria': 'Token share by model, donut chart',
    'st.reloaded': 'Usage data refreshed',
    'set.caps': 'Agent capabilities',
    'set.capsD': 'What your local claude and codex each have — memory, skills, commands, subagents, MCP servers, hooks, plugins. Inventory only, nothing is written.',
    'caps.title': 'Engine', 'caps.note': 'Read-only: names and counts only. Config values (credentials, hook commands) never leave those files — change them through the official entry points (claude mcp add / codex mcp add / /plugin).',
    'caps.memory': 'Memory', 'caps.skills': 'Skills', 'caps.commands': 'Commands', 'caps.agents': 'Subagents',
    'caps.mcp': 'MCP servers', 'caps.hooks': 'Hooks', 'caps.plugins': 'Plugins & marketplaces',
    'caps.none': 'Not on this machine', 'caps.nameOnly': 'Name only — the value may hold credentials',
    'caps.truncated': 'Large file — showing the beginning only.',
    'caps.unsaved': 'This memory file has unsaved edits. Close anyway?',
    'caps.memSaved': 'Memory saved',
    'st.heat': 'Token activity',
    'st.tokens': 'Total tokens', 'st.tokensD': 'Summed from what the CLIs report, cache counted once. Jacquard never calls a model, so nothing reported counts as 0.',
    'st.tokIO': 'Input / output', 'st.tokIOD': 'Input is the uncached part; output is what the agent actually wrote.',
    'st.tokCache': 'Cache read', 'st.tokCacheD': 'Cache hits, split out of the input above so they are never counted twice.',
    'st.tokReason': 'Reasoning', 'st.tokReasonD': 'Chain-of-thought spend. Already inside output, not added again; only engines that report it.',
    'unit.yi': 'B', 'unit.wan': 'K', 'unit.day': 'd', 'unit.hour': 'h',
    'unit.min': 'm', 'unit.sec': 's',
    'mon.0': 'Jan', 'mon.1': 'Feb', 'mon.2': 'Mar', 'mon.3': 'Apr', 'mon.4': 'May', 'mon.5': 'Jun',
    'mon.6': 'Jul', 'mon.7': 'Aug', 'mon.8': 'Sep', 'mon.9': 'Oct', 'mon.10': 'Nov', 'mon.11': 'Dec',
    'st.runs': 'Runs', 'st.runsD': '{done} done · {failed} failed · {running} running · {waiting} at checkpoint · {cancelled} cancelled',
    'st.steps': 'Steps finished', 'st.stepsD': '{d} of {t} steps completed',
    'st.tools': 'Tool calls', 'st.toolsD': '{n} calls · {t} agent turns',
    'st.time': 'Total agent time', 'st.timeD': 'Sum of the execution time each step reported',
    'st.cost': 'Total cost', 'st.costD': 'USD as reported by the engine; providers differ',
    'st.disk': 'Workspace on disk', 'st.diskD': '{n} workspace folders',
    'st.perFlowD': 'Times this workflow has been run',
    'st.orphans': 'Orphan workspaces', 'st.orphansD': 'Folders whose run record is gone but the directory stayed',
    'st.none': 'Nothing left over',
    'about.name': 'App', 'about.api': 'Local server',
    'about.counts': 'Content', 'about.countsD': '{s} skills · {p} workflows · {r} runs · {pre} presets',
    'about.engines': 'Detected engines', 'about.enginesD': '{n}',
    'about.port': 'port {p} · bound to 127.0.0.1 only',

    'pr.add': 'New preset',
    'pr.editTitle': 'Edit preset', 'pr.newTitle': 'New preset', 'pr.displayName': 'Display name',
    'pr.protocol': 'Protocol', 'pr.base': 'API base URL', 'pr.key': 'API key',
    'pr.keyKeep': '(empty keeps the current key)', 'pr.model': 'Model', 'pr.fetchModels': 'Fetch models',
    'pr.searchVendor': 'Search providers…', 'pr.custom': 'Custom preset', 'pr.inUse': 'In use',
    'pr.test': 'Test',
    'pr.saveEdit': 'Save changes', 'pr.saveNew': 'Create preset', 'pr.created': 'Preset created', 'pr.saved': 'Saved',
    'pr.deleted': 'Deleted', 'pr.delConfirm': 'Delete this preset?', 'pr.defaultSet': 'Default preset set',
    'pr.testing': 'Testing connection…', 'pr.testOk': 'Connection ok{msg}', 'pr.testFail': 'Test failed: {msg}',
    'pr.needName': 'Enter a display name', 'pr.needBase': 'Enter an API base URL', 'pr.modelsLoaded': 'Loaded {n} models',
    'pr.modelsEmpty': 'Endpoint answered, but the list is empty', 'pr.modelsFail': 'Fetch failed: {err}',
    'pr.modelsFetching': 'Fetching model list…', 'pr.baseHint': 'Anthropic protocol wants …/anthropic; OpenAI-compatible wants …/v1.',
    'pr.wireHint': 'For the codex engine: responses (new) or chat (legacy gateways)',
  },
};

let LANG = 'zh';

/* ---------------- 行内图标 ----------------
   统一形状语言：24 网格、内容落在 3–21 安全区、1.7 描边、圆头圆角、纯描边；
   需要实心点的地方挂 class="f"（由 .ic .f 打开填充），不混用两种画法。 */
const ICONS = {
  /* 导航与分区 */
  flow:     '<circle cx="5.6" cy="6" r="2.5"/><circle cx="5.6" cy="18" r="2.5"/><circle cx="18.4" cy="12" r="2.5"/><path d="M7.9 7.2 16.1 10.8M7.9 16.8 16.1 13.2"/>',
  skill:    '<path d="M7.2 3.6h9.6a1.6 1.6 0 0 1 1.6 1.6v15.2l-6.4-3.9-6.4 3.9V5.2a1.6 1.6 0 0 1 1.6-1.6z"/>',
  runs:     '<circle cx="12" cy="12" r="8.5"/><path d="M12 7v5.2l3.4 2"/>',
  settings: '<path d="M20.87 9.95 A9.1 9.1 0 0 1 20.87 14.05 L18.82 13.57 A7.0 7.0 0 0 1 17.94 15.71 L19.72 16.82 A9.1 9.1 0 0 1 16.82 19.72 L15.71 17.94 A7.0 7.0 0 0 1 13.57 18.82 L14.05 20.87 A9.1 9.1 0 0 1 9.95 20.87 L10.43 18.82 A7.0 7.0 0 0 1 8.29 17.94 L7.18 19.72 A9.1 9.1 0 0 1 4.28 16.82 L6.06 15.71 A7.0 7.0 0 0 1 5.18 13.57 L3.13 14.05 A9.1 9.1 0 0 1 3.13 9.95 L5.18 10.43 A7.0 7.0 0 0 1 6.06 8.29 L4.28 7.18 A9.1 9.1 0 0 1 7.18 4.28 L8.29 6.06 A7.0 7.0 0 0 1 10.43 5.18 L9.95 3.13 A9.1 9.1 0 0 1 14.05 3.13 L13.57 5.18 A7.0 7.0 0 0 1 15.71 6.06 L16.82 4.28 A9.1 9.1 0 0 1 19.72 7.18 L17.94 8.29 A7.0 7.0 0 0 1 18.82 10.43 Z"/><circle cx="12" cy="12" r="3"/>',
  appearance:'<circle cx="12" cy="12" r="8.5"/><path d="M12 3.5v17M14.7 8.2h3.1M14.7 12h3.9M14.7 15.8h3.1"/>',
  bolt:     '<path d="M13.4 2.9 5.7 13.5h5.1l-1 7.6 7.5-10.9h-5z"/>',
  api:      '<circle cx="8.2" cy="12" r="4.2"/><path d="M12.4 12h8.4M17.2 12v3.4M14.6 12v2.4"/>',
  runtime:  '<path d="M3.8 7.4h8.6M17.4 7.4h2.8M3.8 16.6h2.8M11.4 16.6h8.8"/><circle cx="14.8" cy="7.4" r="2.4"/><circle cx="8.6" cy="16.6" r="2.4"/>',
  keyboard: '<rect x="2.6" y="6.4" width="18.8" height="11.2" rx="2.6"/><path d="M6.4 10h.01M9.6 10h.01M12.8 10h.01M16 10h.01M8.4 14h7.2"/>',
  folder:   '<path d="M3.4 7.2a2 2 0 0 1 2-2h3.4l2.2 2.6h7.6a2 2 0 0 1 2 2V17a2 2 0 0 1-2 2H5.4a2 2 0 0 1-2-2z"/>',
  info:     '<circle cx="12" cy="12" r="8.5"/><path d="M12 11.2v5M12 7.9h.01"/>',

  /* 动作 */
  plus:     '<path d="M12 5.2v13.6M5.2 12h13.6"/>',
  play:     '<path d="M8 5.2 18.6 12 8 18.8z"/>',
  stop:     '<rect x="6.6" y="6.6" width="10.8" height="10.8" rx="2.6"/>',
  send:     '<path d="M4.6 12.2 20 4.8l-5.2 15-2.8-6z"/>',
  arrowUp:  '<path d="M12 19.4V5.2M6.2 11 12 5.2 17.8 11"/>',
  check:    '<path d="M4.8 12.6 9.6 17.4 19.2 6.8"/>',
  close:    '<path d="M6.4 6.4 17.6 17.6M17.6 6.4 6.4 17.6"/>',
  refresh:  '<path d="M20.2 12a8.2 8.2 0 1 1-2.5-5.9"/><path d="M20.6 4v4.6H16"/>',
  retry:    '<path d="M3.8 12a8.2 8.2 0 1 0 2.5-5.9"/><path d="M3.4 4v4.6H8"/>',
  edit:     '<path d="M4 20h4.2L19.4 8.8a2.4 2.4 0 0 0-3.4-3.4L4.8 16.6z"/><path d="M15 6.6 18 9.6"/>',
  trash:    '<path d="M4.4 7h15.2M9.6 7V4.6h4.8V7M6.4 7l.9 12.4A1.7 1.7 0 0 0 9 21h6a1.7 1.7 0 0 0 1.7-1.6L17.6 7"/>',
  copy:     '<rect x="9" y="9" width="11.6" height="11.6" rx="2.4"/><path d="M15.8 5.8a2.4 2.4 0 0 0-2.4-2.4H6.2a2.4 2.4 0 0 0-2.4 2.4v7.2a2.4 2.4 0 0 0 2.4 2.4"/>',
  download: '<path d="M12 3.8v11M7.2 10.4 12 15.2l4.8-4.8M4.4 19.8h15.2"/>',
  eye:      '<path d="M2.6 12S6 5.8 12 5.8 21.4 12 21.4 12 18 18.2 12 18.2 2.6 12 2.6 12z"/><circle cx="12" cy="12" r="2.8"/>',
  search:   '<circle cx="10.8" cy="10.8" r="6.5"/><path d="M15.6 15.6 20.6 20.6"/>',
  link:     '<path d="M10.2 13.8a4.4 4.4 0 0 0 6.2 0l2.6-2.6a4.4 4.4 0 1 0-6.2-6.2l-1.3 1.3"/><path d="M13.8 10.2a4.4 4.4 0 0 0-6.2 0l-2.6 2.6a4.4 4.4 0 1 0 6.2 6.2l1.3-1.3"/>',
  external: '<path d="M14 4.4h5.6V10M19.6 4.4 11.4 12.6M17.4 13.2v5.2a1.8 1.8 0 0 1-1.8 1.8H5.6a1.8 1.8 0 0 1-1.8-1.8V8.2a1.8 1.8 0 0 1 1.8-1.8h5.2"/>',
  terminal: '<rect x="2.6" y="4" width="18.8" height="16" rx="2.6"/><path d="M6.6 9.6 10.4 13l-3.8 3.4M12.8 16.6h5"/>',
  more:     '<path d="M5.6 12h.01M12 12h.01M18.4 12h.01"/>',
  expand:   '<path d="M14 5h5v5M19 5l-6.6 6.6M10 19H5v-5M5 19l6.6-6.6"/>',
  collapse: '<path d="M19.4 9.6h-5v-5M14.4 4.6l5 5M4.6 14.4h5v5M9.6 19.4l-5-5"/>',
  share:    '<circle cx="17.6" cy="5.8" r="2.5"/><circle cx="6.4" cy="12" r="2.5"/><circle cx="17.6" cy="18.2" r="2.5"/><path d="M8.6 10.8 15.4 7M8.6 13.2l6.8 3.8"/>',
  panel:    '<rect x="3.2" y="4.6" width="17.6" height="14.8" rx="2.6"/><path d="M14.6 4.6v14.8"/>',
  /* 无边框窗口的三枚：24 网格、1.7 描边，和其余线性图标同一套。
     最小化是一根 12 长的横线、最大化是一个 12×12 方框、还原是错位的双框。 */
  winMin:   '<path d="M6 12h12"/>',
  winMax:   '<rect x="6" y="6" width="12" height="12" rx="1.6"/>',
  winRestore:'<rect x="8.4" y="5.6" width="10" height="10" rx="1.4"/><path d="M5.6 8.4v10h10"/>',
  save:     '<path d="M5.6 4.4h9.6l4.4 4.4v10a1.8 1.8 0 0 1-1.8 1.8H5.6a1.8 1.8 0 0 1-1.8-1.8V6.2a1.8 1.8 0 0 1 1.8-1.8z"/><path d="M8 4.4v5h6.4v-5M8 20.6v-5.4h8v5.4"/>',
  import:   '<path d="M12 3.6v10.6M7.6 10 12 14.4 16.4 10M4 16.4v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2"/>',

  /* 方向 */
  chevron:  '<path d="M6.4 9.4 12 15l5.6-5.6"/>',
  chevronUp:'<path d="M6.4 14.6 12 9l5.6 5.6"/>',
  chevronRight:'<path d="M9.4 6.4 15 12l-5.6 5.6"/>',
  chevronLeft:'<path d="M14.6 6.4 9 12l5.6 5.6"/>',
  arrowRight:'<path d="M4.4 12h15M14 6.6 19.4 12 14 17.4"/>',

  /* 状态 */
  checkCircle:'<circle cx="12" cy="12" r="8.5"/><path d="M8.2 12.4 11 15.2l5-5.8"/>',
  circle:   '<circle cx="12" cy="12" r="8.5"/>',
  dotCircle:'<circle cx="12" cy="12" r="8.5"/><circle cx="12" cy="12" r="3.2" class="f" stroke="none"/>',
  warn:     '<path d="M12 3.6 21.5 20.2H2.5z"/><path d="M12 9.6v4.6M12 17.4h.01"/>',
  flag:     '<path d="M6 20.8V3.8M6 4.6h11.6l-2.1 4.2 2.1 4.2H6"/>',
  shield:   '<path d="M12 3.2 19.8 6v5.6c0 4.4-3.1 7.6-7.8 9.2-4.7-1.6-7.8-4.8-7.8-9.2V6z"/>',
  timer:    '<circle cx="12" cy="13.6" r="7.2"/><path d="M12 10v3.8l2.6 1.8M9.4 2.8h5.2M19.4 5.6 21 7.2"/>',
  spark:    '<path d="M12 3.4 13.9 8.1 18.6 10 13.9 11.9 12 16.6 10.1 11.9 5.4 10 10.1 8.1z"/><path d="M18.4 15.2 19.3 17.4 21.5 18.3 19.3 19.2 18.4 21.4 17.5 19.2 15.3 18.3 17.5 17.4z"/>',

  /* 数据对象 */
  file:     '<path d="M13.6 3.4H7.4a2 2 0 0 0-2 2v13.2a2 2 0 0 0 2 2h9.2a2 2 0 0 0 2-2V8.2z"/><path d="M13.6 3.4v4.8h4.8"/>',
  artifact: '<path d="M12 3 20.4 7.5v9L12 21 3.6 16.5v-9z"/><path d="M3.6 7.5 12 12l8.4-4.5M12 12v9"/>',
  layers:   '<path d="M12 3.4 21 8l-9 4.6L3 8z"/><path d="M3 12.4 12 17l9-4.6M3 16.4 12 21l9-4.6"/>',
  agent:    '<rect x="3.8" y="8" width="16.4" height="11.4" rx="3"/><path d="M12 4.2V8M8.8 13h.01M15.2 13h.01M9.6 16.4h4.8"/><circle cx="12" cy="3.2" r="1.3"/>',
  branch:   '<circle cx="6.6" cy="5.6" r="2.4"/><circle cx="6.6" cy="18.4" r="2.4"/><circle cx="17.4" cy="8.4" r="2.4"/><path d="M6.6 8v8M6.6 12.6h5.2a5.6 5.6 0 0 0 5.6-4.2"/>',
  target:   '<circle cx="12" cy="12" r="8.4"/><circle cx="12" cy="12" r="4.2"/><path d="M12 11.4a.6.6 0 1 0 0 1.2.6.6 0 0 0 0-1.2z" class="f" stroke="none"/>',
  grip:     '<path d="M9.2 6h.01M14.8 6h.01M9.2 12h.01M14.8 12h.01M9.2 18h.01M14.8 18h.01"/>',
  package:  '<path d="M3.6 8.4 12 4l8.4 4.4v7.2L12 20l-8.4-4.4z"/><path d="M3.6 8.4 12 12.8l8.4-4.4M12 12.8V20"/>',

  /* 观感选项 */
  sun:      '<circle cx="12" cy="12" r="4.2"/><path d="M12 2.8v2.4M12 18.8v2.4M2.8 12h2.4M18.8 12h2.4M5.5 5.5l1.7 1.7M16.8 16.8l1.7 1.7M18.5 5.5l-1.7 1.7M7.2 16.8l-1.7 1.7"/>',
  moon:     '<path d="M20.2 14.6A8.8 8.8 0 0 1 9.4 3.8 8.8 8.8 0 1 0 20.2 14.6z"/>',
  type:     '<path d="M5.2 19.4 12 4.6l6.8 14.8M8.2 14.4h7.6"/>',
  lang:     '<path d="M3.4 6.6h9.2M7.2 4.4v2.2M9.6 6.6C9 10.8 6.6 13.4 3.6 14.8M5.6 10.8c1.2 2.4 3.2 4 5.6 4.8"/><path d="M12.6 20.6 16.6 11l4 9.6M14.2 17.2h4.8"/>',
  help:     '<circle cx="12" cy="12" r="8.5"/><path d="M9.5 9.5a2.5 2.5 0 0 1 4.9.8c0 1.7-2.4 2.1-2.4 3.7M12 17.4h.01"/>',
  spinner:  '<path d="M12 3.4a8.6 8.6 0 1 1-6.1 2.5"/>',
  pause:    '<path d="M9.4 5v14M14.6 5v14"/>',
  chart:    '<path d="M4.2 20h15.6"/><path d="M7.6 20v-5.4M12 20v-9.6M16.4 20v-13.2"/>',
  bell:     '<path d="M18 8.6a6 6 0 1 0-12 0c0 5.6-2.2 7.4-2.2 7.4h16.4S18 14.2 18 8.6z"/><path d="M13.7 20.2a2 2 0 0 1-3.4 0"/>',
  tool:     '<path d="M20.4 5.6a5 5 0 0 1-6.6 6.6L6.2 19.8a2.2 2.2 0 0 1-3.1-3.1l7.6-7.6a5 5 0 0 1 6.6-6.6l-3.2 3.2.1 3.1 3.1.1z"/>',
};
function icon(name, cls) {
  const d = ICONS[name] || ICONS.tool;
  return `<svg class="ic ${cls||''}" viewBox="0 0 24 24" aria-hidden="true">${d}</svg>`;
}
window.ICON_NAMES = Object.keys(ICONS);
window.icon = icon;

function t(key, params) {
  /* 有意留空的描述（某些分区不要副标题）必须真的渲染成空，
     用 || 取字典会把空串当缺失、直接把 key 吐到页面上。 */
  const zh = DICT.zh, cur = DICT[LANG];
  let s = (cur && key in cur) ? cur[key] : (zh && key in zh) ? zh[key] : key;
  if (params) {
    for (const k in params) s = s.split('{' + k + '}').join(String(params[k]));
  }
  return s;
}

const THEMES = ['light', 'dark', 'auto'];
const FONTS = ['default', 'os', 'mono', 'serif'];
const TEXT_SIZES = { s: 0.92, m: 1, l: 1.12, xl: 1.26 };
const ZOOMS = { '90%': 0.9, '100%': 1, '110%': 1.1, '125%': 1.25 };
const WIDTHS = { narrow: '900px', medium: '1180px', wide: '1440px', full: 'none' };

const APP = {
  lang: 'zh', theme: 'dark', font: 'default',
  textSize: 'm', uiZoom: '100%', contentWidth: 'medium', sidebar: 'expanded',
  procPanel: 'idle',
};

function applyAppearance() {
  const html = document.documentElement;
  let theme = APP.theme;
  if (theme === 'auto') {
    theme = (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) ? 'dark' : 'light';
  }
  html.dataset.theme = theme;
  html.dataset.font = APP.font;
  html.dataset.sidebar = APP.sidebar === 'collapsed' ? 'collapsed' : 'expanded';
  html.lang = APP.lang === 'en' ? 'en' : 'zh-CN';
  html.style.setProperty('--text-scale', String(TEXT_SIZES[APP.textSize] || 1));
  html.style.setProperty('--ui-zoom', String(ZOOMS[APP.uiZoom] || 1));
  html.style.setProperty('--content-w', WIDTHS[APP.contentWidth] || '1180px');
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta) meta.content = theme === 'dark' ? '#161616' : '#F8F8F8';
  LANG = APP.lang;
  document.title = t('brand.full');
  const bn = document.getElementById('brandName');
  if (bn) bn.textContent = t('brand.name');
}

/* 只改内存 + 重绘，不落盘：滑块 oninput 走这里，拖动过程不该刷 8 个请求。 */
function previewAppearance(patch) {
  Object.assign(APP, patch || {});
  applyAppearance();
}

function setAppearance(patch) {
  Object.assign(APP, patch || {});
  applyAppearance();
  if (window.__FF_APPEARANCE) Object.assign(window.__FF_APPEARANCE, patch || {});
  const body = {};
  for (const k in patch) body['ui_' + k] = String(patch[k]);
  return fetch('/api/settings/bulk', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  }).then(r => r.json()).catch(() => ({}));
}

function loadAppearance() {
  if (window.__FF_BOOT) {
    return window.__FF_BOOT.then(() => {
      Object.assign(APP, window.__FF_APPEARANCE || {});
      applyAppearance();
      return APP;
    });
  }
  return fetch('/api/settings').then(r => r.ok ? r.json() : {}).then(s => {
    ['lang', 'theme', 'font', 'textSize', 'uiZoom', 'contentWidth', 'sidebar', 'procPanel'].forEach(k => {
      if (s['ui_' + k]) APP[k] = s['ui_' + k];
    });
    applyAppearance();
    return APP;
  }).catch(() => { applyAppearance(); return APP; });
}

/* 极简 markdown → HTML：先整体转义再按行拼，不引第三方解析器。
   只覆盖步骤产物里真会出现的几样：标题 / 围栏代码 / 行内码 / 粗斜体 / 链接 /
   列表 / 表格 / 引用 / 分隔线。链接只放 http(s) 和站内绝对路径，防 javascript:。 */
function mdToHtml(src) {
  /* 引号必须转。这个 e() 以前只转 & < >，而链接那条把 URL 直接塞进 href 属性里 ——
     智能体（或它读的远端资料）产出一个带双引号的 URL 就能逃出那个属性，
     在标签上挂任意事件处理器。全站没有 CSP，产物面板和记忆预览是同一个 sink。 */
  const e = s => String(s == null ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  const inline = s => e(s)
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\*\*([^*]+)\*\*/g, '<b>$1</b>')
    .replace(/(^|[^\w*])\*([^*\n]+)\*(?=[^\w*]|$)/g, '$1<i>$2</i>')
    .replace(/\[([^\]]+)\]\((https?:\/\/[^\s)"']+|\/[^\s)"']*)\)/g,
      '<a href="$2" target="_blank" rel="noopener">$1</a>');
  const lines = String(src == null ? '' : src).replace(/\r\n/g, '\n').split('\n');
  const out = [];
  let list = null, para = [], fence = null, table = null;
  const flushPara = () => { if (para.length) { out.push('<p>' + para.map(inline).join('<br>') + '</p>'); para = []; } };
  const flushList = () => { if (list) { out.push(`<${list.tag}>` + list.items.map(x => `<li>${inline(x)}</li>`).join('') + `</${list.tag}>`); list = null; } };
  const flushTable = () => {
    if (!table) return;
    const cells = r => r.replace(/^\s*\||\|\s*$/g, '').split('|').map(c => c.trim());
    const head = cells(table[0]);
    const body = table.slice(table.length > 1 && /^[\s|:-]+$/.test(table[1]) ? 2 : 1);
    out.push('<table><thead><tr>' + head.map(c => `<th>${inline(c)}</th>`).join('') + '</tr></thead><tbody>'
      + body.map(r => '<tr>' + cells(r).map(c => `<td>${inline(c)}</td>`).join('') + '</tr>').join('')
      + '</tbody></table>');
    table = null;
  };
  for (const ln of lines) {
    if (fence !== null) {
      if (/^```/.test(ln)) { out.push('<pre><code>' + e(fence.join('\n')) + '</code></pre>'); fence = null; }
      else fence.push(ln);
      continue;
    }
    if (/^```/.test(ln)) { flushPara(); flushList(); flushTable(); fence = []; continue; }
    if (/^\s*\|.*\|\s*$/.test(ln)) { flushPara(); flushList(); (table = table || []).push(ln); continue; }
    flushTable();
    const h = /^(#{1,4})\s+(.*)$/.exec(ln);
    if (h) { flushPara(); flushList(); const n = h[1].length + 2; out.push(`<h${n}>${inline(h[2])}</h${n}>`); continue; }
    if (/^\s*([-*_])\s*\1\s*\1[\s\-*_]*$/.test(ln)) { flushPara(); flushList(); out.push('<hr>'); continue; }
    const q = /^>\s?(.*)$/.exec(ln);
    if (q) { flushPara(); flushList(); out.push('<blockquote>' + inline(q[1]) + '</blockquote>'); continue; }
    const ul = /^\s*[-*+]\s+(.*)$/.exec(ln);
    const ol = /^\s*\d+[.)]\s+(.*)$/.exec(ln);
    if (ul || ol) {
      flushPara();
      const tag = ul ? 'ul' : 'ol';
      if (!list || list.tag !== tag) { flushList(); list = { tag, items: [] }; }
      list.items.push((ul || ol)[1]);
      continue;
    }
    flushList();
    if (!ln.trim()) { flushPara(); continue; }
    para.push(ln);
  }
  flushPara(); flushList();
  if (fence !== null) out.push('<pre><code>' + e(fence.join('\n')) + '</code></pre>');
  return out.join('\n');
}

if (window.matchMedia) {
  const mq = window.matchMedia('(prefers-color-scheme: dark)');
  const on = () => { if (APP.theme === 'auto') applyAppearance(); };
  if (mq.addEventListener) mq.addEventListener('change', on);
  else if (mq.addListener) mq.addListener(on);
}

window.t = t;
window.APP = APP;
window.applyAppearance = applyAppearance;
window.setAppearance = setAppearance;
window.previewAppearance = previewAppearance;
window.loadAppearance = loadAppearance;
window.mdToHtml = mdToHtml;
window.AP_OPTS = { THEMES, FONTS, TEXT_SIZES, ZOOMS, WIDTHS };
})();
