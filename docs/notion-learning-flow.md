# 自动知识摄取与复习契约 · 2026-11-20

## 基线与边界

现有 Notion 连接、用户密钥、SyncRun、RawNote、章节处理任务、Provider、KnowledgePoint、ReviewItem、ScheduleState、每日批次和 SMTP 队列继续作为业务主体。同步保存原文与游标，章节完成后独立入队，模型错误由章节任务记录。已有用户可继续编辑知识点，复习历史保持追加写。

本地运行保持 BACKGROUND_TASKS_ENABLED=false。开发及迁移验证使用专用 PostgreSQL 和测试传输。Notion 官方 Webhook 注册需要可公网访问的 HTTPS 回调和订阅验证，当前工作流以用户级增量轮询及有界生命周期核查运行。公开订阅、验证令牌及实收事件留待外部部署授权。[Notion Webhook 文档](https://developers.notion.com/reference/webhooks)

## 数据模型

- Alembic 0006_notion_lifecycle 增加 chapters.notion_archived_at（可空、带时区）、notion_data_sources.lifecycle_cursor（可空、字符串）和 workspace_profiles.review_preferences（JSONB，默认空对象）。学习完成状态与 Notion 内容归档各自保存。已有章节和滚动游标从 null 开始。
- RawNote 继续追加写。再次同步同一版本走现有去重。来源生命周期由显式返回状态判定，权限不足或查无内容时保留现有知识及历史。
- ChapterJob.result.analysis 为附加结构化结果。笔记摘要和不足说明保存在任务结果。知识列表用持久知识点 ID 并关联 RawNote。引文偏移使用 Unicode 代码点，起始包含、结束不含。
- 延期关闭当期任务为 skipped，并更新该知识点 ScheduleState.due_at；复习评分、算法参数及历史沿用已有契约。

## API

|入口|契约|
|---|---|
|GET /api/v1/workspace/processing|当前账号的近期 Notion 同步、章节提取状态和自动处理配置。返回受控状态、完成/重试时间、源/章节 ID 及已完成分析摘要，不返回令牌和模型传输原文。|
|GET /api/v1/chapters/{id}|追加 notion_archived_at，保留既有状态枚举。|
|POST /api/v1/chapters/{id}/reanalyze|所有者，Idempotency-Key。返回 202 与章节任务。已归档/未完成的章节拒绝入队。|
|PUT /api/v1/workspace/memory-preferences|所有者，If-Match。保存新知识的算法、固定间隔、学习目标和偏好，保留既有计划。学科策略优先。|
|POST /api/v1/review-tasks/{id}/defer|所有者，Idempotency-Key。body.days 为 1–30。依据账号时区推迟到相应当地日期，保持更晚的既有到期时间。返回 DailyTaskRead。|
|GET /api/v1/admin/analytics|沿用管理员与日期范围规则。追加模型调用/失败/Token 样本日序列、模型与操作分布，以及现有任务状态队列和工作流计数。|
|GET /api/v1/ai/providers/{id}/readiness|沿用现有端点，按当前账户配置和授权决定就绪状态，仅读取本地。|

缺少配置的章节任务沿用 blocked/CONFIG_MISSING 存储值，学习者显示等待模型配置或授权。SMTP 的 sent 代表邮件服务器接受。适配器可发送不同渠道 payload；最终送达需各渠道的独立回执。

每次完整同步轮转复核最多十个已知页面，不根据查询缺席推断删除。旧游标被拒绝时从已提交水位重启；429/529 的重试时间可使用 Retry-After，终止失败尊重该资料库的同步间隔。可读取的显式归档/回收站状态会暂停该来源的抽取并保留旧知识与复习历史；恢复时只重排相符的当前内容任务。遇到权限失效、不可访问页面或已永久删除后返回 404 时保留本地记录，等待明确状态或授权后的 Webhook 事件。

## 本地配置

在学习者站设置中选学科，保存 Notion 连接并共享资料库；模型接口可留空。配置真实模型时，通过现有模型设置保存供应商、模型名和密钥，再明确批准计费。无可用凭据时章节原文和待处理任务仍可查看。公共 Webhook 以及后台调度启用需完成授权和环境验收。

正式部署前对两站分别构建，使用有备份的目标环境验证 Alembic 0006。数据库配置沿用现有加密凭据和服务端密钥。模型地址必须在部署者的 AI_ALLOWED_BASE_URLS 中；真实凭据应通过学习者配置保存，测试替身只注册在隔离验收脚本。生产后台默认沿用用户确认的暂停配置。

## 当前交付边界

|状态|范围|
|---|---|
|已写入现有工作树|Notion 轮询、同步诊断与生命周期、独立抽取与缺配置等待、结构化原文证据、人工修订、重新分析、两套调度与延期、SMTP 正文、管理员数据库统计。|
|适配器层已实现|沿用企微、公众号、钉钉和 SMTP 端口并加入 Bark。当前学习者的持久化投递链路接线为 SMTP，Bark/企微/公众号/钉钉的持久队列和渠道设置仍待接线。|
|等待 API 配置|真实模型输入、实际输出质量、用量账单和收费验证。统计使用记录的 Token，缺样本留空；费用暂无计量。|
|等待授权|真实 Notion 小范围同步与公开 HTTPS Webhook 注册、真实各渠道发送及服务商/设备实际回执、Windows 正式数据库迁移与部署。|
|尚未实现|可操作的渠道原生按钮回调、逐卡个性化预测曲线、公开 Webhook 事件接线。单次 404 无法区分永久删除与访问权限变化。当前提醒使用已有受认证的学习系统链接。|

## 测试结果和文件清单

隔离 PostgreSQL 0005 → 0006 与 Alembic 结构检查通过。Python 124 后端 + 163 AI + 72 通知通过。两站通过 Next.js 构建和 Edge 验收，包含使用替身传输的 Notion → 原文定位 → 卡片 → 评分及管理统计，以及学科分组、延期和偏好保存。完整结果见 TEST_REPORT.md。

变更文件

- `backend/app/models/notion.py`
- `backend/app/models/runtime.py`
- `backend/app/contracts/core.py`
- `backend/app/api/learning.py`
- `backend/app/services/learning.py`
- `backend/app/api/workspace.py`
- `backend/app/services/workspace.py`
- `backend/app/contracts/admin_analytics.py`
- `backend/app/services/admin_analytics.py`
- `database/schema.sql`
- `frontend/lib/workspace.ts`
- `frontend/components/portal/LearningExperience.tsx`
- `frontend/components/portal/Workspace.tsx`
- `apps/admin-web/lib/client.ts`
- `apps/admin-web/lib/types.ts`
- `apps/admin-web/components/dashboard/Dashboard.tsx`
- `backend/tests_backend/test_core_api.py`
- `backend/tests_backend/test_admin_analytics.py`
- `backend/alembic/versions/0006_notion_lifecycle.py`
- `backend/app/models/workspace.py`
- `backend/app/contracts/workspace.py`
- `backend/app/contracts/processing.py`
- `docs/notion-learning-flow.md`
- `frontend/components/portal/MemoryPreferences.tsx`
- `backend/app/integrations/notion/client.py`
- `backend/app/integrations/notion/models.py`
- `backend/app/integrations/notion/runtime.py`
- `backend/app/services/notion.py`
- `backend/tests_backend/test_notion_runtime.py`
- `backend/app/ai/grounding.py`
- `backend/app/ai/extraction.py`
- `backend/app/ai/prompts.py`
- `backend/app/services/ai_runtime.py`
- `backend/app/api/ai_runtime.py`
- `backend/tests_backend/test_ai_runtime.py`
- `backend/app/services/mail.py`
- `backend/app/notifications/links.py`
- `backend/app/notifications/ports.py`
- `backend/app/notifications/worker.py`
- `backend/app/notifications/channels/bark.py`
- `backend/app/notifications/channels/wechat.py`
- `backend/tests_notif/test_channels.py`
- `backend/tests_backend/test_guided_setup.py`
- `frontend/tests/portal.e2e.cjs`
- `frontend/tests/learning-experience.e2e.cjs`
- `apps/admin-web/tests/console.e2e.cjs`
- `PROJECT_STATUS.md`、`TASK_BOARD.md`、`TEST_REPORT.md`、`DECISIONS.md`、`CHANGELOG.md`
