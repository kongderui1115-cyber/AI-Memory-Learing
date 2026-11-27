# QA 测试用例规格矩阵（可执行规格设计）

> 维护者：QA Agent `qa-dev` ｜ 建立：2026-11-13 ｜ 分支 `agent/qa/qa-core`
>
> **性质：规格设计文档，不是测试执行报告。** 本文把 `TEST_REPORT.md` §3 的 19 个验收用例
> 转成带「输入 / 预期输出 / 前置条件 / 外部授权 / 测试模式」的**可执行规格**，
> 供各模块实现合并后编写与执行测试。
>
> **本批次未执行其中任何一个用例，所有用例状态均为 `未执行`。** 真实执行结果只能写入 `TEST_REPORT.md`。
> 其他 Agent 仍在各自 Worktree 开发，业务实现不可见；本文**不虚构任何针对尚未存在代码的测试结果**。

---

## 1. 分类定义（判定口径）

- **隔离测试（Isolated）**：不触达任何未授权外部服务。允许纯函数、fixture、契约静态检查、
  专用/内存测试库，以及**显式标注**的测试替身（mock / stub / 故障注入）。对应 pytest marker `isolated`。
- **真实联调（Live integration）**：真实调用已授权的外部依赖（Notion、LLM、微信/企业微信/钉钉/SMTP、
  经确认的 PostgreSQL）或真实 HTTP 端到端。对应 pytest marker `integration`。
  **未授权时一律 `skip` 并标注原因；不得以 mock 通过冒充真实联调通过。**
- 标注「隔离测试 + 真实联调」的用例，两类**分别**给出输入/预期输出/前置条件，**分别独立判定**；
  隔离通过 **≠** 真实联调通过。
- **外部授权**取值：`否` / `部分` / `是（BLK-xx）`；`INT-02` 为集成启动前置（非授权但必需）。
  - `BLK-01`：Notion Integration Token + 目标 Database ID
  - `BLK-02`：DeepSeek / OpenAI API Key 及计费许可
  - `BLK-03/04`：微信方向及其它通知渠道凭据、SMTP 账号
  - `BLK-05`：本机 5432 PostgreSQL 实例用途与连接串确认（**禁止猜测凭据连接**）

---

## 2. 总览表

| 用例 ID | 需求 | 测试模式 | 外部授权 | 责任 | 状态 |
| --- | --- | --- | --- | --- | --- |
| TC-ALG-01 | FR-05 | 隔离测试 | 否 | QA-02 | 未执行 |
| TC-ALG-02 | FR-05 | 隔离测试 | 否 | QA-02 | 未执行 |
| TC-ALG-03 | FR-05 | 隔离测试 | 否 | QA-02 | 未执行 |
| TC-TASK-01 | FR-06 | 隔离测试 | 否 | QA-02 | 未执行 |
| TC-TASK-02 | FR-06 | 隔离测试 | 否 | QA-02 | 未执行 |
| TC-CONS-01 | FR-09 | 隔离测试 | 否（需 BLK-05 测试库） | QA-03 | 未执行 |
| TC-CONS-02 | FR-09 | 隔离测试 | 否（需 BLK-05 测试库） | QA-03 | 未执行 |
| TC-SYNC-01 | FR-01 | 隔离测试 + 真实联调 | 部分（BLK-01） | QA-06 | 未执行 |
| TC-SYNC-02 | FR-03 | 隔离测试 + 真实联调 | 部分（BLK-01/02） | QA-06 | 未执行 |
| TC-AI-01 | FR-02 | 隔离测试 | 否（验证"未授权"路径） | QA-06 | 未执行 |
| TC-AI-02 | FR-04 | 隔离测试 + 真实联调 | 部分（BLK-02） | QA-04 | 未执行 |
| TC-SUBJ-01 | FR-10 | 隔离测试 + 真实联调 | 部分（BLK-01/02/03/04） | QA-04 | 未执行 |
| TC-NOTIF-01 | FR-07 | 隔离测试 + 真实联调 | 是（BLK-03/04） | QA-06 | 未执行 |
| TC-NOTIF-02 | FR-08 | 隔离测试 + 真实联调 | 部分（BLK-03/04） | QA-06 | 未执行 |
| TC-NOTIF-03 | FR-08 | 隔离测试 | 否 | QA-04 | 未执行 |
| TC-API-01 | 全部 | 隔离测试 + 真实联调 | 否（需 INT-02 启动） | QA-04 | 未执行 |
| TC-E2E-01 | FR-09 | 真实联调 | 否（需 INT-02 + FE-04/05） | QA-05 | 未执行 |
| TC-EXC-01 | 全部 | 隔离测试 + 真实联调 | 部分（相关 BLK） | QA-06 | 未执行 |
| TC-REG-01 | 全部 | 真实联调（完整回归） | 否（**必须 INT-01/INT-02 后**） | QA-REG-01 | 未执行 |

统计：纯隔离测试 **9** 个、隔离+真实联调分列 **8** 个、纯真实联调 **2** 个，合计 **19** 个，**全部未执行**。

---

## 3. 逐用例规格

### TC-ALG-01 艾宾浩斯固定间隔序列按复习次数精确推进

- **需求** FR-05 ｜ **模式** 隔离测试 ｜ **外部授权** 否 ｜ **责任** QA-02 ｜ **状态** 未执行
- **前置条件**：`BE-05` 交付可导入、无 I/O 的调度纯函数；间隔序列默认 `[1,2,4,7,15,30]` 由 `ARCHITECTURE.md` §6 冻结；pytest 已安装。
- **输入**：`intervals_days=[1,2,4,7,15,30]`；初始 `review_count=0, interval_index=0, lapse_count=0`；固定基准 `reviewed_at=2026-01-01T00:00:00Z`；评分序列 `["good","good","good","again","good","good","good","good","good"]`。
- **预期输出**：第 1/2/3 次 `good` 后 `due_at` 依次 `+1/+2/+4` 天、`interval_index` 依次推进；第 4 次 `again` 重置回首间隔 `+1` 天且 `lapse_count+1`；超出序列长度后沿用末项 `+30` 天；`review_count` 按成功次数递增；同输入重复执行 100 次结果完全一致。
- **判定**：返回的 `due_at / interval_index / review_count / lapse_count` 与冻结期望表逐项相等；全程无 DB/网络调用。

### TC-ALG-02 FSRS 在给定评分序列下状态与 due 可复现

- **需求** FR-05 ｜ **模式** 隔离测试 ｜ **外部授权** 否 ｜ **责任** QA-02 ｜ **状态** 未执行
- **前置条件**：`BE-05` 交付 FSRS 纯函数 **及冻结的固定用例期望值表**（含 `algorithm_version`、`parameters` 快照与浮点容差）；契约 `ScheduleStateRead` 已冻结。**期望数值由 BE-05 依 FR-05 规格给出，QA 不自行编造**；若未提供期望值表，本用例标 `阻塞` 而非通过。
- **输入**：期望值表给定的初始记忆状态（`stability/difficulty/reps/lapses`）、`target_retention=0.9`、固定 `algorithm_version` 与 `parameters`、固定 `reviewed_at`、评分序列（覆盖 `again/hard/good/easy` 各至少一次，含连续 `again`）。
- **预期输出**：每步 `stability/difficulty/retrievability/due_at` 与期望值表一致（按表声明容差）；重复执行结果一致；`last_calculation` 含可解释的计算依据（"为什么今天复习我"）。
- **判定**：逐项比对期望值表；不得臆造数值。

### TC-ALG-03 两套策略对同一知识点产生的结果可对比、可切换

- **需求** FR-05 ｜ **模式** 隔离测试 ｜ **外部授权** 否 ｜ **责任** QA-02 ｜ **状态** 未执行
- **前置条件**：`BE-05` 交付 `ScheduleCompareResponse` 纯计算与 `ScheduleSwitchRequest` 切换逻辑；`ScheduleStateRead/ScheduleProjection` 契约冻结。
- **输入**：同一 `knowledge_point_id`、同一当前记忆状态、固定 `rating`/`reviewed_at`；分别请求 `compare` 与 `strategy` 切换（`ebbinghaus ↔ fsrs`，带/不带 `parameters`）。
- **预期输出**：`compare` 同时返回 `ebbinghaus` 与 `fsrs` 两个 projection（各自含 `due_at/state/explanation`）且**纯计算不写库**（对比前后 `schedule_states` 无变化）；切换后 `strategy` 更新、`strategy_changed_at` 记录、用当前记忆状态初始化目标策略、历史不被改写；两套结果可对比。
- **判定**：响应结构、纯计算无副作用、切换后状态与 `strategy_changed_at` 正确。

### TC-TASK-01 给定到期集，当日任务数量/优先级/学科筛选符合规则

- **需求** FR-06 ｜ **模式** 隔离测试 ｜ **外部授权** 否 ｜ **责任** QA-02 ｜ **状态** 未执行
- **前置条件**：`BE-06` 交付每日生成逻辑；`DailyGenerateRequest`（`daily_limit 1..500`、默认 30）与 `DailyBatchRead/DailyTaskRead` 契约冻结；可用隔离数据集（fixture 或专用测试库）。
- **输入**：固定到期集（3 个学科、不同 `due_at` 与逾期天数、≥50 个知识点）；`local_date=2026-01-02`、`timezone="Asia/Shanghai"`、`daily_limit=10`；另做一组带 `subject_id` 筛选。
- **预期输出**：任务数 = `min(到期数, daily_limit)`；优先级随逾期程度单调；学科筛选后仅含指定学科；`position` 连续且唯一；`(batch_id, knowledge_point_id)` 无重复；响应符合 `DailyBatchRead`。
- **判定**：与按 FR-06 规则计算的期望清单逐项比对。

### TC-TASK-02 重复生成幂等；漏复习滚动到次日不丢失

- **需求** FR-06 ｜ **模式** 隔离测试 ｜ **外部授权** 否 ｜ **责任** QA-02 ｜ **状态** 未执行
- **前置条件**：同 TC-TASK-01；`UQ (user_id, idempotency_key)` 与 `UQ (batch_id, knowledge_point_id)` 约束可用。
- **输入**：同一 `Idempotency-Key` 重复调用生成 3 次；构造前一日 `pending` 未完成任务；次日再按新 `local_date` 生成；对一任务调用 `POST /review-tasks/{id}/skip`。
- **预期输出**：3 次返回同一 `batch.id` 与相同任务清单、DB 无新增重复行；前一日未完成任务对应 `schedule_states.due_at` 保持不变且出现在次日到期集；`skipped` 任务 due 不丢失。
- **判定**：幂等性与补漏（无任务丢失）。

### TC-CONS-01 一次完成 → 1 条历史 + 调度状态更新 + 新 due，事务一致

- **需求** FR-09 ｜ **模式** 隔离测试 ｜ **外部授权** 否（但需 `BLK-05` 确认的**专用测试库**）｜ **责任** QA-03 ｜ **状态** 未执行
- **前置条件**：`BE-07` 交付单事务完成用例；迁移已在专用测试库执行；`ReviewCompleteRequest/ReviewCompleteResponse` 契约冻结。**`BLK-05` 未确认 → 当前该用例标 `阻塞`，不得用内存替身冒充 DB 事务测试。**
- **输入**：一个 `pending` 任务 + 合法 `ReviewCompleteRequest`（`rating=good`、`duration_seconds≥0`、`reviewed_at`）+ `Idempotency-Key`；另注入事务中途失败。
- **预期输出**：`review_history` 恰好新增 1 行且 `task_id` 唯一；`daily_review_tasks.status=completed`；`schedule_states` 按策略产生新 `due_at` 且 `review_count+1`；三者同一事务提交，`ReviewCompleteResponse` 的 `task/history/schedule` 互相引用一致；同 key 重放不产生第二条历史；注入失败时三者**全部回滚**。
- **判定**：DB 行数/字段 + 响应一致性 + 回滚演练。

### TC-CONS-02 历史追加写不可篡改，按知识点/学科/时间可查

- **需求** FR-09 ｜ **模式** 隔离测试 ｜ **外部授权** 否（需 `BLK-05` 测试库）｜ **责任** QA-03 ｜ **状态** 未执行
- **前置条件**：同 TC-CONS-01；`review_history` 追加写约束生效。
- **输入**：多次完成产生多条历史；尝试对历史执行 UPDATE/DELETE 及通过 API 的修改/删除请求；按 `knowledge_point_id`、`subject_id`、`from/to`、`rating` 组合查询 `GET /review-history`。
- **预期输出**：契约中无历史修改/删除端点（可静态校验）；DB 层追加写，既有历史行内容不可变；查询结果与写入集合一致，分页为 `items/next_cursor/has_more` 且默认按 `created_at desc,id desc`，无 offset。
- **判定**：不可篡改 + 多维查询与分页。

### TC-SYNC-01 同 page 同版本重复同步不产生重复知识点

- **需求** FR-01 ｜ **模式** 隔离测试 **+** 真实联调 ｜ **外部授权** 部分（真实联调需 `BLK-01`）｜ **责任** QA-06 ｜ **状态** 未执行

**【隔离测试】**

- 前置：`AI-02` 交付同步适配器；使用**显式标注的 Notion fixture**（`external_page_id`、`external_version`、`last_edited_time`、`content_markdown`），不触达真实 Notion。
- 输入：同一 fixture page 以相同 `external_version` 触发同步 3 次（相同/不同 `Idempotency-Key` 各一组）。
- 预期输出：`raw_notes` 唯一约束 `(data_source_id, external_page_id, external_version)` 生效仅 1 行；`knowledge_points` 不重复（canonical_hash / 来源关联去重）；`sync_runs` 记录 3 次且第 2/3 次 `items_imported=0`；水位仅在成功后推进。
- 判定：结果**仅代表隔离逻辑**，标注为测试替身 fixture。

**【真实联调】**

- 前置：`BLK-01` 用户授权（Notion Token + Database ID）。**未授权则整段 `skip`，不得以 fixture 结果冒充。**
- 输入：对真实 Notion Database 连续两次手动触发同步；另做 Token 失效/断网一次。
- 预期输出：真实拉取页面并落库；第二次不产生重复知识点；Token 失效/断网返回明确 `CONFIG_MISSING` / `EXTERNAL_SERVICE_ERROR` 与重试记录，不返回假同步结果。

### TC-SYNC-02 人工修订内容在再次同步后保留

- **需求** FR-03 ｜ **模式** 隔离测试 **+** 真实联调 ｜ **外部授权** 部分（`BLK-01/02`）｜ **责任** QA-06 ｜ **状态** 未执行

**【隔离测试】**

- 输入：对知识点执行 `PATCH`（契约规定设置 `manual_revision=true`），随后以同源笔记**新版本** fixture 再次同步/抽取。
- 预期输出：`manual_revision=true` 的人工字段（title/body/summary 等）不被覆盖；`version` 递增；来源关联追加而不改写人工内容。
- 判定：fixture 标注为测试替身，仅验证保护逻辑。

**【真实联调】**

- 前置：`BLK-01`（真实同步）+ `BLK-02`（真实抽取）；未授权 `skip`。
- 预期输出：真实再同步后人工修订仍在；生成元数据可追溯。

### TC-AI-01 未配置 Key 时明确报错，不返回假理解结果

- **需求** FR-02 ｜ **模式** 隔离测试 ｜ **外部授权** 否（本用例正是验证"未授权"路径）｜ **责任** QA-06 ｜ **状态** 未执行
- **前置条件**：`AI-01` 交付 Provider 抽象；测试环境确保无相关 Key 且 `AI_BILLING_APPROVED != true`。
- **输入**：Provider 配置存在但 `credential_ref` 指向未设置的环境变量，调用理解/抽取用例。
- **预期输出**：返回明确 `CONFIG_MISSING`（或契约许可的 `FORBIDDEN`），不产生任何结构化知识点、不写"成功"调用日志；`ai_call_logs` 记录 `failed` 与错误码；**绝不返回占位/假理解结果**。
- **判定**：响应错误码 + 无业务副作用 + 日志状态。

### TC-AI-02 题目/答案/摘要生成元数据完整、可重新生成

- **需求** FR-04 ｜ **模式** 隔离测试 **+** 真实联调 ｜ **外部授权** 部分（真实联调需 `BLK-02`）｜ **责任** QA-04 ｜ **状态** 未执行

**【隔离测试】**

- 输入：以**显式标注的结构化输出 fixture** 驱动 `review-items/generate` 编排（不调用真实模型）；随后重新生成、并对一条题目人工编辑后再生成。
- 预期输出：`ReviewItemRead` 含 `item_version/is_current/provider_config_id/model_name/prompt_version/ai_call_log_id`；重新生成产生新版本且旧版保留、`is_current` 仅一条为真；人工编辑后重新生成不覆盖 `manual_revision`。
- 判定：fixture 标注测试替身，仅验证编排与版本逻辑。

**【真实联调】**

- 前置：`BLK-02`（Key + 计费许可）；未授权 `skip`。
- 预期输出：真实模型返回题目/答案/解析/摘要，多题型（`qa/cloze/multiple_choice/short_explanation`）可生成；`ai_call_logs` 记录真实 token 用量/耗时/`status=succeeded`。

### TC-SUBJ-01 新增学科仅靠配置走通抽取→出题→调度→推送

- **需求** FR-10 ｜ **模式** 隔离测试 **+** 真实联调 ｜ **外部授权** 部分（全链路真实需 `BLK-01/02/03/04`）｜ **责任** QA-04 ｜ **状态** 未执行

**【隔离测试】**

- 输入：**仅通过** `POST /subjects` + `PUT /subjects/{id}/strategy` 新增一个全新学科（含 `extraction_prompt`、`question_type_preferences`、`glossary`、`scheduler_overrides`、`notification_template_overrides`、`prompt_version`），不改代码、不重新部署；以 fixture 驱动后续链路；内容含俄/法/英语 Unicode 与 `parent_id` 层级。
- 预期输出：学科与层级正确落库、Unicode 无损；抽取、出题、调度、模板渲染均读取该学科策略覆盖生效；无硬编码学科分支。
- 判定：配置驱动、无代码改动。

**【真实联调】**

- 前置：`BLK-01/02/03/04` 全部授权；未授权则此段 `skip`，**隔离结果不得冒充全链路通过**。
- 预期输出：真实笔记 → 真实知识点 → 真实题目 → 真实调度 → 真实推送收到含具体知识点正文的消息，全程仅靠配置完成。

### TC-NOTIF-01 推送正文含具体知识点内容而非空通知

- **需求** FR-07 ｜ **模式** 隔离测试 **+** 真实联调 ｜ **外部授权** 是（`BLK-03/04`）｜ **责任** QA-06 ｜ **状态** 未执行

**【隔离测试】**

- 输入：以 fixture 知识点（title/summary/问题/答案要点）调用模板渲染与 job 编排；渠道适配器用**显式标注的测试替身**（不真实发送）；另做未配置凭据一组。
- 预期输出：渲染正文含具体知识点内容（标题 + 摘要/问题/答案要点 + 复习入口），**不含**"您有 N 条待复习"空文案；未配置凭据时明确 `CONFIG_MISSING`、**不得返回 `sent`**；按渠道 `max_length` 自适应裁剪/分段。
- 判定：fixture 标注测试替身，仅验证渲染与编排。

**【真实联调】**

- 前置：`BLK-03/04`（用户选定 FR-07 的 A/B/C/D 微信方向并提供凭据）；未授权整段 `skip`。
- 预期输出：真实收到含具体知识点正文的消息；`notification_deliveries` 留痕；**不实现个人微信逆向/非官方协议**，未配置凭据绝不假推送。

### TC-NOTIF-02 渠道失败后退避重试、失败与推送历史可查

- **需求** FR-08 ｜ **模式** 隔离测试 **+** 真实联调 ｜ **外部授权** 部分（`BLK-03/04`）｜ **责任** QA-06 ｜ **状态** 未执行

**【隔离测试】**

- 输入：注入渠道发送失败（异常/超时/限流）；对 `failed` job 调用 `POST /notification/jobs/{id}/retry`；对非 `failed` 状态重试；重复同 `Idempotency-Key`。
- 预期输出：按退避策略递增 `next_attempt_at`、`attempt_count`；每次尝试追加一条 `delivery`（`attempt_no` 唯一）；耗尽 `max_attempts` 后 `status=failed`；`retry` **仅对 `failed` 生效**、返回 202；历史可按 `task_id/status/channel_type/from/to` 查询；幂等键防重复投递。
- 判定：所有故障均为**显式标注的注入替身**。

**【真实联调】**

- 前置：`BLK-03/04` 授权的真实渠道；未授权 `skip`。
- 预期输出：可控地使真实渠道失败后有真实重试与失败记录，不产生"假 `sent`"。

### TC-NOTIF-03 模板渲染变量与渠道长度自适应正确

- **需求** FR-08 ｜ **模式** 隔离测试 ｜ **外部授权** 否 ｜ **责任** QA-04 ｜ **状态** 未执行
- **前置条件**：`NOTIF-02` 交付纯渲染函数；`TemplateWrite.schema_variables/max_length` 契约冻结。
- **输入**：模板含变量（知识点标题/摘要/问题/答案/复习入口）；多组 `max_length`（短/中/长、边界、超长）；Unicode 内容；缺失变量；未闭合占位符。
- **预期输出**：`schema_variables` 与模板实际变量一致；渲染结果无未替换占位符；超出 `max_length` 时按渠道规则裁剪/分段且不截断多字节字符；缺失变量有明确错误而非静默留空。
- **判定**：纯函数逐项比对。

### TC-API-01 所有端点请求/响应 schema、错误码、分页与契约零偏差

- **需求** 全部 ｜ **模式** 隔离测试 **+** 真实联调 ｜ **外部授权** 否（运行时需 `INT-02` 启动）｜ **责任** QA-04 ｜ **状态** 未执行

**【隔离测试（契约静态）】**

- 前置：`API_CONTRACTS.md` §3/§4 与 `app/contracts/models.py`、`enums.py` 冻结；`qa/check_api_contract.py` 可用。
- 输入：契约文档 + 契约代码；`/openapi.json` 导出（若后端可启动）。
- 预期输出：端点登记与格式合法、11 个枚举名称与值集合完全一致、Schema 字典每个模型字段与 Pydantic 模型一致、错误码表与 §1 一致。
- 判定：**本批次已真实运行静态子集并 PASS（`TEST_REPORT.md` §6），但该静态子集不覆盖运行时 schema/错误码/分页/鉴权行为，TC-API-01 整体仍为 `未执行`。**

**【真实联调（运行时）】**

- 前置：`INT-01/INT-02` 完成、服务真实启动、`QA_API_BASE_URL`/`QA_AUTH_TOKEN` 已配置、pytest + httpx 已安装；未满足 `skip`。
- 输入：对 §4 每个 (方法, 路径) 构造合法请求 + 典型非法请求（缺字段 / 非法枚举 / `limit` 超 1..100 / 缺 `Idempotency-Key` / 缺或错 `If-Match` / 错误 Bearer）。
- 预期输出：响应 schema 与契约零偏差；错误结构 `error{code,message,details,request_id,retryable}` 与 HTTP→错误码映射一致；列表 `items/next_cursor/has_more`、`limit` 默认 20、`cursor` 不透明、无 offset；创建 201 / 异步 202 / 删除 204；响应含 `X-Request-ID`；同 `Idempotency-Key` 重放返回原资源；版本冲突返回 `VERSION_CONFLICT`；资源按 `user_id` 隔离；`/health/ready` 不探测未授权外部服务。

### TC-E2E-01 前端完成标记 → 后端历史/状态 → 次日任务真实联动

- **需求** FR-09 ｜ **模式** 真实联调 ｜ **外部授权** 否（需 `INT-02` + `FE-04/05`）｜ **责任** QA-05 ｜ **状态** 未执行
- **前置条件**：`INT-02` 完成、前后端真实启动、真实浏览器或真实 HTTP、`QA_API_BASE_URL`/`QA_AUTH_TOKEN` 配置、`BLK-05` 测试库可用；**不得用 mock 冒充**。
- **输入**：前端「今日复习」完成一道题（选择掌握程度、填写耗时/自评/备注）；随后查询 `GET /review-history`、`GET /knowledge-points/{id}/schedule`，按次日 `local_date` 查询 `GET /review-tasks`。
- **预期输出**：后端产生 1 条历史、任务 `completed`、schedule 新 `due_at`；次日任务按新 due 正确联动；前端统计/历史视图显示真实接口数据、无假数据兜底；文案全中文、移动端可用。
- **判定**：真实浏览器或真实 HTTP 链路；任一环节为 mock 则该用例**不得标通过**。

### TC-EXC-01 外部 API 超时、限流、渠道不可用、DB 故障的行为与记录

- **需求** 全部 ｜ **模式** 隔离测试 **+** 真实联调 ｜ **外部授权** 部分（相关 BLK）｜ **责任** QA-06 ｜ **状态** 未执行

**【隔离测试】**

- 输入：显式注入四类故障 —— HTTP 超时/连接失败、`429 限流`、渠道适配器抛错、DB 连接/事务异常；并覆盖重复同步（同 key）、漏复习（前日 pending）、缺 Key、未配置渠道凭据。
- 预期输出：外部调用有总超时与指数退避且**只重试可重试错误**；错误码为 `EXTERNAL_TIMEOUT/RATE_LIMITED/SERVICE_UNAVAILABLE/CONFIG_MISSING/INTERNAL_ERROR` 之一且与契约一致、`retryable` 标记正确；`ai_call_logs` / `sync_runs` / `notification_deliveries` 均留错误与耗时；失败不推进水位、不产生假成功、不破坏事务一致性；未配置凭据返回明确错误而非降级假数据。
- 判定：所有故障均为**显式标注的注入替身**，结果只代表隔离行为。

**【真实联调】**

- 前置：`BLK-01/02/03/04/05` 中相关项授权；未授权整段 `skip`。
- 预期输出：真实断网 / Token 失效 / 渠道不可用时行为与隔离一致且留可审计日志；**不得以注入结果冒充真实故障联调**。

### TC-REG-01 合并后完整系统回归（硬要求）

- **需求** 全部 ｜ **模式** 真实联调（完整回归）｜ **外部授权** 否（**必须 `INT-01/INT-02` 之后**）｜ **责任** QA-REG-01 ｜ **状态** 未执行（本批次未放行）
- **前置条件（全部满足方可执行）**：Codex 完成 `INT-01`（审查/合并/契约对齐）与 `INT-02`（整体集成与真实启动验证）；后端可启动、前端可构建、迁移可执行、测试依赖已安装；**在 MAIN 树执行**（非 Worktree）。
- **输入**：上述 TC-ALG / TASK / CONS / SYNC / AI / SUBJ / NOTIF / API / E2E / EXC 全部用例 + 前后端构建/启动检查 + `qa/check_api_contract.py`；真实联调部分按 `TEST_REPORT.md` §4 授权状态分组执行，未授权项标 `SKIP` 并单列。
- **预期输出（写入 `TEST_REPORT.md`）**：真实执行命令、完整输出摘要、用例总数/通过/失败/跳过、环境版本、未解决问题；**「隔离测试」与「真实联调」两组结果分别列出**，隔离通过不得计入真实联调通过。
- **判定**：任何失败项交 `INT-03` 修复后重跑；全绿或明确列出未解决项方可由 `PM-05` 汇总。**本批次未执行、未放行。**

---

## 4. 与已完成工作的边界（如实）

- 本批次**唯一真实执行**的是 `qa/check_api_contract.py`（契约静态一致性检查，17 项 PASS / 0 FAIL，退出码 0），
  真实输出见 `TEST_REPORT.md` §6。它只覆盖 **TC-API-01 的静态子集**（端点登记 / 枚举值 / 格式），
  **不覆盖**运行时 schema、错误码、分页、鉴权行为；TC-API-01 整体仍为 `未执行`。
- `backend/tests/conftest.py` 已落盘 fixture 与 marker，但 **pytest 未安装 → 未执行**。
- 本文所有 19 个用例状态为 `未执行`；**无任何用例被写成通过**。
- 回归门禁 `QA-REG-01` 待 `INT-01/INT-02` 后执行，详见 `TEST_REPORT.md` §5。
