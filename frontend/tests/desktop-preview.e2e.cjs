const { chromium } = require("playwright");
const assert = require("node:assert/strict");
const path = require("node:path");
const fs = require("node:fs");

async function main() {
  const output =
    process.env.PREVIEW_SCREENSHOT_DIRECTORY ||
    path.join(process.cwd(), "test-results", "desktop-preview");
  fs.mkdirSync(output, { recursive: true });
  const browser = await chromium.launch({
    channel: process.env.PREVIEW_BROWSER_CHANNEL || "msedge",
    headless: true,
  });
  const context = await browser.newContext({
    viewport: { width: 1536, height: 1080 },
    deviceScaleFactor: 1,
  });
  const page = await context.newPage();
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  const base = process.env.PREVIEW_BASE_URL || "http://127.0.0.1:3030";
  const checks = [];
  async function check(name, action) {
    await action();
    checks.push(name);
    process.stdout.write(`PASS ${name}\n`);
  }
  try {
    await check("dashboard-render", async () => {
      const response = await page.goto(`${base}/preview`, {
        waitUntil: "networkidle",
      });
      assert.equal(response.status(), 200);
      await page.getByText("界面预览 · 示例数据", { exact: true }).waitFor();
      await page.screenshot({
        path: path.join(output, "desktop-dashboard.png"),
        fullPage: true,
      });
      assert.ok(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= window.innerWidth,
        ),
      );
    });
    await check("review-answer-and-persistence", async () => {
      await page.locator("button.ds-review-row").first().click();
      const dialog = page.locator("dialog[open]");
      await dialog.getByRole("button", { name: "查看知识点与解析" }).click();
      await dialog.getByText("解析与理解", { exact: true }).waitFor();
      await page.screenshot({
        path: path.join(output, "desktop-review.png"),
        fullPage: true,
      });
      await dialog.getByRole("button", { name: "记得", exact: true }).click();
      await page.waitForFunction(
        () =>
          JSON.parse(localStorage.getItem("memory-os-ui-preview-v1"))
            .completedReviews.length === 1,
      );
      await page.reload({ waitUntil: "networkidle" });
      await page.waitForFunction(
        () =>
          document.querySelector('.ds-navigation a[href="/preview/review"] b')
            ?.textContent === "6",
      );
    });
    await check("chapter-status-preview", async () => {
      await page.goto(`${base}/preview/learning`, { waitUntil: "networkidle" });
      await page.getByRole("button", { name: "进行中", exact: true }).click();
      assert.equal(await page.locator(".ds-chapter").count(), 1);
      await page
        .getByRole("button", { name: "查看第三章 · I/O 管理器与 IRP" })
        .click();
      await page
        .locator("dialog[open]")
        .getByRole("button", { name: "预览标记已完成" })
        .click();
      await page.locator(".ds-chapters .ds-empty").waitFor();
      await page.getByRole("button", { name: "已完成", exact: true }).click();
      assert.equal(await page.locator(".ds-chapter").count(), 3);
      await page.screenshot({
        path: path.join(output, "desktop-chapters.png"),
        fullPage: true,
      });
    });
    await check("add-subject-preview", async () => {
      await page.locator(".ds-sidebar-subjects>button").click();
      const dialog = page.locator("dialog[open]");
      await dialog.getByLabel("学科名称").fill("哲学");
      await dialog
        .getByRole("button", { name: "添加学科", exact: true })
        .click();
      await page
        .locator(".ds-sidebar-subjects a")
        .filter({ hasText: "哲学" })
        .waitFor();
    });
    await check("keyboard-search", async () => {
      await page.keyboard.press("Control+k");
      const dialog = page.locator("dialog[open]");
      await dialog.getByLabel("搜索示例内容").fill("导数");
      await dialog.locator(".ds-search-results>button").click();
      await dialog.getByRole("heading", { name: "导数与瞬时变化率" }).waitFor();
      await page.keyboard.press("Escape");
    });
    await check("assistant-composer", async () => {
      await page.goto(`${base}/preview/assistant`, {
        waitUntil: "networkidle",
      });
      await page.locator(".full input").pressSequentially("学习计划");
      assert.equal(await page.locator(".full input").inputValue(), "学习计划");
      await page.getByRole("button", { name: "发送问题" }).click();
      await page.locator(".ds-chat-bubble.assistant").waitFor();
      assert.match(
        await page.locator(".ds-chat-bubble.assistant").textContent(),
        /尚未接入/,
      );
    });
    await check("model-and-channel-settings", async () => {
      await page.goto(`${base}/preview/settings`, { waitUntil: "networkidle" });
      await page
        .locator(".ds-provider-card")
        .filter({ hasText: "Kimi" })
        .getByRole("button")
        .click();
      await page.getByRole("button", { name: "通知渠道", exact: true }).click();
      await page
        .locator(".ds-channel-card")
        .filter({ hasText: "钉钉" })
        .getByRole("button", { name: "配置" })
        .click();
      const dialog = page.locator("dialog[open]");
      await dialog.getByLabel("推送时间").selectOption("20:00");
      await dialog.getByRole("button", { name: "设为预览默认渠道" }).click();
      await page.waitForFunction(
        () =>
          JSON.parse(localStorage.getItem("memory-os-ui-preview-v1"))
            .channel === "钉钉",
      );
      await page.screenshot({
        path: path.join(output, "desktop-settings.png"),
        fullPage: true,
      });
    });
    await check("calendar-and-notification-detail", async () => {
      await page.goto(`${base}/preview/calendar`, { waitUntil: "networkidle" });
      await page.locator(".ds-calendar-day").filter({ hasText: /^14/ }).click();
      await page
        .getByRole("button", { name: "预览推送内容", exact: true })
        .click();
      await page
        .locator("dialog[open]")
        .getByText("Notion 原页面", { exact: true })
        .waitFor();
      assert.match(
        await page.locator("dialog[open]").textContent(),
        /钉钉 推送详情预览/,
      );
      await page.keyboard.press("Escape");
    });
    await check("all-preview-pages", async () => {
      for (const view of [
        "knowledge",
        "subjects",
        "notion",
        "statistics",
        "help",
        "review",
      ]) {
        const response = await page.goto(`${base}/preview/${view}`, {
          waitUntil: "networkidle",
        });
        assert.equal(response.status(), 200, view);
        assert.ok(
          await page.evaluate(
            () => document.documentElement.scrollWidth <= window.innerWidth,
          ),
          view,
        );
      }
    });
    await check("admin-role-preview", async () => {
      await page.locator(".ds-profile").click();
      await page
        .locator(".ds-sidebar-bottom")
        .getByRole("link", { name: "管理中心" })
        .click();
      await page
        .getByRole("navigation", { name: "管理员导航" })
        .getByRole("link", { name: "用户与会话", exact: true })
        .click();
      await page
        .getByText("角色切换仅作用于页面预览", { exact: true })
        .waitFor();
      assert.equal(
        await page
          .getByRole("table", { name: "用户复习概览", exact: true })
          .locator("tbody tr")
          .count(),
        3,
      );
    });
    await check("admin-user-review-details", async () => {
      await page
        .getByLabel("选择用户", { exact: true })
        .selectOption("sample-linyu");
      await page
        .getByRole("heading", { name: "林予 的学习空间", exact: true })
        .waitFor();
      const records = page.getByRole("table", {
        name: "林予 的复习记录",
        exact: true,
      });
      assert.equal(await records.locator("tbody tr").count(), 2);
      await page
        .getByLabel("筛选复习状态", { exact: true })
        .selectOption("已逾期");
      assert.equal(await records.locator("tbody tr").count(), 1);
      await records
        .getByRole("button", { name: "导数与瞬时变化率", exact: true })
        .click();
      await page
        .getByRole("region", { name: "知识点详情", exact: true })
        .getByText("林予 / 数学 / 第二章 / 导数与变化率", { exact: true })
        .waitFor();
    });
    await check("admin-user-knowledge-switch", async () => {
      await page.getByRole("tab", { name: "知识库", exact: true }).click();
      assert.equal(
        await page.locator(".ds-admin-knowledge-grid > button").count(),
        2,
      );
      await page
        .getByRole("button", {
          name: "查看知识点 现在完成时的语境",
          exact: true,
        })
        .click();
      await page
        .getByRole("region", { name: "知识点详情", exact: true })
        .getByText("解析与理解", { exact: true })
        .waitFor();
      await page
        .getByLabel("筛选当前用户学科", { exact: true })
        .selectOption("数学");
      assert.equal(
        await page.locator(".ds-admin-knowledge-grid > button").count(),
        1,
      );
      await page
        .getByLabel("搜索当前用户知识库", { exact: true })
        .fill("没有对应内容");
      await page
        .getByText("当前用户的知识库中没有符合条件的内容", { exact: true })
        .waitFor();
      await page
        .getByLabel("选择用户", { exact: true })
        .selectOption("sample-wenjing");
      assert.equal(
        await page
          .getByLabel("搜索当前用户知识库", { exact: true })
          .inputValue(),
        "",
      );
      assert.equal(
        await page
          .getByRole("region", { name: "知识点详情", exact: true })
          .count(),
        0,
      );
      assert.equal(
        await page.locator(".ds-admin-knowledge-grid > button").count(),
        2,
      );
      await page
        .getByRole("button", {
          name: "查看知识点 五十音与词汇例句",
          exact: true,
        })
        .click();
      const detail = page.getByRole("region", {
        name: "用户学习详情",
        exact: true,
      });
      assert.ok(!(await detail.textContent()).includes("现在完成时的语境"));
      await page.evaluate(() => window.scrollTo(0, 0));
      assert.equal((await page.locator(".ds-sidebar").boundingBox()).y, 0);
      await page.screenshot({
        path: path.join(output, "desktop-admin-knowledge.png"),
        fullPage: true,
      });
    });
    await check("admin-user-search-and-actions", async () => {
      const usersTable = page.getByRole("table", {
        name: "用户复习概览",
        exact: true,
      });
      await page.getByLabel("搜索用户", { exact: true }).fill("linyu@");
      assert.equal(await usersTable.locator("tbody tr").count(), 1);
      await usersTable
        .getByRole("button", { name: "查看复习", exact: true })
        .click();
      await page
        .getByRole("table", { name: "林予 的复习记录", exact: true })
        .waitFor();
      await page.getByLabel("搜索用户", { exact: true }).fill("不存在的用户");
      await page.getByText("没有找到符合条件的用户", { exact: true }).waitFor();
      await page.getByLabel("搜索用户", { exact: true }).fill("");
      await page
        .getByLabel("选择用户", { exact: true })
        .selectOption("sample-zirui");
      await page.evaluate(() => window.scrollTo(0, 0));
      assert.equal((await page.locator(".ds-sidebar").boundingBox()).y, 0);
      await page.screenshot({
        path: path.join(output, "desktop-admin.png"),
        fullPage: true,
      });
    });
    await check("admin-desktop-1280-layout", async () => {
      await page.setViewportSize({ width: 1280, height: 1000 });
      assert.ok(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= window.innerWidth,
        ),
      );
      const usersTable = page.getByRole("table", {
        name: "用户复习概览",
        exact: true,
      });
      assert.ok(
        await usersTable.evaluate(
          (table) => table.scrollWidth <= table.parentElement.clientWidth,
        ),
      );
    });
    await check("desktop-1280-layout", async () => {
      await page.setViewportSize({ width: 1280, height: 1000 });
      await page.goto(`${base}/preview`, { waitUntil: "networkidle" });
      assert.ok(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= window.innerWidth,
        ),
      );
      await page.screenshot({
        path: path.join(output, "desktop-1280.png"),
        fullPage: true,
      });
    });
    await check("desktop-1920-layout", async () => {
      await page.setViewportSize({ width: 1920, height: 1080 });
      await page.goto(`${base}/preview`, { waitUntil: "networkidle" });
      assert.ok(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= window.innerWidth,
        ),
      );
    });
    await check("mobile-push-reading", async () => {
      await page.setViewportSize({ width: 390, height: 844 });
      await page.goto(`${base}/preview/push`, { waitUntil: "networkidle" });
      await page
        .getByRole("heading", { name: "知识点", exact: true })
        .waitFor();
      await page
        .getByRole("heading", { name: "解析与理解", exact: true })
        .waitFor();
      await page.getByRole("button", { name: "Notion 原页面" }).click();
      assert.match(await page.getByRole("status").textContent(), /示例来源/);
      await page.getByRole("button", { name: "记得", exact: true }).click();
      await page
        .getByRole("button", { name: "记得", exact: true, pressed: true })
        .waitFor();
      assert.ok(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= window.innerWidth,
        ),
      );
      await page.screenshot({
        path: path.join(output, "mobile-push.png"),
        fullPage: true,
      });
    });
    await check("login-interface", async () => {
      await page.setViewportSize({ width: 1536, height: 1080 });
      await page.goto(`${base}/dashboard`, { waitUntil: "networkidle" });
      await page
        .getByLabel("邮箱地址", { exact: true })
        .fill("preview@example.test");
      const password = page.getByLabel("密码", { exact: true });
      await password.fill("preview-123456");
      assert.equal(await password.getAttribute("type"), "password");
      await page.getByRole("button", { name: "显示密码", exact: true }).click();
      assert.equal(await password.getAttribute("type"), "text");
      await page.getByRole("button", { name: "隐藏密码", exact: true }).click();
      assert.equal(await password.getAttribute("type"), "password");
      assert.ok(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= window.innerWidth,
        ),
      );
      await page.screenshot({
        path: path.join(output, "desktop-login.png"),
        fullPage: true,
      });
    });
    await check("root-welcome-entry", async () => {
      await page.goto(base, { waitUntil: "networkidle" });
      await page
        .getByRole("heading", { name: "欢迎回来", exact: true })
        .waitFor();
      assert.equal(new URL(page.url()).pathname, "/");
    });
    assert.deepEqual(errors, [], "Browser runtime errors");
    process.stdout.write(
      `SUMMARY passed=${checks.length} runtime_errors=${errors.length}\n`,
    );
  } finally {
    await browser.close();
  }
}

main().catch((error) => {
  process.stderr.write(`${error.stack}\n`);
  process.exitCode = 1;
});
