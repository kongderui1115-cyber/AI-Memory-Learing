# Ubuntu 虚拟机运行前端

## 完整应用迁移更新 · 2026-11-18

当前网站已连接后端，正常入口为/，首次配置为/onboarding，真实工作台为/app。完整应用需要Python3.13、PostgreSQL以及本文件列出的Node/pnpm环境。前端采用同源API转发，维护者设置BACKEND_API_URL及邮件链接PUBLIC_APP_URL。完整迁移与数据库/秘密恢复步骤见backend/RUN_BACKEND.md。

下文保留早期前端独立演示安装步骤，/preview与/preview/admin仍为演示入口。Ubuntu目标环境实际运行尚待验收。

---

本包为 AI Learning Memory OS 的前端源码，包含普通用户页面、七页独立管理员后台和手机推送阅读页。所有 /preview 页面使用明确标识的模拟数据，配置交互保存在浏览器中。

## 环境

- Node.js 22 或 24，package.json 声明 >=22 <25。
- pnpm 12.18.0，与 packageManager 字段一致。
- 支持现代 Chrome、Edge 或 Firefox 的电脑浏览器。

已有 Node.js 后可安装 pnpm。

```bash
npm install --global pnpm@12.18.0
node --version
pnpm --version
```

## 在 Ubuntu 中安装和运行

将源码包复制到虚拟机并解压，进入 ai-learning-memory-os-frontend 目录。

```bash
unzip ai-learning-memory-os-frontend-20261116.zip
cd ai-learning-memory-os-frontend
pnpm install --frozen-lockfile
pnpm typecheck
pnpm build
pnpm start --hostname 127.0.0.1 --port 3030
```

在虚拟机浏览器打开 http://127.0.0.1:3030/preview ，管理员后台为 http://127.0.0.1:3030/preview/admin 。前端演示通过 Node.js 启动，普通用户与管理员均可直接查看。

需要从 Windows 主机访问虚拟机时，在虚拟机中使用以下启动命令，浏览器访问 http://虚拟机内网IP:3030/preview/admin 。

```bash
pnpm start --hostname 0.0.0.0 --port 3030
```

## 七页管理员后台

| 页面 | 地址 |
| --- | --- |
| 管理首页 | /preview/admin |
| AI模型管理 | /preview/admin/models |
| 数据源管理 | /preview/admin/sources |
| 通知管理 | /preview/admin/notifications |
| 记忆策略管理 | /preview/admin/memory |
| 用户与会话 | /preview/admin/users |
| 安全日志 | /preview/admin/security |

用户与会话页包含登录起止时间筛选、在线状态、退出时间、最后活跃时间，以及逐用户的复习情况和知识库。在线状态采用页面中标注的演示快照。

## 本地开发

```bash
pnpm dev --hostname 127.0.0.1 --port 3030
```

开发服务器和生产构建使用同一 .next 目录。切换模式时先停止当前进程，再运行对应命令。

## 自动化测试

Windows 本机使用 Edge。运行中的预览服务器默认使用3030端口。

```powershell
pnpm test:preview
pnpm test:admin
```

Ubuntu 可安装 Playwright Chromium 后运行同一批测试。

```bash
pnpm exec playwright install --with-deps chromium
PREVIEW_BROWSER_CHANNEL=chromium pnpm test:preview
PREVIEW_BROWSER_CHANNEL=chromium pnpm test:admin
```

PREVIEW_BASE_URL 可指定其他端口。测试截图默认保存到 test-results，PREVIEW_SCREENSHOT_DIRECTORY 可指定输出目录。

## 验证范围

当前已在 Windows 本机完成锁文件安装、类型检查、生产构建、浏览器页面与交互验收，以及160处本地导入路径大小写检查。Ubuntu虚拟机的实际安装与启动需要在目标系统中执行上述步骤验证。

AI连接测试、Notion同步、消息发送、在线状态、安全日志和管理员身份均采用前端演示。API Key输入为密码形式，关闭或保存弹窗后清空，浏览器仅持久化演示配置元数据。

已补充内网HTTP预览的演示标识兼容处理，浏览器回归在禁用randomUUID的环境下验证新增模型、学科和演示记录。
