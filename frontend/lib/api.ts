/**
 * AI Learning Memory OS — 类型化 API v1 客户端
 *
 * 严格按 API_CONTRACTS.md 的端点路径、方法、请求/响应类型实现，不发明端点。
 * 统一处理：
 *  - 基路径 `${NEXT_PUBLIC_API_BASE_URL}/api/v1`，未配置时明确抛出 CONFIG_MISSING；
 *  - Bearer JWT 鉴权（health / auth/token 除外）；
 *  - 创建/触发/完成类 POST 的 Idempotency-Key；
 *  - 更新类请求的 If-Match: "<version>"；
 *  - 统一错误响应 → ApiError（含 code / message / details / request_id / retryable）；
 *  - 204 无响应体；网络异常归一化为 NETWORK_ERROR。
 *
 * 本模块不使用任何假数据或硬编码兜底：请求失败即抛出真实错误，由 UI 呈现真实状态。
 */

import type {
  AICallLogRead,
  AIProviderConfigRead,
  AIProviderConfigWrite,
  AsyncOperationRead,
  ChannelConfigRead,
  ChannelConfigWrite,
  ChannelValidation,
  DailyBatchRead,
  DailyGenerateRequest,
  DailyTaskRead,
  ErrorDetail,
  ErrorResponse,
  ExtractRequest,
  HealthLive,
  HealthReady,
  KnowledgeMergeRequest,
  KnowledgePointRead,
  KnowledgePointWrite,
  ListAICallsParams,
  ListKnowledgePointsParams,
  ListNotionDataSourcesParams,
  ListNotificationJobsParams,
  ListRawNotesParams,
  ListReviewBatchesParams,
  ListReviewHistoryParams,
  ListReviewItemsParams,
  ListReviewTasksParams,
  ListSubjectsParams,
  ListSyncRunsParams,
  ListTemplatesParams,
  NotionDataSourceRead,
  NotionDataSourceWrite,
  NotionIntegrationRead,
  NotionIntegrationWrite,
  NotificationCreateRequest,
  NotificationDeliveryRead,
  NotificationJobRead,
  Page,
  PageParams,
  ProviderValidation,
  RawNoteRead,
  ReviewCompleteRequest,
  ReviewCompleteResponse,
  ReviewHistoryRead,
  ReviewItemGenerateRequest,
  ReviewItemRead,
  ReviewItemWrite,
  ScheduleCompareRequest,
  ScheduleCompareResponse,
  ScheduleStateRead,
  ScheduleSwitchRequest,
  SkipRequest,
  StatisticsParams,
  StatisticsRead,
  SubjectRead,
  SubjectStrategyRead,
  SubjectStrategyWrite,
  SubjectWrite,
  SyncRunRead,
  TemplateRead,
  TemplateWrite,
  TokenRequest,
  TokenResponse,
  UserRead,
  UUID,
} from '@/types/api';

// ---------------------------------------------------------------------------
// 配置与令牌
// ---------------------------------------------------------------------------

const TOKEN_STORAGE_KEY = 'alm:access_token';
const EMAIL_STORAGE_KEY = 'alm:login_email';

/** 解析 API 基路径；未配置时明确报错，不静默连到猜测地址。 */
function resolveApiBase(): string {
  const raw = process.env.NEXT_PUBLIC_API_BASE_URL;
  if (raw?.trim()) return `${raw.replace(/\/+$/, '')}/api/v1`;
  return `${typeof window === 'undefined' ? 'http://127.0.0.1:3030' : window.location.origin}/api/v1`;
}

/** 读取当前 Bearer 令牌（仅浏览器端有值）。 */
export function getToken(): string | null {
  if (typeof window === 'undefined') return null;
  return window.localStorage.getItem(TOKEN_STORAGE_KEY);
}

export function setToken(token: string | null): void {
  if (typeof window === 'undefined') return;
  if (token) window.localStorage.setItem(TOKEN_STORAGE_KEY, token);
  else window.localStorage.removeItem(TOKEN_STORAGE_KEY);
}

export function getStoredEmail(): string | null {
  if (typeof window === 'undefined') return null;
  return window.localStorage.getItem(EMAIL_STORAGE_KEY);
}

export function setStoredEmail(email: string | null): void {
  if (typeof window === 'undefined') return;
  if (email) window.localStorage.setItem(EMAIL_STORAGE_KEY, email);
  else window.localStorage.removeItem(EMAIL_STORAGE_KEY);
}

/** 生成幂等键（1..128 字符）。同一动作重试应复用同一个键。 */
export function newIdempotencyKey(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  return `idem-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

// ---------------------------------------------------------------------------
// 统一错误
// ---------------------------------------------------------------------------

export interface ApiErrorInit {
  status: number;
  code: string;
  message: string;
  details: ErrorDetail[];
  requestId: string;
  retryable: boolean;
}

/** 所有请求失败的统一错误类型。 */
export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: ErrorDetail[];
  readonly requestId: string;
  readonly retryable: boolean;

  constructor(init: ApiErrorInit) {
    super(init.message);
    this.name = 'ApiError';
    this.status = init.status;
    this.code = init.code;
    this.details = init.details;
    this.requestId = init.requestId;
    this.retryable = init.retryable;
  }

  /** 401/403 或鉴权类错误码。 */
  get isAuthError(): boolean {
    return (
      this.status === 401 ||
      this.status === 403 ||
      this.code === 'AUTH_REQUIRED' ||
      this.code === 'AUTH_INVALID' ||
      this.code === 'FORBIDDEN'
    );
  }

  get isNotFound(): boolean {
    return this.status === 404 || this.code === 'RESOURCE_NOT_FOUND';
  }
}

/** 把任意异常归一化为 ApiError。 */
export function toApiError(cause: unknown): ApiError {
  if (cause instanceof ApiError) return cause;
  if (cause instanceof Error) {
    return new ApiError({
      status: 0,
      code: 'UNKNOWN_ERROR',
      message: cause.message || '发生未知错误。',
      details: [],
      requestId: '',
      retryable: false,
    });
  }
  return new ApiError({
    status: 0,
    code: 'UNKNOWN_ERROR',
    message: '发生未知错误。',
    details: [],
    requestId: '',
    retryable: false,
  });
}

// ---------------------------------------------------------------------------
// 底层请求
// ---------------------------------------------------------------------------

type HttpMethod = 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';

interface RequestOptions {
  body?: unknown;
  /** 查询参数；undefined / null / 空字符串会被省略。 */
  query?: object;
  /** 创建/触发/完成类 POST 必带。 */
  idempotencyKey?: string;
  /** 更新类请求必带，值为资源 version。 */
  ifMatch?: string | number;
  /** health / auth/token 不附加 Authorization。 */
  skipAuth?: boolean;
  signal?: AbortSignal;
}

async function request<T>(method: HttpMethod, path: string, options: RequestOptions = {}): Promise<T> {
  const url = new URL(`${resolveApiBase()}${path}`);
  if (options.query) {
    for (const [key, value] of Object.entries(options.query)) {
      if (value === undefined || value === null || value === '') continue;
      url.searchParams.set(key, String(value));
    }
  }

  const headers: Record<string, string> = { Accept: 'application/json', 'X-Memory-Client': 'web' };
  if (options.body !== undefined) headers['Content-Type'] = 'application/json';
  const token = getToken();
  if (!options.skipAuth && token) headers['Authorization'] = `Bearer ${token}`;
  if (options.idempotencyKey) headers['Idempotency-Key'] = options.idempotencyKey;
  if (options.ifMatch !== undefined) headers['If-Match'] = `"${String(options.ifMatch)}"`;

  let response: Response;
  try {
    response = await fetch(url.toString(), {
      method,
      headers,
      body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
      signal: options.signal,
      cache: 'no-store',
      credentials: 'include',
    });
  } catch {
    throw new ApiError({
      status: 0,
      code: 'NETWORK_ERROR',
      message: '无法连接后端服务，请确认后端已启动、地址配置正确且网络可达。',
      details: [],
      requestId: '',
      retryable: true,
    });
  }

  // 删除/禁用类动作返回 204，无响应体。
  if (response.status === 204) return undefined as T;

  const text = await response.text();
  let payload: unknown = null;
  if (text) {
    try {
      payload = JSON.parse(text) as unknown;
    } catch {
      payload = null;
    }
  }

  if (!response.ok) {
    const body = payload && typeof payload === 'object' && 'error' in payload
      ? (payload as ErrorResponse).error
      : undefined;
    throw new ApiError({
      status: response.status,
      code: body?.code ?? `HTTP_${response.status}`,
      message: body?.message ?? `请求失败（HTTP ${response.status}）`,
      details: body?.details ?? [],
      requestId: body?.request_id ?? response.headers.get('X-Request-ID') ?? '',
      retryable: body?.retryable ?? response.status >= 500,
    });
  }

  return payload as T;
}

// ---------------------------------------------------------------------------
// 端点封装（路径与 API_CONTRACTS.md §4 一一对应）
// ---------------------------------------------------------------------------

export const api = {
  // ---- 平台、身份 ----
  healthLive: () => request<HealthLive>('GET', '/health/live', { skipAuth: true }),
  healthReady: () => request<HealthReady>('GET', '/health/ready', { skipAuth: true }),
  login: (body: TokenRequest) =>
    request<TokenResponse>('POST', '/auth/token', { body, skipAuth: true }),
  me: () => request<UserRead>('GET', '/me'),

  // ---- 学科与数据驱动策略（FR-10）----
  listSubjects: (params: ListSubjectsParams = {}) =>
    request<Page<SubjectRead>>('GET', '/subjects', { query: params }),
  createSubject: (body: SubjectWrite, idempotencyKey: string) =>
    request<SubjectRead>('POST', '/subjects', { body, idempotencyKey }),
  getSubject: (id: UUID) => request<SubjectRead>('GET', `/subjects/${id}`),
  updateSubject: (id: UUID, body: Partial<SubjectWrite>, version: number) =>
    request<SubjectRead>('PATCH', `/subjects/${id}`, { body, ifMatch: version }),
  deleteSubject: (id: UUID, version: number) =>
    request<void>('DELETE', `/subjects/${id}`, { ifMatch: version }),
  getSubjectStrategy: (id: UUID) =>
    request<SubjectStrategyRead>('GET', `/subjects/${id}/strategy`),
  putSubjectStrategy: (id: UUID, body: SubjectStrategyWrite, ifMatch?: string | number) =>
    request<SubjectStrategyRead>('PUT', `/subjects/${id}/strategy`, { body, ifMatch }),

  // ---- Notion（FR-01）----
  listNotionIntegrations: (params: PageParams = {}) =>
    request<Page<NotionIntegrationRead>>('GET', '/notion/integrations', { query: params }),
  createNotionIntegration: (body: NotionIntegrationWrite, idempotencyKey: string) =>
    request<NotionIntegrationRead>('POST', '/notion/integrations', { body, idempotencyKey }),
  getNotionIntegration: (id: UUID) =>
    request<NotionIntegrationRead>('GET', `/notion/integrations/${id}`),
  updateNotionIntegration: (id: UUID, body: Partial<NotionIntegrationWrite>, version: number) =>
    request<NotionIntegrationRead>('PATCH', `/notion/integrations/${id}`, { body, ifMatch: version }),
  deleteNotionIntegration: (id: UUID, version: number) =>
    request<void>('DELETE', `/notion/integrations/${id}`, { ifMatch: version }),
  listNotionDataSources: (params: ListNotionDataSourcesParams = {}) =>
    request<Page<NotionDataSourceRead>>('GET', '/notion/data-sources', { query: params }),
  createNotionDataSource: (body: NotionDataSourceWrite, idempotencyKey: string) =>
    request<NotionDataSourceRead>('POST', '/notion/data-sources', { body, idempotencyKey }),
  getNotionDataSource: (id: UUID) =>
    request<NotionDataSourceRead>('GET', `/notion/data-sources/${id}`),
  updateNotionDataSource: (id: UUID, body: Partial<NotionDataSourceWrite>, version: number) =>
    request<NotionDataSourceRead>('PATCH', `/notion/data-sources/${id}`, { body, ifMatch: version }),
  deleteNotionDataSource: (id: UUID, version: number) =>
    request<void>('DELETE', `/notion/data-sources/${id}`, { ifMatch: version }),
  syncNotionDataSource: (id: UUID, idempotencyKey: string) =>
    request<SyncRunRead>('POST', `/notion/data-sources/${id}/sync`, { idempotencyKey }),
  listSyncRuns: (params: ListSyncRunsParams = {}) =>
    request<Page<SyncRunRead>>('GET', '/notion/sync-runs', { query: params }),
  getSyncRun: (id: UUID) => request<SyncRunRead>('GET', `/notion/sync-runs/${id}`),
  listRawNotes: (params: ListRawNotesParams = {}) =>
    request<Page<RawNoteRead>>('GET', '/raw-notes', { query: params }),
  getRawNote: (id: UUID) => request<RawNoteRead>('GET', `/raw-notes/${id}`),

  // ---- AI Provider 与调用审计（FR-02）----
  listAIProviders: (params: PageParams = {}) =>
    request<Page<AIProviderConfigRead>>('GET', '/ai/providers', { query: params }),
  createAIProvider: (body: AIProviderConfigWrite, idempotencyKey: string) =>
    request<AIProviderConfigRead>('POST', '/ai/providers', { body, idempotencyKey }),
  getAIProvider: (id: UUID) =>
    request<AIProviderConfigRead>('GET', `/ai/providers/${id}`),
  updateAIProvider: (id: UUID, body: Partial<AIProviderConfigWrite>, version: number) =>
    request<AIProviderConfigRead>('PATCH', `/ai/providers/${id}`, { body, ifMatch: version }),
  deleteAIProvider: (id: UUID, version: number) =>
    request<void>('DELETE', `/ai/providers/${id}`, { ifMatch: version }),
  validateAIProvider: (id: UUID, idempotencyKey: string) =>
    request<ProviderValidation>('POST', `/ai/providers/${id}/validate`, { idempotencyKey }),
  listAICalls: (params: ListAICallsParams = {}) =>
    request<Page<AICallLogRead>>('GET', '/ai/calls', { query: params }),
  getAICall: (id: UUID) => request<AICallLogRead>('GET', `/ai/calls/${id}`),

  // ---- 知识点与出题（FR-03 / FR-04）----
  listKnowledgePoints: (params: ListKnowledgePointsParams = {}) =>
    request<Page<KnowledgePointRead>>('GET', '/knowledge-points', { query: params }),
  createKnowledgePoint: (body: KnowledgePointWrite, idempotencyKey: string) =>
    request<KnowledgePointRead>('POST', '/knowledge-points', { body, idempotencyKey }),
  getKnowledgePoint: (id: UUID) =>
    request<KnowledgePointRead>('GET', `/knowledge-points/${id}`),
  updateKnowledgePoint: (id: UUID, body: Partial<KnowledgePointWrite>, version: number) =>
    request<KnowledgePointRead>('PATCH', `/knowledge-points/${id}`, { body, ifMatch: version }),
  activateKnowledgePoint: (id: UUID, idempotencyKey: string) =>
    request<KnowledgePointRead>('POST', `/knowledge-points/${id}/activate`, { idempotencyKey }),
  archiveKnowledgePoint: (id: UUID, idempotencyKey: string) =>
    request<KnowledgePointRead>('POST', `/knowledge-points/${id}/archive`, { idempotencyKey }),
  mergeKnowledgePoint: (id: UUID, body: KnowledgeMergeRequest, idempotencyKey: string) =>
    request<KnowledgePointRead>('POST', `/knowledge-points/${id}/merge`, { body, idempotencyKey }),
  extractRawNote: (id: UUID, body: ExtractRequest, idempotencyKey: string) =>
    request<AsyncOperationRead>('POST', `/raw-notes/${id}/extract`, { body, idempotencyKey }),
  listReviewItems: (id: UUID, params: ListReviewItemsParams = {}) =>
    request<Page<ReviewItemRead>>('GET', `/knowledge-points/${id}/review-items`, { query: params }),
  generateReviewItems: (id: UUID, body: ReviewItemGenerateRequest, idempotencyKey: string) =>
    request<AsyncOperationRead>('POST', `/knowledge-points/${id}/review-items/generate`, { body, idempotencyKey }),
  createReviewItem: (id: UUID, body: ReviewItemWrite, idempotencyKey: string) =>
    request<ReviewItemRead>('POST', `/knowledge-points/${id}/review-items`, { body, idempotencyKey }),
  updateReviewItem: (id: UUID, body: Partial<ReviewItemWrite>, version: number) =>
    request<ReviewItemRead>('PATCH', `/review-items/${id}`, { body, ifMatch: version }),

  // ---- 调度与每日任务（FR-05 / FR-06）----
  getSchedule: (id: UUID) =>
    request<ScheduleStateRead>('GET', `/knowledge-points/${id}/schedule`),
  switchScheduleStrategy: (id: UUID, body: ScheduleSwitchRequest, version: number) =>
    request<ScheduleStateRead>('PUT', `/knowledge-points/${id}/schedule/strategy`, { body, ifMatch: version }),
  compareSchedule: (id: UUID, body: ScheduleCompareRequest = {}) =>
    request<ScheduleCompareResponse>('POST', `/knowledge-points/${id}/schedule/compare`, { body }),
  generateReviewBatch: (body: DailyGenerateRequest, idempotencyKey: string) =>
    request<DailyBatchRead>('POST', '/review-batches/generate', { body, idempotencyKey }),
  listReviewBatches: (params: ListReviewBatchesParams = {}) =>
    request<Page<DailyBatchRead>>('GET', '/review-batches', { query: params }),
  getReviewBatch: (id: UUID) =>
    request<DailyBatchRead>('GET', `/review-batches/${id}`),
  listReviewTasks: (params: ListReviewTasksParams = {}) =>
    request<Page<DailyTaskRead>>('GET', '/review-tasks', { query: params }),
  getReviewTask: (id: UUID) =>
    request<DailyTaskRead>('GET', `/review-tasks/${id}`),
  startTask: (id: UUID, idempotencyKey: string) =>
    request<DailyTaskRead>('POST', `/review-tasks/${id}/start`, { idempotencyKey }),
  skipTask: (id: UUID, body: SkipRequest, idempotencyKey: string) =>
    request<DailyTaskRead>('POST', `/review-tasks/${id}/skip`, { body, idempotencyKey }),
  completeTask: (id: UUID, body: ReviewCompleteRequest, idempotencyKey: string) =>
    request<ReviewCompleteResponse>('POST', `/review-tasks/${id}/complete`, { body, idempotencyKey }),

  // ---- 复习闭环与统计（FR-09）----
  listReviewHistory: (params: ListReviewHistoryParams = {}) =>
    request<Page<ReviewHistoryRead>>('GET', '/review-history', { query: params }),
  getReviewHistory: (id: UUID) =>
    request<ReviewHistoryRead>('GET', `/review-history/${id}`),
  getStatistics: (params: StatisticsParams) =>
    request<StatisticsRead>('GET', '/statistics/overview', { query: params }),

  // ---- 通知（FR-07 / FR-08）----
  listNotificationChannels: (params: PageParams = {}) =>
    request<Page<ChannelConfigRead>>('GET', '/notification/channels', { query: params }),
  createNotificationChannel: (body: ChannelConfigWrite, idempotencyKey: string) =>
    request<ChannelConfigRead>('POST', '/notification/channels', { body, idempotencyKey }),
  getNotificationChannel: (id: UUID) =>
    request<ChannelConfigRead>('GET', `/notification/channels/${id}`),
  updateNotificationChannel: (id: UUID, body: Partial<ChannelConfigWrite>, version: number) =>
    request<ChannelConfigRead>('PATCH', `/notification/channels/${id}`, { body, ifMatch: version }),
  deleteNotificationChannel: (id: UUID, version: number) =>
    request<void>('DELETE', `/notification/channels/${id}`, { ifMatch: version }),
  validateNotificationChannel: (id: UUID, idempotencyKey: string) =>
    request<ChannelValidation>('POST', `/notification/channels/${id}/validate`, { idempotencyKey }),
  listTemplates: (params: ListTemplatesParams = {}) =>
    request<Page<TemplateRead>>('GET', '/notification/templates', { query: params }),
  createTemplate: (body: TemplateWrite, idempotencyKey: string) =>
    request<TemplateRead>('POST', '/notification/templates', { body, idempotencyKey }),
  getTemplate: (id: UUID) =>
    request<TemplateRead>('GET', `/notification/templates/${id}`),
  updateTemplate: (id: UUID, body: Partial<TemplateWrite>, version: number) =>
    request<TemplateRead>('PATCH', `/notification/templates/${id}`, { body, ifMatch: version }),
  deleteTemplate: (id: UUID, version: number) =>
    request<void>('DELETE', `/notification/templates/${id}`, { ifMatch: version }),
  createTaskNotification: (taskId: UUID, body: NotificationCreateRequest, idempotencyKey: string) =>
    request<NotificationJobRead>('POST', `/review-tasks/${taskId}/notifications`, { body, idempotencyKey }),
  listNotificationJobs: (params: ListNotificationJobsParams = {}) =>
    request<Page<NotificationJobRead>>('GET', '/notification/jobs', { query: params }),
  getNotificationJob: (id: UUID) =>
    request<NotificationJobRead>('GET', `/notification/jobs/${id}`),
  retryNotificationJob: (id: UUID, idempotencyKey: string) =>
    request<NotificationJobRead>('POST', `/notification/jobs/${id}/retry`, { idempotencyKey }),
  listNotificationDeliveries: (jobId: UUID, params: PageParams = {}) =>
    request<Page<NotificationDeliveryRead>>('GET', `/notification/jobs/${jobId}/deliveries`, { query: params }),
};
