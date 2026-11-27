# 桌面界面预览

## 当前正式网站入口 · 2026-11-18

首页/提供注册登录，/onboarding提供可恢复首次配置，/app提供真实学习、复习、来源、邮件与设置。管理员登录后在侧栏进入真实用户知识、复习及会话查询。网页同源调用后端，普通用户在设置填写SMTP、Notion和模型凭据。

本机在项目根目录分别运行scripts/start-backend.ps1和scripts/start-frontend.ps1 -Mode start -Port 3030。源码修改后重新构建，构建时停止当前Next.js进程。完整环境与Ubuntu步骤见backend/RUN_BACKEND.md。

本轮类型检查及20页生产构建通过，pnpm test:portal的10项流程通过。该测试使用专用PostgreSQL与明确的外部传输替身，启动条件见backend/tests_backend/portal_server.py。原预览19项和七页管理11项通过。下面保留的/preview说明适用于示例界面。

---

此阶段交付可运行的前端页面，所有 /preview 数据均为示例。

## 启动

在 frontend 目录运行以下命令。

```powershell
pnpm install --fetch-timeout=600000
pnpm dev --hostname 127.0.0.1 --port 3030
```

浏览器访问 http://127.0.0.1:3030/preview 。手机推送阅读页面为 /preview/push 。真实登录入口为 /dashboard 。

## 数据接入

components/desktop/preview-data.ts 的 DesktopWorkspaceData 定义当前界面所需数据。页面组件通过 data 属性接收数据。示例数据集中在 previewWorkspace，后续由后端接口适配为相同的展示模型。

Notion 提供章节、正文、学习状态与来源；AI 提供提取和解析；复习任务、完成历史、调度和统计由后端管理。章节状态与日期在预览数据中定义。

预览交互使用浏览器 localStorage 的 memory-os-ui-preview-v1。新增学科、完成复习、默认模型和推送偏好仅用于界面验收。真实账号、模型调用、Notion 授权与消息发送另行验收。

## 图片

横幅图片来自 Unsplash，已存储在 public/images/mountain-dawn.jpg 。来源为 https://images.unsplash.com/photo-1499336315816-097655dcfbda 。
## 浏览器回归

安装依赖后先在单独终端启动预览，再执行以下命令。默认使用本机 Microsoft Edge。

```powershell
pnpm typecheck
pnpm build
pnpm start --hostname 127.0.0.1 --port 3030
```

另开终端运行测试。

```powershell
pnpm test:preview
```

PREVIEW_BASE_URL 可指定测试地址，PREVIEW_BROWSER_CHANNEL 可指定已安装的 Playwright 浏览器渠道，PREVIEW_SCREENSHOT_DIRECTORY 可指定截图目录。默认截图写入已忽略的 test-results/desktop-preview。测试使用独立浏览器上下文，不提交登录表单，也不发送外部消息。

本机已验证 Node 24.18.0 和 pnpm 12.18.0。生产构建与开发服务器共用 .next，切换运行模式时先停止当前实例再构建。

## 管理员页面

/preview/admin/users可按示例用户查看复习完成量、逾期、复习记录和知识库。支持用户搜索、状态筛选、学科筛选以及知识解析详情。管理示例位于components/desktop/admin-preview-data.ts，经adminUsers属性单独传入。用户切换会清理上一用户的详情和筛选。正式管理员权限与真实数据查询由后端接线实现。

## 独立管理员后台与Ubuntu运行

管理员后台入口为 /preview/admin，七页包含管理首页、AI模型、数据源、通知、记忆策略、用户与会话、安全日志。用户与会话页可筛选用户、登录时段与在线状态，并查看对应用户的复习和知识库。

前端技术栈继续使用Next.js15、React19与TypeScript。模型管理包含DeepSeek、Kimi、OpenAI、Claude及兼容供应商，支持增删改、默认模型、启用开关、用途配置及连接测试演示。通知模板支持知识点、学科、次数、阶段、正文、回忆问题及Notion和复习入口占位符。

管理演示配置位于memory-os-admin-demo-v1本地存储键。密钥仅用于弹窗输入体验，保存与关闭时清空，持久化内容为配置元数据和演示标记。真实服务状态、在线会话和安全日志均在界面中明确标为示例。

Windows与Ubuntu的安装、构建、访问地址及浏览器测试步骤见RUN_ON_UBUNTU.md。

## 管理员添加账号

使用管理员身份登录后，在/app?view=admin点击添加用户。填写称呼、邮箱、至少十位有效字符的初始密码、确认及角色，默认普通用户。新账号登录后进入首次向导。

独立浏览器验收可设置NEXT_BUILD_DIR=.next-test与BACKEND_API_URL指向测试后端，构建后使用相同配置启动3031。测试后端仅连接专用测试数据库，通过PORTAL_TEST_PORT选择8001。默认生产构建仍为.next。


## 正式学习空间升级 · 2026-11-18

正常登录后进入/app，包含仪表盘、章节、复习、知识、学科、同步、日历、统计、历史、助手、邮件和设置。内容来自真实用户API，预览示例仍独立位于/preview。新增组件为components/portal/LearningExperience.tsx；统计契约位于lib/workspace.ts。

新增回归命令为pnpm test:learning。与pnpm test:portal一样，需要先按项目测试说明启动仅使用memory_os_test的portal_server，测试前端默认3031并代理到8001。不得将测试脚本指向正式数据入口。截图输出可通过PORTAL_SCREENSHOT_DIRECTORY设置。正常启动仍使用scripts/start-frontend.ps1 -Mode start -Port 3030。AI助手当前为真实知识检索与复习入口，开放式对话另行实现。


### 可复现的隔离浏览器验收

先确保独立_test数据库已迁移。在项目根目录启动专用测试后端（默认8001），脚本读取TEST_DATABASE_URL或私有.local-test/test.env，只允许测试库、关闭后台并使用隔离外部传输：

```powershell
& '.\.venv\Scripts\python.exe' scripts/start-portal-test-server.py
```

另一个终端进入frontend目录，使用独立构建目录，避免覆盖正在使用的正式.next：

```powershell
$env:NEXT_BUILD_DIR = '.next-test'
$env:BACKEND_API_URL = 'http://127.0.0.1:8001'
pnpm build
pnpm start --hostname 127.0.0.1 --port 3031
```

第三个终端进入frontend目录执行pnpm test:learning与pnpm test:portal。旧预览检查可设置PREVIEW_BASE_URL=http://127.0.0.1:3031后执行pnpm test:preview和pnpm test:admin。测试账户和记录保留于专用测试库，测试脚本不得指向正式服务。两个新测试会在明确的测试服务器中使用独立客户端身份，正式注册限流保持不变。
