const { chromium } = require("playwright");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

async function main() {
  const base = process.env.PORTAL_BASE_URL || "http://127.0.0.1:3031";
   assert.equal(new URL(base).origin, "http://127.0.0.1:3031", "Learning browser tests require the loopback test frontend");
   const identity = await fetch(base + "/api/v1/testing/identity", { redirect: "error" });
   assert.equal(identity.status, 200, "Expected an isolated backend through the learner proxy");
   assert.equal((await identity.json()).environment, "isolated-browser-test");
  const output = process.env.PORTAL_SCREENSHOT_DIRECTORY || path.join(process.cwd(), "test-results", "learning-experience");
  fs.mkdirSync(output, { recursive: true });
  const browser = await chromium.launch({ channel: "msedge", headless: true });
  function newTestContext(options = {}) {
    const hex = crypto.randomUUID().replaceAll("-", "").slice(0, 24);
    const client = "2001:db8:" + hex.match(/.{4}/g).join(":");
    return browser.newContext({ ...options, extraHTTPHeaders: { ...options.extraHTTPHeaders, "X-Memory-Test-Client": client } });
  }

  const context = await newTestContext({ viewport: { width: 1536, height: 1080 }, reducedMotion: "reduce" });
  const page = await context.newPage();
  const errors = [], external = [], serverErrors = [];
  page.on("pageerror", error => errors.push(error.message));
  page.on("request", request => { if (!request.url().startsWith(base) && !request.url().startsWith("data:")) external.push(request.url()); });
  page.on("response", response => { if (response.status() >= 500) serverErrors.push(response.url()); });
  let checks = 0;
  async function check(name, fn) { await fn(); checks++; console.log("PASS", name); }
  async function api(method, endpoint, body) {
    const response = await context.request.fetch(base + "/api/v1" + endpoint, { method, data: body, headers: { "X-Memory-Client": "web", Origin: base, "Idempotency-Key": crypto.randomUUID() } });
    assert.ok(response.ok(), `${endpoint}: ${response.status()} ${await response.text()}`);
    return response.status() === 204 ? null : response.json();
  }
  async function go(view) { await page.goto(base + "/app" + (view ? "?view=" + view : ""), { waitUntil: "networkidle" }); await page.locator(".lx-shell").waitFor(); }
  async function noOverflow() { assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1), `horizontal overflow: ${page.url()}`); }
  async function shot(name) { await page.screenshot({ path: path.join(output, name + ".png"), fullPage: true }); }
  try {
    await check("real-empty-dashboard-and-navigation", async () => {
      await api("POST", "/auth/register", { email: `experience-${Date.now()}@example.com`, display_name: "探索者", password: "Browser-learning-pass-123" });
      await api("POST", "/workspace/onboarding/complete");
      await go("");
      await page.locator(".lx-metric").first().waitFor();
      assert.equal(await page.locator(".lx-metric").count(), 5);
      assert.equal(await page.locator(".portal-sidebar nav a").count(), 12);
      await page.getByText("为你的学习旅程，准备一张地图", { exact: true }).waitFor();
      await noOverflow(); await shot("dashboard-empty");
    });
    const subjects = [];
    for (const name of ["Windows 内核", "英语学习", "数学"]) subjects.push(await api("POST", "/subjects", { name, slug: "ui-" + crypto.randomUUID().slice(0, 12) }));
    const chapters = [];
    for (let i = 0; i < 23; i++) chapters.push(await api("POST", "/chapters", { subject_id: subjects[i % 3].id, title: `探索章节 ${String(i + 1).padStart(2, "0")}`, content: "把这一章分成几个小目标，逐步记录理解与问题。", status: i % 3 === 0 ? "completed" : "in_progress" }));
    for (let i = 0; i < 24; i++) await api("POST", "/knowledge-points", { subject_id: subjects[i % 3].id, title: `学习卡片 ${String(i + 1).padStart(2, "0")}`, body: "这是浏览器回归在独立测试库中创建的知识正文。", summary: "回到原文理解概念，尝试主动回忆，再核对答案。", difficulty: 2, status: "active" });
    for (let i = 0; i < 14; i++) {
      const ended = new Date(Date.now() - i * 86400000 - 60000);
      await api("POST", `/chapters/${chapters[i].id}/study-sessions`, { started_at: new Date(ended.getTime() - (i % 4 + 1) * 1800000).toISOString(), ended_at: ended.toISOString(), notes: "浏览器回归学习记录" });
    }
    await check("due cards are visible before the queue exists", async () => {
      await go("review");
      const panel = page.getByRole("region", { name: "今日复习负荷" });
      await panel.getByText("自动后台已暂停，可手动更新本地复习任务。", { exact: true }).waitFor();
      assert.equal(await panel.locator("dd").allTextContents().then(values => values.join(", ")), "0 项, 24 项, 24 项, 样本不足");
      await page.getByRole("button", { name: "更新任务", exact: true }).click();
      await page.waitForFunction(() =>
        document.querySelector(".lx-review-workload dd")?.textContent === "24 项"
      );
      const queue = await api("GET", "/review-tasks?status=open");
      await api("POST", "/review-tasks/" + queue.items[0].id + "/start");
      await page.reload();
      await page.locator(".lx-review-row").getByText("进行中", { exact: true }).waitFor();
      await shot("review-workload");
    });
    await check("populated-dashboard-real-aggregates-and-charts", async () => {
      await go(""); await page.locator(".lx-metric").first().waitFor();
      const insights = await api("GET", "/workspace/insights");
      assert.equal(insights.metrics.knowledge_total, 24);
      assert.equal(insights.metrics.chapter_total, 23);
      assert.ok(insights.metrics.today_study_seconds > 0);
      assert.equal(await page.locator(".lx-donut").count(), 2);
      await page.getByRole("img", { name: "真实学习时长与复习次数趋势" }).waitFor();
      await noOverflow(); await shot("dashboard-populated");
      await page.setViewportSize({ width: 1280, height: 900 }); await noOverflow(); await shot("dashboard-1280");
      await page.setViewportSize({ width: 1536, height: 1080 });
    });
    await check("chapter-pagination-search-and-study-log", async () => {
      await go("learning"); await page.locator(".lx-chapter-card").first().waitFor();
      assert.equal(await page.locator(".lx-chapter-card").count(), 20);
      await page.getByRole("button", { name: "加载更多" }).click();
      await page.waitForFunction(() => document.querySelectorAll(".lx-chapter-card").length === 23);
      await page.getByLabel("搜索标题").fill("探索章节 23");
      await page.waitForFunction(() => document.querySelectorAll(".lx-chapter-card").length === 1);
      await page.getByRole("button", { name: /探索章节 23/ }).click();
      const dialog = page.locator("dialog[open]");
      await dialog.getByLabel("学习时长（分钟）").fill("35");
      await dialog.getByLabel("这次学到哪里了？").fill("学习记录已持久化");
      await dialog.getByRole("button", { name: "保存学习记录" }).click();
      await page.getByRole("status").filter({ hasText: "这次学习已记录" }).waitFor();
      const logs = await api("GET", `/chapters/${chapters[22].id}/study-sessions`);
      assert.equal(logs.items[0].duration_seconds, 2100);
      await page.getByLabel("搜索标题").fill(""); await page.locator(".lx-chapter-card").first().waitFor(); await shot("chapters");
    });
    await check("review-pagination-completion-and-history", async () => {
      await go("review"); await page.locator(".lx-review-row").first().waitFor();
      const generated = page.waitForResponse(r => r.url().includes("/review-batches/generate") && r.request().method() === "POST");
      await page.getByRole("button", { name: "更新任务", exact: true }).click();
      assert.equal((await generated).status(), 201);
      assert.equal(await page.locator(".lx-review-row").count(), 20);
      await page.getByRole("button", { name: "加载更多", exact: true }).click();
      await page.waitForFunction(() => document.querySelectorAll(".lx-review-row").length === 24);
      await shot("review-populated");
      await page.locator(".lx-review-row").first().click();
      const dialog = page.locator("dialog[open]");
      await dialog.getByRole("button", { name: "查看知识点与解析", exact: true }).click();
      await dialog.getByText("这张卡片尚未生成问答。先回忆它的关键内容，再对照原文检查。", { exact: true }).waitFor();
      await dialog.getByRole("button", { name: "记得", exact: true }).click();
      await page.getByRole("status").filter({ hasText: "复习已保存" }).waitFor();
      const result = await api("GET", "/workspace/insights");
      assert.equal(result.metrics.today_reviews, 1); assert.equal(result.metrics.pending_reviews, 23);
      await go("history"); await page.locator(".lx-review-row").first().waitFor();
      await page.locator(".lx-results").getByText("记得", { exact: true }).waitFor(); await shot("history-populated");
    });
    await check("subject-creation-and-knowledge-composer", async () => {
      await go("subjects"); await page.getByRole("button", { name: "添加学科", exact: true }).click();
      await page.getByLabel("学科名称").fill("天文学"); await page.getByLabel("学习方向").fill("探索星空");
      await page.getByRole("button", { name: "创建学科", exact: true }).click();
      await page.getByRole("heading", { name: "天文学", exact: true }).waitFor(); await shot("subjects");
      await go("knowledge"); await page.locator(".lx-knowledge-card").first().waitFor();
      await page.getByRole("button", { name: "新建知识点", exact: true }).click();
      const dialog = page.locator("dialog[open]"); await dialog.getByLabel("知识点标题").fill("恒星的形成"); await dialog.getByLabel("知识正文").fill("来自学习者手动保存的知识草稿。"); await dialog.getByRole("button", { name: "保存知识点" }).click();
      await page.locator("dialog[open]").waitFor({ state: "detached" });
      await page.getByLabel("搜索知识点").fill("恒星的形成"); await page.getByRole("heading", { name: "恒星的形成", exact: true }).waitFor();
      const draft = await api("GET", "/knowledge-points?q=" + encodeURIComponent("恒星的形成")); assert.equal(draft.items[0].status, "draft");
      await page.getByRole("button", { name: /恒星的形成/ }).click();
      await page.locator("dialog[open]").getByRole("button", { name: "加入复习计划", exact: true }).click();
      await page.getByRole("status").filter({ hasText: "知识点已加入复习" }).waitFor();
      const activated = await api("GET", "/knowledge-points?q=" + encodeURIComponent("恒星的形成")); assert.equal(activated.items[0].status, "active");
      await page.getByLabel("搜索知识点").fill(""); await page.locator(".lx-knowledge-card").first().waitFor(); await shot("knowledge");
    });
    await check("calendar-navigation-statistics-and-timezone-history-filters", async () => {
      await go("calendar"); await page.locator(".lx-calendar-grid button").first().waitFor();
      await page.getByRole("button", { name: "下个月", exact: true }).click(); await page.getByRole("button", { name: "今天", exact: true }).click(); await noOverflow(); await shot("calendar");
      await go("statistics"); await page.getByLabel("统计时间范围").selectOption("30");
      await page.waitForFunction(() => document.querySelectorAll(".lx-heatmap span").length === 30); await shot("statistics");
      await go("history");
      const response = page.waitForResponse(r => r.url().includes("/review-history?") && r.url().includes("from="));
      await page.getByLabel("历史开始日期").fill("2026-11-01"); await page.getByLabel("复习评分").selectOption("good");
      const result = await response; assert.equal(result.status(), 200);
      const url = new URL(result.url()); assert.equal(url.searchParams.get("from"), "2026-10-31T16:00:00.000Z"); await shot("history");
    });
    await check("source-notification-assistant-and-global-search", async () => {
      for (const view of ["notion", "mail", "assistant", "settings", "review"]) { await go(view); await noOverflow(); await shot(view); }
      await go("assistant"); await page.getByLabel("检索我的知识").fill("学习卡片 01"); await page.getByRole("button", { name: "检索笔记", exact: true }).click(); await page.getByRole("button", { name: /学习卡片 01/ }).click(); await page.locator("dialog[open] p.portal-prose").filter({ hasText: "这是浏览器回归在独立测试库中创建的知识正文。" }).waitFor(); await page.getByRole("button", { name: "关闭详情", exact: true }).click();
      await page.keyboard.press("Control+k"); await page.getByLabel("全局搜索").fill("学习卡片 02"); await page.getByLabel("全局搜索").press("Enter"); await page.getByRole("heading", { name: "学习卡片 02", exact: true }).waitFor();
    });
    await check("subject-groups-and-defer-from-the-review-dialog", async () => {
      await go("review");
      await page.locator(".lx-results").getByRole("heading", { name: "Windows 内核", exact: true }).waitFor();
      await page.locator(".lx-review-row").first().click();
      const deferred = page.waitForResponse(response => response.url().endsWith("/defer"));
      await page.getByRole("button", { name: "延期一天", exact: true }).click();
      assert.equal((await deferred).status(), 200);
      await page.getByRole("status").filter({ hasText: "复习已延期" }).waitFor();
      assert.equal((await api("GET", "/workspace/insights")).metrics.today_reviews, 1);
    });
    await check("save-new-knowledge-memory-strategy", async () => {
      await go("settings");
      const preferences = page.getByRole("region", { name: "记忆策略设置" });
      await preferences.getByLabel("记忆算法").selectOption("ebbinghaus");
      await preferences.getByRole("textbox", { name: "固定间隔（天，逗号分隔）" }).fill("2, 5, 9");
      await preferences.getByLabel("学习目标").fill("复习专业概念");
      const saved = page.waitForResponse(response => response.url().endsWith("/memory-preferences"));
      await preferences.getByRole("button", { name: "保存记忆策略" }).click();
      assert.equal((await saved).status(), 200);
      const profile = (await api("GET", "/workspace/settings")).profile;
      assert.equal(profile.review_preferences.strategy, "ebbinghaus");
      assert.deepEqual(profile.review_preferences.intervals_days, [2, 5, 9]);
      assert.equal(profile.review_preferences.learning_goal, "复习专业概念");
    });
    assert.deepEqual(errors, []); assert.deepEqual(serverErrors, []); assert.deepEqual(external, []);
    console.log(`LEARNING_EXPERIENCE_PASSED checks=${checks} page_errors=0 server_errors=0 external_requests=0`);
  } catch (error) {
    await page.screenshot({ path: path.join(output, "failure.png"), fullPage: true });
    console.error("FAILURE_URL", page.url()); console.error((await page.locator("body").innerText()).slice(0, 2200)); throw error;
  } finally { await browser.close(); }
}
main().catch(error => { console.error(error); process.exit(1); });
