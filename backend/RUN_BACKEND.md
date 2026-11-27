# 前后端与数据库运行

后端采用 Python 3.13、FastAPI 和 PostgreSQL，前端采用 Next.js、React 和 TypeScript。新环境从[启动指南](../docs/GETTING_STARTED.md)开始。

## 本机启动

以下命令在仓库根目录运行，复用已有的专用数据库与配置。

```powershell
& '.\.venv\Scripts\python.exe' scripts/init-local-db.py --pg-bin 'C:/Program Files/PostgreSQL/17/bin' --migrate
powershell -NoProfile -ExecutionPolicy Bypass -File '.\scripts\start-backend.ps1'
```

在另一个 PowerShell 窗口启动前端。

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File '.\scripts\start-frontend.ps1' -Mode start -Port 3030
```

源码修改后先停止该前端进程，执行 `scripts/start-frontend.ps1 -Mode build`，再以 `-Mode start` 启动。前端默认使用同源 `/api/v1`，由 Next.js 转发到本机后端。服务维护者可通过 `BACKEND_API_URL` 更换后端部署地址，构建与运行需采用一致配置。`PUBLIC_APP_URL` 决定邮件中的复习链接，本机默认值为 `http://127.0.0.1:3030`。

普通用户在浏览器打开 `http://127.0.0.1:3030` 即可注册或登录。首次登录进入分步向导，进度保存在服务器，允许稍后继续。已完成向导的用户再次登录直接进入学习空间。

## 网站内配置

1. 邮箱步骤填写接收邮箱、每日提醒时间、发件邮箱账号及 SMTP 授权码。每位用户维护自己的发件设置和凭据，接收邮箱可以单独修改。当前提供 QQ、163、Gmail 与 Outlook 的配置预设。点击测试会创建持久化发送任务，页面区分等待、失败与已提交邮件服务器。投递到收件箱的实际情况以邮箱为准。
2. Notion 步骤保存 Integration Token，将目标资料库分享给相应连接，再点击读取资料库并选择。也可粘贴资料库链接。设置学科以及未开始、进行中、已完成三个状态的属性映射后保存，后台开始同步。
3. 模型步骤支持 DeepSeek、Kimi、OpenAI 与兼容供应商，填写模型名称和 Key。勾选允许模型调用后，后台才会为该用户执行模型请求。用户承担相应供应商的实际计费。
4. 进入学习空间后，在设置页面修改邮箱、Notion 和模型配置。密钥输入保存后清空，读取接口仅返回是否已配置。

这些用户级配置由页面直接写入服务器。原有按用户环境变量配置接口继续兼容，适用于已有部署。密钥采用用户与凭据名称绑定的认证加密，数据库保存密文，服务器 `SECRET_KEY` 负责密钥派生。

## 学习与复习

章节可多次学习，未开始与进行中状态持续保存原始笔记。整章变为已完成后，后台创建知识提取任务，保留模型生成标记、调用记录、原文版本和 Notion 链接。人工修改内容受保护。

新学科使用通用提取策略，`/api/v1/subjects/{id}/strategy` 可配置提示词、术语、题型与调度参数。新增学科无需修改业务核心。模型结果经过结构检查后生成知识点、卡片和记忆调度。

每日任务按用户时区与到期知识生成。复习包含主动回忆、知识正文、答案、解析和四档评分。完成记录、历史和下次到期时间在同一数据库事务中保存，重试使用稳定幂等键。新记忆状态使用官方 py-fsrs，保留旧调度状态兼容分派以及固定间隔策略。

邮箱摘要包含知识标题、学科、复习次数、阶段、正文、主动回忆问题、答案、解析、Notion 来源和复习链接。链接在登录后定位对应任务，手机端适配该阅读与复习入口。已完成任务支持再次阅读。开发机的回环链接只适用于本机，迁移后由维护者配置用户可访问的 `PUBLIC_APP_URL`。

SMTP 采用持久化作业、发送尝试记录、退避重试和处理租约。中断尝试保留接收结果不确定的记录，最多尝试三次。远端已经接收邮件而本地状态尚未提交时，恢复重试可能重复发送。稳定 Message-ID 便于核对，系统使用至少一次处理语义。

## 后台运行

后端和独立 Worker 默认暂停自动处理。启用后才会周期处理 Notion 同步、章节提取、每日任务、邮件入队及发送。模型实际调用还须同时开启系统级模型计费许可和用户授权。

仍支持单次 worker，便于 Windows 任务计划或 Linux systemd/cron 调用相同业务代码。

```powershell
& '.\scripts\run-worker.ps1' -Job sync-notion
& '.\scripts\run-worker.ps1' -Job extract-chapters
& '.\scripts\run-worker.ps1' -Job generate-daily-tasks
& '.\scripts\run-worker.ps1' -Job send-daily-digest
```

## 账号与管理

公开注册创建普通用户。密码至少十个有效字符，连续失败超过五次触发限时锁定，同时实施 IP 限流。会话采用 HttpOnly Cookie。学习者写请求检查客户端请求头，独立管理端写请求还校验来源，接口支持 Bearer 调用。详细流程见[认证与凭据](../docs/AUTHENTICATION.md)。

全新环境按[启动指南](../docs/GETTING_STARTED.md)创建首个管理员。登录后可通过 `/api/v1/auth/password` 修改密码。管理员在学习空间侧栏进入后台，查询其他用户的知识、复习记录、登录起止、最后活跃与在线状态。跨用户访问经后端授权并记录审计。七页设计演示保留在 `/preview/admin`，其示例数据与状态在页面中标明。

独立管理员站在 3001。管理员进入系统设置的账号列表 view 后可创建普通学习者、编辑其资料和启停。新用户使用该邮箱和密码登录，首次登录进入配置向导。

## 数据库与备份

专用集群监听 `127.0.0.1:55433`，开发库为 `memory_os_dev`，测试库为 `memory_os_test`。原有未知 5432 实例保持隔离。当前迁移 HEAD 为 `0006_notion_lifecycle`，包含 29 张业务表及一张 Alembic 版本表。

`database/schema.sql` 是当前 HEAD 的完整空库建表 SQL。已有数据库使用 Alembic 升级。迁移账号拥有 DDL 权限，日常应用使用受限角色。初始化脚本配置所需权限，保护原始笔记、复习历史与审计记录的追加写约束。

```powershell
& '.\.venv\Scripts\python.exe' -m app.manage schema-sql --output database/schema.sql
& '.\.venv\Scripts\python.exe' scripts/run-backend-tests.py
```

`backend/.env`、`.local-test/local-db.json`、初始密码、数据库目录与备份均为本机私有文件，保持忽略版本控制。恢复或迁移时须安全保留与密文配套的 `SECRET_KEY`，数据库备份与服务器秘密分别保存。当前已将 0005 开发库备份并恢复到独立验证库。

## Ubuntu 本地虚拟机迁移

准备 Python 3.13、PostgreSQL、Node 22 至 24 和 pnpm 12.18.0，复制完整源码及锁文件。在目标环境建立独立数据库与受限应用账号，并通过服务器环境安全提供 `DATABASE_URL` 与 `SECRET_KEY`。迁移进程采用数据库所有者连接，应用进程采用受限连接。

```bash
python3.13 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements.lock
.venv/bin/python -m pip install --no-deps -e ./backend
cd backend
../.venv/bin/python -m alembic upgrade head
../.venv/bin/python -m app.server app.main:app --host 127.0.0.1 --port 8000
```

另开终端进入前端目录。

```bash
cd frontend
pnpm install --frozen-lockfile
pnpm build
pnpm start --hostname 127.0.0.1 --port 3030
```

新环境通过 `python -m app.manage bootstrap-admin --email <管理员邮箱>` 交互创建管理员。迁移已有数据库时保留管理员记录及配套服务器秘密。首次使用仍通过网站向导配置。虚拟机网络访问由目标环境设置，公开部署、域名与 TLS 在取得用户授权后实施。

Ubuntu 实际安装运行与真实 Notion、模型、邮件服务仍待目标环境和用户凭据验收。当前自动化覆盖真实 PostgreSQL 事务与浏览器操作，外部传输采用明确的测试替身。
