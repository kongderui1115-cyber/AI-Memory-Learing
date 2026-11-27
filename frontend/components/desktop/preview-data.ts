/** Explicit fixtures for the opt-in UI preview. Never used as API fallbacks. */
export type PreviewView =
  | "dashboard"
  | "learning"
  | "review"
  | "knowledge"
  | "subjects"
  | "notion"
  | "calendar"
  | "statistics"
  | "assistant"
  | "settings"
  | "help"
  | "admin";
export type ChapterStatus = "未开始" | "进行中" | "已完成";

export const navigation: { id: PreviewView; label: string; icon: string }[] = [
  { id: "dashboard", label: "首页仪表盘", icon: "home" },
  { id: "learning", label: "今日学习", icon: "book" },
  { id: "review", label: "今日复习", icon: "review" },
  { id: "knowledge", label: "知识库", icon: "library" },
  { id: "subjects", label: "学科管理", icon: "subjects" },
  { id: "notion", label: "Notion 同步", icon: "notion" },
  { id: "calendar", label: "复习日历", icon: "calendar" },
  { id: "statistics", label: "学习统计", icon: "statistics" },
  { id: "assistant", label: "AI 学习助手", icon: "assistant" },
];

export const subjects = [
  {
    id: "windows",
    name: "Windows 内核",
    count: 352,
    color: "blue",
    icon: "cpu",
    percent: 28,
  },
  {
    id: "english",
    name: "英语学习",
    count: 275,
    color: "purple",
    icon: "languages",
    percent: 22,
  },
  {
    id: "reverse",
    name: "逆向工程",
    count: 175,
    color: "cyan",
    icon: "code",
    percent: 14,
  },
  {
    id: "russian",
    name: "俄语",
    count: 124,
    color: "orange",
    icon: "languages",
    percent: 10,
  },
  {
    id: "ai",
    name: "AI 与机器学习",
    count: 150,
    color: "coral",
    icon: "brain",
    percent: 12,
  },
  {
    id: "math",
    name: "数学",
    count: 172,
    color: "teal",
    icon: "math",
    percent: 14,
  },
];

export const learningTasks = [
  {
    id: "learn-1",
    title: "阅读：IRP 的生命周期与处理流程",
    subject: "windows",
    minutes: 45,
    done: true,
  },
  {
    id: "learn-2",
    title: "整理：I/O 管理器关键结构",
    subject: "windows",
    minutes: 60,
    done: true,
  },
  {
    id: "learn-3",
    title: "学习：英语词汇与例句",
    subject: "english",
    minutes: 30,
    done: true,
  },
  {
    id: "learn-4",
    title: "阅读：FSRS 算法原理与参数",
    subject: "ai",
    minutes: 60,
    done: false,
  },
];

export const chapters: {
  id: string;
  title: string;
  subject: string;
  status: ChapterStatus;
  sessions: number;
  points: number;
  updated: string;
  summary: string;
}[] = [
  {
    id: "chapter-1",
    title: "第三章 · I/O 管理器与 IRP",
    subject: "windows",
    status: "进行中",
    sessions: 3,
    points: 12,
    updated: "今天 19:42",
    summary:
      "记录 I/O 请求的发起、驱动处理与完成流程，梳理关键结构之间的联系。",
  },
  {
    id: "chapter-2",
    title: "第四课 · 现在完成时",
    subject: "english",
    status: "已完成",
    sessions: 2,
    points: 8,
    updated: "今天 19:40",
    summary: "归纳现在完成时的基本结构、时间表达与例句，整理容易混淆的用法。",
  },
  {
    id: "chapter-3",
    title: "第二章 · 记忆调度基础",
    subject: "ai",
    status: "未开始",
    sessions: 0,
    points: 0,
    updated: "昨天 21:16",
    summary: "理解固定间隔复习与基于评分的自适应调度，记录学习过程和问题。",
  },
  {
    id: "chapter-4",
    title: "第二章 · 导数与变化率",
    subject: "math",
    status: "已完成",
    sessions: 4,
    points: 10,
    updated: "11月12日",
    summary: "从平均变化率理解瞬时变化率，通过求导规则练习计算并解释结果。",
  },
];

export const reviewItems = [
  {
    id: "review-1",
    title: "IRP 的完成例程",
    subject: "windows",
    strategy: "FSRS",
    stage: 3,
    interval: "2 天",
    question: "一次 I/O 请求的完成过程应当如何理解？",
    content:
      "IRP 用来表示一次 I/O 请求。驱动处理请求后，完成过程让请求结果沿驱动栈返回。",
    explanation:
      "可以把请求路径与完成路径放在一起阅读。记录请求在哪一层处理、当前状态如何更新，以及上层如何得到结果，再回到原笔记中的代码示例逐步核对。",
    source: "Windows 内核笔记库 / 第三章 / IRP 生命周期",
  },
  {
    id: "review-2",
    title: "驱动对象与设备对象",
    subject: "windows",
    strategy: "FSRS",
    stage: 2,
    interval: "3 天",
    question: "驱动对象与设备对象分别描述什么？",
    content:
      "驱动对象描述驱动程序，设备对象描述由驱动管理的设备。一个驱动可以创建和管理多个设备对象。",
    explanation:
      "复习时先画出一个驱动对象和多个设备对象的关系，再根据自己的笔记核对各个字段的职责。将对象之间的关联与具体设备实例联系起来理解。",
    source: "Windows 内核笔记库 / 第二章 / 对象与设备",
  },
  {
    id: "review-3",
    title: "英语 · 现在完成时",
    subject: "english",
    strategy: "Ebb",
    stage: 4,
    interval: "7 天",
    question: "现在完成时的基本结构是什么？",
    content:
      "基本结构为 have / has + 过去分词，常用来表达过去发生的事情与现在之间的联系。",
    explanation:
      "例如 I have finished this chapter. 这句话表达章节已经完成。复习时结合语境，关注动作对现在的影响，并整理笔记中的典型时间表达。",
    source: "英语学习 / 语法 / 现在完成时",
  },
  {
    id: "review-4",
    title: "导数与瞬时变化率",
    subject: "math",
    strategy: "FSRS",
    stage: 2,
    interval: "5 天",
    question: "f(x) = x² 在 x = 3 时的导数是多少？",
    content: "f′(x) = 2x，因此在 x = 3 时导数为 6。",
    explanation:
      "先使用求导规则得到导函数，再代入指定位置。导数值描述该点的瞬时变化率，也对应曲线在这一点的切线斜率。",
    source: "数学 / 第二章 / 导数与变化率",
  },
  {
    id: "review-5",
    title: "间隔复习与主动回忆",
    subject: "ai",
    strategy: "Ebb",
    stage: 2,
    interval: "2 天",
    question: "复习时怎样记录自己的掌握情况？",
    content:
      "先尝试主动回忆，再对照笔记和解析检查结果，并记录忘记、困难、记得或熟练。",
    explanation:
      "评分应基于本次真实回忆过程。先自己回答问题，再查看解析，有助于区分熟悉内容和能够独立回忆内容。",
    source: "AI 学习 / 记忆调度 / 复习方法",
  },
  {
    id: "review-6",
    title: "函数调用与栈帧",
    subject: "reverse",
    strategy: "FSRS",
    stage: 3,
    interval: "4 天",
    question: "阅读函数调用时应该关注哪些变化？",
    content:
      "关注参数传递、返回地址、局部变量与调用约定，并结合具体平台的示例阅读。",
    explanation:
      "将调用前、函数内部和返回后的状态并列记录。具体寄存器和栈布局需要以笔记中的平台与调用约定为准。",
    source: "逆向工程 / 函数与调用",
  },
  {
    id: "review-7",
    title: "俄语词汇 · 学习",
    subject: "russian",
    strategy: "Ebb",
    stage: 1,
    interval: "1 天",
    question: "怎样为新学词汇制作有效的复习卡片？",
    content: "在卡片中保存词义、读音提示和一个完整例句，并关联原笔记。",
    explanation:
      "复习时结合例句回忆用法。容易混淆的词可以建立关联，分别记录区别与适用语境。",
    source: "俄语 / 词汇 / 学习与生活",
  },
];

export const recentSyncs = [
  { title: "Windows 内核笔记库", time: "19:42", pages: 3 },
  { title: "英语学习", time: "19:40", pages: 2 },
  { title: "数学笔记", time: "19:35", pages: 1 },
];

export const upcomingReviews = [
  { day: "11-14", weekday: "明天", count: 23, strategy: "FSRS" },
  { day: "11-15", weekday: "周日", count: 17, strategy: "FSRS" },
  { day: "11-17", weekday: "周二", count: 26, strategy: "Ebb" },
  { day: "11-20", weekday: "周五", count: 14, strategy: "FSRS" },
];

export const trendHours = [
  2.0, 1.9, 2.3, 2.2, 2.9, 2.0, 2.0, 1.9, 2.8, 2.7, 4.2, 4.2, 2.6, 3.3,
];
export const trendReviews = [4, 5, 3, 6, 11, 5, 5, 6, 10, 10, 8, 9, 7, 9];
export const memorySegments = [
  { name: "已掌握", value: 42, color: "#35c5c5" },
  { name: "记忆稳定", value: 25, color: "#9b74fa" },
  { name: "需要强化", value: 20, color: "#ffb563" },
  { name: "容易遗忘", value: 8, color: "#ff7d72" },
  { name: "新学习", value: 5, color: "#c8d1df" },
];

/** Data contract for the visual workspace. A live adapter can supply this shape. */
export interface DesktopWorkspaceData {
  asOf: string;
  user: {
    name: string;
    email: string;
    streak: number;
    role: "user" | "admin";
    timezone: string;
  };
  metrics: {
    studyHours: number;
    studyGrowth: number;
    reviewed: number;
    reviewTotal: number;
    knowledgeTotal: number;
    newKnowledge: number;
    retention: number;
    retentionGrowth: number;
  };
  subjects: {
    id: string;
    name: string;
    count: number;
    color: string;
    icon: string;
    percent: number;
  }[];
  learningTasks: {
    id: string;
    title: string;
    subject: string;
    minutes: number;
    done: boolean;
  }[];
  chapters: {
    id: string;
    title: string;
    subject: string;
    status: ChapterStatus;
    sessions: number;
    points: number;
    updated: string;
    summary: string;
  }[];
  reviewItems: {
    id: string;
    title: string;
    subject: string;
    strategy: string;
    stage: number;
    interval: string;
    question: string;
    content: string;
    explanation: string;
    source: string;
    sourceUrl?: string;
  }[];
  recentSyncs: { title: string; time: string; pages: number }[];
  upcomingReviews: {
    day: string;
    weekday: string;
    count: number;
    strategy: string;
  }[];
  trendHours: number[];
  trendReviews: number[];
  trendDays: string[];
  memorySegments: { name: string; value: number; color: string }[];
  goals: { title: string; progress: number }[];
}

export const previewWorkspace: DesktopWorkspaceData = {
  asOf: "2026-11-13T20:00:00+08:00",
  user: {
    name: "zi rui",
    email: "preview@example.com",
    streak: 48,
    role: "user",
    timezone: "Asia/Shanghai",
  },
  metrics: {
    studyHours: 3.4,
    studyGrowth: 42,
    reviewed: 18,
    reviewTotal: 25,
    knowledgeTotal: 1248,
    newKnowledge: 56,
    retention: 87,
    retentionGrowth: 5,
  },
  subjects,
  learningTasks,
  chapters,
  reviewItems,
  recentSyncs,
  upcomingReviews,
  trendHours,
  trendReviews,
  memorySegments,
  trendDays: [
    "10/31",
    "11/1",
    "11/2",
    "11/3",
    "11/4",
    "11/5",
    "11/6",
    "11/7",
    "11/8",
    "11/9",
    "11/10",
    "11/11",
    "11/12",
    "11/13",
  ],
  goals: [
    { title: "Q4 · Windows 内核进阶", progress: 68 },
    { title: "英语能力提升（C1）", progress: 56 },
    { title: "逆向工程实践", progress: 42 },
  ],
};
