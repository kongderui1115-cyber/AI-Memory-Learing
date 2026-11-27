import type {
  AdminSession,
  AdminUser,
  AiAnalytics,
  AuditEvent,
  DashboardData,
  DateRange,
  JobAnalytics,
  LearnerKnowledge,
  LearnerOverview,
  LearnerReview,
  LearningDay,
  Resource,
  RetentionPoint,
  SubjectMastery,
  SystemResources,
  User,
} from "./types";

const dayMs = 86_400_000;
const demoNow = () => new Date().toISOString();
const fixture = <T>(data: T): Resource<T> => ({ source: "demo", data });

export const demoAdmin: AdminUser = {
  id: "demo-admin",
  email: "admin@example.test",
  display_name: "演示管理员",
  role: "admin",
  timezone: "Asia/Shanghai",
  is_active: true,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
  version: 1,
};

export const demoUsers: User[] = [
  demoAdmin,
  { ...demoAdmin, id: "demo-learner", email: "learner@example.test", display_name: "演示学习者", role: "user" },
];

const demoKnowledge: LearnerKnowledge[] = [
  {
    id: "demo-knowledge-active-recall",
    title: "主动回忆与复习评分",
    body: "先不查看笔记，尝试用自己的语言回答问题。对照资料后，记录本次回忆的准确度和困难程度。",
    summary: "先作答，再核对来源，最后给本次回忆评分。",
    subject_id: "demo-learning",
    chapter_id: "demo-chapter-recall",
    source_url: null,
    status: "active",
    difficulty: 2,
    created_at: "2026-11-12T08:30:00+08:00",
    updated_at: "2026-11-17T08:30:00+08:00",
  },
  {
    id: "demo-knowledge-rate",
    title: "变化率与导数",
    body: "平均变化率在两个位置之间计算。让间隔逐渐缩小，可以用极限定义瞬时变化率。",
    summary: "导数可描述函数的瞬时变化率。",
    subject_id: "demo-math",
    chapter_id: "demo-chapter-derivatives",
    source_url: null,
    status: "active",
    difficulty: 3,
    created_at: "2026-11-11T18:45:00+08:00",
    updated_at: "2026-11-17T18:45:00+08:00",
  },
];

export function demoLearner(user: User): {
  overview: LearnerOverview;
  knowledge: LearnerKnowledge[];
  reviews: LearnerReview[];
} {
  const knowledge = user.role === "user" ? structuredClone(demoKnowledge) : [];
  const reviews = knowledge.map((row, index) => ({
    id: "demo-review-" + row.id,
    knowledge_title: row.title,
    knowledge_point_id: row.id,
    subject_id: row.subject_id,
    strategy: index === 0 ? "fsrs" : "ebbinghaus",
    rating: index === 0 ? "good" : "hard",
    duration_seconds: index === 0 ? 95 : 142,
    reviewed_at: new Date(Date.now() - (index * 1440 + 42) * 60_000).toISOString(),
  }));
  const localDate = new Intl.DateTimeFormat("sv-SE", { timeZone: user.timezone, dateStyle: "short" }).format(new Date());
  return {
    overview: {
      user: { ...user },
      local_date: localDate,
      knowledge_count: knowledge.length,
      chapter_count: new Set(knowledge.map((row) => row.chapter_id)).size,
      today_completed: reviews.filter((row) =>
        new Intl.DateTimeFormat("sv-SE", { timeZone: user.timezone, dateStyle: "short" }).format(new Date(row.reviewed_at)) === localDate).length,
      today_remaining: knowledge.length,
      overdue: knowledge.length ? 1 : 0,
    },
    knowledge,
    reviews,
  };
}

export function demoSessions(): AdminSession[] {
  return demoUsers.map((user, index) => ({
    id: `demo-session-${index}`,
    user_id: user.id,
    email: user.email,
    display_name: user.display_name,
    created_at: new Date(Date.now() - 3_600_000).toISOString(),
    last_seen_at: new Date(Date.now() - (index === 0 ? 60_000 : 2_400_000)).toISOString(),
    expires_at: new Date(Date.now() + dayMs).toISOString(),
    logged_out_at: index === 0 ? null : new Date(Date.now() - 2_400_000).toISOString(),
    ip_address: "192.0.2.10",
    user_agent: "演示浏览器",
    online: index === 0,
  }));
}

const demoActions = [
  ["来源同步完成", "Notion · 26 页完成，2 页等待重试", "notion_sync", "success", "info"],
  ["复习任务已生成", "定时任务 · 已生成 247 条", "review_generate", "success", "info"],
  ["AI 知识提取完成", "DeepSeek · 生成 16 个知识点", "chapter_extract", "success", "info"],
  ["学习提醒已发送", "QQ 邮箱 · 本批次 64 封", "review_notification", "success", "info"],
  ["来源同步等待重试", "Notion · 远端响应超时", "notion_retry", "retrying", "warning"],
  ["管理员登录", "控制台 · 已授权", "auth_login", "allowed", "info"],
] as const;

export function demoAudit(): AuditEvent[] {
  return demoActions.map(([, detail, action, outcome, severity], index) => ({
    id: `demo-event-${index}`,
    actor_label: index === 5 ? demoAdmin.display_name : "演示调度器",
    actor_id: index === 5 ? demoAdmin.id : null,
    target_user_id: null,
    request_id: null,
    action,
    resource: detail,
    outcome,
    severity,
    created_at: new Date(Date.now() - [3, 10, 18, 52, 77, 102][index] * 60_000).toISOString(),
    ip_address: "192.0.2.10",
  }));
}

const mastery: SubjectMastery[] = [
  { id: "windows", name: "Windows 内核", knowledge: 3026, completionRate: 91, mastery: 92, weak: 174 },
  { id: "languages", name: "语言学习", knowledge: 2674, completionRate: 87, mastery: 86, weak: 249 },
  { id: "ai", name: "AI 与机器学习", knowledge: 2431, completionRate: 89, mastery: 88, weak: 184 },
  { id: "math", name: "数学", knowledge: 1789, completionRate: 84, mastery: 83, weak: 199 },
  { id: "engineering", name: "软件工程", knowledge: 1520, completionRate: 81, mastery: 85, weak: 148 },
  { id: "humanities", name: "人文与历史", knowledge: 1046, completionRate: 80, mastery: 81, weak: 135 },
];

const periods = [0, 1, 3, 7, 14, 21, 30];
const retention: RetentionPoint[] = ["全部学科", ...mastery.map((item) => item.name)].flatMap((subject, index) =>
  periods.map((day, dayIndex) => ({
    stage: `D${day}`,
    subject,
    predicted: +(96 - 32 * (1 - Math.exp(-day / 10)) - (index % 4) * 1.4).toFixed(1),
    observed: +(93 - 30 * (1 - Math.exp(-day / 8)) - (index % 4) * 1.5 + [0, 1, -1, 2, 0, -1, -2][dayIndex]).toFixed(1),
    sampleSize: Math.max(9, Math.round((index === 0 ? 720 : 145 + index * 12) / (1 + day / 10))),
  })),
);

function dateSequence(range?: DateRange): string[] {
  const date = new Date();
  const utcToday = Date.UTC(date.getUTCFullYear(), date.getUTCMonth(), date.getUTCDate());
  const first = range ? Date.parse(range.from + "T00:00:00Z") : utcToday - 29 * dayMs;
  const last = range ? Date.parse(range.to + "T00:00:00Z") : utcToday;
  const days = Math.floor((last - first) / dayMs) + 1;
  if (!Number.isFinite(days) || days < 1 || days > 366) {
    throw new RangeError("请选择从早到晚且不超过 366 天的统计区间。");
  }
  return Array.from({ length: days }, (_, index) => new Date(first + index * dayMs).toISOString().slice(0, 10));
}

function jitter(date: string, salt: number, spread: number): number {
  const calendarDay = Math.floor(Date.parse(date) / dayMs);
  const noise = Math.sin(calendarDay * 0.87 + salt * 3.1) * 1e4;
  return Math.round((noise - Math.floor(noise)) * spread);
}

export function demoDashboard(range?: DateRange): DashboardData {
  const dates = dateSequence(range);
  const learning: LearningDay[] = dates.map((date) => ({
    date,
    knowledge: 38 + jitter(date, 2, 81),
    studyMinutes: 85 + jitter(date, 3, 163),
    reviews: 106 + jitter(date, 4, 181),
    completionRate: 71 + jitter(date, 5, 23),
  }));
  const ai: AiAnalytics = {
    days: dates.map((date) => ({
      date,
      calls: 150 + jitter(date, 6, 175),
      tokens: 84_000 + jitter(date, 7, 90_000),
      cost: (115 + jitter(date, 8, 250)) / 100,
      errors: 1 + jitter(date, 9, 7),
    })),
    models: [{ name: "DeepSeek", value: 51 }, { name: "OpenAI", value: 28 }, { name: "Moonshot", value: 15 }, { name: "其他", value: 6 }],
    tasks: [{ name: "知识提取", value: 46 }, { name: "出题", value: 26 }, { name: "答案评价", value: 19 }, { name: "学习报告", value: 9 }],
    currency: "CNY",
  };
  const resourceSeries = dates.map((date) => ({
    date,
    cpu: 18 + jitter(date, 10, 36),
    memory: 51 + jitter(date, 11, 17),
    disk: 64 + jitter(date, 12, 8),
    latencyMs: 82 + jitter(date, 13, 88),
    requests: 1650 + jitter(date, 14, 1550),
    errors: 3 + jitter(date, 15, 15),
  }));
  const resources: SystemResources = {
    ...resourceSeries[resourceSeries.length - 1],
    days: resourceSeries,
  };
  const jobs: JobAnalytics = {
    kinds: [
      { name: "Notion 同步", success: 310, failure: 4, averageMs: 4800 },
      { name: "AI 知识提取", success: 590, failure: 21, averageMs: 12600 },
      { name: "复习任务生成", success: 487, failure: 2, averageMs: 1200 },
      { name: "通知发送", success: 1308, failure: 16, averageMs: 1900 },
    ],
    days: dates.map((date) => ({
      date,
      success: 84 + jitter(date, 16, 103),
      failure: jitter(date, 17, 9),
      averageMs: 3400 + jitter(date, 18, 8200),
    })),
    chapterStatus: { completed: 487, pending: 24, running: 3, failed: 4 },
  };
  const activity = demoAudit().map((event, index) => ({
    id: event.id,
    time: event.created_at,
    label: demoActions[index][0],
    detail: event.resource,
    severity: event.severity,
  }));
  return {
    summary: fixture({
      knowledgePoints: mastery.reduce((sum, subject) => sum + subject.knowledge, 0),
      subjects: mastery.length,
      todayNew: 86,
      todayDue: 247,
      todayCompleted: 198,
      aiCalls: 3420,
      timezone: demoAdmin.timezone,
      asOf: demoNow(),
    }),
    learning: fixture(learning),
    retention: fixture(retention),
    subjects: fixture(mastery),
    ai: fixture(ai),
    resources: fixture(resources),
    jobs: fixture(jobs),
    activity: fixture(activity),
    health: fixture({ status: "ready", database: "ready", migration: "demo", checkedAt: demoNow() }),
  };
}