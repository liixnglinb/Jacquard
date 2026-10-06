#!/usr/bin/env node
/* 织流 E2E 冒烟：真起服务、真浏览器、真增删（数据目录由 FF_DATA_DIR 指进临时沙箱）。
 *
 * 用法：node tests/e2e_smoke.mjs --base http://127.0.0.1:<port>
 * 需要 playwright-core（channel:msedge 起 Edge）。找不到时打印一行明确的
 * { pass:false, reason } 并以 1 退出 —— 由 tests/test_e2e_smoke.py 包装成 pytest
 * 的 skip；本机一次性接法见 README「端到端测试」。
 *
 * 覆盖（每步失败即短路）：
 *   启动 → 首页输入台就位、零控制台错误
 *   建/查：API 建一条流程 → 列表出现
 *   ffAsk 删除流：删除 → 弹窗（焦点在取消）→ 取消 → 行还在 → 再删 → 确认 → 行没了
 *   Back 键守卫：编排器脏改 → 后退 → 弹确认 → 取消 URL 摆回且输入原样 → 确认 → 离开
 *   收尾：全程控制台零错误
 */
import { createRequire } from "node:module";

const arg = (k, d) => { const i = process.argv.indexOf(k); return i > 0 ? process.argv[i + 1] : d; };
const BASE = (arg("--base", "http://127.0.0.1:8000")).replace(/\/$/, "");

let chromium;
try {
  ({ chromium } = createRequire(import.meta.url)("playwright-core"));
} catch (e) {
  console.log(JSON.stringify({ pass: false, reason: "playwright-core 不可用：" + e.message.split("\n")[0] }));
  process.exit(1);
}

const out = { pass: false, checks: [], errors: [] };
const ok = (name, cond, extra) => { out.checks.push({ name, pass: !!cond, ...(extra ? { extra } : {}) }); if (!cond) throw new Error(name); };

const go = async () => {
  const browser = await chromium.launch({ channel: "msedge", headless: true });
  const page = await (await browser.newContext({ viewport: { width: 1600, height: 1000 } })).newPage();
  const consoleErrors = [];
  page.on("pageerror", e => consoleErrors.push("pageerror " + String(e).slice(0, 120)));
  page.on("console", m => { if (m.type() === "error") consoleErrors.push(m.text().slice(0, 120)); });
  const uniq = (v) => "e2e-" + Date.now().toString(36);
  const NAME = uniq();

  // 1. 启动
  await page.goto(BASE + "/#/", { waitUntil: "domcontentloaded" });
  // 首运行（沙箱空数据）：空状态必须带去处——问候语 + 「新建流程」主按钮
  await page.locator(".home-empty .btn").waitFor({ state: "visible", timeout: 20000 });
  ok("空状态带去处（新建流程 CTA）", (await page.locator(".home-empty .btn").count()) === 1);

  // 2. 经 API 建技能 + 流程（步骤必须绑真实存在的 skill，服务端会校验）
  const seeded = await page.evaluate(async name => {
    const j = async (u, m, b2) => { const r = await fetch(u, { method: m, headers: { "content-type": "application/json" }, body: b2 ? JSON.stringify(b2) : undefined }); return { s: r.status, d: await r.json().catch(() => ({})) }; };
    const sk = await j("/api/skills", "POST", { name: name + "-skill",
      content: "---\nname: " + name + "-skill\n---\n\nE2E 冒烟用，只含一句说明。" });
    if (sk.s !== 200) return { step: "skill", ...sk };
    const pl = await j("/api/pipelines", "POST", { name, label: "E2E 冒烟流程", steps: [
      { key: "a", label: "步骤甲", skill: name + "-skill", out: "A.md", checkpoint: false, role: "exec" }] });
    return { step: "pipeline", ...pl };
  }, NAME);
  ok("API 建技能+流程 200", seeded.s === 200, seeded);
  await page.goto(BASE + "/#/pipelines", { waitUntil: "domcontentloaded" });
  await page.locator(".pl-card-row").first().waitFor({ state: "visible", timeout: 20000 });
  ok("列表出现新流程", (await page.locator(".pl-card-row").count()) >= 1);

  // 3. Back 键守卫：进编排器 → 脏改 → 后退 → 确认框 → 取消（输入原样、URL 摆回）→ 再退 → 确认
  await page.evaluate(() => { const b = [...document.querySelectorAll(".pl-card-row button")]
    .find(x => x.textContent.trim() === "编辑"); if (b) b.click(); });
  await page.locator(".step-ipt-label").first().waitFor({ state: "visible", timeout: 20000 });
  await page.locator(".step-ipt-label").first().fill("E2E 脏改 " + NAME.slice(-4));
  await page.waitForTimeout(250);
  await page.goBack();
  await page.waitForTimeout(400);
  ok("脏退出弹确认", (await page.locator(".modal.open.ff-ask").count()) === 1);
  ok("默认焦点在取消", await page.evaluate(() =>
    !!document.activeElement && !!document.activeElement.closest("[data-ask='0']")));
  await page.evaluate(() => { const m = document.querySelector(".modal.open.ff-ask");
    [...m.querySelectorAll("[data-ask]")].filter(x => x.dataset.ask === "0").pop().click(); });
  await page.waitForTimeout(400);
  ok("取消：URL 摆回编排器", (await page.evaluate(() => location.hash)).includes("pipeline-edit"));
  ok("取消：输入原样保留", (await page.inputValue(".step-ipt-label")).startsWith("E2E 脏改"));
  await page.goBack();
  await page.waitForTimeout(350);
  await page.evaluate(() => { const m = document.querySelector(".modal.open.ff-ask");
    [...m.querySelectorAll("[data-ask]")].filter(x => x.dataset.ask === "1").pop().click(); });
  await page.waitForTimeout(700);
  ok("确认后离开编排器", !(await page.evaluate(() => location.hash)).includes("pipeline-edit"));

  // 4. ffAsk 删除流（含焦点断言与确认后真删）
  await page.goto(BASE + "/#/pipelines", { waitUntil: "domcontentloaded" });
  await page.locator(".pl-card-row").first().waitFor({ state: "visible", timeout: 20000 });
  const openDelete = async () => {
    // 行内 ⋯ 菜单 → 菜单里的「删除」；两段都按可见性找
    await page.evaluate(() => { const b = [...document.querySelectorAll(".pl-card-row button")]
      .find(x => /更多操作/.test((x.dataset.tip || "") + (x.getAttribute("aria-label") || "")) &&
        (x.offsetParent || x.getClientRects().length));
      if (b) b.click(); });
    await page.waitForTimeout(300);
    return page.evaluate(() => { const del = [...document.querySelectorAll("button")]
      .find(x => /删除/.test(x.textContent) && (x.offsetParent || x.getClientRects().length));
      if (del) { del.click(); return true; } return false; });
  };
  ok("打开删除入口", await openDelete());
  await page.waitForTimeout(300);
  ok("删除弹 ffAsk", (await page.locator(".modal.open.ff-ask").count()) === 1);
  await page.evaluate(() => { const m = document.querySelector(".modal.open.ff-ask");
    [...m.querySelectorAll("[data-ask]")].filter(x => x.dataset.ask === "0").pop().click(); });
  await page.waitForTimeout(400);
  const rowsAfterCancel = await page.locator(".pl-card-row").count();
  ok("取消后行还在", rowsAfterCancel >= 1, { rowsAfterCancel });
  ok("再开删除入口", await openDelete());
  await page.waitForTimeout(300);
  await page.evaluate(() => { const m = document.querySelector(".modal.open.ff-ask");
    [...m.querySelectorAll("[data-ask]")].filter(x => x.dataset.ask === "1").pop().click(); });
  await page.waitForTimeout(800);
  const rowsAfterDel = await page.locator(".pl-card-row").count();
  ok("确认后行消失", rowsAfterDel === 0, { rowsAfterDel });

  // 5. 关窗守卫（桥桩）：有任务在跑时点关闭 → 页内确认 → 取消不关/确认才关
  await page.evaluate(() => {
    if (!window.__realFetch) window.__realFetch = window.fetch.bind(window);
    const runsRe = new RegExp("/api/runs\\?");
    window.fetch = (u, o) => runsRe.test(String(u))
      ? Promise.resolve(new Response(JSON.stringify({ runs: [
          { id: "run-e2e", pipeline: "x", label: "x", status: "running", created_at: "2026-01-01T00:00:00" }] }),
        { status: 200, headers: { "content-type": "application/json" } }))
      : window.__realFetch(u, o);
    window.__winCalls = [];
    window.pywebview = { api: {
      win_close: async () => { window.__winCalls.push(1); },
      win_minimize: async () => {}, win_maximize_toggle: async () => {},
      win_state: async () => ({ maximized: false }) } };
    window.dispatchEvent(new Event("pywebviewready"));
  });
  await page.evaluate(() => window.renderSidebarLists());
  await page.waitForTimeout(400);
  ok("桥桩到位（窗口键出现）", await page.locator("#winClose").isVisible());
  await page.click("#winClose");
  await page.waitForTimeout(300);
  ok("关窗弹确认（有任务在跑）", (await page.locator(".modal.open.ff-ask").count()) === 1);
  await page.evaluate(() => { const m = document.querySelector(".modal.open.ff-ask");
    [...m.querySelectorAll("[data-ask]")]  .filter(x => x.dataset.ask === "0").pop().click(); });
  await page.waitForTimeout(300);
  ok("取消：窗口未关", (await page.evaluate(() => window.__winCalls.length)) === 0);
  await page.click("#winClose");
  await page.waitForTimeout(300);
  await page.evaluate(() => { const m = document.querySelector(".modal.open.ff-ask");
    [...m.querySelectorAll("[data-ask]")]  .filter(x => x.dataset.ask === "1").pop().click(); });
  await page.waitForTimeout(400);
  ok("确认：win_close 恰好一次", (await page.evaluate(() => window.__winCalls.length)) === 1);
  await page.evaluate(() => { window.fetch = window.__realFetch; });

  // 6. 技能删除确认：技能编辑页 → 删除 → 取消留存 → 确认删除
  await page.goto(BASE + "/#/skills", { waitUntil: "domcontentloaded" });
  // 删除键在双栏视图的列表面板头（skill-edit 单栏编辑页没有删除，这是既有布局）
  await page.locator(".sk-nav-item").first().waitFor({ state: "visible", timeout: 20000 });
  await page.locator(".sk-nav-item").first().click();
  await page.locator(".sk-pane-actions .btn-danger").waitFor({ state: "visible", timeout: 20000 });
  await page.locator(".btn-danger").first().click();
  await page.waitForTimeout(300);
  ok("删技能弹确认", (await page.locator(".modal.open.ff-ask").count()) === 1);
  await page.evaluate(() => { const m = document.querySelector(".modal.open.ff-ask");
    [...m.querySelectorAll("[data-ask]")]  .filter(x => x.dataset.ask === "0").pop().click(); });
  await page.waitForTimeout(300);
  ok("取消：留在技能页且面板还在", (await page.evaluate(() => location.hash)).endsWith("#/skills") &&
    (await page.locator(".sk-pane-actions .btn-danger").count()) === 1);
  await page.locator(".btn-danger").first().click();
  await page.waitForTimeout(300);
  await page.evaluate(() => { const m = document.querySelector(".modal.open.ff-ask");
    [...m.querySelectorAll("[data-ask]")]  .filter(x => x.dataset.ask === "1").pop().click(); });
  await page.waitForTimeout(800);
  // 用列表断言（单条 GET 会 404，浏览器会把 404 记成控制台错误，污染零错误断言）
  ok("确认后技能已删", await page.evaluate(async n => {
    const r = await fetch("/api/skills"); const d = await r.json();
    return r.status === 200 && !(d.skills || []).some(x => x.name === n);  }, NAME + "-skill"));

  // 7. 能力盘点未保存守卫：编辑记忆文件 → 关闭 → 确认框 → 取消留层 → 确认收层
  await page.goto(BASE + "/#/settings/caps", { waitUntil: "domcontentloaded" });
  await page.waitForTimeout(600);
  /* 注意：capsOpen 是"在资源管理器中显示"（POST /api/reveal），不是弹层；
     弹层是 capsView(eng,key,name)，且只有 key=memory 且未被截断才有编辑入口。
     这里只读真文件、只点取消/放弃，绝不点保存。 */
  const capsOpenBtn = await page.evaluate(() => { const b = [...document.querySelectorAll("button")]
    .find(x => /capsView\(/.test(x.getAttribute("onclick") || "") && /memory/.test(x.getAttribute("onclick") || ""));
    if (b) { b.click(); return true; } return false; });
  if (capsOpenBtn) {
    await page.waitForTimeout(400);
    await page.evaluate(() => { const b = [...document.querySelectorAll("button")]
      .find(x => /capsEditMem/.test(x.getAttribute("onclick") || "")); if (b) b.click(); });
    await page.waitForTimeout(300);
    await page.evaluate(() => { const t = document.getElementById("capsTa");
      if (t) { t.value = (t.value || "") + "\nE2E 未保存改动"; t.dispatchEvent(new Event("input", { bubbles: true })); } });
    await page.evaluate(() => { const b = [...document.querySelectorAll("button")]
      .find(x => /capsClose/.test(x.getAttribute("onclick") || "")); if (b) b.click(); });
    await page.waitForTimeout(300);
    ok("能力盘点未保存弹确认", (await page.locator(".modal.open.ff-ask").count()) === 1);
    await page.evaluate(() => { const m = document.querySelector(".modal.open.ff-ask");
      [...m.querySelectorAll("[data-ask]")]  .filter(x => x.dataset.ask === "0").pop().click(); });
    await page.waitForTimeout(250);
    ok("取消：盘点层还在", (await page.locator("#capsViewRoot").count()) === 1);
    await page.evaluate(() => { const b = [...document.querySelectorAll("button")]
      .find(x => /capsClose/.test(x.getAttribute("onclick") || "")); if (b) b.click(); });
    await page.waitForTimeout(250);
    await page.evaluate(() => { const m = document.querySelector(".modal.open.ff-ask");
      if (m) [...m.querySelectorAll("[data-ask]")]  .filter(x => x.dataset.ask === "1").pop().click(); });
    await page.waitForTimeout(400);
    ok("确认：盘点层收起", (await page.locator("#capsViewRoot").count()) === 0);
  }

  // 8. 全程零控制台错误
  ok("控制台零错误", consoleErrors.length === 0, { consoleErrors: consoleErrors.slice(0, 4) });
  out.errors = consoleErrors;
  await browser.close();
};

go().then(() => { out.pass = true; console.log(JSON.stringify(out)); process.exit(0); })
  .catch(e => { out.fail = String(e && e.message || e).slice(0, 200);
    try { console.log(JSON.stringify(out)); } catch (_) { console.log(JSON.stringify({ pass: false, fail: out.fail })); }
    process.exit(1); });
