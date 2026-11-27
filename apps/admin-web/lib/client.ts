import { managementFixtures } from "../components/management/data";
import { demoAdmin, demoAudit, demoDashboard, demoLearner, demoSessions, demoUsers } from "./mock";
import type { AdminOperations } from "./operations";
import type {
  ActivityEvent,
  AdminClient,
  AdminMode,
  AdminSession,
  AdminUser,
  AuditEvent,
  AuditFilters,
  DashboardData,
  DateRange,
  JobAnalytics,
  ManagementRecord,
  ManagementSection,
  Page,
  PasswordInput,
  Resource,
  SystemHealth,
  User,
} from "./types";

export type * from "./types";

export class AdminApiError extends Error {
  constructor(message: string, readonly status: number, readonly code?: string) {
    super(message);
    this.name = "AdminApiError";
  }
}

const gateway = "/api/admin-gateway";
type Query = Record<string, string | number | boolean | undefined>;

type BackendOverview = {
  counts: {
    knowledge_points: number;
    subjects: number;
    today_knowledge_created: number;
    today_reviews_completed: number;
  };
  as_of: string;
  timezone: string;
  chapter_jobs: Record<string, number>;
};

type BackendJobCounts = {
  success: number;
  failure: number;
  partial: number;
  average_ms: number | null;
  duration_samples: number;
};

type BackendAnalytics = {
  as_of: string;
  timezone: string;
  from_date: string;
  to_date: string;
  today_due: number;
  today_ai_calls: number;
  ai_usage?: {
    days: { date: string; calls: number; terminal_calls: number; errors: number; tokens: number | null; token_samples: number }[];
    models: { name: string; value: number }[];
    tasks: { name: string; value: number }[];
  };
  workflow?: DashboardData["workflow"];
  learning: {
    date: string; knowledge: number; study_seconds: number; reviews: number;
    assigned: number; completed: number; completion_rate: number | null;
  }[];
  subjects: {
    id: string; name: string; knowledge: number; reviews: number;
    completion_rate: number | null; recall_rate: number | null; weak: number | null;
  }[];
  retention: {
    stage: string; subject_id: string | null; subject_name: string; predicted: number | null;
    observed: number | null; observed_samples: number; predicted_samples: number; prediction_versions: string[];
  }[];
  jobs: {
    kinds: (BackendJobCounts & { key: string; name: string })[];
    days: (BackendJobCounts & { date: string })[];
  };
};

type Readiness = {
  status: "ready" | "unavailable";
  checks: { database?: { status: string; migration?: string | null } };
};

const activityLabels: Record<string, string> = {
  admin_overview_read: "查看系统总览",
  admin_analytics_read: "读取运营统计",
  admin_users_read: "查看用户列表",
  admin_user_read: "查看学习数据",
  admin_sessions_read: "查看登录会话",
  audit_read: "查看审计日志",
  login_success: "用户登录",
  logout: "用户退出",
  password_changed: "修改账户密码",
  user_created: "创建用户",
  user_updated: "更新用户",
};

const connected = <T>(data: T): Resource<T> => ({ source: "live", data });
const demo = <T>(data: T): Resource<T> => ({ source: "demo", data });
const unavailable = <T>(message: string): Resource<T> => ({ source: "unavailable", data: null, message });

function asRecord(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null;
}

function normalizeTime(value: string | undefined, last: boolean): string | undefined {
  if (!value || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return value;
  return `${value}T${last ? "23:59:59.999" : "00:00:00.000"}Z`;
}

function normalizeFilters<Q extends { from?: string; to?: string }>(filters: Q): Q {
  return { ...filters, from: normalizeTime(filters.from, false), to: normalizeTime(filters.to, true) };
}

function queryString(query?: Query): string {
  const result = new URLSearchParams();
  for (const [key, value] of Object.entries(query ?? {})) {
    if (value !== undefined && value !== "") result.set(key, String(value));
  }
  const encoded = result.toString();
  return encoded ? `?${encoded}` : "";
}

function requestError(response: Response, payload: unknown): AdminApiError {
  const body = asRecord(payload);
  const problem = asRecord(body?.error) ?? body;
  const message = typeof problem?.message === "string" && problem.message
    ? problem.message
    : ({
        401: "登录状态已失效，请重新登录。",
        403: "当前账号没有管理员权限。",
        404: "此后端接口尚未开放。",
        429: "请求过于频繁，请稍后再试。",
      } as Record<number, string>)[response.status] ?? "管理服务暂时无法处理此请求，请稍后再试。";
  return new AdminApiError(message, response.status, typeof problem?.code === "string" ? problem.code : undefined);
}

function isReadiness(value: unknown): value is Readiness {
  const item = asRecord(value);
  return (item?.status === "ready" || item?.status === "unavailable") && asRecord(item.checks) !== null;
}

async function request<T>(
  action: string,
  options: { method?: "POST" | "PATCH"; body?: unknown; query?: Query; acceptUnready?: boolean; idempotencyKey?: string; version?: number } = {},
): Promise<T> {
  const headers = new Headers({ Accept: "application/json" });
  if (options.method) {
    headers.set("Content-Type", "application/json");
    headers.set("X-Admin-Client", "console");
  }
  if (options.idempotencyKey) headers.set("Idempotency-Key", options.idempotencyKey);
  if (options.version !== undefined) headers.set("If-Match", `"${options.version}"`);
  let response: Response;
  try {
    response = await fetch(`${gateway}/${action}${queryString(options.query)}`, {
      method: options.method ?? "GET",
      headers,
      body: options.method ? JSON.stringify(options.body ?? {}) : undefined,
      cache: "no-store",
      credentials: "same-origin",
    });
  } catch {
    throw new AdminApiError("无法连接管理服务。请检查服务是否已启动。", 0, "NETWORK_ERROR");
  }
  if (response.status === 204) return undefined as T;
  const payload: unknown = await response.json().catch(() => null);
  if (!response.ok && !(options.acceptUnready && response.status === 503 && isReadiness(payload))) {
    throw requestError(response, payload);
  }
  if (payload === null) throw new AdminApiError("管理服务返回了无效数据。", 502, "INVALID_RESPONSE");
  return payload as T;
}

function adminProfile(user: User): AdminUser {
  if (!asRecord(user) || typeof user.id !== "string" || typeof user.email !== "string") {
    throw new AdminApiError("管理服务返回了无效的管理员资料。", 502, "INVALID_RESPONSE");
  }
  if (user.role !== "admin" || user.is_active !== true) {
    throw new AdminApiError("当前账号没有管理员权限。", 403, "ADMIN_REQUIRED");
  }
  return { ...user, role: "admin" };
}

async function readResource<T>(callback: () => Promise<T>): Promise<Resource<T>> {
  try {
    return connected(await callback());
  } catch (error) {
    if (!(error instanceof AdminApiError) || error.status === 401 || error.status === 403) throw error;
    return unavailable(error.message);
  }
}

async function readHealth(): Promise<Resource<SystemHealth>> {
  return readResource(async () => {
    const result = await request<unknown>("health", { acceptUnready: true });
    if (!isReadiness(result)) throw new AdminApiError("健康接口缺少数据库就绪信息。", 502, "INVALID_RESPONSE");
    const database = result.checks.database;
    return {
      status: result.status,
      database: database?.status === "ok" ? "ready" : "unavailable",
      migration: typeof database?.migration === "string" ? database.migration : null,
      checkedAt: new Date().toISOString(),
    };
  });
}

async function readPage<T>(action: string, query?: Query): Promise<Resource<Page<T>>> {
  return readResource(async () => {
    const payload = await request<Page<T>>(action, { query });
    if (!asRecord(payload) || !Array.isArray(payload.items) || typeof payload.has_more !== "boolean") {
      throw new AdminApiError("管理服务返回了无效的分页记录。", 502, "INVALID_RESPONSE");
    }
    return payload;
  });
}

async function readAudit(filters: AuditFilters = {}): Promise<Resource<Page<AuditEvent>>> {
  return readPage("audit", normalizeFilters(filters));
}

function asActivity(event: AuditEvent): ActivityEvent {
  return {
    id: event.id,
    time: event.created_at,
    label: activityLabels[event.action] ?? event.action,
    detail: [event.actor_label, event.resource, event.outcome].filter(Boolean).join(" · "),
    severity: event.severity,
  };
}

function readOverview(): Promise<Resource<BackendOverview>> {
  return readResource(async () => {
    const overview = await request<BackendOverview>("overview");
    if (!asRecord(overview) || !asRecord(overview.counts) || !asRecord(overview.chapter_jobs)
      || typeof overview.timezone !== "string" || typeof overview.as_of !== "string") {
      throw new AdminApiError("管理服务返回了无效的总览记录。", 502, "INVALID_RESPONSE");
    }
    return overview;
  });
}

function readAnalytics(range?: DateRange) {
  return readResource(() => request<BackendAnalytics>("analytics", {
    query: range ? { from_date: range.from, to_date: range.to } : undefined,
  }));
}

function jobCounts(row: BackendJobCounts) {
  return {
    success: row.success, failure: row.failure, partial: row.partial,
    averageMs: row.average_ms, durationSamples: row.duration_samples,
  };
}

function mapJobs(jobs: BackendAnalytics["jobs"]): JobAnalytics {
  return {
    kinds: jobs.kinds.map(row => ({ key: row.key, name: row.name, ...jobCounts(row) })),
    days: jobs.days.map(row => ({ date: row.date, ...jobCounts(row) })),
  };
}

function percentValue(ratio: number | null) {
  return ratio === null ? null : ratio * 100;
}

function mapAiUsage(usage: BackendAnalytics["ai_usage"] | undefined): DashboardData["ai"] {
  return usage ? connected({
    days: usage.days.map(row => ({
      date: row.date, calls: row.calls, errors: row.errors, tokens: row.tokens, cost: null,
      terminalCalls: row.terminal_calls, tokenSamples: row.token_samples,
    })),
    models: usage.models, tasks: usage.tasks, currency: "",
  }) : unavailable("全站模型用量暂未获取。");
}

const operations: AdminOperations = {
  providers: (query) => request("model-providers", { query }),
  providerReadiness: (resource_id) => request("model-readiness", { query: { resource_id } }),
  updateProvider: (resource_id, version, body) => request("model-providers", { method: "PATCH", query: { resource_id }, version, body }),
  aiUsage: async () => mapAiUsage((await readAnalytics()).data?.ai_usage),
  policies: (query) => request("memory-policies", { query }),
  updatePolicy: (resource_id, version, body) => request("memory-policies", { method: "PATCH", query: { resource_id }, version, body }),
  simulate: (body) => request("memory-simulations", { method: "POST", body }),
  sources: (query) => request("sources", { query }),
  sourceRuns: (resource_id, filters) => request("source-runs", { query: { resource_id, ...filters } }),
  queueSource: (resource_id, idempotencyKey) => request("source-sync", { method: "POST", query: { resource_id }, idempotencyKey }),
  channels: (query) => request("notification-channels", { query }),
  deliveries: (query) => request("notification-deliveries", { query }),
  jobs: (query) => request("jobs", { query }),
  telemetry: (minutes = 60) => request("telemetry", { query: { minutes } }),
  systemInfo: () => request("system-info"),
  backups: () => request("backups"),
  createBackup: (idempotencyKey) => request("backups", { method: "POST", idempotencyKey }),
};

function readResources(): Promise<DashboardData["resources"]> {
  return readResource(async () => {
    const telemetry = await operations.telemetry();
    return {
      cpu: telemetry.cpu, memory: telemetry.memory, disk: telemetry.disk, latencyMs: telemetry.latency_ms,
      requests: telemetry.requests, errors: telemetry.errors, windowMinutes: telemetry.window_minutes,
      days: telemetry.buckets.map(row => ({
        date: row.date, requests: row.requests, errors: row.errors, latencyMs: row.latency_ms,
        cpu: null, memory: null, disk: null,
      })),
    };
  });
}

async function realDashboard(range?: DateRange): Promise<DashboardData> {
  const [overview, analytics, audit, health, resources] = await Promise.all([
    readOverview(),
    readAnalytics(range),
    readAudit({ limit: 8 }),
    readHealth(),
    readResources(),
  ]);
  const current = overview.data;
  const values = analytics.data;
  const missing = unavailable<never>(analytics.message ?? "运营统计暂不可用。");
  return {
    window: values ? { from: values.from_date, to: values.to_date, timezone: values.timezone } : undefined,
    summary: current
      ? connected({
          asOf: values?.as_of ?? current.as_of,
          timezone: values?.timezone ?? current.timezone,
          knowledgePoints: current.counts.knowledge_points,
          subjects: current.counts.subjects,
          todayNew: current.counts.today_knowledge_created,
          todayDue: values?.today_due ?? null,
          todayCompleted: current.counts.today_reviews_completed,
          aiCalls: values?.today_ai_calls ?? null,
        })
      : unavailable(overview.message ?? "当前无法读取系统总览。"),
    learning: values ? connected(values.learning.map(row => ({
      date: row.date, knowledge: row.knowledge, studyMinutes: row.study_seconds / 60,
      reviews: row.reviews, assigned: row.assigned, completed: row.completed,
      completionRate: percentValue(row.completion_rate),
    }))) : missing,
    retention: values ? connected(values.retention.map(row => ({
      stage: row.stage, subject: row.subject_name, subjectId: row.subject_id,
      predicted: percentValue(row.predicted), observed: percentValue(row.observed),
      sampleSize: row.observed_samples, predictionSampleSize: row.predicted_samples,
      predictionVersions: row.prediction_versions,
    }))) : missing,
    subjects: values ? connected(values.subjects.map(row => ({
      id: row.id, name: row.name, knowledge: row.knowledge, completionRate: percentValue(row.completion_rate),
      mastery: percentValue(row.recall_rate), recallSamples: row.reviews, weak: row.weak,
    }))) : missing,
    ai: mapAiUsage(values?.ai_usage),
    workflow: values?.workflow,
    resources,
    jobs: values ? connected(mapJobs(values.jobs)) : current
      ? connected({ kinds: [], days: [], chapterStatus: current.chapter_jobs })
      : missing,
    activity: audit.data
      ? connected(audit.data.items.map(asActivity))
      : unavailable(audit.message ?? "当前无法读取系统活动。"),
    health,
  };
}

const missingManagement = (section: ManagementSection): string => ({
  models: "全站模型管理 API 待接入。",
  sources: "全站数据源管理 API 待接入。",
  notifications: "全站通知渠道与模板 API 待接入。",
  memory: "全站记忆策略管理 API 待接入。",
  jobs: "统一任务调度管理 API 待接入。",
  monitoring: "资源采集与运行服务监控 API 待接入。",
  settings: "系统设置与备份管理 API 待接入。",
})[section];

function liveClient(): AdminClient {
  return {
    mode: "live",
    operations,
    login: async (email, password) => adminProfile(await request("login", { method: "POST", body: { email, password } })),
    session: async () => adminProfile(await request("session")),
    logout: () => request("logout", { method: "POST" }),
    changePassword: (input) => request("password", { method: "POST", body: input }),
    dashboard: realDashboard,
    jobAnalytics: async (range) => {
      const result = await readAnalytics(range);
      return result.data ? connected(mapJobs(result.data.jobs)) : unavailable(result.message ?? "暂无任务统计。");
    },
    collection: async (section) => unavailable(missingManagement(section)),
    saveRecord: async (section) => unavailable(missingManagement(section)),
    deleteRecord: async (section) => unavailable(missingManagement(section)),
    runAction: async (section) => unavailable(missingManagement(section)),
    audit: readAudit,
    users: (query) => readPage("users", query),
    createUser: (body, idempotencyKey) => request("users", { method: "POST", body, idempotencyKey }),
    updateUser: (user_id, version, body) => request("users", { method: "PATCH", query: { user_id }, body, version }),
    userOverview: (user_id) => readResource(() => request("user-overview", { query: { user_id } })),
    userKnowledge: (user_id, filters) => readPage("user-knowledge", { ...filters, user_id }),
    userHistory: (user_id, filters) => readPage("user-history", { ...filters, user_id }),
    sessions: ({ online_only, ...filters } = {}) =>
      readPage("sessions", { ...normalizeFilters(filters), online: online_only }),
    health: readHealth,
  };
}

function page<T>(items: T[], limit = 20, cursor?: string): Page<T> {
  const offset = cursor && /^\d+$/.test(cursor) ? Number(cursor) : 0;
  const size = Math.min(100, Math.max(1, Math.floor(limit) || 20));
  const end = offset + size;
  return { items: items.slice(offset, end), next_cursor: end < items.length ? String(end) : null, has_more: end < items.length };
}

function withinTime(at: string, range: { from?: string; to?: string }): boolean {
  const time = Date.parse(at);
  return (!range.from || time >= Date.parse(range.from)) && (!range.to || time <= Date.parse(range.to));
}

function safeDemoMeta(meta?: Record<string, string>): Record<string, string> | undefined {
  if (!meta) return undefined;
  return Object.fromEntries(Object.entries(meta).filter(([key, value]) => {
    if (key === "credential") return value === "true" || value === "false";
    if (key === "baseUrl" && value) {
      try {
        const url = new URL(value);
        return ["http:", "https:"].includes(url.protocol) && !url.username && !url.password && !url.search && !url.hash;
      } catch {
        return false;
      }
    }
    return !/(password|secret|token|credential|api.?key|authorization|webhook)/i.test(key);
  }));
}

function applyDemoAction(section: ManagementSection, record: ManagementRecord, action: string): string {
  const updatedAt = new Date().toISOString();
  if (section === "models" && action === "test") {
    return `演示连接检查完成 · ${record.name}。未向模型服务发出请求。`;
  }
  if (section === "sources" && action === "sync") {
    record.updatedAt = updatedAt;
    record.meta = { ...record.meta, history: "演示同步完成 · 4 条成功 · 0 条失败", success: "4", failed: "0" };
    return `演示同步完成 · ${record.name}。未读取外部资料。`;
  }
  if (section === "notifications" && action === "test") {
    return `演示消息预检完成 · ${record.name}。未发送外部消息。`;
  }
  if (section === "jobs" && action === "trigger") {
    record.updatedAt = updatedAt;
    record.status = "queued";
    return `演示任务已排队 · ${record.name}。后台任务保持暂停。`;
  }
  throw new AdminApiError("未找到此演示操作。", 400, "DEMO_ACTION_UNSUPPORTED");
}

function demoClient(): AdminClient {
  const records = structuredClone(managementFixtures);
  const requireLearner = (id: string) => {
    const row = demoUsers.find((user) => user.id === id);
    if (!row) throw new AdminApiError("未找到此演示用户。", 404, "DEMO_NOT_FOUND");
    return demoLearner(row);
  };
  const requireRecord = (section: ManagementSection, id: string): ManagementRecord => {
    const record = records[section].find((item) => item.id === id);
    if (!record) throw new AdminApiError("未找到这条演示记录。", 404, "DEMO_NOT_FOUND");
    return record;
  };
  return {
    mode: "demo",
    operations: null,
    login: async () => { throw new AdminApiError("当前是演示模式。请使用演示入口。", 400, "DEMO_ONLY"); },
    session: async () => ({ ...demoAdmin }),
    logout: async () => {},
    changePassword: async (_input: PasswordInput) => {
      throw new AdminApiError("演示会话没有可修改的密码。", 400, "DEMO_ONLY");
    },
    dashboard: async (range) => demoDashboard(range),
    jobAnalytics: async (range) => demoDashboard(range).jobs,
    collection: async (section) => demo(structuredClone(records[section])),
    saveRecord: async (section, input, id) => {
      if (id) requireRecord(section, id);
      const next = {
        ...input,
        meta: safeDemoMeta(input.meta),
        id: id ?? crypto.randomUUID(),
        updatedAt: new Date().toISOString(),
      };
      let rows = records[section].filter((row) => row.id !== next.id);
      if (section === "models" && next.meta?.default === "true") {
        rows = rows.map((row) => row.meta?.default === "true"
          ? { ...row, meta: { ...row.meta, default: "false" } }
          : row);
      }
      records[section] = [next, ...rows];
      return demo(structuredClone(next));
    },
    deleteRecord: async (section, id) => {
      requireRecord(section, id);
      records[section] = records[section].filter((row) => row.id !== id);
      return demo(null);
    },
    runAction: async (section, id, action) => {
      const record = requireRecord(section, id);
      return demo({ message: applyDemoAction(section, record, action) });
    },
    audit: async (input = {}) => {
      const filters = normalizeFilters(input);
      const items = demoAudit().filter((event) =>
        (!filters.severity || event.severity === filters.severity)
        && (!filters.action || event.action === filters.action)
        && (!filters.user_id || event.actor_id === filters.user_id || event.target_user_id === filters.user_id)
        && withinTime(event.created_at, filters));
      return demo(page(items, filters.limit, filters.cursor));
    },
    users: async ({ limit, cursor, q } = {}) => {
      const search = q?.trim().toLocaleLowerCase();
      const items = demoUsers.filter((user) => !search || [user.display_name, user.email].some((field) =>
        field.toLocaleLowerCase().includes(search)));
      return demo(page(items, limit, cursor));
    },
    createUser: async () => { throw new AdminApiError("演示模式无法创建真实账户。", 403, "DEMO_ONLY"); },
    updateUser: async () => { throw new AdminApiError("演示模式无法修改真实账户。", 403, "DEMO_ONLY"); },
    userOverview: async (userId) => demo(requireLearner(userId).overview),
    userKnowledge: async (userId, { limit, cursor } = {}) => demo(page(requireLearner(userId).knowledge, limit, cursor)),
    userHistory: async (userId, { limit, cursor } = {}) => demo(page(requireLearner(userId).reviews, limit, cursor)),
    sessions: async ({ limit, cursor, online_only, user_id, ...input } = {}) => {
      const filters = normalizeFilters(input);
      const items = demoSessions().filter((entry) =>
        (!user_id || entry.user_id === user_id)
        && (online_only === undefined || entry.online === online_only)
        && withinTime(entry.created_at, filters));
      return demo(page<AdminSession>(items, limit, cursor));
    },
    health: async () => demo({ status: "ready", database: "ready", migration: "demo", checkedAt: new Date().toISOString() }),
  };
}

export function createAdminClient(mode: AdminMode): AdminClient {
  return mode === "demo" ? demoClient() : liveClient();
}
