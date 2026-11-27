# 认证与凭据

## 学习者请求

1. 首页用邮箱和密码调用 `POST /api/v1/auth/token`，注册调用 `POST /api/v1/auth/register`。Next.js 把同源 `/api/v1/*` 请求转发给 FastAPI。公开注册创建 `user` 角色，注册成功后也会签发登录会话。[学习者入口](../frontend/components/portal/Welcome.tsx)、[代理配置](../frontend/next.config.mjs)、[认证 API](../backend/app/api/auth.py)、[注册 API](../backend/app/api/workspace.py)
2. FastAPI 对邮箱和来源 IP 做持久化限流，再用 Argon2 校验数据库中的密码哈希。默认连续失败 6 次锁定对应账号 15 分钟，IP 也有独立阈值。认证成功后创建数据库会话，签发 HS256 JWT，写入 `sub`、`sid`、`iat`、`exp`、`iss` 和 `aud`，并在 PostgreSQL 中保存 JWT 的 SHA-256 摘要和会话有效期。会话时长由 `ACCESS_TOKEN_EXPIRE_MINUTES` 控制。[账号服务](../backend/app/services/accounts.py)、[密码和 JWT](../backend/app/security.py)、[默认设置](../backend/app/config.py)
3. 成功响应会设置 `memory_session` Cookie，使用 `HttpOnly`、`SameSite=Lax` 和 `Path=/`，生产环境或 HTTPS 请求还会启用 `Secure`。认证接口的 JSON 同时提供 `access_token`，供直接调用 API 的客户端使用。学习者正式界面依赖 Cookie，登录后用 `/me` 更新身份并清理旧版浏览器 token 缓存。API 客户端可以发送 `Authorization: Bearer …`。[Cookie 设置](../backend/app/api/workspace.py)、[学习者会话](../frontend/components/AuthProvider.tsx)
4. `current_user` 优先采用 Bearer token，否则读取 Cookie。使用 Cookie 的写请求须带 `X-Memory-Client: web`。服务端校验 JWT 签名、有效期、签发者和受众，再检查数据库里的会话 ID、用户、令牌摘要、到期和撤销状态以及账号是否启用。学习者页面每分钟发送会话心跳以记录在线状态。退出撤销当前会话，修改密码撤销该用户的会话，令牌到期后重新登录。[请求鉴权](../backend/app/api/dependencies.py)、[会话服务](../backend/app/services/accounts.py)、[页面心跳](../frontend/components/AuthProvider.tsx)

## 管理员请求

1. 管理员站调用自己的 `/api/admin-gateway/login`。Next.js 网关在服务端向同一 FastAPI 交换 JWT，调用 `/me` 验证 `admin` 角色，然后把 JWT 放在独立的 `memory_admin_session` HttpOnly Cookie 中。登录页面收到管理员资料。普通用户访问该入口会被拒绝，网关尝试撤销为该次登录创建的会话。[管理端网关](../apps/admin-web/app/api/admin-gateway/%5Baction%5D/route.ts)
2. 后续管理请求由网关从管理员 Cookie 取 token，并在服务端以 Bearer 发送给 FastAPI。网关对写请求校验浏览器 `Origin` 和 `X-Admin-Client: console`。FastAPI 的管理员依赖独立核验账号角色，跨用户读写按相关接口记录审计。[管理端网关](../apps/admin-web/app/api/admin-gateway/%5Baction%5D/route.ts)、[管理员鉴权](../backend/app/api/dependencies.py)、[管理 API](../backend/app/api/admin.py)
3. 新库的第一个管理员通过 `python -m app.manage bootstrap-admin` 创建。密码可在终端交互输入，也可由服务端生成并写进指定的私有文件。[管理员命令](../backend/app/manage.py)

## 凭据与恢复

| 数据 | 处理方式 |
| --- | --- |
| 用户和管理员密码 | 以 Argon2 哈希写入 PostgreSQL，登录时验证哈希。 |
| 登录 JWT | 浏览器通过对应站点的 HttpOnly Cookie 持有，API 客户端可用 Bearer。数据库持有摘要及可撤销的会话状态。 |
| Notion Token、模型 Key、SMTP 授权码等用户设置 | 以 Fernet 认证加密后保存到 `user_secrets`。加密密钥由 `SECRET_KEY`、用户 ID 和凭据名称通过 HMAC-SHA-256 派生。设置读取接口提供是否已配置等状态，后台在执行获准的集成任务时解密。 |
| `SECRET_KEY` 和数据库连接串 | 由服务器环境或私有 `.env` 提供。恢复数据库时，原密文依赖与它配套的 `SECRET_KEY`。更换此密钥会使旧 JWT 失效，并需要重新保存或迁移已有加密凭据。 |

实现见[凭据服务](../backend/app/services/credentials.py)、[用户设置](../backend/app/services/workspace.py)、[环境配置](../backend/app/config.py)和[数据库结构](../database/schema.sql)。
