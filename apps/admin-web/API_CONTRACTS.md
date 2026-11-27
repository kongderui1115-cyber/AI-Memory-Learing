# 独立管理控制台 API 契约

## 边界

浏览器只访问同源 `/api/admin-gateway/<action>`。Next.js 服务端用部署配置指向 FastAPI 的 `/api/v1`。`lib/types.ts` 定义页面模型，`lib/client.ts` 是真实/演示适配入口。服务端认证和授权由 FastAPI 执行。演示路由直接使用本地适配器。

管理员网关登录成功后将 FastAPI 会话凭据放进独立 HttpOnly、SameSite=Strict Cookie，作用域限定为网关路径。生产 HTTPS 需要 Secure。浏览器不会从 JSON 收到访问令牌。写操作要求同源 Origin 和 `X-Admin-Client: console`。网关响应禁止缓存。

## 已接通

|网关动作|方法|FastAPI 路径|
|---|---|---|
|login|POST|`/auth/token` + `/me` 角色校验|
|session|GET|`/me`|
|logout|POST|`/auth/logout`|
|password|POST|`/auth/password`|
|overview|GET|`/admin/overview`|
|analytics|GET|`/admin/analytics`|
|audit|GET|`/admin/audit-events`|
|users|GET|`/admin/users`|
|users|POST|`/admin/users`|
|users|PATCH|`/admin/users/{uuid}`|
|sessions|GET|`/admin/sessions`|
|user-overview|GET|`/admin/users/{uuid}/overview`|
|user-knowledge|GET|`/admin/users/{uuid}/knowledge-points`|
|user-history|GET|`/admin/users/{uuid}/review-history`|
|health|GET|`/health/ready`，网关先验证管理员角色|

筛选和分页沿用后端字段名 `limit`、`cursor`、`q`、`user_id`、`online`、`severity`、`action`、`from` 与 `to`，具体视端点而定。聚合统计以账号时区为准，登录和审计日期筛选在客户端按浏览器本地日期换算为 ISO 时间后提交。

统计接口使用 `from_date`、`to_date` 或 `days`，返回学习、学科回忆、FSRS 历史对照和任务终态聚合。详见 [运营统计契约](../../docs/admin-analytics-contract.md)。

## 管理员运营与维护接口

所有接口均验证后端管理员会话。跨用户资源使用管理员 API 的所有者关联，界面沿用独立网关。读取不返回密钥、凭据引用、正文或第三方原始响应。

|区域|已支持的端点与行为|
|---|---|
|模型|`GET /admin/model-providers`、`GET /admin/model-providers/{id}/readiness`、`PATCH /admin/model-providers/{id}`。列出配置及本地就绪状态。启停和默认项修改需要 `If-Match`。就绪检测无需向模型提供商发请求。|
|来源|`GET /admin/sources`、`GET /admin/sources/{id}/runs`、`POST /admin/sources/{id}/sync`。同步请求使用 `Idempotency-Key`，只写入待执行队列。暂停后台时仍可查看排队状态。|
|通知|`GET /admin/notification-channels`、`GET /admin/notification-deliveries`。区分平台接受与送达状态，实际可用数据取自对应通道及投递记录。|
|记忆|`GET /admin/memory/policies`、`PATCH /admin/memory/policies/{id}`、`POST /admin/memory/simulations`。按账号和学科查看策略，修改已有学科策略需 `If-Match`，作用于新建调度。模拟调用纯算法，不写复习历史。|
|作业|`GET /admin/jobs`。统一展示同步、提取、复习生成及通知作业，支持按类型/状态/账号查询，返回时间、状态、错误代码与重试信息。|
|系统|`GET /admin/telemetry`、`GET /admin/system/info`。主机采样为当前 CPU、内存、磁盘。API 计数、5xx 和延迟来自当前后端进程，最多统计最近 24 小时。无采样值以 null 返回。|
|备份|`GET /admin/backups`、`POST /admin/backups`。POST 需要 `Idempotency-Key`，生成 PostgreSQL 归档并记审计。需部署者配置绝对路径 `ADMIN_BACKUP_DIRECTORY` 和 `ADMIN_PG_DUMP_PATH`，目录应仅允许运行账号访问。接口默认关闭，只返回归档元信息。|

## 后续扩展

采用下列契约面实施时再增加权限、校验、审计与幂等处理。路径为拟议接口。

|模块|拟议路由与字段|
|---|---|
|模型治理|管理员代管连接密钥、跨账号创建与删除、用途分配、实际供应商连通性验收及费用归集。用户继续在学习者端设置自己的密钥、地址和计费授权。|
|知识来源|管理员代配用户授权、其他数据源适配与外部平台验收。|
|消息通知|管理员代配渠道、模板写入、真实测试发送和更多通道持久化。|
|记忆策略|可持久变更的系统默认值，以及旧调度的批量迁移流程。|
|任务调度|按类型的手动操作及重试策略，待各队列提供对应的权限与幂等契约。|
|系统运维|持久化及跨实例指标、外部 Worker/Redis 采集、多实例备份存储及恢复审核。|
