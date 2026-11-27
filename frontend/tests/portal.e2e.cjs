const { chromium } = require("playwright");
const assert = require("node:assert/strict");
const path = require("node:path");
const fs = require("node:fs");

async function main() {
  const base = process.env.PORTAL_BASE_URL || "http://127.0.0.1:3031";
   assert.equal(new URL(base).origin, "http://127.0.0.1:3031", "Learning browser tests require the loopback test frontend");
   const identity = await fetch(base + "/api/v1/testing/identity", { redirect: "error" });
   assert.equal(identity.status, 200, "Expected an isolated backend through the learner proxy");
   assert.equal((await identity.json()).environment, "isolated-browser-test");
  const output =
    process.env.PORTAL_SCREENSHOT_DIRECTORY ||
    path.join(process.cwd(), "test-results", "portal");
  fs.mkdirSync(output, { recursive: true });
  const browser = await chromium.launch({ channel: "msedge", headless: true });
  function newTestContext(options = {}) {
    const hex = crypto.randomUUID().replaceAll("-", "").slice(0, 24);
    const client = "2001:db8:" + hex.match(/.{4}/g).join(":");
    return browser.newContext({ ...options, extraHTTPHeaders: { ...options.extraHTTPHeaders, "X-Memory-Test-Client": client } });
  }

  const context = await newTestContext({
    viewport: { width: 1536, height: 1080 },
  });
  const errors = [];
  const externalRequests = [];
  function observe(testPage) {
    testPage.on("pageerror", (error) => errors.push(error.message));
    testPage.on("request", (request) => {
      if (!request.url().startsWith(base) && !request.url().startsWith("data:"))
        externalRequests.push(request.url());
    });
  }
  context.on("page", observe);
  const page = await context.newPage();
  let activePage = page;
  const email = `portal-${Date.now()}@example.com`;
  const password = "Browser-user-pass-123";
  async function check(name, action) {
    try {
      await action();
      console.log("PASS", name);
    } catch (error) {
      await activePage.screenshot({
        path: path.join(output, "failure.png"),
        fullPage: true,
      });
      console.log("FAILURE_URL", activePage.url());
      console.log(
        "FAILURE_PAGE",
        (await activePage.locator("body").innerText()).slice(0, 1800),
      );
      throw error;
    }
  }

  try {
    await check("welcome-and-registration", async () => {
      await page.goto(base, { waitUntil: "networkidle" });
      await page.getByRole("heading", { name: "欢迎回来" }).waitFor();
      await page.screenshot({
        path: path.join(output, "welcome.png"),
        fullPage: true,
      });
      await page.getByRole("tab", { name: "注册", exact: true }).click();
      await page.getByLabel("称呼", { exact: true }).fill("浏览器验收用户");
      await page.getByLabel("账号邮箱", { exact: true }).fill(email);
      await page.getByLabel("登录密码", { exact: true }).fill(password);
      await page.getByLabel("确认密码", { exact: true }).fill(password);
      await page.getByRole("button", { name: "创建账户", exact: true }).click();
      await page.waitForURL("**/onboarding");
      await page
        .getByRole("heading", { name: "邮箱通知", exact: true })
        .waitFor();
      const cookie = (await context.cookies()).find(
        (c) => c.name === "memory_session",
      );
      assert.ok(cookie?.httpOnly);
      assert.equal(
        await page.evaluate(() => localStorage.getItem("alm:access_token")),
        null,
      );
      await page.screenshot({
        path: path.join(output, "onboarding-email.png"),
        fullPage: true,
      });
    });
    await check("email-configuration-in-wizard", async () => {
      await page.getByLabel("每日提醒时间").fill("00:00");
      await page
        .getByLabel("邮箱授权码 / SMTP 密码")
        .fill("browser-private-fixture-password");
      await page
        .getByRole("button", { name: "保存并继续", exact: true })
        .click();
      await page
        .getByRole("heading", { name: "连接 Notion", exact: true })
        .waitFor();
    });
    await check("notion-discovery-and-status-mapping", async () => {
      await page
        .getByLabel("Notion Token", { exact: true })
        .fill("browser-private-fixture-token");
      await page
        .getByRole("button", { name: "保存 Token", exact: true })
        .click();
      await page
        .getByRole("button", { name: "读取资料库", exact: true })
        .click();
      await page.getByRole("button", { name: /浏览器测试知识库/ }).click();
      await page.screenshot({
        path: path.join(output, "onboarding-notion.png"),
        fullPage: true,
      });
      assert.equal(
        await page.getByLabel("Notion Token", { exact: true }).inputValue(),
        "",
      );
      await page
        .getByRole("button", { name: "保存并继续", exact: true })
        .click();
      await page
        .getByRole("heading", { name: "选择 AI 模型", exact: true })
        .waitFor();
    });
    await check("model-consent-and-onboarding-completion", async () => {
      await page
        .getByLabel("API Key", { exact: true })
        .fill("browser-private-fixture-ai-key");
      await page.getByLabel(/允许使用此模型/).check();
      await page
        .getByRole("button", { name: "保存并继续", exact: true })
        .click();
      await page
        .getByRole("heading", { name: "你的学习空间已准备好", exact: true })
        .waitFor();
      await page
        .getByRole("button", { name: "进入学习空间", exact: true })
        .click();
      await page.waitForURL("**/app");
      const response = await context.request.post(
        base + "/api/v1/testing/drain",
        { headers: { "X-Memory-Client": "web" } },
      );
      assert.equal(response.status(), 200, await response.text());
      await page.getByRole("button", { name: "刷新", exact: true }).click();
      await page.getByText("章节 · 原始笔记", { exact: true }).waitFor();
      await page.screenshot({
        path: path.join(output, "workspace-real-data.png"),
        fullPage: true,
      });
    });
    await check("source-located-notion-analysis", async () => {
      await page.goto(base + "/app?view=notion");
      await page.getByRole("heading", { name: "知识自动整理", exact: true }).waitFor();
      await page.getByText(/自动后台已暂停/).waitFor();
      await page.getByText("章节 · 原始笔记", { exact: true }).click();
      await page.getByText("原文与示例的摘要", { exact: true }).waitFor();
      await page.getByText("知识点 1 的原文与分析", { exact: true }).click();
      await page.getByText("原文正文及例子。", { exact: true }).waitFor();
      await page.getByRole("button", { name: "查看知识与卡片 1" }).click();
      const dialog = page.locator("dialog[open]");
      await dialog.getByText("结合原文例子理解", { exact: true }).waitFor();
      await page.keyboard.press("Escape");
      await dialog.waitFor({ state: "detached" });
    });
    await check("real-review-completion", async () => {
      await page.locator(".portal-sidebar").getByRole("link", { name: /今日复习/ }).click();
      await page.getByRole("button", { name: /知识单元/ }).click();
      const dialog = page.locator("dialog[open]");
      await dialog.getByRole("button", { name: "查看知识点与解析" }).click();
      await dialog.getByText("结合原文例子理解", { exact: true }).waitFor();
      await dialog.getByRole("button", { name: "记得", exact: true }).click();
      await page
        .getByRole("status")
        .filter({ hasText: "复习已保存" })
        .waitFor();
    });
    await check("settings-edit-and-email-test", async () => {
      await page.getByRole("link", { name: "设置", exact: true }).click();
      await page
        .getByRole("button", { name: "发送测试邮件", exact: true })
        .click();
      assert.equal(
        (
          await context.request.post(base + "/api/v1/testing/drain", {
            headers: { "X-Memory-Client": "web" },
          })
        ).status(),
        200,
      );
      await page.getByLabel("每日提醒时间").fill("18:45");
      await page.getByRole("button", { name: "保存设置", exact: true }).click();
      await page
        .getByRole("status")
        .filter({ hasText: "设置已保存" })
        .waitFor();
      await page.reload({ waitUntil: "networkidle" });
      assert.equal(await page.getByLabel("每日提醒时间").inputValue(), "18:45");
      await page.getByRole("link", { name: "邮件通知", exact: true }).click();
      await page
        .getByText("AI 学习记忆系统 · 邮箱测试", { exact: true })
        .waitFor();
      await page
        .getByText("已提交邮件服务器", { exact: true })
        .first()
        .waitFor();
      assert.equal(
        await page
          .getByRole("link", { name: "管理员后台", exact: true })
          .count(),
        0,
      );
    });
    await check("logout-login-skips-completed-wizard", async () => {
      await page.getByRole("button", { name: "退出登录", exact: true }).click();
      await page.waitForURL(base + "/");
      await page.getByLabel("账号邮箱", { exact: true }).fill(email);
      await page.getByLabel("登录密码", { exact: true }).fill(password);
      await page.getByRole("button", { name: "登录", exact: true }).click();
      await page.waitForURL(base + "/app");
      const result = await context.request.get(
        base + "/api/v1/workspace/settings",
      );
      const settings = await result.json();
      assert.equal(settings.profile.reminder_time, "18:45");
      assert.ok(!JSON.stringify(settings).includes("browser-private-fixture"));
      assert.equal(
        (await context.request.get(base + "/api/v1/admin/users")).status(),
        403,
      );
    });
    await check(
      "email-review-link-survives-login-and-fits-mobile",
      async () => {
        const tasks = await (
          await context.request.get(base + "/api/v1/review-tasks?limit=100")
        ).json();
        const completed = tasks.items.find(
          (task) => task.status === "completed",
        );
        assert.ok(completed);
        const target = "/app?view=review&task=" + completed.id;
        const mobileContext = await newTestContext({
          viewport: { width: 390, height: 844 },
        });
        mobileContext.on("page", observe);
        const mobile = await mobileContext.newPage();
        activePage = mobile;
        await mobile.goto(base + target);
        await mobile.waitForURL(
          (url) => url.pathname === "/" && url.searchParams.has("next"),
        );
        await mobile.getByLabel("账号邮箱", { exact: true }).fill(email);
        await mobile.getByLabel("登录密码", { exact: true }).fill(password);
        await mobile.getByRole("button", { name: "登录", exact: true }).click();
        await mobile.waitForURL(base + target);
        const dialog = mobile.locator("dialog[open]");
        await dialog.getByRole("button", { name: "查看知识点与解析" }).click();
        await dialog.getByText("结合原文例子理解", { exact: true }).waitFor();
        await dialog
          .getByRole("status")
          .filter({ hasText: "本次任务已完成" })
          .waitFor();
        assert.equal(
          await dialog
            .getByRole("button", { name: "记得", exact: true })
            .count(),
          0,
        );
        assert.ok(
          await mobile.evaluate(
            () => document.documentElement.scrollWidth <= window.innerWidth,
          ),
        );
        await mobile.screenshot({
          path: path.join(output, "mobile-review-link.png"),
          fullPage: true,
        });
        await mobile.goto(
          base + "/?next=" + encodeURIComponent("https://external.invalid/"),
        );
        await mobile.waitForURL(base + "/app");
        await mobileContext.close();
        activePage = page;
      },
    );
    await check("skip-setup-and-cross-user-isolation", async () => {
      const secondContext = await newTestContext();
      secondContext.on("page", observe);
      const other = await secondContext.newPage();
      activePage = other;
      await other.goto(base, { waitUntil: "networkidle" });
      await other.getByRole("tab", { name: "注册", exact: true }).click();
      await other.getByLabel("称呼", { exact: true }).fill("另一位学习者");
      await other
        .getByLabel("账号邮箱", { exact: true })
        .fill(`other-${Date.now()}@example.com`);
      await other.getByLabel("登录密码", { exact: true }).fill(password);
      await other.getByLabel("确认密码", { exact: true }).fill(password);
      await other
        .getByRole("button", { name: "创建账户", exact: true })
        .click();
      await other.waitForURL("**/onboarding");
      for (const title of ["连接 Notion", "选择 AI 模型", "准备就绪"]) {
        await other
          .getByRole("button", { name: "稍后配置", exact: true })
          .click();
        await other
          .getByRole("heading", { name: title, exact: true })
          .waitFor();
      }
      await other
        .getByRole("button", { name: "进入学习空间", exact: true })
        .click();
      await other.waitForURL("**/app");
      const data = await (
        await secondContext.request.get(base + "/api/v1/workspace")
      ).json();
      assert.equal(data.sources.length, 0);
      assert.equal(data.knowledge_total, 0);
      assert.equal(data.mail_history.length, 0);
      const original = await (
        await context.request.get(base + "/api/v1/workspace")
      ).json();
      assert.equal(
        (
          await secondContext.request.get(
            base + "/api/v1/notion/data-sources/" + original.sources[0].id,
          )
        ).status(),
        404,
      );
      await secondContext.close();
      activePage = page;
    });
    await check("administrator-sees-user-knowledge-and-sessions", async () => {
      const staffContext = await newTestContext({
        viewport: { width: 1536, height: 1080 },
      });
      staffContext.on("page", observe);
      const staff = await staffContext.newPage();
      activePage = staff;
      await staff.goto(base, { waitUntil: "networkidle" });
      await staff
        .getByLabel("账号邮箱", { exact: true })
        .fill("portal-admin@example.com");
      await staff
        .getByLabel("登录密码", { exact: true })
        .fill("Browser-admin-pass-123");
      await staff.getByRole("button", { name: "登录", exact: true }).click();
      await staff.waitForURL(/\/(app|onboarding)$/);
      if (staff.url().endsWith("/onboarding")) {
        for (const title of ["连接 Notion", "选择 AI 模型", "准备就绪"]) {
          await staff
            .getByRole("button", { name: "稍后配置", exact: true })
            .click();
          await staff
            .getByRole("heading", { name: title, exact: true })
            .waitFor();
        }
        await staff
          .getByRole("button", { name: "进入学习空间", exact: true })
          .click();
        await staff.waitForURL("**/app");
      }
      const consoleLink = staff.getByRole("link", { name: "管理员后台", exact: true });
      assert.equal(await consoleLink.getAttribute("href"), process.env.PORTAL_TEST_ADMIN_URL || "http://127.0.0.1:3001");
      await staff.goto(base + "/app?view=admin");
      const original = await (
        await context.request.get(base + "/api/v1/workspace")
      ).json();
      await staff.getByLabel("搜索用户", { exact: true }).fill(email);
      const userSearch = staff.waitForResponse((response) => {
        const url = new URL(response.url());
        return (
          url.pathname === "/api/v1/admin/users" &&
          url.searchParams.get("q") === email
        );
      });
      await staff.getByRole("button", { name: "搜索", exact: true }).click();
      assert.equal((await userSearch).status(), 200);
      await staff
        .getByLabel("查看用户", { exact: true })
        .selectOption(original.user.id);
      await staff.getByText("知识单元", { exact: true }).waitFor();
      await staff
        .getByRole("heading", { name: "最近登录与在线状态", exact: true })
        .waitFor();
      const moreSessions = staff.getByRole("button", {
        name: "加载更早的登录记录",
        exact: true,
      });
      if (await moreSessions.count()) {
        const before = await staff
          .locator(".portal-admin-sessions .portal-list-row")
          .count();
        const nextSessions = staff.waitForResponse((response) => {
          const url = new URL(response.url());
          return (
            url.pathname === "/api/v1/admin/sessions" &&
            url.searchParams.has("cursor")
          );
        });
        await moreSessions.click();
        assert.equal((await nextSessions).status(), 200);
        await staff.waitForFunction(
          (count) =>
            document.querySelectorAll(".portal-admin-sessions .portal-list-row")
              .length > count,
          before,
        );
      }
      assert.ok((await staff.locator("body").boundingBox()).height < 2000);
      await staff.screenshot({
        path: path.join(output, "live-admin.png"),
        fullPage: true,
      });
      await staff.getByLabel("查看用户", { exact: true }).selectOption("");
      assert.equal(
        await staff.getByText("知识单元", { exact: true }).count(),
        0,
      );
      await staff
        .getByRole("button", { name: "添加用户", exact: true })
        .click();
      const createDialog = staff.getByRole("dialog", {
        name: "添加用户",
        exact: true,
      });
      const createdEmail = `created-${Date.now()}@example.com`;
      const createdPassword = "Created-user-pass-123";
      await createDialog
        .getByLabel("用户称呼", { exact: true })
        .fill("管理员添加的用户");
      await createDialog
        .getByLabel("用户邮箱", { exact: true })
        .fill(createdEmail);
      await createDialog
        .getByLabel("初始密码", { exact: true })
        .fill(createdPassword);
      await createDialog
        .getByLabel("确认初始密码", { exact: true })
        .fill("Mismatch-password-123");
      assert.equal(
        await createDialog.getByLabel("用户角色", { exact: true }).inputValue(),
        "user",
      );
      await createDialog
        .getByRole("button", { name: "创建用户", exact: true })
        .click();
      await createDialog
        .getByRole("alert")
        .filter({ hasText: "两次密码输入不一致" })
        .waitFor();
      await createDialog
        .getByLabel("确认初始密码", { exact: true })
        .fill(createdPassword);
      const createKeys = [];
      let createdId;
      await staff.route("**/api/v1/admin/users", async (route) => {
        if (route.request().method() !== "POST") return route.continue();
        createKeys.push(route.request().headers()["idempotency-key"]);
        const result = await route.fetch();
        assert.equal(result.status(), 201);
        const user = await result.json();
        if (createdId) assert.equal(user.id, createdId);
        createdId = user.id;
        if (createKeys.length === 1) return route.abort("failed");
        return route.fulfill({ response: result });
      });
      await createDialog
        .getByRole("button", { name: "创建用户", exact: true })
        .click();
      await createDialog.getByRole("alert").waitFor();
      await createDialog
        .getByRole("button", { name: "创建用户", exact: true })
        .click();
      await staff
        .getByRole("status")
        .filter({ hasText: "已创建用户 管理员添加的用户" })
        .waitFor();
      await createDialog.waitFor({ state: "hidden" });
      assert.equal(createKeys.length, 2);
      assert.ok(createKeys[0]);
      assert.equal(createKeys[0], createKeys[1]);
      assert.equal(
        await staff.getByLabel("查看用户", { exact: true }).inputValue(),
        createdId,
      );
      await staff.unroute("**/api/v1/admin/users");
      await staff
        .getByRole("button", { name: "添加用户", exact: true })
        .click();
      assert.equal(
        await createDialog.getByLabel("初始密码", { exact: true }).inputValue(),
        "",
      );
      assert.equal(
        await createDialog
          .getByLabel("确认初始密码", { exact: true })
          .inputValue(),
        "",
      );
      await createDialog
        .getByRole("button", { name: "取消", exact: true })
        .click();
      const createdContext = await newTestContext();
      createdContext.on("page", observe);
      const createdPage = await createdContext.newPage();
      activePage = createdPage;
      await createdPage.goto(base);
      await createdPage
        .getByLabel("账号邮箱", { exact: true })
        .fill(createdEmail);
      await createdPage
        .getByLabel("登录密码", { exact: true })
        .fill(createdPassword);
      await createdPage
        .getByRole("button", { name: "登录", exact: true })
        .click();
      await createdPage.waitForURL("**/onboarding");
      await createdPage
        .getByRole("heading", { name: "邮箱通知", exact: true })
        .waitFor();
      const denied = await createdContext.request.post(
        base + "/api/v1/admin/users",
        {
          headers: {
            "X-Memory-Client": "web",
            "Idempotency-Key": "unauthorized-create",
          },
          data: {
            email: `denied-${Date.now()}@example.com`,
            display_name: "denied",
            password: createdPassword,
            role: "admin",
          },
        },
      );
      assert.equal(denied.status(), 403);
      await createdContext.close();
      activePage = staff;
      console.log(
        "ADMIN_CREATE_USER_RETRY_PASSED created_login=onboarding non_admin_create=403 password_cleared=true",
      );
      await staffContext.close();
      activePage = page;
    });
    assert.deepEqual(errors, []);
    assert.deepEqual(externalRequests, []);
    console.log("PORTAL_CHECKS=10 PAGE_ERRORS=0 EXTERNAL_BROWSER_REQUESTS=0");
  } finally {
    await browser.close();
  }
}
main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
