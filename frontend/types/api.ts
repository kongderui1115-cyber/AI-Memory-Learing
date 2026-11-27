/**
 * AI Learning Memory OS — REST API v1 严格类型定义
 *
 * 唯一事实源：API_CONTRACTS.md（契约 1.0.0，基路径 /api/v1）与冻结的契约基线
 * backend/app/contracts/{enums,models}.py。本文件为手写锁定版本，字段名、枚举值、
 * 可选性、可空性均严格对齐契约，不自行发明字段或端点。
 *
 * 约定：
 *  - 字段一律 snake_case；
 *  - UUID / RFC3339 时间 / YYYY-MM-DD 日期在 JSON 中均为 string（见下方别名说明）；
 *  - Decimal 不转成 JS number，契约中对应字段一律按 string 看待（本契约响应中未出现 Decimal）；
 *  - Optional[T] 的响应字段为 `T | null`，请求中的可省略字段为 `?:`；
 *  - 所有列表响应统一为 Page<T>；
 *  - 资源公共字段：id / created_at / updated_at / version。
 *
 * 说明：契约 §5 提到由 branded 类型约束 UUID / datetime / date。这里采用带文档说明的
 * string 别名，保持与 fetch JSON 的零摩擦互操作；格式约束由服务端校验与这里的注释共同表达。
 */

// ---------------------------------------------------------------------------
// 标量别名
// ---------------------------------------------------------------------------

/** UUID 字符串，例如 "9f1c7e6a-...."。 */
export type UUID = string;
/** UTC RFC3339 date-time 字符串，例如 "2026-11-13T08:00:00Z"。 */
export type DateTime = string;
/** 日期字符串，格式 YYYY-MM-DD。 */
export type DateOnly = string;

// ---------------------------------------------------------------------------
// 枚举（字符串联合，值必须与契约 / enums.py 完全一致）
// ---------------------------------------------------------------------------

export type ScheduleStrategy = 'ebbinghaus' | 'fsrs';
export type ReviewRating = 'again' | 'hard' | 'good' | 'easy';
export type KnowledgePointStatus = 'draft' | 'active' | 'archived' | 'merged';
export type QuestionType = 'qa' | 'cloze' | 'multiple_choice' | 'short_explanation';
export type TaskStatus = 'pending' | 'in_progress' | 'completed' | 'skipped' | 'cancelled';
export type BatchStatus = 'pending' | 'ready' | 'completed' | 'cancelled';
export type RunStatus = 'pending' | 'running' | 'succeeded' | 'failed' | 'partial' | 'cancelled';
export type NotificationChannelType =
  | 'wecom_app'
  | 'wechat_official_account'
  | 'third_party_push'
  | 'wecom_webhook'
  | 'dingtalk_webhook'
  | 'dingtalk_app'
  | 'smtp';
export type NotificationJobStatus = 'pending' | 'processing' | 'sent' | 'failed' | 'cancelled';
export type AIProviderType = 'openai' | 'deepseek' | 'openai_compatible';
export type AICallStatus = 'pending' | 'running' | 'succeeded' | 'failed' | 'cancelled';

/** Notion 数据源类型（models.py: Literal["database", "page_tree"]）。 */
export type NotionSourceType = 'database' | 'page_tree';
/** 同步触发方式（models.py: Literal["manual", "scheduled"]）。 */
export type SyncTriggerType = 'manual' | 'scheduled';
/** 通知投递状态（models.py: Literal["sending", "sent", "failed"]）。 */
export type DeliveryStatus = 'sending' | 'sent' | 'failed';

/** 契约 §1 中出现的全部业务错误码（供参考与穷举提示）。 */
export type ContractErrorCode =
  | 'VALIDATION_ERROR'
  | 'INVALID_STATE'
  | 'UNSUPPORTED_STRATEGY'
  | 'AUTH_REQUIRED'
  | 'AUTH_INVALID'
  | 'FORBIDDEN'
  | 'RESOURCE_NOT_FOUND'
  | 'CONFLICT'
  | 'DUPLICATE_RESOURCE'
  | 'IDEMPOTENCY_CONFLICT'
  | 'VERSION_CONFLICT'
  | 'TASK_ALREADY_COMPLETED'
  | 'SEMANTIC_VALIDATION_ERROR'
  | 'RATE_LIMITED'
  | 'INTERNAL_ERROR'
  | 'EXTERNAL_SERVICE_ERROR'
  | 'CONFIG_MISSING'
  | 'SERVICE_UNAVAILABLE'
  | 'EXTERNAL_TIMEOUT';

// ---------------------------------------------------------------------------
// 通用结构
// ---------------------------------------------------------------------------

/** 成功资源的公共字段（契约 §1）。 */
export interface Resource {
  id: UUID;
  created_at: DateTime;
  updated_at: DateTime;
  /** 版本号 >= 1，更新时作为 If-Match 的值。 */
  version: number;
}

/** 统一分页响应：`{"items":[T],"next_cursor":"opaque|null","has_more":bool}`。 */
export interface Page<T> {
  items: T[];
  next_cursor: string | null;
  has_more: boolean;
}

export interface ErrorDetail {
  field: string | null;
  reason: string;
}

export interface ErrorBody {
  code: string;
  message: string;
  details: ErrorDetail[];
  request_id: string;
  retryable: boolean;
}

/** 统一错误响应体：`{"error": {...}}`。 */
export interface ErrorResponse {
  error: ErrorBody;
}

// ---------------------------------------------------------------------------
// 平台、身份
// ---------------------------------------------------------------------------

export interface TokenRequest {
  email: string;
  /** 契约约束 8..256 字符。 */
  password: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: 'bearer';
  expires_in_seconds: number;
}

export interface UserRead extends Resource {
  email: string;
  display_name: string;
  timezone: string;
  is_active: boolean;
}

/** GET /health/live → { status: "ok" } */
export interface HealthLive {
  status: 'ok';
}

/** GET /health/ready → { status, checks }；checks 结构由后端决定。 */
export interface HealthReady {
  status: string;
  checks: Record<string, unknown>;
}

// ---------------------------------------------------------------------------
// 学科与学科策略（FR-10）
// ---------------------------------------------------------------------------

export interface SubjectWrite {
  name: string;
  /** 契约正则 ^[a-z0-9][a-z0-9-]{0,79}$ */
  slug: string;
  parent_id?: UUID | null;
  description?: string | null;
  language_code?: string;
  tags?: string[];
  is_active?: boolean;
}

export interface SubjectRead extends Resource {
  name: string;
  slug: string;
  parent_id: UUID | null;
  description: string | null;
  language_code: string;
  tags: string[];
  is_active: boolean;
}

export interface SubjectStrategyWrite {
  extraction_prompt: string;
  question_type_preferences?: QuestionType[];
  glossary?: Record<string, string>;
  scheduler_overrides?: Record<string, unknown>;
  notification_template_overrides?: Record<string, unknown>;
  prompt_version: string;
  is_active?: boolean;
}

export interface SubjectStrategyRead extends Resource {
  subject_id: UUID;
  extraction_prompt: string;
  question_type_preferences: QuestionType[];
  glossary: Record<string, string>;
  scheduler_overrides: Record<string, unknown>;
  notification_template_overrides: Record<string, unknown>;
  prompt_version: string;
  is_active: boolean;
}

// ---------------------------------------------------------------------------
// Notion（FR-01）
// ---------------------------------------------------------------------------

export interface NotionIntegrationWrite {
  name: string;
  /** 环境变量名，不是秘密值。 */
  credential_ref: string;
  api_version?: string;
  is_enabled?: boolean;
}

export interface NotionIntegrationRead extends Resource {
  name: string;
  credential_ref: string;
  api_version: string;
  is_enabled: boolean;
  last_validated_at: DateTime | null;
}

export interface NotionDataSourceWrite {
  integration_id: UUID;
  source_type: NotionSourceType;
  external_source_id: string;
  name: string;
  /** 契约约束 >= 5，默认 60。 */
  sync_interval_minutes?: number;
  is_enabled?: boolean;
}

export interface NotionDataSourceRead extends Resource {
  integration_id: UUID;
  source_type: NotionSourceType;
  external_source_id: string;
  name: string;
  sync_interval_minutes: number;
  is_enabled: boolean;
  last_edited_watermark: DateTime | null;
  next_sync_at: DateTime | null;
}

export interface SyncRunRead {
  id: UUID;
  data_source_id: UUID;
  trigger_type: SyncTriggerType;
  status: RunStatus;
  watermark_from: DateTime | null;
  watermark_to: DateTime | null;
  items_seen: number;
  items_imported: number;
  items_failed: number;
  attempt: number;
  started_at: DateTime | null;
  finished_at: DateTime | null;
  error_code: string | null;
  error_message: string | null;
}

export interface RawNoteRead {
  id: UUID;
  data_source_id: UUID;
  external_page_id: string;
  external_version: string;
  last_edited_time: DateTime;
  title: string;
  content_markdown: string;
  content_hash: string;
  source_url: string;
  metadata: Record<string, unknown>;
  synced_at: DateTime;
}

// ---------------------------------------------------------------------------
// AI Provider 与调用审计（FR-02）
// ---------------------------------------------------------------------------

export interface AIProviderConfigWrite {
  name: string;
  provider: AIProviderType;
  model_name: string;
  base_url?: string | null;
  /** 环境变量名，不是秘密值。 */
  credential_ref: string;
  temperature?: number;
  timeout_seconds?: number;
  max_retries?: number;
  rate_limit_per_minute?: number | null;
  is_enabled?: boolean;
  is_default?: boolean;
}

export interface AIProviderConfigRead extends Resource {
  name: string;
  provider: AIProviderType;
  model_name: string;
  base_url: string | null;
  credential_ref: string;
  temperature: number;
  timeout_seconds: number;
  max_retries: number;
  rate_limit_per_minute: number | null;
  is_enabled: boolean;
  is_default: boolean;
}

export interface AICallLogRead {
  id: UUID;
  provider_config_id: UUID;
  operation: string;
  provider: AIProviderType;
  model_name: string;
  prompt_version: string;
  request_id: UUID;
  status: AICallStatus;
  input_tokens: number | null;
  output_tokens: number | null;
  total_tokens: number | null;
  duration_ms: number | null;
  attempt_count: number;
  error_code: string | null;
  error_message: string | null;
  started_at: DateTime;
  finished_at: DateTime | null;
}

/** POST /ai/providers/{id}/validate → { valid, provider, model }（契约 §4）。 */
export interface ProviderValidation {
  valid: boolean;
  provider: AIProviderType;
  model: string;
}

// ---------------------------------------------------------------------------
// 知识点与题目（FR-03 / FR-04）
// ---------------------------------------------------------------------------

export interface KnowledgePointWrite {
  subject_id: UUID;
  title: string;
  body: string;
  summary: string;
  /** 契约约束 1..5。 */
  difficulty: number;
  keywords?: string[];
  tags?: string[];
  status?: KnowledgePointStatus;
}

export interface KnowledgePointRead extends Resource {
  subject_id: UUID;
  title: string;
  body: string;
  summary: string;
  difficulty: number;
  keywords: string[];
  tags: string[];
  status: KnowledgePointStatus;
  /** 人工修订标记：为真时自动同步不得覆盖。 */
  manual_revision: boolean;
  merged_into_id: UUID | null;
  canonical_hash: string;
}

export interface KnowledgeMergeRequest {
  target_id: UUID;
  reason?: string | null;
}

export interface ReviewItemWrite {
  question_type: QuestionType;
  question: string;
  answer: string;
  explanation?: string;
  summary?: string;
  options?: string[] | null;
}

export interface ReviewItemRead extends Resource {
  knowledge_point_id: UUID;
  question_type: QuestionType;
  question: string;
  answer: string;
  explanation: string;
  summary: string;
  options: string[] | null;
  item_version: number;
  is_current: boolean;
  manual_revision: boolean;
  provider_config_id: UUID | null;
  model_name: string | null;
  prompt_version: string | null;
  ai_call_log_id: UUID | null;
}

/** POST /raw-notes/{id}/extract 的请求体（契约 §4）。 */
export interface ExtractRequest {
  provider_config_id: UUID;
  subject_id?: UUID;
}

/** POST /knowledge-points/{id}/review-items/generate 的请求体（契约 §4）。 */
export interface ReviewItemGenerateRequest {
  provider_config_id: UUID;
  question_types: QuestionType[];
  /** 契约约束 1..20。 */
  count: number;
}

/**
 * 异步触发类端点（extract / review-items/generate / notification retry 等）
 * 的 202 响应 `{operation_id, status}`。形状来自 API_CONTRACTS.md §4。
 */
export interface AsyncOperationRead {
  operation_id: UUID;
  status: RunStatus;
}

// ---------------------------------------------------------------------------
// 调度与每日任务（FR-05 / FR-06）
// ---------------------------------------------------------------------------

export interface ScheduleStateRead extends Resource {
  knowledge_point_id: UUID;
  strategy: ScheduleStrategy;
  due_at: DateTime;
  last_reviewed_at: DateTime | null;
  review_count: number;
  lapse_count: number;
  interval_index: number;
  interval_days: number | null;
  stability: number | null;
  difficulty: number | null;
  retrievability: number | null;
  target_retention: number | null;
  algorithm_version: string;
  parameters: Record<string, unknown>;
  last_calculation: Record<string, unknown>;
  strategy_changed_at: DateTime;
}

export interface ScheduleSwitchRequest {
  strategy: ScheduleStrategy;
  parameters?: Record<string, unknown>;
}

export interface ScheduleProjection {
  due_at: DateTime;
  state: Record<string, unknown>;
  explanation: Record<string, unknown>;
}

export interface ScheduleCompareResponse {
  ebbinghaus: ScheduleProjection;
  fsrs: ScheduleProjection;
}

/** POST /knowledge-points/{id}/schedule/compare 的请求体（纯计算，不写库）。 */
export interface ScheduleCompareRequest {
  rating?: ReviewRating;
  reviewed_at?: DateTime;
}

export interface DailyGenerateRequest {
  local_date: DateOnly;
  timezone: string;
  /** 契约约束 1..500，默认 30。 */
  daily_limit?: number;
  subject_id?: UUID | null;
}

export interface DailyTaskRead extends Resource {
  batch_id: UUID;
  knowledge_point_id: UUID;
  review_item_id: UUID | null;
  scheduled_due_at: DateTime;
  priority: number;
  position: number;
  status: TaskStatus;
  started_at: DateTime | null;
  completed_at: DateTime | null;
}

export interface DailyBatchRead extends Resource {
  local_date: DateOnly;
  timezone: string;
  subject_id: UUID | null;
  daily_limit: number;
  status: BatchStatus;
  generated_at: DateTime;
  tasks: DailyTaskRead[];
}

/** POST /review-tasks/{id}/skip 的请求体。 */
export interface SkipRequest {
  reason?: string;
}

// ---------------------------------------------------------------------------
// 复习闭环与统计（FR-09）
// ---------------------------------------------------------------------------

export interface ReviewCompleteRequest {
  rating: ReviewRating;
  /** 契约约束 >= 0。 */
  duration_seconds: number;
  answer_self_assessment?: string | null;
  notes?: string | null;
  reviewed_at: DateTime;
}

export interface ReviewHistoryRead {
  id: UUID;
  task_id: UUID;
  knowledge_point_id: UUID;
  review_item_id: UUID | null;
  strategy: ScheduleStrategy;
  rating: ReviewRating;
  duration_seconds: number;
  answer_self_assessment: string | null;
  notes: string | null;
  reviewed_at: DateTime;
  previous_schedule: Record<string, unknown>;
  result_schedule: Record<string, unknown>;
}

/** 完成操作单事务返回：任务 + 历史 + 更新后的调度状态。 */
export interface ReviewCompleteResponse {
  task: DailyTaskRead;
  history: ReviewHistoryRead;
  schedule: ScheduleStateRead;
}

export interface TrendPoint {
  date: DateOnly;
  value: number;
}

export interface HeatmapPoint {
  date: DateOnly;
  count: number;
}

export interface StatisticsRead {
  from_date: DateOnly;
  to_date: DateOnly;
  total_tasks: number;
  completed_tasks: number;
  /** 0..1 */
  completion_rate: number;
  retention_trend: TrendPoint[];
  heatmap: HeatmapPoint[];
}

// ---------------------------------------------------------------------------
// 通知（FR-07 / FR-08）
// ---------------------------------------------------------------------------

export interface ChannelConfigWrite {
  name: string;
  channel_type: NotificationChannelType;
  /** 环境变量名，不是秘密值。 */
  credential_ref: string;
  settings?: Record<string, unknown>;
  is_enabled?: boolean;
  is_default?: boolean;
}

export interface ChannelConfigRead extends Resource {
  name: string;
  channel_type: NotificationChannelType;
  credential_ref: string;
  settings: Record<string, unknown>;
  is_enabled: boolean;
  is_default: boolean;
}

/** POST /notification/channels/{id}/validate → { valid, channel_type }（契约 §4）。 */
export interface ChannelValidation {
  valid: boolean;
  channel_type: NotificationChannelType;
}

export interface TemplateWrite {
  subject_id?: UUID | null;
  channel_type: NotificationChannelType;
  template_key: string;
  title_template: string;
  body_template: string;
  schema_variables?: string[];
  max_length?: number | null;
  is_active?: boolean;
}

export interface TemplateRead extends Resource {
  subject_id: UUID | null;
  channel_type: NotificationChannelType;
  template_key: string;
  title_template: string;
  body_template: string;
  schema_variables: string[];
  max_length: number | null;
  is_active: boolean;
}

export interface NotificationJobRead extends Resource {
  task_id: UUID;
  channel_config_id: UUID;
  template_id: UUID;
  status: NotificationJobStatus;
  attempt_count: number;
  max_attempts: number;
  next_attempt_at: DateTime | null;
  last_error_code: string | null;
  last_error_message: string | null;
  sent_at: DateTime | null;
}

export interface NotificationDeliveryRead {
  id: UUID;
  job_id: UUID;
  attempt_no: number;
  status: DeliveryStatus;
  provider_message_id: string | null;
  error_code: string | null;
  error_message: string | null;
  duration_ms: number | null;
  attempted_at: DateTime;
}

/** POST /review-tasks/{id}/notifications 的请求体（契约 §4）。 */
export interface NotificationCreateRequest {
  channel_config_id: UUID;
  template_id?: UUID;
}

// ---------------------------------------------------------------------------
// 查询参数（契约 §4 各端点允许的 query 参数；不发明额外参数）
// ---------------------------------------------------------------------------

export interface PageParams {
  /** 默认 20，范围 1..100。 */
  limit?: number;
  /** 不透明游标。 */
  cursor?: string;
}

export interface ListSubjectsParams extends PageParams {
  parent_id?: UUID;
  is_active?: boolean;
}

export interface ListNotionDataSourcesParams extends PageParams {
  integration_id?: UUID;
}

export interface ListSyncRunsParams extends PageParams {
  data_source_id?: UUID;
  status?: RunStatus;
  from?: string;
  to?: string;
}

export interface ListRawNotesParams extends PageParams {
  data_source_id?: UUID;
  external_page_id?: string;
  from?: string;
  to?: string;
}

export interface ListAICallsParams extends PageParams {
  provider_config_id?: UUID;
  operation?: string;
  status?: AICallStatus;
  from?: string;
  to?: string;
}

export interface ListKnowledgePointsParams extends PageParams {
  subject_id?: UUID;
  status?: KnowledgePointStatus;
  tag?: string;
  q?: string;
}

export interface ListReviewItemsParams extends PageParams {
  current_only?: boolean;
}

export interface ListReviewBatchesParams extends PageParams {
  local_date?: DateOnly;
  status?: BatchStatus;
  subject_id?: UUID;
}

export interface ListReviewTasksParams extends PageParams {
  local_date?: DateOnly;
  status?: TaskStatus;
  subject_id?: UUID;
  overdue?: boolean;
}

export interface ListReviewHistoryParams extends PageParams {
  knowledge_point_id?: UUID;
  subject_id?: UUID;
  from?: string;
  to?: string;
  rating?: ReviewRating;
}

export interface StatisticsParams {
  from_date: DateOnly;
  to_date: DateOnly;
  subject_id?: UUID;
}

export interface ListNotificationJobsParams extends PageParams {
  task_id?: UUID;
  status?: NotificationJobStatus;
  channel_type?: NotificationChannelType;
  from?: string;
  to?: string;
}

export interface ListTemplatesParams extends PageParams {
  subject_id?: UUID;
  channel_type?: NotificationChannelType;
  template_key?: string;
  is_active?: boolean;
}
