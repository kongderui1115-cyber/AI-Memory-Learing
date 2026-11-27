# AI Learning Memory OS 管理控制台

本应用独立运行于 `http://127.0.0.1:3001`。学习者应用在当前项目中保留 `frontend/` 与本机 `3030` 端口。两套应用使用同一 FastAPI 和 PostgreSQL。管理员控制台将访问发送给自己的同源网关，网关再连接统一 API。

## Windows 启动

从项目工作树根目录执行，需 Node.js 22–24 和 pnpm。

```powershell
pnpm --dir apps/admin-web install --frozen-lockfile
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start-admin.ps1
```

打开 [管理员登录](http://127.0.0.1:3001/login) 或 [演示控制台](http://127.0.0.1:3001/demo)。开发终端按 `Ctrl+C` 停止当前进程。端口冲突时为启动脚本传入 `-Port 3002` 等空闲端口。生产构建使用同一脚本的 `-Mode Build`，生成后用 `-Mode Start` 启动。

## Linux / Ubuntu

```bash
pnpm --dir apps/admin-web install --frozen-lockfile
pnpm --dir apps/admin-web build
pnpm --dir apps/admin-web start
```

服务器的反向代理可以将管理域名转发至 `127.0.0.1:3001`。设置 `ADMIN_PUBLIC_ORIGIN` 为浏览器所使用的完整 HTTPS 源，设置 `ADMIN_COOKIE_SECURE=true`，由代理终止 TLS。私有 FastAPI 地址通过 `ADMIN_BACKEND_URL` 在服务端注入，默认 `http://127.0.0.1:8000`。网关保留 FastAPI 的角色检查和登录限流。独立部署时，FastAPI 当前审计中的来源 IP 会记录代理链看到的地址，配置可信反向代理后再依该字段判断客户端地址。

## 数据模式

|模式|入口|数据与操作|
|---|---|---|
|真实|从 `/login` 登录后访问 `/`|FastAPI 验证管理员会话。显示学习趋势、复习完成率、分学科回忆表现、FSRS 历史对照和按类型汇总的任务终态。审计、用户及登录会话、知识与复习记录、API 和数据库就绪也来自统一后端。密码修改调用现有真实 API。|
|演示|`/demo` 及其子路径|使用内存夹具。更改应用于当前页面会话，刷新后复位。连接测试、同步、测试发送、策略模拟、任务触发等展示交互过程。敏感输入始终使用密码字段。|

真实模式可管理学习者账号，查看模型和学科策略，调整模型启停/默认项、修改已有学科策略、运行记忆模拟、查看来源与同步历史、把 Notion 同步请求加入队列，以及查询通知投递、任务运行和主机/API 指标。模型就绪检查是本地检查，真实供应商连通性和最终送达分别验收。

数据库备份需由部署者配置 `ADMIN_BACKUP_DIRECTORY` 和 `ADMIN_PG_DUMP_PATH`。配置生效后，管理员可以创建备份并查看归档元数据。数据库连接必须显式提供主机、端口、库名及用户。归档文件保存在服务器私有目录，恢复使用 [独立空库流程](../../docs/BACKUP_RESTORE.md)。

与外部服务授权、调度及待扩展管理操作有关的范围见 [管理员 API 契约](API_CONTRACTS.md)。

## 验证

```powershell
pnpm --dir apps/admin-web typecheck
pnpm --dir apps/admin-web build
$env:ADMIN_TEST_URL = 'http://127.0.0.1:3001'
node apps/admin-web/tests/console.e2e.cjs
```

浏览器测试复用学习者项目已安装的 Playwright 和系统 Edge。若 Playwright 位于其他目录，可设置 `ADMIN_PLAYWRIGHT_PATH`。另可设置 `ADMIN_SCREENSHOT_DIR` 保存图表截图。

真实认证回归需先运行现有的 `scripts/start-portal-test-server.py`，并让独立的测试控制台在 3002 指向 8001。该脚本强制要求数据库名以 `_test` 结尾。设置 `ADMIN_TEST_URL=http://127.0.0.1:3002`、`ADMIN_TEST_LIVE=1` 后运行同一测试。

跨站读写验收可额外在 3031 启动指向 8001 的学习者端隔离构建，然后设置 `ADMIN_TEST_LEARNER_URL=http://127.0.0.1:3031`。测试从学习者界面保存学习与复习，再刷新管理员总览比较真实统计增量。
