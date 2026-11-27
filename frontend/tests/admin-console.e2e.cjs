const { chromium } = require("playwright");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const base = process.env.PREVIEW_BASE_URL || "http://127.0.0.1:3030";
const output =
  process.env.PREVIEW_SCREENSHOT_DIRECTORY ||
  path.join(process.cwd(), "test-results", "admin-console");
const storageKey = "memory-os-admin-demo-v1";
const sections = [
  "",
  "/models",
  "/sources",
  "/notifications",
  "/memory",
  "/users",
  "/security",
];

async function main() {
  fs.mkdirSync(output, { recursive: true });
  const browser = await chromium.launch({
    channel: process.env.PREVIEW_BROWSER_CHANNEL || "msedge",
    headless: true,
  });
  const context = await browser.newContext({
    viewport: { width: 1536, height: 1080 },
  });
  await context.addInitScript(() => {
    Object.defineProperty(window.crypto, "randomUUID", {
      value: undefined,
      configurable: true,
    });
  });
  const page = await context.newPage();
  const errors = [];
  const networkCalls = [];
  page.on("pageerror", (error) =>
    errors.push(`${page.url()} ${error.message}`),
  );
  page.on("request", (request) => {
    if (
      new URL(request.url()).origin !== new URL(base).origin ||
      request.url().includes("/api/v1/")
    )
      networkCalls.push(request.url());
  });
  let passed = 0;
  async function check(name, action) {
    await action();
    passed++;
    process.stdout.write(`PASS ${name}\n`);
  }
  async function goto(section) {
    const response = await page.goto(`${base}/preview/admin${section}`, {
      waitUntil: "networkidle",
    });
    assert.equal(response.status(), 200);
    await page.getByRole("navigation", { name: "管理员导航" }).waitFor();
  }
  async function snapshot(name) {
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.screenshot({ path: path.join(output, name), fullPage: true });
  }
  try {
    await check("vm-http-preview-identifier-support", async () => {
      await page.goto(`${base}/preview`, { waitUntil: "networkidle" });
      assert.equal(
        await page.evaluate(() => typeof crypto.randomUUID),
        "undefined",
      );
      await page.locator(".ds-sidebar-subjects>button").click();
      const dialog = page.locator("dialog[open]");
      await dialog
        .getByLabel("学科名称", { exact: true })
        .fill("虚拟机示例学科");
      await dialog
        .getByRole("button", { name: "添加学科", exact: true })
        .click();
      await page
        .locator(".ds-sidebar-subjects a")
        .filter({ hasText: "虚拟机示例学科" })
        .waitFor();
    });
    await check("seven-admin-pages", async () => {
      for (const section of sections) {
        await goto(section);
        assert.equal(await page.locator(".ds-admin-console-nav a").count(), 7);
        assert.ok(
          await page.evaluate(
            () => document.documentElement.scrollWidth <= innerWidth,
          ),
          section,
        );
      }
      await goto("");
      await page.getByText("系统运行正常 · 示例", { exact: true }).waitFor();
      await snapshot("admin-console-dashboard.png");
    });
    await check("model-add-edit-default-toggle-delete", async () => {
      await goto("/models");
      await page
        .getByRole("button", { name: "添加模型供应商", exact: true })
        .click();
      let dialog = page.locator("dialog[open]");
      await dialog
        .getByLabel("模型配置名称", { exact: true })
        .fill("测试兼容模型");
      await dialog.getByLabel("模型名称", { exact: true }).fill("demo-model");
      await dialog
        .getByLabel("模型 Base URL", { exact: true })
        .fill("https://model.example.test/v1");
      const secret = dialog.getByLabel("模型 API Key", { exact: true });
      assert.equal(await secret.getAttribute("type"), "password");
      await secret.fill("demo-only-secret-42");
      await dialog
        .getByRole("button", { name: "保存演示配置", exact: true })
        .click();
      let card = page
        .locator(".ac-model-card")
        .filter({ hasText: "测试兼容模型" });
      await card.getByRole("button", { name: "设为默认", exact: true }).click();
      await card.getByText("默认模型", { exact: true }).waitFor();
      await card.getByRole("button", { name: "编辑", exact: true }).click();
      dialog = page.locator("dialog[open]");
      assert.equal(
        await dialog.getByLabel("模型 API Key", { exact: true }).inputValue(),
        "",
      );
      await dialog
        .getByLabel("模型配置名称", { exact: true })
        .fill("测试兼容模型修订");
      await dialog
        .getByRole("button", { name: "保存演示配置", exact: true })
        .click();
      await page.waitForFunction(
        (key) => localStorage.getItem(key)?.includes("测试兼容模型修订"),
        storageKey,
      );
      assert.ok(
        !(
          await page.evaluate((key) => localStorage.getItem(key), storageKey)
        ).includes("demo-only-secret-42"),
      );
      await page.reload({ waitUntil: "networkidle" });
      card = page
        .locator(".ac-model-card")
        .filter({ hasText: "测试兼容模型修订" });
      await card.getByText("默认模型", { exact: true }).waitFor();
      await card.getByRole("switch").click();
      await card
        .getByRole("button", { name: "删除 测试兼容模型修订", exact: true })
        .click();
      await page
        .locator("dialog[open]")
        .getByRole("button", { name: "确认移除", exact: true })
        .click();
      assert.equal(await page.locator(".ac-model-card").count(), 5);
    });
    await check("honest-model-connection-demo", async () => {
      const card = page
        .locator(".ac-model-card")
        .filter({ hasText: "DeepSeek 主模型" });
      await card.getByRole("button", { name: "连接测试", exact: true }).click();
      await card
        .getByText("前端演示完成 · 真实连接尚待后端验证", { exact: true })
        .waitFor();
      await snapshot("admin-console-models.png");
    });
    await check("notion-config-frequency-and-sync-demo", async () => {
      await goto("/sources");
      await page
        .getByLabel("Windows 内核笔记库同步频率", { exact: true })
        .selectOption("60");
      await page
        .getByRole("switch", {
          name: "Windows 内核笔记库自动同步",
          exact: true,
        })
        .click();
      await page
        .getByRole("button", { name: "API 授权配置", exact: true })
        .click();
      const input = page
        .locator("dialog[open]")
        .getByLabel("Notion Integration Token", { exact: true });
      assert.equal(await input.getAttribute("type"), "password");
      await input.fill("demo-notion-secret-42");
      await page
        .locator("dialog[open]")
        .getByRole("button", { name: "保存授权演示", exact: true })
        .click();
      await page
        .getByRole("button", { name: "手动同步演示", exact: true })
        .first()
        .click();
      await page
        .getByRole("table", { name: "同步历史", exact: true })
        .getByText("演示完成 · 未读取 Notion", { exact: true })
        .waitFor();
      assert.ok(
        !(
          await page.evaluate((key) => localStorage.getItem(key), storageKey)
        ).includes("demo-notion-secret-42"),
      );
      await snapshot("admin-console-sources.png");
    });
    await check("channel-config-and-template-demo", async () => {
      await goto("/notifications");
      const email = page
        .locator(".ac-channel-card")
        .filter({ hasText: "邮件" });
      await email.getByRole("switch").click();
      await email.getByRole("button", { name: "配置", exact: true }).click();
      const dialog = page.locator("dialog[open]");
      await dialog
        .getByLabel("通知接收身份", { exact: true })
        .fill("demo@example.test");
      const secret = dialog.getByLabel("通知渠道密钥", { exact: true });
      assert.equal(await secret.getAttribute("type"), "password");
      await secret.fill("demo-channel-secret-42");
      await dialog
        .getByRole("button", { name: "保存渠道演示", exact: true })
        .click();
      await email
        .getByRole("button", { name: "测试发送", exact: true })
        .click();
      await page
        .getByRole("table", { name: "消息发送历史", exact: true })
        .getByText("前端演示完成 · 未投递", { exact: true })
        .waitFor();
      const template = page.getByLabel("模板内容", { exact: true });
      const original = await template.inputValue();
      await template.fill("{{unknown_variable}}");
      await page
        .getByRole("button", { name: "保存模板演示", exact: true })
        .click();
      await page.locator(".ac-form-error[role=alert]").waitFor();
      await template.fill("{{constructor}}");
      await page
        .getByRole("button", { name: "保存模板演示", exact: true })
        .click();
      await page
        .getByText("请检查未知变量 constructor", { exact: true })
        .waitFor();
      await template.fill(original);
      await page
        .getByRole("button", { name: "保存模板演示", exact: true })
        .click();
      assert.ok(
        !(await page.locator(".ac-message-preview pre").textContent()).includes(
          "{{",
        ),
      );
      assert.ok(
        !(
          await page.evaluate((key) => localStorage.getItem(key), storageKey)
        ).includes("demo-channel-secret-42"),
      );
      await page
        .getByLabel("筛选消息渠道", { exact: true })
        .selectOption("Telegram");
      await page.getByText("当前渠道暂无发送记录", { exact: true }).waitFor();
      await page
        .getByLabel("筛选消息渠道", { exact: true })
        .selectOption("邮件");
      assert.equal(
        await page
          .getByRole("table", { name: "消息发送历史", exact: true })
          .locator("tbody tr")
          .count(),
        1,
      );
      await page
        .getByLabel("筛选消息渠道", { exact: true })
        .selectOption("all");
      await snapshot("admin-console-notifications.png");
    });
    await check("memory-configuration-validation-and-persistence", async () => {
      await goto("/memory");
      const intervals = page.getByLabel("艾宾浩斯复习间隔", { exact: true });
      await intervals.fill("3, 2, 1");
      await page
        .getByRole("button", { name: "保存固定间隔", exact: true })
        .click();
      await page.locator(".ac-form-error[role=alert]").waitFor();
      await intervals.fill("1, 3, 7");
      await page
        .getByRole("button", { name: "保存固定间隔", exact: true })
        .click();
      assert.equal(
        await page.locator(".ac-interval-timeline > span").count(),
        3,
      );
      await page.getByLabel("FSRS目标保持率", { exact: true }).fill("93");
      await page.getByLabel("FSRS最大间隔", { exact: true }).fill("180");
      await page
        .getByRole("button", { name: "保存 FSRS 参数", exact: true })
        .click();
      await page.waitForFunction(
        (key) => JSON.parse(localStorage.getItem(key)).retention === 93,
        storageKey,
      );
      await page.reload({ waitUntil: "networkidle" });
      assert.equal(
        await page.getByLabel("FSRS目标保持率", { exact: true }).inputValue(),
        "93",
      );
      assert.equal(
        await page.getByLabel("艾宾浩斯复习间隔", { exact: true }).inputValue(),
        "1, 3, 7",
      );
      await snapshot("admin-console-memory.png");
    });
    await check("login-time-range-online-and-empty-states", async () => {
      await goto("/users");
      const rows = page
        .getByRole("table", { name: "用户登录会话", exact: true })
        .locator("tbody tr");
      assert.equal(await rows.count(), 5);
      await page
        .getByLabel("筛选在线状态", { exact: true })
        .selectOption("online");
      assert.equal(await rows.count(), 2);
      await page
        .getByLabel("筛选登录用户", { exact: true })
        .selectOption("sample-linyu");
      assert.equal(await rows.count(), 1);
      await page.getByRole("button", { name: "清空筛选", exact: true }).click();
      await page
        .getByLabel("登录起始时间", { exact: true })
        .fill("2026-11-13T00:00");
      await page
        .getByLabel("登录结束时间", { exact: true })
        .fill("2026-11-13T23:59");
      assert.equal(await rows.count(), 3);
      await page
        .getByLabel("登录起始时间", { exact: true })
        .fill("2026-11-14T00:00");
      await page.locator(".ac-form-error[role=alert]").waitFor();
      assert.equal(await rows.count(), 0);
      await page.getByRole("button", { name: "清空筛选", exact: true }).click();
      await snapshot("admin-console-users.png");
    });
    await check("security-event-filters-and-detail", async () => {
      await goto("/security");
      const rows = page
        .getByRole("table", { name: "安全事件日志", exact: true })
        .locator("tbody tr");
      assert.equal(await rows.count(), 6);
      await page
        .getByLabel("筛选安全级别", { exact: true })
        .selectOption("高风险");
      assert.equal(await rows.count(), 1);
      await rows
        .getByRole("button", { name: "查看日志 event-4", exact: true })
        .click();
      await page
        .locator("dialog[open]")
        .getByText("账号登录", { exact: true })
        .waitFor();
      await page.keyboard.press("Escape");
      await page.getByLabel("搜索安全日志", { exact: true }).fill("没有此记录");
      assert.equal(await rows.count(), 0);
      await page.getByLabel("搜索安全日志", { exact: true }).fill("");
      await page
        .getByLabel("筛选安全级别", { exact: true })
        .selectOption("all");
      await snapshot("admin-console-security.png");
    });
    await check("all-admin-pages-1280-layout", async () => {
      await page.setViewportSize({ width: 1280, height: 1000 });
      for (const section of sections) {
        await goto(section);
        assert.ok(
          await page.evaluate(
            () => document.documentElement.scrollWidth <= innerWidth,
          ),
          section,
        );
      }
    });
    await check("unknown-admin-route", async () => {
      const response = await page.goto(`${base}/preview/admin/constructor`, {
        waitUntil: "networkidle",
      });
      assert.equal(response.status(), 404);
    });
    assert.deepEqual(errors, [], "Browser runtime errors");
    assert.deepEqual(networkCalls, [], "Demo must use local UI data");
    process.stdout.write(
      `SUMMARY passed=${passed} runtime_errors=${errors.length} external_or_api_requests=${networkCalls.length}\n`,
    );
  } finally {
    await browser.close();
  }
}
main().catch((error) => {
  process.stderr.write(`${error.stack}\n`);
  process.exitCode = 1;
});
