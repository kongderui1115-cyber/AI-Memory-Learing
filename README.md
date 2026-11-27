# AI Learning Memory OS

AI 学习记忆系统包含学习者网站、独立管理员控制台、统一的 FastAPI 服务和 PostgreSQL 数据库。学习者可以导入 Notion 资料、整理知识点、进行复习和设置提醒。管理员可以管理学习者账号、查看审计与运行统计，并维护系统策略。

| 组件 | 目录 | 本机入口 |
| --- | --- | --- |
| 学习者网站 | [`frontend/`](frontend/) | `http://127.0.0.1:3030/` |
| 独立管理员控制台 | [`apps/admin-web/`](apps/admin-web/) | `http://127.0.0.1:3001/login` |
| FastAPI 服务 | [`backend/`](backend/) | `http://127.0.0.1:8000/health/ready` |
| PostgreSQL | [`database/`](database/) 和 [`backend/alembic/`](backend/alembic/) | 本机独立集群默认 `127.0.0.1:55433` |

## 运行环境

准备 **Python 3.13、Node.js 22 至 24、pnpm 12.18.0 和 PostgreSQL 17**，并安装 PostgreSQL 命令行工具。Windows 可使用 PowerShell 5.1 或更新版本。Docker 非必需。

按[安装、配置和启动指南](docs/GETTING_STARTED.md)完成依赖安装、数据库初始化和管理员创建，再启动三个服务。登录后可以在学习者设置中添加 Notion、模型和 SMTP 凭据。示例配置见 [`.env.example`](.env.example)。

## 技术文档

- [认证与凭据](docs/AUTHENTICATION.md)介绍两个网站的登录流程、Cookie、Bearer JWT、会话撤销和第三方凭据的存储。
- [数据库说明](database/README.md)链接空库建表 SQL 和 Alembic 迁移。
- [后端运行](backend/RUN_BACKEND.md)介绍业务配置和后台任务。
- [管理员控制台](apps/admin-web/README.md)介绍控制台的真实模式、演示模式和验证步骤。
- [API 契约](API_CONTRACTS.md)记录接口、数据格式和错误码。
