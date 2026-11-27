"use client";

import Link from "next/link";
import { createPreviewId } from "./preview-id";
import { useEffect, useRef, useState } from "react";
import type { FormEvent, ReactNode } from "react";
import {
  ArrowRight,
  ArrowUpRight,
  Bell,
  BookOpen,
  Bot,
  BrainCircuit,
  CalendarDays,
  Check,
  CheckCheck,
  ChevronLeft,
  ChevronRight,
  CircleHelp,
  Clock3,
  Code2,
  Cpu,
  ExternalLink,
  FileText,
  GraduationCap,
  Home,
  Languages,
  Layers3,
  LoaderCircle,
  LogIn,
  Maximize2,
  MessageSquare,
  Network,
  Plus,
  RefreshCw,
  Search,
  Send,
  Settings2,
  ShieldCheck,
  Sparkles,
  Target,
  TrendingUp,
  Users,
  X,
} from "lucide-react";
import { Donut, StudyTrend } from "./PreviewCharts";
import { navigation } from "./preview-data";
import type {
  ChapterStatus,
  DesktopWorkspaceData,
  PreviewView,
} from "./preview-data";

const iconMap = {
  home: Home,
  book: BookOpen,
  review: RefreshCw,
  library: Layers3,
  subjects: Network,
  notion: FileText,
  calendar: CalendarDays,
  statistics: TrendingUp,
  assistant: Bot,
  cpu: Cpu,
  languages: Languages,
  code: Code2,
  brain: BrainCircuit,
  math: GraduationCap,
};
function Icon({ name, size = 19 }: { name: string; size?: number }) {
  const Component = iconMap[name as keyof typeof iconMap] ?? BookOpen;
  return <Component size={size} strokeWidth={1.8} aria-hidden="true" />;
}
const route = (view: PreviewView) =>
  view === "dashboard" ? "/preview" : `/preview/${view}`;
const subjectColors = [
  "#4d83ff",
  "#9c70fa",
  "#3bc5c8",
  "#ffb06b",
  "#f18a9f",
  "#8fa9d3",
];
type DialogState = {
  kind: "review" | "chapter" | "push" | "channel" | "subject" | "search";
  id?: string;
} | null;
type LocalPreviewState = {
  checkedTasks: string[];
  completedReviews: string[];
  chapterStatus: Record<string, ChapterStatus>;
  addedSubjects: DesktopWorkspaceData["subjects"];
  model: string;
  channel: string;
  pushTime: string;
  admin: boolean;
};

function Panel({
  title,
  children,
  action,
  className = "",
}: {
  title: string;
  children: ReactNode;
  action?: ReactNode;
  className?: string;
}) {
  return (
    <section className={`ds-panel ${className}`}>
      <div className="ds-panel-heading">
        <h2>{title}</h2>
        {action}
      </div>
      {children}
    </section>
  );
}

export default function DesktopPreview({
  view,
  data,
  initialSubject = "all",
  initialPrompt = "",
}: {
  view: PreviewView;
  data: DesktopWorkspaceData;
  initialSubject?: string;
  initialPrompt?: string;
}) {
  const [local, setLocal] = useState<LocalPreviewState>(() => ({
    checkedTasks: data.learningTasks
      .filter((task) => task.done)
      .map((task) => task.id),
    completedReviews: [],
    chapterStatus: {},
    addedSubjects: [],
    model: "DeepSeek",
    channel: "PushPlus",
    pushTime: "09:00",
    admin: false,
  }));
  const [hydrated, setHydrated] = useState(false);
  const [dialog, setDialog] = useState<DialogState>(null);
  const [toast, setToast] = useState("");
  const [query, setQuery] = useState("");
  const [subjectFilter, setSubjectFilter] = useState(initialSubject);
  const [statusFilter, setStatusFilter] = useState("all");
  const [settingsTab, setSettingsTab] = useState("模型配置");
  const [reviewTab, setReviewTab] = useState("pending");
  const [showAnswer, setShowAnswer] = useState(false);
  const [chatInput, setChatInput] = useState(initialPrompt);
  const [chatMessages, setChatMessages] = useState<
    { role: "user" | "assistant"; text: string }[]
  >([]);
  const [syncing, setSyncing] = useState(false);
  const asOf = new Date(data.asOf);
  const snapshotYear = Number(data.asOf.slice(0, 4));
  const snapshotMonth = Number(data.asOf.slice(5, 7)) - 1;
  const snapshotDay = Number(data.asOf.slice(8, 10));
  const [calendar, setCalendar] = useState({
    year: snapshotYear,
    month: snapshotMonth,
    day: snapshotDay,
  });
  const formattedDate = asOf.toLocaleDateString("zh-CN", {
    year: "numeric",
    month: "long",
    day: "numeric",
    weekday: "short",
    timeZone: data.user.timezone,
  });
  const modal = useRef<HTMLDialogElement>(null);
  const allSubjects = [...data.subjects, ...local.addedSubjects];
  const remaining = data.reviewItems.filter(
    (item) => !local.completedReviews.includes(item.id),
  );
  const reviewed = data.metrics.reviewed + local.completedReviews.length;
  const reviewPercent =
    data.metrics.reviewTotal > 0
      ? Math.min(100, Math.round((reviewed / data.metrics.reviewTotal) * 100))
      : 0;
  const currentReview =
    data.reviewItems.find((item) => item.id === dialog?.id) ??
    data.reviewItems[0];
  const currentChapter =
    data.chapters.find((chapter) => chapter.id === dialog?.id) ??
    data.chapters[0];
  const title =
    navigation.find((item) => item.id === view)?.label ??
    ({ settings: "系统设置", help: "帮助中心", admin: "管理中心" } as const)[
      view as "settings" | "help" | "admin"
    ];

  useEffect(() => {
    try {
      const saved = JSON.parse(
        localStorage.getItem("memory-os-ui-preview-v1") ?? "null",
      );
      if (
        saved &&
        Array.isArray(saved.checkedTasks) &&
        Array.isArray(saved.completedReviews) &&
        typeof saved.chapterStatus === "object"
      ) {
        setLocal((previous) => ({
          ...previous,
          ...saved,
          addedSubjects: Array.isArray(saved.addedSubjects)
            ? saved.addedSubjects
            : [],
        }));
      }
    } catch {
      /* Preview remains usable when browser storage is unavailable. */
    }
    const filter = new URLSearchParams(window.location.search).get("subject");
    if (filter) setSubjectFilter(filter);
    setHydrated(true);
  }, []);

  useEffect(() => {
    if (hydrated) {
      try {
        localStorage.setItem("memory-os-ui-preview-v1", JSON.stringify(local));
      } catch {
        /* Storage is optional for a UI preview. */
      }
    }
  }, [local, hydrated]);

  useEffect(() => {
    if (!toast) return;
    const timeout = window.setTimeout(() => setToast(""), 4200);
    return () => window.clearTimeout(timeout);
  }, [toast]);

  useEffect(() => {
    if (dialog) {
      setShowAnswer(dialog.kind === "push");
      modal.current?.showModal();
    } else {
      modal.current?.close();
    }
  }, [dialog]);

  useEffect(() => {
    function shortcut(event: KeyboardEvent) {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setDialog({ kind: "search" });
      }
    }
    window.addEventListener("keydown", shortcut);
    return () => window.removeEventListener("keydown", shortcut);
  }, []);

  function getSubject(id: string) {
    return allSubjects.find((subject) => subject.id === id);
  }
  function SubjectTag({ id }: { id: string }) {
    const subject = getSubject(id);
    return (
      <span className={`ds-subject-tag ${subject?.color ?? "blue"}`}>
        {subject?.name ?? "未分类"}
      </span>
    );
  }
  function toggleTask(id: string) {
    setLocal((previous) => ({
      ...previous,
      checkedTasks: previous.checkedTasks.includes(id)
        ? previous.checkedTasks.filter((value) => value !== id)
        : [...previous.checkedTasks, id],
    }));
  }
  function finishReview(rating: string) {
    if (!local.completedReviews.includes(currentReview.id)) {
      setLocal((previous) => ({
        ...previous,
        completedReviews: [...previous.completedReviews, currentReview.id],
      }));
    }
    setDialog(null);
    setToast(`预览已记录“${rating}”，当前任务已完成。正式调度由后端计算。`);
  }
  function previewSync() {
    if (syncing) return;
    setSyncing(true);
    window.setTimeout(() => {
      setSyncing(false);
      setToast(
        "已演示同步操作。当前页面使用示例数据，真实 Notion 授权待接入。",
      );
    }, 900);
  }
  function sendChat(event: FormEvent) {
    event.preventDefault();
    const text = chatInput.trim();
    if (!text) return;
    setChatMessages((previous) => [
      ...previous,
      { role: "user", text },
      {
        role: "assistant",
        text: `已收到你的问题。当前为 ${local.model} 对话界面预览，模型尚未接入。正式接入后会结合你有权限的笔记回答，并附上来源。`,
      },
    ]);
    setChatInput("");
  }
  function addSubject(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const name = String(form.get("name") ?? "").trim();
    if (!name) return;
    if (allSubjects.some((subject) => subject.name === name)) {
      setToast("这个学科名称已存在");
      return;
    }
    setLocal((previous) => ({
      ...previous,
      addedSubjects: [
        ...previous.addedSubjects,
        {
          id: `preview-${createPreviewId()}`,
          name,
          count: 0,
          color: "purple",
          icon: "book",
          percent: 0,
        },
      ],
    }));
    setDialog(null);
    setToast(`已在本地预览中添加“${name}”`);
  }
  function ReviewRows({ limit }: { limit?: number }) {
    const items = remaining.filter(
      (item) => subjectFilter === "all" || item.subject === subjectFilter,
    );
    const visible = limit ? items.slice(0, limit) : items;
    return (
      <div className="ds-review-list">
        {visible.map((item) => (
          <button
            className="ds-review-row"
            key={item.id}
            onClick={() => setDialog({ kind: "review", id: item.id })}
          >
            <span
              className={`ds-play ${getSubject(item.subject)?.color ?? "blue"}`}
            >
              <ChevronRight size={14} fill="currentColor" />
            </span>
            <span className="ds-row-title">
              {item.title}
              <small>第 {item.stage} 次复习</small>
            </span>
            <SubjectTag id={item.subject} />
            <span className="ds-row-meta">
              {item.strategy} · {item.interval}
            </span>
          </button>
        ))}
        {items.length === 0 && (
          <div className="ds-empty">
            <CheckCheck />
            <h3>这一组复习已完成</h3>
            <p>本次预览中的完成状态已保存在当前浏览器。</p>
          </div>
        )}
      </div>
    );
  }
  function miniAssistant({ full = false }: { full?: boolean }) {
    return (
      <div className={`ds-assistant-box ${full ? "full" : ""}`}>
        <div className="ds-assistant-intro">
          <span className="ds-bot-avatar">
            <Bot size={28} />
          </span>
          <div>
            <strong>AI 学习助手</strong>
            <p>把知识讲清楚，陪你记得更久。</p>
          </div>
        </div>
        <div className="ds-assistant-actions">
          {[
            { text: "解析笔记", icon: BookOpen },
            { text: "出复习题", icon: BrainCircuit },
            { text: "制定计划", icon: CalendarDays },
            { text: "分析薄弱点", icon: TrendingUp },
          ].map((action) => (
            <button
              key={action.text}
              onClick={() => {
                setChatInput(`请帮我${action.text}`);
                if (!full)
                  window.location.href = `${route("assistant")}?action=${encodeURIComponent(action.text)}`;
              }}
            >
              <action.icon size={16} />
              {action.text}
            </button>
          ))}
        </div>
        {full && (
          <div className="ds-chat-messages" aria-live="polite">
            {chatMessages.length === 0 ? (
              <div className="ds-chat-welcome">
                <Sparkles size={30} />
                <h2>从一个问题，开始理解。</h2>
                <p>可以询问笔记、生成练习，或者整理一章的知识脉络。</p>
                <span className="ds-preview-inline">
                  AI 对话布局预览 · 尚未调用模型
                </span>
              </div>
            ) : (
              chatMessages.map((message, index) => (
                <div className={`ds-chat-bubble ${message.role}`} key={index}>
                  {message.text}
                </div>
              ))
            )}
          </div>
        )}
        <form
          className="ds-chat-composer"
          onSubmit={(event) => {
            if (!full) {
              event.preventDefault();
              window.location.href = `${route("assistant")}?prompt=${encodeURIComponent(chatInput)}`;
            } else sendChat(event);
          }}
        >
          <label
            className="ds-sr-only"
            htmlFor={full ? "full-chat" : "mini-chat"}
          >
            向 AI 学习助手提问
          </label>
          <input
            id={full ? "full-chat" : "mini-chat"}
            value={chatInput}
            onChange={(event) => setChatInput(event.target.value)}
            placeholder="向我提问，或输入学习内容…"
            autoComplete="off"
          />
          <button aria-label="发送问题" type="submit">
            <ArrowRight size={22} />
          </button>
        </form>
      </div>
    );
  }

  const subjectSegments = data.subjects.map((subject, index) => ({
    name: subject.name,
    value: subject.percent,
    color: subjectColors[index % subjectColors.length],
  }));
  const taskList = (
    <div className="ds-task-list">
      {data.learningTasks.map((task) => (
        <label className="ds-task-row" key={task.id}>
          <input
            type="checkbox"
            checked={local.checkedTasks.includes(task.id)}
            onChange={() => toggleTask(task.id)}
          />
          <span className="ds-row-title">{task.title}</span>
          <SubjectTag id={task.subject} />
          <span className="ds-row-meta">{task.minutes} min</span>
        </label>
      ))}
    </div>
  );
  const goals = (
    <div className="ds-goals">
      {data.goals.map((goal) => (
        <div key={goal.title}>
          <div>
            <span>{goal.title}</span>
            <strong>{goal.progress}%</strong>
          </div>
          <div className="ds-progress-track">
            <span style={{ width: `${goal.progress}%` }} />
          </div>
        </div>
      ))}
    </div>
  );

  function dashboard() {
    const stats = [
      {
        title: "今日学习",
        value: data.metrics.studyHours,
        unit: "小时",
        icon: BookOpen,
        color: "purple",
        note: `较昨日 +${data.metrics.studyGrowth}%`,
      },
      {
        title: "今日复习",
        value: reviewed,
        unit: "个",
        icon: RefreshCw,
        color: "blue",
        note: `完成率 ${reviewPercent}%`,
      },
      {
        title: "知识点总数",
        value: data.metrics.knowledgeTotal.toLocaleString(),
        unit: "个",
        icon: Layers3,
        color: "blue",
        note: `本周 +${data.metrics.newKnowledge}`,
      },
      {
        title: "记忆保持率",
        value: `${data.metrics.retention}%`,
        unit: "",
        icon: BrainCircuit,
        color: "pink",
        note: `示例指标 · 较上周 +${data.metrics.retentionGrowth}%`,
      },
      {
        title: "连续学习",
        value: data.user.streak,
        unit: "天",
        icon: CalendarDays,
        color: "purple",
        note: "目标 100 天",
      },
    ];
    return (
      <div className="ds-dashboard-grid">
        <div className="ds-dashboard-main">
          <section className="ds-hero">
            <div>
              <h2>持续学习 · 深度记忆 · 长期成长</h2>
              <p>把每一次学习，变成可积累的能力。</p>
            </div>
          </section>
          <div className="ds-metric-grid">
            {stats.map((stat) => (
              <section className="ds-metric" key={stat.title}>
                <span className={`ds-icon-tile ${stat.color}`}>
                  <stat.icon size={22} strokeWidth={2} />
                </span>
                <div>
                  <h3>{stat.title}</h3>
                  <strong>
                    {stat.value}
                    <small>{stat.unit}</small>
                  </strong>
                  <p className={stat.note.includes("+") ? "positive" : ""}>
                    {stat.note}
                  </p>
                </div>
              </section>
            ))}
          </div>
          <div className="ds-chart-grid">
            <Panel
              title="学习趋势"
              action={<span className="ds-muted">近14天</span>}
            >
              <StudyTrend
                hours={data.trendHours}
                reviews={data.trendReviews}
                days={data.trendDays}
              />
            </Panel>
            <Panel
              title="学科分布"
              action={<span className="ds-muted">知识点</span>}
            >
              <Donut
                segments={subjectSegments}
                total={data.metrics.knowledgeTotal.toLocaleString()}
              />
            </Panel>
          </div>
          <div className="ds-lists-grid">
            <Panel
              title={`今日学习任务（${data.learningTasks.length}）`}
              action={
                <Link href={route("learning")} className="ds-text-link">
                  查看全部 <ChevronRight size={14} />
                </Link>
              }
            >
              {taskList}
            </Panel>
            <Panel
              title={`今日复习任务（${remaining.length}）`}
              action={
                <Link href={route("review")} className="ds-text-link">
                  查看全部 <ChevronRight size={14} />
                </Link>
              }
            >
              <ReviewRows limit={4} />
            </Panel>
          </div>
          <div className="ds-bottom-grid">
            <Panel title="记忆状态分布">
              <Donut
                segments={data.memorySegments}
                small
                total={data.metrics.knowledgeTotal.toLocaleString()}
              />
            </Panel>
            <Panel title="近期复习计划">
              <div className="ds-upcoming-list">
                {data.upcomingReviews.map((item) => (
                  <button
                    key={item.day}
                    onClick={() => {
                      window.location.href = route("calendar");
                    }}
                  >
                    <span>
                      {item.day}
                      <small>（{item.weekday}）</small>
                    </span>
                    <span>{item.count} 个任务</span>
                    <i
                      className={`ds-strategy ${item.strategy === "Ebb" ? "ebb" : ""}`}
                    >
                      {item.strategy}
                    </i>
                  </button>
                ))}
              </div>
            </Panel>
            <Panel title="学习目标">{goals}</Panel>
          </div>
        </div>
        <aside className="ds-dashboard-rail">
          <Panel title="今日进度">
            <div className="ds-today-progress">
              <div
                className="ds-progress-ring"
                style={{
                  background: `conic-gradient(#a47cff 0%, #486ffa ${reviewPercent}%, #e9eef8 ${reviewPercent}%)`,
                }}
              >
                <strong>{reviewPercent}%</strong>
              </div>
              <div>
                <p>
                  <span>
                    <i className="ds-dot blue" />
                    学习任务
                  </span>
                  <strong>
                    {local.checkedTasks.length} / {data.learningTasks.length}
                  </strong>
                </p>
                <p>
                  <span>
                    <i className="ds-dot purple" />
                    复习任务
                  </span>
                  <strong>
                    {reviewed} / {data.metrics.reviewTotal}
                  </strong>
                </p>
                <p>
                  <span>
                    <i className="ds-dot gray" />
                    学习时长
                  </span>
                  <strong>{data.metrics.studyHours} h</strong>
                </p>
              </div>
            </div>
          </Panel>
          <Panel title="快捷操作">
            <div className="ds-quick-actions">
              <button onClick={previewSync}>
                <span>
                  <RefreshCw size={21} className={syncing ? "ds-spin" : ""} />
                </span>
                同步 Notion
              </button>
              <Link href={route("knowledge")}>
                <span>
                  <FileText size={21} />
                </span>
                浏览知识点
              </Link>
              <button onClick={() => setDialog({ kind: "subject" })}>
                <span>
                  <Network size={21} />
                </span>
                添加学科
              </button>
              <Link href={route("assistant")}>
                <span>
                  <Bot size={21} />
                </span>
                AI 问答
              </Link>
            </div>
          </Panel>
          <Panel
            title="最近同步（Notion）"
            action={
              <Link href={route("notion")} className="ds-text-link">
                查看全部 <ChevronRight size={13} />
              </Link>
            }
          >
            <div className="ds-sync-list">
              {data.recentSyncs.map((sync) => (
                <div key={sync.title}>
                  <span className="ds-success-icon">
                    <Check size={13} />
                  </span>
                  <div>
                    <strong>{sync.title}</strong>
                    <small>
                      11-13 {sync.time} · {sync.pages} 页
                    </small>
                  </div>
                  <time>{sync.time}</time>
                </div>
              ))}
            </div>
          </Panel>
          <Panel title="AI 学习助手" className="ds-rail-assistant">
            {miniAssistant({})}
          </Panel>
        </aside>
      </div>
    );
  }

  function learningPage() {
    const filtered = data.chapters.filter(
      (chapter) =>
        (subjectFilter === "all" || chapter.subject === subjectFilter) &&
        (statusFilter === "all" ||
          (local.chapterStatus[chapter.id] ?? chapter.status) === statusFilter),
    );
    return (
      <>
        <div className="ds-page-heading">
          <div>
            <h1>沿着你的节奏，继续学习</h1>
            <p>在 Notion 记录每一次学习，完成整章后统一汇总与排期。</p>
          </div>
          <button className="ds-button primary" onClick={previewSync}>
            <RefreshCw size={16} className={syncing ? "ds-spin" : ""} />
            同步章节
          </button>
        </div>
        <div className="ds-workspace-columns">
          <div>
            <Panel
              title="课程与章节"
              action={<span className="ds-muted">Notion 状态映射</span>}
            >
              <div className="ds-filters">
                <select
                  aria-label="按学科筛选章节"
                  value={subjectFilter}
                  onChange={(event) => setSubjectFilter(event.target.value)}
                >
                  <option value="all">全部学科</option>
                  {allSubjects.map((subject) => (
                    <option key={subject.id} value={subject.id}>
                      {subject.name}
                    </option>
                  ))}
                </select>
                <div className="ds-tabs">
                  {["all", "未开始", "进行中", "已完成"].map((status) => (
                    <button
                      key={status}
                      onClick={() => setStatusFilter(status)}
                      aria-pressed={statusFilter === status}
                    >
                      {status === "all" ? "全部" : status}
                    </button>
                  ))}
                </div>
              </div>
              <div className="ds-chapters">
                {filtered.map((chapter) => {
                  const status =
                    local.chapterStatus[chapter.id] ?? chapter.status;
                  return (
                    <article className="ds-chapter" key={chapter.id}>
                      <span
                        className={`ds-icon-tile ${getSubject(chapter.subject)?.color}`}
                      >
                        <Icon
                          name={getSubject(chapter.subject)?.icon ?? "book"}
                        />
                      </span>
                      <div>
                        <div className="ds-chapter-heading">
                          <h3>{chapter.title}</h3>
                          <span
                            className={`ds-status ${status === "已完成" ? "done" : status === "进行中" ? "active" : ""}`}
                          >
                            {status}
                          </span>
                        </div>
                        <p>{chapter.summary}</p>
                        <div className="ds-chapter-meta">
                          <SubjectTag id={chapter.subject} />
                          <span>
                            <Clock3 size={13} />
                            已学习 {chapter.sessions} 次
                          </span>
                          <span>
                            <Layers3 size={13} />
                            {chapter.points} 个知识点
                          </span>
                          <span>{chapter.updated}</span>
                        </div>
                      </div>
                      <button
                        className="ds-icon-button"
                        aria-label={`查看${chapter.title}`}
                        onClick={() =>
                          setDialog({ kind: "chapter", id: chapter.id })
                        }
                      >
                        <ChevronRight size={19} />
                      </button>
                    </article>
                  );
                })}
                {filtered.length === 0 && (
                  <div className="ds-empty">
                    <BookOpen />
                    <p>当前筛选下没有章节。</p>
                  </div>
                )}
              </div>
            </Panel>
            <Panel title="今日学习清单" className="ds-spaced-panel">
              {taskList}
            </Panel>
          </div>
          <aside>
            <Panel title="章节完成后会发生什么">
              <ol className="ds-steps">
                <li>
                  <span>1</span>
                  <div>
                    <strong>在 Notion 标记已完成</strong>
                    <p>保留本章各次学习记录与原文来源。</p>
                  </div>
                </li>
                <li>
                  <span>2</span>
                  <div>
                    <strong>汇总知识与解析</strong>
                    <p>整理章节脉络，生成关联的复习卡片。</p>
                  </div>
                </li>
                <li>
                  <span>3</span>
                  <div>
                    <strong>安排复习和推送</strong>
                    <p>以实际完成时间为基点，计算到期任务。</p>
                  </div>
                </li>
              </ol>
              <div className="ds-info-note">
                <Sparkles size={16} />
                此流程当前用于界面演示。
              </div>
            </Panel>
          </aside>
        </div>
      </>
    );
  }

  function reviewPage() {
    return (
      <>
        <div className="ds-page-heading">
          <div>
            <h1>每一次回忆，都让记忆更稳固</h1>
            <p>先独立回忆，再查看解析，记录本次掌握程度。</p>
          </div>
          <span className="ds-page-summary">
            今日已完成 <strong>{reviewed}</strong> / {data.metrics.reviewTotal}
          </span>
        </div>
        <Panel
          title="复习任务"
          action={
            <button
              className="ds-button primary"
              disabled={remaining.length === 0}
              onClick={() =>
                setDialog({ kind: "review", id: remaining[0]?.id })
              }
            >
              开始复习 <ArrowRight size={15} />
            </button>
          }
        >
          <div className="ds-filters">
            <div className="ds-tabs">
              <button
                aria-pressed={reviewTab === "pending"}
                onClick={() => setReviewTab("pending")}
              >
                待复习 {remaining.length}
              </button>
              <button
                aria-pressed={reviewTab === "done"}
                onClick={() => setReviewTab("done")}
              >
                本次已完成 {local.completedReviews.length}
              </button>
            </div>
            <select
              aria-label="筛选复习学科"
              value={subjectFilter}
              onChange={(event) => setSubjectFilter(event.target.value)}
            >
              <option value="all">全部学科</option>
              {allSubjects.map((subject) => (
                <option key={subject.id} value={subject.id}>
                  {subject.name}
                </option>
              ))}
            </select>
          </div>
          {reviewTab === "pending" ? (
            <ReviewRows />
          ) : (
            <div className="ds-review-list">
              {data.reviewItems
                .filter((item) => local.completedReviews.includes(item.id))
                .map((item) => (
                  <div className="ds-review-row" key={item.id}>
                    <span className="ds-success-icon">
                      <Check size={14} />
                    </span>
                    <strong className="ds-row-title">{item.title}</strong>
                    <SubjectTag id={item.subject} />
                    <span className="ds-status done">预览已完成</span>
                  </div>
                ))}
              {local.completedReviews.length === 0 && (
                <div className="ds-empty">
                  <CheckCheck />
                  <h3>完成一次复习后，记录会显示在这里</h3>
                </div>
              )}
            </div>
          )}
        </Panel>
        <div className="ds-info-note ds-spaced-panel">
          <ShieldCheck size={17} />
          本页操作保存到当前浏览器的界面预览记录。正式复习历史与到期时间由后端持久化。
        </div>
      </>
    );
  }

  function knowledgePage() {
    const matches = data.reviewItems.filter(
      (item) =>
        (subjectFilter === "all" || item.subject === subjectFilter) &&
        `${item.title}${item.content}`
          .toLowerCase()
          .includes(query.toLowerCase()),
    );
    return (
      <>
        <div className="ds-page-heading">
          <div>
            <h1>让零散的笔记，形成自己的知识库</h1>
            <p>每一个知识点，都能追溯到原笔记与章节。</p>
          </div>
          <button
            className="ds-button"
            onClick={() =>
              setToast("新增知识点的真实保存功能将在后端接入后开放。")
            }
          >
            <Plus size={16} />
            新增知识点
          </button>
        </div>
        <Panel
          title="知识点"
          action={<span className="ds-muted">示例知识库</span>}
        >
          <div className="ds-filters">
            <label className="ds-inline-search">
              <Search size={16} />
              <input
                aria-label="搜索知识点"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="搜索标题或正文…"
              />
            </label>
            <select
              aria-label="筛选知识库学科"
              value={subjectFilter}
              onChange={(event) => setSubjectFilter(event.target.value)}
            >
              <option value="all">全部学科</option>
              {allSubjects.map((subject) => (
                <option key={subject.id} value={subject.id}>
                  {subject.name}
                </option>
              ))}
            </select>
          </div>
          <div className="ds-knowledge-grid">
            {matches.map((item) => (
              <button
                className="ds-knowledge-card"
                key={item.id}
                onClick={() => setDialog({ kind: "review", id: item.id })}
              >
                <div>
                  <SubjectTag id={item.subject} />
                  <span className="ds-muted">{item.strategy}</span>
                </div>
                <h3>{item.title}</h3>
                <p>{item.content}</p>
                <footer>
                  <FileText size={14} />
                  <span>{item.source}</span>
                  <ArrowUpRight size={15} />
                </footer>
              </button>
            ))}
            {matches.length === 0 && (
              <div className="ds-empty">
                <Search />
                <p>没有找到符合条件的知识点。</p>
              </div>
            )}
          </div>
        </Panel>
      </>
    );
  }

  function subjectsPage() {
    return (
      <>
        <div className="ds-page-heading">
          <div>
            <h1>为每一个兴趣，留一个位置</h1>
            <p>学科通过配置扩展，承载课程、知识点与学习策略。</p>
          </div>
          <button
            className="ds-button primary"
            onClick={() => setDialog({ kind: "subject" })}
          >
            <Plus size={16} />
            添加学科
          </button>
        </div>
        <div className="ds-subject-grid">
          {allSubjects.map((subject) => (
            <article className="ds-panel ds-subject-card" key={subject.id}>
              <span className={`ds-icon-tile ${subject.color}`}>
                <Icon name={subject.icon} size={25} />
              </span>
              <h2>{subject.name}</h2>
              <p>
                <strong>{subject.count}</strong> 个知识点
              </p>
              <div className="ds-subject-card-footer">
                <span className="ds-muted">学习策略可配置</span>
                <Link
                  href={`${route("knowledge")}?subject=${subject.id}`}
                  className="ds-text-link"
                >
                  打开知识库 <ArrowUpRight size={15} />
                </Link>
              </div>
            </article>
          ))}
        </div>
      </>
    );
  }

  function notionPage() {
    return (
      <>
        <div className="ds-page-heading">
          <div>
            <h1>让你的笔记，自然进入学习循环</h1>
            <p>同步原文、章节状态与来源信息，保留完整的知识脉络。</p>
          </div>
          <button className="ds-button primary" onClick={previewSync}>
            {syncing ? (
              <LoaderCircle size={16} className="ds-spin" />
            ) : (
              <RefreshCw size={16} />
            )}
            预览同步
          </button>
        </div>
        <div className="ds-workspace-columns">
          <Panel
            title="Notion 数据源"
            action={<span className="ds-status">示例配置</span>}
          >
            <div className="ds-source-list">
              {data.recentSyncs.map((sync) => (
                <div key={sync.title}>
                  <span className="ds-icon-tile blue">
                    <FileText />
                  </span>
                  <div>
                    <h3>{sync.title}</h3>
                    <p>最近示例同步 · 11月13日 {sync.time}</p>
                  </div>
                  <span className="ds-status done">
                    {sync.pages} 页示例内容
                  </span>
                </div>
              ))}
            </div>
            <button
              className="ds-button ds-top-gap"
              onClick={() =>
                setToast(
                  "真实接入时，在此绑定 Notion Integration 与目标知识库。",
                )
              }
            >
              <Plus size={16} />
              添加知识库
            </button>
          </Panel>
          <Panel title="章节状态映射">
            <div className="ds-mapping">
              <span>Notion 状态</span>
              <span>系统处理</span>
              {[
                ["未开始", "保留章节信息"],
                ["进行中", "记录学习过程与笔记"],
                ["已完成", "汇总知识并生成复习计划"],
              ].map(([status, meaning]) => (
                <div key={status}>
                  <strong>{status}</strong>
                  <span>
                    <ArrowRight size={14} />
                    {meaning}
                  </span>
                </div>
              ))}
            </div>
            <div className="ds-info-note ds-top-gap">
              <ShieldCheck size={16} />
              真实凭据将在后端安全配置，页面显示连接状态与授权范围。
            </div>
          </Panel>
        </div>
        <Panel title="同步记录" className="ds-spaced-panel">
          <div className="ds-table-wrap">
            <table>
              <thead>
                <tr>
                  <th>知识库</th>
                  <th>时间</th>
                  <th>内容</th>
                  <th>状态</th>
                </tr>
              </thead>
              <tbody>
                {data.recentSyncs.map((sync) => (
                  <tr key={sync.title}>
                    <td>{sync.title}</td>
                    <td>2026-11-13 {sync.time}</td>
                    <td>更新 {sync.pages} 页</td>
                    <td>
                      <span className="ds-status">界面示例</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>
      </>
    );
  }

  function calendarPage() {
    const start = (new Date(calendar.year, calendar.month, 1).getDay() + 6) % 7;
    const days = new Date(calendar.year, calendar.month + 1, 0).getDate();
    const events: Record<number, number> = {};
    for (const item of data.upcomingReviews) {
      const [month, day] = item.day.split("-").map(Number);
      if (calendar.year === snapshotYear && calendar.month === month - 1)
        events[day] = item.count;
    }
    if (calendar.year === snapshotYear && calendar.month === snapshotMonth)
      events[snapshotDay] = remaining.length;
    function moveMonth(offset: number) {
      const date = new Date(calendar.year, calendar.month + offset, 1);
      setCalendar({ year: date.getFullYear(), month: date.getMonth(), day: 1 });
    }
    return (
      <>
        <div className="ds-page-heading">
          <div>
            <h1>给记忆一个恰好的重逢时间</h1>
            <p>根据章节完成时间与复习反馈，查看接下来的学习安排。</p>
          </div>
          <button
            className="ds-button"
            onClick={() =>
              setCalendar({
                year: snapshotYear,
                month: snapshotMonth,
                day: snapshotDay,
              })
            }
          >
            回到示例今天
          </button>
        </div>
        <div className="ds-calendar-columns">
          <Panel
            title={`${calendar.year}年 ${calendar.month + 1}月`}
            action={
              <div className="ds-calendar-controls">
                <button
                  className="ds-icon-button"
                  aria-label="上个月"
                  onClick={() => moveMonth(-1)}
                >
                  <ChevronLeft size={18} />
                </button>
                <button
                  className="ds-icon-button"
                  aria-label="下个月"
                  onClick={() => moveMonth(1)}
                >
                  <ChevronRight size={18} />
                </button>
              </div>
            }
          >
            <div className="ds-calendar-grid">
              {["一", "二", "三", "四", "五", "六", "日"].map((day) => (
                <span className="ds-weekday" key={day}>
                  周{day}
                </span>
              ))}
              {Array.from(
                { length: Math.ceil((start + days) / 7) * 7 },
                (_, index) => {
                  const day = index - start + 1;
                  return day < 1 || day > days ? (
                    <span className="ds-calendar-blank" key={index} />
                  ) : (
                    <button
                      key={index}
                      className={`ds-calendar-day ${calendar.day === day ? "selected" : ""} ${day === snapshotDay && calendar.month === snapshotMonth && calendar.year === snapshotYear ? "today" : ""}`}
                      onClick={() =>
                        setCalendar((previous) => ({ ...previous, day }))
                      }
                    >
                      <strong>{day}</strong>
                      {events[day] !== undefined && (
                        <span>{events[day]} 个复习</span>
                      )}
                    </button>
                  );
                },
              )}
            </div>
          </Panel>
          <Panel title={`${calendar.month + 1}月${calendar.day}日`}>
            <div className="ds-calendar-summary">
              <CalendarDays size={32} />
              <strong>{events[calendar.day] ?? 0}</strong>
              <span>个示例复习任务</span>
            </div>
            {events[calendar.day] ? (
              <>
                <p className="ds-muted">推送时段 · {local.pushTime}</p>
                <p className="ds-muted ds-top-gap">渠道 · {local.channel}</p>
                <button
                  className="ds-button primary ds-top-gap"
                  onClick={() =>
                    setDialog({ kind: "push", id: data.reviewItems[0].id })
                  }
                >
                  预览推送内容
                </button>
              </>
            ) : (
              <div className="ds-empty">
                <p>这一天没有示例安排。</p>
              </div>
            )}
          </Panel>
        </div>
      </>
    );
  }

  function statisticsPage() {
    return (
      <>
        <div className="ds-page-heading">
          <div>
            <h1>让每一份积累，都看得见</h1>
            <p>学习时长、复习行为和知识分布，构成你的成长记录。</p>
          </div>
          <span className="ds-preview-inline">统计数据为示例</span>
        </div>
        <Panel
          title="学习与复习趋势"
          action={<span className="ds-muted">最近14天</span>}
        >
          <StudyTrend
            hours={data.trendHours}
            reviews={data.trendReviews}
            days={data.trendDays}
          />
        </Panel>
        <div className="ds-statistics-grid ds-spaced-panel">
          <Panel title="知识学科分布">
            <Donut
              segments={subjectSegments}
              total={data.metrics.knowledgeTotal.toLocaleString()}
            />
          </Panel>
          <Panel title="记忆状态分布">
            <Donut
              segments={data.memorySegments}
              total={data.metrics.knowledgeTotal.toLocaleString()}
            />
          </Panel>
          <Panel title="长期学习目标">
            {goals}
            <div className="ds-info-note ds-top-gap">
              <Target size={16} />
              目标进度在正式接入后根据学习记录计算。
            </div>
          </Panel>
        </div>
      </>
    );
  }

  function settingsPage() {
    const providers = [
      { name: "DeepSeek", note: "知识提取、总结与问答", color: "blue" },
      { name: "Kimi", note: "章节整理与学习陪伴", color: "purple" },
      { name: "OpenAI", note: "通过 OpenAI API 接入", color: "teal" },
    ];
    const channels = [
      {
        name: "PushPlus",
        text: "微信通知与完整内容详情",
        icon: MessageSquare,
        color: "teal",
      },
      {
        name: "钉钉",
        text: "应用机器人个人定向消息",
        icon: Send,
        color: "blue",
      },
      {
        name: "邮件",
        text: "章节总结与完整解析",
        icon: FileText,
        color: "purple",
      },
      {
        name: "飞书",
        text: "应用机器人与消息卡片",
        icon: Network,
        color: "cyan",
      },
      {
        name: "企业微信",
        text: "按成员发送应用消息",
        icon: Users,
        color: "blue",
      },
      { name: "Bark", text: "iPhone 自定义推送", icon: Bell, color: "orange" },
    ];
    return (
      <>
        <div className="ds-page-heading">
          <div>
            <h1>让系统适合你的学习方式</h1>
            <p>管理模型、推送偏好与账号安全。</p>
          </div>
        </div>
        <div className="ds-settings-tabs ds-tabs">
          {["模型配置", "通知渠道", "账号安全"].map((tab) => (
            <button
              key={tab}
              aria-pressed={settingsTab === tab}
              onClick={() => setSettingsTab(tab)}
            >
              {tab}
            </button>
          ))}
        </div>
        {settingsTab === "模型配置" ? (
          <>
            <div className="ds-provider-grid">
              {providers.map((provider) => (
                <article
                  className={`ds-panel ds-provider-card ${local.model === provider.name ? "selected" : ""}`}
                  key={provider.name}
                >
                  <span className={`ds-icon-tile ${provider.color}`}>
                    <BrainCircuit size={25} />
                  </span>
                  <div>
                    <h2>{provider.name}</h2>
                    <p>{provider.note}</p>
                  </div>
                  <span className="ds-status">待 API 授权</span>
                  <button
                    className={`ds-button ${local.model === provider.name ? "primary" : ""}`}
                    onClick={() => {
                      setLocal((previous) => ({
                        ...previous,
                        model: provider.name,
                      }));
                      setToast(`已将 ${provider.name} 设为预览默认模型`);
                    }}
                  >
                    {local.model === provider.name ? (
                      <>
                        <Check size={15} />
                        当前预览默认
                      </>
                    ) : (
                      "设为预览默认"
                    )}
                  </button>
                </article>
              ))}
            </div>
            <Panel title="按任务选择模型" className="ds-spaced-panel">
              <form
                className="ds-form-grid"
                onSubmit={(event) => {
                  event.preventDefault();
                  setToast(
                    "模型分工已在本次界面中确认，真实配置保存待后端接入。",
                  );
                }}
              >
                {["章节总结", "知识提取", "生成复习题", "答案评价"].map(
                  (label) => (
                    <label key={label}>
                      {label}
                      <select defaultValue={local.model}>
                        {providers.map((provider) => (
                          <option key={provider.name}>{provider.name}</option>
                        ))}
                      </select>
                    </label>
                  ),
                )}
                <button className="ds-button primary" type="submit">
                  保存预览设置
                </button>
              </form>
            </Panel>
          </>
        ) : settingsTab === "通知渠道" ? (
          <>
            <div className="ds-channel-grid">
              {channels.map((channel) => (
                <article
                  className="ds-panel ds-channel-card"
                  key={channel.name}
                >
                  <span className={`ds-icon-tile ${channel.color}`}>
                    <channel.icon size={23} />
                  </span>
                  <div>
                    <h2>
                      {channel.name}
                      {local.channel === channel.name && (
                        <span className="ds-status done">预览默认</span>
                      )}
                    </h2>
                    <p>{channel.text}</p>
                  </div>
                  <button
                    className="ds-button"
                    onClick={() =>
                      setDialog({ kind: "channel", id: channel.name })
                    }
                  >
                    配置
                  </button>
                </article>
              ))}
            </div>
            <div className="ds-info-note ds-spaced-panel">
              <ShieldCheck size={17} />
              各用户独立绑定接收身份。真实凭据及授权在后端接入阶段配置。
            </div>
          </>
        ) : (
          <Panel title="账号与安全">
            <div className="ds-account-row">
              <span className="ds-user-avatar">Z</span>
              <div>
                <h3>{data.user.name}</h3>
                <p>{data.user.email} · 示例账号</p>
              </div>
            </div>
            <div className="ds-security-list">
              <div>
                <span>
                  <ShieldCheck size={19} />
                  密码策略
                </span>
                <strong>按最终安全策略配置</strong>
              </div>
              <div>
                <span>
                  <LogIn size={19} />
                  登录保护
                </span>
                <strong>失败次数限制与会话撤销</strong>
              </div>
              <div>
                <span>
                  <Users size={19} />
                  数据访问
                </span>
                <strong>个人数据与管理员权限分别校验</strong>
              </div>
            </div>
            <div className="ds-info-note">
              当前为安全设置布局预览，相关策略尚待后端实现与验收。
            </div>
          </Panel>
        )}
      </>
    );
  }

  function helpPage() {
    return (
      <>
        <div className="ds-page-heading">
          <div>
            <h1>从笔记到记忆，每一步都清晰</h1>
            <p>本次桌面界面预览的操作说明。</p>
          </div>
        </div>
        <Panel title="使用说明">
          <div className="ds-help-list">
            {[
              {
                title: "这些数字来自哪里？",
                text: "本次所有数据都来自独立的预览数据集。后续章节、正文和来源接入 Notion，知识与解析接入 AI，任务、历史和统计接入后端。",
              },
              {
                title: "一章可以分多次学完吗？",
                text: "可以。章节支持未开始、进行中、已完成三种状态。完成整章后统一汇总并生成复习计划。",
              },
              {
                title: "怎样体验复习？",
                text: "进入今日复习，打开一张卡片，尝试回答后查看解析，并选择掌握程度。预览记录保存在当前浏览器。",
              },
              {
                title: "怎样预览推送？",
                text: "点击顶部通知或日历中的预览推送。消息详情包含知识点、解析与 Notion 来源位置。",
              },
            ].map((item) => (
              <details key={item.title} open>
                <summary>{item.title}</summary>
                <p>{item.text}</p>
              </details>
            ))}
          </div>
        </Panel>
      </>
    );
  }

  return (
    <div className="desktop-os">
      <aside className="ds-sidebar">
        <Link href="/preview" className="ds-brand">
          <span className="ds-brand-mark">
            <BrainCircuit size={30} strokeWidth={2} />
          </span>
          <span>
            <strong>AI 学习记忆系统</strong>
            <small>AI Learning Memory OS</small>
          </span>
        </Link>
        <nav className="ds-navigation" aria-label="学习导航">
          {navigation.map((item) => (
            <Link
              key={item.id}
              href={route(item.id)}
              className={view === item.id ? "active" : ""}
            >
              <Icon name={item.icon} />
              <span>{item.label}</span>
              {item.id === "review" && remaining.length > 0 && (
                <b>{remaining.length}</b>
              )}
            </Link>
          ))}
        </nav>
        <div className="ds-sidebar-subjects">
          <h2>我的学科</h2>
          {allSubjects.map((subject) => (
            <Link
              key={subject.id}
              href={`${route("knowledge")}?subject=${subject.id}`}
            >
              <span className={`ds-subject-symbol ${subject.color}`}>
                <Icon name={subject.icon} size={15} />
              </span>
              <span>{subject.name}</span>
              <small>{subject.count}</small>
            </Link>
          ))}
          <button onClick={() => setDialog({ kind: "subject" })}>
            <Plus size={17} />
            添加学科
          </button>
        </div>
        <div className="ds-sidebar-bottom">
          <Link
            href={route("settings")}
            className={view === "settings" ? "active" : ""}
          >
            <Settings2 size={18} />
            设置
          </Link>
          <Link
            href={route("help")}
            className={view === "help" ? "active" : ""}
          >
            <CircleHelp size={18} />
            帮助中心
          </Link>
          {local.admin && (
            <Link
              href={route("admin")}
              className={view === "admin" ? "active" : ""}
            >
              <ShieldCheck size={18} />
              管理中心
            </Link>
          )}
          <button
            className="ds-profile"
            onClick={() => {
              setLocal((previous) => ({ ...previous, admin: !previous.admin }));
              setToast(
                local.admin
                  ? "已切换为普通用户界面预览"
                  : "已显示管理员界面预览入口",
              );
            }}
          >
            <span className="ds-user-avatar">Z</span>
            <span>
              <strong>{data.user.name}</strong>
              <small>
                {local.admin
                  ? "管理员角色预览"
                  : `学习第 ${data.user.streak} 天 · 示例账号`}
              </small>
            </span>
            <Settings2 size={13} />
          </button>
        </div>
      </aside>
      <div className="ds-workspace">
        <header className="ds-header">
          <div>
            {view === "dashboard" ? (
              <>
                <h1>
                  晚上好，{data.user.name} <span className="ds-wave">👋</span>
                </h1>
                <p>
                  今天是 {formattedDate}，坚持学习第 {data.user.streak} 天
                </p>
              </>
            ) : (
              <>
                <h1>{title}</h1>
                <p>你的学习空间 / {title}</p>
              </>
            )}
          </div>
          <div className="ds-header-actions">
            <button
              className="ds-search"
              onClick={() => {
                setQuery("");
                setDialog({ kind: "search" });
              }}
            >
              <Search size={17} />
              <span>搜索知识点、笔记、任务…</span>
              <kbd>Ctrl + K</kbd>
            </button>
            <button
              className="ds-icon-button ds-notification"
              aria-label="查看推送预览"
              onClick={() => setDialog({ kind: "push", id: remaining[0]?.id })}
            >
              <Bell size={21} />
              <i />
            </button>
            <button
              className="ds-icon-button"
              aria-label="切换全屏"
              onClick={() => {
                if (document.fullscreenElement)
                  document
                    .exitFullscreen()
                    .catch(() => setToast("当前浏览器未能退出全屏"));
                else
                  document.documentElement
                    .requestFullscreen?.()
                    .catch(() => setToast("当前浏览器不支持全屏预览"));
              }}
            >
              <Maximize2 size={20} />
            </button>
          </div>
        </header>
        <div className="ds-preview-bar">
          <span>
            <span className="ds-preview-dot" />
            界面预览 · 示例数据
          </span>
          <span>后续由 Notion、AI 与后端记录填充</span>
          <Link href="/dashboard">
            进入账号登录 <ArrowUpRight size={12} />
          </Link>
        </div>
        <main className="ds-main" id="desktop-main">
          {view === "dashboard" ? (
            dashboard()
          ) : view === "learning" ? (
            learningPage()
          ) : view === "review" ? (
            reviewPage()
          ) : view === "knowledge" ? (
            knowledgePage()
          ) : view === "subjects" ? (
            subjectsPage()
          ) : view === "notion" ? (
            notionPage()
          ) : view === "calendar" ? (
            calendarPage()
          ) : view === "statistics" ? (
            statisticsPage()
          ) : view === "settings" ? (
            settingsPage()
          ) : view === "help" ? (
            helpPage()
          ) : (
            <>
              <div className="ds-page-heading">
                <div>
                  <h1>一起把知识，理解得更深一点</h1>
                  <p>笔记解析、复习问题与学习计划，都可以从这里开始。</p>
                </div>
                <select
                  aria-label="选择对话模型"
                  value={local.model}
                  onChange={(event) =>
                    setLocal((previous) => ({
                      ...previous,
                      model: event.target.value,
                    }))
                  }
                >
                  {["DeepSeek", "Kimi", "OpenAI"].map((model) => (
                    <option key={model}>{model}</option>
                  ))}
                </select>
              </div>
              <Panel
                title="AI 学习助手"
                action={<span className="ds-status">模型待接入</span>}
              >
                {miniAssistant({ full: true })}
              </Panel>
            </>
          )}
        </main>
        <footer className="ds-footer">
          <BrainCircuit size={14} />
          <span>AI Learning Memory OS</span>
          <span>学习 · 理解 · 记忆 · 成长</span>
          <span>桌面界面预览</span>
        </footer>
      </div>
      {toast && (
        <div className="ds-toast" role="status">
          <Check size={17} />
          {toast}
        </div>
      )}
      <dialog
        ref={modal}
        className={`ds-dialog ${dialog?.kind === "search" ? "ds-search-dialog" : ""}`}
        onCancel={() => setDialog(null)}
        onClick={(event) => {
          if (event.target === event.currentTarget) setDialog(null);
        }}
      >
        <div className="ds-dialog-content">
          {dialog && (
            <>
              <div className="ds-dialog-heading">
                <div>
                  <span className="ds-eyebrow">
                    {dialog.kind === "push"
                      ? `${local.channel} 推送详情预览`
                      : dialog.kind === "review"
                        ? "知识点复习 · 示例"
                        : dialog.kind === "chapter"
                          ? "章节详情 · 示例"
                          : dialog.kind === "search"
                            ? "搜索预览知识库"
                            : "界面配置预览"}
                  </span>
                  <h2>
                    {dialog.kind === "review" || dialog.kind === "push"
                      ? currentReview.title
                      : dialog.kind === "chapter"
                        ? currentChapter.title
                        : dialog.kind === "subject"
                          ? "添加新的学科"
                          : dialog.kind === "channel"
                            ? `${dialog.id} 接收配置`
                            : "找到你想复习的内容"}
                  </h2>
                </div>
                <button
                  className="ds-icon-button"
                  aria-label="关闭弹窗"
                  onClick={() => setDialog(null)}
                >
                  <X size={21} />
                </button>
              </div>
              {(dialog.kind === "review" || dialog.kind === "push") && (
                <>
                  <div className="ds-review-meta">
                    <SubjectTag id={currentReview.subject} />
                    <span>第 {currentReview.stage} 次复习</span>
                    <span className="ds-strategy">
                      {currentReview.strategy}
                    </span>
                  </div>
                  <section className="ds-question">
                    <span>主动回忆</span>
                    <h3>{currentReview.question}</h3>
                  </section>
                  {!showAnswer && (
                    <button
                      className="ds-button primary ds-answer-button"
                      onClick={() => setShowAnswer(true)}
                    >
                      查看知识点与解析 <ChevronRight size={16} />
                    </button>
                  )}
                  {showAnswer && (
                    <div className="ds-answer">
                      <h3>
                        <BookOpen size={17} />
                        知识点
                      </h3>
                      <p>{currentReview.content}</p>
                      <h3>
                        <Sparkles size={17} />
                        解析与理解
                      </h3>
                      <p>{currentReview.explanation}</p>
                      <div className="ds-source-reference">
                        <FileText size={19} />
                        <div>
                          <strong>Notion 原页面</strong>
                          <span>{currentReview.source}</span>
                        </div>
                        <button
                          className="ds-icon-button"
                          aria-label="打开Notion来源"
                          onClick={() => {
                            if (currentReview.sourceUrl?.startsWith("https://"))
                              window.open(
                                currentReview.sourceUrl,
                                "_blank",
                                "noopener,noreferrer",
                              );
                            else
                              setToast(
                                "当前为示例来源。正式同步后将提供原页面链接。",
                              );
                          }}
                        >
                          <ExternalLink size={17} />
                        </button>
                      </div>
                      <p className="ds-preview-caption">
                        示例笔记与解析，用于界面验收。
                      </p>
                    </div>
                  )}
                  {showAnswer && dialog.kind === "review" && (
                    <div className="ds-rating-section">
                      <span>这次回忆的掌握程度</span>
                      <div>
                        {["忘记", "困难", "记得", "熟练"].map(
                          (rating, index) => (
                            <button
                              key={rating}
                              className={`rating-${index}`}
                              disabled={local.completedReviews.includes(
                                currentReview.id,
                              )}
                              onClick={() => finishReview(rating)}
                            >
                              {rating}
                            </button>
                          ),
                        )}
                      </div>
                      {local.completedReviews.includes(currentReview.id) && (
                        <p className="ds-preview-caption">
                          这张卡片已在本次预览中完成。
                        </p>
                      )}
                    </div>
                  )}
                  {dialog.kind === "push" && (
                    <>
                      <div className="ds-info-note">
                        <Bell size={16} />
                        实际推送按渠道展示限制分段，或通过详情页提供完整内容。
                      </div>
                      <div className="ds-dialog-actions">
                        <Link
                          className="ds-button"
                          href="/preview/push"
                          target="_blank"
                          rel="noreferrer"
                        >
                          打开手机阅读页
                          <ExternalLink size={15} />
                        </Link>
                      </div>
                    </>
                  )}
                </>
              )}
              {dialog.kind === "chapter" && (
                <>
                  <div className="ds-review-meta">
                    <SubjectTag id={currentChapter.subject} />
                    <span className="ds-status">
                      {local.chapterStatus[currentChapter.id] ??
                        currentChapter.status}
                    </span>
                    <span>已记录 {currentChapter.sessions} 次学习</span>
                  </div>
                  <p className="ds-chapter-description">
                    {currentChapter.summary}
                  </p>
                  <div className="ds-chapter-timeline">
                    <h3>章节学习记录</h3>
                    {Array.from(
                      { length: Math.max(1, currentChapter.sessions) },
                      (_, index) => (
                        <div key={index}>
                          <span className="ds-timeline-dot" />
                          <div>
                            <strong>
                              {currentChapter.sessions
                                ? `第 ${index + 1} 次学习`
                                : "等待开始学习"}
                            </strong>
                            <p>
                              {index === 0
                                ? "建立章节结构，记录关键概念。"
                                : index === currentChapter.sessions - 1
                                  ? "补充例子，整理待解决的问题。"
                                  : "继续补充笔记，关联知识点。"}
                            </p>
                          </div>
                        </div>
                      ),
                    )}
                  </div>
                  <div className="ds-info-note">
                    <FileText size={16} />
                    正式章节状态来自 Notion，标记已完成后汇总与排期。
                  </div>
                  <div className="ds-dialog-actions">
                    <button
                      className="ds-button"
                      onClick={() =>
                        setToast("示例章节尚未绑定真实 Notion 页面。")
                      }
                    >
                      <ExternalLink size={15} />
                      查看 Notion 原文
                    </button>
                    <button
                      className="ds-button primary"
                      onClick={() => {
                        setLocal((previous) => ({
                          ...previous,
                          chapterStatus: {
                            ...previous.chapterStatus,
                            [currentChapter.id]: "已完成",
                          },
                        }));
                        setDialog(null);
                        setToast(
                          "已演示章节完成状态。真实总结和排期将在后端接入后生成。",
                        );
                      }}
                    >
                      预览标记已完成
                    </button>
                  </div>
                </>
              )}
              {dialog.kind === "subject" && (
                <form className="ds-dialog-form" onSubmit={addSubject}>
                  <label>
                    学科名称
                    <input
                      name="name"
                      autoComplete="off"
                      placeholder="例如：哲学、日语、历史"
                      required
                      maxLength={120}
                    />
                  </label>
                  <label>
                    学习方向
                    <textarea
                      name="description"
                      placeholder="记录你的学习方向与目标"
                      rows={3}
                    />
                  </label>
                  <p className="ds-preview-caption">
                    本次添加仅保存到当前浏览器的预览数据。
                  </p>
                  <div className="ds-dialog-actions">
                    <button
                      type="button"
                      className="ds-button"
                      onClick={() => setDialog(null)}
                    >
                      取消
                    </button>
                    <button className="ds-button primary" type="submit">
                      添加学科
                    </button>
                  </div>
                </form>
              )}
              {dialog.kind === "channel" && (
                <form
                  className="ds-dialog-form"
                  onSubmit={(event) => {
                    event.preventDefault();
                    const values = new FormData(event.currentTarget);
                    setLocal((previous) => ({
                      ...previous,
                      channel: dialog.id ?? "PushPlus",
                      pushTime: String(values.get("pushTime")),
                    }));
                    setDialog(null);
                    setToast("已保存预览推送偏好，真实接收身份尚待授权绑定。");
                  }}
                >
                  <label>
                    接收身份
                    <input
                      placeholder="真实账号绑定将在后端接入时完成"
                      disabled
                    />
                  </label>
                  <label>
                    推送时间
                    <select name="pushTime" defaultValue={local.pushTime}>
                      {[
                        "08:00",
                        "09:00",
                        "12:00",
                        "18:00",
                        "20:00",
                        "21:00",
                      ].map((time) => (
                        <option key={time}>{time}</option>
                      ))}
                    </select>
                  </label>
                  <div className="ds-info-note">
                    <ShieldCheck size={16} />
                    每位用户分别绑定接收身份和渠道凭据。
                  </div>
                  <div className="ds-dialog-actions">
                    <button className="ds-button primary" type="submit">
                      设为预览默认渠道
                    </button>
                  </div>
                </form>
              )}
              {dialog.kind === "search" && (
                <>
                  <label className="ds-dialog-search">
                    <Search size={19} />
                    <input
                      aria-label="搜索示例内容"
                      placeholder="输入知识点、章节或正文关键词"
                      value={query}
                      onChange={(event) => setQuery(event.target.value)}
                      autoFocus
                    />
                  </label>
                  <div className="ds-search-results">
                    {data.reviewItems
                      .filter((item) =>
                        `${item.title}${item.content}`
                          .toLowerCase()
                          .includes(query.toLowerCase()),
                      )
                      .map((item) => (
                        <button
                          key={item.id}
                          onClick={() =>
                            setDialog({ kind: "review", id: item.id })
                          }
                        >
                          <span
                            className={`ds-icon-tile ${getSubject(item.subject)?.color}`}
                          >
                            <BookOpen size={18} />
                          </span>
                          <span>
                            <strong>{item.title}</strong>
                            <small>
                              {getSubject(item.subject)?.name} · {item.source}
                            </small>
                          </span>
                          <ChevronRight size={17} />
                        </button>
                      ))}
                    {data.reviewItems.filter((item) =>
                      `${item.title}${item.content}`
                        .toLowerCase()
                        .includes(query.toLowerCase()),
                    ).length === 0 && (
                      <div className="ds-empty">
                        <Search />
                        <p>没有找到符合条件的示例内容。</p>
                      </div>
                    )}
                  </div>
                </>
              )}
            </>
          )}
        </div>
      </dialog>
    </div>
  );
}
