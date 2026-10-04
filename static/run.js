/* =====================================================================
 * Loom 织流 运行控制台（#/run/<id> · #/runs）—— Codex 式转录 + 底部输入面板
 * ===================================================================== */
(function(){
'use strict';
const $ = s => document.querySelector(s);
const t = window.t;
const ico = window.icon;
const esc = s => String(s??'').replace(/[&<>"']/g, c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const _api = (u,o) => !o || !o.method || o.method==='GET' ? window.voyraRead(u,o) : fetch(u,o).then(r=>r.json());
const _post = (u,b) => _api(u,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b||{})});
const toast = (m,ok) => window.ffToast(m,ok);
const ART_URL = (runId,name) => '/api/runs/'+encodeURIComponent(runId)+'/artifacts/'+encodeURI(name);

/* 运行记录里的 steps 可能是数组，也可能是旧数据留下的对象（DB 里确实存着 {"oops":1}）。
   统一从这里取，别让 .filter/.map 在脏数据上把整页炸成错误态。 */
const runSteps = (u) => Array.isArray(u && u.steps) ? u.steps : [];
const dur = ms => { const s=Math.round((ms||0)/1000);
  return s<60 ? s+'s' : t('run.durLong',{m:Math.floor(s/60), s:s%60}); };

/* ---------------- 运行列表（Voyra v11 模块 5：高密度表格） ---------------- */
window.renderRuns = async function(){
  window.viewLoading();
  const RS = window.RUN_ST();
  const runs = (await _api('/api/runs')).runs||[];
  window.__chrome = {title:t('nav.runs'), icon:'runs'};   /* 这页只看历史，下任务走侧栏入口 */
  const row = u => {
    const steps = runSteps(u);
    const done = steps.filter(s=>s.status==='done').length;
    const pct = steps.length ? Math.round(done/steps.length*100) : 0;
    return `<tr class="rl-row" onclick="nav.go('run/${esc(u.id)}')">
      <td>${renderBadge(RS[u.status]||u.status, u.status)}</td>
      <td><div class="rl-cell-main">
        <span class="rl-label">${esc(u.label||u.pipeline)}</span>
        <code class="rl-brief">${esc(u.id)}${u.brief?' · '+esc(u.brief):''}</code></div></td>
      <td><div class="rl-progress-box">
        <span class="mono">${done}/${steps.length} · ${pct}%</span>
        <span class="rl-progress-bar"><i style="width:${pct}%"></i></span></div></td>
      <td class="muted-sm">${esc(u.created_at||'')}</td>
      <td><div class="rl-head-actions" onclick="event.stopPropagation()">
        <button class="pf-op pf-op-start" onclick="nav.go('run/${esc(u.id)}')">${esc(t('c.view'))}</button>
        <button class="pf-op pf-op-danger" onclick="runDelete('${esc(u.id)}')">${esc(t('c.delete'))}</button></div></td>
    </tr>`;
  };
  $('#view').innerHTML = `
    <div class="runs-list-layout view-enter">
      <div class="runs-list-header">
        <div class="rl-head-title"><h2>${esc(t('nav.runs'))}</h2>
          <span class="muted-sm">${esc(t('home.plRuns',{n:runs.length}))}</span></div>
        <div class="rl-head-actions">
          <button class="btn btn-primary btn-sm" onclick="taskModal()">${ico('plus')} ${esc(t('nav.newTask'))}</button>
        </div>
      </div>
      <div class="runs-table-card">
        <table class="rl-table">
          <thead><tr>
            <th>${esc(t('run.colStatus'))}</th>
            <th>${esc(t('run.brief'))}</th>
            <th>${esc(t('run.proc'))}</th>
            <th>${esc(t('run.colCreated'))}</th>
            <th></th>
          </tr></thead>
          <tbody>${runs.length ? runs.map(row).join('')
            : `<tr><td colspan="5"><div class="empty-state">${ico('runs')}<p>${esc(t('home.recentEmpty'))}</p></div></td></tr>`}</tbody>
        </table>
      </div>
    </div>`;
};
window.runDelete = async function(id){
  if(!confirm(t('run.delConfirm'))) return;
  await _api('/api/runs/'+id, {method:'DELETE'}).catch(()=>({}));
  toast(t('run.deleted'));
  window.renderSidebarLists();
  renderRuns();
};

/* ---------------- 控制台状态 ---------------- */
let RUN = null;
let ARTS = {};
let LOGS = [];
let ES = null;
let ACTIVE_STEP = null;
let REVISER = {};
let CONVO = [];
let TRACE = {};
let FOLD = {};      // 步骤 → 是否展开全部轨迹

function chromeActions(u){
  const b = [];
  if(u.status==='waiting') b.push(`<button class="btn btn-primary btn-sm" onclick="runContinue()">${esc(t('run.continue'))}</button>`);
  if(u.status==='running') b.push(`<button class="btn btn-ghost btn-sm" onclick="runCancel()">${ico('stop')}${esc(t('run.stop'))}</button>`);
  if(u.status!=='running' && u.status!=='waiting') b.push(`<button class="btn btn-ghost btn-sm" onclick="runRerun(0)">${ico('refresh')}${esc(t('run.rerun'))}</button>`);
  b.push(`<button class="btn btn-ghost btn-sm" onclick="runDelete('${esc(u.id)}')">${esc(t('c.delete'))}</button>`);
  return b.join('');
}

/* 检查点挂起横幅（Voyra v11 · 模块 7）：waiting 状态必须在转录流顶部给出
   高优先级介入入口，而不是只靠一点色差。 */
function rcCheckpointBanner(u){
  const steps = runSteps(u);
  let idx = steps.findIndex(s => ['waiting','running','revising'].includes(s.status));
  if(idx < 0) idx = steps.findIndex(s => s.status !== 'done');
  if(idx < 0) idx = steps.length - 1;
  const s = steps[idx] || {};
  return `<div class="checkpoint-banner" role="alert">
    <div class="cp-banner-icon">${ico('warn')}</div>
    <div class="cp-banner-main">
      <div class="cp-banner-title">流程已暂停在检查点：步骤 ${idx + 1} (${esc(s.label || s.key || '')})</div>
      <div class="cp-banner-desc">智能体已完成本阶段任务并落盘至 <code>${esc(s.out || t('run.artifacts'))}</code>。
        请在右侧产物栏审阅内容，确认无误后点击「${esc(t('run.continue'))}」，或在下方输入修订指令。</div>
    </div>
    <div class="cp-banner-acts">
      <button class="btn btn-primary btn-sm" onclick="runContinue()">${ico('play')}${esc(t('run.continue'))}</button>
    </div>
  </div>`;
}

window.renderRunConsole = async function(runId){
  window.viewLoading();
  const d = await _api('/api/runs/'+encodeURIComponent(runId));
  if(!d || !d.run){ toast(t('run.notFound')); nav.go('runs'); return; }
  RUN = d.run; ARTS = d.artifacts||{}; LOGS = d.logs||[];
  WS = [];                               /* 清单跟着运行走，切回来重新拉 */
  TRACE = {}; FOLD = {}; CONVO = CONVO.filter(m=>m._run===runId);
  if(ACTIVE_STEP===null || ACTIVE_STEP>=runSteps(RUN).length)
    ACTIVE_STEP = Math.min(RUN.cur_step||0, Math.max(0,runSteps(RUN).length-1));
  drawConsole();
  connectStream(runId);
};

function drawConsole(){
  const u = RUN;
  const steps = runSteps(u);
  const done = steps.filter(s=>s.status==='done').length;
  const pct = steps.length ? Math.round(done/steps.length*100) : 0;
  window.__chrome = {title:u.label||u.pipeline, icon:'runs', actions:chromeActions(u)};
  window.paintChrome && window.paintChrome();
  $('#view').classList.add('with-composer');

  $('#view').innerHTML = `
    <div class="run-console-frame view-enter">
      <div class="run-main-stream">
        <div class="rp-bar">
          <div class="run-badge rb-${esc(u.status)}">${esc(window.RUN_ST()[u.status]||u.status)}</div>
          <div class="rp-track"><div class="rp-fill" style="width:${pct}%"></div></div>
          <span class="rp-pct">${pct}%</span>
          <span class="muted-sm">${esc(t('run.stepOf',{done, total:steps.length}))}</span>
        </div>

        ${u.status==='waiting' ? rcCheckpointBanner(u) : ''}

        ${u.brief?`<div class="card"><div class="card-h"><div><div class="ct">${esc(t('run.brief'))}</div>
          <div class="cs">${esc(t('run.briefSub'))}</div></div>
          <button class="btn btn-ghost btn-sm" onclick="toggleBrief()">${esc(t('c.view'))}</button></div>
          <div class="brief-text" id="briefBox">${esc(u.brief)}</div></div>`:''}

        ${u.error?`<div class="rs-fail-msg">${esc(u.error)}</div>`:''}

        <div class="transcript" id="transcript">${steps.map((s,i)=>stepBlock(s,i)).join('')}</div>

        ${(u.workdir||'')?`<div class="rt-wd">${ico('folder')}<span>${esc(t('run.workedIn'))}
          <b class="mono">${esc(u.workdir)}</b></span></div>`:''}

        ${composerHtml(u)}
      </div>

      <aside class="run-side-pane" aria-label="${esc(t('run.proc'))}">
        <div class="rsp-section">
          <div class="rsp-head"><b>${esc(t('run.proc'))}</b>
            <span class="rsp-badge" id="procCount">${done}/${steps.length}</span></div>
          <div class="rsp-body">${procCard()}</div>
        </div>
        <div class="rsp-section rsp-files">
          <div class="rsp-head"><b>${esc(t('run.artifacts'))}</b>
            <span class="rsp-badge" id="wsCount">${WS.length}</span>
            ${['running','revising','waiting'].includes(u.status)?`<span class="ws-live"><i></i>${esc(t('run.wsLive'))}</span>`:''}
            <span class="spacer"></span>
            <button class="pf-op" onclick="runRefreshArts(true)">${ico('refresh')}${esc(t('c.refresh'))}</button></div>
          <div class="rsp-body" id="runArts">${wsRows()}</div>
        </div>
      </aside>
    </div>`;
  drawConvo();
  wsWatch();                       /* 跑动中才轮询，状态一变这里就会停表 */
  if(!WS.length) wsTick();
}

function toggleBriefOpen(){
  const b = document.getElementById('briefBox');
  if(b) b.classList.toggle('hidden');
}
window.toggleBrief = toggleBriefOpen;

/* ---------------- 工作区：实时文件面板 ----------------
   智能体是在子进程里直接写盘的，没有任何事件可订阅，所以跑动期间定点轮询
   /files（一次 scandir，几十个小文件而已）。停下就立刻停表，不留后台定时器。 */
let WS = [];
let WS_TIMER = null;
const WS_HOT_SEC = 20;    /* 「刚写入」按 mtime 距今算，不按轮询相位算 ——
                             后者会让标记只活 0–3 秒，写盘时机差一点就整轮看不见 */

const fmtB = n => { n = n || 0;
  return n < 1024 ? n + ' B' : n < 1048576 ? (n/1024).toFixed(1) + ' KB' : (n/1048576).toFixed(1) + ' MB'; };
const ago = sec => { if(!sec) return ''; const d = Math.max(0, Math.floor(Date.now()/1000) - sec);
  return d < 60 ? 'now' : window.ffRelDate(new Date(sec*1000).toISOString()); };
const outNames = () => new Set(runSteps(RUN).map(s => s.out).filter(Boolean));

function wsRows(){
  const outs = outNames();
  const files = WS.length ? WS : [...outs].map(n => ({path:n, bytes:0, mtime:0, kind:'text'}));
  if(!files.length) return `<div class="pf-empty">${esc(t('run.noArtifacts'))}</div>`;
  return files.map(f => {
    const isOut = outs.has(f.path);
    const chg = f.mtime && (Date.now()/1000 - f.mtime) < WS_HOT_SEC;
    return `
    <div class="pl-card-row art-row">
      <div class="pl-row-main"><div class="pl-row-title">
        <span class="ws-ic">${ico(WS_ICON[f.kind] || 'file')}</span>
        <span class="pl-row-name mono">${esc(f.path)}</span>
        ${isOut?`<span class="ff-tag">${esc(t('run.wsOut'))}</span>`:''}
        ${chg?`<span class="ws-chip">${esc(t('run.wsChg'))}</span>`:''}
        <span class="muted-sm">${f.bytes?esc(fmtB(f.bytes)):'·'}${f.mtime?' · '+esc(ago(f.mtime)):''}</span></div></div>
      <div class="pl-row-ops" onclick="event.stopPropagation()">
        <button class="pf-op" onclick="runViewArt('${jsq(f.path)}')">${esc(t('c.view'))}</button>
        <a class="pf-op" href="${ART_URL(RUN.id,f.path)}" download>${esc(t('c.download'))}</a>
      </div>
    </div>`;
  }).join('');
}
const WS_ICON = {image:'eye', pdf:'file', text:'file', binary:'package'};

function wsPaint(){
  const box = document.getElementById('runArts');
  if(box) box.innerHTML = wsRows();
  const n = document.getElementById('wsCount');
  if(n) n.textContent = String(WS.length);
}

async function wsTick(){
  if(!RUN) return;
  /* 面板已经不在页面上（切到别的视图）→ 顺手停表，别留一个后台轮询 */
  if(!document.getElementById('runArts')){
    if(WS_TIMER){ clearInterval(WS_TIMER); WS_TIMER = null; }
    return;
  }
  const d = await _api('/api/runs/'+encodeURIComponent(RUN.id)+'/files').catch(()=>null);
  if(!d || !d.files) return;
  WS = d.files;
  wsPaint();
}

function wsWatch(){
  const live = RUN && ['running','revising','waiting'].includes(RUN.status);
  if(live && !WS_TIMER) WS_TIMER = setInterval(wsTick, 3000);
  if(!live && WS_TIMER){ clearInterval(WS_TIMER); WS_TIMER = null; }
}

/* ---------------- 步骤：转录块 ---------------- */
const KIND_ICON = {tool:'tool', status:'chevron', note:'bolt', err:'warn'};

function traceLines(s, i){
  const rows = (TRACE[i] && TRACE[i].length) ? TRACE[i] : (s.trace||[]);
  if(!rows.length) return '';
  const all = rows.map(x=>`<div class="ts-line ${esc(x.kind||'status')}">${ico(KIND_ICON[x.kind]||'tool')}
    ${x.name?`<b>${esc(x.name)}</b>`:''}<span>${esc(x.text||'')}</span></div>`).join('');
  if(rows.length<=10 || FOLD[i]) return all;
  return `<button type="button" class="ts-line ts-more" onclick="runFold(${i})">${ico('chevron')}<span>${esc(t('run.moreLines',{n:rows.length-10}))}</span></button>`
    + rows.slice(-10).map(x=>`<div class="ts-line ${esc(x.kind||'status')}">${ico(KIND_ICON[x.kind]||'tool')}
        ${x.name?`<b>${esc(x.name)}</b>`:''}<span>${esc(x.text||'')}</span></div>`).join('');
}

/* 轨迹折叠行是真的按钮，不是提示文字：点了就地展开这一步的全部轨迹。
   以前这行写着"点标题栏展开"但没人接 —— 标题栏只管整步开合，展开不到轨迹。 */
window.runFold = function(i){
  FOLD[i] = true;
  refreshTranscript();
};

function stepLog(s, i){
  if(s.meta && s.meta.log) return s.meta.log;
  if(!s.key) return '';
  const p = String(i+1).padStart(2,'0')+'_'+s.key+'_';
  const hit = LOGS.find(L=>L.name.startsWith(p));
  return hit ? hit.name : '';
}

function stepBlock(s, i){
  const RS = window.RUN_ST();
  const st = s.status||'pending';
  const open = i===ACTIVE_STEP;
  const meta = s.meta||{};
  const art = s.out && ARTS[s.out]!==undefined;
  const iconBody = st==='done' ? ico('check') : String(i+1);
  const stateCls = st==='done'?'is-done':st==='running'?'is-running':st==='failed'?'is-failed':
                   st==='revising'?'is-running':st==='waiting'?'is-waiting':'';
  return `
  <div class="ts-step ${stateCls} ${open?'open':''}" data-i="${i}">
    <div class="ts-head" onclick="runToggleStep(${i})">
      <div class="ts-ico">${iconBody}</div>
      <div class="ts-name">${esc(s.label||s.key)}</div>
      <div class="ts-meta">
        ${s.engine_used?`<span>${esc(window.ENGINE_LABEL(s.engine_used))}</span>`:''}
        ${meta.tools?`<span>${meta.tools} ${esc(t('run.toolUnit'))}</span>`:''}
        ${meta.duration_ms?`<span>${dur(meta.duration_ms)}</span>`:''}
        <span class="run-badge rb-${esc(st)}">${esc(RS[st]||st)}</span>
        ${st!=='running'?`<button class="pf-op" onclick="event.stopPropagation();runRerun(${i})">${ico('refresh')}${esc(t('run.rerunFrom'))}</button>`:''}
        ${(()=>{ const lg=stepLog(s,i); return lg?`<button class="pf-op" onclick="event.stopPropagation();runShowLog('${jsq(lg)}')" title="${esc(t('run.logHint'))}">${ico('terminal')}${esc(t('run.log'))}</button>`:''; })()}
      </div>
    </div>
    <div class="ts-body">
      ${s.skill?`<div class="ts-line"><b>${esc(t('ed.mainSkill'))}</b><span>${esc(s.skill)}</span></div>`:''}
      ${traceLines(s,i)}
      ${(s.delta||'').trim()?`<pre class="run-delta" id="delta-${i}">${esc((s.delta||'').slice(-8000))}</pre>`:''}
      ${st==='failed'&&s.msg?`<div class="ts-line err">${ico('warn')}<span>${esc(s.msg)}</span></div>`:''}
      ${art?`<div class="ts-art">${ico('file')}<code>${esc(s.out)}</code>
        <button class="pf-op" onclick="runViewArt('${jsq(s.out)}')">${esc(t('c.view'))}</button>
        <span class="muted">${esc(t('c.words',{n:(ARTS[s.out]||'').length}))}</span></div>`:''}
    </div>
  </div>`;
}

/* ---------------- 右上角：进程面板 ----------------
   只读 RUN.steps 的状态，不另存一份 —— 转录区和进程卡永远说同一句话。 */
const PROC_ICON = {
  done:      {ic:'checkCircle', cls:'ok'},
  running:   {ic:'spinner',     cls:'live'},
  revising:  {ic:'spinner',     cls:'live'},
  waiting:   {ic:'pause',       cls:'wait'},
  failed:    {ic:'warn',        cls:'bad'},
  cancelled: {ic:'circle',      cls:'dim'},
  pending:   {ic:'circle',      cls:'dim'},
};
let PROC_USER = null;      // 用户手动切过就临时以它为准，运行状态一跳变就交还给策略
let _procLive = null, _procShape = '';
const PROC_POLICIES = ['always', 'idle', 'pill'];

function procPolicy(){
  const p = (window.APP && window.APP.procPanel) || 'idle';
  return PROC_POLICIES.includes(p) ? p : 'idle';
}
function runIsLive(){
  return runSteps(RUN).some(s => ['running','revising','waiting'].includes(s.status));
}
/* 「跑完收成胶囊」是默认档：还在跑就摊开给人盯，跑完就收起来让位给正文 */
function procOpen(){
  if(PROC_USER !== null) return PROC_USER;
  const p = procPolicy();
  if(p === 'always') return true;
  if(p === 'pill') return false;
  return runIsLive();
}
function procLatest(){
  const steps = runSteps(RUN);
  for(let i = steps.length - 1; i >= 0; i--){
    if((steps[i].status || 'pending') !== 'pending') return steps[i];
  }
  return steps[steps.length - 1] || null;
}

function procRows(){
  const steps = runSteps(RUN);
  return steps.map((s,i)=>{
    const st = s.status || 'pending';
    const m = PROC_ICON[st] || PROC_ICON.pending;
    return `<button class="pc-row ${m.cls}${i===ACTIVE_STEP?' on':''}" onclick="procJump(${i})">
      <span class="pc-ic ${m.cls==='live'?'sp':''}">${ico(m.ic)}</span>
      <span class="pc-t">${esc(s.label||s.key||(''+(i+1)))}</span>
      ${st==='failed'&&s.meta&&s.meta.log
        ? `<span class="pc-log" role="button" title="${esc(t('run.log'))}"
             onclick="event.stopPropagation();runShowLog('${jsq(s.meta.log)}')">${ico('terminal')}</span>`
        : ''}</button>`;
  }).join('');
}

/* 图标按钮静止时只有图标，指针进来才把文字标签撑开 —— 所以 aria-label 才是可访问名，
   不再叠一层 tooltip，否则同一个按钮会同时飘出两套说明。 */
function procActs(open){
  return `<span class="pc-acts">
    <button class="pc-btn" aria-label="${esc(t('run.procPolicy'))}" onclick="procPolicyMenu(event)">
      <i class="pc-lbl">${esc(t('run.procPolicy'))}</i><span class="pc-glyph">${ico('more')}</span></button>
    <button class="pc-btn" aria-label="${esc(t('run.procToggle'))}" onclick="procToggle()">
      <i class="pc-lbl">${esc(t(open?'run.procCollapse':'run.procExpand'))}</i>
      <span class="pc-glyph">${ico(open?'collapse':'expand')}</span></button>
  </span>`;
}

function procCard(){
  const steps = runSteps(RUN);
  if(!steps.length) return '';
  const done = steps.filter(s=>s.status==='done').length;
  if(!procOpen()){
    const last = procLatest();
    const m = PROC_ICON[(last && last.status) || 'pending'] || PROC_ICON.pending;
    return `<aside class="proc-card pill" id="procCard">
      <button class="pc-btn pp-act" aria-label="${esc(t('run.procExpand'))}" onclick="procToggle()">
        <i class="pc-lbl">${esc(t('run.procExpand'))}</i></button>
      <span class="pp-state ${m.cls}${m.cls==='live'?' sp':''}">${ico(m.ic)}</span>
      <span class="pp-t">${esc((last && (last.label||last.key)) || '')}</span>
    </aside>`;
  }
  return `<aside class="proc-card" id="procCard">
    <div class="pc-head">
      <span class="pc-title">${esc(t('run.proc'))}</span>
      <span class="pc-count">${done}/${steps.length}</span>
      ${procActs(true)}
    </div>
    <div class="pc-list">${procRows()}</div></aside>`;
}

function procShapeKey(){
  return (procOpen()?'o':'c') + '|' + doneCount() + '|' +
    runSteps(RUN).map(s=>s.status).join(',');
}
function doneCount(){ return runSteps(RUN).filter(s=>s.status==='done').length; }

function paintProc(){
  const live = runIsLive();
  if(live !== _procLive){ _procLive = live; PROC_USER = null; }   // 状态跳变，交还给展开策略
  const host = document.getElementById('procCard');
  if(!host) return;
  const k = procShapeKey();
  if(k !== _procShape){ host.outerHTML = procCard(); _procShape = k; return; }
  const list = document.querySelector('#procCard .pc-list');
  if(list) list.innerHTML = procRows();
  const cnt = document.querySelector('#procCard .pc-count');
  if(cnt) cnt.textContent = doneCount()+'/'+(((RUN&&RUN.steps)||[]).length);
  const pc = document.getElementById('procCount');
  if(pc) pc.textContent = doneCount()+'/'+(((RUN&&RUN.steps)||[]).length);
}

window.procToggle = function(){
  PROC_USER = !procOpen();
  _procShape = '';
  paintProc();
};

window.procPolicyMenu = function(ev){
  ev.stopPropagation();
  const old = document.getElementById('pcMenu');
  if(old){ procCloseMenu(); return; }
  const r = ev.currentTarget.getBoundingClientRect();
  const cur = procPolicy();
  const el = document.createElement('div');
  el.className = 'pc-menu'; el.id = 'pcMenu';
  el.setAttribute('role', 'menu');
  el.innerHTML = PROC_POLICIES.map(p =>
    `<button role="menuitemradio" aria-checked="${p===cur?'true':'false'}" class="pcm-item${p===cur?' on':''}" onclick="procSetPolicy('${p}')">
      <span>${esc(t('run.policy.'+p))}</span>${ico('check')}</button>`).join('');
  document.body.appendChild(el);
  el.style.top = (r.bottom + 6) + 'px';
  el.style.left = Math.max(8, r.right - el.offsetWidth) + 'px';
  document.addEventListener('click', procCloseMenu);
};
function procCloseMenu(){
  const m = document.getElementById('pcMenu');
  if(m) m.remove();
  document.removeEventListener('click', procCloseMenu);
}
window.procSetPolicy = function(p){
  if(!PROC_POLICIES.includes(p)) return;
  if(window.apSet) window.apSet('procPanel', p);
  else if(window.APP) window.APP.procPanel = p;
  PROC_USER = null; _procShape = '';
  procCloseMenu();
  paintProc();
};
window.procJump = function(i){
  ACTIVE_STEP = i;                  // 点进程卡就是"我要看这一步"，已展开的也要跟过来
  const box = document.getElementById('transcript');
  const el = box && box.children[i];
  const s = document.getElementById('rvStep');
  if(s) s.value = String(i);
  if(!el){ paintProc(); return; }
  if(!el.classList.contains('open')){
    const head = el.querySelector('.ts-head');
    if(head) head.click();          // 展开走既有开合逻辑，别在这儿复制一份状态机
  }
  paintProc();
  el.scrollIntoView({block:'center', behavior:'smooth'});
};

/* ---------------- 底部输入面板 ---------------- */
function composerHtml(u){
  const steps = runSteps(u);
  const running = u.status==='running'||u.status==='revising';
  const cur = steps[Math.min(u.cur_step||0, steps.length-1)] || {};
  return `
  <div class="composer">
    <div class="composer-inner">
      ${running?`<div class="cp-state">${ico('bolt')}<span>${esc(t('run.runningOn',{label:cur.label||cur.key||''}))}</span>
        <span class="spacer"></span><button class="pf-op" onclick="runCancel()">${esc(t('run.stop'))}</button></div>`:''}
      ${u.status==='waiting'?`<div class="cp-state">${ico('play')}<span>${esc(t('run.checkpointWait').trim())}</span>
        <span class="spacer"></span><button class="pf-op pf-op-start" onclick="runContinue()">${esc(t('run.continue'))}</button></div>`:''}
      <div id="runConvo"></div>
      <div class="cp-row">
        ${ffSelect(steps.map((s,i)=>({v:String(i), label:(i+1)+'. '+(s.label||s.key)})),
          String(ACTIVE_STEP), {id:'rvStep', cls:'ff-ghost'})}
        <textarea class="cp-input" id="rvText" rows="1" placeholder="${esc(t('run.composerPh'))}"
          oninput="cpGrow(this)" onkeydown="cpKey(event)"></textarea>
        <button class="cp-send" onclick="runRevise()" title="${esc(t('run.send'))}">${ico('send')}</button>
      </div>
    </div>
  </div>`;
}
window.cpGrow = function(el){ el.style.height='auto'; el.style.height=Math.min(el.scrollHeight,160)+'px'; };
window.cpKey = function(e){
  /* 中文输入法回车是在"确认候选词"，不是发送。不判 isComposing 会把半截话发出去 ——
     而这个产品的主语言就是中文。keyCode 229 是老 WebKit 上 isComposing 不成立时的兜底。 */
  if(e.isComposing || e.keyCode===229) return;
  if(e.key==='Enter' && !e.shiftKey){ e.preventDefault(); runRevise(); }
};

/* ---------------- SSE ---------------- */
function connectStream(runId){
  if(ES){ ES.close(); ES=null; }
  const es = new EventSource('/api/runs/'+encodeURIComponent(runId)+'/stream');
  ES = es;
  es.onmessage = e => { let ev; try{ ev = JSON.parse(e.data); }catch(_){ return; } handleEvent(ev, runId); };
}

function handleEvent(ev, runId){
  if(!RUN || RUN.id!==runId) return;
  if(ev.type==='state'){
    const prev = RUN.status;
    const remote = ev.run;
    if(remote){
      (remote.steps||[]).forEach((rs,i)=>{
        const local = RUN.steps && RUN.steps[i];
        if(local && local.delta && !rs.delta) rs.delta = local.delta;
        if(local && (TRACE[i]||[]).length && !(rs.trace||[]).length) rs.trace = TRACE[i];
      });
      RUN = remote;
      if(ev.artifacts) ARTS = ev.artifacts;
      if(prev!==RUN.status){ redraw(); window.renderSidebarLists(); }
      else refreshTranscript();
    }
    return;
  }
  if(ev.type==='delta'){
    const i = ev.index;
    if(RUN.steps && RUN.steps[i]){
      RUN.steps[i].delta = (RUN.steps[i].delta||'') + ev.text;
      RUN.steps[i].status = 'running';
    }
    updateDeltaPane(i);
  }
  else if(ev.type==='step_start'){
    if(RUN.steps && RUN.steps[ev.index]){ RUN.steps[ev.index].status='running'; RUN.steps[ev.index].delta=''; }
    TRACE[ev.index]=[]; FOLD[ev.index]=false;
    RUN.cur_step = ev.index; ACTIVE_STEP = ev.index;
    redraw();
  }
  else if(ev.type==='step_done'){
    if(RUN.steps && RUN.steps[ev.index]){
      RUN.steps[ev.index].status='done';
      if(ev.step) Object.assign(RUN.steps[ev.index], ev.step);
    }
    runRefreshArts(true);
    redraw();
  }
  else if(ev.type==='tool' || ev.type==='status' || ev.type==='note'){
    appendTrace(ev.index, {kind:ev.type, name:ev.name||'', text:ev.text||''});
  }
  else if(ev.type==='checkpoint'){ toast(t('run.checkpointWait').trim(), true); }
  else if(ev.type==='revise_delta'){
    REVISER[ev.index] = true;
    if(RUN.steps && RUN.steps[ev.index]){
      RUN.steps[ev.index].status='revising';
      RUN.steps[ev.index].delta = (RUN.steps[ev.index].delta||'') + ev.text;
    }
    updateDeltaPane(ev.index);
  }
  else if(ev.type==='revise_done'){
    REVISER[ev.index] = false;
    // ev.ok 必须判：后端把改不动的情况标成 failed 发回来了，
    // 以前不分叉，失败的修订也照样说一句「已按要求改写」
    const lbl = (RUN.steps[ev.index]||{}).label||'';
    CONVO.push({_run:RUN.id, role:'assistant',
      text: t(ev.ok ? 'run.reviseDone' : 'run.reviseFail', {label: lbl})});
    redraw();
    runRefreshArts(true);
  }
  else if(ev.type==='error'){
    toast(ev.message||'error');
    if(ev.index!==undefined) appendTrace(ev.index, {kind:'err', name:'', text:ev.message||''});
  }
}

function redraw(){ drawConsole(); }
function refreshTranscript(){
  const box = document.getElementById('transcript');
  if(box) box.innerHTML = runSteps(RUN).map((s,i)=>stepBlock(s,i)).join('');
  paintProc();          /* 状态事件只走这条，进程卡不能落后于转录 */
}

function updateDeltaPane(i){
  const el = document.getElementById('delta-'+i);
  if(el){ el.textContent = ((RUN.steps[i]||{}).delta||'').slice(-8000); autoScroll(el); }
}
function appendTrace(i, line){
  if(i===undefined || i===null) return;
  TRACE[i] = (TRACE[i]||[]).concat([line]);
  if(TRACE[i].length > 400) TRACE[i] = TRACE[i].slice(-300);
  const box = document.querySelector(`.ts-step[data-i="${i}"] .ts-body`);
  if(!box){ refreshTranscript(); return; }
  const d = document.createElement('div');
  d.className = 'ts-line '+(line.kind||'status');
  d.innerHTML = ico(KIND_ICON[line.kind]||'tool')
    + (line.name?`<b>${esc(line.name)}</b>`:'')+`<span>${esc(line.text||'')}</span>`;
  const pre = box.querySelector('.run-delta');
  box.insertBefore(d, pre || (box.querySelector('.ts-art') || null));
}
function autoScroll(el){
  if(!el) return;
  if(el.scrollHeight - el.scrollTop - el.clientHeight < 80) el.scrollTop = el.scrollHeight;
}

window.runToggleStep = function(i){
  const el = document.querySelector(`.ts-step[data-i="${i}"]`);
  if(!el) return;
  const open = !el.classList.contains('open');
  el.classList.toggle('open', open);
  if(open){ ACTIVE_STEP = i;
    const st = runSteps(RUN)[i] || {};
    window.ffSetValue('rvStep', String(i), (i+1)+'. '+(st.label||st.key||''));
  }
  paintProc();          /* 进程卡的高亮跟着 ACTIVE_STEP 走，直接点转录标题也一样 */
};

/* ---------------- 操作 ---------------- */
window.runContinue = async function(){
  const r = await _post('/api/runs/'+RUN.id+'/continue');
  if(r.detail){ toast(r.detail); return; }
  toast(t('st.running'), true);
};
window.runCancel = async function(){
  const r = await _post('/api/runs/'+RUN.id+'/cancel');
  if(r.detail){ toast(r.detail); return; }
  toast(t('st.cancelled'));
};
window.runRerun = async function(index){
  const s = runSteps(RUN)[index]||{};
  const tail = runSteps(RUN).length - index - 1;
  let msg = t('run.rerunConfirm',{n:index+1, label:s.label||s.key||''});
  if(tail>0) msg += '\n' + t('run.rerunTail',{n:tail}).replace(/^\\n/,'');
  if(!confirm(msg)) return;
  const r = await _post('/api/runs/'+RUN.id+'/rerun', {index}).catch(e=>({detail:String(e)}));
  if(r.detail){ toast(r.detail); return; }
  toast(t('run.rerunDone'), true);
  TRACE = {}; FOLD = {}; ACTIVE_STEP = index;
  renderRunConsole(RUN.id);
};
window.runRefreshArts = async function(silent){
  const d = await _api('/api/runs/'+RUN.id+'/artifacts').catch(()=>null);
  if(d) ARTS = d.artifacts||{};
  await wsTick();
  if(!silent) toast(t('c.refresh'), true);
};

/* 预览一个工作区文件：文本 / markdown（可切原文）、图片、PDF 就地看，
   pptx / docx 这类浏览器画不出来的，给下载和「在文件夹中显示」。 */
let WS_MD_RAW = false;
let WS_VIEW = null;
window.runViewArt = async function(n){
  const stale = document.getElementById('runArtRoot');
  if(stale) stale.remove();
  _lockScroll(true);
  const meta = WS.find(f => f.path === n) || {path:n, kind:'text'};
  const root = document.createElement('div');
  root.id = 'runArtRoot';
  root.innerHTML = `<div class="modal open" onclick="if(event.target===this)runCloseArt()">
    <div class="modal-box sk-view-modal">
      <div class="modal-top"><div class="pv-head"><h3>${esc(n)}</h3>
        <span class="muted-sm">${esc(fmtB(meta.bytes))}</span></div>
        <button class="modal-x" onclick="runCloseArt()">×</button></div>
      <div class="sk-view-body" id="wsBody"><div class="lg-empty">${esc(t('run.wsLoading'))}</div></div>
      <div class="sk-view-foot">
        <span class="ws-md-toggle" id="wsToggle" hidden>
          <button class="pf-op" onclick="wsSetView(false)">${esc(t('run.wsRendered'))}</button>
          <button class="pf-op" onclick="wsSetView(true)">${esc(t('run.wsRaw'))}</button></span>
        <span class="spacer"></span>
        <button class="btn btn-ghost btn-sm" onclick="wsReveal('${jsq(n)}')">${esc(t('run.wsReveal'))}</button>
        <a class="btn btn-primary btn-sm" href="${ART_URL(RUN.id,n)}" download>${esc(t('c.download'))}</a>
      </div>
    </div></div>`;
  document.body.appendChild(root);
  WS_VIEW = {path:n, kind:meta.kind, text:ARTS[n] || ''};
  wsPaintBody();
};

function wsSetView(raw){ WS_MD_RAW = !!raw; wsPaintBody(); }
window.wsSetView = wsSetView;

async function wsPaintBody(){
  const body = document.getElementById('wsBody');
  if(!body || !WS_VIEW) return;
  const {path, kind} = WS_VIEW;
  const url = ART_URL(RUN.id, path);
  const tg = document.getElementById('wsToggle');
  if(tg) tg.hidden = !(kind === 'text' && /\.(md|markdown)$/i.test(path));
  if(kind === 'image'){ body.innerHTML = `<div class="ws-media"><img src="${url}" alt="${esc(path)}"></div>`; return; }
  if(kind === 'pdf'){ body.innerHTML = `<iframe class="ws-frame" src="${url}"></iframe>`; return; }
  if(kind !== 'text'){
    body.innerHTML = `<div class="lg-empty">${ico('package')}<span>${esc(t('run.wsBinary'))}</span></div>`;
    return;
  }
  if(WS_VIEW.text === '' || WS_VIEW.truncated){
    const d = await _api(`/api/runs/${encodeURIComponent(RUN.id)}/files/${path.split('/').map(encodeURIComponent).join('/')}`)
                .catch(()=>null);
    if(!d || d.detail){ body.innerHTML = `<div class="lg-empty">${esc((d&&d.detail)||t('run.wsFail'))}</div>`; return; }
    WS_VIEW = {path, kind, text:d.text||'', truncated:d.truncated};
  }
  const isMd = /\.(md|markdown)$/i.test(path);
  const txt = WS_VIEW.text;
  body.innerHTML = (isMd && !WS_MD_RAW)
    ? `<div class="ws-md">${window.mdToHtml(txt)}</div>`
    : `<pre class="sk-pre">${esc(txt)}</pre>`;
  if(WS_VIEW.truncated) body.insertAdjacentHTML('beforeend', `<div class="muted-sm">${esc(t('run.wsTrunc'))}</div>`);
}

window.wsReveal = async function(n){
  const q = `which=run&run_id=${encodeURIComponent(RUN.id)}&file=${encodeURIComponent(n)}`;
  const r = await _api('/api/reveal?'+q, {method:'POST'}).catch(()=>({detail:''}));
  if(r && r.detail) toast(r.detail || t('run.wsRevealFail'));
};
window.runCloseArt = function(){ const r=document.getElementById('runArtRoot'); if(r) r.remove(); _lockScroll(false); };

/* ---------------- 转录日志（诊断） ----------------
   引擎吐的是 stream-json 原始行，claude / codex 形状不同但都在这里压成
   「一类一行」的现场时间线；解析不出来的行原样兜底显示，绝不吞掉。 */
let LOG_RAW = '';
function logArgs(input){
  if(!input || typeof input!=='object') return '';
  for(const k of ['command','file_path','path','pattern','query','url','description']){
    const v = input[k];
    if(typeof v==='string' && v.trim()) return v.trim().replace(/\s+/g,' ').slice(0,180);
  }
  const s = JSON.stringify(input);
  return s.length>180 ? s.slice(0,180)+'…' : s;
}

function oneLine(v){
  if(typeof v==='string') return v;
  if(Array.isArray(v)) return v.map(oneLine).filter(Boolean).join(' ');
  if(v && typeof v==='object') return oneLine(v.text)||oneLine(v.message)||JSON.stringify(v);
  return String(v==null?'':v);
}

function parseLogLine(raw){
  let ev;
  try{ ev = JSON.parse(raw); }catch(e){ return [{kind:'raw', text: raw.slice(0,300)}]; }
  if(!ev || typeof ev!=='object') return [{kind:'raw', text: String(raw).slice(0,300)}];
  const rows = [];
  const t = ev.type;
  if(t==='system'){
    if(ev.subtype==='init')
      rows.push({kind:'sys', text:`${ev.model||'?'} · ${(ev.tools||[]).length} ${t0('run.lgTools')}`});
    else if(ev.subtype==='api_retry')
      rows.push({kind:'err', text:`${t0('run.lgRetry')} ${ev.attempt||'?'}/${ev.max_retries||'?'} · `
        + `${oneLine(ev.error).slice(0,160)} · ${Math.round((ev.retry_delay_ms||0)/1000)}s`});
    else rows.push({kind:'sys', text: oneLine(ev).slice(0,240)});
  }else if(t==='assistant'){
    for(const b of (ev.message||{}).content||[]){
      if(b.type==='text' && (b.text||'').trim()) rows.push({kind:'out', text: b.text.trim().replace(/\s+/g,' ').slice(0,400)});
      else if(b.type==='tool_use') rows.push({kind:'tool', text: `${b.name||'tool'} · ${logArgs(b.input)}`});
      else if(b.type!=='thinking') rows.push({kind:'raw', text: `${b.type} ${logArgs(b)}`.slice(0,240)});
    }
    if((ev.message||{}).error) rows.push({kind:'err', text: oneLine(ev.message.error).slice(0,240)});
  }else if(t==='user'){
    for(const b of (ev.message||{}).content||[]){
      if(b.type!=='tool_result') continue;
      rows.push({kind: b.is_error?'err':'ret', text: oneLine(b.content).replace(/\s+/g,' ').slice(0,260)});
    }
  }else if(t==='result'){
    const bits = [`${ev.num_turns||0} ${t0('run.lgTurns')}`,
                  `${Math.round((ev.duration_ms||0)/1000)}s`];
    if(ev.total_cost_usd) bits.push('$'+Number(ev.total_cost_usd).toFixed(4));
    rows.push({kind: ev.is_error?'err':'end',
      text: bits.join(' · ')+' · '+(oneLine(ev.result||ev.terminal_reason)||t0(ev.is_error?'run.lgFailed':'run.lgOk'))
        .replace(/\s+/g,' ').slice(0,300)});
  }else if(t==='thread.started'||t==='turn.started'){
    rows.push({kind:'sys', text: t});
  }else if(t==='item.completed'){
    const it = ev.item||{};
    if(it.type==='agent_message' && (it.text||'').trim())
      rows.push({kind:'out', text: it.text.trim().replace(/\s+/g,' ').slice(0,400)});
    else if(it.type==='command_execution')
      rows.push({kind:'tool', text:`shell · ${oneLine(it.command).slice(0,180)}`
        + (it.exit_code!=null ? ` → ${t0('run.lgExit')} ${it.exit_code}` : '')});
    else if(it.type==='file_change')
      rows.push({kind:'tool', text:`files · ${(it.changes||[]).map(c=>c.path).join(', ').slice(0,180)}`});
    else if(it.type==='reasoning' && (it.text||'').trim())
      rows.push({kind:'ret', text: it.text.trim().replace(/\s+/g,' ').slice(0,260)});
    else if(it.type==='error') rows.push({kind:'err', text: oneLine(it).slice(0,240)});
  }else if(t==='turn.completed'){
    const u = ev.usage||{};
    rows.push({kind:'end', text:`${t0('run.lgOk')} · in ${u.input_tokens||0} · out ${u.output_tokens||0}`
      + (u.cached_input_tokens?` · cache ${u.cached_input_tokens}`:'')});
  }else if(t==='turn.failed'||t==='error'){
    rows.push({kind:'err', text: oneLine(ev.error||ev.message||ev).slice(0,300)});
  }
  return rows.length ? rows : null;
}

function t0(k){ return window.t(k); }

function logRows(lines){
  const out = [];
  for(const ln of lines||[]){
    if(!ln || !ln.trim()) continue;
    const r = parseLogLine(ln);
    if(r) out.push(...r);
  }
  return out;
}

window.runShowLog = async function(name){
  const stale = document.getElementById('runLogRoot');
  if(stale) stale.remove();          // 连续点两步的日志会叠两层、锁死滚动
  _lockScroll(true);
  const root = document.createElement('div');
  root.id = 'runLogRoot';
  root.innerHTML = `<div class="modal open" onclick="if(event.target===this)runCloseLog()">
    <div class="modal-box sk-view-modal">
      <div class="modal-top"><div class="pv-head"><h3>${esc(t('run.lgTitle'))}</h3>
        <span class="lg-name">${esc(name)}</span></div>
        <button class="modal-x" onclick="runCloseLog()">×</button></div>
      <div class="sk-view-body"><div class="lg-empty">${ico('spinner')}<span>${esc(t('run.lgLoading'))}</span></div></div>
    </div></div>`;
  document.body.appendChild(root);
  const d = await _api(`/api/runs/${RUN.id}/logs/${encodeURIComponent(name)}?lines=1200`).catch(e=>({detail:String(e)}));
  const body = root.querySelector('.sk-view-body');
  if(!body) return;
  if(d.detail || !d.lines){
    body.innerHTML = `<div class="lg-empty">${esc(d.detail||t('run.lgEmpty'))}</div>`;
    return;
  }
  const rows = logRows(d.lines);
  LOG_RAW = d.lines.join('\n');
  const head = `<div class="lg-bar"><span>${esc(t('run.lgMeta'))} · ${d.lines.length} ${esc(t('run.lgLines'))}`
    + ` · ${(d.bytes/1024).toFixed(1)} KB${d.truncated?' · '+esc(t('run.lgTrunc')):''}</span>
      <span class="spacer"></span>
      <button class="pf-op" onclick="runCopyLog()">${ico('copy')}${esc(t('run.lgCopy'))}</button>
      <a class="pf-op" href="${ART_URL(RUN.id,'_turn_logs/'+name)}" download>${ico('download')}${esc(t('c.download'))}</a></div>`;
  body.innerHTML = head + (rows.length ? `<div class="lg-list">${rows.map(r=>
    `<div class="lg-line lg-${r.kind}"><span class="lg-k">${esc(t('run.lg'+r.kind.charAt(0).toUpperCase()+r.kind.slice(1)))}</span>`
    +`<span class="lg-t">${esc(r.text)}</span></div>`).join('')}</div>`
    : `<div class="lg-empty">${esc(t('run.lgEmpty'))}</div>`);
};
window.runCopyLog = function(){
  navigator.clipboard.writeText(LOG_RAW).then(()=>toast(t('run.lgCopied'), true))
    .catch(()=>toast(t('run.lgCopyFail')));
};
window.runCloseLog = function(){ const r=document.getElementById('runLogRoot'); if(r) r.remove(); _lockScroll(false); };

/* ---------------- 通过输入面板发起修改 ---------------- */
async function runRevise(){
  const sel = document.getElementById('rvStep');
  const txt = document.getElementById('rvText');
  if(!sel || !txt) return;
  const instruction = (txt.value||'').trim();
  if(!instruction){ toast(t('run.reviseEmpty')); return; }
  const idx = Number(sel.value);
  CONVO.push({_run:RUN.id, role:'user', text:instruction});
  txt.value=''; txt.style.height='auto';
  drawConvo();
  const r = await _post('/api/runs/'+RUN.id+'/revise', {index: idx, instruction}).catch(e=>({detail:String(e)}));
  if(r.detail){ CONVO.push({_run:RUN.id, role:'assistant', text:r.detail}); drawConvo(); return; }
}
window.runRevise = runRevise;

function drawConvo(){
  const box = document.getElementById('runConvo');
  if(!box) return;
  const items = CONVO.filter(m=>m._run===RUN.id);
  box.innerHTML = items.length ? `<div class="convo-list">${items.map(m=>`
    <div class="convo-msg"><div class="cm-role">${m.role==='user'?'YOU':'AI'}</div>
      <div class="cm-text">${esc(m.text)}</div></div>`).join('')}</div>` : '';
  box.scrollTop = box.scrollHeight;
}

window.addEventListener('hashchange', ()=>{
  if(ES && !location.hash.startsWith('#/run/')){ ES.close(); ES=null; }
  $('#view') && $('#view').classList.remove('with-composer');
});

})();
