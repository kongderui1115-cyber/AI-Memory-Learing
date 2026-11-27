# infra/ — Linux 云服务器后台任务替换方案（DEVOPS-04 / FR-12）

> Owner: `devops-dev` ｜ 状态：**静态交付，⛔ 未演练**
> 本目录用于「未来迁移 Linux 云服务器」时，把 Windows 原生后台任务替换为系统级调度。
> 当前项目仍以 Windows 原生运行（FR-11），**本目录不作为当前运行前提**，容器化同样为可选而非必需。

## 1. 与 Windows 方案的对应关系

| 后台任务 | Windows 原生 | Linux systemd | Linux cron |
| --- | --- | --- | --- |
| Notion 定时增量同步 | 任务计划 `AILMOS-NotionSync` → `run-worker.ps1 -Job sync-notion` | `ailmos-notion-sync.timer` → `ailmos-worker@sync-notion.service` | 每小时一行 |
| 每日复习任务生成 | `AILMOS-DailyTasks` → `-Job generate-daily-tasks` | `ailmos-daily-tasks.timer` → `ailmos-worker@generate-daily-tasks.service` | `5 0 * * *` |
| 每日推送 | `AILMOS-DailyDigest` → `-Job send-daily-digest` | `ailmos-daily-digest.timer` → `ailmos-worker@send-daily-digest.service` | `0 8 * * *` |
| 后端常驻 | `start-all.ps1` / `start-backend.ps1` | `ailmos-backend.service` | — |
| 前端常驻 | `start-all.ps1` / `start-frontend.ps1` | `ailmos-frontend.service` | — |

三种 Windows 形态（任务计划单次触发 / `run-worker.ps1 -Loop` 常驻循环 / 业务侧 APScheduler）
与两种 Linux 形态（systemd timer / cron）调用的是**同一个业务 CLI**：
`python -m app.worker <job>`（可用 `WORKER_MODULE` 覆盖）。因此系统调度器是可替换适配层，
业务代码不绑定操作系统，符合 FR-12「同一份代码仅换配置即可运行」。

## 2. 目录内容

```text
infra/
├─ README.md                          # 本说明
├─ systemd/
│  ├─ ailmos-backend.service          # uvicorn 常驻服务
│  ├─ ailmos-frontend.service         # Next.js 常驻服务（需先 pnpm build）
│  ├─ ailmos-worker@.service          # oneshot 模板，%i = 任务名
│  ├─ ailmos-notion-sync.timer        # 周期同步（OnUnitActiveSec=60min）
│  ├─ ailmos-daily-tasks.timer        # 每天 00:05 UTC
│  └─ ailmos-daily-digest.timer       # 每天 08:00 UTC
└─ cron/
   └─ ailmos.crontab                  # cron 替代方案（与 timer 二选一）
```

## 3. 启用步骤（示例，未演练）

```bash
# 0) 前置：同一份代码部署到 /srv/ailmos，创建 venv、安装依赖、执行 Alembic 迁移
sudo install -d -o ailmos -g ailmos /var/log/ailmos /etc/ailmos
sudo install -m 600 /dev/null /etc/ailmos/env        # 填入 DATABASE_URL / SECRET_KEY / 外部凭据
sudo cp infra/systemd/*.service infra/systemd/*.timer /etc/systemd/system/
sudo systemctl daemon-reload

# 1) 常驻服务（前端需先 pnpm build）
sudo systemctl enable --now ailmos-backend.service
sudo systemctl enable --now ailmos-frontend.service

# 2) 定时任务（timer 与 cron 二选一）
sudo systemctl enable --now ailmos-notion-sync.timer
sudo systemctl enable --now ailmos-daily-tasks.timer
sudo systemctl enable --now ailmos-daily-digest.timer
systemctl list-timers 'ailmos-*'

# 或改用 cron（先确认未启用上述 timer）
sudo crontab -u ailmos infra/cron/ailmos.crontab
```

`/etc/ailmos/env` 与 Windows 的 `.env` 等价：只含配置，权限 `600`，**不入库、不入 Git、不写日志**。
unit 里的 `/srv/ailmos`、`/usr/bin/pnpm`、`ailmos` 用户组均为示例，迁移时只需替换路径与账号，
不需要改业务代码。unit 中端口/入口通过 `${APP_HOST}`、`${APP_PORT}`、`${UVICORN_APP}`、
`${FRONTEND_PORT}` 从 EnvironmentFile 读取，不写死。

## 4. 时间与时区

- 业务时间统一 UTC 带时区存储；`DAILY_TASKS_AT` / `DAILY_DIGEST_AT` 按 UTC 解释。
- systemd timer 用 `OnCalendar=... UTC`；cron 建议 `CRON_TZ=UTC`。
- Windows 任务计划用本地时间触发，业务内部按 UTC 处理；跨时区部署时注意换算。

## 5. ⛔ 未演练声明（如实）

- 本机环境为 Windows 10.0.22631，**无 Docker、无 WSL**，未安装 PostgreSQL 客户端工具，
  `5432` 上的未知实例凭据未确认（BLK-05）。
- 本目录所有 unit / timer / crontab 均为**静态示例**，本次开发：
  - 未在 Linux 上执行过 `systemctl daemon-reload` / `enable --now` / `crontab`；
  - 未执行过 Alembic 迁移、`pnpm build`、任何备份恢复；
  - 未连接任何数据库、未调用任何外部 API、未产生任何费用。
- 因此 `DEPLOYMENT.md` 的 Linux 迁移清单中每一项均标注 **⏳ 未演练**，
  不得写成已通过。演练后须把真实命令与输出填入 `DEPLOYMENT.md` / `TEST_REPORT.md` 并更新本声明。
