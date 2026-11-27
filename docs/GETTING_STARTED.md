# 安装、配置和启动

本指南从空数据库启动学习者网站、管理员控制台和 FastAPI。准备 Python 3.13、Node.js 22 至 24、pnpm 12.18.0、PostgreSQL 17 及其命令行工具。已有数据库时，先备份，再由数据库所有者运行版本迁移，保留原 `SECRET_KEY` 和管理员账号。

## Windows 本机

将源码放在当前 Windows 账号拥有写权限的目录。建议选择纯英文路径，例如 `C:\dev\AI-Memory-Learing`，以避免本机 PostgreSQL 工具的路径编码问题。以下命令从仓库根目录执行。确认 `python --version` 显示 3.13，按实际安装位置修改 `--pg-bin`。

```powershell
python -m venv .venv
$python = '.\.venv\Scripts\python.exe'
& $python -m pip install -r backend/requirements.lock
& $python -m pip install --no-deps -e ./backend
pnpm --dir frontend install --frozen-lockfile
pnpm --dir apps/admin-web install --frozen-lockfile
& $python scripts/init-local-db.py --pg-bin 'C:/Program Files/PostgreSQL/17/bin' --migrate
& $python -m app.manage bootstrap-admin --email admin@example.com
```

把 `admin@example.com` 换成你的管理员邮箱，在提示中输入至少 10 字符的密码。初始化脚本在 `127.0.0.1:55433` 启动专用 PostgreSQL，建立开发库 `memory_os_dev` 和测试库 `memory_os_test`，并把开发库连接串及随机 `SECRET_KEY` 写入 `backend/.env`。沿用自动生成的配置时，从根目录启动脚本前保持根目录 `.env` 缺省。启动脚本优先读取根目录 `.env`。再次启动电脑后，可重复执行同一个数据库初始化命令恢复专用数据库进程。

从仓库根目录打开三个 PowerShell 窗口，各运行一组命令。开发模式可将 `build` 和 `start` 两行替换为各启动脚本的 `-Mode dev`。

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start-backend.ps1
```

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start-frontend.ps1 -Mode build
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start-frontend.ps1 -Mode start -Port 3030
```

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start-admin.ps1 -Mode Build
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start-admin.ps1 -Mode Start
```

## Linux / Ubuntu 本机

安装上述运行时与 PostgreSQL 工具后，从仓库根目录以普通用户执行。将 `pg_config --bindir` 替换为本机 PostgreSQL 17 的 `bin` 路径也可以。

```bash
python3.13 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements.lock
.venv/bin/python -m pip install --no-deps -e ./backend
pnpm --dir frontend install --frozen-lockfile
pnpm --dir apps/admin-web install --frozen-lockfile
.venv/bin/python scripts/init-local-db.py --pg-bin "$(pg_config --bindir)" --migrate
.venv/bin/python -m app.manage bootstrap-admin --email admin@example.com
```

分别在三个终端从仓库根目录执行这些命令。`Ctrl+C` 可以停止各前台服务。

```bash
.venv/bin/python -m app.server app.main:app --host 127.0.0.1 --port 8000
```

```bash
pnpm --dir frontend build
pnpm --dir frontend start --hostname 127.0.0.1 --port 3030
```

```bash
pnpm --dir apps/admin-web build
pnpm --dir apps/admin-web start
```

## 入口与功能配置

| 地址 | 操作 |
| --- | --- |
| `http://127.0.0.1:8000/health/ready` | 确认 API 和数据库迁移就绪 |
| `http://127.0.0.1:3030/` | 学习者注册或登录。第一次登录进入配置向导 |
| `http://127.0.0.1:3001/login` | 使用已创建的管理员账号登录 |
| `http://127.0.0.1:3001/demo` | 使用示例数据查看独立控制台 |

- **Notion**。把资料库分享给 Notion Integration，在网站保存 Integration Token，再选择资料库、学科和状态字段映射。
- **模型**。按需填写供应商、模型名和 API Key。调用需同时满足系统环境变量 `AI_BILLING_APPROVED=true` 和该用户在网站的计费授权。
- **邮件**。填写收件邮箱、提醒时间、发件账号和 SMTP 授权码，按需测试。
- **自动任务**。`BACKGROUND_TASKS_ENABLED` 默认为 `false`。确认外部配置和授权后再启用预期的 Notion、模型、复习任务和邮件处理。

## 使用自备数据库或域名

运行 FastAPI 至少需要 `DATABASE_URL` 和随机的 `SECRET_KEY`。数据库连接串格式为 `postgresql+psycopg://USER:PASSWORD@HOST:5432/DBNAME`，密码含保留字符时要做 URL 编码。使用数据库所有者的连接从 `backend/` 执行 `python -m alembic upgrade head`，随后为 FastAPI 换回权限受限的应用连接。空库也可由所有者执行 [`database/schema.sql`](../database/schema.sql)，并按[初始化脚本](../scripts/init-local-db.py)为运行角色授予所需权限。`SECRET_KEY` 须为至少 32 字符的随机值，单独保管，恢复原有数据库时沿用与密文配套的密钥。

`BACKEND_API_URL` 和 `ADMIN_BACKEND_URL` 分别指定两个 Next.js 站点的内部 FastAPI 地址。HTTPS 部署时设置 FastAPI 的 `APP_ENV=production` 和 `PUBLIC_APP_URL`，把浏览器可见的管理员地址设为 `ADMIN_PUBLIC_ORIGIN`，并设置 `ADMIN_COOKIE_SECURE=true`。在学习者站构建时注入 `NEXT_PUBLIC_ADMIN_APP_URL`，让侧栏链接到实际管理员域名。反向代理负责 HTTPS，PostgreSQL 和 FastAPI 保持在内网。完整参数见[环境变量示例](../.env.example)。
