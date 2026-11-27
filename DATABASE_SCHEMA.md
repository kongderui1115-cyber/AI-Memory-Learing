# AI Learning Memory OS 数据库契约

## 当前已验证结构 · 2026-11-17

迁移HEAD为0004_notion_sources，27张业务表。database/schema.sql已覆盖0001至0004，并在新建验证库真实执行。Alembic结构漂移检查通过。

AIProviderConfig、AICallLog及KnowledgePointSource沿用既有表。模型调用metadata保存任务ID、请求指纹及已验证输出，公开调用日志接口仅返回既定审计字段。ChapterJob.result记录知识点ID、原文来源和AI生成标识。新增AI持久化实现无需额外DDL。

已有数据源subject_id为空时可通过PATCH补充学科并重置增量水位。原始笔记、历史与审计的应用角色追加写权限继续生效。开发库已成功备份恢复到独立新库。

---

## 当前增量模型 · 2026-11-16

基线20张表继承保留。0002增加7张业务表，总计27张业务表，另有Alembic版本表。

新增表为 `user_sessions`、`login_throttles`、`audit_events`、`idempotency_records`、`chapters`、`study_sessions`、`chapter_jobs`。账号增加角色及资源版本，知识点增加章节关联，每日批次增加版本。租户关联通过(user_id,关联id)复合外键校验双方所有者。

0003增加 `daily_review_tasks.skip_reason`。0004增加数据源学科、学习状态属性、选项映射、分页期间的候选水位，并允许 `data_source` 来源类型。0004已应用到专用开发库和测试库，新增业务仍待回归。

迁移入口位于 `backend/alembic/versions`，当前HEAD为 `0004_notion_sources`。`database/schema.sql`已在新空库实测到0003，尚待重新导出0004。SQL仅用于全新数据库，既有数据库升级应通过Alembic执行。

数据库秘密位于忽略版本控制的本地环境文件。原始笔记、复习历史、安全审计对应用角色采用追加写权限。

---

> 版本 1.0.0。PostgreSQL 为唯一目标数据库。所有 `id` 为 `uuid`（默认 `gen_random_uuid()`），所有时间为 `timestamptz` UTC；未特别说明的 `created_at/updated_at` 均为非空、默认 `now()`。外键默认 `RESTRICT`，显式标注除外。

## 1. 通用约定

- 业务表均含 `user_id uuid NOT NULL → users.id`；单用户阶段也不得省略。
- 可编辑资源采用 `version int NOT NULL DEFAULT 1` 乐观锁；API 更新时传 `If-Match`。
- `jsonb` 默认 `{}`/`[]` 并加结构校验；秘密不得入库，只保存环境变量名 `credential_ref`。
- 历史/调用/投递表追加写，不提供 UPDATE/DELETE 业务端点。软删除使用状态或 `archived_at`。

## 2. 表定义

下表中 `PK/FK/UQ/CK` 分别表示主键、外键、唯一和检查约束。

### 身份与学科

| 表 | 字段（类型；约束/默认） | 索引 |
| --- | --- | --- |
| `users` | `id uuid PK`; `email citext NOT NULL UQ`; `display_name varchar(120) NOT NULL`; `password_hash text NOT NULL`; `timezone varchar(64) NOT NULL DEFAULT 'Asia/Shanghai'`; `is_active bool NOT NULL DEFAULT true`; `created_at`, `updated_at` | UQ email；`is_active` |
| `subjects` | `id`; `user_id FK`; `parent_id uuid FK subjects NULL`; `slug varchar(80) NOT NULL`; `name varchar(120) NOT NULL`; `description text NULL`; `language_code varchar(16) NOT NULL DEFAULT 'zh-CN'`; `tags jsonb NOT NULL DEFAULT '[]'`; `is_active bool DEFAULT true`; `version`; timestamps | UQ `(user_id,slug)`；`(user_id,parent_id)`；GIN tags |
| `subject_strategies` | `id`; `user_id FK`; `subject_id FK subjects CASCADE`; `extraction_prompt text NOT NULL`; `question_type_preferences jsonb DEFAULT '[]'`; `glossary jsonb DEFAULT '{}'`; `scheduler_overrides jsonb DEFAULT '{}'`; `notification_template_overrides jsonb DEFAULT '{}'`; `prompt_version varchar(40) NOT NULL`; `is_active bool DEFAULT true`; `version`; timestamps | UQ partial `(subject_id) WHERE is_active`; `(user_id,subject_id)` |

### Notion 同步与原文

| 表 | 字段（类型；约束/默认） | 索引 |
| --- | --- | --- |
| `notion_integrations` | `id`; `user_id FK`; `name`; `credential_ref varchar(160) NOT NULL`; `api_version varchar(20) DEFAULT '2022-06-28'`; `is_enabled bool DEFAULT true`; `last_validated_at timestamptz NULL`; `version`; timestamps | UQ `(user_id,name)` |
| `notion_data_sources` | `id`; `user_id`; `integration_id FK notion_integrations`; `source_type varchar(20) CK IN ('database','page_tree')`; `external_source_id varchar(128)`; `name`; `sync_interval_minutes int CK >=5`; `is_enabled`; `last_edited_watermark timestamptz NULL`; `last_cursor text NULL`; `next_sync_at timestamptz NULL`; `version`; timestamps | UQ `(integration_id,external_source_id)`；`(is_enabled,next_sync_at)` |
| `sync_runs` | `id`; `user_id`; `data_source_id FK`; `trigger_type varchar(20) CK IN ('manual','scheduled')`; `status varchar(20) CK IN ('pending','running','succeeded','failed','partial','cancelled')`; `idempotency_key varchar(128) NOT NULL`; `watermark_from/to timestamptz NULL`; `cursor_from/to text NULL`; `items_seen/imported/failed int DEFAULT 0`; `attempt int DEFAULT 1`; `started_at/finished_at/next_retry_at timestamptz NULL`; `error_code/error_message text NULL`; `created_at` | UQ `(user_id,idempotency_key)`；`(data_source_id,created_at DESC)`；`(status,next_retry_at)` |
| `raw_notes` | `id`; `user_id`; `data_source_id FK`; `sync_run_id FK`; `external_page_id varchar(128)`; `external_version varchar(128)`; `last_edited_time timestamptz`; `title text`; `content_markdown text`; `content_hash char(64)`; `source_url text`; `metadata jsonb DEFAULT '{}'`; `synced_at timestamptz DEFAULT now()`; `created_at` | UQ `(data_source_id,external_page_id,external_version)`；`(user_id,last_edited_time)`；`content_hash` |

### 知识与生成内容

| 表 | 字段（类型；约束/默认） | 索引 |
| --- | --- | --- |
| `knowledge_points` | `id`; `user_id`; `subject_id FK`; `title varchar(300)`; `body text`; `summary text`; `difficulty smallint CK 1..5`; `keywords jsonb DEFAULT '[]'`; `tags jsonb DEFAULT '[]'`; `status varchar(20) CK IN ('draft','active','archived','merged')`; `merged_into_id uuid FK self NULL`; `canonical_hash char(64)`; `manual_revision bool DEFAULT false`; `source_generated_at timestamptz NULL`; `version`; timestamps; `archived_at NULL` | UQ partial `(user_id,canonical_hash) WHERE status!='merged'`; `(user_id,subject_id,status)`；GIN keywords/tags |
| `knowledge_point_sources` | `id`; `user_id`; `knowledge_point_id FK CASCADE`; `raw_note_id FK`; `source_excerpt text NULL`; `created_at` | UQ `(knowledge_point_id,raw_note_id)`；`raw_note_id` |
| `review_items` | `id`; `user_id`; `knowledge_point_id FK CASCADE`; `question_type varchar(24) CK IN ('qa','cloze','multiple_choice','short_explanation')`; `question text`; `answer text`; `explanation text`; `summary text`; `options jsonb NULL`; `item_version int >=1`; `is_current bool DEFAULT true`; `manual_revision bool DEFAULT false`; `provider_config_id uuid FK ai_provider_configs NULL`; `model_name`; `prompt_version`; `ai_call_log_id uuid FK ai_call_logs NULL`; timestamps | UQ `(knowledge_point_id,question_type,item_version)`；partial `(knowledge_point_id,is_current)`；`user_id` |

### 调度、任务与历史

| 表 | 字段（类型；约束/默认） | 索引 |
| --- | --- | --- |
| `schedule_states` | `id`; `user_id`; `knowledge_point_id FK UQ`; `strategy varchar(20) CK IN ('ebbinghaus','fsrs')`; `state_version int DEFAULT 1`; `due_at timestamptz`; `last_reviewed_at NULL`; `review_count int DEFAULT 0`; `lapse_count int DEFAULT 0`; `interval_index int DEFAULT 0`; `interval_days numeric(10,3) NULL`; `stability numeric(12,6) NULL`; `difficulty numeric(8,6) NULL`; `retrievability numeric(8,6) NULL`; `target_retention numeric(5,4) NULL`; `algorithm_version varchar(40)`; `parameters jsonb`; `last_calculation jsonb`; `strategy_changed_at`; timestamps | `(user_id,due_at)`；`(strategy,due_at)` |
| `daily_review_batches` | `id`; `user_id`; `local_date date`; `timezone varchar(64)`; `subject_id uuid NULL`; `daily_limit int`; `status varchar(20) CK IN ('pending','ready','completed','cancelled')`; `idempotency_key varchar(128)`; `generated_at`; timestamps | UQ `(user_id,idempotency_key)`；UQ `(user_id,local_date,subject_id)` NULLS NOT DISTINCT |
| `daily_review_tasks` | `id`; `user_id`; `batch_id FK`; `knowledge_point_id FK`; `review_item_id FK NULL`; `scheduled_due_at timestamptz`; `priority int DEFAULT 0`; `status varchar(20) CK IN ('pending','in_progress','completed','skipped','cancelled')`; `position int`; `started_at/completed_at timestamptz NULL`; `version`; timestamps | UQ `(batch_id,knowledge_point_id)`；`(user_id,status,scheduled_due_at)`；`batch_id,position` |
| `review_history` | `id`; `user_id`; `task_id FK UQ`; `knowledge_point_id FK`; `review_item_id FK NULL`; `strategy`; `rating varchar(16) CK IN ('again','hard','good','easy')`; `duration_seconds int CK >=0`; `answer_self_assessment text NULL`; `notes text NULL`; `reviewed_at timestamptz`; `previous_schedule jsonb`; `result_schedule jsonb`; `idempotency_key varchar(128)`; `created_at` | UQ `(user_id,idempotency_key)`；`(user_id,reviewed_at DESC)`；`(knowledge_point_id,reviewed_at DESC)` |

### 通知

| 表 | 字段（类型；约束/默认） | 索引 |
| --- | --- | --- |
| `notification_channel_configs` | `id`; `user_id`; `name`; `channel_type varchar(40)`（枚举见 API）; `credential_ref varchar(160)`; `settings jsonb`（仅非秘密）; `is_enabled`; `is_default`; `version`; timestamps | UQ `(user_id,name)`；partial UQ `(user_id) WHERE is_default`; `(user_id,channel_type,is_enabled)` |
| `notification_templates` | `id`; `user_id`; `subject_id FK NULL`; `channel_type`; `template_key varchar(80)`; `title_template text`; `body_template text`; `schema_variables jsonb`; `max_length int NULL`; `is_active`; `version`; timestamps | UQ `(user_id,subject_id,channel_type,template_key,version)`；active lookup |
| `notification_jobs` | `id`; `user_id`; `task_id FK`; `channel_config_id FK`; `template_id FK`; `status varchar(20) CK IN ('pending','processing','sent','failed','cancelled')`; `idempotency_key`; `rendered_title/body text`; `attempt_count int DEFAULT 0`; `max_attempts int`; `next_attempt_at`; `last_error_code/message`; `sent_at`; timestamps | UQ `(user_id,idempotency_key)`；`(status,next_attempt_at)`；`task_id` |
| `notification_deliveries` | `id`; `user_id`; `job_id FK`; `attempt_no int`; `status varchar(20) CK IN ('sending','sent','failed')`; `provider_message_id`; `request_metadata jsonb`; `response_metadata jsonb`（脱敏）; `error_code/message`; `duration_ms int`; `attempted_at`; `created_at` | UQ `(job_id,attempt_no)`；`(user_id,attempted_at DESC)` |

### AI 配置与审计

| 表 | 字段（类型；约束/默认） | 索引 |
| --- | --- | --- |
| `ai_provider_configs` | `id`; `user_id`; `name`; `provider varchar(32) CK IN ('openai','deepseek','openai_compatible')`; `model_name`; `base_url NULL`; `credential_ref`; `temperature numeric(3,2) CK 0..2`; `timeout_seconds int >0`; `max_retries int >=0`; `rate_limit_per_minute int NULL`; `is_enabled`; `is_default`; `version`; timestamps | UQ `(user_id,name)`；partial UQ `(user_id) WHERE is_default` |
| `ai_call_logs` | `id`; `user_id`; `provider_config_id FK`; `operation varchar(40)`; `provider`; `model_name`; `prompt_version`; `request_id uuid`; `status varchar(20) CK IN ('pending','running','succeeded','failed','cancelled')`; `input_tokens/output_tokens/total_tokens int NULL`; `duration_ms int NULL`; `attempt_count int DEFAULT 1`; `error_code/message NULL`; `started_at`; `finished_at NULL`; `metadata jsonb`（不含 prompt 原文/密钥）; `created_at` | `(user_id,created_at DESC)`；`(status,created_at)`；`request_id` |

## 3. 关系与生命周期

`user → subjects → knowledge_points → review_items/schedule_state → daily tasks → review_history`；`notion integration → data sources → sync runs/raw notes → knowledge_point_sources`；task 通过 notification job 产生多次 delivery；AI 生成实体引用 call log。

- 知识点：`draft → active → archived`；`draft|active → merged`，merged 必须设置 `merged_into_id`，终态只读。
- 同步：`pending → running → succeeded|partial|failed|cancelled`。
- 每日任务：`pending → in_progress → completed`；`pending|in_progress → skipped|cancelled`。完成不可逆。
- 通知：`pending → processing → sent`；失败可回 `pending` 重试，耗尽后 `failed`；每次尝试追加 delivery。

## 4. 幂等与事务

- 同步请求：客户端 `Idempotency-Key` + 数据源；页面版本 UQ 防重复原文，知识点 canonical hash/来源关联防重复提取。
- 每日生成：key=`user:local_date:subject-or-all:policy-hash`；批次和任务双重 UQ。逾期 schedule 仍参与次日查询。
- 复习完成：key 绑定用户和请求；事务以 `SELECT ... FOR UPDATE` 锁 task 与 schedule，校验任务未完成，计算纯函数，依次 INSERT history、UPDATE schedule、UPDATE task；任一步失败全部回滚。历史 UQ task 和 idempotency 双保险。通知在事务提交后由 outbox/job 异步处理。
- 外部调用不包在数据库长事务内；先落运行/任务状态，调用后短事务更新。水位仅在该批次持久化成功后推进。

## 5. 迁移与演进

Alembic revision 只前进、不改已发布 revision；生产先 expand（可空字段/新表）再迁数据、切代码、最后 contract。枚举以数据库 `varchar+CHECK` 管理，新增值需同步文档、Pydantic、前端生成类型和迁移。破坏性变化升 API/契约主版本。迁移必须在独立已授权 PostgreSQL 验证；当前未知 5432 实例禁止连接，迁移执行尚未进行。

## 引导流程暂停记录 · 2026-11-18

0005_guided_setup已在独立开发与测试库应用，新增workspace_profiles和user_secrets，总计29张业务表。notification_jobs增加purpose、locked_until，task_id允许空值。源码中的完整SQL当前仍对应0004，下一次恢复需要导出0005与空库检查。

## 0005交付验收 · 2026-11-18

当前29张业务表及alembic_version已通过schema.sql空库执行和Alembic check。新增workspace_profiles与user_secrets，notification_jobs包含purpose、locked_until并支持摘要任务为空的task_id。开发库备份已恢复到独立新库，版本、用户、凭据数量及表数一致。

管理员读取兼容历史邮箱字符串，无需修改用户数据。邮件中断恢复、发送尝试与上限通过现有notification_jobs/notification_deliveries完成，本轮无需新增迁移。数据库密文依赖配套服务器SECRET_KEY，恢复流程须保留该秘密。
