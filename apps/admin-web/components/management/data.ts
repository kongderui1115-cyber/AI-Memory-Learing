import type { ManagementRecord, ManagementSection } from "@/lib/client";

export type RecordStatus = ManagementRecord["status"];

const record = (
  id: string,
  name: string,
  detail: string,
  status: RecordStatus,
  meta?: Record<string, string>,
): ManagementRecord => ({
  id, name, detail, status, meta, updatedAt: "2026-11-19T08:40:00+08:00",
});

export const managementFixtures: Record<ManagementSection, ManagementRecord[]> = {
  models: [
    record("deepseek", "DeepSeek", "deepseek-chat", "ok", { baseUrl: "https://api.deepseek.com", assigned: "知识提取", default: "true", credential: "true", provider: "DeepSeek" }),
    record("openai", "OpenAI", "gpt-4.1-mini", "ok", { baseUrl: "https://api.openai.com/v1", assigned: "复习题生成", credential: "true", provider: "OpenAI" }),
    record("claude", "Anthropic", "claude-sonnet", "paused", { baseUrl: "https://api.anthropic.com", assigned: "未分配", credential: "false", provider: "Anthropic" }),
    record("kimi", "Moonshot", "kimi-k2", "ok", { baseUrl: "https://api.moonshot.cn/v1", assigned: "答案评价", credential: "false", provider: "Moonshot" }),
    record("local", "OpenAI 兼容服务", "local-embedding", "paused", { baseUrl: "http://localhost:8080/v1", assigned: "未分配", credential: "false", provider: "兼容服务" }),
  ],
  sources: [
    record("notion", "Notion", "学习资料库 / 技术笔记", "ok", { success: "128", failed: "2", frequency: "30", automatic: "true", lastSync: "2026-11-19T08:40:00+08:00", history: "成功 128 条 · 失败 2 条", credential: "true" }),
    record("obsidian", "Obsidian", "Markdown 笔记库", "planned", { success: "0", failed: "0", automatic: "false" }),
    record("files", "本地文件", "Markdown 与纯文本", "planned"),
    record("pdf", "PDF", "讲义与技术文档", "planned"),
    record("web", "网页", "网页摘录与文章", "planned"),
    record("video", "视频", "字幕与时间码", "planned"),
    record("github", "GitHub", "项目文档与 README", "planned"),
    record("other", "其他来源", "来源适配器扩展", "planned"),
  ],
  notifications: [
    record("review-template", "复习通知模板", "知识点标题  {{title}}\n学科名称  {{subject}}\n复习次数  {{review_count}}\n记忆阶段  {{stage}}\n知识点正文  {{content}}\n知识点解析  {{explanation}}\n主动回忆问题  {{question}}\nNotion 原始链接  {{notion_url}}\n复习入口  {{review_url}}", "ok"),
    record("bark", "Bark", "移动端复习提醒", "ok", { delivery: "182 / 184", rate: "98.9%", credential: "true" }),
    record("qq", "QQ 邮箱", "学习摘要与到期提醒", "ok", { delivery: "415 / 420", rate: "98.8%", credential: "true" }),
    record("wechat", "企业微信", "群机器人", "paused", { delivery: "—", rate: "—" }),
    record("dingtalk", "钉钉", "群通知与任务提醒", "planned"),
    record("telegram", "Telegram", "Bot 消息", "planned"),
    record("other", "其他通知渠道", "Webhook 与渠道扩展", "planned"),
  ],
  memory: [
    record("global", "全局默认", "FSRS", "ok", { retention: "90", interval: "1,3,7,14,30", maxInterval: "365", default: "true", difficulty: "5" }),
    record("english", "英语学习", "FSRS", "ok", { retention: "92", interval: "1,3,7,14,30", maxInterval: "180", difficulty: "5" }),
    record("math", "数学", "艾宾浩斯", "ok", { retention: "90", interval: "1,2,4,7,15,30", maxInterval: "365", difficulty: "6" }),
    record("windows", "Windows 内核", "FSRS", "ok", { retention: "88", interval: "1,3,7,14,30", maxInterval: "270", difficulty: "7" }),
  ],
  jobs: [
    record("sync", "Notion 自动同步", "每 30 分钟", "ok", { success: "98.6%", failure: "1.4%", duration: "4.8 秒", cadence: "每 30 分钟" }),
    record("extract", "AI 知识提取", "按需触发", "running", { success: "96.4%", failure: "3.6%", duration: "12.6 秒", cadence: "按需触发" }),
    record("review", "复习任务生成", "每日 06:00", "ok", { success: "99.7%", failure: "0.3%", duration: "1.2 秒", cadence: "每日 06:00" }),
    record("delivery", "通知推送", "每日 08:00", "failed", { success: "98.8%", failure: "1.2%", duration: "1.9 秒", cadence: "每日 08:00", error: "演示：远端响应超时，等待重试。" }),
    record("statistics", "学习统计计算", "每小时", "ok", { success: "100%", failure: "0%", duration: "2.4 秒", cadence: "每小时" }),
    record("report", "自动报告生成", "每周一", "paused", { success: "—", failure: "—", duration: "—", cadence: "每周一" }),
  ],
  monitoring: [
    record("api", "API 服务", "HTTP 路由与请求", "ok"),
    record("db", "PostgreSQL", "主数据库连接", "ok"),
    record("redis", "Redis", "缓存与队列", "planned"),
    record("worker", "后台 Worker", "作业运行与恢复", "paused"),
  ],
  settings: [
    record("event01", "admin.overview.read", "系统概览", "ok", { actor: "演示管理员", severity: "info", outcome: "允许" }),
    record("event02", "auth.password.changed", "账户安全", "ok", { actor: "演示管理员", severity: "info", outcome: "完成" }),
    record("event03", "admin.access.denied", "管理资源", "failed", { actor: "演示用户", severity: "warning", outcome: "拒绝" }),
  ],
};

const days = ["11/13", "11/14", "11/15", "11/16", "11/17", "11/18", "11/19"];

export const modelCalls = days.map((date, i) => ({
  date,
  calls: [208, 247, 230, 311, 284, 362, 324][i],
  tokens: [82, 98, 91, 124, 110, 151, 132][i],
  cost: [2.6, 3.1, 2.8, 4.1, 3.6, 5.2, 4.5][i],
  error: [1.3, 1.8, 1.5, 1.2, 2.1, 1.4, 0.9][i],
}));

export const taskRuns = days.map((date, i) => ({
  date,
  sync: [26, 30, 29, 31, 26, 33, 32][i],
  extraction: [16, 18, 14, 20, 17, 23, 22][i],
  review: [11, 13, 12, 16, 14, 18, 17][i],
  delivery: [22, 25, 23, 27, 25, 30, 27][i],
}));

export const resources = days.map((date, i) => ({
  date,
  cpu: [34, 40, 28, 47, 36, 45, 32][i],
  memory: [56, 60, 59, 65, 62, 64, 61][i],
  disk: [68, 69, 70, 70, 71, 71, 72][i],
  latency: [82, 104, 91, 143, 119, 107, 96][i],
  requests: [928, 1091, 945, 1267, 1093, 1461, 1312][i],
  errors: [3, 7, 4, 9, 8, 6, 5][i],
}));

export const deliveryExamples = [
  { id: "delivery-1", name: "学习摘要", channel: "QQ 邮箱", time: "09:00", result: "ok" },
  { id: "delivery-2", name: "今日复习提醒", channel: "Bark", time: "08:00", result: "ok" },
  { id: "delivery-3", name: "今日复习提醒", channel: "QQ 邮箱", time: "08:00", result: "failed" },
] as const;

export function memoryExample(target: number, subject: string) {
  // Display-only illustrative series. Production predictions require simulator results.
  const observations: Record<string, readonly number[]> = {
    global: [96, 91, 83, 78, 75, 71],
    english: [97, 94, 87, 83, 77, 75],
    math: [95, 89, 82, 80, 79, 72],
    windows: [96, 90, 82, 74, 71, 66],
  };
  return [0, 1, 3, 7, 14, 30].map((day, i) => ({
    date: "第 " + day + " 天",
    predicted: Math.round(target + (100 - target) * Math.exp(-day / 3) - 3 * Math.log2(day + 1)),
    observed: (observations[subject] ?? observations.global)[i],
  }));
}

