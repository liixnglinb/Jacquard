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

  // 5. 全程零控制台错误
  ok("控制台零错误", consoleErrors.length === 0, { consoleErrors: consoleErrors.slice(0, 4) });
  out.errors = consoleErrors;
  await browser.close();
};

go().then(() => { out.pass = true; console.log(JSON.stringify(out)); process.exit(0); })
  .catch(e => { out.fail = String(e && e.message || e).slice(0, 200);
    try { console.log(JSON.stringify(out)); } catch (_) { console.log(JSON.stringify({ pass: false, fail: out.fail })); }
    process.exit(1); });
