"use client";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { Bell, Bot, BookOpen, History, Maximize2, Network, Plus, Search, TrendingUp, BrainCircuit, CalendarDays, CheckCircle2, FileText, Home, Layers3, LoaderCircle, LogOut, Mail, RefreshCw, Settings2, ShieldCheck, Users, X, } from "lucide-react";
import { useAuth } from "@/components/AuthProvider";
import { learningDestination, webApi } from "@/lib/workspace";
import type { PortalUser, ReviewContent, ReviewTask, WorkspaceData, } from "@/lib/workspace";
import Setup from "./Setup";
import MemoryPreferences from "./MemoryPreferences";
import AdminUserForm from "./AdminUserForm";
import "./portal.css";
import LearningExperience from "./LearningExperience";
import type { Chapter, Knowledge } from "./LearningExperience";
import "./learning-experience.css";
type Point = Knowledge;
const statusLabel: Record<string, string> = {
    pending: "等待处理",
    processing: "发送中",
    running: "处理中",
    succeeded: "已完成",
    failed: "失败",
    sent: "已提交邮件服务器",
    cancelled: "已取消",
    skipped: "已跳过",
    not_started: "未开始",
    in_progress: "进行中",
    completed: "已完成",
};
export default function Workspace({ onboarding = false, }: {
    onboarding?: boolean;
}) {
    const auth = useAuth();
    const router = useRouter();
    const params = useSearchParams();
    const requestedView = params.get("view") || "home";
    const view = ["home", "learning", "review", "knowledge", "subjects", "notion", "calendar", "statistics", "history", "assistant", "mail", "settings", "admin"].includes(requestedView) ? requestedView : "home";
    const requestedTask = params.get("task");
    const destination = learningDestination(requestedTask
        ? "/app?view=review&task=" + encodeURIComponent(requestedTask)
        : params.get("next"));
    const openedLink = useRef<string | null>(null);
    const reviewGeneration = useRef(0);
    const [data, setData] = useState<WorkspaceData | null>(null);
    const [tasks, setTasks] = useState<ReviewTask[]>([]);
    const [taskOverflow, setTaskOverflow] = useState(false);
    const [points, setPoints] = useState<Point[]>([]);
    const [error, setError] = useState("");
    const [message, setMessage] = useState("");
    const [pending, setPending] = useState(false);
    const [selectedTask, setSelectedTask] = useState<ReviewTask | null>(null);
    const [activeChapter, setActiveChapter] = useState<Chapter | null>(null);
    const [studyMinutes, setStudyMinutes] = useState("25");
    const [studyNotes, setStudyNotes] = useState("");
    const studySubmission = useRef<{
        signature: string;
        key: string;
        body: {
            started_at: string;
            ended_at: string;
            notes: string;
        };
    } | null>(null);
    const searchInput = useRef<HTMLInputElement>(null);
    const [globalQuery, setGlobalQuery] = useState("");
    const [chapterId, setChapterId] = useState<string | null>(null);
    const [reviewContent, setReviewContent] = useState<ReviewContent | null>(null);
    const [answer, setAnswer] = useState(false);
    const [point, setPoint] = useState<Point | null>(null);
    const [pointItem, setPointItem] = useState<{ question: string; answer: string; explanation: string } | null>(null);
    const [pointItemError, setPointItemError] = useState("");
    const dialog = useRef<HTMLDialogElement>(null);
    const started = useRef(Date.now());
    const completion = useRef<{
        rating: string;
        duration_seconds: number;
        reviewed_at: string;
    } | null>(null);
    const load = useCallback(async () => {
        const [workspace, review, resumed, knowledge] = await Promise.all([
            webApi<WorkspaceData>("/workspace"),
            webApi<{
                items: ReviewTask[];
                has_more: boolean;
            }>("/review-tasks?limit=100&status=pending"),
            webApi<{ items: ReviewTask[]; has_more: boolean }>("/review-tasks?limit=100&status=in_progress"),
            webApi<{
                items: Point[];
                has_more: boolean;
            }>("/knowledge-points?limit=100"),
        ]);
        setData(workspace);
        setTasks([...review.items, ...resumed.items]);
        setTaskOverflow(review.has_more || resumed.has_more);
        setPoints(knowledge.items);
    }, []);
    useEffect(() => {
        if (auth.ready && !auth.authenticated) {
            router.replace(destination === "/app"
                ? "/"
                : "/?next=" + encodeURIComponent(destination));
            return;
        }
        if (!auth.authenticated)
            return;
        let active = true;
        load().catch((cause) => active && setError(cause.message));
        const timer = setInterval(() => load().catch((cause) => active && setError(cause.message)), 15000);
        return () => {
            active = false;
            clearInterval(timer);
        };
    }, [auth.ready, auth.authenticated, load, router, destination]);
    useEffect(() => {
        if (data && !onboarding && !data.profile.onboarding_completed_at)
            router.replace("/onboarding" +
                (destination === "/app"
                    ? ""
                    : "?next=" + encodeURIComponent(destination)));
    }, [data, onboarding, router, destination]);
    useEffect(() => {
        if (!requestedTask) {
            openedLink.current = null;
            return;
        }
        if (view !== "review" ||
            onboarding ||
            !data?.profile.onboarding_completed_at)
            return;
        if (openedLink.current === requestedTask)
            return;
        openedLink.current = requestedTask;
        let active = true;
        setPending(true);
        webApi<ReviewContent>(`/review-tasks/${encodeURIComponent(requestedTask)}/content`)
            .then((content) => {
            if (!active)
                return;
            setReviewContent(content);
            setSelectedTask(content.task);
            setAnswer(false);
            started.current = Date.now();
            completion.current = null;
        })
            .catch((cause) => active && setError(cause.message))
            .finally(() => active && setPending(false));
        return () => {
            active = false;
        };
    }, [requestedTask, view, onboarding, data?.profile.onboarding_completed_at]);
    useEffect(() => {
        if ((selectedTask || point || chapterId) &&
            dialog.current &&
            !dialog.current.open)
            dialog.current.showModal();
    }, [selectedTask, point, chapterId]);
    async function act(action: () => Promise<void>) {
        setPending(true);
        setError("");
        setMessage("");
        try {
            await action();
            await load();
        }
        catch (cause) {
            setError(cause instanceof Error ? cause.message : "操作失败");
        }
        finally {
            setPending(false);
        }
    }
    async function openReview(task: ReviewTask) {
        const request = ++reviewGeneration.current;
        await act(async () => {
            const content = await webApi<ReviewContent>(`/review-tasks/${task.id}/content`);
            if (request !== reviewGeneration.current) return;
            setReviewContent(content);
            setAnswer(false);
            setSelectedTask(content.task);
            started.current = Date.now();
            completion.current = null;
        });
    }
    function openChapter(chapter: Chapter) {
        setActiveChapter(chapter);
        setChapterId(chapter.id);
        setStudyMinutes("25");
        setStudyNotes("");
        studySubmission.current = null;
    }
    useEffect(() => {
        function shortcut(event: KeyboardEvent) {
            if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
                event.preventDefault();
                searchInput.current?.focus();
            }
        }
        window.addEventListener("keydown", shortcut);
        return () => window.removeEventListener("keydown", shortcut);
    }, []);
    function closeDialog() {
        reviewGeneration.current++;
        dialog.current?.close();
        setSelectedTask(null);
        setPoint(null);
        setChapterId(null);
        setActiveChapter(null);
        setReviewContent(null);
        if (requestedTask)
            router.replace("/app?view=review");
    }
    const unfinished = tasks.filter((t) => ["pending", "in_progress"].includes(t.status));
    useEffect(() => { reviewGeneration.current++; }, [view]);
    const selectedChapter = activeChapter || data?.chapters.find((c) => c.id === chapterId);
    useEffect(() => {
        setPointItem(null); setPointItemError("");
        if (!point) return;
        let active = true;
        webApi<{ items: { question: string; answer: string; explanation: string }[] }>(`/knowledge-points/${point.id}/review-items?limit=1`)
            .then(result => { if (active) setPointItem(result.items[0] || null); })
            .catch(cause => { if (active) setPointItemError(cause.message); });
        return () => { active = false; };
    }, [point]);

    if (!auth.ready || !auth.authenticated || !data)
        return (<div className="portal portal-loading">
        <LoaderCircle className="portal-spin"/>
        <span>{error || "正在载入你的学习空间…"}</span>
      </div>);
    if (onboarding)
        return (<div className="portal portal-onboarding">
        <header className="portal-onboard-header">
          <Link href="/" className="portal-brand">
            <BrainCircuit size={32}/>
            <span>
              <strong>AI 学习记忆系统</strong>
              <small>AI Learning Memory OS</small>
            </span>
          </Link>
          <span>{data.user.email}</span>
          <button className="portal-text-button" onClick={auth.signOut}>
            退出登录
          </button>
        </header>
        <main>
          <h1>你好，{data.user.display_name}</h1>
          <p className="portal-muted portal-onboard-intro">
            花几分钟连接你的笔记与邮箱，让学习和复习自然衔接。
          </p>
          <Setup data={data} reload={load} onboarding onDone={() => router.replace(destination)}/>
        </main>
      </div>);
    const navigation = [
        { id: "home", name: "学习主页", icon: Home },
        { id: "learning", name: "章节学习", icon: BookOpen },
        { id: "review", name: "今日复习", icon: RefreshCw },
        { id: "knowledge", name: "知识库", icon: Layers3 },
        { id: "subjects", name: "学科管理", icon: Network },
        { id: "notion", name: "Notion 同步", icon: FileText },
        { id: "calendar", name: "复习日历", icon: CalendarDays },
        { id: "statistics", name: "学习统计", icon: TrendingUp },
        { id: "history", name: "复习历史", icon: History },
        { id: "assistant", name: "AI 学习助手", icon: Bot },
        { id: "mail", name: "邮件通知", icon: Mail },
        { id: "settings", name: "设置", icon: Settings2 },
        ...(data.user.role === "admin" ? [{ id: "admin", name: "管理员后台", icon: ShieldCheck }] : []),
    ];
    const hour = Number(new Intl.DateTimeFormat("en-GB", { timeZone: data.user.timezone, hour: "numeric", hourCycle: "h23" }).format(new Date()));
    const greeting = hour < 6 ? "夜深了" : hour < 12 ? "早上好" : hour < 18 ? "下午好" : "晚上好";
    return (<div className={"portal portal-app lx-shell" + (requestedTask ? " portal-review-entry" : "")}>
      <aside className="portal-sidebar">
        <Link href="/app" className="portal-brand">
          <BrainCircuit size={32}/>
          <span>
            <strong>AI 学习记忆系统</strong>
            <small>AI Learning Memory OS</small>
          </span>
        </Link>
        <nav>
          {navigation.map((item) => item.id === "admin" ? (
            <a href={process.env.NEXT_PUBLIC_ADMIN_APP_URL || "http://127.0.0.1:3001"} key={item.id}>
              <item.icon size={19}/>
              {item.name}
            </a>
          ) : (<Link href={item.id === "home" ? "/app" : `/app?view=${item.id}`} key={item.id} className={view === item.id ? "active" : ""}>
              <item.icon size={19}/>
              {item.name}
              {item.id === "review" && unfinished.length > 0 && (<b>{unfinished.length}{taskOverflow ? "+" : ""}</b>)}
            </Link>))}
        </nav>
        <div className="portal-sidebar-subjects">
          <h3>我的学科</h3>
          {data.subjects.length ? (data.subjects.map((s) => (<Link href={`/app?view=knowledge&subject=${s.id}`} key={s.id}>
                <BookOpen size={16}/>
                {s.name}
                <small>{s.count}</small>
              </Link>))) : (<p>连接笔记后，学科会显示在这里。</p>)}
          <Link className="lx-add-subject" href="/app?view=subjects"><Plus size={15}/>添加学科</Link>
        </div>
        <footer>
          <span className="lx-avatar">{data.user.display_name.slice(0, 1).toUpperCase()}</span>
          <div>
            <strong>{data.user.display_name}</strong>
            <small>{data.user.email}</small>
          </div>
          <button title="退出登录" aria-label="退出登录" onClick={auth.signOut}>
            <LogOut size={18}/>
          </button>
        </footer>
      </aside>
      <main className="portal-main">
        <header className="portal-main-header">
          <div>
            <h1>
              {view === "home"
            ? `${greeting}，${data.user.display_name} 👋`
            : navigation.find((item) => item.id === view)?.name ||
                "学习空间"}
            </h1>
            <p>
              {new Date().toLocaleDateString("zh-CN", {
            dateStyle: "full",
            timeZone: data.user.timezone,
        })}
            </p>
          </div>
          <div className="lx-header-actions">
            <form className="lx-header-search" onSubmit={event => { event.preventDefault(); router.push("/app?view=knowledge&q=" + encodeURIComponent(globalQuery.trim())); }}>
              <Search size={17}/><input ref={searchInput} aria-label="全局搜索" placeholder="搜索知识点、笔记…" maxLength={200} value={globalQuery} onChange={event => setGlobalQuery(event.target.value)}/><kbd>Ctrl + K</kbd>
            </form>
            <Link className="lx-icon-button" aria-label="查看通知" href="/app?view=mail"><Bell size={20}/>{data.mail_history.some(j => j.status === "failed") && <i />}</Link>
            <button className="lx-icon-button" title="全屏" aria-label="切换全屏" onClick={async () => {
            try {
                if (document.fullscreenElement)
                    await document.exitFullscreen();
                else
                    await document.documentElement.requestFullscreen();
            }
            catch {
                setMessage("当前浏览器不支持切换全屏，可使用浏览器的全屏菜单。");
            }
        }}><Maximize2 size={18}/></button>
            <button className="lx-icon-button" title="刷新" aria-label="刷新" disabled={pending} onClick={() => act(load)}><RefreshCw size={18} className={pending ? "portal-spin" : ""}/></button>
          </div>
        </header>
        {error && (<p role="alert" className="portal-error">
            {error}
          </p>)}
        {message && (<p role="status" className="portal-success">
            {message}
          </p>)}
        {view === "settings" ? <><div className="lx-settings-intro"><h2>让学习系统，更合你的习惯</h2><p>邮箱、笔记和模型，你可以随时在这里调整。</p></div><Setup data={data} reload={load}/><MemoryPreferences profile={data.profile} busy={pending} save={act}/></> : view === "admin" && data.user.role === "admin" ? <LiveAdmin /> : <LearningExperience key={`${view}:${params.get("subject") || ""}:${params.get("q") || ""}:${params.get("create") || ""}`} view={view} data={data} tasks={tasks} points={points} pending={pending} onChapter={openChapter} onPoint={setPoint} onReview={openReview} act={act}/>}
      </main>
      {(selectedTask || point || chapterId) && (<dialog className="portal portal-dialog" ref={dialog} onCancel={closeDialog}>
          <button className="portal-dialog-close" aria-label="关闭详情" onClick={closeDialog}>
            <X size={22}/>
          </button>
          {selectedChapter && (<>
              <span className="portal-eyebrow">
                {statusLabel[selectedChapter.status]}
              </span>
              <h2>{selectedChapter.title}</h2>
              <p className="portal-prose">
                {selectedChapter.content || "章节正文尚未同步。"}
              </p>
              {selectedChapter.source_url && (<a className="portal-inline-link" href={selectedChapter.source_url} target="_blank" rel="noreferrer">
                  打开 Notion 原始笔记 ↗
                </a>)}
              <form className="lx-study-form" onSubmit={event => {
                    event.preventDefault();
                    act(async () => {
                        const duration = Number(studyMinutes);
                        if (!Number.isFinite(duration) || duration < 1 || duration > 1440)
                            throw new Error("请填写1至1440分钟的学习时长");
                        const signature = JSON.stringify([selectedChapter.id, duration, studyNotes]);
                        if (studySubmission.current?.signature !== signature) {
                            const end = new Date();
                            studySubmission.current = { signature, key: crypto.randomUUID(), body: { started_at: new Date(end.getTime() - duration * 60000).toISOString(), ended_at: end.toISOString(), notes: studyNotes } };
                        }
                        await webApi(`/chapters/${selectedChapter.id}/study-sessions`, { method: "POST", key: studySubmission.current.key, body: studySubmission.current.body });
                        studySubmission.current = null;
                        closeDialog();
                        setMessage("这次学习已记录，章节无需一次学完。");
                    });
                }}><h3>记下这一次学习</h3><div><label>学习时长（分钟）<input type="number" min="1" max="1440" required value={studyMinutes} onChange={event => setStudyMinutes(event.target.value)}/></label><label>这次学到哪里了？<input maxLength={10000} value={studyNotes} onChange={event => setStudyNotes(event.target.value)} placeholder="例如：梳理了请求发起流程"/></label><button className="portal-primary" disabled={pending}>保存学习记录</button></div></form>
              <div className="portal-inline">
                <button className="portal-secondary" disabled={pending} onClick={() => act(async () => {
                    await webApi(`/chapters/${selectedChapter.id}`, {
                        method: "PATCH",
                        version: selectedChapter.version,
                        body: { status: "in_progress" },
                    });
                    closeDialog();
                })}>
                  标记进行中
                </button>
                <button className="portal-primary" disabled={pending} onClick={() => act(async () => {
                    await webApi(`/chapters/${selectedChapter.id}/complete`, {
                        method: "POST",
                    });
                    closeDialog();
                    setMessage("章节已完成，知识提取任务已创建。");
                })}>
                  完成整章
                </button>
              </div>
            </>)}
          {point && (<>
              <span className="portal-eyebrow">
                {point.manual_revision
                    ? "人工修订"
                    : "AI 整理 · 已关联原始章节"}
              </span>
              <h2>{point.title}</h2>
              <p className="portal-prose">{point.body}</p>{pointItemError && <p role="alert" className="portal-error">复习解析暂时不可用：{pointItemError}</p>}
              {pointItem && <><section className="portal-recall"><h3>主动回忆问题</h3><p className="portal-prose">{pointItem.question}</p></section><h3>答案与解析</h3><p className="portal-prose">{pointItem.answer}</p><p className="portal-prose">{pointItem.explanation}</p></>}
              {pointItemError && <p className="portal-error" role="alert">复习解析读取失败：{pointItemError}</p>}
              {point.status === "draft" && <div className="portal-inline"><button className="portal-primary" disabled={pending} onClick={() => act(async () => { await webApi(`/knowledge-points/${point.id}/activate`, { method: "POST" }); closeDialog(); setMessage("知识点已加入复习，系统将按记忆策略安排任务。"); })}><RefreshCw size={16}/>加入复习计划</button></div>}

              {point.version !== undefined && <details className="portal-recall" key={point.version}>
                <summary>人工修订</summary>
                <form onSubmit={event => {
                    event.preventDefault();
                    const input = new FormData(event.currentTarget);
                    void act(async () => {
                        const updated = await webApi<Point>(`/knowledge-points/${point.id}`, {
                            method: "PATCH", version: point.version,
                            body: { title: input.get("title"), body: input.get("body"), summary: input.get("summary") },
                        });
                        setPoint(updated);
                        setMessage("人工修订已保存。");
                    });
                }}>
                    <label>知识标题<input name="title" required maxLength={300} defaultValue={point.title}/></label>
                    <label>知识正文<textarea name="body" required defaultValue={point.body}/></label>
                    <label>知识摘要<textarea name="summary" defaultValue={point.summary}/></label>
                    <button className="portal-secondary" disabled={pending}>保存修订</button>
                </form>
              </details>}

              {point.source_url && (<a className="portal-inline-link" href={point.source_url} target="_blank" rel="noreferrer">
                  查看 Notion 原文 ↗
                </a>)}
            </>)}
          {reviewContent && selectedTask && (<>
              <span className="portal-eyebrow">
                {reviewContent.schedule?.strategy} · 已复习{" "}
                {reviewContent.schedule?.review_count || 0} 次
              </span>
              <h2>{reviewContent.knowledge.title}</h2>
              {reviewContent.schedule && <p className="lx-help">
                  当前阶段 {reviewContent.schedule.strategy === "fsrs"
                    ? (reviewContent.schedule.review_count ? "复习巩固" : "首次学习")
                    : `第 ${reviewContent.schedule.interval_index + 1} 阶段`} · 计划时间 {new Date(reviewContent.schedule.due_at).toLocaleString("zh-CN", { timeZone: data.user.timezone })}
              </p>}
              <section className="portal-recall">
                <h3>先尝试主动回忆</h3>
                <p>
                  {reviewContent.review_item?.question ||
                    reviewContent.knowledge.title}
                </p>
              </section>
              {!answer ? (<button className="portal-primary" onClick={() => setAnswer(true)}>
                  查看知识点与解析
                </button>) : (<>
                  <h3>知识正文</h3>
                  <p className="portal-prose">{reviewContent.knowledge.body}</p>
                  <h3>答案与解析</h3>
                  {!reviewContent.review_item && <p className="portal-prose">这张卡片尚未生成问答。先回忆它的关键内容，再对照原文检查。</p>}
                  <p className="portal-prose">
                    {reviewContent.review_item?.answer}
                  </p>
                  <p className="portal-prose">
                    {reviewContent.review_item?.explanation}
                  </p>
                  {reviewContent.knowledge.source_url && (<a href={reviewContent.knowledge.source_url} target="_blank" rel="noreferrer">
                      Notion 原始笔记 ↗
                    </a>)}
                  {!["pending", "in_progress"].includes(selectedTask.status) && (<p role="status">
                      本次任务{statusLabel[selectedTask.status] || "已结束"}。
                    </p>)}
                  {["pending", "in_progress"].includes(selectedTask.status) && (<div className="portal-rating">
                      {[
                            ["again", "忘记"],
                            ["hard", "困难"],
                            ["good", "记得"],
                            ["easy", "熟练"],
                        ].map(([rating, label]) => (<button key={rating} disabled={pending} onClick={() => act(async () => {
                                if (completion.current &&
                                    completion.current.rating !== rating) {
                                    throw new Error("请重试上次选择的评分，以核验提交结果");
                                }
                                completion.current ||= {
                                    rating,
                                    duration_seconds: Math.round((Date.now() - started.current) / 1000),
                                    reviewed_at: new Date().toISOString(),
                                };
                                await webApi(`/review-tasks/${selectedTask.id}/complete`, {
                                    method: "POST",
                                    key: `review-${selectedTask.id}`,
                                    body: completion.current,
                                });
                                closeDialog();
                                setMessage("复习已保存，下次复习时间已更新。");
                            })}>
                          {label}
                        </button>))}
                    </div>)}
                </>)}
              {["pending", "in_progress"].includes(selectedTask.status) && <div className="portal-inline">
                <button className="portal-secondary" disabled={pending} onClick={() => act(async () => {
                    await webApi(`/review-tasks/${selectedTask.id}/skip`, { method: "POST", key: `skip-${selectedTask.id}` });
                    closeDialog();
                    setMessage("本次任务已跳过，未记录评分。");
                })}>跳过本次</button>
                <button className="portal-secondary" disabled={pending} onClick={() => act(async () => {
                    await webApi(`/review-tasks/${selectedTask.id}/defer`, {
                        method: "POST", key: `defer-next-day-${selectedTask.id}`, body: { days: 1 },
                    });
                    closeDialog();
                    setMessage("复习已延期，时间按账户时区计算。");
                })}>延期一天</button>
              </div>}
            </>)}
          {error && (<p role="alert" className="portal-error">
              {error}
            </p>)}
        </dialog>)}
    </div>);
}
function Empty({ title, detail, href, action, }: {
    title: string;
    detail: string;
    href?: string;
    action?: string;
}) {
    return (<div className="portal-empty">
      <BookOpen size={30}/>
      <h3>{title}</h3>
      <p>{detail}</p>
      {href && (<Link className="portal-primary" href={href}>
          {action}
        </Link>)}
    </div>);
}
function LiveAdmin() {
    const [users, setUsers] = useState<PortalUser[]>([]);
    const [userMessage, setUserMessage] = useState("");
    const [sessions, setSessions] = useState<{
        id: string;
        user_id: string;
        display_name: string;
        email: string;
        created_at: string;
        last_seen_at: string;
        logged_out_at: string | null;
        online: boolean;
    }[]>([]);
    const [query, setQuery] = useState("");
    const [appliedQuery, setAppliedQuery] = useState("");
    const [usersCursor, setUsersCursor] = useState<string | null>(null);
    const [sessionsCursor, setSessionsCursor] = useState<string | null>(null);
    const [loadingList, setLoadingList] = useState(false);
    const [selection, setSelection] = useState("");
    const selectedUser = useRef("");
    const [loadingUser, setLoadingUser] = useState(false);
    const [points, setPoints] = useState<Point[]>([]);
    const [history, setHistory] = useState<{
        id: string;
        reviewed_at: string;
        rating: string;
    }[]>([]);
    const [error, setError] = useState("");
    useEffect(() => {
        Promise.all([
            webApi<{
                items: PortalUser[];
                next_cursor: string | null;
            }>("/admin/users?limit=100"),
            webApi<{
                items: typeof sessions;
                next_cursor: string | null;
            }>("/admin/sessions?limit=20"),
        ])
            .then(([u, s]) => {
            setUsers(u.items);
            setUsersCursor(u.next_cursor);
            setSessions(s.items);
            setSessionsCursor(s.next_cursor);
        })
            .catch((e) => setError(e.message));
    }, []);
    async function loadList(kind: "users" | "sessions", cursor: string | null = null, search = appliedQuery) {
        setLoadingList(true);
        setError("");
        try {
            if (kind === "users") {
                const params = new URLSearchParams({ limit: "100", q: search });
                if (cursor)
                    params.set("cursor", cursor);
                const result = await webApi<{
                    items: PortalUser[];
                    next_cursor: string | null;
                }>("/admin/users?" + params);
                setUsers((current) => cursor ? [...current, ...result.items] : result.items);
                setUsersCursor(result.next_cursor);
                setAppliedQuery(search);
            }
            else {
                const params = new URLSearchParams({ limit: "20" });
                if (cursor)
                    params.set("cursor", cursor);
                const result = await webApi<{
                    items: typeof sessions;
                    next_cursor: string | null;
                }>("/admin/sessions?" + params);
                setSessions((current) => cursor ? [...current, ...result.items] : result.items);
                setSessionsCursor(result.next_cursor);
            }
        }
        catch (cause) {
            setError(cause instanceof Error ? cause.message : "读取失败");
        }
        finally {
            setLoadingList(false);
        }
    }
    async function choose(userId: string) {
        selectedUser.current = userId;
        setSelection(userId);
        setPoints([]);
        setHistory([]);
        setError("");
        setLoadingUser(Boolean(userId));
        if (!userId)
            return;
        try {
            const [p, h] = await Promise.all([
                webApi<{
                    items: Point[];
                }>(`/admin/users/${userId}/knowledge-points`),
                webApi<{
                    items: typeof history;
                }>(`/admin/users/${userId}/review-history`),
            ]);
            if (selectedUser.current !== userId)
                return;
            setPoints(p.items);
            setHistory(h.items);
        }
        catch (cause) {
            if (selectedUser.current === userId)
                setError(cause instanceof Error ? cause.message : "读取失败");
        }
        finally {
            if (selectedUser.current === userId)
                setLoadingUser(false);
        }
    }
    return (<div className="portal-dashboard-grid portal-admin-grid">
      <section className="portal-panel">
        <div className="portal-admin-heading">
          <h2>用户知识与复习</h2>
          <AdminUserForm onCreated={(user) => {
            setUsers([user]);
            setUsersCursor(null);
            setQuery(user.email);
            setAppliedQuery(user.email);
            setUserMessage(`已创建用户 ${user.display_name}，可使用新账号登录。`);
            void choose(user.id);
        }}/>
        </div>
        {userMessage && (<p className="portal-success" role="status">
            {userMessage}
          </p>)}
        {error && (<p className="portal-error" role="alert">
            {error}
          </p>)}
        <form className="portal-inline" onSubmit={(event) => {
            event.preventDefault();
            void choose("");
            void loadList("users", null, query);
        }}>
          <input aria-label="搜索用户" placeholder="搜索姓名或邮箱" value={query} onChange={(event) => setQuery(event.target.value)}/>
          <button className="portal-secondary" disabled={loadingList}>
            搜索
          </button>
        </form>
        <label>
          查看用户
          <select aria-label="查看用户" value={selection} onChange={(e) => choose(e.target.value)}>
            <option value="">选择用户</option>
            {users.map((u) => (<option key={u.id} value={u.id}>
                {u.display_name} · {u.email}
              </option>))}
          </select>
        </label>
        {usersCursor && (<button className="portal-text-button" disabled={loadingList} onClick={() => loadList("users", usersCursor)}>
            加载更多用户
          </button>)}
        {loadingUser && <p role="status">正在读取用户数据…</p>}
        <h3>知识库</h3>
        {selection && !loadingUser && !error && points.length === 0 && (<p className="portal-muted">该用户尚无知识点。</p>)}
        {points.map((p) => (<details key={p.id}>
            <summary>{p.title}</summary>
            <p className="portal-prose">{p.body}</p>
          </details>))}
        <h3>复习记录</h3>
        {selection && !loadingUser && !error && history.length === 0 && (<p className="portal-muted">该用户尚无复习记录。</p>)}
        {history.map((h) => (<p className="portal-list-row" key={h.id}>
            {new Date(h.reviewed_at).toLocaleString("zh-CN")} · {h.rating}
          </p>))}
      </section>
      <section className="portal-panel">
        <h2>最近登录与在线状态</h2>
        <div className="portal-admin-sessions">
          {sessions.map((s) => (<div className="portal-list-row" key={s.id}>
              <Users size={18}/>
              <span>
                <strong>
                  {s.display_name}
                  <small>{s.email}</small>
                </strong>
                <small>
                  登录 {new Date(s.created_at).toLocaleString("zh-CN")}
                  <br />
                  最后活跃 {new Date(s.last_seen_at).toLocaleString("zh-CN")}
                  <br />
                  {s.logged_out_at
                ? `退出 ${new Date(s.logged_out_at).toLocaleString("zh-CN")}`
                : "会话保持登录"}
                </small>
              </span>
              <em>{s.online ? "在线" : "离线"}</em>
            </div>))}
        </div>
        {sessionsCursor && (<button className="portal-text-button" disabled={loadingList} onClick={() => loadList("sessions", sessionsCursor)}>
            加载更早的登录记录
          </button>)}
      </section>
    </div>);
}
