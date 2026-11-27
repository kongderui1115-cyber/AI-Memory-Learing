# AI Learning Memory OS 架构设计

## 当前运行时接线 · 2026-11-17

Notion API和AI配置API已注册到/api/v1。同步与章节任务使用PostgreSQL事务级advisory lock协调同一资源的worker执行。数据源游标、原文版本、章节和完成队列在事务中更新。

AI调用采用既有Provider端口和协议适配器。配置及调用日志落库，HTTP执行在独立线程运行。已校验的调用结果先保存，知识、来源、卡片、调度及章节任务随后原子提交。重试按任务及请求指纹复用成功结果。外部执行与本地记录的中断边界见运行说明。

知识处理继续采用通用学科策略，模型选择、提示词、题型及调度覆盖由数据驱动。当前已接通的单次worker为sync-notion、extract-chapters和generate-daily-tasks。通知持久化作业接线、AI陪伴及正式前端数据适配继续开发。

---

## 当前后端实现补充 · 2026-11-16

后端采用模块化单体，API层验证会话与请求，服务层控制用户作用域、事务、幂等和资源版本，领域层执行记忆算法，PostgreSQL保存长期状态。管理员访问使用独立路由与审计。

同一套业务代码通过环境变量在Windows和Linux运行。Windows入口显式配置Selector事件循环以支持psycopg异步连接。官方FSRS SDK封装在 `app/domain/memory.py`，按算法版本分派新旧状态。

Notion运行时服务正在接线，按数据源使用PostgreSQL事务级advisory lock串行同步。原文版本追加保存，分页完成前保持增量查询下界，水位及数据一并提交。外部传输使用可注入端口，集成测试可隔离HTTP，数据库事务使用真实PostgreSQL。新增同步代码尚待验收。

章节提取队列已经持久化，实际AI消费worker仍待接线。通知适配器已继承，数据库队列接线仍待完成。桌面preview界面仍使用明确标注的示例数据，正式前端接线是后续任务。

---

> 契约版本：1.0.0 ｜ 状态：冻结基线 ｜ 日期：2026-11-13 ｜ Owner：Chief Architect

## 1. 目标、非目标与原则

目标是把 Notion 笔记可靠同步为可追溯原文，经可替换 LLM 提取知识点并生成题目，以固定间隔或 FSRS 调度每日复习，通过授权渠道推送具体内容，完成后原子更新历史与下次到期时间。产品目标已更新为多用户与管理员，每位用户的业务记录按 `user_id` 隔离。既有鉴权与数据库基线继续继承，多用户隔离和管理员权限仍需完整实现及验收。

非目标：不接入个人微信逆向协议；不在未授权时调用外部 API 或产生费用；不以 SQLite 替代 PostgreSQL；不把 Docker/WSL 作为 Windows 运行前提；不在本阶段实现业务代码或伪造外部服务结果。

原则：PostgreSQL 为唯一生产数据库；UTC 带时区存储；UUID 主键；配置环境变量化；领域纯逻辑与 I/O 隔离；所有外部动作可审计、可重试、幂等；OpenAPI/Pydantic 为后端运行契约，TypeScript 类型由 OpenAPI 生成。

## 2. 技术选型

| 层 | 选型 | 理由 |
| --- | --- | --- |
| API | Python 3.13 + FastAPI + Pydantic v2 | 类型驱动 OpenAPI、异步 I/O、输入校验清晰 |
| 数据 | PostgreSQL 16+ | 事务、行锁、JSONB、时区、约束与迁移能力满足一致性要求；禁止换 SQLite |
| ORM/迁移 | SQLAlchemy 2 async + Alembic + psycopg 3 | 显式事务、跨平台、迁移可审计 |
| 外部 HTTP | httpx + tenacity | async、超时、退避重试 |
| 后台调度 | APScheduler 进程入口；系统调度器负责守护 | Windows 任务计划与 Linux systemd/cron 可替换，不绑定 OS |
| Web | Next.js 15 + React 19 + TypeScript 5 | 电脑端中文 UI、手机推送阅读页、服务端/客户端组合、契约类型化 |
| 测试/质量 | pytest、pytest-asyncio、coverage、ruff、mypy；前端后续 Vitest | 算法纯函数和契约可重复验证 |

## 3. 分层、模块边界与依赖方向

`API → application use cases → domain → ports`；基础设施适配器实现 ports，领域层不得依赖 FastAPI、SQLAlchemy、Notion 或具体 LLM/通知 SDK。

| 模块 | 唯一职责 | 禁止越界 |
| --- | --- | --- |
| `app/contracts` | 枚举、请求/响应与错误模型 | 不含 ORM/业务实现；冻结后仅由 Chief Architect 变更 |
| `app/api` | 路由、鉴权、HTTP 映射 | 不直接写 SQL/调用外部 API |
| `app/domain` | 调度纯函数、实体规则、端口接口 | 不依赖框架与适配器 |
| `app/services` | 用例、事务边界、幂等编排 | 不持有外部密钥 |
| `app/models`, `repositories` | ORM 与持久化 | 不实现 HTTP/LLM 渲染 |
| `app/ai` | Provider 抽象、提示词、结构化输出 | 不负责 Notion 拉取或通知 |
| `app/integrations/notion` | Notion 数据源与同步适配器 | 不生成知识点业务规则 |
| `app/notifications` | 渠道插件、模板、重试与历史 | 不改变复习调度 |
| `frontend` | 电脑端中文 UI、手机推送阅读页与类型化 API client | 不复制服务端调度规则 |

## 4. 目标目录与所有权

```text
/
├─ ARCHITECTURE.md / DATABASE_SCHEMA.md / API_CONTRACTS.md  # Chief Architect
├─ backend/
│  ├─ pyproject.toml                                         # 基线由 Architect；后续 Backend/DevOps 协调
│  ├─ alembic/                                               # Backend
│  ├─ app/
│  │  ├─ contracts/                                         # Chief Architect（共享只读）
│  │  ├─ api/ domain/ services/ models/ repositories/       # Backend
│  │  ├─ ai/ integrations/notion/                           # AI Integration
│  │  └─ notifications/                                     # Notification
│  └─ tests/                                                # QA
├─ frontend/                                                # Frontend
├─ scripts/ infra/ .env.example DEPLOYMENT.md               # DevOps
└─ tests/ TEST_REPORT.md                                    # QA
```

对 `AGENTS.md` §3 的唯一补充：`backend/app/contracts/**` 在契约冻结后归 Chief Architect 独占；`backend/pyproject.toml` 的本次基线由 Chief Architect 创建，后续依赖变更由 Backend 提案、DevOps 落盘并经 Architect 审核。这样避免六个 worktree 同时改共享契约，其余矩阵不变。

## 5. 核心数据流

1. 定时器或手动请求创建 `sync_runs`，Notion 适配器从数据源水位按 `last_edited_time` 增量读取。
2. 以 `(data_source_id, external_page_id, external_version)` 幂等写 `raw_notes`，成功后推进水位，失败保留错误与重试时间。
3. AI 用例读取原文与学科策略，通过 `AIProvider` 返回结构化结果；`ai_call_logs` 记录模型、prompt 版本、token、耗时和错误。
4. 去重/合并服务创建或关联 `knowledge_points`；人工字段通过 `manual_revision` 与内容版本保护，自动同步不得覆盖。
5. 出题服务写入版本化 `review_items`（问题、答案、解析、摘要和生成来源）。
6. 激活知识点时建立独立 `schedule_states`；每日生成器按 due、逾期程度、优先级、学科过滤，幂等写 `daily_review_tasks`，遗漏项保持 due 并次日滚入。
7. 通知编排渲染具体知识点内容，创建 `notification_jobs`，渠道插件发送并追加 `notification_deliveries`。
8. 用户完成任务后，单事务写追加式 `review_history`、更新任务、计算并更新调度状态与新 due；提交后才返回结果。

## 6. 两套调度策略

每个知识点仅有一个当前 `schedule_state.strategy`，可在 `ebbinghaus` 与 `fsrs` 间切换；策略参数快照和 `last_calculation` JSONB 保存“为什么今天复习”。学科策略提供默认覆盖，知识点状态保存最终生效快照，防止配置变化篡改历史。

- 固定间隔：`intervals_days`（默认 `[1,2,4,7,15,30]`）按成功复习次数推进；`again` 重置到首间隔，其余评分按规则推进。超出序列沿用末项。
- FSRS：保存 `stability`、`difficulty`、`retrievability`、`reps`、`lapses` 与算法参数版本；评分 `again/hard/good/easy` 作为确定性输入，以目标留存率计算 due。
- 切换：API 必须携带策略和可选参数；服务记录 `strategy_changed_at`，用当前记忆状态初始化目标策略，但不改历史。比较端点以同一状态纯计算两种结果，不写库。

## 7. 可替换扩展点

`AIProvider.complete_structured()` 的实现包括 OpenAI、DeepSeek、OpenAI-compatible；业务只依赖端口。Provider 配置表只存非敏感参数和环境变量名，Key 不入库；缺 Key 或 `AI_BILLING_APPROVED!=true` 返回明确错误。

`NotificationChannel.send()` 由注册表按 `channel_type` 解析。`WechatChannel` 是合规适配器族：`wecom_app`、`wechat_official_account`、`third_party_push`、`wecom_webhook`。个人微信没有官方主动推送 API，绝不实现逆向协议或“假成功”。另有 `dingtalk_webhook`、`dingtalk_app`、`smtp`，新增插件不修改核心编排。

学科及 `subject_strategies` 全部数据驱动，保存抽取 prompt、题型偏好、术语、调度覆盖和通知模板覆盖；层级用 `parent_id`，Unicode 原生支持。新增学科经 API 配置即可贯穿抽取、出题、调度与通知，无需部署代码。

## 8. 安全、授权与可观测性

- 单用户阶段仍使用 Bearer JWT；初始管理员由部署配置创建，密码只存 Argon2 哈希。所有资源按 `user_id` 过滤。
- 外部密钥仅在环境变量/本机密钥文件；数据库只存 `credential_ref`，日志统一脱敏。输入长度、URL、枚举、JSON schema 均校验。
- 外部调用有 connect/read 总超时、指数退避、速率限制和幂等键；只重试可重试错误。
- 结构化 JSON 日志含 `request_id`、`user_id`、`operation`、`duration_ms`；AI、同步、通知另有持久化审计表。健康检查区分 liveness/readiness，但不得探测未授权外部服务。
- Notion、LLM、通知、未知 PostgreSQL 均维持未连接，直到用户明确授权；未配置时返回 `CONFIG_MISSING`，不降级为假数据。

## 9. Windows 运行与 Linux 迁移

同一代码使用 `pathlib`、环境变量、stdout 日志和存储端口，无注册表/COM/硬编码盘符。Windows 用 PowerShell 启动 uvicorn、Next.js 和 worker，任务计划程序只触发通用 CLI。Linux 以同样入口配 systemd service/timer 或 cron；反向代理/TLS、对象存储和可选容器是部署适配层。PostgreSQL/Alembic 迁移保持一致。当前 Linux、备份恢复、服务启动均未演练，必须在 `DEPLOYMENT.md` 如实记录。

## 10. FR-01~12 承载矩阵

| 需求 | 主模块 | 协作模块/验证重点 |
| --- | --- | --- |
| FR-01 | `integrations/notion` + sync service | raw notes、watermark、幂等与失败日志 |
| FR-02 | `ai/providers` | 配置授权、调用日志、结构化输出 |
| FR-03 | AI extraction + Backend knowledge service | 去重、合并、人工修订保护 |
| FR-04 | AI generation + review item repository | 多题型、版本、来源元数据 |
| FR-05 | Backend domain scheduler | 两套纯函数、切换/比较、依据快照 |
| FR-06 | Backend daily-task service | 上限、优先级、筛选、补漏、幂等 |
| FR-07 | `notifications/wechat` | 授权适配器、具体内容、无个人微信逆向 API |
| FR-08 | notifications registry/template/worker | 企业微信、钉钉、SMTP、重试历史 |
| FR-09 | review transaction + Frontend | 历史追加写、任务/调度原子一致、统计 |
| FR-10 | subjects/strategies + AI/notification consumers | 数据驱动、层级、多语言、全链路 |
| FR-11 | DevOps PowerShell/worker | Windows 原生、无 Docker/WSL 前提 |
| FR-12 | cross-platform ports + DevOps | PostgreSQL、systemd/cron、迁移/备份清单 |

## 11. 并行开发与集成

契约文档和 `app/contracts` 先冻结。六个专项 Agent 遵循一人一 worktree/分支和文件所有权；发现字段、枚举或路径缺失立即停止并提交契约变更请求。Chief Architect 以 `git merge --no-ff` 顺序合并，先契约检查，再静态检查/单测/迁移审查，最后真实启动；冲突由 Architect 裁决，PM 更新治理状态。契约破坏性变更必须升主版本并提供迁移期，1.x 仅允许向后兼容新增。

## 桌面前端展示层 · 2026-11-14

继承 Next.js 15、React 19 和 TypeScript，业务后端继续使用 Python/FastAPI 与 PostgreSQL。此轮完成电脑端页面验收，手机适配覆盖 /preview/push。

- app/preview 提供独立、可识别的示例页面入口。应用根路径在此阶段跳转到该入口。
- DesktopPreview 通过必需的 data 属性接收 DesktopWorkspaceData，学习任务、章节、复习内容、统计和用户信息均由展示模型提供。
- preview-data.ts 集中保存验收示例。正式数据经后端 API 转换为展示模型，Notion 章节与原文、AI 提取结果、业务复习历史和统计分别保留来源。
- localStorage 的 memory-os-ui-preview-v1 保存页面验收状态。真实鉴权继续使用既有 AuthProvider 和 API 登录入口，管理中心的示例角色切换仅作用于预览页面。
- 图标使用 lucide-react，横幅图片本地存放。Playwright 覆盖页面入口、刷新后的状态、知识解析、章节筛选和桌面/推送阅读布局。

## 管理员学习查看展示层 · 2026-11-14

管理中心通过独立AdminPreview组件呈现用户概览、复习记录与知识库。AdminUserSnapshot描述单个用户的管理展示输入，各用户记录与知识点分别归属对应快照。选择用户时清理上一用户的筛选和详情状态。

示例管理数据集中在admin-preview-data.ts，仅由/preview/admin页面传入adminUsers属性。正式接线由管理员专用后端查询提供数据，权限校验、分页查询与访问审计在后端实施。

## 独立管理员后台前端 · 2026-11-16

/preview/admin采用独立AdminShell和AdminDemoProvider，复用现有视觉样式、图表、图标、图片和用户知识详情组件。七页采用明确的静态路由，独立于普通用户端布局。

AdminDemoProvider仅保存前端配置元数据及演示状态，API Key和授权凭据为弹窗内临时输入。七页的连接测试、同步、发送、服务运行状态、登录会话和安全事件均采用显式示例数据。现有后端代码继续继承，本轮实现限定为前端。

用户与会话页组合登录时段和在线筛选，以及既有AdminPreview用户学习详情。正式用户隔离、管理员权限、心跳、审计、密钥保护和业务调用在后端接线阶段验收。

Windows与Ubuntu使用同一套Next.js源码和锁文件，在目标系统安装依赖并构建。前端迁移包及RUN_ON_UBUNTU.md记录运行方式和验证范围。

## 引导流程暂停记录 · 2026-11-18

增加用户工作区配置层、加密凭据解析和自动后台编排。Notion同步与AI提取读取当前用户的加密配置，模型费用同意按用户保存。邮件使用现有SMTP传输端口，新增SSL465与证书验证，持久化摘要、投递尝试和退避状态。正式前端采用欢迎页、首次引导和真实工作区，preview保留独立验收用途。当前尚未完成正式端口切换。

## 2026-11-18 当前本地运行架构

浏览器访问Next.js3030，/api/v1由同源代理转发到FastAPI8000，业务持久化到独立PostgreSQL55433。欢迎、向导、正式工作台统一使用真实API。后台默认处理同步、章节提取、每日任务与邮箱作业，复用CLI worker相同业务函数。测试服务器、外部传输替身与testing/drain仅位于明确的测试入口。

用户级SMTP、Notion和模型密钥认证加密保存，服务器SECRET_KEY与数据库备份分开维护。现有通知适配器、原始笔记版本、来源关系和调度策略继续复用。微信、飞书、钉钉通过统一渠道接口扩展，当前用户网页以邮箱闭环为首期运行路径。


## 正式学习体验接线 · 2026-11-18

components/portal/Workspace保留鉴权、首次配置与复习事务控制；LearningExperience负责正式首页及各学习视图，learning-experience.css提供独立前缀样式，避免影响既有预览。backend/app/services/insights为只读用户聚合，contracts/insights.py定义OpenAPI响应，不引入新表或后台任务。分页及搜索在服务端授权后执行。正式数据与测试数据仍使用不同数据库、8000/8001后端与3030/3031前端隔离。
