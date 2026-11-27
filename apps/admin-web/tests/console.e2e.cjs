const assert = require("node:assert/strict");
const path = require("node:path");
const { chromium } = require(process.env.ADMIN_PLAYWRIGHT_PATH || "../../../frontend/node_modules/playwright");

const origin = process.env.ADMIN_TEST_URL || "http://127.0.0.1:3002";
const testAPI = process.env.ADMIN_TEST_BACKEND || "http://127.0.0.1:8001";
const learnerOrigin = process.env.ADMIN_TEST_LEARNER_URL;
const captureDirectory = process.env.ADMIN_SCREENSHOT_DIR;
const sections = [
  ["", "系统运行总览"],
  ["/models", "AI 模型管理"],
  ["/sources", "数据源管理"],
  ["/notifications", "通知管理"],
  ["/memory", "记忆策略"],
  ["/jobs", "任务调度"],
  ["/monitoring", "系统监控"],
  ["/settings", "系统设置"],
];

async function visible(locator) {
  await locator.first().waitFor({ state: "visible" });
}

async function login(page, email, password) {
  await page.getByLabel("管理员邮箱").fill(email);
  await page.locator("#admin-password").fill(password);
  await page.getByRole("button", { name: "进入管理控制台" }).click();
}

async function checkSharedLearning(browser, admin, gateway, email, password) {
  assert.equal(new URL(learnerOrigin).origin, "http://127.0.0.1:3031");
  const learner = await browser.newContext();
  try {
    const testProxy = await learner.request.get(learnerOrigin + "/api/v1/testing/identity", { maxRedirects: 0 });
    assert.equal(testProxy.status(), 200);
    assert.equal((await testProxy.json()).environment, "isolated-browser-test", "learner proxy must expose the isolated test route");
    const write = async (endpoint, body) => {
      const result = await learner.request.post(learnerOrigin + "/api/v1" + endpoint, {
        data: body,
        headers: { "X-Memory-Client": "web", Origin: learnerOrigin, "Idempotency-Key": crypto.randomUUID() },
      });
      assert(result.ok(), endpoint + " returned " + result.status());
      return result.status() === 204 ? null : result.json();
    };
    const { access_token: token } = await write("/auth/token", { email, password });
    const protectedAnalytics = await learner.request.get(testAPI + "/api/v1/admin/analytics", {
      headers: { Authorization: "Bearer " + token },
    });
    assert.equal(protectedAnalytics.status(), 403);
    await write("/workspace/onboarding/complete");
    await admin.goto(origin);
    await visible(admin.getByRole("heading", { name: "系统运行总览" }));
    const adminGet = async (path) => {
      const result = await admin.request.get(gateway + path);
      assert.equal(result.status(), 200);
      return result.json();
    };
    const before = await adminGet("/analytics");
    const suffix = Date.now();
    const subject = await write("/subjects", { name: "共享数据验收 " + suffix, slug: "shared-" + suffix });
    const chapter = await write("/chapters", {
      subject_id: subject.id, title: "跨站同源学习记录 " + suffix, status: "in_progress", content: "隔离验收章节",
    });
    await write("/knowledge-points", {
      subject_id: subject.id, title: "共享验收知识点 " + suffix,
      body: "隔离数据库中的验收数据", summary: "知识点验收摘要", difficulty: 2, status: "active",
    });
    const learnerPage = await learner.newPage();
    await learnerPage.goto(learnerOrigin + "/app?view=learning");
    await learnerPage.getByRole("button", { name: new RegExp(chapter.title) }).click();
    const study = learnerPage.locator("dialog[open]");
    await study.getByLabel("学习时长（分钟）").fill("35");
    await study.getByRole("button", { name: "保存学习记录" }).click();
    await visible(learnerPage.getByRole("status").filter({ hasText: "这次学习已记录" }));
    await learnerPage.goto(learnerOrigin + "/app?view=review");
    await learnerPage.getByRole("button", { name: "更新任务", exact: true }).click();
    await learnerPage.locator(".lx-review-row").first().click();
    const review = learnerPage.locator("dialog[open]");
    await review.getByRole("button", { name: "查看知识点与解析", exact: true }).click();
    await review.getByRole("button", { name: "记得", exact: true }).click();
    await visible(learnerPage.getByRole("status").filter({ hasText: "复习已保存" }));

    const insights = await learner.request.get(learnerOrigin + "/api/v1/workspace/insights?days=30");
    assert.equal(insights.status(), 200);
    const personal = await insights.json();
    const request = admin.waitForResponse(response => response.url().startsWith(gateway + "/analytics?"));
    await admin.getByRole("button", { name: "刷新数据" }).click();
    const refreshed = await request;
    assert.equal(refreshed.status(), 200);
    const after = await refreshed.json();
    assert.equal(after.from_date, before.from_date);
    assert.equal(after.to_date, before.to_date);
    for (const [key, amount] of [
      ["knowledge", 1], ["study_seconds", personal.activity.reduce((seconds, day) => seconds + day.study_seconds, 0)],
      ["reviews", 1], ["assigned", 1], ["completed", 1],
    ]) {
      const total = (window) => window.learning.reduce((count, day) => count + day[key], 0);
      assert.equal(total(after) - total(before), amount, key);
    }
    assert.equal(personal.metrics.today_reviews, 1);
    assert.equal(personal.metrics.today_completed_tasks, 1);
    const waiting = admin.waitForResponse(response => response.url().startsWith(gateway + "/analytics?"));
    await admin.getByRole("button", { name: "近 7 天", exact: true }).click();
    assert.equal((await (await waiting).json()).learning.length, 7);
    await admin.goto(origin + "/jobs");
    await visible(admin.getByRole("heading", { name: "任务运行汇总" }));
    await visible(admin.getByText("已生成的复习批次", { exact: true }));
  } finally {
    await learner.close();
  }
}

async function checkOperations(admin, gateway, email, password) {
  const loginResponse = await admin.request.post(testAPI + "/api/v1/auth/token", { data: { email, password } });
  assert.equal(loginResponse.status(), 200);
  const token = (await loginResponse.json()).access_token;
  const direct = async (method, path, data, headers = {}) => {
    const response = await admin.request.fetch(testAPI + "/api/v1" + path, {
      method, data, maxRedirects: 0, headers: { ...headers, Authorization: "Bearer " + token },
    });
    assert(response.ok(), method + " " + path + " returned " + response.status());
    return response.json();
  };
  const get = async (path) => {
    const response = await admin.request.get(gateway + path);
    assert.equal(response.status(), 200, path);
    return response.json();
  };
  const suffix = Date.now();
  const { id: ownerId } = await direct("GET", "/me");
  assert(ownerId, "Fixture learner account must have an ID");
  const model = "fixture-admin-model-" + suffix;
  const source = "管理员同步测试 " + suffix;
  const fixtureKey = "isolated-admin-test-secret";
  await direct("PUT", "/workspace/model", { provider: "openai", model_name: model, api_key: fixtureKey });
  await direct("PUT", "/workspace/notion/token", { token: fixtureKey });
  const sync = await direct("POST", "/workspace/notion/connect", {
    name: source, subject_name: "管理端验收", external_id: crypto.randomUUID(),
  });
  const { profile } = await direct("GET", "/workspace/settings");
  await direct("PUT", "/workspace/email", {
    provider: "qq", username: "fixture-" + suffix + "@qq.com", password: fixtureKey,
  }, { "If-Match": '"' + profile.version + '"' });
  await direct("POST", "/workspace/email/test", undefined, { "Idempotency-Key": crypto.randomUUID() });
  for (const endpoint of ["/model-providers", "/sources", "/notification-channels", "/notification-deliveries", "/jobs", "/memory-policies"]) {
    const result = await get(endpoint);
    assert(Array.isArray(result.items), endpoint);
    assert(!JSON.stringify(result).includes(fixtureKey), endpoint);
  }

  await admin.goto(origin + "/models");
  await visible(admin.getByRole("heading", { name: "已配置模型" }));
  const modelRow = admin.getByRole("row").filter({ hasText: model });
  await modelRow.getByRole("button", { name: "检查配置" }).click();
  await visible(admin.getByRole("dialog", { name: "模型配置检查" }).getByText("尚未向模型供应商发送请求。", { exact: false }));
  await admin.keyboard.press("Escape");
  const update = admin.waitForResponse(response =>
    response.url().startsWith(gateway + "/model-providers?") && response.request().method() === "PATCH");
  await modelRow.getByRole("button", { name: "停用" }).click();
  const change = await update;
  assert.equal(change.status(), 200);
  assert.equal((await change.json()).is_enabled, false);
  assert(await change.request().headerValue("if-match"));
  await visible(modelRow.getByRole("button", { name: "启用" }));

  await admin.goto(origin + "/sources");
  const sourceRow = admin.getByRole("row").filter({ hasText: source });
  await sourceRow.getByRole("button", { name: "同步历史" }).click();
  await visible(admin.getByRole("dialog").getByRole("row").filter({ hasText: "待处理" }));
  await admin.keyboard.press("Escape");
  await sourceRow.getByRole("button", { name: "手动同步" }).click();
  const queued = admin.waitForResponse(response => response.url().startsWith(gateway + "/source-sync?"));
  await admin.getByRole("dialog").getByRole("button", { name: "确认排队" }).click();
  const queuedResult = await queued;
  assert.equal(queuedResult.status(), 202);
  assert.equal((await queuedResult.json()).id, sync.id);
  await visible(admin.getByRole("status").filter({ hasText: "同步任务已登记" }));
  await direct("POST", "/testing/drain");

  await admin.goto(origin + "/notifications");
  await visible(admin.getByRole("heading", { name: "通知渠道" }));
  await admin.getByLabel("投递状态").selectOption("sent");
  await visible(admin.getByRole("row").filter({ hasText: "普通验收用户" }).filter({ hasText: "已提交服务商" }));
  const deliveries = await get("/notification-deliveries?user_id=" + encodeURIComponent(ownerId));
  assert(deliveries.items.some(item => item.status === "sent" && item.provider_accepted));

  await admin.goto(origin + "/memory");
  await visible(admin.getByRole("heading", { name: "默认记忆策略" }));
  await visible(admin.getByText("默认算法", { exact: true }));
  const simulationForm = admin.locator("form").filter({
    has: admin.getByRole("button", { name: "运行模拟", exact: true }),
  });
  await simulationForm.getByRole("combobox").selectOption("ebbinghaus");
  const simulation = admin.waitForResponse(response => response.url() === gateway + "/memory-simulations");
  await admin.getByRole("button", { name: "运行模拟" }).click();
  const simulated = await simulation;
  assert.equal(simulated.status(), 200);
  const result = await simulated.json();
  assert.equal(result.simulation, true);
  assert(result.steps.length > 0);
  await visible(admin.getByText(/算法版本/));

  await admin.goto(origin + "/jobs");
  await visible(admin.getByRole("heading", { name: "实际任务记录" }));
  await admin.getByLabel("任务类型").selectOption("notion");
  const jobs = await get("/jobs?kind=notion&user_id=" + encodeURIComponent(ownerId));
  assert(jobs.items.some(item => item.id === sync.id));

  await admin.goto(origin + "/monitoring");
  await visible(admin.getByRole("heading", { name: "后台运行与资源采样" }));
  await visible(admin.getByText("已暂停", { exact: true }));
  const telemetry = await get("/telemetry?minutes=60");
  assert(telemetry.requests > 0);
  assert(telemetry.errors >= 0);
  await visible(admin.getByText("近似 P95 延迟", { exact: true }));

  await admin.goto(origin + "/settings");
  await visible(admin.getByRole("heading", { name: "系统信息与备份" }));
  const createBackup = admin.getByRole("button", { name: "创建备份", exact: true });
  await visible(createBackup);
  const backup = await get("/backups");
  assert.equal(await createBackup.isEnabled(), backup.enabled);
  if (!backup.enabled) await visible(admin.getByText("服务器备份功能尚未配置。", { exact: true }));
  console.log("PASS genuine admin operations: provider configuration and versioned change, source history and queued sync, fixture delivery, memory simulation, job list, telemetry and backup config");
}

async function main() {
  const browser = await chromium.launch({ channel: process.env.PREVIEW_BROWSER_CHANNEL || "msedge", headless: true });
  try {
    const demo = await browser.newContext({ viewport: { width: 1536, height: 1024 } });
    const page = await demo.newPage();
    const errors = [];
    const gatewayRequests = [];
    page.on("pageerror", error => errors.push(error.message));
    page.on("request", request => {
      const url = new URL(request.url());
      if (url.origin !== origin || url.pathname.startsWith("/api/admin-gateway/")) gatewayRequests.push(url.pathname);
    });

    for (const [segment, title] of sections) {
      assert.equal((await page.goto(origin + "/demo" + segment)).status(), 200);
      await visible(page.getByRole("heading", { name: new RegExp(title) }));
      await visible(page.getByText(/演示模式 · 图表和操作/));
      assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
    }
    console.log("PASS desktop demo: eight routes and no horizontal overflow");

    await page.getByRole("link", { name: "系统总览", exact: true }).click();
    await visible(page.locator(".recharts-surface"));
    for (const days of [7, 30, 90]) {
      const button = page.getByRole("button", { name: "近 " + days + " 天" });
      await button.click();
      assert.equal(await button.getAttribute("aria-pressed"), "true");
    }
    await page.getByRole("button", { name: "自定义", exact: true }).click();
    const dates = page.locator('input[type="date"]');
    await dates.nth(0).fill("2026-10-05");
    await dates.nth(1).fill("2026-10-20");
    await page.getByRole("button", { name: "应用范围" }).click();
    await visible(page.locator(".recharts-surface"));
    await page.getByLabel("记忆保持率学科").selectOption({ index: 1 });
    console.log("PASS dashboard date presets, custom range, subject comparison");

    await page.goto(origin + "/demo/models");
    await page.getByRole("button", { name: "添加模型" }).click();
    await visible(page.getByRole("dialog"));
    assert(await page.getByRole("dialog").locator('input[type="password"]').count());
    await page.keyboard.press("Escape");
    await page.getByRole("button", { name: "连接测试" }).first().click();
    await visible(page.getByRole("status"));
    await page.goto(origin + "/demo/sources");
    await page.getByRole("button", { name: "手动同步" }).first().click();
    await visible(page.getByRole("status"));
    await page.goto(origin + "/demo/notifications");
    await page.getByRole("button", { name: "测试发送" }).first().click();
    await page.getByRole("button", { name: "保存模板" }).click();
    await visible(page.getByRole("status"));
    await page.goto(origin + "/demo/memory");
    await page.getByRole("button", { name: "模拟预览" }).click();
    await visible(page.locator(".recharts-surface"));
    await page.goto(origin + "/demo/jobs");
    await page.getByRole("button", { name: "详情" }).first().click();
    await visible(page.getByRole("dialog"));
    await page.keyboard.press("Escape");
    await page.getByRole("combobox", { name: "任务状态" }).selectOption("failed");
    await page.goto(origin + "/demo/monitoring");
    await page.getByRole("button", { name: "刷新服务状态" }).click();
    await page.goto(origin + "/demo/settings");
    await page.getByRole("button", { name: "备份入口" }).click();
    await visible(page.getByRole("dialog"));
    await page.keyboard.press("Escape");
    await page.getByRole("button", { name: "查看登录" }).first().click();
    assert.deepEqual(errors, []);
    assert.deepEqual(gatewayRequests, []);
    console.log("PASS demo controls: charts, models, sources, notifications, policies, jobs, monitoring, backup and login history; zero API requests");

    if (captureDirectory) {
      await page.goto(origin + "/demo");
      await visible(page.locator(".recharts-surface"));
      await page.screenshot({ path: path.join(captureDirectory, "admin-dashboard.png"), fullPage: true });
    }

    const mobile = await browser.newPage({ viewport: { width: 390, height: 844 }, isMobile: true, deviceScaleFactor: 1, hasTouch: true });
    await mobile.goto(origin + "/demo");
    await visible(mobile.getByRole("heading", { name: "系统运行总览" }));
    await mobile.getByRole("button", { name: "打开导航" }).click();
    await mobile.getByRole("link", { name: "AI 模型管理" }).click();
    for (const [segment, title] of sections) {
      await mobile.goto(origin + "/demo" + segment);
      await visible(mobile.getByRole("heading", { name: new RegExp(title) }));
      assert(await mobile.evaluate(() => document.documentElement.scrollWidth <= innerWidth), title + " overflow");
    }
    console.log("PASS mobile: all eight routes fit a 390 px viewport and navigation works");

    if (process.env.ADMIN_TEST_LIVE !== "1") return;
    // Only run these mutations against the repository's isolated test API.
    assert.equal(new URL(origin).origin, "http://127.0.0.1:3002");
    assert.equal(new URL(testAPI).hostname, "127.0.0.1");
    assert.notEqual(new URL(testAPI).port, "8000");
    const api = await browser.newContext();
    const testBackend = await api.request.get(testAPI + "/api/v1/testing/identity", { maxRedirects: 0 });
    assert.equal(testBackend.status(), 200);
    assert.equal((await testBackend.json()).environment, "isolated-browser-test");
    const admin = await api.newPage();
    admin.on("pageerror", error => errors.push(error.message));
    const gateway = origin + "/api/admin-gateway";
    const unauthenticated = await api.request.get(gateway + "/overview");
    assert.equal(unauthenticated.status(), 401);
    assert.equal((await api.request.get(gateway + "/analytics")).status(), 401);
    for (const endpoint of ["model-providers", "sources", "notification-channels", "notification-deliveries", "memory-policies", "jobs", "telemetry", "system-info", "backups"]) {
      assert.equal((await api.request.get(gateway + "/" + endpoint)).status(), 401, endpoint);
    }
    const rejectedOrigin = await api.request.post(gateway + "/login", { headers: { "X-Admin-Client": "console", Origin: "http://127.0.0.1:3030" }, data: {} });
    assert.equal(rejectedOrigin.status(), 403);

    const ordinaryEmail = "admin-interface-" + Date.now() + "@example.com";
    const ordinaryPassword = "Local-test-learner-123";
    const register = await api.request.post(testAPI + "/api/v1/auth/register", {
      data: { email: ordinaryEmail, password: ordinaryPassword, display_name: "普通验收用户" },
    });
    assert.equal(register.status(), 201);
    await admin.goto(origin + "/settings");
    await admin.waitForURL("**/login");
    const forbidden = admin.waitForResponse(response => response.url() === gateway + "/login");
    await login(admin, ordinaryEmail, ordinaryPassword);
    assert.equal((await forbidden).status(), 403);
    assert(!(await api.cookies()).some(cookie => cookie.name === "memory_admin_session"));

    const auth = admin.waitForResponse(response => response.url() === gateway + "/login");
    await login(admin, "portal-admin@example.com", "Browser-admin-pass-123");
    const success = await auth;
    assert.equal(success.status(), 200);
    const principal = await success.json();
    assert.equal(principal.role, "admin");
    assert(!("access_token" in principal));
    const cookie = (await api.cookies()).find(item => item.name === "memory_admin_session");
    assert(cookie && cookie.httpOnly && cookie.sameSite === "Strict" && cookie.path === "/api/admin-gateway");
    await visible(admin.getByRole("heading", { name: "系统运行总览" }));
    await visible(admin.getByRole("heading", { name: "知识自动整理", exact: true }));
    await visible(admin.getByText(/Token 实测样本/));
    const overview = await api.request.get(gateway + "/overview");
    assert.equal(overview.status(), 200);
    assert.equal(typeof (await overview.json()).counts.knowledge_points, "number");
    for (const endpoint of ["health", "users", "sessions", "audit", "analytics"]) {
      assert.equal((await api.request.get(gateway + "/" + endpoint)).status(), 200, endpoint);
    }
    const userQuery = await api.request.get(gateway + "/users?q=" + encodeURIComponent(ordinaryEmail));
    const [learner] = (await userQuery.json()).items;
    assert.equal(learner.email, ordinaryEmail);
    for (const endpoint of ["user-overview", "user-knowledge", "user-history"]) {
      assert.equal((await api.request.get(gateway + "/" + endpoint + "?user_id=" + learner.id)).status(), 200, endpoint);
    }
    if (learnerOrigin) {
      await checkSharedLearning(browser, admin, gateway, ordinaryEmail, ordinaryPassword);
      console.log("PASS learner browser writes and admin refresh share the same live analytics and real jobs");
    }
    await admin.goto(origin + "/settings");
    await visible(admin.getByRole("heading", { name: "系统设置" }));
    const fixturePrincipal = await api.request.get(testAPI + "/api/v1/me", {
      headers: { Authorization: "Bearer " + cookie.value },
    });
    assert.equal(fixturePrincipal.status(), 200, "The console must use the isolated backend before account mutations");
    assert.equal((await fixturePrincipal.json()).id, principal.id);
    await checkOperations(admin, gateway, ordinaryEmail, ordinaryPassword);
    const accountEmail = "admin-created-" + Date.now() + "@example.com";
    const create = admin.waitForResponse(response => response.url() === gateway + "/users" && response.request().method() === "POST");
    await admin.getByRole("button", { name: "新增学习者", exact: true }).click();
    const createForm = admin.getByRole("dialog", { name: "新增学习者" });
    await createForm.getByLabel("用户称呼").fill("独立控制台创建");
    await createForm.getByLabel("用户邮箱").fill(accountEmail);
    await createForm.locator('input[name="password"]').fill("Local-admin-created-456");
    await createForm.getByLabel("确认初始密码").fill("Local-admin-created-456");
    await createForm.getByRole("button", { name: "创建学习者" }).click();
    const createdResponse = await create;
    assert.equal(createdResponse.status(), 201);
    const account = await createdResponse.json();
    assert.equal(account.role, "user");
    assert.equal(account.email, accountEmail);
    assert.equal(account.is_active, true);
    assert(await createdResponse.request().headerValue("idempotency-key"));
    assert(!("password" in account));
    const accountRow = admin.getByRole("row").filter({ hasText: accountEmail });
    await visible(accountRow.getByText("已启用"));

    const update = admin.waitForResponse(response => response.url() === gateway + "/users?user_id=" + account.id && response.request().method() === "PATCH");
    await accountRow.getByRole("button", { name: "编辑学习者" }).click();
    const updateForm = admin.getByRole("dialog", { name: "编辑学习者" });
    await updateForm.getByLabel("用户称呼").fill("独立控制台已更新");
    await updateForm.getByLabel("启用学习者账号").uncheck();
    await updateForm.getByRole("button", { name: "保存学习者" }).click();
    const updatedResponse = await update;
    assert.equal(updatedResponse.status(), 200);
    assert.equal(await updatedResponse.request().headerValue("if-match"), `"${account.version}"`);
    const updatedAccount = await updatedResponse.json();
    assert.equal(updatedAccount.version, account.version + 1);
    assert.equal(updatedAccount.is_active, false);
    await visible(accountRow.getByText("独立控制台已更新"));
    await visible(accountRow.getByText("已停用"));
    console.log("PASS isolated admin account creation and versioned editing from the console UI");
    await admin.getByRole("button", { name: "退出登录" }).click();
    await admin.waitForURL("**/login");
    assert.equal((await api.request.get(gateway + "/overview")).status(), 401);
    const revoked = await api.request.get(testAPI + "/api/v1/me", { headers: { Authorization: "Bearer " + cookie.value } });
    assert.equal(revoked.status(), 401);
    assert.deepEqual(errors, []);
    console.log("PASS live: login redirect, ordinary user and cross-origin denied, admin role and scoped cookie, shared preview API data, session revoked");
  } finally {
    await browser.close();
  }
}

main().catch(error => { console.error(error); process.exitCode = 1; });
