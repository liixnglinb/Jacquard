/* 页内确认框（ffAsk）：替代原生 confirm()。
 *
 * 为什么必须换：原生 confirm() 在 WebView2 里顶着一句「127.0.0.1:8000 显示」——
 * 那是开发服务器来源，不是软件名；按钮是系统蓝，跟黑白金的品牌无关；它还会把
 * 整个页面线程挂起。装更新那两记 confirm 在 1.2.6 就因此换成了页内两步确认，
 * 这一份把同一待遇给到其余全部确认场景。
 *
 * 结构契约：渲染成 .modal.open > .modal-box，voyra-dialogs.js 会自动给它挂上
 * role=dialog / aria-modal / Tab 循环 / Esc 关闭（点 data-dialog-close）/ 关闭后
 * 焦点还原。默认焦点放在"取消"上——危险操作的安全默认是"不做"。
 * Enter=确认、Esc=取消，与原生 confirm 的肌肉记忆一致。
 */
(() => {
  'use strict';
  let seq = 0;
  let chain = Promise.resolve();          // 上一枚没关，新的排队：连点删除不会叠两层

  const esc = s => String(s == null ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  const T = (k, fallback) => (window.t ? window.t(k) : fallback);

  window.ffAsk = function(o) {
    o = o || {};
    const run = () => new Promise(resolve => {
      const n = ++seq;
      const mask = document.createElement('div');
      mask.className = 'modal open ff-ask';
      mask.innerHTML =
        '<div class="modal-box ff-ask-box modal-enter" role="alertdialog" aria-modal="true"'
        + ' aria-labelledby="ffAskTtl' + n + '">'
        + '<div class="modal-top"><h3 id="ffAskTtl' + n + '">' + esc(o.title || T('ff.confirm', '请确认')) + '</h3>'
        + '<button type="button" class="modal-x" data-ask="0" data-dialog-close'
        + ' aria-label="' + esc(T('c.cancel', '取消')) + '">×</button></div>'
        + (o.body ? '<div class="ff-ask-body">' + esc(o.body) + '</div>' : '')
        + '<div class="modal-foot">'
        + '<button type="button" class="btn btn-ghost" data-ask="0" data-dialog-close data-safe-focus>'
        + esc(o.cancel || T('c.cancel', '取消')) + '</button>'
        + '<button type="button" class="btn ' + (o.danger ? 'btn-danger' : 'btn-primary') + '" data-ask="1">'
        + esc(o.ok || T('ff.ok', '确定')) + '</button>'
        + '</div></div>';
      const done = v => { mask.remove(); resolve(v); };
      mask.addEventListener('click', e => {
        const b = e.target.closest('[data-ask]');
        if (b) { e.preventDefault(); done(b.dataset.ask === '1'); return; }
        if (e.target === mask) done(false);          // 点遮罩 = 取消，与浮层习惯一致
      });
      mask.addEventListener('keydown', e => {
        if (e.key === 'Enter' && !e.shiftKey && !e.isComposing
            && e.target && e.target.tagName !== 'BUTTON') { e.preventDefault(); done(true); }
      });
      document.body.appendChild(mask);
    });
    const p = chain.then(() => run());
    chain = p.catch(() => {});
    return p;
  };
})();
