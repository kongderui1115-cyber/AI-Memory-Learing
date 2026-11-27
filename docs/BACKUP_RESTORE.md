# 在独立 PostgreSQL 数据库中验证恢复

使用当前版本或更新版本的 PostgreSQL 客户端。`backup.ps1` 的默认 `custom` 格式和可选 `tar` 格式由 `restore.ps1` 支持。纯 SQL 格式需要单独的 `psql` 恢复流程。只使用来源可信的备份，数据库归档可以包含在恢复时执行的 SQL。

1. 由数据库管理员创建新的空库，例如 `memory_os_rehearsal_restore`，并准备拥有该库、权限仅用于恢复的账号。将应用连接继续指向原库，停止对恢复库的其他连接。
2. 通过受保护的运行环境提供 `RESTORE_DATABASE_URL`，例如 `postgresql://<user>:<url-encoded-password>@<host>:<port>/memory_os_rehearsal_restore`。从现有应用环境或项目 `.env` 读取 `DATABASE_URL`，用于拦截与应用库同名的目标。远程连接通过标准 libpq 环境变量设置证书和 `PGSSLMODE`。连接串中的查询参数不受脚本支持。
3. 在 Windows PowerShell 5.1 中，运行以下命令。`pg_restore` 和 `psql` 可以来自 `PATH`，也可以使用 `-PgRestorePath` 和 `-PsqlPath` 指定完整路径。

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File '.\scripts\restore.ps1' -BackupFile '.\backups\memory-os.dump'
```

脚本先读取归档目录，再通过 PostgreSQL 系统目录和连接状态核对目标是空库。恢复在单一事务中执行，遇到错误回滚。重复执行时，如果目标已有对象，脚本拒绝继续。旧版 `-IUnderstandThisOverwritesData` 参数已移除。

恢复成功后，核对 Alembic 版本、关键表记录量、租户关键数据和复习记录。服务器加密密钥需与备份对应，密钥和数据库归档应分别由维护人员保管。将验证后的数据库用于应用需要另行安排切换与回滚。
