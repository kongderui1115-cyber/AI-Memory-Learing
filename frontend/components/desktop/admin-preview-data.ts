/** Administrator-only presentation inputs. All values below are explicit UI fixtures. */
export interface AdminKnowledgePoint {
  id: string;
  title: string;
  subject: string;
  mastery: string;
  content: string;
  explanation: string;
  source: string;
  sourceUrl?: string;
}

export interface AdminUserSnapshot {
  id: string;
  name: string;
  email: string;
  role: "user" | "admin";
  todayDue: number;
  todayCompleted: number;
  overdue: number;
  knowledgeTotal: number;
  streak: number;
  retention: number;
  lastActive: string;
  subjects: string[];
  knowledge: AdminKnowledgePoint[];
  reviews: {
    id: string;
    knowledgeId: string;
    status: "待复习" | "已完成" | "已逾期";
    strategy: string;
    reviewCount: number;
    rating?: string;
    reviewedAt?: string;
    nextDue: string;
  }[];
}

export const adminPreviewUsers: AdminUserSnapshot[] = [
  {
    id: "sample-zirui",
    name: "zi rui",
    email: "zirui@example.test",
    role: "admin",
    todayDue: 25,
    todayCompleted: 18,
    overdue: 3,
    knowledgeTotal: 1248,
    streak: 48,
    retention: 87,
    lastActive: "11-13 19:42",
    subjects: ["Windows 内核", "逆向工程"],
    knowledge: [
      {
        id: "zirui-irp",
        title: "IRP 的完成例程",
        subject: "Windows 内核",
        mastery: "需要强化",
        content: "IRP 表示一次 I/O 请求，完成过程将处理结果沿驱动栈返回。",
        explanation:
          "结合请求发起与完成两条路径，核对当前处理层、状态更新和结果返回过程。具体实现以原笔记中的平台和代码为准。",
        source: "zi rui / Windows 内核 / 第三章 / IRP 生命周期",
      },
      {
        id: "zirui-stack",
        title: "函数调用与栈帧",
        subject: "逆向工程",
        mastery: "记忆稳定",
        content: "阅读函数调用时，关注参数、返回地址、局部变量和调用约定。",
        explanation:
          "对照调用前、函数内部和返回后的状态，结合笔记中的具体平台核对布局。",
        source: "zi rui / 逆向工程 / 函数与调用",
      },
      {
        id: "zirui-device",
        title: "驱动对象与设备对象",
        subject: "Windows 内核",
        mastery: "新学习",
        content: "驱动对象描述驱动程序，设备对象表示由驱动管理的设备实例。",
        explanation:
          "结合笔记中的对象关系，核对一个驱动如何创建并管理多个设备对象。",
        source: "zi rui / Windows 内核 / 第二章 / 对象与设备",
      },
    ],
    reviews: [
      {
        id: "zirui-review-1",
        knowledgeId: "zirui-irp",
        status: "已逾期",
        strategy: "FSRS",
        reviewCount: 3,
        rating: "困难",
        reviewedAt: "11-10 20:12",
        nextDue: "11-12 20:00",
      },
      {
        id: "zirui-review-2",
        knowledgeId: "zirui-stack",
        status: "已完成",
        strategy: "FSRS",
        reviewCount: 4,
        rating: "记得",
        reviewedAt: "11-13 19:30",
        nextDue: "11-17 20:00",
      },
      {
        id: "zirui-review-3",
        knowledgeId: "zirui-device",
        status: "待复习",
        strategy: "FSRS",
        reviewCount: 1,
        nextDue: "11-13 20:00",
      },
    ],
  },
  {
    id: "sample-linyu",
    name: "林予",
    email: "linyu@example.test",
    role: "user",
    todayDue: 12,
    todayCompleted: 9,
    overdue: 1,
    knowledgeTotal: 386,
    streak: 21,
    retention: 82,
    lastActive: "11-13 18:26",
    subjects: ["英语学习", "数学"],
    knowledge: [
      {
        id: "linyu-perfect",
        title: "现在完成时的语境",
        subject: "英语学习",
        mastery: "已掌握",
        content: "have / has + 过去分词，表达过去的事情与现在之间的联系。",
        explanation:
          "用 I have finished this chapter. 结合上下文理解动作完成对现在的影响，再与原笔记的例句对照。",
        source: "林予 / 英语学习 / 第四课 / 现在完成时",
      },
      {
        id: "linyu-derivative",
        title: "导数与瞬时变化率",
        subject: "数学",
        mastery: "需要强化",
        content: "对于 f(x) = x²，导函数 f′(x) = 2x，在 x = 3 时导数为 6。",
        explanation:
          "先求导，再代入指定位置。结合图像理解导数值与切线斜率的关系。",
        source: "林予 / 数学 / 第二章 / 导数与变化率",
      },
    ],
    reviews: [
      {
        id: "linyu-review-1",
        knowledgeId: "linyu-perfect",
        status: "已完成",
        strategy: "Ebb",
        reviewCount: 4,
        rating: "熟练",
        reviewedAt: "11-13 18:26",
        nextDue: "11-20 19:00",
      },
      {
        id: "linyu-review-2",
        knowledgeId: "linyu-derivative",
        status: "已逾期",
        strategy: "FSRS",
        reviewCount: 2,
        rating: "困难",
        reviewedAt: "11-09 19:00",
        nextDue: "11-12 19:00",
      },
    ],
  },
  {
    id: "sample-wenjing",
    name: "闻静",
    email: "wenjing@example.test",
    role: "user",
    todayDue: 8,
    todayCompleted: 5,
    overdue: 2,
    knowledgeTotal: 208,
    streak: 12,
    retention: 76,
    lastActive: "11-13 17:50",
    subjects: ["日语", "历史"],
    knowledge: [
      {
        id: "wenjing-kana",
        title: "五十音与词汇例句",
        subject: "日语",
        mastery: "新学习",
        content: "将假名、读音提示与完整词汇例句一同整理，结合语境回忆。",
        explanation:
          "先回忆读音和词义，再对照原笔记。相近字形单独整理，记录自己的易错点。",
        source: "闻静 / 日语 / 第一课 / 假名与词汇",
      },
      {
        id: "wenjing-history",
        title: "历史事件的因果脉络",
        subject: "历史",
        mastery: "记忆稳定",
        content: "按时间、背景、参与者与结果整理事件，并保留原始笔记中的来源。",
        explanation:
          "将事件之间的关系绘成时间线，区分原文记录、资料引用与自己的理解。",
        source: "闻静 / 历史 / 第一章 / 时间线",
      },
    ],
    reviews: [
      {
        id: "wenjing-review-1",
        knowledgeId: "wenjing-kana",
        status: "已逾期",
        strategy: "Ebb",
        reviewCount: 1,
        nextDue: "11-12 18:00",
      },
      {
        id: "wenjing-review-2",
        knowledgeId: "wenjing-history",
        status: "已完成",
        strategy: "FSRS",
        reviewCount: 3,
        rating: "记得",
        reviewedAt: "11-13 17:50",
        nextDue: "11-18 18:00",
      },
    ],
  },
];
