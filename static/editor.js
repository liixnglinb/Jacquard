/* Loom 织流 · 流程编排器 + 技能编辑器
 * 路由 #/pipelines #/pipeline-edit/<name|new> #/skills #/skill-edit/<name|new>
 * 文案走 window.t()
 */
(function(){
"use strict";

const $ = s => document.querySelector(s);
const t = window.t;
const ico = window.icon;
function esc(s){ return String(s==null?'':s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;'); }
function toast(msg, ok=false){ window.ffToast(msg, ok); }
async function _api(path, opts){
  if (!opts || !opts.method || opts.method === 'GET') return window.voyraRead(path, opts);
  const r = await fetch(path, opts);
  const ct = r.headers.get('content-type')||'';
  if(ct.includes('application/json')) return r.json();
  if(!r.ok) throw new Error('HTTP '+r.status);
  return r.text();
}
function _post(path, data){ return _api(path, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(data||{})}); }
function _put(path, data){ return _api(path, {method:'PUT', headers:{'Content-Type':'application/json'}, body:JSON.stringify(data||{})}); }
function _del(path){ return _api(path, {method:'DELETE'}); }
/* ---------------- 数据 ---------------- */
let PL_TPLS = [];
let PL_SKILLS = [];
let PL_EXT = {claude: [], codex: []};
let PL_DEF_ENGINE = '';
let PL_EDIT = null;
let SK_EDIT = null;
let _ST_PRESETS = null;

/* ---------------- 未保存离开保护 ----------------
   两个编辑器原来一点保护都没有：改完步骤直接按取消、点侧栏、按 Ctrl K 就静默丢。
   守卫按 location.hash 自判归属，离开编辑器就自动不报脏，所以不需要谁去反注册。 */
const NAV_GUARDS = [];
function navIsDirty(){
  return NAV_GUARDS.some(f => { try { return !!f(); } catch (e) { return false; } });
}
// nav.go 与真 href 的锚点点击都问这一个口子（app.js / 下面的点击捕获）
window.navGuardAsk = () => !navIsDirty() || !!confirm(t('ed.unsavedLeave'));

let PL_BASE = '';
function plSnap(E){
  return JSON.stringify({n:E.name||'', l:E.label||'', d:E.desc||'', g:E.g||'',
    s:(E.steps||[]).map(x=>[(x.key||'').trim(),(x.label||'').trim(),
      [(x.skill||'').trim(), ...(x.extra_skills||[])].join(' ').trim(),(x.skill_src||''),(x.out||'').trim(),
      x.checkpoint?1:0, x.role||'', (x.model||'').trim(), (x.engine||'').trim(),
      (x.extra_prompt||'').trim()])});
}
function plDirty(){
  if(!PL_EDIT || !location.hash.startsWith('#/pipeline-edit')) return false;
  plSyncInputs();
  return plSnap(PL_EDIT) !== PL_BASE;
}
let SK_BASE = '';
function skSnap(o){
  return JSON.stringify({n:o.n||'', c:o.c||'', nw:o.nw?1:0});
}
function skDirty(){
  if(!SK_EDIT || !location.hash.startsWith('#/skill-edit')) return false;
  const el = document.getElementById('skContent'), nm = document.getElementById('skName');
  return skSnap({n: nm ? nm.value : SK_EDIT.name,
                 c: el ? el.value : SK_EDIT.content,
                 nw: SK_EDIT.isNew}) !== SK_BASE;
}
NAV_GUARDS.push(plDirty); NAV_GUARDS.push(skDirty);
/* 存盘成功即视为不脏：否则 plSave 末尾那句 nav.go 会把自己拦下来问一遍 */
window.markSavedClean = function(which){
  if(which === 'pl' && PL_EDIT){ plSyncInputs(); PL_BASE = plSnap(PL_EDIT); }
  if(which === 'sk' && SK_EDIT){
    const el = document.getElementById('skContent'), nm = document.getElementById('skName');
    SK_EDIT.content = el ? el.value : SK_EDIT.content;
    if(nm) SK_EDIT.name = nm.value;
    SK_BASE = skSnap({n:SK_EDIT.name, c:SK_EDIT.content, nw:SK_EDIT.isNew});
  }
};
window.addEventListener('beforeunload', (e)=>{
  if(navIsDirty()){ e.preventDefault(); e.returnValue = ''; }
});
// 主导航和侧栏条目现在是真 href，浏览器默认直接改 hash，nav.go 拦不到，只能在这儿接
document.addEventListener('click', (e)=>{
  const a = e.target && e.target.closest ? e.target.closest('a[href^="#/"]') : null;
  if(a && !window.navGuardAsk()) e.preventDefault();
}, true);

async function plLoad(){
  const [pips, sks, caps, ag] = await Promise.all([
    _api('/api/pipelines'),
    _api('/api/skills'),
    _api('/api/agents/capabilities').catch(()=>null),
    _api('/api/agents').catch(()=>null),
  ]);
  PL_TPLS = pips.pipelines || [];
  PL_SKILLS = sks.skills || [];
  PL_EXT = {claude: plSkillNames(caps, 'claude'), codex: plSkillNames(caps, 'codex')};
  PL_DEF_ENGINE = (ag && ag.default_engine) || '';
}
const plSkillNames = (caps, eng) => {
  const it = ((caps || {})[eng] || {}).items || [];
  const sk = it.find(x => x.key === 'skills');
  return sk ? sk.entries.map(e => e.name) : [];
};
/* 一个下拉里并列三家，值里带上来源：skill_src 只有一个字段，
   所以一步的主技能与叠加技能必须同源 —— 混着选会说不清那份规范到底归谁。 */
const plSkillValue = (src, name) => (src ? src + ':' : '') + name;
const plSkillOpt = (src, name) => ({
  v: plSkillValue(src, name),
  label: name + (src ? ' · ' + t('ed.src.' + src) : ''),
});
const plSkillOptions = (src) =>
  (src === 'claude' ? PL_EXT.claude : src === 'codex' ? PL_EXT.codex : PL_SKILLS.map(x => x.name))
    .filter(Boolean).map(n => plSkillOpt(src, n));
const plSplitSkill = (v) => {
  const i = String(v || '').indexOf(':');
  return i > 0 ? {src: v.slice(0, i), name: v.slice(i + 1)} : {src: '', name: v || ''};
};
async function stPresets(){
  if(_ST_PRESETS) return _ST_PRESETS;
  try{ _ST_PRESETS = (await _api('/api/providers')).presets||[]; }
  catch(e){ _ST_PRESETS = []; }
  return _ST_PRESETS;
}

const ROLES = () => [
  {v:'executor', label:t('ed.role.executor'), hint:t('ed.roleHint.executor')},
  {v:'reviewer', label:t('ed.role.reviewer'), hint:t('ed.roleHint.reviewer')},
  {v:'editor',   label:t('ed.role.editor'),   hint:t('ed.roleHint.editor')},
];
const pvf = (label, inner, hint) => `
  <div class="pv-f"><label class="pv-label">${label}</label>${inner}${hint||''}</div>`;
const pvh = (txt, id) => `<div class="pv-foot-hint"${id?` id="${esc(id)}"`:''}>${esc(txt)}</div>`;

/* =====================================================================
 * 技能库
 * ===================================================================== */
window.renderSkills = async function(){
  window.viewLoading();
  await plLoad();
  const row = s => `
    <article class="pl-card-row">
      <button type="button" class="pl-row-main" onclick="skView('${jsq(s.name)}')">
        <div class="pl-row-title"><span class="pl-row-name">${esc(s.name)}</span>
          <span class="muted-sm">${s.chars>0?(s.chars/1000).toFixed(1)+'k':esc(t('sk.empty2'))}</span></div>
        ${s.desc?`<div class="pl-steps-mini"><span class="pl-step-chip pl-chip-wide">${esc(s.desc)}</span></div>`:''}
      </button>
      <div class="pl-row-ops" onclick="event.stopPropagation()">
        <button class="pf-op" onclick="skView('${jsq(s.name)}')">${esc(t('c.view'))}</button>
        <button class="pf-op" onclick="nav.go('skill-edit/${jsq(s.name)}')">${esc(t('c.edit'))}</button>
      </div>
    </article>`;
  window.__chrome = {title:t('sk.title'), icon:'skill',
    actions:`<button class="btn btn-ghost btn-sm" onclick="skImportModal()">${esc(t('c.import'))}</button>
      <button class="btn btn-primary btn-sm" onclick="nav.go('skill-edit/new')"><span class="btn-plus">＋</span> ${esc(t('sk.new'))}</button>`};
  $('#view').innerHTML = `
    <input class="pl-file" type="file" id="skImportFile" accept=".zip,.md" onchange="skImportDo(this)">
    <div class="pl-list">${PL_SKILLS.length?PL_SKILLS.map(row).join('')
      :`<div class="pf-empty">${esc(t('sk.empty'))}</div>`}</div>`;
};

window.skImportModal = function(){ const el=document.getElementById('skImportFile'); if(el) el.click(); };
window.skImportDo = async function(input){
  const f = input.files && input.files[0];
  input.value = '';
  if(!f) return;
  toast(t('sk.importing',{name:f.name}));
  const fd = new FormData(); fd.append('file', f);
  try{
    const r = await fetch('/api/skills/import', {method:'POST', body: fd});
    const d = await r.json().catch(()=>({detail:'HTTP '+r.status}));
    if(d.detail){ toast(d.detail); return; }
    toast(t('sk.imported',{name:d.name}), true);
    renderSkills();
  }catch(e){ toast(t('sk.importFail',{err:e})); }
};

window.skView = async function(name){
  const d = await _api('/api/skills/'+encodeURIComponent(name)).catch(e=>({detail:e.message}));
  if(d.detail){ toast(d.detail); return; }
  _lockScroll(true);
  const root = document.createElement('div');
  root.id = 'skViewRoot';
  root.innerHTML = `<div class="modal open" onclick="if(event.target===this)skCloseModal()">
    <div class="modal-box sk-view-modal">
      <div class="modal-top"><div class="pv-head"><h3>${esc(d.name)}</h3></div>
        <button class="modal-x" onclick="skCloseModal()">×</button></div>
      <div class="sk-view-body"><pre class="sk-pre">${esc(d.content)}</pre></div>
      <div class="sk-view-foot">
        <button class="btn btn-ghost btn-sm" onclick="skCloseModal()">${esc(t('c.close'))}</button>
        <button class="btn btn-ghost btn-sm" onclick="skDuplicate('${esc(d.name)}')">${esc(t('sk.dupe'))}</button>
        <button class="btn btn-ghost btn-sm pl-danger" onclick="skDelete('${esc(d.name)}')">${esc(t('c.delete'))}</button>
        <button class="btn btn-primary btn-sm" onclick="skCloseModal();nav.go('skill-edit/${jsq(d.name)}')">${esc(t('c.edit'))}</button>
      </div>
    </div></div>`;
  document.body.appendChild(root);
};
window.skCloseModal = function(){ const r=document.getElementById('skViewRoot'); if(r) r.remove(); _lockScroll(false); };
window.skDuplicate = async function(name){
  skCloseModal();
  const nn = prompt(t('sk.dupeName'), name + '-my');
  if(nn===null) return;
  const r = await _post('/api/skills/'+encodeURIComponent(name)+'/duplicate', {name: nn.trim()})
    .catch(e=>({detail:e.message||'fail'}));
  if(r.detail){ toast(r.detail); return; }
  toast(t('sk.dupeDone',{name:r.name}), true);
  nav.go('skill-edit/'+r.name);
};
window.skDelete = async function(name){
  if(!confirm(t('sk.delConfirm',{name}))) return;
  skCloseModal();
  const r = await _del('/api/skills/'+encodeURIComponent(name)).catch(e=>({detail:e.message}));
  if(r.detail){ toast(r.detail); return; }
  toast(t('sk.deleted')); renderSkills();
};

window.renderSkillEdit = async function(name){
  window.viewLoading();
  if(name && name !== 'new'){
    const d = await _api('/api/skills/'+encodeURIComponent(name)).catch(e=>({detail:e.message}));
    if(d.detail){ toast(d.detail); nav.go('skills'); return; }
    SK_EDIT = {name: d.name, content: d.content, isNew: false};
  }else{
    SK_EDIT = {name:'', content:'', isNew:true};
  }
  skDrawEditor();
  SK_BASE = skSnap({n:SK_EDIT.name, c:SK_EDIT.content, nw:SK_EDIT.isNew});
};

function skDrawEditor(){
  const E = SK_EDIT;
  const lines = E.content ? E.content.split('\n').length : 0;
  const title = (E.isNew?t('sk.newTitle'):t('sk.editTitle'))
    + (E.name?` · ${E.name}`:'');
  window.__chrome = {title: title, icon:'skill', actions: `
    <button class="btn btn-ghost btn-sm" onclick="skBack()">${esc(t('c.back'))}</button>
    <button class="btn btn-primary btn-sm" onclick="skSave()">${esc(t('sk.save'))}</button>`};
  $('#view').innerHTML = `
    <div class="card sk-edit-card">
      ${E.isNew?`
      <div class="sk-field">
        <label class="pv-label">${esc(t('sk.nameField'))} <b class="req">*</b></label>
        <input class="pv-input mono" id="skName" placeholder="${esc(t('sk.namePh'))}" maxlength="64">
        <div class="sk-hint">${esc(t('sk.nameHint'))}</div>
      </div>`:''}
      <div class="sk-field sk-grow">
        <label class="pv-label">${esc(t('sk.content'))} <b class="req">*</b></label>
        <textarea class="pv-input mono sk-content" id="skContent"
          placeholder="${esc(t('sk.contentPh'))}" oninput="skSync()">${esc(E.content)}</textarea>
        <div class="sk-hint" id="skCount">${esc(t('sk.lines',{n:lines}))}</div>
      </div>
    </div>`;
  setTimeout(()=>{ const el=document.getElementById('skContent'); if(el && E.isNew) el.focus(); }, 50);
}
window.skSync = function(){
  const el = document.getElementById('skContent');
  const c = document.getElementById('skCount');
  if(el && c) c.textContent = t('sk.lines',{n: el.value?el.value.split('\n').length:0});
  if(el) SK_EDIT.content = el.value;
};
window.skBack = function(){ nav.go('skills'); };
window.skSave = async function(){
  const E = SK_EDIT;
  const content = ($('#skContent') && $('#skContent').value) || E.content || '';
  if(!content.trim()){ toast(t('sk.needContent')); return; }
  if(E.isNew){
    const name = ($('#skName') && $('#skName').value || '').trim();
    if(!name){ toast(t('sk.needName')); return; }
    const r = await _post('/api/skills', {name, content}).catch(e=>({detail:e.message}));
    if(r.detail){ toast(r.detail); return; }
    toast(t('sk.created'), true); window.markSavedClean('sk'); nav.go('skills');
  }else{
    const r = await _put('/api/skills/'+encodeURIComponent(E.name), {name:E.name, content})
      .catch(e=>({detail:e.message}));
    if(r.detail){ toast(r.detail); return; }
    toast(t('sk.saved'), true); window.markSavedClean('sk'); nav.go('skills');
  }
};

/* =====================================================================
 * 流程编排
 * ===================================================================== */
window.renderPipelines = async function(){
  window.viewLoading();
  await plLoad();
  const row = p => `
    <article class="pl-card-row${p.archived?' archived':''}">
      <a class="pl-row-main" href="#/pipeline-edit/${jsq(p.name)}">
        <div class="pl-row-title"><span class="pl-row-name">${esc(p.label||p.name)}</span>
          <code>${esc(p.name)}</code>
          ${p.archived?`<span class="pl-arch-tag">${esc(t('sb.archived'))}</span>`:''}
          ${p.desc?`<span class="pf-url">${esc(p.desc)}</span>`:''}</div>
        <div class="pl-row-meta"><span>${p.steps.length} ${esc(t('c.steps'))}</span>
          <span class="pl-steps-mini">${p.steps.map((s,i)=>
            `<span class="pl-step-chip" title="${esc(s.skill)}">${i+1}. ${esc(s.label)}</span>`).join('')}</span></div>
      </a>
      <div class="pl-row-ops" onclick="event.stopPropagation()">
        <button class="pf-op pf-op-start" onclick="taskModal('${esc(p.name)}')">${esc(t('list.runned'))}</button>
        <button class="pf-op" onclick="nav.go('pipeline-edit/${jsq(p.name)}')">${esc(t('c.edit'))}</button>
        <button class="pf-op pf-op-more" data-tip-any="1" data-tip="${esc(t('c.more'))}"
          aria-label="${esc(t('c.more'))}" onclick="plRowMore(event,'${esc(p.name)}')">${ico('more')}</button>
      </div>
    </article>`;
  window.__chrome = {title:t('list.flows'), icon:'flow',
    actions:`<button class="btn btn-ghost btn-sm" onclick="plImportPick()">${esc(t('c.import'))}</button>
      <input class="pl-file" type="file" id="plImportFile" accept="application/json,.json"
        onchange="plImportFile(this)">
      <button class="btn btn-ghost btn-sm" onclick="taskModal()">${esc(t('home.giveTask'))}</button>
      <button class="btn btn-primary btn-sm" onclick="nav.go('pipeline-edit/new')"><span class="btn-plus">＋</span> ${esc(t('c.create'))}</button>`};
  $('#view').innerHTML = `
    <div class="pl-list">${PL_TPLS.length?PL_TPLS.map(row).join('')
      :`<div class="pf-empty">${esc(t('home.mineEmpty'))}</div>`}</div>`;
};

window.plDuplicate = async function(name){
  const base = PL_TPLS.find(p=>p.name===name); if(!base) return;
  let nn = name + '-copy', k = 2;
  while(PL_TPLS.some(p=>p.name===nn)) nn = `${name}-copy${k++}`;
  const label = prompt(t('list.duplicateName'), base.label + ' copy');
  if(label===null) return;
  const r = await _post(`/api/pipelines/${encodeURIComponent(name)}/duplicate`,
    {name: nn, label, steps: base.steps}).catch(e=>({detail:e.message}));
  if(r.detail){ toast(r.detail); return; }
  toast(t('list.copied',{name:label}), true);
  nav.go('pipeline-edit/'+r.name);
};
window.plDelete = async function(name){
  if(!confirm(t('list.deleteConfirm',{name}))) return;
  const r = await _del(`/api/pipelines/${encodeURIComponent(name)}`).catch(e=>({detail:e.message}));
  if(r.detail){ toast(r.detail); return; }
  renderPipelines();
};

/* 行操作收进 ⋯：副本 / 导出 / 删除都不是每次都点的，
   摊在行上是三个按钮，删除还和「运行」挨在一起。 */
window.plRowMore = function(e, name){
  const p = PL_TPLS.find(x=>x.name===name);
  const items = [
    {v:'dup', label:t('c.duplicate'), run:()=>plDuplicate(name)},
    {v:'exp', label:t('c.export'), run:()=>plExport(name)},
  ];
  /* 归档的开关在侧栏那一栏，这里只给「这一条要不要回到侧栏」，
     不再复制一个视图切换 —— 同一个动作留一个入口。 */
  if (p && p.archived) items.push({v:'unarch', label:t('sb.unarchive'), run:()=>plArchive(name, false)});
  else items.push({v:'arch', label:t('sb.archive'), run:()=>plArchive(name, true)});
  items.push({v:'del', label:t('c.delete'), danger:true, run:()=>plDelete(name)});
  window.ffActionMenu(e, items);
};
window.plArchive = async function(name, flag){
  const p = PL_TPLS.find(x=>x.name===name);
  const r = await _post(`/api/pipelines/${encodeURIComponent(name)}/archive`, {archived:flag})
    .catch(e=>({detail:e.message}));
  if(r && r.detail){ toast(r.detail); return; }
  toast(t(flag ? 'sb.archivedToast' : 'sb.unarchivedToast', {name:(p&&p.label)||name}), true);
  renderPipelines();
};
window.plExport = function(name){
  const a = document.createElement('a');
  a.href = `/api/pipelines/${encodeURIComponent(name)}/export`;
  a.download = 'loom-' + name + '.json';
  document.body.appendChild(a); a.click(); a.remove();
};
window.plImportPick = function(){
  const el = document.getElementById('plImportFile'); if(el) el.click();
};
window.plImportFile = async function(el){
  const f = el.files && el.files[0]; el.value = '';
  if(!f) return;
  let j = null;
  try { j = JSON.parse(await f.text()); } catch(_){ toast(t('list.importBad')); return; }
  const name = String((j && j.name) || '').trim();
  const steps = (j && Array.isArray(j.steps)) ? j.steps : [];
  if(!name || !steps.length){ toast(t('list.importBad')); return; }
  let send = name, extra = '';
  if(PL_TPLS.some(p=>p.name===name)){
    let nn = name + '-copy', k = 2;
    while(PL_TPLS.some(p=>p.name===nn)) nn = `${name}-copy${k++}`;
    if(!confirm(t('list.importDup',{name, nn}))) return;
    send = nn; extra = ' copy';      /* 撞名换了标识还沿用原显示名，列表里会出现两行同名 */
  }
  const r = await _post('/api/pipelines', {name: send, label: (j.label || name) + extra,
      desc: j.desc || '', emoji: j.emoji || '', g: j.g || 'custom', steps}).catch(e=>({detail:e.message}));
  if(r.detail){ toast(r.detail); return; }
  toast(t('list.imported',{name: r.name || send}), true);
  await plLoad();
  nav.go('pipeline-edit/' + (r.name || send));
};

function plBlankStep(n){
  return {key:'step'+n, label:t('ed.newStep',{n}), skill:(PL_SKILLS[0]?PL_SKILLS[0].name:''),
    skill_src:'', extra_skills:[], out:'STEP'+n+'.md', checkpoint:false, role:'executor',
    engine:'', model:'', extra_prompt:''};
}
function plNormalizeSteps(){
  for(const s of PL_EDIT.steps){
    const parts = String(s.skill||'').trim().split(/\s+/).filter(Boolean);
    s.skill = parts[0] || '';
    s.skill_src = (s.skill_src === 'claude' || s.skill_src === 'codex') ? s.skill_src : '';
    s.extra_skills = Array.isArray(s.extra_skills) ? s.extra_skills : parts.slice(1);
    s.extra_prompt = s.extra_prompt || '';
    s.engine = s.engine || '';
  }
}
function plSyncInputs(){
  const E = PL_EDIT; if(!E) return;
  const labelEl = $('#plLabel'), descEl = $('#plDesc'), nameEl = $('#plName');
  if(!E.name && nameEl && nameEl.value.trim()) E._draftName = nameEl.value.trim();
  if(labelEl) E.label = labelEl.value;
  if(descEl) E.desc = descEl.value;
}

function plDrawEditor(){
  plSyncInputs();
  plNormalizeSteps();
  const E = PL_EDIT;
  const isNew = !E.name;
  const skillInfo = n => PL_SKILLS.find(s=>s.name===n) || null;
  const presetNames = (_ST_PRESETS||[]).map(p=>p.name);
  const readyEngines = (window.ST&&window.ST.agents||[]).filter(a=>a.found).map(a=>a.engine).join(' / ');
  const ROLES_ = ROLES();

  const stepCard = (s,i) => {
    const main = skillInfo(s.skill);
    const keyDup = E.steps.filter(x=>(x.key||'').trim()===s.key.trim()).length > 1;
    const keyBad = !/^[a-z0-9][a-z0-9_-]*$/.test((s.key||'').trim());
    return `
    <div class="step-card" data-i="${i}">
      <div class="step-rail">
        <div class="step-no">${i+1}</div>
        ${i<E.steps.length-1?'<div class="step-line"></div>':''}
      </div>
      <div class="step-body">
        <div class="pv-form">
          <div class="pv-row2">
            ${pvf(`${esc(t('ed.stepName'))} <b class="req">*</b>`,
              `<input class="pv-input" value="${esc(s.label)}" oninput="plSet(${i},'label',this.value)">`)}
            ${pvf(`${esc(t('ed.stepKey'))} <b class="req">*</b>`,
              `<input class="pv-input mono ${keyDup||keyBad?'fld-err':''}" value="${esc(s.key)}"
                oninput="plSet(${i},'key',this.value)">`,
              keyDup?`<div class="fld-err-t">${esc(t('ed.keyDup'))}</div>`
                    :keyBad?`<div class="fld-err-t">${esc(t('ed.keyHint'))}</div>`:'')}
          </div>
          <div class="pv-row2">
            ${pvf(`${esc(t('ed.mainSkill'))} <b class="req">*</b>
              <a class="fld-link" onclick="nav.go('skills')">${esc(t('ed.viewSkills'))}</a>`,
              (()=>{ let os=[{v:'',label:'—'}]
                    .concat(plSkillOptions(''), plSkillOptions('claude'), plSkillOptions('codex'));
                  const cur = plSkillValue(s.skill_src||'', s.skill||'');
                  if(s.skill && !os.some(o=>o.v===cur)) os.push({v:cur, label:s.skill+'（'+t('sk.deleted')+'）'});
                  return ffSelect(os, cur, {mono:true, onChange:(v)=>{
                    const sp = plSplitSkill(v);
                    plSet(i,'skill',sp.name); PL_EDIT.steps[i].skill_src = sp.src; plDrawEditor(); }}); })(),
              (s.skill_src ? `<div class="pv-foot-hint">${esc(t('ed.extHint'))}</div>`
                           : main ? `<div class="pv-foot-hint">${esc(main.desc)}</div>`
                           : s.skill ? `<div class="pv-foot-hint">${esc(t('ed.lostSkill'))}</div>` : ''))}
            ${pvf(esc(t('ed.out')),
              `<input class="pv-input mono" value="${esc(s.out||'')}" placeholder="${esc(t('ed.outPh'))}"
                oninput="plSet(${i},'out',this.value)">`,
              pvh(t('ed.outHint')))}
          </div>
          ${pvf(esc(t('ed.role')),
            ffSelect(ROLES_.map(r=>({v:r.v, label:r.label})), s.role||'executor',
              {cls:'ff-pill', onChange:(v)=>plRole(i,v)}),
            pvh((ROLES_.find(r=>r.v===(s.role||'executor'))||ROLES_[0]).hint, 'roleHint-'+i))}
          <div class="step-adv">
            <button type="button" class="step-adv-toggle" onclick="this.parentElement.classList.toggle('open')">
              <span class="adv-arrow">▸</span> ${esc(t('ed.advanced'))}
              <span class="adv-dot" id="advDot-${i}"
                style="${(s.model||s.engine||(s.extra_skills||[]).length||s.extra_prompt)?'':'display:none'}"></span>
            </button>
            <div class="step-adv-body">
              <div class="pv-row2">
                ${pvf(esc(t('ed.engine')),
                  ffSelect([['', t('ed.engineDefault')],['claude',t('eng.claude')],['codex',t('eng.codex')]]
                    .map(([v,label])=>({v,label})), s.engine||'',
                    {cls:'ff-pill', onChange:(v)=>plEng(i,v)}),
                  pvh(readyEngines ? t('ed.engineHint')+' · '+t('ed.engineReady',{list:readyEngines}) : t('ed.engineNone')))}
                ${pvf(esc(t('ed.model')),
                  (()=>{ const om=[{v:'',label:t('ed.modelFollow')}].concat(
                      presetNames.map(n=>({v:n, label:t('ed.modelPreset',{name:n})})));
                    if(s.model && !presetNames.includes(s.model)) om.push({v:s.model, label:t('ed.modelRaw',{model:s.model})});
                    return ffSelect(om, s.model||'', {onChange:(v)=>{ plSet(i,'model',v); plDrawEditor(); }}); })(),
                  pvh(t('ed.modelHint')))}
              </div>
              ${pvf(esc(t('ed.extraSkills')),
                `<div class="extra-chips">
                  ${(s.extra_skills||[]).map((n,xi)=>`<span class="x-chip">${esc(n)}<b onclick="plExtraDel(${i},${xi})">×</b></span>`).join('')||`<span class="muted-sm">${esc(t('c.none'))}</span>`}
                  ${(s.skill_src?`<div class="pv-foot-hint">${esc(t('ed.src.'+s.skill_src))} · ${esc(t('ed.extHint'))}</div>`:'')}
                  ${(()=>{ const add=plSkillOptions(s.skill_src||'')
                        .filter(o=>plSplitSkill(o.v).name!==s.skill && !(s.extra_skills||[]).includes(plSplitSkill(o.v).name));
                      return add.length ? ffSelect(add, '', {action:true, cls:'ff-ghost',
                        placeholder:t('ed.addSkill'), onChange:(v)=>plExtraAdd(i, plSplitSkill(v).name)}) : ''; })()}
                </div>`)}
              ${pvf(esc(t('ed.stepExtra')),
                `<textarea class="pv-input" rows="3" placeholder="${esc(t('ed.stepExtraPh'))}"
                  oninput="plSet(${i},'extra_prompt',this.value)">${esc(s.extra_prompt||'')}</textarea>`,
                pvh(t('ed.stepExtraHint')))}
              <div class="pl-check-row">
                <div><div class="k">${esc(t('ed.checkpoint'))}</div><div class="cs2">${esc(t('ed.checkpointHint'))}</div></div>
                <label class="switch"><input type="checkbox" ${s.checkpoint?'checked':''}
                  onchange="plSet(${i},'checkpoint',this.checked)"><span class="slider"></span></label>
              </div>
              <div class="pl-check-row">
                <div><div class="k">${esc(t('ed.preview'))}</div><div class="cs2">${esc(t('ed.previewSub'))}</div></div>
                <button type="button" class="btn btn-ghost btn-sm" onclick="plPreview(${i})">${esc(t('ed.preview'))}</button>
              </div>
            </div>
          </div>
        </div>
      </div>
      <div class="step-ops">
        <button type="button" class="plop" title="${esc(t('ed.moveUp'))}" onclick="plMove(${i},-1)" ${i===0?'disabled':''}>↑</button>
        <button type="button" class="plop" title="${esc(t('ed.moveDown'))}" onclick="plMove(${i},1)" ${i===E.steps.length-1?'disabled':''}>↓</button>
        <button type="button" class="plop plop-del" title="${esc(t('ed.delStep'))}" onclick="plDel(${i})">×</button>
      </div>
    </div>`;
  };

  window.__chrome = {
    title: (isNew?t('ed.newTitle'):t('ed.editTitle')) + (E.label?` · ${E.label}`:''),
    icon:'flow',
    actions: `<button class="btn btn-ghost btn-sm" onclick="nav.go('pipelines')">${esc(t('c.cancel'))}</button>
      <button class="btn btn-primary btn-sm" onclick="plSave()">${esc(t('ed.save'))}</button>`,
  };
  $('#view').innerHTML = `
    <div class="card">
      <div class="card-h"><div><div class="ct">${esc(t('ed.basic'))}</div></div></div>
      <div class="pv-form">
        <div class="pv-row2">
          ${pvf(`${esc(t('ed.name'))} <b class="req">*</b>`,
            `<input class="pv-input mono" id="plName" placeholder="${esc(t('ed.namePh'))}"
              value="${esc(isNew?(E._draftName||''):E.name)}" ${isNew?'':'disabled'}>`,
            isNew?pvh(t('ed.nameHint')):'')}
          ${pvf(`${esc(t('ed.label'))} <b class="req">*</b>`,
            `<input class="pv-input" id="plLabel" value="${esc(E.label)}" oninput="plEdit('label',this.value)">`)}
        </div>
        ${pvf(esc(t('ed.desc')),
          `<textarea class="pv-input" id="plDesc" rows="2" placeholder="${esc(t('ed.descPh'))}"
            oninput="plEdit('desc',this.value)">${esc(E.desc||'')}</textarea>`)}
      </div>
    </div>
    <div class="card">
      <div class="card-h"><div><div class="ct">${esc(t('ed.stepsTitle'))} <span class="muted">(${E.steps.length})</span></div>
        <div class="cs">${esc(t('ed.stepsSub'))}</div></div>
        <button class="btn btn-accent btn-sm" onclick="plAdd()"><span class="btn-plus">＋</span> ${esc(t('ed.addStep'))}</button></div>
      <div class="pl-steps-body" id="plSteps">${E.steps.map(stepCard).join('')}</div>
    </div>`;
}

/* ---------------- 编辑操作 ---------------- */
window.plEdit = function(k, v){ PL_EDIT[k] = v; };
window.plSet = function(i, k, v){ PL_EDIT.steps[i][k] = (k==='checkpoint') ? !!v : v; };
/* 就地改：整页重渲染会把「高级配置」折叠回去，选一次引擎就得重新展开 */
window.plAdvTouch = function(i){
  const s = PL_EDIT.steps[i]||{}; const el = document.getElementById('advDot-'+i);
  if(el) el.style.display = (s.model||s.engine||(s.extra_skills||[]).length||s.extra_prompt)?'':'none';
};
window.plRole = function(i, v){
  plSet(i,'role',v);
  const r = ROLES().find(x=>x.v===v); const el = document.getElementById('roleHint-'+i);
  if(r && el) el.textContent = r.hint;
};
window.plEng = function(i, v){ plSet(i,'engine',v); plAdvTouch(i); };
window.plExtraAdd = function(i, name){
  if(!name) return;
  const s = PL_EDIT.steps[i];
  s.extra_skills = s.extra_skills || [];
  if(!s.extra_skills.includes(name)) s.extra_skills.push(name);
  plDrawEditor();
};
window.plExtraDel = function(i, xi){ PL_EDIT.steps[i].extra_skills.splice(xi,1); plDrawEditor(); };
window.plAdd = function(){
  PL_EDIT.steps.push(plBlankStep(PL_EDIT.steps.length + 1));
  plDrawEditor();
  requestAnimationFrame(()=>{
    const cards = document.querySelectorAll('.step-card');
    const last = cards[cards.length-1];
    if(last) last.scrollIntoView({behavior:'smooth', block:'center'});
  });
};
window.plDel = function(i){
  PL_EDIT.steps.splice(i,1);
  if(!PL_EDIT.steps.length) PL_EDIT.steps.push(plBlankStep(1));
  plDrawEditor();
};
window.plMove = function(i, d){
  const j = i + d;
  if(j<0 || j>=PL_EDIT.steps.length) return;
  const a = PL_EDIT.steps;
  [a[i], a[j]] = [a[j], a[i]];
  plDrawEditor();
};
window.renderPipelineEdit = async function(name){
  window.viewLoading();
  await Promise.all([plLoad(), stPresets()]);
  if(name && name !== 'new'){
    const p = PL_TPLS.find(x=>x.name===name);
    if(!p){ toast(t('ed.notFound')); nav.go('pipelines'); return; }
    PL_EDIT = JSON.parse(JSON.stringify(p));
  }else{
    PL_EDIT = {name:'', label:'', desc:'', g:'custom', steps:[plBlankStep(1)]};
  }
  plDrawEditor();
  PL_BASE = plSnap(PL_EDIT);   // 刚渲染完就是"已保存"的基准
};

window.plSave = async function(){
  const E = PL_EDIT;
  plSyncInputs();
  const name = E.name || (E._draftName||'').trim() || ($('#plName') && $('#plName').value || '').trim();
  if(!name){ toast(t('ed.needName')); return; }
  const label = (($('#plLabel') && $('#plLabel').value) || E.label || '').trim() || name;
  const keys = new Set();
  for(let i=0;i<E.steps.length;i++){
    const s = E.steps[i];
    if(!(s.label||'').trim()){ toast(t('ed.needLabel',{n:i+1})); return; }
    const key = (s.key||'').trim();
    if(!/^[a-z0-9][a-z0-9_-]*$/.test(key)){ toast(t('ed.needKey',{n:i+1,key})); return; }
    if(keys.has(key)){ toast(t('ed.needKey',{n:i+1,key})); return; }
    keys.add(key);
    if(!(s.skill||'').trim()){ toast(t('ed.needSkill',{n:i+1,label:s.label||key})); return; }
  }
  const payload = { name, label, desc: E.desc||'', g: E.g||'custom',
    steps: E.steps.map(s=>({
      key:(s.key||'').trim(), label:(s.label||'').trim(),
      skill:[(s.skill||'').trim(), ...(s.extra_skills||[])].join(' ').trim(),
      skill_src:(s.skill_src||''),
      out:(s.out||'').trim(), checkpoint:!!s.checkpoint,
      role:s.role||'executor', model:(s.model||'').trim(),
      engine:(s.engine||'').trim(), extra_prompt:(s.extra_prompt||'').trim(),
    })),
  };
  const isNew = !E.name;
  const url = isNew ? '/api/pipelines' : `/api/pipelines/${encodeURIComponent(E.name)}`;
  const r = await (isNew ? _post(url, payload) : _put(url, payload)).catch(e=>({detail:e.message}));
  if(r.detail){ toast(r.detail); return; }
  toast(t('ed.saved'), true);
  window.markSavedClean('pl');
  nav.go('pipelines');
};

/* ---------------- 提示词预览 ---------------- */
window.plPreview = async function(i){
  const E = PL_EDIT;
  if(!E.name){ toast(t('ed.unsavedPreview')); return; }
  const raw = prompt(t('ed.previewBriefPh'));
  if(raw===null) return;
  const d = await _api(`/api/pipelines/${encodeURIComponent(E.name)}/preview/${i}?brief=`+encodeURIComponent(raw.trim()))
    .catch(e=>({detail:e.message}));
  if(d.detail){ toast(d.detail); return; }
  const mainSkill = String((E.steps[i]||{}).skill||'').trim().split(/\s+/)[0] || '';
  _lockScroll(true);
  const root = document.createElement('div');
  root.id='pvPromptRoot';
  root.innerHTML = `<div class="modal open" onclick="if(event.target===this)plClosePreview()">
    <div class="modal-box sk-view-modal">
      <div class="modal-top"><div class="pv-head"><h3>${esc(t('ed.previewTitle',{n:i+1}))}</h3>
        <span class="sk-badge">${esc(window.ENGINE_LABEL(d.engine))}</span></div>
        <button class="modal-x" onclick="plClosePreview()">×</button></div>
      <div class="sk-view-body">
        <div class="pp-label">${esc(t('ed.previewSystem'))}</div>
        <pre class="sk-pre">${esc(d.system)}</pre>
        <div class="pp-label">${esc(t('ed.previewUser'))}</div>
        <pre class="sk-pre">${esc(d.user)}</pre>
      </div>
      <div class="sk-view-foot">
        <button class="btn btn-ghost btn-sm" onclick="plClosePreview()">${esc(t('c.close'))}</button>
        <button class="btn btn-primary btn-sm" onclick="plClosePreview();nav.go('skill-edit/${jsq(mainSkill)}')">${esc(t('ed.goSkill'))}</button>
      </div>
    </div></div>`;
  document.body.appendChild(root);
};
window.plClosePreview = function(){ const r=document.getElementById('pvPromptRoot'); if(r) r.remove(); _lockScroll(false); };

})();
