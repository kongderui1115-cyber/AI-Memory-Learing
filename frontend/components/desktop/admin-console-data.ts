export type AdminPage =
  | "dashboard"
  | "models"
  | "sources"
  | "notifications"
  | "memory"
  | "users"
  | "security";
export const adminNavigation: { id: AdminPage; label: string }[] = [
  { id: "dashboard", label: "管理首页" },
  { id: "models", label: "AI 模型管理" },
  { id: "sources", label: "数据源管理" },
  { id: "notifications", label: "通知管理" },
  { id: "memory", label: "记忆策略管理" },
  { id: "users", label: "用户与会话" },
  { id: "security", label: "安全日志" },
];
export const adminHref = (page: AdminPage) =>
  page === "dashboard" ? "/preview/admin" : `/preview/admin/${page}`;

export interface ModelConfig {
  id: string;
  name: string;
  provider: string;
  baseUrl: string;
  model: string;
  enabled: boolean;
  configured: boolean;
  purposes: string[];
}
export interface SourceConfig {
  id: string;
  name: string;
  owner: string;
  database: string;
  automatic: boolean;
  frequency: string;
  success: number;
  failed: number;
  lastSync: string;
}
export interface ChannelConfig {
  id: string;
  name: string;
  description: string;
  enabled: boolean;
  configured: boolean;
}
export interface SecurityEvent {
  id: string;
  time: string;
  actor: string;
  action: string;
  target: string;
  level: "信息" | "警告" | "高风险";
  result: string;
  ip: string;
}
export interface LoginSession {
  id: string;
  userId: string;
  name: string;
  login: string;
  logout?: string;
  lastActive: string;
  online: boolean;
  ip: string;
  device: string;
}
export interface AdminDemoState {
  models: ModelConfig[];
  defaultModel: string;
  uses: Record<string, string>;
  sources: SourceConfig[];
  channels: ChannelConfig[];
  template: string;
  intervals: string;
  retention: number;
  maxInterval: number;
  defaultStrategy: string;
  securityEvents: SecurityEvent[];
}

export const defaultTemplate = `{{subject}} · {{title}}
第 {{review_count}} 次复习 · {{memory_stage}}

{{content}}

主动回忆
{{question}}

Notion 原页面 {{notion_url}}
开始复习 {{review_url}}`;

export const initialAdminDemo: AdminDemoState = {
  models: [
    {
      id: "model-deepseek",
      name: "DeepSeek 主模型",
      provider: "DeepSeek",
      baseUrl: "https://api.deepseek.com",
      model: "deepseek-chat",
      enabled: true,
      configured: true,
      purposes: ["知识提取", "答案评价"],
    },
    {
      id: "model-kimi",
      name: "Kimi 长文阅读",
      provider: "Kimi",
      baseUrl: "https://api.moonshot.cn/v1",
      model: "待选择模型",
      enabled: true,
      configured: false,
      purposes: ["章节总结"],
    },
    {
      id: "model-openai",
      name: "OpenAI",
      provider: "OpenAI",
      baseUrl: "https://api.openai.com/v1",
      model: "待选择模型",
      enabled: false,
      configured: false,
      purposes: ["学习助手"],
    },
    {
      id: "model-claude",
      name: "Claude",
      provider: "Claude",
      baseUrl: "https://api.anthropic.com",
      model: "待选择模型",
      enabled: false,
      configured: false,
      purposes: [],
    },
    {
      id: "model-compatible",
      name: "兼容 API",
      provider: "OpenAI 兼容",
      baseUrl: "",
      model: "待配置",
      enabled: false,
      configured: false,
      purposes: [],
    },
  ],
  defaultModel: "model-deepseek",
  uses: {
    知识提取: "model-deepseek",
    章节总结: "model-kimi",
    答案评价: "model-deepseek",
    学习助手: "model-deepseek",
  },
  sources: [
    {
      id: "source-windows",
      name: "Windows 内核笔记库",
      owner: "zi rui",
      database: "Windows 内核 / 章节",
      automatic: true,
      frequency: "30",
      success: 32,
      failed: 0,
      lastSync: "11-13 19:42",
    },
    {
      id: "source-english",
      name: "英语学习",
      owner: "林予",
      database: "英语 / 课程与语法",
      automatic: true,
      frequency: "60",
      success: 18,
      failed: 1,
      lastSync: "11-13 19:40",
    },
    {
      id: "source-history",
      name: "历史阅读笔记",
      owner: "闻静",
      database: "历史 / 章节",
      automatic: false,
      frequency: "120",
      success: 12,
      failed: 0,
      lastSync: "11-13 18:05",
    },
  ],
  channels: [
    {
      id: "pushplus",
      name: "PushPlus",
      description: "微信消息推送服务",
      enabled: true,
      configured: true,
    },
    {
      id: "wechat",
      name: "微信官方接入",
      description: "公众号等官方授权渠道",
      enabled: false,
      configured: false,
    },
    {
      id: "wecom",
      name: "企业微信",
      description: "应用消息与群机器人",
      enabled: false,
      configured: false,
    },
    {
      id: "dingtalk",
      name: "钉钉",
      description: "应用消息与机器人",
      enabled: true,
      configured: true,
    },
    {
      id: "telegram",
      name: "Telegram",
      description: "Bot 通知",
      enabled: false,
      configured: false,
    },
    {
      id: "email",
      name: "邮件",
      description: "SMTP 学习摘要与复习内容",
      enabled: false,
      configured: false,
    },
    {
      id: "feishu",
      name: "飞书",
      description: "应用与机器人扩展",
      enabled: false,
      configured: false,
    },
    {
      id: "bark",
      name: "Bark",
      description: "iPhone 推送扩展",
      enabled: false,
      configured: false,
    },
  ],
  template: defaultTemplate,
  intervals: "1, 2, 4, 7, 15, 30",
  retention: 90,
  maxInterval: 365,
  defaultStrategy: "FSRS",
  securityEvents: [
    {
      id: "event-1",
      time: "2026-11-13 19:59:12",
      actor: "zi rui",
      action: "查看用户资料",
      target: "林予的复习概览",
      level: "信息",
      result: "允许（示例）",
      ip: "192.0.2.10",
    },
    {
      id: "event-2",
      time: "2026-11-13 19:55:40",
      actor: "林予",
      action: "登录成功",
      target: "浏览器会话",
      level: "信息",
      result: "会话建立（示例）",
      ip: "192.0.2.21",
    },
    {
      id: "event-3",
      time: "2026-11-13 19:43:08",
      actor: "学习者示例",
      action: "登录失败",
      target: "账号登录",
      level: "警告",
      result: "密码验证失败（示例）",
      ip: "198.51.100.8",
    },
    {
      id: "event-4",
      time: "2026-11-13 19:42:35",
      actor: "学习者示例",
      action: "登录限制",
      target: "账号登录",
      level: "高风险",
      result: "连续失败触发限时限制（示例）",
      ip: "198.51.100.8",
    },
    {
      id: "event-5",
      time: "2026-11-13 19:35:00",
      actor: "普通用户示例",
      action: "权限拦截",
      target: "管理员配置",
      level: "警告",
      result: "访问拒绝（示例）",
      ip: "192.0.2.30",
    },
    {
      id: "event-6",
      time: "2026-11-13 19:20:00",
      actor: "zi rui",
      action: "配置变更",
      target: "默认知识提取模型",
      level: "信息",
      result: "已记录演示操作",
      ip: "192.0.2.10",
    },
  ],
};

export const sampleSessions: LoginSession[] = [
  {
    id: "session-1",
    userId: "sample-zirui",
    name: "zi rui",
    login: "2026-11-13T19:05:00",
    lastActive: "2026-11-13T19:59:40",
    online: true,
    ip: "192.0.2.10",
    device: "Windows · Edge",
  },
  {
    id: "session-2",
    userId: "sample-linyu",
    name: "林予",
    login: "2026-11-13T19:55:40",
    lastActive: "2026-11-13T19:59:10",
    online: true,
    ip: "192.0.2.21",
    device: "Windows · Chrome",
  },
  {
    id: "session-3",
    userId: "sample-wenjing",
    name: "闻静",
    login: "2026-11-13T16:40:00",
    logout: "2026-11-13T17:58:00",
    lastActive: "2026-11-13T17:50:00",
    online: false,
    ip: "192.0.2.30",
    device: "macOS · Safari",
  },
  {
    id: "session-4",
    userId: "sample-linyu",
    name: "林予",
    login: "2026-11-12T18:30:00",
    logout: "2026-11-12T19:20:00",
    lastActive: "2026-11-12T19:19:00",
    online: false,
    ip: "192.0.2.21",
    device: "Windows · Chrome",
  },
  {
    id: "session-5",
    userId: "sample-zirui",
    name: "zi rui",
    login: "2026-11-12T20:00:00",
    logout: "2026-11-12T21:45:00",
    lastActive: "2026-11-12T21:42:00",
    online: false,
    ip: "192.0.2.10",
    device: "Windows · Edge",
  },
];
export const templateValues: Record<string, string> = {
  subject: "Windows 内核",
  title: "IRP 的完成例程",
  review_count: "3",
  memory_stage: "需要强化",
  content: "IRP 表示一次 I/O 请求。完成过程将处理结果沿驱动栈返回。",
  question: "一次 I/O 请求的完成过程应当如何理解？",
  notion_url: "[同步后填入原始 Notion 页面]",
  review_url: "[接线后填入复习入口]",
};
