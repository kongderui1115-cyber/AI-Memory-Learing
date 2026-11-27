# AI Learning Memory OS REST API 契约

## 当前已实现增量 · 2026-11-17

Notion端点已通过回归，包括连接与数据源GET/POST/PATCH、同步入队、失败重试、同步记录和原文查询。数据源学习状态、用户作用域和凭据变量名按运行说明配置。独立页面树支持系统内的学习状态维护。

新增已注册端点包括/ai/providers、/ai/providers/{id}、/ai/providers/{id}/readiness、/ai/calls、/ai/calls/{id}、/subjects/{id}/strategy和/chapter-jobs/{id}/retry。模型配置支持创建、读取和部分修改，删除业务待后续明确生命周期。readiness明确返回connection_tested=false。

当前OpenAPI含64个路径。在线模型连接测试、单个知识点重新生成及AI陪伴目标契约继续开发。当前完成章节worker会自动完成提取、生成卡片和初始调度。真实外部调用与费用授权独立验收。

---

## 当前运行时契约增量 · 2026-11-16

服务使用 `/api/v1`，Bearer登录会话。普通资源的user_id取自已验证会话。管理员通过专用管理端点跨用户查看，相关访问记录审计。当前正文中较早的端点登记是目标契约，实际路由以已注册代码和运行时OpenAPI为准。

核心已实现端点包括认证、`/me`、心跳及注销、学科、章节、学习记录、知识点、卡片、调度、每日批次及任务、复习历史、统计，以及 `/admin/users`、`/admin/overview`、`/admin/sessions`、`/admin/audit-events` 和指定用户知识及复习查询。写入使用Idempotency-Key或If-Match，具体要求见对应Pydantic及路由定义。

新增开发中的Notion端点位于 `app/api/notion.py`，包括连接和数据源的GET/POST/PATCH、同步入队及失败重试、同步记录与原始笔记查询。连接引用必须匹配 `MEMORY_USER_<用户UUID无连字符大写>_` 前缀。数据源增加subject_id、status_property和status_mapping，默认状态映射为未开始、进行中、已完成。

POST同步返回202与持久化运行记录。一次性worker执行实际同步，缺少运行时凭据会记录失败原因。新增Notion路由尚待运行时验收。AI配置、提取及通知的持久化业务接线继续开发，早期契约中登记的这些路径尚未全部注册。

---

> 版本 `v1` / 契约 `1.0.0`，基路径 `/api/v1`，JSON UTF-8。字段使用 `snake_case`，ID 为 UUID 字符串，时间为 UTC RFC3339 `date-time`，日期为 `YYYY-MM-DD`。

## 1. 全局约定

除 `/health/live`、`/health/ready`、`/auth/token` 外均需 `Authorization: Bearer <JWT>`。当前为单用户，仍从 token 得到 `user_id` 并强制资源隔离。创建/触发/完成类 POST 必须携带 `Idempotency-Key`（1..128 字符）；更新携带 `If-Match: "<version>"`。响应携带 `X-Request-ID`。

列表响应统一：`{"items":[T],"next_cursor":"opaque|null","has_more":bool}`；查询 `limit` 默认 20、范围 1..100，`cursor` 不透明，默认按 `created_at desc,id desc`。不使用 offset。删除均为归档/禁用，返回 204。

成功资源公共字段：`id, created_at, updated_at, version`。创建 201，查询/更新/动作 200，异步触发 202，删除 204。

错误结构：

```json
{"error":{"code":"VALIDATION_ERROR","message":"可读说明","details":[{"field":"body.name","reason":"required"}],"request_id":"uuid","retryable":false}}
```

| HTTP | 错误码 |
| --- | --- |
| 400 | `VALIDATION_ERROR`, `INVALID_STATE`, `UNSUPPORTED_STRATEGY` |
| 401/403 | `AUTH_REQUIRED`, `AUTH_INVALID`, `FORBIDDEN` |
| 404 | `RESOURCE_NOT_FOUND` |
| 409 | `CONFLICT`, `DUPLICATE_RESOURCE`, `IDEMPOTENCY_CONFLICT`, `VERSION_CONFLICT`, `TASK_ALREADY_COMPLETED` |
| 422 | `SEMANTIC_VALIDATION_ERROR` |
| 429 | `RATE_LIMITED` |
| 500/502/503/504 | `INTERNAL_ERROR`, `EXTERNAL_SERVICE_ERROR`, `CONFIG_MISSING`, `SERVICE_UNAVAILABLE`, `EXTERNAL_TIMEOUT` |

## 2. 枚举

| 名称 | 值 |
| --- | --- |
| `ScheduleStrategy` | `ebbinghaus`, `fsrs` |
| `ReviewRating` | `again`, `hard`, `good`, `easy` |
| `KnowledgePointStatus` | `draft`, `active`, `archived`, `merged` |
| `QuestionType` | `qa`, `cloze`, `multiple_choice`, `short_explanation` |
| `TaskStatus` | `pending`, `in_progress`, `completed`, `skipped`, `cancelled` |
| `BatchStatus` | `pending`, `ready`, `completed`, `cancelled` |
| `RunStatus` | `pending`, `running`, `succeeded`, `failed`, `partial`, `cancelled` |
| `NotificationChannelType` | `wecom_app`, `wechat_official_account`, `third_party_push`, `wecom_webhook`, `dingtalk_webhook`, `dingtalk_app`, `smtp` |
| `NotificationJobStatus` | `pending`, `processing`, `sent`, `failed`, `cancelled` |
| `AIProviderType` | `openai`, `deepseek`, `openai_compatible` |
| `AICallStatus` | `pending`, `running`, `succeeded`, `failed`, `cancelled` |

## 3. Schema 字典

以下未重复列出的资源公共字段见 §1。请求中 `credential_ref` 是环境变量名，不是秘密值。

| Schema | 字段 |
| --- | --- |
| `TokenRequest` | `email:EmailStr`, `password:str` |
| `TokenResponse` | `access_token:str`, `token_type:"bearer"`, `expires_in_seconds:int` |
| `SubjectWrite` | `name`, `slug`, `parent_id?`, `description?`, `language_code="zh-CN"`, `tags:list[str]`, `is_active=true` |
| `SubjectStrategyWrite` | `extraction_prompt`, `question_type_preferences:list[QuestionType]`, `glossary:dict[str,str]`, `scheduler_overrides:object`, `notification_template_overrides:object`, `prompt_version`, `is_active` |
| `NotionIntegrationWrite` | `name`, `credential_ref`, `api_version="2022-06-28"`, `is_enabled` |
| `NotionDataSourceWrite` | `integration_id`, `source_type:"database"|"page_tree"`, `external_source_id`, `name`, `sync_interval_minutes>=5`, `is_enabled` |
| `SyncRunRead` | `id,data_source_id,trigger_type,status,watermark_from,to,items_seen,items_imported,items_failed,attempt,started_at,finished_at,error_code,error_message` |
| `RawNoteRead` | `id,data_source_id,external_page_id,external_version,last_edited_time,title,content_markdown,content_hash,source_url,metadata,synced_at` |
| `KnowledgePointWrite` | `subject_id,title,body,summary,difficulty:1..5,keywords,tags,status` |
| `KnowledgePointRead` | Write 字段 + `manual_revision,merged_into_id,canonical_hash` |
| `KnowledgeMergeRequest` | `target_id`, `reason?` |
| `ReviewItemWrite` | `question_type,question,answer,explanation,summary,options?` |
| `ReviewItemRead` | Write + `knowledge_point_id,item_version,is_current,manual_revision,provider_config_id,model_name,prompt_version,ai_call_log_id` |
| `ScheduleStateRead` | `knowledge_point_id,strategy,due_at,last_reviewed_at,review_count,lapse_count,interval_index,interval_days,stability,difficulty,retrievability,target_retention,algorithm_version,parameters,last_calculation,strategy_changed_at` |
| `ScheduleSwitchRequest` | `strategy`, `parameters:object={}` |
| `ScheduleCompareResponse` | `ebbinghaus:ScheduleProjection`, `fsrs:ScheduleProjection`; projection 含 `due_at,state,explanation` |
| `DailyGenerateRequest` | `local_date`, `timezone`, `daily_limit:1..500`, `subject_id?` |
| `DailyBatchRead` | `id,local_date,timezone,subject_id,daily_limit,status,generated_at,tasks:list[DailyTaskRead]` |
| `DailyTaskRead` | `id,batch_id,knowledge_point_id,review_item_id,scheduled_due_at,priority,position,status,started_at,completed_at` |
| `ReviewCompleteRequest` | `rating`, `duration_seconds>=0`, `answer_self_assessment?`, `notes?`, `reviewed_at` |
| `ReviewCompleteResponse` | `task:DailyTaskRead`, `history:ReviewHistoryRead`, `schedule:ScheduleStateRead` |
| `ReviewHistoryRead` | `id,task_id,knowledge_point_id,review_item_id,strategy,rating,duration_seconds,answer_self_assessment,notes,reviewed_at,previous_schedule,result_schedule` |
| `StatisticsRead` | `from_date,to_date,total_tasks,completed_tasks,completion_rate,retention_trend:[{date,value}],heatmap:[{date,count}]` |
| `ChannelConfigWrite` | `name,channel_type,credential_ref,settings:object,is_enabled,is_default` |
| `TemplateWrite` | `subject_id?,channel_type,template_key,title_template,body_template,schema_variables:list[str],max_length?,is_active` |
| `NotificationJobRead` | `id,task_id,channel_config_id,template_id,status,attempt_count,max_attempts,next_attempt_at,last_error_code,last_error_message,sent_at` |
| `NotificationDeliveryRead` | `id,job_id,attempt_no,status,provider_message_id,error_code,error_message,duration_ms,attempted_at` |
| `AIProviderConfigWrite` | `name,provider,model_name,base_url?,credential_ref,temperature:0..2,timeout_seconds>0,max_retries>=0,rate_limit_per_minute?,is_enabled,is_default` |
| `AICallLogRead` | `id,provider_config_id,operation,provider,model_name,prompt_version,request_id,status,input_tokens,output_tokens,total_tokens,duration_ms,attempt_count,error_code,error_message,started_at,finished_at` |

## 4. 端点

### 平台、身份

| 方法与路径 | 参数/请求 | 响应 | 状态/说明 |
| --- | --- | --- | --- |
| `GET /health/live` | — | `{status:"ok"}` | 200，仅进程存活 |
| `GET /health/ready` | — | `{status,checks}` | 200/503；仅检查必要内部依赖，不调用未授权外部 API |
| `POST /auth/token` | `TokenRequest` | `TokenResponse` | 200/401 |
| `GET /me` | — | `UserRead` | 200 |

### 学科与数据驱动策略（FR-10）

| 方法与路径 | 参数/请求 | 响应 |
| --- | --- | --- |
| `GET /subjects` | `limit,cursor,parent_id?,is_active?` | Page[`SubjectRead`] |
| `POST /subjects` | `SubjectWrite` | `SubjectRead` |
| `GET /subjects/{subject_id}` | UUID | `SubjectRead` |
| `PATCH /subjects/{subject_id}` | partial `SubjectWrite` + If-Match | `SubjectRead` |
| `DELETE /subjects/{subject_id}` | If-Match | 204（禁用） |
| `GET /subjects/{subject_id}/strategy` | — | `SubjectStrategyRead` |
| `PUT /subjects/{subject_id}/strategy` | `SubjectStrategyWrite` + If-Match（首次可无） | `SubjectStrategyRead` |

### Notion（FR-01）

| 方法与路径 | 参数/请求 | 响应/说明 |
| --- | --- | --- |
| `GET/POST /notion/integrations` | list 参数 / `NotionIntegrationWrite` | Page / 201 resource |
| `GET/PATCH/DELETE /notion/integrations/{id}` | PATCH partial + If-Match | resource / 204 |
| `GET/POST /notion/data-sources` | `integration_id?` / `NotionDataSourceWrite` | Page / 201 resource |
| `GET/PATCH/DELETE /notion/data-sources/{id}` | PATCH partial + If-Match | resource / 204 |
| `POST /notion/data-sources/{id}/sync` | header Idempotency-Key | 202 `SyncRunRead`; 未授权 `CONFIG_MISSING` |
| `GET /notion/sync-runs` | `data_source_id?,status?,from?,to?,limit,cursor` | Page[`SyncRunRead`] |
| `GET /notion/sync-runs/{id}` | — | `SyncRunRead` |
| `GET /raw-notes` | `data_source_id?,external_page_id?,from?,to?,limit,cursor` | Page[`RawNoteRead`] |
| `GET /raw-notes/{id}` | — | `RawNoteRead` |

### AI Provider 与调用审计（FR-02）

| 方法与路径 | 参数/请求 | 响应/说明 |
| --- | --- | --- |
| `GET/POST /ai/providers` | list / `AIProviderConfigWrite` | Page / 201 resource |
| `GET/PATCH/DELETE /ai/providers/{id}` | PATCH partial + If-Match | resource / 204 |
| `POST /ai/providers/{id}/validate` | Idempotency-Key | 200 `{valid,provider,model}`；须 Key 与计费授权，否则 `CONFIG_MISSING/FORBIDDEN` |
| `GET /ai/calls` | `provider_config_id?,operation?,status?,from?,to?,limit,cursor` | Page[`AICallLogRead`] |
| `GET /ai/calls/{id}` | — | `AICallLogRead` |

### 知识点与出题（FR-03/04）

| 方法与路径 | 参数/请求 | 响应/说明 |
| --- | --- | --- |
| `GET /knowledge-points` | `subject_id?,status?,tag?,q?,limit,cursor` | Page[`KnowledgePointRead`] |
| `POST /knowledge-points` | `KnowledgePointWrite` | 201 resource（人工创建） |
| `GET/PATCH /knowledge-points/{id}` | PATCH partial + If-Match | resource；PATCH 设置 `manual_revision=true` |
| `POST /knowledge-points/{id}/activate` | Idempotency-Key | resource + 初始化 schedule |
| `POST /knowledge-points/{id}/archive` | Idempotency-Key | resource |
| `POST /knowledge-points/{id}/merge` | `KnowledgeMergeRequest`, Idempotency-Key | target resource |
| `POST /raw-notes/{id}/extract` | `{provider_config_id,subject_id?}`, Idempotency-Key | 202 `{operation_id,status}` |
| `GET /knowledge-points/{id}/review-items` | `current_only=true,limit,cursor` | Page[`ReviewItemRead`] |
| `POST /knowledge-points/{id}/review-items/generate` | `{provider_config_id,question_types,count:1..20}`, Idempotency-Key | 202 `{operation_id,status}` |
| `POST /knowledge-points/{id}/review-items` | `ReviewItemWrite` | 201 manual item |
| `PATCH /review-items/{id}` | partial `ReviewItemWrite` + If-Match | 新版本 `ReviewItemRead`，旧版保留 |

### 调度与每日任务（FR-05/06）

| 方法与路径 | 参数/请求 | 响应 |
| --- | --- | --- |
| `GET /knowledge-points/{id}/schedule` | — | `ScheduleStateRead` |
| `PUT /knowledge-points/{id}/schedule/strategy` | `ScheduleSwitchRequest` + If-Match | `ScheduleStateRead` |
| `POST /knowledge-points/{id}/schedule/compare` | `{rating?,reviewed_at?}` | `ScheduleCompareResponse`（纯计算不写库） |
| `POST /review-batches/generate` | `DailyGenerateRequest`, Idempotency-Key | 201/200 `DailyBatchRead`（同 key 重放返回原资源） |
| `GET /review-batches` | `local_date?,status?,subject_id?,limit,cursor` | Page[`DailyBatchRead`] |
| `GET /review-batches/{id}` | — | `DailyBatchRead` |
| `GET /review-tasks` | `local_date?,status?,subject_id?,overdue?,limit,cursor` | Page[`DailyTaskRead`] |
| `GET /review-tasks/{id}` | — | `DailyTaskRead` |
| `POST /review-tasks/{id}/start` | Idempotency-Key | `DailyTaskRead` |
| `POST /review-tasks/{id}/skip` | `{reason?}`, Idempotency-Key | `DailyTaskRead`；schedule due 不丢失 |

### 复习闭环与统计（FR-09）

| 方法与路径 | 参数/请求 | 响应/说明 |
| --- | --- | --- |
| `POST /review-tasks/{id}/complete` | `ReviewCompleteRequest`, Idempotency-Key | `ReviewCompleteResponse`；历史+schedule+task 单事务 |
| `GET /review-history` | `knowledge_point_id?,subject_id?,from?,to?,rating?,limit,cursor` | Page[`ReviewHistoryRead`] |
| `GET /review-history/{id}` | — | `ReviewHistoryRead`；无修改/删除端点 |
| `GET /statistics/overview` | `from_date,to_date,subject_id?` | `StatisticsRead` |

### 通知（FR-07/08）

| 方法与路径 | 参数/请求 | 响应/说明 |
| --- | --- | --- |
| `GET/POST /notification/channels` | list / `ChannelConfigWrite` | Page / 201 resource；秘密只经 credential_ref |
| `GET/PATCH/DELETE /notification/channels/{id}` | PATCH + If-Match | resource / 204 |
| `POST /notification/channels/{id}/validate` | Idempotency-Key | `{valid,channel_type}`；不会伪发送 |
| `GET/POST /notification/templates` | filters / `TemplateWrite` | Page / 201 resource |
| `GET/PATCH/DELETE /notification/templates/{id}` | PATCH + If-Match | resource / 204 |
| `POST /review-tasks/{id}/notifications` | `{channel_config_id,template_id?}`, Idempotency-Key | 202 `NotificationJobRead`；正文必须含具体知识点 |
| `GET /notification/jobs` | `task_id?,status?,channel_type?,from?,to?,limit,cursor` | Page[`NotificationJobRead`] |
| `GET /notification/jobs/{id}` | — | `NotificationJobRead` |
| `POST /notification/jobs/{id}/retry` | Idempotency-Key | 202 job；仅 failed 可重试 |
| `GET /notification/jobs/{id}/deliveries` | pagination | Page[`NotificationDeliveryRead`] |

个人微信无官方主动推送 API；`NotificationChannelType` 中四个微信方向均要求用户授权。未配置凭据返回 `CONFIG_MISSING`，不得返回 sent。

## 5. 前后端类型映射与覆盖

| OpenAPI/Python | TypeScript |
| --- | --- |
| `UUID`, `datetime`, `date`, `Decimal` | `string`（分别由 branded UUID/RFC3339/date 类型约束；Decimal 不转 JS number） |
| `Enum` | 字符串 union |
| `Optional[T]` | `T | null`；可省略请求字段另为 `?:` |
| `dict/jsonb` | `Record<string, unknown>` 或专用 interface |

前端不得手写漂移类型；由 `/openapi.json` 生成并锁定。FR-01~04 由 Notion/AI/知识端点覆盖，FR-05/06 由 schedule/batch/task 覆盖，FR-07/08 由 notification 覆盖，FR-09 由 complete/history/statistics 覆盖，FR-10 由 subjects/strategy 覆盖；FR-11/12 是部署契约，无业务 REST 端点，由 health/readiness 和跨平台运行入口验证。

## 2026-11-13 兼容性补充

`AsyncOperationRead` 为提取和出题的异步响应，包含 UUID `operation_id` 与 `RunStatus` 枚举 `status`。
`ProviderValidation` 包含 `valid: boolean`、`provider: AIProviderType`、`model: string`。
`ChannelValidation` 包含 `valid: boolean` 与 `channel_type: NotificationChannelType`。
三者已补入 Pydantic 契约模型，保持现有响应字段名称。

复习完成请求的reviewed_at必须包含时区偏移或Z，Pydantic以AwareDatetime校验。

## 桌面前端展示模型 · 2026-11-14

DesktopWorkspaceData 位于 frontend/components/desktop/preview-data.ts，描述用户、学科、任务、章节、知识解析、来源、同步记录、复习计划和统计图表的展示输入。当前 /preview 将 previewWorkspace 作为输入用于界面验收。

正式接线沿用本文件的后端端点与字段契约，由前端适配层转换为展示模型。Notion 来源信息与业务数据库的任务、历史、调度和统计分别映射。多用户和管理员的授权由后端执行，预览角色切换仅控制示例页面展示。

## 管理员跨用户查看的接线要求 · 2026-11-14

管理员可按用户查询复习完成率、逾期、复习记录、评分、下次时间以及知识库正文、解析和Notion来源。当前AdminUserSnapshot为前端展示输入，管理端点尚待实现。正式接口须校验管理员角色，按目标用户限定查询条件，并记录操作者、目标用户与访问范围。正式权限验收包含普通用户拒绝访问管理查询、管理员正确查看指定用户、跨用户切换结果归属及审计记录。

## 首次使用流程 · 2026-11-18

本轮新增注册与HttpOnly会话Cookie，继续支持既有Bearer调用。workspace接口提供首次配置进度、加密凭据保存、Notion资料库发现、邮件及模型设置、真实用户数据。写请求校验Origin，Cookie写请求携带X-Memory-Client头。秘密只接受写入，读取返回配置状态。通知测试与复习摘要采用持久化作业和受控重试。

## 引导流程暂停记录 · 2026-11-18

新增/auth/register、/workspace、/workspace/settings、/workspace/profile、/workspace/email及test、/workspace/notion/token、discover与connect、/workspace/model及onboarding/complete。注册固定user角色。网页请求使用HttpOnly Cookie、同源API与X-Memory-Client头，保留已有Bearer调用。密码和第三方秘密输入不回显。当前该增量仍处于验收中。

## 2026-11-18 运行入口验收补充

GET /api/v1/admin/users的UserAccount.email返回已保存的字符串，注册和管理员创建输入仍验证邮箱。用户列表支持q与cursor，登录记录支持cursor，页面已连接搜索与继续加载。

GET /api/v1/review-tasks/{id}/content返回task、knowledge、review_item与schedule。邮件入口使用/app?view=review&task={id}，登录及首次配置完成后回到该任务。已结束任务提供内容回看，复习写入仍由任务状态和服务端所有权控制。

会话Cookie为memory_session，HttpOnly与SameSite=Lax，生产或HTTPS启用Secure。Cookie写请求携带X-Memory-Client=web并校验Origin。Bearer调用保持兼容，秘密读取只返回配置状态。注册创建role=user，额外角色字段拒绝。


## 正式学习体验与统计接口 · UI-POLISH-01 · 2026-11-18

- GET /workspace/insights：已登录用户的只读统计，使用账号时区。days默认14，范围1–90；from_date/to_date可指定连续不超过366天的日历范围。无活动日期补零，无回忆记录时recall_rate为null。响应WorkspaceInsights包含metrics、activity、subjects、memory、scheduled与upcoming，OpenAPI有明确响应模型。
- metrics提供活跃知识/章节数、今日学习与复习秒数/次数、今日批次任务及完成数、全量待办/逾期、累计复习与活跃天数、连续天数。回忆成功率为统计区间good/easy历史数占比，不是模型预测保持率。
- activity按本地日期分摊跨午夜学习的实际秒数，DST按时间戳计算。活跃日以学习记录结束日或复习提交日计数；今日未活动时保留截至昨日的连续天数。
- memory按已调度活跃知识的实际复习次数分为0、1–2、3次以上，不代表已掌握概率。scheduled展示所选区间当前到期日期；upcoming展示今天起30天的当前到期计划，评分后变化，不预造未来任务。
- /chapters、/review-tasks、/review-history新增q参数（最长200字符），按标题在服务端搜索，继续支持既有游标和学科筛选。任务及历史列表新增knowledge_title和subject_id展示字段，均按请求者身份读取，不接受用户ID切换。
- 学科创建、手工知识草稿和分段学习记录复用现有幂等写接口。本次不改数据库模型，无新增迁移。

统计日期支持1970至9998年；非法顺序、超366天或日期溢出返回VALIDATION_ERROR。请求只查询统计期间及今日活动，避免远期日历范围扩大为从该日期至今日的全量扫描。
## 今日复习负荷 · 2026-11-19

`GET /api/v1/workspace/review-workload` 要求登录，无请求参数，只读取当前用户，返回：

| 字段 | 含义 |
| --- | --- |
| local_date, timezone | 服务端按用户时区计算的当天日期及其 IANA 时区 |
| queued | 所有待复习与进行中任务数，包含历史积压 |
| due_unqueued | 已激活且到期、当前没有未完成任务的知识点数 |
| can_enqueue | 按今日全学科批次的容量可新增任务数，排除该批次已收录的知识点，取消的批次为 0 |
| daily_limit | 已建今日全学科批次的上限，未建批次时采用服务器配置 |
| estimated_seconds, sample_size | 待办数乘以个人近 30 天有效复习时长中位数。有效时长为 1 至 3600 秒，至少 5 条才估算，样本不足返回 null |
| automatic_processing_enabled | 当前 API 进程的自动处理配置，供页面区分暂停与可手动生成 |

`GET /api/v1/review-tasks?status=open` 是列表专用过滤条件，包含 pending 和 in_progress。既有状态参数和游标契约保持兼容。主页可显示到期但未排队的数量。生成按钮复用现有 `POST /review-batches/generate`，按上面返回的日期、时区和容量提交，原有幂等处理继续生效。负荷值是快照，生成时由服务端重新计算资格。
