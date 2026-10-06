/* ==========================================================================
 * Loom 织流 · 外壳与视图
 * 路由：#/home 工作流控制台 · #/skills 技能库 · #/runs 运行记录 · #/settings 设置
 * 文案全部走 window.t()，外观（语言/明暗/字体/字号/缩放/宽度）走 window.APP
 * ========================================================================== */
(() => {
'use strict';

/* ---------------- 工具 ---------------- */
const $ = s => document.querySelector(s);
const t = window.t;
function esc(s){ return String(s==null?'':s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;'); }
/* 往内联事件里塞字符串参数要转义两次（HTML 属性 + JS 字面量）；弹窗打开时锁背景滚动。
   这两个原来在 editor.js / run.js 各有一份，现在统一从这里走。 */
const jsq = s => String(s==null?'':s).replace(/\\/g,'\\\\').replace(/"/g,'&quot;').replace(/'/g,"\\'");
window.jsq = jsq;
const _lockScroll = on => { document.body.style.overflow = on ? 'hidden' : ''; };
window._lockScroll = _lockScroll;

async function api(path, opts){
  if (!opts || !opts.method || opts.method === 'GET') return window.voyraRead(path, opts);
  const r = await fetch(path, opts);
  const ct = r.headers.get('content-type')||'';
  if(ct.includes('application/json')) return r.json();
  if(!r.ok) throw new Error('HTTP '+r.status);
  return r.text();
}
function post(path, data){
  return api(path, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(data||{})});
}
function put(path, data){
  return api(path, {method:'PUT', headers:{'Content-Type':'application/json'}, body:JSON.stringify(data||{})});
}
function del(path){ return api(path, {method:'DELETE'}); }

let toastTimer=null;
function toast(msg, ok=false){
  const el = $('#toast');
  if(!el) return;
  el.textContent = msg||'';
  el.className = 'toast show '+(ok?'ok':'err');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(()=>{ el.className='toast'; }, 2600);
}
window.ffToast = toast;

function relDate(str){
  if(!str) return '';
  const d = new Date(str.replace(' ', 'T'));
  if(isNaN(d)) return str;
  const diff = (Date.now()-d.getTime())/1000;
  if(diff < 60) return t('c.justNow');
  if(diff < 3600) return t('c.minAgo',{n:Math.floor(diff/60)});
  if(diff < 86400) return t('c.hourAgo',{n:Math.floor(diff/3600)});
  if(diff < 86400*30) return t('c.dayAgo',{n:Math.floor(diff/86400)});
  return str.slice(0,10);
}
window.ffRelDate = relDate;

/* ---------------- 状态 ---------------- */
const ST = { agents:[], defaultEngine:'',
             claudeCli:'', codexCli:'', paths:{},
             agentTimeout:'2700', effortOptions:['auto'], permMode:'',
             reasoningEffort:'auto', stepRetry:'0', autoContinue:'0',
             skills:[], flows:[], runs:[], caps:null, version:'',
             liveRuns:0,
             presets:null };   /* 端点预设清单，首页模型 chip 的候选；进过设置页会刷新 */
window.ST = ST;

const RUN_ST = () => ({pending:t('st.pending'), running:t('st.running'), waiting:t('st.waiting'),
  done:t('st.done'), failed:t('st.failed'), cancelled:t('st.cancelled'), revising:t('st.revising')});
window.RUN_ST = RUN_ST;
const ENG_ZH = () => ({claude:t('eng.claude'), codex:t('eng.codex')});
window.ENGINE_LABEL = e => (e ? ((ENG_ZH()[e]||e)) : t('ed.engineDefault'));

/* ---------------- 外壳：侧栏 / 顶栏 ---------------- */
const ico = window.icon;

function renderNav(active){
  /* 五行：两行动作（新建任务 / 搜索）+ 三条路由。设置走左下角入口；工作台已并入输入台。
     动作行必须是 <button>，路由行必须是带真 href 的 <a>：
     没 href 的 <a> 拿不到键盘焦点，Tab 会直接跳过整条主导航。
     aria-label 是因为折叠轨道会把 <span> 整个 display:none 掉，折上就没了可访问名。 */
  const items = [
    {id:'newTask',   icon:'plus',   label:t('nav.newTask'),  chord:chordOf('newTask'),  act:'taskModal'},
    {id:'search',    icon:'search', label:t('sb.search'),    chord:chordOf('search'),   act:'sbSearch', row:'sbSearchRow'},
    {id:'pipelines', icon:'flow',   label:t('nav.workflows')},
    {id:'skills',    icon:'skill',  label:t('nav.skills')},
    {id:'runs',      icon:'runs',   label:t('nav.runs')},
  ];
  const html = items.map(n=>{
    const inner = `${ico(n.icon)}<span>${esc(n.label)}</span>`
      + (n.chord ? `<span class="sb-kbd">${esc(n.chord)}</span>` : '');
    const tip = `data-tip-any="1" data-tip="${esc(n.label)}" aria-label="${esc(n.label)}"`;
    if(n.act){
      return `<button class="sb-item" type="button" ${tip}
        ${n.row?`id="${n.row}"`:''} onclick="${n.act}()">${inner}</button>`;
    }
    return `<a class="sb-item ${n.id===active?'active':''}" href="#/${n.id}" data-v="${n.id}" ${tip}
      ${n.id===active?'aria-current="page"':''}>${inner}</a>`;
  }).join('');
  const box = $('#mainNav');
  if(box && box.dataset.sig !== html){ box.innerHTML = html; box.dataset.sig = html; }
  paintBrand();
  /* 换语言时这两处的文案没人刷：它们不在 renderNav 的重绘链上，只在启动 / 轮询里写 */
  paintFootMe(); paintUpdate();
}

/* 折叠开关。它原来长在侧栏顶部（品牌位就是它，一个控件两件事），
   无边框之后搬到标题行右侧，和窗口按钮同排 —— 品牌位退回纯标识。 */
function paintBrand(){
  const b = $('#tbCollapse'); if(!b) return;
  const collapsed = document.documentElement.dataset.sidebar === 'collapsed';
  b.innerHTML = ico('panel');
  b.dataset.tip = t('sb.toggle');
  b.setAttribute('aria-expanded', collapsed ? 'false' : 'true');
  b.setAttribute('aria-label', t('sb.toggle'));
}
window.sbToggle = async function(){
  const cur = document.documentElement.dataset.sidebar === 'collapsed';
  await window.setAppearance({sidebar: cur ? 'expanded' : 'collapsed'});
  hideTip(); paintBrand();
};

/* ---------------- 窗口外壳（无边框标题行右侧那三枚） ----------------
   只有 pywebview 把 bridge 注进来才出现：浏览器里那三枚按不动的按钮是骗人的，
   而关掉标签就等于关窗口，本来也不需要它们。 */
let SHELL_OK = false, SHELL_MAX = false;
function shellApi(fn){
  const api = window.pywebview && window.pywebview.api;
  return (SHELL_OK && api && typeof api[fn] === 'function') ? api[fn].bind(api) : null;
}
function shellCall(fn, ...args){
  const f = shellApi(fn);
  return f ? Promise.resolve(f(...args)) : Promise.resolve(null);
}
function paintShell(){
  const box = $('#tbWin'); if(!box) return;
  box.hidden = !SHELL_OK;
  const set = (id, html, tip) => {
    const e = document.getElementById(id);
    if(e){ e.innerHTML = html; e.dataset.tip = tip; e.setAttribute('aria-label', tip); }
  };
  set('winMin', ico('winMin'), t('win.min'));
  set('winMax', ico(SHELL_MAX ? 'winRestore' : 'winMax'),
      t(SHELL_MAX ? 'win.restore' : 'win.max'));
  set('winClose', ico('close'), t('win.close'));
  /* 最大化时八个拉边手柄也必须跟着藏：窗口铺满屏幕本来就拉不动，
     留着它们等于一排按不动的假控件（pointerdown 里那道 SHELL_MAX 判断
     只挡住动作，挡不住"看着能按"）。 */
  const rz = $('#rzLayer'); if(rz) rz.hidden = !SHELL_OK || SHELL_MAX;
  document.documentElement.dataset.shell = SHELL_OK ? 'native' : '';
}
async function syncShell(){
  const s = await shellCall('win_state');
  SHELL_MAX = !!(s && s.maximized);
  paintShell();
}
window.winMin = () => { shellCall('win_minimize'); };
window.winMaxToggle = async () => { await shellCall('win_maximize_toggle'); await syncShell(); };
window.winClose = async () => {
  /* 读的是 liveRuns —— 以前这里读的是另一个从没被赋值过的名字，于是那个条件恒假、
     n 恒 0：有任务在跑时关窗口从来不弹确认，直接杀掉正在跑的智能体。
     名字对不上不会报错，只会静默失效，所以有一条测试全局禁那个拼法。 */
  const n = (ST.liveRuns !== undefined) ? ST.liveRuns : 0;
  if(n > 0 && !(await window.ffAsk({danger:true, title:t('win.closeTitle'),
      body:t('win.closeBusy', {n}), ok:t('win.closeOk')}))) return;
  await shellCall('win_close');
};
window.addEventListener('pywebviewready', () => { SHELL_OK = true; syncShell(); });

/* Win+↑、贴边快照、拖动到屏幕顶这些系统途径进来的最大化不经过我们的按钮，
   SHELL_MAX 就停在旧值上（图标还是"最大化"、拉边手柄还露着）。窗口尺寸一变
   WebView2 就跟着变，resize 是这些变化唯一都会经过的信号；重新获得焦点再兜一次。
   拖边框会连发几十个 resize，所以合并成一个尾巴上的调用。 */
let shellSyncTimer = 0;
function syncShellSoon(){
  if(shellSyncTimer) clearTimeout(shellSyncTimer);
  shellSyncTimer = setTimeout(() => { shellSyncTimer = 0; syncShell(); }, 100);
}
window.addEventListener('resize', syncShellSoon);
window.addEventListener('focus', syncShellSoon);

/* 双击标题行的空白处 = 最大化/还原。easy_drag 只管拖，不管这一下，得自己接。 */
function shellDragBind(){
  document.querySelectorAll('.pywebview-drag-region').forEach(el => {
    if(el.dataset.dbldbl) return;
    el.dataset.dbldbl = '1';
    el.addEventListener('dblclick', (e) => {
      if(e.target.closest('button')) return;
      window.winMaxToggle();
    });
  });
}

/* 八方向拉边：pywebview 的 frameless 把可拉的边框一起去掉了，
   所以页面上铺八个透明手柄，按下后把目标尺寸发给 shell，
   由 Python 侧按对侧那个角钉住位置。最小尺寸和后端建窗的 min_size 同一个数。 */
const RZ_MIN_W = 980, RZ_MIN_H = 620;
function shellResizeBind(){
  const layer = $('#rzLayer'); if(!layer || layer.dataset.bound) return;
  layer.dataset.bound = '1';
  layer.querySelectorAll('.rz').forEach(h => {
    h.addEventListener('pointerdown', (e) => {
      if(!SHELL_OK || SHELL_MAX) return;
      const edge = h.dataset.edge;
      const sx = e.screenX, sy = e.screenY, w0 = window.outerWidth, h0 = window.outerHeight;
      h.setPointerCapture(e.pointerId);
      const move = (ev) => {
        const dx = ev.screenX - sx, dy = ev.screenY - sy;
        let w = w0 + (edge.includes('e') ? dx : edge.includes('w') ? -dx : 0);
        let hh = h0 + (edge.includes('s') ? dy : edge.includes('n') ? -dy : 0);
        shellCall('win_resize', Math.max(RZ_MIN_W, Math.round(w)),
                  Math.max(RZ_MIN_H, Math.round(hh)), edge);
      };
      const up = () => {
        h.removeEventListener('pointermove', move);
        h.removeEventListener('pointerup', up);
        h.removeEventListener('pointercancel', up);
        syncShell();
      };
      h.addEventListener('pointermove', move);
      h.addEventListener('pointerup', up);
      h.addEventListener('pointercancel', up);
    });
  });
}

/* ---------------- 悬停提示 ----------------
   原生 title 有一秒延迟、样式跟着系统，折叠成轨道后全靠它补标签不够用。
   带 data-tip-any 的（只有图标的按钮）两种宽度下都提示，其余只在轨道下提示，
   免得展开时给本来就写着文字的行再糊一层。 */
let TIP_EL = null;
function tipWants(el){
  return el.dataset.tip && el.matches('[data-tip-any], html[data-sidebar="collapsed"] [data-tip]');
}
function showTip(el){
  const tip = $('#ffTip'); if(!tip) return;
  tip.textContent = el.dataset.tip; tip.hidden = false;
  const r = el.getBoundingClientRect(), b = tip.getBoundingClientRect();
  const rail = document.documentElement.dataset.sidebar==='collapsed' && el.closest('.sidebar');
  let left = rail ? r.right + 8 : r.left;
  let top  = rail ? r.top + r.height/2 - b.height/2 : r.bottom + 6;
  // 贴底的那一排（热力图最后一行）往下放就出屏了，翻到格子上方
  if (!rail && top + b.height > window.innerHeight - 8) top = r.top - b.height - 6;
  left = Math.max(8, Math.min(left, window.innerWidth - b.width - 8));
  top  = Math.max(8, Math.min(top, window.innerHeight - b.height - 8));
  tip.style.left = left + 'px'; tip.style.top = top + 'px';
}
function hideTip(){ TIP_EL = null; const tip = $('#ffTip'); if(tip) tip.hidden = true; }
function tipHover(el){
  if(!el || !tipWants(el)){ if(TIP_EL) hideTip(); return; }
  if(el === TIP_EL) return;
  TIP_EL = el; showTip(el);
}
document.addEventListener('pointerover', (e)=>{
  tipHover(e.target && e.target.closest ? e.target.closest('[data-tip]') : null);
});
document.addEventListener('focusin', (e)=>{
  tipHover(e.target && e.target.closest ? e.target.closest('[data-tip]') : null);
});
document.addEventListener('focusout', hideTip);
document.addEventListener('pointerdown', hideTip);
window.addEventListener('blur', hideTip);
window.addEventListener('scroll', hideTip, true);

/* 顶栏：视图渲染时写 window.__chrome，由 paintChrome 落地 */
window.__chrome = {title:'', icon:'flow', actions:''};
function paintChrome(){
  const c = window.__chrome || {title:'', icon:'flow'};
  const bar = document.querySelector('.topbar');
  /* 没标题也没动作就把整条收掉：首页的页头是空的，留 52px 只放一个图标，
     看着像坏了的占位。运行台/列表页都有标题，不受影响。 */
  const empty = !(c.title||'').trim() && !(c.actions||'').trim();
  if(bar){ bar.hidden = empty; }
  if(empty) return;
  const tt = $('#tbTitle');
  if(tt) tt.innerHTML = `${ico(c.icon||'flow')}<span>${esc(c.title||'')}</span>`;
  const ta = $('#tbActions');
  if(ta) ta.innerHTML = c.actions||'';
}
window.paintChrome = paintChrome;

/* 侧栏下半区：全部流程 + 最近运行（Codex 的「项目 / 最近」分组） */
const RUN_ICON = {
  running:  {ic:'spinner', cls:'sb-live',   sp:1},
  revising: {ic:'spinner', cls:'sb-live',   sp:1},
  waiting:  {ic:'pause',   cls:'sb-wait',   sp:0},
  failed:   {ic:'warn',    cls:'sb-bad',    sp:0},
  done:     {ic:'',        cls:'',          sp:0},
  cancelled:{ic:'',        cls:'',          sp:0},
  pending:  {ic:'circle',  cls:'sb-idle',   sp:0},
};

/* 库里的时间串是 "%Y-%m-%d %H:%M:%S" 本地时间（app/db.py:23），不带时区，
   所以 new Date("2026-09-22 11:04:03") 这种写法不能依赖 —— 手工拆字段。
   四档阈值抄参考实现（taskListItemPresentation.ts:33-53）：不给月/年档。 */
function parseLdb(iso){
  const m = /^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2}):(\d{2})/.exec(iso||'');
  return m ? new Date(+m[1], +m[2]-1, +m[3], +m[4], +m[5], +m[6]).getTime() : NaN;
}
function relUnit(iso, now){
  const mins = Math.floor(((now==null ? Date.now() : now) - parseLdb(iso)) / 60000);
  if(!(mins >= 0)) return {s:0, u:'now'};     // 时间戳在未来（时钟没同步）也当"刚刚"，别印 -5 分
  if(mins < 1)  return {s:0, u:'now'};
  if(mins < 60) return {s:mins, u:'m'};
  const hrs = Math.floor(mins/60);
  if(hrs < 24)  return {s:hrs, u:'h'};
  return {s:Math.floor(hrs/24), u:'d'};
}
window.relTime = (iso, now) => {
  const r = relUnit(iso, now);
  return r.u === 'now' ? t('time.now') : t('time.'+r.u, {n:r.s});
};

let SB_ARCH = false;      /* 侧栏「项目」这一栏当前看的是未归档还是已归档（切换钮和行菜单都读它） */

async function renderSidebarLists(){
  const box = $('#sbLists');
  if(!box) return;
  const [pr, rr] = await Promise.all([
    api('/api/pipelines').catch(()=>({pipelines:[]})),
    api('/api/runs?limit=30').catch(()=>({runs:[]})),
  ]);
  const flows = (pr.pipelines||[]).filter(p=>p.runs>0);   /* 项目 = 真跑过的流程 */
  const runs = rr.runs||[];
  ST.sbFlows = pr.pipelines||[]; ST.sbRuns = runs;
  const cur = (location.hash.split('/')[2]||'');
  const live = runs.filter(u=>u.status==='running'||u.status==='revising'||u.status==='waiting').length;
  ST.liveRuns = live;   /* 关窗口前要知道有没有活着的运行，标题行那三枚按钮用 */

  const proj = flows.filter(p=>!p.archived);
  /* 归档列表必须走同一个 flows 口径：否则「没跑过的流程」从没在侧栏出现过，
     却在归档视图里凭空冒出来。能归档的前提是它先是一行。 */
  const arch = flows.filter(p=>p.archived);
  /* run 嵌在自己那条流程下面（参考实现按工作空间分组），不再另起一组「最近运行」：
     同一次运行在侧栏出现两次就是两个入口管一件事。每组最多两条，侧栏是入口不是清单。 */
  const byFlow = {};
  runs.forEach(u => { (byFlow[u.pipeline] = byFlow[u.pipeline] || []).push(u); });
  const sub = (u) => {
    const m = RUN_ICON[u.status] || RUN_ICON.pending;
    return `<a class="sb-run sb-sub ${u.id===cur?'active':''}" href="#/run/${esc(u.id)}"
      data-tip="${esc(u.label||u.pipeline)}" aria-label="${esc(u.label||u.pipeline)}"
      ${u.id===cur?'aria-current="page"':''}>
      <span class="sb-rico ${m.cls}">${m.ic?(m.sp?ico(m.ic,'sp'):ico(m.ic)):'&nbsp;'}</span>
      <span class="sb-rname">${esc(u.label||u.pipeline)}</span>
      <span class="sb-rtag">${esc(relTime(u.created_at))}</span></a>`;
  };
  const row = (p) => {
    const kids = (byFlow[p.name] || []).slice(0, 2);
    return `<div class="sb-row">
      <a class="sb-run ${p.name===cur?'active':''}"
        href="#/pipeline-edit/${esc(p.name)}" data-tip="${esc(p.label||p.name)}"
        aria-label="${esc(p.label||p.name)}"
        ${p.name===cur?'aria-current="page"':''}>
        <span class="sb-rico">${ico('flow')}</span>
        <span class="sb-rname">${esc(p.label||p.name)}</span></a>
      <button class="sb-more" data-tip-any="1" data-tip="${esc(t('sb.rowMore'))}"
          aria-label="${esc(t('sb.rowMore'))}"
          onclick="sbRowMore(event,'${jsq(p.name)}')">${ico('more')}</button>
    </div>` + (kids.length ? `<div class="sb-runlist">${kids.map(sub).join('')}</div>` : '');
  };
  /* 归档清空后切换钮必须还在 —— 否则人就困在「已归档」这一栏里出不来了。 */
  const garch = (arch.length || SB_ARCH) ? `<button class="sb-garch" data-tip-any="1"
      data-tip="${esc(SB_ARCH ? t('sb.backToProjects') : t('sb.showArchived'))}"
      aria-label="${esc(SB_ARCH ? t('sb.backToProjects') : t('sb.showArchived'))}"
      aria-pressed="${SB_ARCH ? 'true' : 'false'}"
      onclick="sbToggleArchived()">${ico('package')}${SB_ARCH ? '' : `<span class="sb-badge">${arch.length}</span>`}</button>` : '';
  /* 在跑计数挂在分组标题上（参考实现：计数只在组头，行里放状态点和时间） */
  let html = `<div class="sb-group"><span>${esc(SB_ARCH ? t('sb.archived') : t('sb.flows'))}</span>
      ${live?`<span class="sb-gcount">${live}</span>`:''}
      ${garch}
      <button class="sb-gadd" data-tip-any="1" data-tip="${esc(t('sb.newFlow'))}"
        aria-label="${esc(t('sb.newFlow'))}"
        onclick="nav.go('pipeline-edit/new')">${ico('plus')}</button></div>`
    + (SB_ARCH
        ? (arch.length ? arch.map(row).join('')
                       : `<div class="sb-empty">${esc(t('sb.archivedEmpty'))}</div>`)
        : (proj.length ? proj.map(row).join('')
                       : `<div class="sb-empty">${esc(t('sb.noProject'))}</div>`));
  if(box.dataset.sig !== html){ box.innerHTML = html; box.dataset.sig = html; }
  const ab = $('#sbActBtn');
  if(ab){ ab.innerHTML = ico('bell') + (live?`<span class="sb-badge">${live}</span>`:'');
          ab.classList.toggle('on', !!live);
          ab.dataset.tip = live? t('sb.liveN',{n:live}) : t('sb.noLive');
          ab.setAttribute('aria-label', ab.dataset.tip); }
}

/* 侧栏搜索：流程 + 运行一起找 */
function sbHit(label, sub, onPick, icon){
  return `<button class="sb-fi" onclick="${onPick}"><span class="sb-rico">${ico(icon)}</span>
    <span class="sb-fmain"><b>${esc(label)}</b><i>${esc(sub)}</i></span></button>`;
}
window.sbSearch = function(e){
  if(e) e.stopPropagation();
  const p = document.getElementById('sbFind');
  if(!p) return;
  if(!p.hidden){ p.hidden = true; return; }
  const draw = (q)=>{
    const k = (q||'').trim().toLowerCase();
    const fl = (ST.sbFlows||[]).filter(x=>!k || ((x.label||'')+' '+x.name).toLowerCase().includes(k));
    const ru = (ST.sbRuns||[]).filter(x=>!k || ((x.label||'')+' '+x.pipeline).toLowerCase().includes(k));
    const body = (fl.length||ru.length)
      ? fl.slice(0,6).map(x=>sbHit(x.label||x.name, t('sb.stepsN',{n:(x.steps||[]).length}),
            `sbGo('pipeline-edit/${jsq(x.name)}')`, 'flow')).join('')
        + ru.slice(0,6).map(x=>sbHit(x.label||x.pipeline, RUN_ST()[x.status]||x.status,
            `sbGo('run/${jsq(x.id)}')`, 'runs')).join('')
      : `<div class="sb-empty">${esc(t('sb.noHit'))}</div>`;
    p.innerHTML = `<div class="sb-fbox">${ico('search')}
        <input id="sbFQ" placeholder="${esc(t('sb.search'))}" value="${esc(q||'')}"
          oninput="sbSearchType(this.value)"></div>
       <div class="sb-fres">${body}</div>`;
  };
  window.sbSearchType = (v)=>{ const q=document.getElementById('sbFQ'); const pos=q?q.selectionStart:0;
    draw(v); const n=document.getElementById('sbFQ'); n.focus(); try{n.setSelectionRange(pos,pos);}catch(_){} };
  window.sbGo = (hash)=>{ p.hidden = true; nav.go(hash); };
  draw('');
  p.hidden = false;
  const src = document.getElementById('sbSearchRow') || document.querySelector('.sb-nav');
  const r = src.getBoundingClientRect();
  p.style.left = Math.max(8, r.left - 4) + 'px';
  p.style.top = (r.bottom + 6) + 'px';
  setTimeout(()=>{ const n=document.getElementById('sbFQ'); if(n) n.focus(); }, 30);
};

window.sbActivity = function(e){
  if(e) e.stopPropagation();
  const p = document.getElementById('sbFind');
  if(p && !p.hidden){ p.hidden = true; }
  const runs = (ST.sbRuns||[]).filter(u=>u.status!=='done'&&u.status!=='cancelled');
  nav.go(runs.length ? 'run/'+runs[0].id : 'runs');
};
window.renderSidebarLists = renderSidebarLists;

async function loadAgents(){
  const r = await api('/api/agents').catch(()=>null);
  if(!r) return;
  /* 开机就要读权限模式：输入台那枚 chip 在启动时就渲染，
     以前只有进过一次设置页才同步，于是服务端是 plan、chip 显示「默认」。 */
  ST.permMode = r.permission_mode||'';
  ST.agents = r.agents||[];
  ST.defaultEngine = r.default_engine||'';
  ST.claudeCli = r.claude_cli||'';
  ST.codexCli = r.codex_cli||'';
  const ready = ST.agents.filter(a=>a.found);
  paintFootMe(ready);
}
window.loadAgents = loadAgents;

/* ---------------- 左下角配置浮层 ---------------- */
function paintFootMe(ready){
  const el = document.getElementById('sbMeName');
  if(!el) return;
  ready = ready || ST.agents.filter(a=>a.found);
  el.textContent = ready.length ? ready.map(a=>a.engine).join(' · ')
                                : t('home.engineNone');
  const av = document.getElementById('sbMeAv');
  if(av){ av.innerHTML = ico('settings'); }
  const me = document.getElementById('sbMe');
  if(me){ me.dataset.tip = t('nav.settings'); me.setAttribute('aria-label', t('nav.settings')); }
  const ch = document.getElementById('sbMeChev');
  if(ch) ch.innerHTML = ico('chevronUp');
}
function footRows(){
  const A = window.APP;
  const ready = ST.agents.filter(a=>a.found);
  return `
    <button class="sb-prow" onclick="footCycle('theme')">${ico('appearance')}
      <span>${esc(t('foot.theme'))}</span>
      <span class="sb-pv">${esc(t('ap.theme.'+A.theme))}</span>${ico('chevronRight','ic-chev')}</button>
    <button class="sb-prow" onclick="footCycle('lang')">${ico('lang')}
      <span>${esc(t('foot.lang'))}</span>
      <span class="sb-pv">${esc(A.lang==='en'?'English':'简体中文')}</span>${ico('chevronRight','ic-chev')}</button>
    <button class="sb-prow" onclick="closeFootMenu();nav.go('settings','engines')">${ico('agent')}
      <span>${esc(t('foot.engines'))}</span>
      <span class="sb-pv"><i class="sb-pdot ${ready.length?'ok':'no'}"></i>${ready.length}/${ST.agents.length||2}</span>
      ${ico('chevronRight','ic-chev')}</button>
    <div class="sb-sep"></div>
    <button class="sb-prow" onclick="closeFootMenu();nav.go('settings')">${ico('settings')}
      <span>${esc(t('nav.settings'))}</span><span class="sb-pkbd">Ctrl ,</span></button>`;
}
window.footMenu = function(e){
  if(e) e.stopPropagation();
  const pop = document.getElementById('sbPop');
  if(!pop) return;
  if(!pop.hidden){ closeFootMenu(); return; }
  pop.innerHTML = footRows();
  pop.hidden = false;
  document.getElementById('sbMe').setAttribute('aria-expanded', 'true');
  const r = document.getElementById('sbMe').getBoundingClientRect();
  pop.style.left = Math.max(8, Math.min(r.left, window.innerWidth - pop.offsetWidth - 8)) + 'px';
  pop.style.bottom = (window.innerHeight - r.top + 6) + 'px';
};
window.closeFootMenu = function(){
  const pop = document.getElementById('sbPop');
  if(pop){ pop.hidden = true; pop.innerHTML=''; }
  const me = document.getElementById('sbMe');
  if(me) me.setAttribute('aria-expanded', 'false');
};
window.footCycle = async function(key){
  const A = window.APP;
  const CYCLE = { theme:['light','dark','auto'], lang:['zh','en'] };
  const list = CYCLE[key]; if(!list) return;
  // 这条路径直接 nav.resolve() 重绘整页，绕开了 nav.go 上那道未保存守卫 ——
  // 在流程编辑器里换个主题就能把没存的步骤改动冲没。所以先问守卫，再动设置。
  if(!await Promise.resolve(window.navGuardAsk && window.navGuardAsk())) return;
  const next = list[(list.indexOf(String(A[key] ?? list[0])) + 1) % list.length];
  await window.setAppearance({[key]: next});
  const pop = document.getElementById('sbPop');
  if(pop && !pop.hidden) pop.innerHTML = footRows();
  nav.resolve();
};

/* ---------------- 左下角：更新 ----------------
   只有「有东西可点」的时候才占位：idle / checking / 已是最新 一律隐藏，
   免得一个永远灰着的按钮骗人。 */
let UP = null, UP_POLL = null;
/* 页内两步确认的"上膛"状态：'' | 'apply' | 'download'。
   这一步以前是原生 confirm()，在 WebView2 里顶着一句「127.0.0.1:8000 显示」——
   那报的是开发服务器来源，不是软件名；按钮还是系统蓝，跟黑白品牌没关系。 */
let UP_ASK = '';
const mb = n => (n/1048576).toFixed(1) + ' MB';

/* 悬停要能看到"更新了什么"。发版说明截到 140 字，全文在浮层里 ——
   提示框宽 264px，把清单里最长 2000 字的 notes 整段塞进去会糊成一大块。 */
function upNoteTip(s){
  const n = String((s && s.notes) || '').replace(/\s+/g, ' ').trim();
  return n ? ' · ' + (n.length > 140 ? n.slice(0, 140) + '…' : n) : '';
}

function upView(s){
  if(!s || !s.configured) return null;
  const pct = s.size ? Math.min(99, Math.floor((s.got||0)*100/s.size)) : 0;
  const note = upNoteTip(s);
  /* available 与 downloading 两态**不画图标**：那颗下载小箭头是用户点名去掉的
     （"不要有下载的小箭头"）。进度由百分比和进度条表达，不需要一个箭头说"在下"。 */
  if(s.phase === 'available')
    return {text: t('up.avail'), tip: t('up.tipAvail', {v: s.latest, cur: s.local}) + note,
            tone: '', ic:'', p: 0};
  if(s.phase === 'downloading')
    return {text: pct + '%', tip: t('up.tipDl', {got: mb(s.got||0), size: mb(s.size)}) + note,
            tone: 'dl', ic:'', p: pct};
  if(s.phase === 'ready')
    return {text: t('up.ready'), tip: t('up.tipReady', {p: s.path || ''}) + note,
            tone: 'ok', ic:'checkCircle', p: 100};
  if(s.phase === 'error')
    return {text: t('up.failed'), tip: t('up.tipErr', {e: s.error || ''}),
            tone: 'err', ic:'warn', p: 0};
  return null;
}

/* 轨道宽度下放不下「已下载」三个字，所以文字和图标各渲染一份，CSS 挑着显示 */
function paintUpdate(){
  const b = $('#sbUpdate'); if(!b) return;
  const v = upView(UP);
  /* 胶囊没东西可报就收起，但**别顺手关掉用户正开着的浮层** ——
     "重新检查"回来发现没新版本时，浮层要留在原地告诉他"已是最新"，
     而不是点一下就凭空消失。关浮层的判断交给 upRepaintDialog（它认 UP 是否还在）。 */
  if(!v){ b.hidden = true; b.innerHTML = ''; b.dataset.tip = ''; window.upRepaintDialog(); return; }
  b.hidden = false;
  b.className = 'sb-update' + (v.tone ? ' is-' + v.tone : '');
  b.innerHTML = (v.tone === 'dl' ? '<span class="sb-up-bar"></span>' : '')
              + (v.ic ? `<span class="sb-up-ic">${ico(v.ic)}</span>` : '')
              + '<span class="sb-up-tx">' + esc(v.text) + '</span>';
  b.dataset.tip = v.tip;
  b.setAttribute('aria-label', v.tip);
  b.style.setProperty('--p', (v.p || 0) + '%');
  window.upRepaintDialog();
}

/* ---------------- 更新浮层（胶囊 + 居中对话框两件套） ----------------
   三态标题照参考实现（UpdateStatusDialog：New version / Downloading / is ready）。
   按钮只放后端真支持的：check / download / apply 三条端点，
   所以「取消下载」「跳过此版本」「自动下载并安装」一概不做。 */
function upTitle(u){
  if(u.phase === 'downloading') return t('up.tDownloading', {v: u.latest || ''});
  if(u.phase === 'ready')       return t('up.tReady', {v: u.latest || ''});
  if(u.phase === 'error')       return t('up.tFailed');
  return t('up.tAvailable', {v: u.latest || ''});
}

function upCardHtml(){
  const u = UP || {};
  const known = u.phase==='available' || u.phase==='downloading'
             || u.phase==='ready' || u.phase==='error';
  const pct = u.phase==='ready' ? 100
            : (u.size ? Math.min(99, Math.floor((u.got||0)*100/u.size)) : 0);
  const bar = (u.phase==='downloading' || u.phase==='ready')
    ? `<div class="up-bar"><i class="up-fill" style="width:${pct}%"></i></div>
       <div class="up-mb">${esc(mb(u.got||0))} / ${esc(mb(u.size||0))}</div>` : '';
  const err = u.phase==='error' ? `<div class="up-err">${esc(u.error||t('up.unknown'))}</div>` : '';
  const later = `<button class="btn" onclick="upClose()">${esc(t('up.later'))}</button>`;
  const cancel = `<button class="btn" onclick="upAskCancel()">${esc(t('c.cancel'))}</button>`;
  /* 后果说在按钮上方，不再弹一个跟本软件无关的系统框：「装完要自己再打开」和
     「在跑的任务会被打断」才是按下去之前需要读完的两句话。 */
  const runN = u.active_runs || 0;
  const ask = !UP_ASK ? '' : `<div class="up-ask"><b>${
      esc(t(UP_ASK === 'apply' ? 'up.askApply' : 'up.askDownload', {v: u.latest || ''}))}</b>${
      runN > 0 ? `<div class="up-ask-warn">${
        esc(t(UP_ASK === 'apply' ? 'up.askBusyQuit' : 'up.askBusyDl', {n: runN}))}</div>` : ''
    }</div>`;
  let btns;
  if(u.phase === 'available')
    btns = `<button class="btn btn-primary" onclick="upDownload()">${esc(t('up.downloadNow'))}</button>${UP_ASK === 'download' ? cancel : later}`;
  else if(u.phase === 'downloading')
    btns = later;
  else if(u.phase === 'ready')
    btns = UP_ASK === 'apply'
      ? `<button class="btn btn-primary" onclick="upApply()">${esc(t('up.askGo'))}</button>${cancel}`
      : `<button class="btn btn-primary" ${u.frozen?'':'disabled'}
              onclick="upApply()">${esc(t('up.apply'))}</button>${later}`;
  else if(u.phase === 'error')
    btns = `<button class="btn btn-primary" onclick="upCheckNow()">${esc(t('up.recheck'))}</button>${later}`;
  else   /* current / checking / idle：重新检查后没新东西，也要有话说 —— 以前这里 upView 返回 null，
            直接把用户正开着的那层关掉，等于"点了重新检查，窗口自己消失了"。 */
    btns = `<button class="btn btn-primary" onclick="upCheckNow()">${esc(t('up.recheck'))}</button>${later}`;
  const title = known ? upTitle(u) : t('up.tUpToDate', {v: u.local || ''});
  /* 清单里的 notes 一直落到 STATE，却从没被渲染过 —— 发版时写的那段说明，
     用户在软件里一个字都看不到。出错的这一轮不显示：那时候要看的是错误原因。 */
  const notes = (u.phase !== 'error' && String(u.notes || '').trim())
    ? `<div class="up-notes">${esc(u.notes)}</div>` : '';
  return `<div class="up-head"><b id="upHeadTtl">${esc(title)}</b>
      <button class="up-x ic-btn" onclick="upClose()" data-tip-any="1"
        data-tip="${esc(t('up.close'))}" aria-label="${esc(t('up.close'))}">${ico('close')}</button></div>
    <div class="up-ver">${esc(t('up.nowOn', {v: u.local || ''}))}</div>
    ${bar}${err}${notes}${ask}
    <div class="up-btns">${btns}</div>`;
}

window.upOpen = function(){
  const c = document.getElementById('upCard'); if(!c) return;
  document.body.classList.add('up-on');
  c.hidden = false;
  c.dataset.phase = (UP && UP.phase) || '';
  c.innerHTML = upCardHtml();
  const b = c.querySelector('.up-x'); if(b) b.focus();
};
window.upClose = function(){
  const c = document.getElementById('upCard'); if(!c || c.hidden) return;
  UP_ASK = '';
  c.hidden = true;
  document.body.classList.remove('up-on');
};
window.upRepaintDialog = function(){
  const c = document.getElementById('upCard');
  if(!c || c.hidden) return;
  if(!UP || !UP.configured){ window.upClose(); return; }
  /* 下载中每 400ms 轮询一次。整块换 innerHTML 会把焦点从 ✕ 上踢掉，
     还会让你按下去的那一瞬正好赶上按钮被替换（点了没反应）。
     所以只有阶段真的变了才重画结构，否则只改进度条宽度和那行字节数。 */
  if(c.dataset.phase !== UP.phase || c.dataset.ask !== UP_ASK){
    /* 上膛/退膛不换 phase，只换那一行确认和按钮 —— 只按 phase 判断的话，
       点「安装并重启」会毫无反应，用户只能再点一次，然后以为程序卡住了。
       阶段真的变了就顺手退膛：下载完成时不该还停在「确认下载」那一行。 */
    if(c.dataset.phase !== UP.phase) UP_ASK = '';
    c.dataset.phase = UP.phase;
    c.dataset.ask = UP_ASK;
    c.innerHTML = upCardHtml();
    return;
  }
  const pct = UP.phase==='ready' ? 100
            : (UP.size ? Math.min(99, Math.floor((UP.got||0)*100/UP.size)) : 0);
  const fill = c.querySelector('.up-fill'), mbEl = c.querySelector('.up-mb');
  if(fill) fill.style.width = pct + '%';
  if(mbEl) mbEl.textContent = mb(UP.got||0) + ' / ' + mb(UP.size||0);
};
function upArm(what){
  UP_ASK = what;
  window.upRepaintDialog();
  const b = document.querySelector('#upCard .up-btns .btn-primary');
  if(b) b.focus();   // 上膛后焦点落在真正会执行的那颗上，键盘用户不必再 Tab 一次
}
window.upAskCancel = function(){ UP_ASK = ''; window.upRepaintDialog(); };
window.upDownload = async function(){
  const n = (UP && UP.active_runs) || 0;
  if(n > 0 && UP_ASK !== 'download'){ upArm('download'); return; }
  UP_ASK = '';
  UP = await post('/api/update/download').catch(()=>({phase:'error', error:t('up.reqFail')}));
  paintUpdate(); upPoll();
  if(UP && UP.phase === 'error') toast(UP.error);
};
window.upApply = async function(){
  if(UP_ASK !== 'apply'){ upArm('apply'); return; }   // 第一下只上膛，把"要退出"说在按钮上方
  const r = await post('/api/update/apply').catch(e=>({detail:String(e)}));
  /* 成败都把膛退掉并重画。以前是发请求前先清标记，失败时浮层还停在「确认安装并退出」
     那两颗按钮上 —— 再点一次只是重新上膛，画面不动，看着就像按钮坏了。 */
  UP_ASK = '';
  window.upRepaintDialog();
  if(r && r.detail){ toast(r.detail); return; }
  toast(t('up.applyStarted'), true);
};
window.upCheckNow = async function(){
  UP = await post('/api/update/check').catch(()=>UP);
  paintUpdate();
  await upAutoDownload();
};

function upPoll(){
  if(UP_POLL){ clearInterval(UP_POLL); UP_POLL = null; }
  if(!UP || UP.phase !== 'downloading') return;
  UP_POLL = setInterval(async ()=>{
    const s = await api('/api/update').catch(()=>null);
    if(!s) return;
    UP = s; paintUpdate();
    if(s.phase !== 'downloading'){ clearInterval(UP_POLL); UP_POLL = null; }
  }, 400);
}

/* 胶囊只负责"有没有事要你看"，动作全在浮层里 —— 原来点一下就默默开始下载，
   用户没机会先看版本号和当前在跑几个任务。 */
window.sbUpdateClick = function(e){
  if(e) e.stopPropagation();
  if(!UP) return;
  window.upOpen();
};

/* 检测到就自己开始下（用户的要求：进软件自动检测、有新版就下，点一下才是"装"）。
   后端对"已经在下的"是幂等的，两次调用不会下出两份。 */
async function upAutoDownload(){
  if(!UP || UP.phase !== 'available') return;
  UP = await post('/api/update/download').catch(()=>UP);
  paintUpdate(); upPoll();
}

async function upInit(){
  const s = await api('/api/update').catch(()=>null);
  if(!s || !s.configured) return;
  UP = s;
  if(s.phase === 'idle' || s.phase === 'error'){
    UP = await post('/api/update/check').catch(()=>UP);
    /* 开机自动检查失败不该在左下角挂一个红胶囊骂人：
       用户没问的时候保持安静，设置页里照样能看到具体错在哪。 */
    if(UP && UP.phase === 'error'){ UP = Object.assign({}, UP, {phase:'idle'}); }
  }
  paintUpdate();
  if(UP && UP.phase === 'downloading') upPoll();
  else if(UP) await upAutoDownload();
}
window.upInit = upInit;
window.paintUpdate = paintUpdate;
document.addEventListener('click', (e)=>{
  const pop = document.getElementById('sbPop');
  if(pop && !pop.hidden && !e.target.closest('#sbPop') && !e.target.closest('#sbMe')) closeFootMenu();
  const fd = document.getElementById('sbFind');
  if(fd && !fd.hidden && !e.target.closest('#sbFind') && !e.target.closest('#sbSearchRow')) fd.hidden = true;
});

/* ---------------- 路由 ---------------- */
function viewTransitionOut(){
  const v = document.getElementById('view');
  if(!v) return Promise.resolve();
  v.classList.remove('mf-enter');
  return Promise.resolve();
}
function viewTransitionIn(){
  const v = document.getElementById('view');
  if(!v) return;
  v.classList.remove('mf-enter');
  void v.offsetWidth;
  v.classList.add('mf-enter');
}

let NAV_SEQ=0;
let NAV_CHAIN=Promise.resolve();   /* 导航排队用，见 nav.resolve() */
let GUARD_PASS='', GUARD_SKIP=false, LAST_VIEW='#/';   /* 未保存守卫：见 resolve() 开头 */
/* 永远不把已有内容清空：旧页面一直留到新页面算好之后一次性换掉。
   换页时短暂显示上一页，比整页白一下再长出来要稳。 */
function viewLoading(){
  const v = $('#view'); if(!v) return;
  v.setAttribute('aria-busy','true');
  if(v.children.length) return;
  v.innerHTML = '<div class="loading-bar"></div>';
}
window.viewLoading = viewLoading;

const nav = {
  go(id, extra){
    // editor.js 注册的未保存守卫；没有编辑器在场时它永远返回 true。
    // 守卫现在是页内 Promise（原生 confirm 会挂起整页线程），确认时带上目标
    // hash —— resolve() 那道 Back 键守卫看到同一目标就不再二次问。
    let hash = '#/'+id;
    if(extra) hash += '/'+extra;
    const proceed = () => {
      if(location.hash === hash){ nav.resolve(); return; }
      location.hash = hash;
    };
    Promise.resolve(window.navGuardAsk && window.navGuardAsk(hash)).then(ok => { if(ok) proceed(); });
  },
  resolve(){
    /* Back 键和手改 URL 不经过 nav.go，直接落在 hashchange 上 —— 这里是它们
       唯一的守卫口。难点：hashchange 跑的时候 URL 已经改走了，plDirty/skDirty
       按 hash 自判归属会返回 false（守卫整个哑掉，改动被静默重绘冲掉——
       1.3.3 第一版就栽在这）。所以用 LAST_VIEW（出发地）问 navGuardOwns，
       再把出发地 hash 递给 navIsDirty 判脏；确认才放行渲染，取消把 hash 摆回
       并跳过本轮渲染（界面原样，输入框里的字一个不动）。 */
    const target = location.hash || '#/home';
    const from = LAST_VIEW;
    /* 取消后摆回 hash 引起的本轮必须最先短路，而且要在 leavingEditor 判断**之外**：
       摆回之后 target === from，"正离开编辑器"不成立，skip 检查若嵌在里面会被
       绕过，于是照常全量重渲染 —— 用户明明选了"留在本页"，改动却被冲回基线。 */
    if(GUARD_SKIP){ GUARD_SKIP = false; return; }
    const leavingEditor = window.navGuardOwns && window.navGuardOwns(from) && from !== target;
    if(window.navGuardAsk && leavingEditor && GUARD_PASS !== target){
      const dirty = (window.navIsDirty ? navIsDirty(from) : false);
      if(dirty){
        Promise.resolve(window.navGuardAsk(target, true)).then(ok => {
          if(ok){ GUARD_PASS = target; nav.resolve(); }
          else { GUARD_SKIP = true; if(location.hash !== from) location.hash = from; }
        });
        return;
      }
    }
    GUARD_PASS = '';
    const seq=++NAV_SEQ;
    let raw = (location.hash||'').replace(/^#\/?/,'');
    if(!raw) raw = 'home';
    const [view, ...rest] = raw.split('/');
    const extra = rest.join('/');
    /* 必须排队，不能各跑各的：以前 viewTransitionOut().then() 一挂上就并发，
       连点两条运行记录时两次导航都先过了下面那句 seq 比较（那时 NAV_SEQ 还没再变），
       然后先点的那条响应慢、后落地，界面就停在上一页 —— 更糟的是迟到的 renderSettings
       会把 dataset.shell='settings' 留在一个非设置页上，侧栏和顶栏一起消失。
       串起来之后开头那次比较才是有效的：被取代的那一轮根本不会开始渲染。 */
    NAV_CHAIN = NAV_CHAIN.then(async ()=>{
      if(seq!==NAV_SEQ) return;
      await viewTransitionOut();
      if(seq!==NAV_SEQ) return;
      window.__chrome = {title:'', icon:'flow', actions:''};
      const v = $('#view'); if(v) v.classList.remove('with-composer');
      if(view!=='settings') delete $('#app').dataset.shell;
      const run = async (fn, key)=>{ try { await fn(); renderNav(key); paintChrome(); window.voyraReadReady(); } finally { $('#view')?.setAttribute('aria-busy','false'); } };
      if(view==='home') await run(window.renderHome,'home');
      else if(view==='skills') await run(window.renderSkills,'skills');
      else if(view==='skill-edit') await run(()=>window.renderSkillEdit(extra),'skills');
      else if(view==='pipelines') await run(window.renderPipelines,'pipelines');
      else if(view==='pipeline-edit') await run(()=>window.renderPipelineEdit(extra),'pipelines');
      else if(view==='settings') await run(()=>renderSettings(extra),'settings');
      else if(view==='runs') await run(window.renderRuns,'runs');
      else if(view==='run') await run(()=>window.renderRunConsole(extra),'runs');
      else await run(window.renderHome,'home');   /* 认不出来的一律回首页输入台 */
      if(seq===NAV_SEQ){ viewTransitionIn(); renderSidebarLists(); LAST_VIEW = location.hash || LAST_VIEW; }
    }).catch(e => {
      /* 排队就是把所有后续导航挂在这一条 promise 上：某一轮里抛出来异常
         会让链子变成 rejected 状态，之后每一次 .then 都被跳过 —— 整个应用
         再也翻不了页。所以这一层必须吃掉异常，链子永远是 resolved。 */
      console.error('导航失败：', e);
      $('#view')?.setAttribute('aria-busy','false');
      window.voyraReadError(e.message || String(e));
    });
  },
};
window.nav = nav;
window.addEventListener('hashchange', ()=>nav.resolve());

/* ---------------- 下任务：首页就是输入台 ----------------
   以前它是一个居中小弹层，打开时整个应用被遮罩盖住。参考实现把输入台直接
   长在主页上（大标题 + 卡片），所以这里改成渲染进 #view —— 六个调用点
   （侧栏「新建任务」、Ctrl+K、⋯ 菜单、流程行「运行」、页头「下任务」）
   仍然统一走 taskModal()，只是它现在做的是"回到首页并把这条流程选中"。 */
function tkStageHtml(tpls, flow){
  /* 引擎候选来自实测盘点（ST.agents 的 found 标记），不是写死两家 ——
     本机没装 codex 时，选它只会让第一条任务在起进程那一步炸掉。
     boot() 先 await loadAgents() 才渲染这里，所以 ST.agents 此时已就位；
     两家都没检测到就只留「跟随默认」一枚，不放按下去必错的假控件。 */
  const ready = (ST.agents||[]).filter(a=>a.found).map(a=>a.engine);
  const ENGS = [{v:'', label:t('ed.engineDefault')}].concat(
    ready.map(v => ({v, label:t('eng.'+v)})));
  const PERMS = [{v:'', label:t('pm.default'), note:t('pm.defaultNote')}].concat(
    PERM_MODES.map(m => ({v:m, label:t('pm.'+m), note:t('pm.'+m+'D')})));
  /* 模型候选只有真存在的预设名 —— 裸模型名这里不做：那是编辑器里逐步挑端点的事，
     输入台要的是一句"整条流程换成这套端点"，而预设才是那个粒度。 */
  const PSET = (ST.presets||[]).map(p=>({v:p.name, label:p.name,
    note:[p.provider, p.model].filter(Boolean).join(' · ')}));
  /* 选中的预设可能在设置里被删过：那时 chip 会退回「跟随步骤」，
     但 TK_MODEL 还留着死名字 —— 必须一起归零，否则显示的是一套、发出去的是另一套。 */
  if(!PSET.some(o=>o.v===TK_MODEL)) TK_MODEL = '';
  return `<div class="home-stage view-enter">
    <div class="tk-greet-row">
      <h1 class="tk-greet">${esc(t('tk.greet'))}</h1>
      <span class="tk-sub">${esc(t('tk.subDesc'))}</span>
    </div>
    <div class="tk-card" role="region" aria-label="${esc(t('nav.newTask'))}">
      <div class="tk-top">
        ${ffSelect(tpls.map(p=>({v:p.name, label:(p.label||p.name),
                                 note:p.steps.length+' '+t('c.steps')})),
                   flow, {id:'tkFlow', icon:'flow', onChange:'tkSync'})}
        ${ffSelect(PERMS, ST.permMode||'', {id:'tkPerm', icon:'shield', onChange:'tkPermSet', short:true})}
        <label class="tk-dirw" title="${esc(t('task.dirTip'))}">${ico('folder')}
          <input class="tk-dir" id="tkDir" type="text" spellcheck="false" autocomplete="off"
            value="${esc(TK_DIR)}" placeholder="${esc(t('task.dirPh'))}"
            aria-label="${esc(t('task.dirPh'))}"></label>
        <input class="tk-name" id="tkLabel" placeholder="${esc(t('task.labelPh'))}">
      </div>
      <div class="tk-field">
        <textarea class="tk-input" id="tkBrief" rows="4" placeholder="${esc(t('task.briefPh'))}"
          oninput="tkSync()"></textarea>
      </div>
      <div class="tk-bar">
        <div class="tk-steps" id="tkSteps" role="list" aria-label="${esc(t('tk.stepsAria'))}"></div>
        ${ffSelect(ENGS, TK_ENG, {id:'tkEngine', icon:'agent', onChange:'tkEngineSet'})}
        ${PSET.length ? ffSelect([{v:'', label:t('tk.modelAny'), note:t('tk.modelAnyD')}].concat(PSET),
                                 TK_MODEL,
                                 {id:'tkModel', icon:'api', onChange:'tkModelSet', short:true}) : ''}
        <button class="cp-send" onclick="taskStart()" aria-label="${esc(t('task.start'))}"
          title="${esc(t('task.start'))}">${ico('arrowUp')}</button>
      </div>
    </div>

    <div class="home-pipelines-sect">
      <div class="sect-head">
        <span class="sect-title">${esc(t('home.allPipelines'))}</span>
        <button class="btn btn-ghost btn-sm" onclick="nav.go('pipeline-edit/new')">${ico('plus')} ${esc(t('home.newPipeline'))}</button>
      </div>
      <div class="pl-list" id="homePlList">${tpls.length
        ? tpls.map(plRowHtml).join('')
        : `<div class="pf-empty">${esc(t('task.noFlow'))}</div>`}</div>
    </div>
  </div>`;
}

/* 模块 2：模板行 —— 十阶段点阵 / 阶段数 / 检查点数 / 已关联 Run 数 / 最近产物 / 快捷执行。
   只读 /api/pipelines 已有的字段，不额外打请求。 */
function plRowHtml(p){
  const steps = p.steps || [];
  const cp = steps.filter(s=>s.checkpoint).length;
  const last = steps.length ? (steps[steps.length-1].out || '') : '';
  const dots = steps.slice(0, 12).map(s=>`<i class="${s.checkpoint?'cp':''}"></i>`).join('');
  return `<article class="pl-card-row${p.archived?' archived':''}">
    <button type="button" class="pl-row-main" onclick="taskModal('${jsq(p.name)}')">
      <div class="pl-row-title"><span class="pl-row-name">${esc(p.label||p.name)}</span>
        <code>${esc(p.name)}</code></div>
      <div class="pl-row-facts">
        <span class="pl-mini-track" aria-hidden="true">${dots}</span>
        <span class="pl-fact">${ico('flow')}${esc(t('home.plStages',{n:steps.length}))}</span>
        ${cp?`<span class="pl-fact">${ico('shield')}${esc(t('home.plCp',{n:cp}))}</span>`:''}
        <span class="pl-fact">${ico('runs')}${esc(t('home.plRuns',{n:p.runs||0}))}</span>
        ${last?`<span class="pl-fact">${ico('file')}<code>${esc(last)}</code></span>`:''}
      </div>
    </button>
    <div class="pl-row-ops" onclick="event.stopPropagation()">
      <button class="pf-op pf-op-start" onclick="taskModal('${jsq(p.name)}')">${esc(t('home.plRun'))}</button>
      <button class="pf-op" onclick="nav.go('pipeline-edit/${jsq(p.name)}')">${esc(t('c.edit'))}</button>
    </div>
  </article>`;
}

/* 和后端 agents.PERM_MODES 同源，改一处必须改两处（两边都有测试钉着）。
   只有这三档能同时落到 claude 的 --permission-mode 和 codex 的 -s 沙箱上；
   claude 还认 manual / dontAsk / auto，但 manual 要我们实现"回答提问"的回调工具，
   而 codex 的 exec 模式根本没有回通道 —— 所以那几档宁可不放，不放半边的假控件。 */
const PERM_MODES = ['plan', 'acceptEdits', 'bypassPermissions'];

/* 模式是全局默认（它接管了原来设置里那行 codex 沙箱），不是这一条任务的临时值 ——
   所以选完要 toast 说清作用域，别让人以为只影响这次。
   不能走 postAgents：它成功后固定弹一句「已保存」，会把这句说清作用域的提示顶掉。 */
window.tkPermSet = async function(v){
  const prev = ST.permMode||'';
  const name = (m) => m ? t('pm.'+m) : t('pm.default');
  const r = await post('/api/agents', {permission_mode: v}).catch(e=>({detail:String(e)}));
  if(r && r.detail){
    /* 菜单在调 onChange 之前就把隐藏 input 和按钮文字都写好了（ffOpen 的 pick 分支），
       所以失败时必须连标签一起退回 —— 否则 chip 会显示一个服务端根本没接受的模式。
       网络断了也一样：post() 的 catch 给的是 {detail:...}，是真值，别当成成功。 */
    ST.permMode = prev;
    window.ffSetValue('tkPerm', prev, name(prev));
    toast(r.detail);
    return;
  }
  ST.permMode = v;
  toast(t('pm.nowGlobal', {m: name(v)}), true);
};

/* 底部那一排步骤：把选中流程的每一步摊开发送键左边，一眼看见"这条要跑几段"。
   带检查点的那一步画一个空心环 —— 原来那行「含 N 个检查点」的信息搬到这里，
   而且落在具体某一步上比一个总数有用。 */
function tkPaintSteps(flow){
  const box = document.getElementById('tkSteps'); if(!box) return;
  const p = (ST.flows||[]).find(x=>x.name===flow);
  const steps = (p && p.steps) || [];
  box.innerHTML = steps.length
    ? steps.map((s,i)=>`<span class="tk-step-chip${s.checkpoint?' has-cp':''}" role="listitem"
        title="${esc(s.label||'')}${s.checkpoint?' · '+t('tk.cpMark'):''}">
        <i>${i+1}</i><span>${esc(s.label||'')}</span></span>`).join('')
    : `<span class="tk-step-empty">${esc(t('tk.noSteps'))}</span>`;
}

window.renderHome = async function(){
  window.viewLoading();
  let tpls = ST.flows;
  const needPreset = ST.presets === null;   /* 空数组=拉过了真没有，别再拉一遍 */
  const [pr, pv] = await Promise.all([
    (tpls && tpls.length) ? Promise.resolve(null)
                          : api('/api/pipelines'),
    needPreset ? api('/api/providers') : Promise.resolve(null),
  ]);
  if(pv) ST.presets = pv.presets||[];
  if(pr) tpls = pr.pipelines||[];
  tpls = tpls || [];
  ST.flows = tpls;
  window.__chrome = {title:'', icon:'', actions:''};
  if(!tpls.length){
    $('#view').innerHTML = `<div class="home-stage"><h1 class="tk-greet">${esc(t('tk.greet'))}</h1>
      <span class="tk-sub">${esc(t('tk.subDesc'))}</span>
      <div class="pf-empty home-empty">
        <p>${esc(t('task.noFlow'))}</p>
        <!-- 空状态必须有去处：按钮与工作流页同一个「新建流程」入口，不另开第二个 -->
        <button class="btn btn-primary" onclick="nav.go('pipeline-edit/new')">${ico('plus')} ${esc(t('home.newPipeline'))}</button>
      </div></div>`;
    return;
  }
  const first = TK_PICK || tpls[0].name;
  $('#view').innerHTML = tkStageHtml(tpls, first);
  TK_PICK = '';
  tkPaintSteps(first);
  const b = document.getElementById('tkBrief'); if(b) b.focus();
};

window.taskModal = function(presetFlow){
  if(presetFlow) TK_PICK = presetFlow;
  // 已经在首页：不重新渲染（那会清掉用户正在写的草稿），只换选中的流程并聚焦。
  if((location.hash||'').replace(/^#\/?/,'').split('/')[0] === 'home'){
    const hid = document.getElementById('tkFlow');
    if(hid && presetFlow){
      // 必须连按钮上那行文字一起换：ffSetValue 只写隐藏 input 的话，
      // 芯片还显示着上一条流程 —— 这个坑以前踩过一次。
      const p = (ST.flows||[]).find(x=>x.name===presetFlow);
      window.ffSetValue('tkFlow', presetFlow,
        p ? ffFlat({label:(p.label||p.name), note:p.steps.length+' '+t('c.steps')}) : presetFlow);
    }
    tkSync();
    const b = document.getElementById('tkBrief'); if(b) b.focus();
    return;
  }
  nav.go('home');
};
/* 输入台上唯一的"重算一切"入口：换流程要重画步骤条，打字要换发送键的可用态。
   以前它还管那行提示文字，文字已按用户要求撤掉。 */
function tkSync(){
  tkPaintSteps(((document.getElementById('tkFlow')||{}).value)||'');
  const brief = ((document.getElementById('tkBrief')||{}).value||'').trim();
  const send = document.querySelector('.tk-bar .cp-send');
  if(send) send.classList.toggle('is-on', brief.length > 0);
}
window.tkSync = tkSync;
let TK_PICK = '';  /* taskModal 带进来的预选流程：由 renderHome 消费一次就清空 */
let TK_ENG = '';   /* 这一条任务用哪个 CLI 引擎；'' = 不指定，沿用步骤自带/全局默认 */
window.tkEngineSet = function(v){ TK_ENG = v || ''; };
/* 运行级模型覆盖：存的是预设名，盖到每一步的 model 上，之后仍走那条
   「预设名 > 裸模型名 > 默认预设」的老阶梯 —— 这里不另开一套解析。 */
let TK_MODEL = '';
window.tkModelSet = function(v){ TK_MODEL = v || ''; };
/* 在哪个目录里干活。'' = 用软件自己派的 run-<id> 工作区。
   和引擎/模型一样是"这一条任务的选择"，但起跑后不清：连着跑同一个工程是常态。 */
let TK_DIR = '';
window.taskStart = async function(){
  const flow = (document.getElementById('tkFlow')||{}).value||'';
  const brief = ((document.getElementById('tkBrief')||{}).value||'').trim();
  const label = ((document.getElementById('tkLabel')||{}).value||'').trim();
  const dir = ((document.getElementById('tkDir')||{}).value||'').trim();
  if(!brief){ toast(t('task.needBrief')); return; }
  TK_DIR = dir;
  const r = await post('/api/pipelines/'+encodeURIComponent(flow)+'/run',
                       {brief, label, engine: TK_ENG, model: TK_MODEL, workdir: dir})
    .catch(e=>({detail:String(e)}));
  if(r.detail){ toast(r.detail); return; }
  // 输入台现在长在页面上，没有"关掉窗口"这回事了 —— 起跑后把草稿清空，
  // 免得回到首页时上一条任务的话还挂在框里。
  const ta = document.getElementById('tkBrief'); if(ta) ta.value = '';
  const lb = document.getElementById('tkLabel'); if(lb) lb.value = '';
  tkSync();
  toast(t('task.started'), true);
  nav.go('run/'+r.run.id);
};

/* ================= 设置：Codex 式两栏外壳 ================= */
const SET_SECTIONS = [
  {grp:'set.grp.pref', items:[['appearance','set.appearance','appearance'],
                              ['shortcuts','set.shortcuts','keyboard']]},
  {grp:'set.grp.exec', items:[['engines','set.engines','agent'],['presets','set.presets','api'],
                              ['runtime','set.runtime','runtime'],['caps','set.caps','layers']]},
  {grp:'set.grp.data', items:[['dirs','set.dirs','folder'],['stats','set.stats','chart'],
                              ['update','set.update','download'],['about','set.about','info']]},
];
window.sbToggleArchived = function(){ SB_ARCH = !SB_ARCH; renderSidebarLists(); };
window.sbRowMore = function(e, name){
  const items = [{v:'files', label:t('sb.viewFiles'), run:()=>sbShowFiles(name)}];
  if (SB_ARCH) {
    items.push({v:'unarch', label:t('sb.unarchive'), run:()=>sbArchive(name, false)});
    items.push({v:'del', label:t('c.delete'), danger:true, run:()=>sbDelete(name)});
  } else {
    items.push({v:'task', label:t('sb.newTaskHere'), run:()=>taskModal(name)});
    items.push({v:'arch', label:t('sb.archive'), run:()=>sbArchive(name, true)});
  }
  window.ffActionMenu(e, items);
};
/* 项目没有自己的工作区目录，产物在每次运行的工作区里 —— 「查看文件」开的是最近那次。 */
window.sbShowFiles = async function(name){
  const p = (ST.sbFlows||[]).find(x=>x.name===name);
  const id = p && p.last_run && p.last_run.id;
  if (!id){ toast(t('sb.noRunYet')); return; }
  const r = await post('/api/reveal?which=run&run_id='+encodeURIComponent(id))
    .catch(e=>({detail:String(e)}));
  if (r && r.detail) toast(r.detail);
};
window.sbArchive = async function(name, flag){
  const r = await post('/api/pipelines/'+encodeURIComponent(name)+'/archive', {archived:flag})
    .catch(e=>({detail:String(e)}));
  if (r && r.detail){ toast(r.detail); return; }
  /* toast 上给人看的是他认得的那个名字，不是库里的 slug */
  const p = (ST.sbFlows||[]).find(x=>x.name===name);
  toast(t(flag ? 'sb.archivedToast' : 'sb.unarchivedToast', {name:(p&&p.label)||name}), true);
  renderSidebarLists();
};
window.sbDelete = async function(name){
  if (!(await window.ffAsk({danger:true, title:t('ff.delFlow'),
      body:t('list.deleteConfirm',{name}), ok:t('ff.delete')}))) return;
  const r = await del('/api/pipelines/'+encodeURIComponent(name)).catch(e=>({detail:String(e)}));
  if (r && r.detail){ toast(r.detail); return; }
  renderSidebarLists();
};

let SET_SECTION = 'appearance';
let SET_Q = '';
let PATH_EDIT = '';

/* 拼音首字母：中文界面上人打的是"mx"，不是"模型"的原文 —— 纯子串匹配命中不了。
   表只覆盖 ui.js 中文案出现过的 570 个字（离线用 Intl.Collator 的 pinyin 排序生成，
   生成器不进仓库），表里没有的字直接跳过。全拼要整张字典，为这个搜索框不值当。 */
const PY_GROUPS = "A:安按案暗|B:本把步边版败保并包编闭别标背不帮遍报表板部贝补绑必变比被|C:程操查此产侧存出错成创除从材拆词持次车策称场测充才参衬尺寸窗彩传超吃残插磁常|D:地的当多档到调单读点打断定掉导带洞段短大动待等订对第端叠都道度电低登代弹但|E:额|F:放份发副返分付方法复符范费风峰服|G:工个更归过观关刚果给告改功高跟挂规管共格感光该各钩官孤供|H:或还回换候击后会含和画核合划户好耗灰黄恢忽唤环活缓话获|J:技记建近件即检继己接将辑角就景交今据结进假夹具胶截经基加见既级机际计捷键局聚焦界间距积旧金兼径几较监|K:库开看可空拷快框宽控口槛考|L:流录来栏留零料理论落里逻漏量浏览了类令列略轮连裸离立另累蓝路力络两链|M:没目们码么每明名面秒描母默模吗密满某门命|N:能内哪囊你那拿|P:匹配跑排批偏盘判|Q:前去起取切强擎清请求确启器区全其契缺浅气抢趋|R:任认入人染日如润容让仍软|S:水设搜索色上是失稍尚始它双删刷时首什试赛数示说少实送输收手束述适随识审生使所受式深缩事树省沙身势他市算思商|T:体台挑条同态停退替天题图提太推头填套添统通特跳听|W:务文物外未完无我问唯为位尾网围万|X:线行新项消下现续序小享绪想些写形先修显渲选需信息型效系性须校响箱协|Y:运与有一已语言引用页由源右样要研原依应也英意预优于约移硬钥云验影阅沿越议域忆亿月义|Z:织智作置在最这址载状正知中装重自直骤钟字执子整至则只止指展早志转终制择主做找暂再准注长窄逐走专折住值周柱占真支之着增";
const PY_CHAR = {};
PY_GROUPS.split('|').forEach(gp => {
  const i = gp.indexOf(':'), L = gp.slice(0, i).toLowerCase();
  for (const ch of gp.slice(i + 1)) PY_CHAR[ch] = L;
});
function pyInit(s){ let r = ''; for (const ch of String(s||'')){ const v = PY_CHAR[ch]; if (v) r += v; } return r; }
/* 搜索键的唯一出口：原文小写 + 一串首字母，两边拼在同一个 data-k 里，
   过滤器只看 includes，不需要知道拼音这件事存在。 */
function kAttr(v){ const t = String(v == null ? '' : v).toLowerCase(); return esc(t + ' ' + pyInit(t)); }

const srow = (title, desc, ctl, extra='') => `
  <div class="st-row" data-k="${kAttr((title||'')+' '+(desc||'')+' '+extra)}">
    <div class="st-row-main"><div class="st-t">${title}</div>
      ${desc?`<div class="st-d">${desc}</div>`:''}</div>
    <div class="st-ctl">${ctl||''}</div>
  </div>`;
/* 统计页用"卡片内标题"，别的分区用"卡片上方那行分组标签" —— 参考图里那张屏没有分组标签 */
const stCard = (title, rows) => `<div class="st-block"><div class="st-panel">`
  + (title ? `<div class="st-pttl">${esc(title)}</div>` : '') + rows + `</div></div>`;
const spanel = (rows, label='', actions='') => `
  <div class="st-block">${label || actions ? `<div class="st-labelrow">
      ${label ? `<div class="st-label">${esc(label)}</div>` : '<span></span>'}
      ${actions ? `<div class="st-label-acts">${actions}</div>` : ''}</div>` : ''}
    <div class="st-panel">${rows}</div></div>`;
/* 标题带说明在上、输入框整行铺开在卡片内；宽度归容器，不用内联 style 凑 */
const stIn = (title, desc, id, val, ph, saveFn, extra='', mono=true, acts='') => `
  <div class="st-row" data-k="${kAttr((title||'')+' '+(desc||'')+' '+extra)}">
    <div class="st-row-main"><div class="st-t">${title}</div>
      ${desc?`<div class="st-d">${desc}</div>`:''}</div>
    <div class="st-ctl"><button class="st-btn" onclick="${saveFn}">${esc(t('c.save'))}</button>${acts}</div>
  </div>
  <div class="st-rowsub"><input class="st-input${mono?' mono':''}" id="${id}"
    placeholder="${esc(ph||'')}" value="${esc(val||'')}"></div>`;
/* 一整块控件（磁贴 / 色板）放不下右侧的，就自己占一行铺在标题下面 */
const sblk = (title, desc, body, extra='') => `
  <div class="st-row st-row-col" data-k="${kAttr((title||'')+' '+(desc||'')+' '+extra)}">
    <div class="st-row-main"><div class="st-t">${title}</div>
      ${desc?`<div class="st-d">${desc}</div>`:''}</div>${body}</div>`;
/* 设置页的「多选一」：跟 ssel 同一个盒子形状，只是还能带一个参数（语言/引擎按行切换） */
const sseg = (opts, cur, fn, arg) => ffSelect(opts.map(([v,l])=>({v, label:l})), cur,
  {onChange:(v)=>{ const f=window[fn]; if(f){ if(arg) f(arg,v); else f(v); } }});
const ssel = (opts, cur, fn) => ffSelect(opts.map(([v,l])=>({v,label:l})), cur, {onChange:fn});
const ssw = (on, fn) => `<label class="switch"><input type="checkbox" ${on?'checked':''}
  onchange="swPick(this,'${fn}')"><span class="slider"></span></label>`;
window.swPick = function(el, fn){ const f=window[fn]; if(f) f(el.checked); };
const schips = (items) => `<div class="st-chips">${items.map(x=>
  `<span class="st-chip">${esc(x)}</span>`).join('')}</div>`;
const skey = (k) => `<kbd class="st-kbd">${esc(k)}</kbd>`;

/* 1rem 的基准像素，和 style.css 里 html{font-size:calc(14px * var(--text-scale))} 对齐
   （tests/test_static_contract.py 钉住两边一致）。滑块读数要说「人话」就得靠它换算。 */
const ROOT_PX = 14;
const SL_OPTS = {
  textSize: () => Object.keys(window.AP_OPTS.TEXT_SIZES),
  uiZoom: () => Object.keys(window.AP_OPTS.ZOOMS),
  contentWidth: () => Object.keys(window.AP_OPTS.WIDTHS),
};
const SL_LBL = { textSize:'ap.textSize', uiZoom:'ap.zoom', contentWidth:'ap.width' };
function apValText(key, v){
  const O = window.AP_OPTS;
  if(key==='textSize') return t('ap.size.'+v)+' · '+Math.round(ROOT_PX*O.TEXT_SIZES[v])+'px';
  if(key==='uiZoom') return v;
  return v==='full' ? t('ap.width.full') : t('ap.width.'+v)+' · '+O.WIDTHS[v];
}
const sslider = (key, cur) => {
  const opts = SL_OPTS[key]();
  const i = Math.max(0, opts.indexOf(cur));
  return `<div class="st-slider">
    <input type="range" class="st-range" min="0" max="${opts.length-1}" step="1" value="${i}"
      aria-label="${esc(t(SL_LBL[key]))}" data-sk="${key}"
      oninput="slPick('${key}',this.value)" onchange="slPick('${key}',this.value,1)">
    <span class="st-slider-val" data-sv="${key}">${esc(apValText(key, cur))}</span></div>`;
};
/* 拖动只改内存（oninput），松手才落盘（onchange）：落盘走 apSet，不重渲染整页。 */
window.slPick = function(key, i, commit){
  const v = SL_OPTS[key]()[Number(i)];
  if(!v) return;
  const out = document.querySelector('[data-sv="'+key+'"]');
  if(out) out.textContent = apValText(key, v);
  if(commit) window.apSet(key, v); else window.previewAppearance({[key]: v});
};

const apTiles = () => `<div class="st-tiles" id="stTiles">${window.AP_OPTS.THEMES.map(v=>{
  const on = window.APP.theme===v;
  return `<button type="button" class="st-tile${on?' active':''}" data-v="${v}"
    aria-pressed="${on?'true':'false'}" onclick="apTile('${v}')">
    <span class="st-tile-prev" data-prev="${v}"></span>
    <span class="st-tile-name">${esc(t('ap.theme.'+v))}</span></button>`;}).join('')}</div>`;
/* 磁贴/色板点了不能重渲染：整页重绘会丢滚动位置，也让 CSS 变量看起来「闪」了一下 */
window.apTile = function(v){ pickIn('#stTiles', 'st-tile', 'theme', v); };
function pickIn(sel, cls, key, v){
  document.querySelectorAll(sel+' .'+cls).forEach(b=>{
    const on = b.dataset.v===v;
    b.classList.toggle('active', on);
    b.setAttribute('aria-pressed', on ? 'true' : 'false');
  });
  window.apSet(key, v);
}
window.apReset = async function(){
  await window.setAppearance({theme:'dark', font:'default',
    textSize:'m', uiZoom:'100%', contentWidth:'medium'});
  toast(t('ap.resetDone'), true);
  renderSettings(SET_SECTION);
};

function secAppearance(){
  const A = window.APP;
  const lang = spanel([
    srow(t('ap.language'), t('ap.languageD'),
      sseg([['zh','中文'],['en','English']], A.lang, 'apSet', 'lang'), 'language locale'),
  ].join(''), t('ap.grpLang'));
  const look = spanel([
    sblk(t('ap.theme'), t('ap.themeD'), apTiles(), 'theme dark light system 明暗'),
    srow(t('ap.font'), t('ap.fontD'),
      ssel(window.AP_OPTS.FONTS.map(v=>[v,t('ap.font.'+v)]), A.font, 'apSetFont'), 'font typeface'),
  ].join(''), t('ap.grpLook'));
  const size = spanel([
    srow(t('ap.textSize'), t('ap.textSizeD'), sslider('textSize', A.textSize), 'text size font 字号'),
    srow(t('ap.zoom'), t('ap.zoomD'), sslider('uiZoom', A.uiZoom), 'zoom scale ui 缩放'),
    srow(t('ap.width'), t('ap.widthD'), sslider('contentWidth', A.contentWidth), 'width content 宽度'),
  ].join(''), t('ap.grpSize'));
  const pv = spanel(
    `<div class="st-preview">
       <div class="spv-title">${esc(t('ap.pvTitle'))}</div>
       <div class="spv-body">${esc(t('ap.pvBody'))}</div>
       <div class="spv-code">${esc(t('ap.pvCode'))}</div>
       <div class="spv-meta">${esc(t('ap.pvMeta'))}</div>
     </div>`, t('ap.grpPreview'),
    `<button class="st-btn" onclick="apReset()">${esc(t('ap.reset'))}</button>`);
  return lang + look + size + pv;
}

function secEngines(){
  const engRows = ST.agents.map(a=>{
    const isDef = ST.defaultEngine===a.engine;
    const bits = [];
    if(a.version) bits.push(t('eng.ver',{v:a.version}));
    if(a.needs) bits.push(t('eng.need',{n:a.needs}));
    const ctl = a.found
      ? `<span class="st-state ok"><i></i>${esc(t('eng.ready'))}</span>
         ${isDef?`<span class="sk-badge sk-badge-user">${esc(t('eng.defaultTag'))}</span>`:''}`
      : `<span class="st-state no"><i></i>${esc(t('eng.missing'))}</span>`;
    return srow(t('eng.'+a.engine), esc(t('eng.'+a.engine+'D'))
      + (bits.length?`<div class="st-d2">${esc(bits.join(' · '))}</div>`:''), ctl, a.engine+' cli binary agent default');
  }).join('');
  const head = srow(t('eng.default'), t('eng.defaultD'),
    sseg([['', t('eng.auto')]].concat(ST.agents.map(a=>[a.engine,t('eng.'+a.engine)]))
      , ST.defaultEngine, 'setDefaultEngine'), 'default engine');
  const paths = ST.agents.map(a=>{
    const cur = a.engine==='claude'?(ST.claudeCli||''):(ST.codexCli||'');
    const title = esc(t('eng.pathFor',{e:t('eng.'+a.engine)}));
    if(PATH_EDIT===a.engine){
      return stIn(title, t('eng.pathD'), 'path_'+a.engine, cur, t('eng.pathPh'),
                  "savePath('"+a.engine+"')", a.engine+' path binary', true,
                  `<button class="st-btn" onclick="cancelPath()">${esc(t('c.cancel'))}</button>`);
    }
    return srow(title, t('eng.pathD'),
      `<span class="st-val st-val-path">${esc(cur || a.bin || t('eng.auto'))}</span>
       <button class="st-btn" onclick="editPath('${a.engine}')">${esc(t('eng.change'))}</button>`, a.engine+' path binary');
  }).join('');
  return spanel(head + engRows, t('eng.grpEngines')) + spanel(paths, t('eng.grpBinary'));
}

function secPresets(){
  const rows = PRESETS.map(p=>{
    const disp = (p.extra&&p.extra.display_name)||p.name;
    const prov = (p.provider||'openai')==='anthropic'?'Anthropic':'OpenAI';
    const bits = [prov, p.api_base||'—']; if(p.model) bits.push(p.model);
    if(p.key_hint) bits.push(p.key_hint);   // 清单里不再有 api_key，只回末四位
    return srow(esc(disp), esc(bits.join(' · ')),
      `${p.is_default?`<span class="sk-badge sk-badge-user">${esc(t('pr.inUse'))}</span>`
        :`<button class="st-btn" onclick="pfSetDefault(${p.id})">${esc(t('eng.setDefault'))}</button>`}
       <button class="st-btn" onclick="pfTest(${p.id})">${esc(t('pr.test'))}</button>
       <button class="st-btn" onclick="pfEdit(${p.id})">${esc(t('c.edit'))}</button>
       <button class="st-btn st-btn-danger" ${p.is_default?'disabled':''} onclick="pfDel(${p.id})">${esc(t('c.delete'))}</button>`,
      disp+' preset endpoint key model protocol');
  }).join('');
  const list = spanel((rows || srow(t('pre.none'), t('pre.desc'), '', 'preset none empty'))
    + srow(t('pr.add'), '',
        `<button class="st-btn" onclick="pfOpenNew()"><span class="btn-plus">＋</span> ${esc(t('pr.add'))}</button>`,
        'preset add new endpoint'), t('pre.grpList'));
  const gate = spanel(
    srow(t('pre.gate'), t('pre.gateD'),
      schips(['claude ↔ Anthropic', 'codex ↔ OpenAI']), 'protocol gate anthropic openai'),
    t('pre.grpGate'));
  return list + gate;
}

function secRuntime(){
  const mins = [['300','5'],['600','10'],['900','15'],['1800','30'],['2700','45'],['3600','60'],['7200','120']]
    .map(([v,l])=>[v, l+' '+t('rt.timeoutMin')]);
  const ef = (ST.effortOptions||['auto']).map(v=>[v,t('rt.effort.'+v)]);
  const rt = [0,1,2,3].map(v=>[String(v), v? t('rt.retryTimes',{n:v}) : t('rt.retryNone')]);
  /* 这里以前有一行「codex 沙箱」选择器：输入台的模式 chip 接管了它之后必须删干净 ——
     一个入口改沙箱、另一个入口改模式（它也会改沙箱），两边会互相打脸。 */
  return spanel(
    srow(t('rt.timeout'), t('rt.timeoutD'), ssel(mins, ST.agentTimeout||'2700', 'saveTimeout'), 'timeout limit seconds step')
    + srow(t('rt.retry'), t('rt.retryD'), sseg(rt, ST.stepRetry||'0', 'saveRetry'), 'retry fail times')
    + srow(t('rt.effort'), t('rt.effortD'), sseg(ef, ST.reasoningEffort||'auto', 'saveEffort'), 'reasoning effort think codex')
    + srow(t('rt.auto'), t('rt.autoD'), ssw(ST.autoContinue==='1', 'saveAutoContinue'), 'checkpoint auto continue pause'),
    t('rt.grpPolicy'));
}

function secDirs(){
  const P = ST.paths||{};
  const row = (k,title,desc) => srow(title, desc,
    `<span class="st-val st-val-path">${esc(P[k]||'—')}</span>
     <button class="st-btn" onclick="revealDir('${k}')">${esc(t('dir.open'))}</button>`, title+' folder path directory');
  return spanel(
    row('data',t('dir.data'),t('dir.dataD'))
    + row('skills',t('dir.skills'),t('dir.skillsD'))
    + row('workspaces',t('dir.workspaces'),t('dir.workspacesD'))
    + srow(t('dir.runs'), t('dir.runsD',{n:(ST.runs||[]).length}),
        `<button class="st-btn" onclick="setExit('runs')">${esc(t('c.view'))}</button>`, 'runs history record'),
    t('dir.grpFolders'));
}

function secShortcuts(){
  /* 说明页不再手抄一份字面量：表里有什么，这里就有什么（见文件末尾的 KEYMAP）。
     作用域是真实差异，不是装饰：g 在哪都能按，s 只在设置页生效，i 只在输入框里有意义。
     没有做「操作」列 —— 键位是表里的常量，不能重绑，放假按钮没意义。 */
  const rows = KEYMAP.map(r =>
    [r.chord, t('sc.'+r.id), t('sc.'+r.id+'D'), r.scope, 'shortcut '+r.id]
  ).map(([k,tt,d,sc,x])=>`<div class="sc-tr" data-k="${kAttr(tt+' '+k+' '+x+' '+t('sc.scope.'+sc))}">
      <div class="sc-td"><span class="sc-name">${esc(tt)}</span>
        <span class="sc-desc">${esc(d)}</span></div>
      <div class="sc-td sc-td-k"><span class="st-keys">${k.split(' ').map(skey).join('')}</span></div>
      <div class="sc-td sc-td-s"><span class="sc-scope sc-scope-${sc}">${esc(t('sc.scope.'+sc))}</span></div>
    </div>`).join('');
  return `<div id="scBox">
    <div class="st-scq">${ico('search')}
      <input id="scQ" placeholder="${esc(t('sc.searchPh'))}" oninput="scFilter(this.value)"
        ${SET_Q.trim() ? 'disabled' : ''}></div>
    <div class="sc-card">
      <div class="sc-tr sc-thead">
        <div class="sc-td">${esc(t('sc.colCmd'))}</div>
        <div class="sc-td sc-td-k">${esc(t('sc.colKey'))}</div>
        <div class="sc-td sc-td-s">${esc(t('sc.colScope'))}</div>
      </div>
      ${rows}
    </div>
    <div class="st-empty st-hidden">${esc(t('sc.noHit'))}</div></div>`;
}
/* 键位页自己的过滤器：整页搜索会把别的分区一起摊开，找一个 Esc 不该看六张卡 */
window.scFilter = function(q){
  const box = document.getElementById('scBox');
  if(!box) return;
  if(SET_Q.trim()) return;   // 整页搜索在管这张表（框渲染时就 disable 了），两个过滤器别抢同一批行
  const s = (q||'').trim().toLowerCase();
  let n = 0;
  box.querySelectorAll('.sc-tr:not(.sc-thead)').forEach(r=>{
    const on = !s || (r.dataset.k||'').includes(s);
    r.classList.toggle('st-hidden', !on);
    if(on) n++;
  });
  const e = box.querySelector('.st-empty');
  if(e) e.classList.toggle('st-hidden', n>0);
};

function upStatusText(s){
  if(!s) return t('up.unknown');
  const m = {checking:t('up.checking'), available:t('up.hasNew',{v:s.latest}),
             current:t('up.isCurrent',{v:s.local}), downloading:t('up.downloadingPct',
               {p: s.size?Math.floor((s.got||0)*100/s.size):0}),
             ready:t('up.readyTip',{p:s.path||''}), error:t('up.errPrefix',{e:s.error||''})};
  return m[s.phase] || t('up.idle');
}

function secUpdate(){
  const u = ST.update || {};
  const apply = u.frozen
    ? `<button class="st-btn" onclick="applyUpdate()" ${u.phase==='ready'?'':'disabled'}>${esc(t('up.apply'))}</button>`
    : `<span class="st-state no"><i></i>${esc(t('up.applyNo'))}</span>`;
  /* 下载中给一条真刻度条：数字来自 got/size，和左下角胶囊同一份状态，不是装饰 */
  const pct = u.phase==='ready' ? 100
    : (u.phase==='downloading' && u.size) ? Math.floor((u.got||0)*100/u.size) : -1;
  const bar = pct < 0 ? '' : `<div class="st-prog"><i style="width:${pct}%"></i></div>`;
  return spanel(
      stIn(t('up.url'), t('up.urlD'), 'upUrl',
        (u.update_url===u.default_url ? '' : (u.update_url||'')), t('up.urlPh'),
        'saveUpdUrl()', 'update manifest url cos')
    + srow(t('up.status'), t('up.statusD',{v:u.local||''}),
        `<span class="st-val">${esc(upStatusText(u))}</span>${bar}
         <button class="st-btn" onclick="checkNow()">${ico('refresh')}${esc(t('up.check'))}</button>`,
        'update check version status progress')
    + srow(t('up.apply'), t('up.applyD'), apply, 'update install apply'),
    t('up.grp'));
}

window.applyUpdate = async function(){
  /* 设置页这颗按钮不再自己弹一套确认 —— 确认只有一处形状：居中浮层里那一行后果说明。
     所以它做的事是打开浮层并直接上膛，第二下才算数。 */
  if(!UP) UP = ST.update || null;
  if(!UP || !UP.frozen){ toast(t('up.applyNo')); return; }
  const c = document.getElementById('upCard');
  if(!c || c.hidden) window.upOpen();
  upArm('apply');
};

const MB1024 = 1048576;
const fmtBytes = n => n >= MB1024 ? (n/MB1024).toFixed(1)+' MB'
                     : n >= 1024  ? (n/1024).toFixed(0)+' KB' : (n||0)+' B';
function fmtDur(ms){
  const s = Math.round((ms||0)/1000);
  if ((window.APP && window.APP.lang) === 'en') {
    if (s < 60) return s+'s';
    const h = Math.floor(s/3600), m = Math.floor((s%3600)/60);
    return h ? h+'h '+m+'m' : m+'m '+(s%60)+'s';
  }
  // 中文里 "7h 2m" 读不成一句话；参考图写的是 "7 小时 2 分钟"
  if (s < 60) return s + ' ' + t('unit.sec');
  const h = Math.floor(s/3600), m = Math.floor((s%3600)/60), sec = s % 60;
  if (h) return m ? h+' '+t('unit.hour')+' '+m+' '+t('unit.min') : h+' '+t('unit.hour');
  return sec ? m+' '+t('unit.min')+' '+sec+' '+t('unit.sec') : m+' '+t('unit.min');
}
/* 亿/万只在中文用，英文走 K/M —— 直接写死一套单位会在另一语言里读不通 */
function fmtTok(n){
  n = n || 0;
  const zh = (window.APP && window.APP.lang) !== 'en';
  if (zh) {
    if (n >= 1e8) return (n/1e8).toFixed(1) + ' ' + t('unit.yi');
    if (n >= 1e4) return (n/1e4).toFixed(1) + ' ' + t('unit.wan');
    return String(n);
  }
  if (n >= 1e6) return (n/1e6).toFixed(1) + 'M';
  if (n >= 1e3) return (n/1e3).toFixed(1) + 'K';
  return String(n);
}
/* 热力图：一格一天，按列铺、每列 7 格。起始补空格把日期对齐到周日，
   否则格子会随数据量左右错位，看不出周节律。 */
/* 统计页的两个视图开关只作用于这一分区，不写进外观通道（那是要落库的全局偏好），
   所以刷新页面回到默认。切档与切范围都只重渲染这块，不重新拉接口。 */
let ST_MODE = 'day';
let ST_RANGE = 7;
const HM_WEEKS = 52;        /* 52 列 × 15px 节距 = 780，正好铺满设置页那张卡的宽度。
                               锚点取"今天那一周的周日"往回数 51 周，列数恒定 52；
                               以前按天数换算再补一周，非周日收尾时会多出第 53 列把网格顶出卡片。 */

const stSeg = (opts, cur, fn) => `<div class="st-seg" role="group">`
  + opts.map(([v, l]) => `<button type="button" class="st-segb"
      aria-pressed="${v === cur ? 'true' : 'false'}" onclick="${fn}('${v}')">${esc(l)}</button>`)
      .join('') + `</div>`;

const hmKey = d => `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;

/* 轴上的刻度不带年份（参考图是 "8月22日"），悬停卡片才带全年 */
function stDateShort(iso){
  const p = iso.split('-');
  return (window.APP && window.APP.lang) === 'en'
    ? `${t('mon.'+(+p[1]-1))} ${+p[2]}` : `${+p[1]}月${+p[2]}日`;
}

function stDateLong(iso){
  const p = iso.split('-');
  return (window.APP && window.APP.lang) === 'en'
    ? `${t('mon.'+(+p[1]-1))} ${+p[2]}, ${p[0]}`
    : `${p[0]}年${+p[1]}月${+p[2]}日`;
}

/* 三档共用同一套格子，只有读数不同 —— 周视图塌成一行反而看不出周节律，所以整列同色。
   后端按本地日期入库（time.strftime("%Y-%m-%d")），这里绝不能用 toISOString ——
   那是 UTC，UTC+8 下每格都会读成前一天，"今天"永远是空的。 */
function hmValues(daily, mode){
  const today = new Date(); today.setHours(0, 0, 0, 0);
  const start = new Date(today); start.setDate(start.getDate() - (HM_WEEKS - 1) * 7);
  start.setDate(start.getDate() - start.getDay());
  const cols = [];
  for (let w = 0; w < HM_WEEKS; w++){
    const one = [];
    for (let i = 0; i < 7; i++){
      const d = new Date(start); d.setDate(d.getDate() + w*7 + i);
      one.push(d > today ? null : hmKey(d));
    }
    cols.push(one);
  }
  const day = {}, week = {}, cum = {};
  let run = 0;
  cols.forEach(one => {
    let wk = 0;
    one.forEach(iso => { if(!iso) return;
      const v = ((daily||{})[iso]||{}).tokens || 0;
      day[iso] = v; wk += v; run += v; cum[iso] = run; });
    one.forEach(iso => { if(iso) week[iso] = wk; });
  });
  return { cols, val: mode === 'week' ? week : mode === 'cum' ? cum : day };
}

function tokenHeat(daily, mode){
  const m = mode || 'day';
  const hv = hmValues(daily, m);
  const cols = hv.cols, val = hv.val;
  // 分档按峰值等比（ceil(v/max*4)），不用分位数：分位数会把每个轻活日都推到 1~2 档，
  // 一整年看过去永远"满屏有色"，恰好抹掉了"哪天是我最好的一天"这个唯一信号。
  let mx = 1;
  cols.forEach(one => one.forEach(iso => { if (iso) mx = Math.max(mx, val[iso] || 0); }));
  const lvl = v => !v ? 0 : Math.min(4, Math.max(1, Math.ceil(v / mx * 4)));
  const colVal = one => { for (let i = one.length - 1; i >= 0; i--){ if (one[i]) return val[one[i]] || 0; } return 0; };
  const colTurns = one => one.reduce((a, iso) => a + (iso ? ((daily||{})[iso]||{}).turns || 0 : 0), 0);
  const grid = cols.map(one => {
    /* 周/累计档整列一个值，格子自下而上填（周日在顶、周六在底）—— 一列就是一根
       条形图。整列铺同一档会把"这周多少"读成"这周每天都这么多"。 */
    const cv = m === 'day' ? 0 : colVal(one);
    const fill = m === 'day' ? 7 : Math.max(cv > 0 ? 1 : 0, Math.ceil(cv / mx * 7));
    return '<div class="hm-col">' + one.map((iso, i) => {
      if (!iso) return '<i class="hm-cell hm-out"></i>';
      const v = val[iso] || 0, e = (daily||{})[iso] || {};
      const on = m === 'day' || i >= 7 - fill;
      // 悬停走自研提示：原生 title 有一秒延迟、样式跟系统、而且只能一行。
      // 两行之间用 &#10; 分隔 —— 属性值里的裸换行会被归一化成空格。
      const l1 = m === 'week' ? `${stDateLong(one[0])} – ${stDateLong(one[6] || one[0])}` : stDateLong(iso);
      /* 轮数只能按档求和：后端没有累计轮数序列，累加档里干脆不报这一项，
         也不要拿"这一天的轮数"配"整周/累计的 token 数"糊在一起。 */
      const l2 = m === 'cum' ? `${esc(t('st.cumTo'))} ${fmtTok(cv)} tokens`
             : m === 'week' ? `${fmtTok(cv)} tokens · ${colTurns(one)} ${esc(t('st.msgs'))}`
             : `${fmtTok(v)} tokens · ${(e.turns || 0)} ${esc(t('st.msgs'))}`;
      return `<i class="hm-cell ${'hm-l'+(on ? lvl(m === 'day' ? v : cv) : 0)}" data-tip-any="1" data-tip="${esc(l1)}&#10;${l2}"></i>`;
    }).join('') + '</div>';
  }).join('');
  // 月份轴和列在同一个循环里产出。以前是两套循环各数各的，
  // 27 对 27 只是巧合，谁动一边轴就会整体错位。
  // 标签槽只有 12px（文字靠 nowrap 溢出），所以两档之间至少隔两列才放得下 ——
  // 一年里唯一撞车的就是窗口起点：9 月中开、下一周就跨进 10 月。
  const axis = []; let lastM = -1, lastCol = -9;
  cols.forEach((one, w) => {
    const sun = one[0];
    const mo = sun ? +sun.split('-')[1] - 1 : -1;
    if (sun && mo !== lastM && w - lastCol >= 2){
      axis.push(`<span class="hm-mo">${esc(t('mon.'+mo))}</span>`);
      lastM = mo; lastCol = w;
    } else axis.push('<span class="hm-mo"></span>');
  });
  // 网格和轴必须在同一个横向滚动容器里，否则网格一滚，轴留在原地就对不上列了
  return `<div class="hm-wrap"><div class="hm-grid">${grid}</div>
      <div class="hm-axis">${axis.join('')}</div></div>`;
}

function stNoData(){
  return `<div class="st-nodata"><b>${esc(t('st.noData'))}</b>
    <span>${esc(t('st.noDataD'))}</span></div>`;
}

/* 手写 SVG：这个项目没有构建步骤也不联网，为两张图引一个图表库不值当。
   配色走 --chart-1..6（分类色，不随强调色变），图例、折线、环形、四处共用
   同一份分组结果，免得四张脸对不上。 */
const CHART_N = 6;
/* 参考图的图例与清单都只写模型名 —— 加上 "claude · " 前缀后五个条目就撑成两行了。
   只有同名模型挂在两个引擎下时才补引擎，否则那一条本来就说不清是谁的。 */
function stModelNames(rows){
  const seen = {};
  rows.forEach(b => { const k = b.model || ''; seen[k] = (seen[k] || 0) + 1; });
  return rows.map(b => (b.model && seen[b.model] > 1)
    ? (b.engine || '?') + ' · ' + b.model
    : (b.model || t('st.noModelInjected')));
}

function stSeries(byModel){
  const rows = (byModel || []).filter(b => b && (b.tokens || b.steps));
  /* 正好六条时六条全画 —— 第 7 档没有颜色了，但"六条 + 其他"那种一行只剩
     "其他"两个字的图例更难看。所以合并的触发条件是"超过六条"，切成 5 具名 + 其他。 */
  const split = rows.length > CHART_N ? CHART_N - 1 : rows.length;
  const top = rows.slice(0, split), names = stModelNames(rows);
  const out = top.map((b, i) => ({
    name: names[i], daily: b.daily || {}, tokens: b.tokens || 0, turns: b.turns || 0}));
  const rest = rows.slice(split);
  if (rest.length){
    const d = {};
    rest.forEach(b => { Object.keys(b.daily || {}).forEach(k => { d[k] = (d[k] || 0) + b.daily[k]; }); });
    out.push({name: t('st.others'), daily: d,
              tokens: rest.reduce((a, b) => a + (b.tokens || 0), 0),
              turns: rest.reduce((a, b) => a + (b.turns || 0), 0)});
  }
  return out;
}

function stDays(range){
  const today = new Date(); today.setHours(0, 0, 0, 0);
  const days = [];
  for (let i = range - 1; i >= 0; i--){
    const d = new Date(today); d.setDate(d.getDate() - i); days.push(hmKey(d));
  }
  return days;
}

/* 水平控制点的三次曲线：峰是圆的，和参考图那种折角分明的折线不是一回事 */
function stPath(vals, mx, W, H){
  const n = vals.length;
  if (!n) return '';
  const x = i => n === 1 ? W / 2 : i * (W / (n - 1));
  const y = v => H - Math.min(H, mx ? H * v / mx : 0);
  let d = `M${x(0).toFixed(1)},${y(vals[0]).toFixed(1)}`;
  for (let i = 1; i < n; i++){
    const cx = ((x(i - 1) + x(i)) / 2).toFixed(1);
    d += ` C${cx},${y(vals[i-1]).toFixed(1)} ${cx},${y(vals[i]).toFixed(1)} ${x(i).toFixed(1)},${y(vals[i]).toFixed(1)}`;
  }
  return d;
}

function stTrend(byModel, range){
  const series = stSeries(byModel);
  const days = stDays(range);
  const vals = series.map(b => days.map(k => b.daily[k] || 0));
  const mx = Math.max.apply(null, [1].concat.apply([1], vals));
  if (!series.some((b, i) => vals[i].some(v => v > 0))) return stNoData();
  const W = 1000, H = 186;
  let grid = '';
  for (let g = 1; g <= 3; g++){
    const yy = (H * g / 4).toFixed(1);
    grid += `<line class="st-gline" x1="0" y1="${yy}" x2="${W}" y2="${yy}"></line>`;
  }
  grid += `<line class="st-base" x1="0" y1="${H}" x2="${W}" y2="${H}"></line>`;
  const lines = series.map((b, i) =>
    `<path class="st-line ${'st-s'+(i % CHART_N + 1)}" vector-effect="non-scaling-stroke" d="${stPath(vals[i], mx, W, H)}"></path>`
  ).join('');
  const legend = `<div class="st-lgd">` + series.map((b, i) =>
    `<span class="st-lgdi"><i class="st-dot ${'st-c'+(i % CHART_N + 1)}"></i>${esc(b.name)}</span>`).join('') +
    `</div>`;
  // 首末标签贴绘图区两端（已经跟着卡片留了 18px），再多就压到卡片边框上了
  const step = Math.max(1, Math.round((days.length - 1) / 6));
  const ticks = [];
  for (let i = 0; i < days.length; i += step) ticks.push(days[i]);
  if (ticks[ticks.length - 1] !== days[days.length - 1]) ticks.push(days[days.length - 1]);
  return legend + `<div class="st-plot"><svg class="st-lines" viewBox="0 0 ${W} ${H}" `
    + `preserveAspectRatio="none" role="img" aria-label="${esc(t('st.trendAria'))}">`
    + grid + lines + `</svg></div>`
    + `<div class="st-cx">` + ticks.map(k => `<span>${esc(stDateShort(k))}</span>`).join('') + `</div>`;
}

/* 环形用一圈 <circle> 的 dasharray 拼出来：比手算弧形的 path 短，
   段与段之间留 1 单位空白，就是参考图上那道细缝。 */
function stModels(byModel){
  const rows = stSeries(byModel);
  if (!rows.length) return stNoData();
  const total = rows.reduce((a, b) => a + b.tokens, 0);
  const R = 79.5, C = 2 * Math.PI * R, D = 96;
  let acc = 0;
  const arcs = rows.map((b, i) => {
    const f = total ? b.tokens / total : 0;
    const on = Math.max(0, C * f - 1), off = C - on;
    const el = `<circle class="${'st-s'+(i % CHART_N + 1)}" cx="${D}" cy="${D}" r="${R}" fill="none" `
      + `stroke-width="33" vector-effect="non-scaling-stroke" `
      + `stroke-dasharray="${on.toFixed(2)} ${off.toFixed(2)}" `
      + `stroke-dashoffset="${(-C * acc).toFixed(2)}" transform="rotate(-90 ${D} ${D})"></circle>`;
    acc += f;
    return el;
  }).join('');
  const donut = `<div class="st-donut"><svg viewBox="0 0 192 192" role="img" `
    + `aria-label="${esc(t('st.donutAria'))}">${arcs}</svg>`
    + `<div class="st-dmid"><b>${esc(fmtTok(total))}</b><span>tokens</span></div></div>`;
  const list = `<div class="st-mlist">` + rows.map((b, i) =>
    `<div class="st-mrow"><i class="st-dot ${'st-c'+(i % CHART_N + 1)}"></i>`
    + `<div class="st-mmain"><div class="st-mname">${esc(b.name)}</div>`
    + `<div class="st-msub">${esc(fmtTok(b.tokens))} tokens</div></div>`
    + `<span class="st-mpct">${total ? Math.round(b.tokens / total * 100) : 0}%</span></div>`).join('')
    + `</div>`;
  return `<div class="st-donutrow">${donut}${list}</div>`;
}

function secStats(){
  const s = ST.stats || {};
  const bs = s.by_status || {};
  const pw = Object.entries(s.per_workflow || {}).sort((a,b)=>b[1]-a[1]);
  const orphans = s.orphans || [];
  const orphanBytes = orphans.reduce((a,o)=>a+(o.bytes||0), 0);
  const tk = s.tokens || {};
  const strip = `<div class="st-strip">
    <div><b>${esc(fmtTok(s.tokens_total))}</b><span>${esc(t('st.tokTotal'))}</span></div>
    <div><b>${esc(fmtTok(s.peak_day_tokens))}</b><span>${esc(t('st.peakDay'))}</span></div>
    <div><b>${esc(fmtDur(s.peak_step_ms))}</b><span>${esc(t('st.peakStep'))}</span></div>
    <div><b>${(s.streak_now||0)+' '+t('unit.day')}</b><span>${esc(t('st.streakNow'))}</span></div>
    <div><b>${(s.streak_best||0)+' '+t('unit.day')}</b><span>${esc(t('st.streakBest'))}</span></div>
  </div>`;
  const heat = stCard('',
      `<div class="st-cardtop"><div class="hm-title">${esc(t('st.heat'))}</div>`
        + stSeg([['day', t('st.modeDay')], ['week', t('st.modeWeek')], ['cum', t('st.modeCum')]],
                ST_MODE, 'stSetMode') + `</div>`
      + tokenHeat(s.daily || {}, ST_MODE));
  const rangeRow = `<div class="st-rangerow"><span>${esc(t('st.range'))}</span>`
    + stSeg([['7', t('st.last7')], ['30', t('st.last30')]], String(ST_RANGE), 'stSetRange')
    + `</div>`;
  const trend = stCard(t('st.trend'), stTrend(s.by_model, ST_RANGE));
  const models = stCard(t('st.models'), stModels(s.by_model));
  const usage = stCard(t('st.grpUsage'),
      srow(t('st.runs'), t('st.runsD',{done:bs.done||0, failed:bs.failed||0,
          running:(bs.running||0)+(bs.revising||0), waiting:bs.waiting||0,
          cancelled:bs.cancelled||0}),
        `<span class="st-val">${s.runs||0}</span>`, 'stats runs total status')
    + srow(t('st.steps'), t('st.stepsD',{d:s.steps_done||0, t:s.steps_total||0}),
        `<span class="st-val">${s.steps_done||0} / ${s.steps_total||0}</span>`, 'stats steps')
    + srow(t('st.tools'), t('st.toolsD',{n:s.tool_calls||0, t:s.agent_turns||0}),
        `<span class="st-val">${s.tool_calls||0}</span>`, 'stats tool calls turns')
    + srow(t('st.time'), t('st.timeD'),
        `<span class="st-val">${esc(fmtDur(s.duration_ms))}</span>`, 'stats duration time')
    + srow(t('st.cost'), t('st.costD'),
        `<span class="st-val">${(s.cost_usd||0).toFixed(4)}</span>`, 'stats cost usd money')
    + srow(t('st.tokens'), t('st.tokensD'),
        `<span class="st-val">${esc(fmtTok(s.tokens_total))}</span>`, 'stats token tokens usage')
    + srow(t('st.tokIO'), t('st.tokIOD'),
        `<span class="st-val">${esc(fmtTok(tk.in))} / ${esc(fmtTok(tk.out))}</span>`, 'token input output')
    + srow(t('st.tokCache'), t('st.tokCacheD'),
        `<span class="st-val">${esc(fmtTok(tk.cache_read))}</span>`, 'token cache read')
    + srow(t('st.tokReason'), t('st.tokReasonD'),
        `<span class="st-val">${esc(fmtTok(tk.reason))}</span>`, 'token reasoning thought')
    + srow(t('st.disk'), t('st.diskD',{n:s.workspaces||0}),
        `<span class="st-val">${esc(fmtBytes(s.workspace_bytes))}</span>`, 'stats disk bytes workspace')
  );
  const foot = `<div class="st-foot"><button class="st-btn" onclick="stReload()">`
    + `${ico('refresh')}${esc(t('c.refresh'))}</button></div>`;
  return `<div class="st-stats">` + strip + heat + rangeRow + trend + models + usage
  + (pw.length ? stCard(t('st.grpFlows'),
      pw.map(([k,v])=>srow(esc(k), t('st.perFlowD'),
        `<span class="st-val">${v}</span>`, 'stats per workflow')).join('')) : '')
  + stCard(t('st.grpClean'),
      srow(t('st.orphans'), t('st.orphansD'),
        orphans.length
          ? `<span class="st-state no"><i></i>${orphans.length} · ${esc(fmtBytes(orphanBytes))}</span>`
          : `<span class="st-state ok"><i></i>${esc(t('st.none'))}</span>`,
        'stats orphan leftover cleanup')
      + (orphans.length
          ? `<div class="st-cleanrow"><button class="st-btn st-btn-danger" onclick="stCleanupOrphans()">${ico('trash')} ${esc(t('st.cleanupBtn'))}</button></div>`
          : '')
  ) + foot + `</div>`;
}

/* ---------------- Agent 能力：两家 CLI 自己的配置面（只读盘点） ----------------
   只回名字与条数：那些文件里就是真密钥（settings.json 的 env、config.toml 的 bearer
   token），所以 mcp / hooks / plugins 连预览口都不开。改动请走各自的官方入口。 */
let CAPS_ENGINE = '';
let CAPS_VIEW = null;   /* {eng, key, text, dirty} —— 预览/编辑弹窗现在读的那一份 */
const capsEngine = () => CAPS_ENGINE || ST.defaultEngine || 'claude';
const CAPS_PREVIEW = {memory:1, skills:1, commands:1, agents:1};

function secCaps(){
  const eng = capsEngine();
  const d = (ST.caps || {})[eng] || {items: []};
  const head = `<div class="st-block"><div class="st-panel">
      <div class="st-cardtop"><div class="hm-title">${esc(t('caps.title'))}</div>`
    + stSeg([['claude', t('eng.claude')], ['codex', t('eng.codex')]], eng, 'capsSetEngine')
    + `</div><div class="st-note">${esc(t('caps.note'))}</div></div></div>`;
  return head + (d.items || []).map(it => {
    const label = t('caps.' + it.key);
    const open = it.found
      ? `<button class="st-btn" onclick="capsOpen('${jsq(eng)}','${jsq(it.key)}')">`
        + esc(t('dir.open')) + `</button>` : '';
    let rows;
    if (!it.count){
      rows = srow(label, t('caps.none') + ' · ' + it.path, '', 'capabilities none cli ' + label);
    } else if (CAPS_PREVIEW[it.key]){
      rows = it.entries.map(e => srow(esc(e.name), fmtBytes(e.bytes) + ' · ' + it.path,
        `<button class="st-btn" onclick="capsView('${jsq(eng)}','${jsq(it.key)}','${jsq(e.name)}')">`
        + esc(t('c.view')) + `</button>`, 'capabilities ' + label)).join('');
    } else {
      rows = it.entries.map(e => srow(esc(e.name), t('caps.nameOnly'), '',
                                      'capabilities ' + label)).join('');
    }
    return spanel(rows, label, open);
  }).join('');
}

window.capsSetEngine = function(v){ CAPS_ENGINE = v; secRepaint('caps'); };
window.capsOpen = async function(eng, key){
  const url = '/api/reveal?which=agent&engine=' + encodeURIComponent(eng)
            + '&key=' + encodeURIComponent(key);
  const r = await post(url).catch(e => ({detail: String(e)}));
  if (r && r.detail) toast(r.detail);
};
window.capsView = async function(eng, key, name){
  const url = '/api/agents/capabilities/' + encodeURIComponent(eng) + '/'
            + encodeURIComponent(key) + (name ? '/' + encodeURIComponent(name) : '');
  const d = await api(url).catch(e => ({detail: String((e && e.message) || e)}));
  if (d.detail){ toast(d.detail); return; }
  CAPS_VIEW = {eng, key, text: d.text || ''};
  _lockScroll(true);
  const root = document.createElement('div');
  root.id = 'capsViewRoot';
  /* 只有记忆文件给编辑入口（其余类目是 CLI 自己的格式，改坏了归官方入口管）。
     被截断过的正文一律不给编辑：那是一份不完整的副本，存回去等于把尾巴抹掉。 */
  const canEdit = key === 'memory' && !d.truncated;
  root.innerHTML = `<div class="modal open" onclick="if(event.target===this)capsClose()">
    <div class="modal-box sk-view-modal">
      <div class="modal-top"><div class="pv-head"><h3>${esc(name || key)}</h3>
        <span class="muted-sm mono">${esc(d.path)}</span></div>
        <button class="modal-x" onclick="capsClose()">×</button></div>
      <div class="sk-view-body" id="capsBody"><div class="ws-md">${window.mdToHtml(d.text || '')}</div>
        ${d.truncated ? `<div class="st-note">${esc(t('caps.truncated'))}</div>` : ''}</div>
      <div class="sk-view-foot"><span class="spacer"></span>
        ${canEdit ? `<button class="btn btn-ghost btn-sm" onclick="capsEditMem()">${esc(t('c.edit'))}</button>` : ''}
        <button class="btn btn-ghost btn-sm" onclick="capsClose()">${esc(t('c.close'))}</button>
      </div></div></div>`;
  document.body.appendChild(root);
};
/* 读→改同一个缓冲区：textarea 里就是 GET 回来的全文，保存时整块 PUT 回去。
   路径不在这里传 —— 后端按引擎名自己算，界面拿不到也改不了它。 */
window.capsEditMem = function(){
  const body = document.getElementById('capsBody');
  if (!body || !CAPS_VIEW) return;
  body.innerHTML = `<textarea class="pv-input mono sk-content" id="capsTa" spellcheck="false"
      oninput="capsDirty()">${esc(CAPS_VIEW.text)}</textarea>`;
  const ta = document.getElementById('capsTa');
  const foot = body.parentElement.querySelector('.sk-view-foot');
  foot.innerHTML = `<span class="spacer"></span>
    <button class="btn btn-ghost btn-sm" onclick="capsClose()">${esc(t('c.cancel'))}</button>
    <button class="btn btn-primary btn-sm" onclick="capsSaveMem()">${esc(t('c.save'))}</button>`;
  ta.focus();
  ta.setSelectionRange(ta.value.length, ta.value.length);
};
window.capsDirty = function(){ if (CAPS_VIEW) CAPS_VIEW.dirty = true; };
window.capsSaveMem = async function(){
  const ta = document.getElementById('capsTa');
  if (!ta || !CAPS_VIEW) return;
  const r = await put('/api/agents/capabilities/memory',
                      {engine: CAPS_VIEW.eng, content: ta.value})
    .catch(e => ({detail: String(e)}));
  if (r && r.detail){ toast(r.detail); return; }
  CAPS_VIEW.dirty = false;
  toast(t('caps.memSaved'), true);
  ST.caps = (await api('/api/agents/capabilities').catch(() => null)) || ST.caps;
  secRepaint('caps');   // 条目的字节数是盘点出来的，不重算就还是旧数字
  window.capsClose();
};
window.capsClose = async function(){
  if (CAPS_VIEW && CAPS_VIEW.dirty && document.getElementById('capsTa')
      && !(await window.ffAsk({title:t('ff.unsavedTitle'), body:t('caps.unsaved'),
        ok:t('ff.leave'), cancel:t('ff.keep')}))) return;
  CAPS_VIEW = null;
  const r = document.getElementById('capsViewRoot');
  if (r) r.remove();
  _lockScroll(false);
};

/* 只重渲染当前这一块：切档、切范围、刷新、换引擎都走这里 ——
   整页重渲染会重新拉那八个接口，还会把滚动位置还回顶部。
   搜索结果态下分区在 [data-sec] 里，标题得一起补回去。 */
function secRepaint(id){
  const inSearch = !!(id && id !== SET_SECTION);
  const host = inSearch ? document.querySelector('#stBody [data-sec="' + id + '"]')
                        : document.getElementById('stSec');
  if (!host){ renderSettings(SET_SECTION); return; }
  const sec = id || SET_SECTION;
  host.innerHTML = (inSearch ? `<div class="st-h2">${esc(secTitle(sec))}</div>` : '')
    + sectionBody(sec);
  // 页头那枚 chip 在 #stSec 外面，只换分区它会留下上一次的读数（切引擎后还写着旧引擎）
  const chip = document.querySelector('.st-hchip');
  if (chip && SEC_CHIP[sec]) chip.textContent = String(SEC_CHIP[sec]() || '');
  if (SET_Q.trim()) applySearch();
}
window.stSetMode = function(v){ ST_MODE = v; secRepaint('stats'); };
window.stSetRange = function(v){ ST_RANGE = +v || 7; secRepaint('stats'); };
window.stReload = async function(){
  const st = await api('/api/stats').catch(()=>null);
  if (st) ST.stats = st;
  secRepaint('stats');
  toast(t('st.reloaded'), true);
};
/* 只删「孤儿」—— 没有任何运行记录指向的工作区目录。删了不可恢复，所以确认框
   里必须把数量和体积报出来；后端另有 409 挡活跃运行，这里把它的 detail 原样透出。 */
window.stCleanupOrphans = async function(){
  const orphans = (ST.stats || {}).orphans || [];
  if (!orphans.length) return;
  const bytes = orphans.reduce((a, o) => a + (o.bytes || 0), 0);
  const ok = await window.ffAsk({danger: true, title: t('st.cleanupBtn'),
    body: t('st.cleanupAsk', {n: orphans.length, size: fmtBytes(bytes)}),
    ok: t('ff.delete')});
  if (!ok) return;
  const r = await post('/api/workspaces/cleanup-orphans').catch(e => ({detail: String(e)}));
  if (r && r.detail){ toast(r.detail); return; }
  toast(t('st.cleanupDone', {n: (r.removed || []).length, size: fmtBytes(r.bytes || 0)}), true);
  if ((r.failed || []).length) toast(r.failed.map(x => x.name + ': ' + x.err).join('; '));
  stReload();
};

function secAbout(){
  const ready = ST.agents.filter(a=>a.found).map(a=>t('eng.'+a.engine));
  return spanel(
    srow(t('brand.full'), esc(t('brand.sub')+' · '+t('about.name')),
      `<span class="st-val">v${esc(ST.version||'')}</span>`, 'version about app loom')
    + srow(t('about.api'), t('about.port',{p:location.port||'8000'}),
        `<span class="st-state ok"><i></i>FastAPI</span>`, 'server api local')
    + srow(t('about.engines'), t('about.enginesD',{n:ready.length})+' · '+esc(ready.join(' / ')),
        '', 'engines detected cli')
    + srow(t('about.counts'), t('about.countsD',{s:(ST.skills||[]).length,p:(ST.flows||[]).length,
        r:(ST.runs||[]).length,pre:PRESETS.length}), '', 'counts skills workflows runs presets')
    + srow(t('dir.data'), '', `<span class="st-val st-val-path">${esc((ST.paths||{}).data||'—')}</span>`, 'data folder path'),
    t('about.grpInfo'));
}

window.saveUpdUrl = async function(){
  const url = ((document.getElementById('upUrl')||{}).value||'').trim();
  const r = await post('/api/update/url', {url}).catch(e=>({detail:String(e)}));
  if(r.detail){ toast(r.detail); return; }
  ST.update = r; UP = r; paintUpdate();
  toast(t('up.saved', {v: r.latest || '—'}), true);
  renderSettings(SET_SECTION);
};
window.checkNow = async function(){
  const r = await post('/api/update/check').catch(()=>null);
  if(!r){ toast(t('up.reqFail')); return; }
  ST.update = r; UP = r; paintUpdate();
  if(r.phase==='error'){ toast(r.error||t('up.failed')); }
  else { toast(t('up.checked',{s:upStatusText(r)}), true); }
  await upAutoDownload();     // 手动重检也一样：有就下，别让人再点一次
  renderSettings(SET_SECTION);
};

const SEC_RENDER = {appearance:secAppearance, engines:secEngines, presets:secPresets,
                    runtime:secRuntime, caps:secCaps, dirs:secDirs,
                    shortcuts:secShortcuts, stats:secStats, update:secUpdate, about:secAbout};
const SEC_FLAT = () => SET_SECTIONS.flatMap(g=>g.items);
/* 页头那枚 chip 只报"这一屏现在生效的是什么"，且只挂有真实数据源的分区 ——
   没数据可报的分区就不挂，免得造一个永远不变的装饰。 */
const SEC_CHIP = {
  appearance: () => t('ap.theme.'+(window.APP.theme || 'dark')),
  engines: () => { const a = ST.agents || []; const f = a.filter(x=>x.found).length;
                   return f ? t('set.chipEngines',{n:f}) : t('set.chipNone'); },
  caps: () => t('eng.' + capsEngine()),
  update: () => ST.version ? 'v' + ST.version : '',
  about:  () => ST.version ? 'v' + ST.version : '',
};
const secTitle = id => { const s = SEC_FLAT().find(x=>x[0]===id); return s? t(s[1]) : ''; };

function settingsMain(){
  if(SET_Q.trim()){
    return `<div class="st-h1">${esc(t('set.search'))}</div>
      <div class="st-hsub">${esc(SET_Q.trim())}</div>`
      + SET_SECTIONS.flatMap(g=>g.items).map(([id])=>
          `<div data-sec="${id}"><div class="st-h2">${esc(secTitle(id))}</div>${sectionBody(id)}</div>`).join('');
  }
  const sub = t('set.'+SET_SECTION+'D');
  const chip = (SEC_CHIP[SET_SECTION] || (() => ''))();
  const meta = (chip || sub) ? `<div class="st-hmeta">
      ${chip?`<span class="st-hchip">${esc(chip)}</span>`:''}
      ${sub?`<div class="st-hsub">${esc(sub)}</div>`:''}</div>` : '';
  return `<div class="st-h1">${esc(secTitle(SET_SECTION))}</div>
    ${meta}<div id="stSec">${sectionBody(SET_SECTION)}</div>`;
}
function sectionBody(id){ return (SEC_RENDER[id]||secAppearance)(); }


window.renderSettings = async function(section){
  viewLoading();
  if(section && section!=='settings') SET_SECTION = section;
  const [r, ag, sk, pl, rn, hp, up, st, cp] = await Promise.all([
    api('/api/providers').catch(()=>({presets:[],default:null})),
    api('/api/agents').catch(()=>null),
    api('/api/skills').catch(()=>({skills:[]})),
    api('/api/pipelines').catch(()=>({pipelines:[]})),
    api('/api/runs').catch(()=>({runs:[]})),
    api('/api/health').catch(()=>({})),
    api('/api/update').catch(()=>null),
    api('/api/stats').catch(()=>null),
    api('/api/agents/capabilities').catch(()=>null),
  ]);
  ST.update = up || null; ST.stats = st || null; ST.caps = cp || null;
  PRESETS = r.presets||[];   // 设置页自己的清单只认这一个变量
  ST.presets = PRESETS;      // 首页模型 chip 也要这份候选，跟着增删一起刷新
  ST.skills = sk.skills||[]; ST.flows = pl.pipelines||[]; ST.runs = rn.runs||[];
  if(ag){
    ST.agents = ag.agents||[]; ST.defaultEngine = ag.default_engine||'';
    ST.claudeCli = ag.claude_cli||''; ST.codexCli = ag.codex_cli||'';
    ST.paths = ag.paths||{};
    ST.agentTimeout = ag.agent_timeout;
    ST.permMode = ag.permission_mode||'';
    ST.effortOptions = ag.effort_options||['auto'];
    ST.reasoningEffort = ag.reasoning_effort||'auto';
    ST.stepRetry = ag.step_retry||'0'; ST.autoContinue = ag.auto_continue||'0';
  }
  ST.version = hp.version||'';

  const navHtml = SET_SECTIONS.map(g=>`<div class="st-grp">${esc(t(g.grp))}</div>`
    + g.items.map(([id,key,ic])=>`<button type="button" class="st-item ${(!SET_Q&&id===SET_SECTION)?'active':''}"
        data-nav="${id}" data-k="${kAttr(t(key)+' '+key)}" onclick="setGo('${id}')">
        ${ico(ic)}<span>${esc(t(key))}</span></button>`).join('')).join('');

  const keep = document.querySelector('.st-main');
  const keepTop = keep ? keep.scrollTop : 0;
  $('#app').dataset.shell = 'settings';
  $('#view').classList.remove('with-composer');
  $('#view').innerHTML = `
    <div class="st-shell">
      <aside class="st-side">
        <button type="button" class="st-back" onclick="setExit()">${ico('chevronLeft')}<span>${esc(t('set.back'))}</span></button>
        <div class="st-search">${ico('search')}<input id="stQ" placeholder="${esc(t('set.search'))}"
          value="${esc(SET_Q)}" oninput="setQuery(this.value)"></div>
        <div id="stNav">${navHtml}</div>
      </aside>
      <div class="st-main"><div class="st-inner" id="stBody">${settingsMain()}</div></div>
    </div>`;
  if(SET_Q) applySearch();
  const m = document.querySelector('.st-main');
  if(m && keepTop) m.scrollTop = keepTop;
};

function applySearch(){
  const q = SET_Q.trim().toLowerCase();
  const body = document.getElementById('stBody');
  if(!body) return;
  let hitRows = 0, hitSecs = 0;
  body.querySelectorAll('[data-sec]').forEach(sec=>{
    let inSec = 0;
    const blocks = [...sec.querySelectorAll('.st-block')];
    if(!blocks.length){
      // 键位表是张表，没有 .st-block/.st-row 外壳。照下面的走法它永远 0 命中，
      // 结果整段被搜索藏掉 —— 所以这类分区直接认行上的 data-k。
      const trs = [...sec.querySelectorAll('.sc-tr[data-k]')];
      const shown = trs.filter(r=>!q || (r.dataset.k||'').includes(q)).length;
      trs.forEach(r=>r.classList.toggle('st-hidden',
        !!q && !(r.dataset.k||'').includes(q)));
      if(shown){ inSec = 1; hitRows += shown; }
    }
    blocks.forEach(bl=>{
      const rows = [...bl.querySelectorAll('.st-row')];
      if(!rows.length){
        // 热力图、实时预览这类卡里一行 .st-row 都没有，没法按行过滤。
        // 一律留下是不行的：那样随便敲一串乱码它也算命中，"没有匹配"永远出不来。
        // 折中是拿卡自己的标题文案比一次 —— "token" 命中热力图标题，"zzzz" 谁都不命中。
        // 卡标题用的是 .st-pttl（统计页那六张），漏进这份清单就等于那张卡搜不到。
        const k = [...bl.querySelectorAll('.st-label,.hm-title,.spv-title,.st-pttl,.st-t,.st-d')]
          .map(e=>e.textContent).join(' ').toLowerCase();
        const on = !q || k.includes(q) || pyInit(k).includes(q);
        bl.classList.toggle('st-hidden', !on);
        if(on){ inSec++; hitRows++; }
        return;
      }
      let shown = 0;
      rows.forEach(r=>{
        const on = !q || (r.dataset.k||'').includes(q);
        r.classList.toggle('st-hidden', !on);
        // 整行铺开的输入框是标签行的"下半身"，行藏了它必须跟着藏，否则裸留一个框
        const sub = r.nextElementSibling;
        if(sub && sub.classList.contains('st-rowsub')) sub.classList.toggle('st-hidden', !on);
        if(on) shown++;
      });
      bl.classList.toggle('st-hidden', shown===0);
      if(shown){ inSec++; hitRows++; }
    });
    sec.classList.toggle('st-hidden', inSec===0);
    if(inSec) hitSecs++;
  });
  const empty = body.querySelector('.st-noresult');
  if(!hitRows && !empty){
    const d = document.createElement('div');
    d.className = 'st-empty st-noresult'; d.textContent = t('set.noHit');
    body.appendChild(d);
  } else if(hitRows && empty) empty.remove();
  const sub = body.querySelector('.st-hsub');
  if(sub && q) sub.textContent = SET_Q.trim()+' · '+t('set.hits',{n:hitSecs});
  const live = new Set([...body.querySelectorAll('[data-sec]:not(.st-hidden)')].map(e=>e.dataset.sec));
  document.querySelectorAll('#stNav .st-item').forEach(it=>
    it.classList.toggle('st-hidden', !!q && !live.has(it.dataset.nav)));
}

window.setGo = function(id){ SET_SECTION = id; SET_Q = ''; PATH_EDIT=''; renderSettings(id); };
window.setExit = function(view){ const a=document.getElementById('app'); if(a) delete a.dataset.shell;
  SET_Q=''; PATH_EDIT=''; nav.go(view||'pipelines'); };
window.setQuery = function(v){ SET_Q = v||'';
  const body = document.getElementById('stBody'); if(!body) return;
  body.innerHTML = settingsMain();
  if(SET_Q.trim()) applySearch();
  else document.querySelectorAll('#stNav .st-item').forEach(i=>{
    i.classList.remove('st-hidden');
    i.classList.toggle('active', i.dataset.nav===SET_SECTION);
  });
};

window.apSet = async function(key, val){
  await window.setAppearance({[key]: val});
  if(key !== 'lang') return;          // 主题/字号/缩放/宽度都是 CSS 变量，即时生效
  renderNav(document.querySelector('#mainNav .sb-item.active')?.dataset.v || 'settings');
  renderSettings();
};
window.apSetFont = function(v){ window.apSet('font', v); };

window.editPath = function(eng){ PATH_EDIT = eng; renderSettings();
  setTimeout(()=>{ const el=document.getElementById('path_'+eng); if(el){ el.focus(); el.select(); } },60); };
window.cancelPath = function(){ PATH_EDIT=''; renderSettings(); };
window.savePath = async function(eng){
  const el = document.getElementById('path_'+eng);
  const body = eng==='claude' ? {claude_cli:(el?el.value:'').trim()} : {codex_cli:(el?el.value:'').trim()};
  PATH_EDIT='';
  const r = await post('/api/agents', body).catch(e=>({detail:String(e)}));
  if(r.detail){ toast(r.detail); }
  else toast(t('eng.saved'), true);
  renderSettings();
};
window.setDefaultEngine = async function(eng){
  const r = await post('/api/agents', {default_engine:eng}).catch(e=>({detail:String(e)}));
  if(r.detail){ toast(r.detail); return; }
  toast(t('eng.saved'), true);
  await loadAgents(); renderSettings();
};
async function postAgents(body){
  const r = await post('/api/agents', body).catch(e=>({detail:String(e)}));
  if(r.detail){
    /* 以前这里把 r 原样返回，而调用方一律写 `if(!await postAgents(...)) return;` ——
       {detail:...} 是真值，那四道守卫一次也没生效过：保存失败照样改 ST，
       于是页面上显示一个服务端根本没收下的值。失败要返回假值，并把这一节按 ST
       里的旧值重画回去（控件已经跟着用户的点击换了显示，不重画就是假成功）。 */
    toast(r.detail);
    renderSettings();
    return null;
  }
  toast(t('eng.saved'), true);
  return r;
}
window.saveTimeout = async function(v){
  if(!await postAgents({agent_timeout:v})) return;
  ST.agentTimeout = v;
};
window.saveRetry = async function(v){
  if(!await postAgents({step_retry:v})) return;
  ST.stepRetry = v;
};
window.saveEffort = async function(v){
  if(!await postAgents({reasoning_effort:v})) return;
  ST.reasoningEffort = v;
};
window.saveAutoContinue = async function(on){
  if(!await postAgents({auto_continue:on?'1':'0'})) return;
  ST.autoContinue = on?'1':'0';
};
window.revealDir = async function(k){
  const r = await post('/api/reveal?which='+encodeURIComponent(k)).catch(e=>({detail:String(e)}));
  if(r.detail) toast(r.detail);
};
/* ---------------- 预设（列表已并入设置 › API 接入） ---------------- */
let PRESETS = [];

/* ---------------- 预设弹窗 ---------------- */
let PF_EDIT=null;
function pfOpenNew(){ pfOpenModal(null); }
window.pfOpenNew = pfOpenNew;

function pfOpenModal(p){
  PF_EDIT = p;
  document.body.style.overflow='hidden';
  const cat = window.PROVIDER_CATALOG||[];
  const grid = cat.map(t2=>{
    const letter=(t2.name||'?').slice(0,1).toUpperCase();
    return `<div class="pv-item ${p&&p.name===t2.name?'pv-sel':''}" data-name="${esc(t2.name)}" onclick="pfPick('${esc(t2.name)}')">
      <span class="pv-ico">${esc(letter)}</span><span class="pv-name">${esc(t2.name)}</span></div>`;
  }).join('') + `<div class="pv-item pv-item-custom" data-name="__custom__" onclick="pfPickCustom()">
      <span class="pv-ico pv-ico-custom">＋</span><span class="pv-name">${esc(t('pr.custom'))}</span></div>`;

  const root=document.createElement('div');
  root.id='pfModalRoot';
  root.innerHTML=`<div class="modal open" onclick="if(event.target===this)pfCloseModal()">
    <div class="modal-box pv-modal">
      <div class="modal-top"><div class="pv-head"><h3>${p?esc(t('pr.editTitle')):esc(t('pr.newTitle'))}</h3></div>
        <button class="modal-x" onclick="pfCloseModal()">×</button></div>
      <div class="pv-scroll">
        ${p?'':`<div class="pv-search-wrap"><input class="pv-input" id="pfQ" placeholder="${esc(t('pr.searchVendor'))}" oninput="pfDrawQ()"></div>
        <div class="pv-grid" id="pfGrid">${grid}</div><div class="pv-divider"></div>`}
        <div class="pv-form pv-flat">
          <div class="pv-row2">
            <div class="pv-f"><label class="pv-label">${esc(t('pr.displayName'))} <b class="req">*</b></label>
              <input class="pv-input" id="pfDisp" value="${esc((p&&((p.extra&&p.extra.display_name)||p.name))||'')}"></div>
            <div class="pv-f"><label class="pv-label">${esc(t('pr.protocol'))}</label>
              ${ffSelect([{v:'anthropic',label:'Anthropic Messages'},{v:'openai',label:'OpenAI compatible'}],
                (!p||p.provider==='anthropic')?'anthropic':'openai', {id:'pfProvider'})}</div>
          </div>
          <div class="pv-f"><label class="pv-label">${esc(t('pr.base'))} <b class="req">*</b></label>
            <input class="pv-input mono" id="pfBase" placeholder="https://api.example.com/anthropic" value="${esc(p?p.api_base:'')}"></div>
          <div class="pv-f"><label class="pv-label">${esc(t('pr.key'))} ${p?`<span class="muted">${esc(t('pr.keyKeep'))}</span>`:'<b class="req">*</b>'}</label>
            <input class="pv-input mono" id="pfKey" type="password" value=""></div>
          <div class="pv-f"><label class="pv-label">${esc(t('pr.model'))}</label>
            <div style="display:flex;gap:8px">
              <input class="pv-input mono" id="pfModel" placeholder="claude-sonnet-4-5 / deepseek-chat" value="${esc(p?p.model:'')}" style="flex:1">
              <button class="btn btn-ghost btn-sm" onclick="pfFetchModels()">${esc(t('pr.fetchModels'))}</button>
            </div>
            <div class="pv-fhint" id="pfModelHint">${esc(t('pr.wireHint'))}</div></div>
          <div class="pv-fhint">${esc(t('pr.baseHint'))}</div>
        </div>
      </div>
      <div class="modal-foot">
        <button class="btn btn-ghost" onclick="pfCloseModal()">${esc(t('c.cancel'))}</button>
        <button class="btn btn-primary" onclick="pfSave()">${p?esc(t('pr.saveEdit')):esc(t('pr.saveNew'))}</button>
      </div>
    </div></div>`;
  document.body.appendChild(root);
  window.PF_PICKED = p ? {name:p.name, api_base:p.api_base, provider:p.provider} : null;
}
window.pfCloseModal=function(){
  const r=document.getElementById('pfModalRoot'); if(r) r.remove();
  document.body.style.overflow='';
};
window.pfDrawQ=function(){
  const q=(document.getElementById('pfQ')||{}).value||'';
  const grid=document.getElementById('pfGrid'); if(!grid) return;
  const items=(window.PROVIDER_CATALOG||[]).filter(x=>!q||x.name.toLowerCase().includes(q.toLowerCase()));
  grid.innerHTML=items.map(x=>`<div class="pv-item" data-name="${esc(x.name)}" onclick="pfPick('${esc(x.name)}')">
    <span class="pv-ico">${esc((x.name||'?').slice(0,1).toUpperCase())}</span><span class="pv-name">${esc(x.name)}</span></div>`).join('')
    +`<div class="pv-item pv-item-custom" onclick="pfPickCustom()"><span class="pv-ico pv-ico-custom">＋</span>
      <span class="pv-name">${esc(t('pr.custom'))}</span></div>`;
};
window.pfPick=function(name){
  const x=(window.PROVIDER_CATALOG||[]).find(v=>v.name===name); if(!x) return;
  window.PF_PICKED={name:x.name, api_base:x.api_base||'', provider:x.provider||'anthropic', site:x.site||''};
  const grid=document.getElementById('pfGrid');
  if(grid) grid.querySelectorAll('.pv-item').forEach(el=>el.classList.toggle('pv-sel',el.dataset.name===x.name));
  const disp=document.getElementById('pfDisp'); if(disp&&!disp.value.trim()) disp.value=x.name;
  const prov=document.getElementById('pfProvider');
  if(prov) window.ffSetValue('pfProvider', x.provider==='anthropic'?'anthropic':'openai',
                             x.provider==='anthropic'?'Anthropic Messages':'OpenAI compatible');
  const base=document.getElementById('pfBase'); if(base) base.value=x.api_base||'';
};
window.pfPickCustom=function(){
  window.PF_PICKED=null;
  const grid=document.getElementById('pfGrid');
  if(grid) grid.querySelectorAll('.pv-item').forEach(el=>el.classList.toggle('pv-sel',el.dataset.name==='__custom__'));
};
window.pfFetchModels=async function(){
  const base=(document.getElementById('pfBase')||{}).value||'';
  const key=(document.getElementById('pfKey')||{}).value||'';
  if(!base){ toast(t('pr.needBase')); return; }
  toast(t('pr.modelsFetching'));
  try{
    const provider=(document.getElementById('pfProvider')||{}).value||'anthropic';
    const r=await post('/api/models/list',{api_base:base, api_key:key, provider,
      id:(PF_EDIT&&PF_EDIT.id)||0});   // 编辑已存预设时密钥不在前端，让服务端按 id 自己取
    if(!r.ok){ toast(t('pr.modelsFail',{err:r.error||''})); return; }
    const ids=(r.models||[]).map(x=>x.id||x.model||x.name||x).filter(Boolean).slice(0,200);
    const hint=document.getElementById('pfModelHint');
    if(hint) hint.textContent = ids.length
      ? (ids.slice(0,30).join(' · ') + (ids.length>30?` …${ids.length}`:''))
      : t('pr.modelsEmpty');
    if(ids.length) toast(t('pr.modelsLoaded',{n:ids.length}), true);
  }catch(e){ toast(t('pr.modelsFail',{err:e})); }
};
window.pfSave=async function(){
  const name=(document.getElementById('pfDisp')||{}).value||'';
  const provider=(document.getElementById('pfProvider')||{}).value||'anthropic';
  const api_base=(document.getElementById('pfBase')||{}).value||'';
  const api_key=(document.getElementById('pfKey')||{}).value||'';
  const model=(document.getElementById('pfModel')||{}).value||'';
  if(!name.trim()){ toast(t('pr.needName')); return; }
  if(!api_base.trim()){ toast(t('pr.needBase')); return; }
  const picked=window.PF_PICKED;
  /* extra 整列是覆盖写的。这个表单只拥有 display_name 和 site 两个键，
     别把没在界面上露面的 model_map / fallback_model（端点/模型阶梯靠它们）一起擦掉。 */
  const kept=(PF_EDIT && typeof PF_EDIT.extra==='object' && PF_EDIT.extra) ? PF_EDIT.extra : {};
  const body={name:name.trim(), provider, api_base:api_base.trim(), model:model.trim(),
              extra:{...kept, display_name:name.trim(), site:(picked&&picked.site)||''}};
  let r;
  if(PF_EDIT){ r=await put('/api/providers/'+PF_EDIT.id, {...body, api_key}).catch(e=>({detail:String(e)})); }
  else { r=await post('/api/providers', {...body, api_key}).catch(e=>({detail:String(e)})); }
  if(r.detail){ toast(r.detail); return; }
  toast(PF_EDIT?t('pr.saved'):t('pr.created'), true);
  pfCloseModal(); renderSettings();
};
window.pfEdit=function(id){
  const p=PRESETS.find(x=>x.id===id); if(!p) return;
  pfOpenModal({...p});
};
window.pfDel=async function(id){
  if(!(await window.ffAsk({danger:true, title:t('ff.delPreset'),
      body:t('pr.delConfirm'), ok:t('ff.delete')}))) return;
  const r=await del('/api/providers/'+id).catch(e=>({detail:String(e)}));
  if(r.detail){ toast(r.detail); return; }
  toast(t('pr.deleted')); renderSettings();
};
window.pfSetDefault=async function(id){
  const r=await post('/api/providers/'+id+'/default').catch(e=>({detail:String(e)}));
  if(r.detail){ toast(r.detail); return; }
  toast(t('pr.defaultSet'), true); renderSettings();
};
window.pfTest=async function(id){
  const p=PRESETS.find(x=>x.id===id); if(!p) return;
  toast(t('pr.testing'));
  const r=await post('/api/providers/test',{id, provider:p.provider, model:p.model})
    .catch(e=>({ok:false,msg:String(e)}));
  toast(r.ok?t('pr.testOk',{msg:r.msg?('：'+r.msg):''}):t('pr.testFail',{msg:r.msg||''}), !!r.ok);
};

/* ---------------- 下拉按钮（统一的 split-button 菜单） ----------------
   渲染一个隐藏 input 镜像（沿用传入的 id），所以老代码里 .value 的读法不受影响。 */
const FF_SEL = {};
let FF_N = 0;

/* note 在菜单里右对齐成第二列，在按钮上只能并成一行 —— .ff-sv 自带省略号，
   所以并起来也不会把长名字顶出按钮。 */
function ffFlat(o){
  if(!o) return '';
  return o.note ? `${o.label} · ${o.note}` : (o.label || '');
}

function ffSelect(opts, cur, cfg){
  cfg = cfg || {};
  const id = cfg.id || ('ffs'+(++FF_N));
  const key = 'ff'+id;
  FF_SEL[key] = {opts, id, onChange:cfg.onChange, arg:cfg.arg, action:!!cfg.action, short:!!cfg.short};
  const hit = opts.find(o=>String(o.v)===String(cur));
  /* short = 收起的那枚按钮只写名字，说明留在展开的菜单里。
     工具条上的 chip 宽度是按"一个词"算的，带上 note 会变成一整句话（实测把步骤条挤到溢出）。 */
  const flat = (o) => (cfg.short ? ((o && o.label) || '') : ffFlat(o));
  const label = flat(hit) || cfg.placeholder || flat(opts[0]) || '';
  return `<span class="ff-selw${cfg.mono?' ff-mono':''}${cfg.cls?' '+cfg.cls:''}">
    <input type="hidden" id="${esc(id)}" value="${esc(cur==null?'':cur)}">
    <button type="button" class="ff-sel" data-k="${esc(key)}" onclick="ffOpen(event,'${esc(key)}')">
      ${cfg.icon ? `<span class="ff-sic">${ico(cfg.icon)}</span>` : ''}
      <span class="ff-sv">${esc(label)}</span>
      <span class="ff-sdiv"></span>
      <span class="ff-sc">${ico('chevron')}</span>
    </button></span>`;
}

function ffMenuEl(){
  let m = document.getElementById('ffMenu');
  if(!m){ m = document.createElement('div'); m.id='ffMenu'; m.className='ff-menu'; m.hidden = true;
          document.body.appendChild(m); }
  return m;
}
window.ffClose = function(){
  const m=ffMenuEl(); m.hidden=true; m.innerHTML='';
  document.querySelectorAll('.ff-selw.open').forEach(e=>e.classList.remove('open'));
};
/* 从代码里改选中值必须走这里。隐藏 input 和按钮上那行 .ff-sv 文字是两个东西：
   只写 input，按钮会一直显示着上一项 —— 切步骤、选供应商都就是这么错给用户的。 */
window.ffSetValue = function(id, v, label){
  const hid = document.getElementById(id); if(!hid) return;
  hid.value = v;
  const sv = hid.parentElement && hid.parentElement.querySelector('.ff-sv');
  if(sv && label != null) sv.textContent = label;
};

/* FF_SEL 里没传 id 的选择器每次渲染都领一个新号（ffs1、ffs2…），旧条目以前没人删。
   编辑器每步两三枚、每重画一遍就换一批号，一个长会话能攒上千条，每条还攥着整份
   opts 数组（模型清单那种能到几百项）。判据只有一条：按钮不在 DOM 里了，
   那个 key 就再也点不出来，留着只是占内存。
   必须挂在 ffOpen 上而不是 ffSelect 里 —— 后者生成的是字符串，那一刻它的按钮
   还没进 DOM，边生成边删会把同一轮里刚登记的活条目一起删掉。 */
function ffPrune(){
  const live = new Set();
  document.querySelectorAll('.ff-sel').forEach(b => live.add(b.dataset.k));
  for(const k in FF_SEL){ if(!live.has(k)) delete FF_SEL[k]; }
}

window.ffOpen = function(e, key){
  e.stopPropagation();
  ffPrune();
  const cfg = FF_SEL[key]; if(!cfg) return;
  const m = ffMenuEl();
  if(!m.hidden && m.dataset.k===key){ ffClose(); return; }
  const btn = e.currentTarget;
  const cur = cfg.action ? null : (btn.parentElement.querySelector('input[type=hidden]')||{}).value;
  m.dataset.k = key;
  m.innerHTML = cfg.opts.map(o=>`<button type="button" class="ff-mi${String(o.v)===String(cur)?' on':''}"
      data-v="${esc(o.v)}"><span class="ff-ml">${esc(o.label)}</span>${o.note?`<i>${esc(o.note)}</i>`:''}</button>`).join('');
  m.hidden = false;
  const r = btn.getBoundingClientRect();
  const mw = m.offsetWidth, mh = m.offsetHeight;
  let left = Math.min(r.left, window.innerWidth - mw - 10);
  if(left < 10) left = 10;
  let top = r.bottom + 6;
  if(top + mh > window.innerHeight - 10) top = Math.max(10, r.top - mh - 6);
  m.style.left = left+'px'; m.style.top = top+'px';
  btn.parentElement.classList.add('open');
  const pick = m.querySelector('.ff-mi.on') || m.querySelector('.ff-mi');
  if(pick && pick.scrollIntoView) pick.scrollIntoView({block:'nearest'});
  m.querySelectorAll('.ff-mi').forEach(el=>el.addEventListener('click', (ev)=>{
    ev.stopPropagation();
    const v = el.dataset.v;
    if(!cfg.action){
      const hid = document.getElementById(cfg.id); if(hid) hid.value = v;
      /* 不能用 el.textContent：菜单项现在是 <span>名字</span><i>注</i>，
         拼起来会少了中间那个分隔符。回到选项本身取。 */
      const o = cfg.opts.find(x=>String(x.v)===String(v));
      const shown = cfg.short ? ((o && o.label) || el.textContent) : (ffFlat(o) || el.textContent);
      btn.querySelector('.ff-sv').textContent = shown;
    }
    ffClose();
    if(typeof cfg.onChange === 'function') cfg.onChange(v, cfg.arg);
    else if(cfg.onChange && window[cfg.onChange]) window[cfg.onChange](v, cfg.arg);
  }));
};

document.addEventListener('click', (e)=>{
  const m = document.getElementById('ffMenu');
  if(m && !m.hidden && !e.target.closest('#ffMenu') && !e.target.closest('.ff-sel')) ffClose();
});
window.ffSelect = ffSelect;

/* 动作菜单：和 ffSelect 共用 .ff-menu 外壳与那套开合逻辑，
   但项目是「点一下就去做」而不是「选一个值」。 */
window.ffActionMenu = function(e, items){
  e.stopPropagation();
  const m = ffMenuEl();
  if(!m.hidden && m.dataset.k === '__act'){ ffClose(); return; }
  const btn = e.currentTarget || e.target;   /* 图标按钮里点到的可能是内部 <svg> */
  m.dataset.k = '__act';
  m.innerHTML = items.map(it=>`<button type="button" class="ff-mi${it.danger?' ff-mi-danger':''}"
      data-act="${esc(it.v)}">${esc(it.label)}</button>`).join('');
  m.hidden = false;
  const r = btn.getBoundingClientRect(), mw = m.offsetWidth, mh = m.offsetHeight;
  let left = Math.min(r.right - mw, window.innerWidth - mw - 10);   /* 右对齐触发按钮 */
  if(left < 10) left = 10;
  let top = r.bottom + 6;
  if(top + mh > window.innerHeight - 10) top = Math.max(10, r.top - mh - 6);
  m.style.left = left + 'px'; m.style.top = top + 'px';
  m.querySelectorAll('.ff-mi').forEach(el=>el.addEventListener('click', (ev)=>{
    ev.stopPropagation();
    const it = items.find(x=>x.v === el.dataset.act);
    ffClose();
    if(it && it.run) it.run();
  }));
};

/* ---------------- 全局快捷键 ----------------
   一张表当唯一事实来源：设置页的「键位」说明和这里的分发读同一份数据，
   所以不会出现"说明里写了没绑 / 绑了没写说明"。参考实现同思路
   （ZCode packages/shared/src/shortcutCommands.ts:57-100）。
   scope: g = 全局；s = 只在设置页生效（由设置页自己消费）；i = 输入框内（Enter 族）。
   浏览器形态下 Ctrl+N / Ctrl+K 会被 Chrome/Edge 抢走（新窗口、地址栏），preventDefault
   拦不住 —— 所以不要求 Shift 的条目两种按法都认，浏览器里用 Ctrl+Shift+N 那条。
   打包成桌面壳后没有这个竞争。 */
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

/* 界面上任何"这键是干什么的"的提示都从表里取，别再手抄一遍字面量。 */
const chordOf = (id) => (KEYMAP.find(r=>r.id===id) || {}).chord || '';

function keyMatches(r, e){
  const ctrl = !!(e.ctrlKey || e.metaKey);
  if(r.key !== (e.key||'').toLowerCase()) return false;
  if(r.mod.includes('ctrl') !== ctrl) return false;
  if(r.mod.includes('shift') && !e.shiftKey) return false;   /* 不要求 Shift 的两可，见上面注释 */
  if(!r.mod.includes('ctrl') && (e.altKey || e.shiftKey)) return false;
  return true;
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

const inSettings = () => {
  const a = document.getElementById('app');
  return !!(a && a.dataset.shell==='settings');
};

document.addEventListener('keydown', (e)=>{
  if(e.repeat) return;   // 长按会一路连发，每次都打一次 setAppearance POST
  const hit = KEYMAP.find(r => r.scope==='g' && keyMatches(r, e));
  if(hit && hit.id !== 'close'){ e.preventDefault(); KEY_ACTION[hit.id](); return; }
  if(e.key==='Escape'){
    /* 关闭顺序 = 谁画在上面先关谁。z 刻度里 --z-menu(100) 压过 --z-modal(60)，
       所以菜单/下拉先关，再关更新浮层 —— 反过来就会出现"浮层关了、菜单还飘在那"。
       （这里以前写反了，注释还声称浮层在最上：源码顺序看着对，实际层级是另一回事。） */
    const fm = document.getElementById('ffMenu');
    if(fm && !fm.hidden){ e.preventDefault(); ffClose(); return; }
    const fd = document.getElementById('sbFind');
    if(fd && !fd.hidden){ e.preventDefault(); fd.hidden = true; return; }
    const pop = document.getElementById('sbPop');
    if(pop && !pop.hidden){ e.preventDefault(); closeFootMenu(); return; }
    const uc = document.getElementById('upCard');
    if(uc && !uc.hidden){ e.preventDefault(); window.upClose(); return; }
    const m = document.querySelector('.modal.open');
    if(m){ const x = m.querySelector('.modal-x'); if(x){ e.preventDefault(); x.click(); } return; }
    if(inSettings()){ e.preventDefault(); window.setExit(); }
    return;
  }
  if(e.key==='/' && !e.ctrlKey && !e.metaKey && !e.altKey && !e.shiftKey
     && !isTyping(e.target) && inSettings()){
    const q = document.getElementById('stQ');
    if(q){ e.preventDefault(); q.focus(); q.select(); }
  }
});

/* ---------------- 启动 ---------------- */
async function boot(){
  await window.loadAppearance();
  await loadAgents();
  paintShell(); shellDragBind(); shellResizeBind();
  renderNav('pipelines');
  nav.resolve();
  upInit();
}
if(document.readyState==='loading') document.addEventListener('DOMContentLoaded', boot);
else boot();

})();
