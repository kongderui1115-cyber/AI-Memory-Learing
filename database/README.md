# 数据库交付

[`schema.sql`](schema.sql) 包含从空库升级至 `0006_notion_lifecycle` 的完整 PostgreSQL DDL 和 Alembic 版本记录，共 29 张业务表和一张版本表。空库可以运行 `alembic upgrade head`，也可由数据库所有者执行该 SQL。请选择一种建库方式。

已有数据库通过 [`backend/alembic/versions/`](../backend/alembic/versions/) 升级。迁移身份需要 DDL 权限，日常 HTTP 应用采用受限业务账号。本机初始化脚本配置权限与私有凭据，操作见[启动指南](../docs/GETTING_STARTED.md)。

`0001` 建立基础表。`0002` 增加会话、限流、审计、幂等和学习工作流相关表。`0003` 保存复习跳过原因。`0004` 增加 Notion 状态与增量水位。`0005` 支持向导资料、加密凭据和摘要邮件作业。`0006` 补充 Notion 同步资源的生命周期字段。

开发库已使用pg_dump备份并恢复到独立验证库，版本、用户、凭据数量和表数一致。私有数据与备份位于.local-test。密文恢复还需安全保留配套服务器SECRET_KEY。源码交付排除环境文件、密码、数据库目录和备份。

网站操作、Windows启动、SQL导出及Ubuntu完整迁移见backend/RUN_BACKEND.md。
