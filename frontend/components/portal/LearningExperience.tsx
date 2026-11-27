"use client";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Fragment, useCallback, useEffect, useId, useRef, useState } from "react";
import type { CSSProperties, FormEvent, ReactNode } from "react";
import { ArrowRight, ArrowUpRight, BookOpen, Bot, CalendarDays, Check, CheckCircle2, ChevronLeft, ChevronRight, Clock3, ExternalLink, FileText, Flame, FolderOpen, Layers3, LoaderCircle, Mail, Network, Plus, RefreshCw, Search, Settings2, Sparkles, Target, TrendingUp, X } from "lucide-react";
import { useReviewWorkload, ReviewWorkloadPanel } from "./ReviewWorkloadPanel";
import { webApi } from "@/lib/workspace";
import type { ProcessingProgress, ReviewTask, WorkspaceData, WorkspaceInsights } from "@/lib/workspace";
export type Knowledge = {
    id: string;
    title: string;
    body: string;
    summary: string;
    subject_id: string;
    source_url: string | null;
    manual_revision: boolean;
    status?: string;
    version?: number;
};
export type Chapter = WorkspaceData["chapters"][number];
type History = {
    id: string;
    task_id: string;
    knowledge_title: string;
    subject_id: string;
    rating: string;
    strategy: string;
    duration_seconds: number;
    reviewed_at: string;
};
type Page<T> = {
    items: T[];
    next_cursor: string | null;
    has_more: boolean;
};
type Props = {
    view: string;
    data: WorkspaceData;
    tasks: ReviewTask[];
    points: Knowledge[];
    pending: boolean;
    onChapter: (chapter: Chapter) => void;
    onPoint: (point: Knowledge) => void;
    onReview: (task: ReviewTask) => void;
    act: (action: () => Promise<void>) => Promise<void>;
};
export const palette = ["#4e80ff", "#9b71f7", "#30bfc3", "#f7aa64", "#ed85a3", "#8da2c9"];
export const statusNames: Record<string, string> = { not_started: "未开始", in_progress: "进行中", completed: "已完成", pending: "待复习", skipped: "已跳过", active: "已激活", draft: "草稿", archived: "已归档", again: "忘记", hard: "困难", good: "记得", easy: "熟练", succeeded: "已完成", failed: "失败", running: "处理中", processing: "发送中", sent: "已提交邮件服务器", cancelled: "已取消" };
const href = (view: string) => view === "home" ? "/app" : `/app?view=${view}`;
const num = (value: number) => value.toLocaleString("zh-CN");
const minutes = (seconds: number) => `${Math.round(seconds / 60)} 分钟`;
const dateText = (value: string, zone: string) => new Date(value).toLocaleString("zh-CN", { timeZone: zone, month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
const dayKey = (year: number, month: number, day: number) => `${year}-${String(month + 1).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
function Panel({ title, action, children, className = "" }: {
    title: string;
    action?: ReactNode;
    children: ReactNode;
    className?: string;
}) {
    return <section className={`lx-panel ${className}`}><div className="lx-panel-heading"><h2>{title}</h2>{action}</div>{children}</section>;
}
function More({ view, children = "查看全部" }: {
    view: string;
    children?: ReactNode;
}) { return <Link className="lx-more" href={href(view)}>{children}<ChevronRight size={14}/></Link>; }
function Empty({ icon = "book", title, detail, action }: {
    icon?: string;
    title: string;
    detail: string;
    action?: ReactNode;
}) {
    const Icon = icon === "review" ? RefreshCw : icon === "chart" ? TrendingUp : BookOpen;
    return <div className="lx-empty"><div className="lx-empty-orbit"><Icon size={25}/><i /><i /></div><h3>{title}</h3><p>{detail}</p>{action}</div>;
}
function Badge({ value }: {
    value: string;
}) { return <span className={`lx-badge lx-status-${value}`}>{statusNames[value] || value}</span>; }
function Metric({ title, value, unit, note, icon, color = "blue" }: {
    title: string;
    value: ReactNode;
    unit?: string;
    note: string;
    icon: ReactNode;
    color?: string;
}) {
    return <article className={`lx-metric lx-${color}`}><span className="lx-metric-icon">{icon}</span><div><p>{title}</p><strong>{value}<small>{unit}</small></strong></div><span className="lx-metric-note">{note}</span></article>;
}
function Ring({ value, label, caption }: {
    value: number;
    label: string;
    caption: string;
}) {
    return <div className="lx-ring" style={{ "--progress": `${Math.max(0, Math.min(100, value))}%` } as CSSProperties} role="img" aria-label={`${caption} ${label}`}><div><strong>{label}</strong><small>{caption}</small></div></div>;
}
function Trend({ activity }: {
    activity: WorkspaceInsights["activity"];
}) {
    const id = useId().replace(/:/g, "");
    const [selected, setSelected] = useState<number | null>(null);
    const maxHours = Math.max(1, ...activity.map(a => a.study_seconds / 3600));
    const maxCount = Math.max(5, ...activity.map(a => a.reviews));
    const x = (i: number) => 34 + i * 470 / Math.max(1, activity.length - 1);
    const y = (seconds: number) => 166 - seconds / 3600 / maxHours * 125;
    const points = activity.map((a, i) => `${x(i)},${y(a.study_seconds)}`).join(" ");
    return <div className="lx-trend"><div className="lx-chart-legend"><span><i />学习时长（小时）</span><span><i />复习完成数（右轴）</span></div><svg viewBox="0 0 550 200" role="img" aria-label="真实学习时长与复习次数趋势"><defs><linearGradient id={`line-${id}`} x2="0" y2="1"><stop stopColor="#5287ff" stopOpacity=".2"/><stop offset="1" stopColor="#5287ff" stopOpacity="0"/></linearGradient><linearGradient id={`bar-${id}`} x2="0" y2="1"><stop stopColor="#ac85fa" stopOpacity=".8"/><stop offset="1" stopColor="#e6dbff" stopOpacity=".5"/></linearGradient></defs>{[0, 1, 2, 3].map(i => <g key={i}><line x1="30" x2="518" y1={166 - i * 42} y2={166 - i * 42} stroke="#edf1f8" strokeDasharray="3 4"/><text x="3" y={170 - i * 42}>{(maxHours * i / 3).toFixed(1)}h</text><text x="525" y={170 - i * 42}>{Math.round(maxCount * i / 3)}</text></g>)}<polygon points={`34,166 ${points} 504,166`} fill={`url(#line-${id})`}/>{activity.map((a, i) => <g key={a.date} onMouseEnter={() => setSelected(i)} onMouseLeave={() => setSelected(null)}><rect x={x(i) - 5} y={166 - a.reviews / maxCount * 125} width="10" height={a.reviews / maxCount * 125} rx="3" fill={`url(#bar-${id})`}/><rect x={x(i) - 12} y="30" width="24" height="145" fill="transparent"><title>{a.date} · 学习{minutes(a.study_seconds)} · 复习{a.reviews}次</title></rect>{(activity.length <= 14 || i % Math.ceil(activity.length / 10) === 0) && <text x={x(i)} y="190" textAnchor="middle">{a.date.slice(5).replace("-", "/")}</text>}</g>)}<polyline points={points} fill="none" stroke="#4f82ff" strokeWidth="2.5" strokeLinejoin="round"/>{activity.length <= 31 && activity.map((a, i) => <circle key={a.date} cx={x(i)} cy={y(a.study_seconds)} r={selected === i ? 5 : 3.2} stroke="#4f82ff" strokeWidth="2" fill="white"/>)}</svg><p className="lx-chart-caption">{selected === null ? activity.some(a => a.study_seconds || a.reviews) ? "每一次投入，都在这里留下成长的痕迹" : "还没有学习记录，完成第一次学习后点亮这条曲线" : `${activity[selected].date} · 学习 ${minutes(activity[selected].study_seconds)} · 复习 ${activity[selected].reviews} 次`}</p></div>;
}
function Distribution({ segments, total, caption = "知识点" }: {
    segments: {
        name: string;
        count: number;
    }[];
    total: number;
    caption?: string;
}) {
    let cursor = 0;
    const sum = segments.reduce((s, a) => s + a.count, 0);
    const stops = segments.filter(a => a.count > 0).map((a) => { const begin = cursor; cursor += a.count / Math.max(1, sum) * 100; return `${palette[segments.indexOf(a) % palette.length]} ${begin}% ${cursor}%`; });
    return <div className="lx-distribution"><div className={`lx-donut ${sum ? "" : "is-empty"}`} style={{ background: sum ? `conic-gradient(${stops.join(",")})` : undefined }} role="img" aria-label={`${caption}分布，共${total}个`}><div><strong>{num(total)}</strong><small>{caption}</small></div></div><div className="lx-distribution-legend">{segments.length ? segments.slice(0, 7).map((s, i) => <div key={s.name}><span><i style={{ background: palette[i % palette.length] }}/>{s.name}</span><strong>{num(s.count)}</strong></div>) : <p>你的知识版图<br /><small>从第一个学科开始</small></p>}</div></div>;
}
export default function LearningExperience(props: Props) {
    const { view, data } = props;
    const [insights, setInsights] = useState<WorkspaceInsights | null>(null);
    const [error, setError] = useState("");
    const [days, setDays] = useState(14);
    const requestGeneration = useRef(0);
    const reload = useCallback(async () => {
        const request = ++requestGeneration.current;
        try {
            const result = await webApi<WorkspaceInsights>(`/workspace/insights?days=${days}`);
            if (request === requestGeneration.current) {
                setInsights(result);
                setError("");
            }
        }
        catch (cause) {
            if (request === requestGeneration.current)
                setError(cause instanceof Error ? cause.message : "统计读取失败");
        }
    }, [days]);
    useEffect(() => { reload(); return () => { requestGeneration.current++; }; }, [data, reload]);
    return <div className="learning-experience">{error && <div className="lx-notice" role="alert">统计暂时不可用：{error}<button onClick={reload}>重试</button></div>}{view === "home" && <Dashboard {...props} insights={insights}/>}{["learning", "knowledge", "review", "history"].includes(view) && <Explorer key={view} {...props} insights={insights}/>}{view === "subjects" && <Subjects data={data} insights={insights} onSaved={reload} act={props.act}/>}{view === "calendar" && <Calendar data={data}/>}{view === "statistics" && <><PageIntro eyebrow="YOUR LEARNING, IN PERSPECTIVE" title="让成长，看得见" detail="从真实学习与复习记录中，发现你的节奏。" action={<select aria-label="统计时间范围" value={days} onChange={e => setDays(Number(e.target.value))}><option value={7}>最近 7 天</option><option value={14}>最近 14 天</option><option value={30}>最近 30 天</option><option value={90}>最近 90 天</option></select>}/>{insights ? <><MetricRow insights={insights}/><div className="lx-chart-grid"><Panel title={`学习趋势 · 近${days}天`}><Trend activity={insights.activity}/></Panel><Panel title="知识版图"><Distribution segments={insights.subjects.map(s => ({ name: s.name, count: s.knowledge_count }))} total={insights.metrics.knowledge_total}/></Panel></div><div className="lx-chart-grid"><Panel title="学习活动热力图"><div className="lx-heatmap">{insights.activity.map(a => <span key={a.date} style={{ opacity: a.reviews || a.study_seconds ? Math.min(1, .3 + (a.reviews + a.study_seconds / 600) / 15) : .09 }} title={`${a.date} · 学习${minutes(a.study_seconds)} · 复习${a.reviews}次`}/>)}</div><p className="lx-help">颜色越深，投入越多 · 学习时长与复习次数共同显示活跃程度</p></Panel><Panel title="复习足迹"><div className="lx-big-number">{num(insights.metrics.review_total)}<small>次累计复习</small></div><p className="lx-help">学习活跃 {insights.metrics.learning_days} 天，连续坚持 {insights.metrics.streak_days} 天。</p><More view="history">查看完整复习历史</More></Panel></div></> : <Skeleton />}</>}{view === "notion" && <Sources {...props}/>}{view === "mail" && <Notifications {...props}/>}{view === "assistant" && <Assistant {...props}/>}</div>;
}
function Skeleton() { return <div className="lx-skeleton" aria-label="正在加载统计"><span /><span /><span /></div>; }
function PageIntro({ eyebrow, title, detail, action }: {
    eyebrow: string;
    title: string;
    detail: string;
    action?: ReactNode;
}) { return <div className="lx-page-intro"><div><span>{eyebrow}</span><h2>{title}</h2><p>{detail}</p></div>{action}</div>; }
function MetricRow({ insights }: {
    insights: WorkspaceInsights;
}) {
    const m = insights.metrics;
    return <div className="lx-metrics"><Metric title="今日学习" value={(m.today_study_seconds / 3600).toFixed(1)} unit="小时" note="来自已保存的学习记录" icon={<BookOpen size={23}/>} color="purple"/><Metric title="今日复习" value={m.today_reviews} unit="次" note={`${m.pending_reviews} 个任务等你回顾`} icon={<RefreshCw size={23}/>}/><Metric title="知识点总数" value={num(m.knowledge_total)} unit="个" note={`${m.chapter_total} 个章节汇成知识版图`} icon={<Layers3 size={23}/>}/><Metric title="回忆成功率" value={m.recall_rate === null ? "—" : Math.round(m.recall_rate * 100)} unit={m.recall_rate === null ? "" : "%"} note="统计期内「记得 / 熟练」占比" icon={<Sparkles size={23}/>} color="pink"/><Metric title="连续学习" value={m.streak_days} unit="天" note={`累计活跃 ${m.learning_days} 天`} icon={<Flame size={23}/>} color="orange"/></div>;
}
function Dashboard(props: Props & {
    insights: WorkspaceInsights | null;
}) {
    const { data, tasks, points, insights, onChapter, onReview } = props;
    const m = insights?.metrics;
    const unfinished = tasks.filter(t => ["pending", "in_progress"].includes(t.status));
    const percent = m && m.today_tasks ? Math.round(m.today_completed_tasks / m.today_tasks * 100) : 0;
    const continueChapters = [...data.chapters].sort((a, b) => Number(b.status === "in_progress") - Number(a.status === "in_progress")).slice(0, 4);
    const steps = [{ label: "连接笔记", done: data.notion_configured && data.sources.length > 0, view: "settings" }, { label: "完成章节", done: !!m?.chapter_completed, view: "learning" }, { label: "开始复习", done: !!m?.review_total, view: "review" }];
    return <div className="lx-dashboard"><div className="lx-dashboard-center"><section className="lx-hero"><div><span>YOUR NEXT CHAPTER STARTS HERE</span><h2>持续学习 · 深度记忆 · 长期成长</h2><p>把每一次学习，变成可以积累的能力。</p><Link href={href(unfinished.length ? "review" : "learning")}>{unfinished.length ? "开始今日复习" : "开启今天的学习"}<ArrowRight size={15}/></Link></div><span className="lx-hero-chip"><Sparkles size={14}/>每天进步一点点</span></section>{insights ? <MetricRow insights={insights}/> : <Skeleton />}{!data.sources.length && !data.knowledge_total && <div className="lx-get-started"><span className="lx-get-started-icon"><Sparkles size={22}/></span><div><strong>为你的学习旅程，准备一张地图</strong><p>连接 Notion 后，知识、复习与成长会在这里逐渐展开。</p></div><Link href={href("settings")}>连接我的笔记<ArrowRight size={16}/></Link></div>}<div className="lx-chart-grid"><Panel title="学习趋势" action={<span className="lx-soft-label">最近 14 天</span>}>{insights ? <Trend activity={insights.activity}/> : <Skeleton />}</Panel><Panel title="学科分布" action={<More view="subjects"/>}>{insights ? <Distribution segments={insights.subjects.map(s => ({ name: s.name, count: s.knowledge_count }))} total={insights.metrics.knowledge_total}/> : <Skeleton />}</Panel></div><div className="lx-two-col"><Panel title="继续学习" action={<More view="learning"/>}>{continueChapters.length ? continueChapters.map((c, i) => <button className="lx-task-row" key={c.id} onClick={() => onChapter(c)}><span className={`lx-row-icon ${c.status === "completed" ? "green" : ""}`}>{c.status === "completed" ? <Check size={15}/> : <BookOpen size={15}/>}</span><span><strong>{c.title}</strong><small>{data.subjects.find(s => s.id === c.subject_id)?.name}</small></span><Badge value={c.status}/></button>) : <Empty title="从你的第一份笔记开始" detail="章节可以分多次学习，完成整章后再汇总知识。" action={<More view="settings">连接 Notion</More>}/>}</Panel><Panel title={`今日复习${m ? ` · ${m.pending_reviews} 个待办` : ""}`} action={<More view="review">开始复习</More>}>{unfinished.length ? unfinished.slice(0, 4).map(t => <button className="lx-task-row" key={t.id} onClick={() => onReview(t)}><span className="lx-row-icon purple"><RefreshCw size={15}/></span><span><strong>{t.knowledge_title || points.find(p => p.id === t.knowledge_point_id)?.title || "查看复习知识点"}</strong><small>{data.subjects.find(s => s.id === t.subject_id)?.name || "主动回忆 · 对照解析"}</small></span><ChevronRight size={16}/></button>) : <Empty icon="review" title="此刻，没有待复习的内容" detail="下一次复习会按你的记忆节奏到来。先学一点新知识吧。"/>}</Panel></div><div className="lx-two-col"><Panel title="记忆进程">{insights && <Distribution segments={insights.memory} total={insights.memory.reduce((s, a) => s + a.count, 0)} caption="已调度知识"/>}<p className="lx-help">按实际复习次数分类，持续回忆会让记忆更牢固。</p></Panel><Panel title="近期复习计划" action={<More view="calendar"/>}>{insights?.upcoming.length ? insights.upcoming.slice(0, 4).map(p => <Link className="lx-plan-row" key={p.date} href={`${href("calendar")}&date=${p.date}`}><span className="lx-date-tile">{p.date.slice(5)}</span><span>{p.count} 个知识点<small>{p.fsrs ? `FSRS ${p.fsrs}` : ""}{p.fsrs && p.ebbinghaus ? " · " : ""}{p.ebbinghaus ? `固定间隔 ${p.ebbinghaus}` : ""}</small></span><ChevronRight size={15}/></Link>) : <Empty icon="chart" title="为记忆留出下一站" detail="激活知识卡片后，接下来30天的到期计划会显示在这里。"/>}</Panel></div></div><aside className="lx-dashboard-rail"><Panel title="今日进度"><div className="lx-progress-content"><Ring value={percent} label={m ? `${percent}%` : "—"} caption="复习完成"/><div><p><i className="lx-dot"/>复习任务<strong>{m?.today_completed_tasks ?? "—"} / {m?.today_tasks ?? "—"}</strong></p><p><i className="lx-dot purple"/>复习次数<strong>{m?.today_reviews ?? "—"} 次</strong></p><p><i className="lx-dot grey"/>今日投入<strong>{m ? minutes(m.today_study_seconds + m.today_review_seconds) : "—"}</strong></p></div></div></Panel><Panel title="快捷操作"><div className="lx-quick-actions">{[{ name: "同步 Notion", view: "notion", icon: FileText }, { name: "新建知识点", view: "knowledge&create=1", icon: Plus }, { name: "添加学科", view: "subjects", icon: Network }, { name: "学习助手", view: "assistant", icon: Bot }].map(a => <Link href={href(a.view)} key={a.name}><span><a.icon size={22}/></span>{a.name}</Link>)}</div></Panel><Panel title="最近同步 · Notion" action={<More view="notion"/>}>{data.sync_history.length ? data.sync_history.slice(0, 3).map(s => <div className="lx-sync-item" key={s.id}><span className={`lx-sync-check ${s.status === "failed" ? "is-failed" : ""}`}>{s.status === "succeeded" ? <Check size={14}/> : <RefreshCw size={14}/>}</span><span><strong>{statusNames[s.status] || s.status}</strong><small>{dateText(s.created_at, data.user.timezone)}</small></span><small>{s.imported} 页</small></div>) : <div className="lx-rail-empty"><FileText size={27}/><p>笔记与学习，在这里相遇</p><small>连接资料库，开启自动同步</small><More view="settings">设置 Notion</More></div>}</Panel><section className="lx-assistant-card"><div className="lx-assistant-stars">✧</div><div className="lx-assistant-avatar"><Bot size={30}/></div><h2>你的学习搭子，随时在这里</h2><p>找回笔记里的线索，<br />把模糊的知识重新串联。</p><div className="lx-assistant-pills"><Link href={href("assistant")}>检索我的笔记</Link><Link href={href("review")}>练习主动回忆</Link></div><Link className="lx-assistant-cta" href={href("assistant")}>一起学一点<ArrowUpRight size={19}/></Link></section><Panel title="一步一步，构建你的学习系统"><div className="lx-journey">{steps.map((s, i) => <Link href={href(s.view)} key={s.label}><span className={s.done ? "is-done" : ""}>{s.done ? <Check size={14}/> : i + 1}</span><strong>{s.label}</strong><small>{s.done ? "已完成" : "去开启"}</small></Link>)}</div></Panel></aside></div>;
}
function Explorer(props: Props & {
    insights: WorkspaceInsights | null;
}) {
    const { view, data, onChapter, onPoint, onReview, act, pending } = props;
    const params = useSearchParams();
    const [query, setQuery] = useState(() => params.get("q") || "");
    const [subject, setSubject] = useState(() => params.get("subject") || "");
    const [status, setStatus] = useState(view === "review" ? "open" : "");
    const workload = useReviewWorkload(view === "review", data);
    const [rating, setRating] = useState("");
    const [from, setFrom] = useState("");
    const [to, setTo] = useState("");
    const [rows, setRows] = useState<(Knowledge | Chapter | ReviewTask | History)[]>([]);
    const [cursor, setCursor] = useState<string | null>(null);
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState("");
    const [compose, setCompose] = useState(() => params.get("create") === "1");
    const generation = useRef(0);
    const endpoint = view === "learning" ? "/chapters" : view === "knowledge" ? "/knowledge-points" : view === "review" ? "/review-tasks" : "/review-history";
    const filters = new URLSearchParams({ limit: "20" });
    if (subject)
        filters.set("subject_id", subject);
    if (status)
        filters.set("status", status);
    if (query)
        filters.set("q", query);
    if (rating)
        filters.set("rating", rating);
    // Explicit offset keeps history filtering consistent with the account's configured timezone.
    if (from)
        filters.set("from", localBoundary(from, data.user.timezone));
    if (to)
        filters.set("to", localBoundary(to, data.user.timezone, true));
    const filterKey = endpoint + "?" + filters;
    const fetchPage = useCallback(async (next: string | null = null) => {
        const request = ++generation.current;
        setBusy(true);
        setError("");
        try {
            const page = await webApi<Page<Knowledge | Chapter | ReviewTask | History>>(filterKey + (next ? "&cursor=" + encodeURIComponent(next) : ""));
            if (request !== generation.current)
                return;
            setRows(previous => next ? [...previous, ...page.items] : page.items);
            setCursor(page.next_cursor);
        }
        catch (cause) {
            if (request === generation.current)
                setError(cause instanceof Error ? cause.message : "读取失败");
        }
        finally {
            if (request === generation.current)
                setBusy(false);
        }
    }, [filterKey]);
    const contentSignature = JSON.stringify([data.knowledge_total, data.chapters.map(c => [c.id, c.version]), props.tasks.map(t => [t.id, t.status])]);
    useEffect(() => {
        setRows([]); setCursor(null); setBusy(true);
        const timer = setTimeout(() => fetchPage(), 200);
        return () => { clearTimeout(timer); generation.current++; };
    }, [contentSignature, fetchPage]);
    const copy: Record<string, [
        string,
        string,
        string
    ]> = { learning: ["A LITTLE LEARNING, EVERY DAY", "今天，继续探索", "不用一次学完整章。记录每一段投入，完成整章后再整理和复习。"], knowledge: ["YOUR PERSONAL KNOWLEDGE GARDEN", "让知识，生长成体系", "把笔记变成可回忆、可追溯、能反复生长的知识卡片。"], review: ["RECALL. CONNECT. REMEMBER.", "今天的回忆，明天的底气", "先尝试自己回答，再查看知识点与解析，为这次回忆诚实评分。"], history: ["EVERY REVIEW COUNTS", "每一次回忆，都有迹可循", "按学科、评分与时间筛选，回看你的复习记录与记忆变化。"] };
    const [eyebrow, title, detail] = copy[view];
    const reviewGroup = (row: ReviewTask) => data.subjects.findIndex(item => item.id === row.subject_id);
    const visibleRows = view === "review" && !subject
        ? [...rows].sort((a, b) => reviewGroup(a as ReviewTask) - reviewGroup(b as ReviewTask))
        : rows;
    return <><PageIntro eyebrow={eyebrow} title={title} detail={detail} action={view === "knowledge" ? <button className="portal-primary" onClick={() => setCompose(true)}><Plus size={16}/>新建知识点</button> : view === "review" ? <button className="portal-primary" disabled={pending || !workload.data} onClick={() => {
        const snapshot = workload.data;
        if (snapshot) void act(async () => {
            await webApi("/review-batches/generate", {
                method: "POST",
                body: {
                    daily_limit: snapshot.daily_limit,
                    timezone: snapshot.timezone,
                    local_date: snapshot.local_date,
                },
            });
            await fetchPage();
        });
    }}><RefreshCw size={16}/>更新任务</button> : <More view={view === "history" ? "statistics" : "notion"}>{view === "history" ? "查看学习统计" : "管理学习来源"}</More>}/>{view === "review" && <ReviewWorkloadPanel {...workload} />}{view === "learning" && <div className="lx-chapter-summary">{[["全部章节", props.insights?.metrics.chapter_total, BookOpen], ["已完成章节", props.insights?.metrics.chapter_completed, CheckCircle2], ["累计学习天数", props.insights?.metrics.learning_days, Flame]].map(([name, count, Icon]) => { const I = Icon as typeof BookOpen; return <div key={String(name)}><I size={21}/><span>{String(name)}</span><strong>{count === undefined ? "—" : String(count)}</strong></div>; })}</div>}<section className="lx-panel"><div className="lx-filterbar"><div className="lx-filter-search"><Search size={17}/><input aria-label={view === "knowledge" ? "搜索知识点" : "搜索标题"} placeholder="搜索标题，发现知识的线索…" maxLength={200} value={query} onChange={e => setQuery(e.target.value)}/></div><select aria-label="筛选学科" value={subject} onChange={e => setSubject(e.target.value)}><option value="">全部学科</option>{data.subjects.map(s => <option value={s.id} key={s.id}>{s.name}</option>)}</select>{view !== "history" ? <select aria-label="筛选状态" value={status} onChange={e => setStatus(e.target.value)}><option value="">全部状态</option>{(view === "learning" ? ["not_started", "in_progress", "completed"] : view === "review" ? ["open", "pending", "in_progress", "completed", "skipped"] : ["active", "draft", "archived"]).map(s => <option key={s} value={s}>{s === "open" ? "全部待办" : statusNames[s]}</option>)}</select> : <><select aria-label="复习评分" value={rating} onChange={e => setRating(e.target.value)}><option value="">全部评分</option>{["again", "hard", "good", "easy"].map(s => <option key={s} value={s}>{statusNames[s]}</option>)}</select><input aria-label="历史开始日期" type="date" value={from} onChange={e => setFrom(e.target.value)}/><span>至</span><input aria-label="历史结束日期" type="date" value={to} onChange={e => setTo(e.target.value)}/></>}</div><div className="lx-result-meta"><span>{view === "learning" ? "我的章节" : view === "knowledge" ? "我的知识库" : view === "review" ? "复习任务" : "完整复习历史"}</span><small>{busy ? "正在读取…" : `已载入 ${rows.length} 项${cursor ? " · 还有更多" : ""}`}</small></div>{error && <p className="portal-error" role="alert">{error}<button onClick={() => fetchPage()}>重试</button></p>}<div className={view === "knowledge" || view === "learning" ? "lx-content-grid" : "lx-results"}>{visibleRows.map((row, index) => {
            const subjectInfo = data.subjects.find(s => s.id === (row as Knowledge).subject_id);
            const color = palette[Math.max(0, data.subjects.findIndex(s => s.id === subjectInfo?.id)) % palette.length];
            if (view === "learning") {
                const c = row as Chapter;
                return <button key={c.id} className="lx-chapter-card" onClick={() => onChapter(c)} style={{ "--subject-color": color } as CSSProperties}><div><span className="lx-colored-icon"><BookOpen size={21}/></span><Badge value={c.status}/></div><h3>{c.title}</h3><p>{c.content?.slice(0, 100) || "记录新的发现，逐步完成这一章的学习。"}</p><footer><span className="lx-subject-tag">{subjectInfo?.name || "学习章节"}</span><span>继续学习<ArrowRight size={14}/></span></footer></button>;
            }
            if (view === "knowledge") {
                const p = row as Knowledge;
                return <button key={p.id} className="lx-knowledge-card" onClick={() => onPoint(p)} style={{ "--subject-color": color } as CSSProperties}><span className="lx-subject-tag">{subjectInfo?.name || "知识卡片"}</span><Layers3 className="lx-card-watermark" size={60}/><h3>{p.title}</h3><p>{p.summary || p.body.slice(0, 130)}</p><footer><small>{p.manual_revision ? "人工修订" : "知识卡片"} · {statusNames[p.status || "active"]}</small><span>查看解析<ArrowUpRight size={15}/></span></footer></button>;
            }
            if (view === "review") {
                const t = row as ReviewTask;
                return <Fragment key={t.id}>{!subject && (index === 0 || reviewGroup(visibleRows[index - 1] as ReviewTask) !== reviewGroup(t)) && <h3 className="lx-soft-label">{subjectInfo?.name || "其他学科"}</h3>}<button className="lx-review-row" disabled={pending} onClick={() => onReview(t)}><span className="lx-review-index">{String(index + 1).padStart(2, "0")}</span><span className="lx-row-icon"><RefreshCw size={20}/></span><span className="lx-row-main"><strong>{t.knowledge_title || "查看知识点"}</strong><small>{subjectInfo?.name || "复习卡片"}{t.scheduled_due_at ? ` · ${dateText(t.scheduled_due_at, data.user.timezone)} 到期` : ""}</small></span><Badge value={t.status}/><span className="lx-review-action">{t.status === "completed" ? "再次阅读" : "开始回忆"}<ArrowRight size={16}/></span></button></Fragment>;
            }
            const h = row as History;
            return <button key={h.id} className="lx-review-row" disabled={pending} onClick={() => onReview({ id: h.task_id, knowledge_point_id: "", status: "completed", version: 1 })}><span className="lx-row-icon green"><CheckCircle2 size={20}/></span><span className="lx-row-main"><strong>{h.knowledge_title || "复习记录"}</strong><small>{subjectInfo?.name} · {dateText(h.reviewed_at, data.user.timezone)} · {h.strategy === "fsrs" ? "FSRS" : "艾宾浩斯"} · {h.duration_seconds} 秒</small></span><Badge value={h.rating}/><ChevronRight size={16}/></button>;
        })}</div>{!busy && !rows.length && !error && <Empty icon={view === "review" ? "review" : "book"} title={query || subject || from || to || rating ? "暂时没有匹配的内容" : view === "review" ? "当前没有待复习内容" : "在这里，积累你的第一个发现"} detail={query || subject ? "试着调整筛选条件，或搜索另一个标题。" : "连接笔记、记录学习，你的内容将逐渐填满这里。"} action={<More view="settings">管理我的连接</More>}/>}{busy && <div className="lx-loading"><LoaderCircle size={18} className="portal-spin"/>正在载入你的内容</div>}{cursor && <button className="lx-load-more" disabled={busy} onClick={() => fetchPage(cursor)}>加载更多<ChevronRight size={16}/></button>}</section>{compose && <KnowledgeComposer data={data} onClose={() => setCompose(false)} onSaved={async () => { setCompose(false); await fetchPage(); await act(async () => { }); }}/>}</>;
}
// Convert account-local calendar boundaries without assuming the browser has the same timezone.
function localBoundary(value: string, zone: string, end = false) {
    const [year, month, day] = value.split("-").map(Number);
    const target = Date.UTC(year, month - 1, day + (end ? 1 : 0));
    let utc = target;
    for (let i = 0; i < 3; i++) {
        const parts = new Intl.DateTimeFormat("en-GB", { timeZone: zone, year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit", hourCycle: "h23" }).formatToParts(new Date(utc));
        const p = Object.fromEntries(parts.map(p => [p.type, p.value]));
        utc += target - Date.UTC(+p.year, +p.month - 1, +p.day, +p.hour, +p.minute, +p.second);
    }
    return new Date(utc - (end ? 1 : 0)).toISOString();
}
function Subjects({ data, insights, onSaved, act }: {
    data: WorkspaceData;
    insights: WorkspaceInsights | null;
    onSaved: () => Promise<void>;
    act: Props["act"];
}) {
    const [adding, setAdding] = useState(false);
    const [name, setName] = useState("");
    const [description, setDescription] = useState("");
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState("");
    const requestKey = useRef<{
        payload: string;
        key: string;
        slug: string;
    } | null>(null);
    async function submit(event: FormEvent) {
        event.preventDefault();
        if (busy)
            return;
        setBusy(true);
        setError("");
        try {
            const payload = JSON.stringify([name.trim(), description]);
            if (requestKey.current?.payload !== payload)
                requestKey.current = { payload, key: crypto.randomUUID(), slug: `subject-${crypto.randomUUID().slice(0, 12)}` };
            await webApi("/subjects", { method: "POST", key: requestKey.current.key, body: { name: name.trim(), slug: requestKey.current.slug, description } });
            setAdding(false);
            setName("");
            setDescription("");
            requestKey.current = null;
            await act(async () => { });
            await onSaved();
        }
        catch (cause) {
            setError(cause instanceof Error ? cause.message : "创建失败");
        }
        finally {
            setBusy(false);
        }
    }
    return <><PageIntro eyebrow="MAKE ROOM FOR YOUR CURIOSITY" title="每一种好奇，都值得一个位置" detail="语言、技术、数学，或是你正在探索的任何领域。" action={<button className="portal-primary" onClick={() => setAdding(!adding)}><Plus size={17}/>添加学科</button>}/>{adding && <Panel title="开启一门新学科"><form className="lx-subject-form" onSubmit={submit}><label>学科名称<input required maxLength={120} value={name} onChange={e => setName(e.target.value)} placeholder="例如：日语、天文学、操作系统"/></label><label>学习方向<input value={description} onChange={e => setDescription(e.target.value)} placeholder="你希望在这个领域探索什么？"/></label><button className="portal-primary" disabled={busy}>创建学科</button><button type="button" className="portal-secondary" onClick={() => setAdding(false)}>取消</button></form>{error && <p role="alert" className="portal-error">{error}</p>}</Panel>}<div className="lx-subject-grid">{data.subjects.map((s, i) => { const stats = insights?.subjects.find(a => a.id === s.id); const progress = stats?.chapter_count ? Math.round(stats.completed_chapters / stats.chapter_count * 100) : 0; return <article className="lx-subject-card" key={s.id} style={{ "--subject-color": palette[i % palette.length] } as CSSProperties}><span className="lx-colored-icon"><Network size={26}/></span><h3>{s.name}</h3><p>构建属于你的知识体系</p><div className="lx-subject-counts"><span><strong>{stats?.knowledge_count ?? s.count}</strong>知识点</span><span><strong>{stats?.chapter_count ?? "—"}</strong>学习章节</span></div><div className="lx-subject-progress"><span>章节完成度</span><strong>{progress}%</strong><div><i style={{ width: `${progress}%` }}/></div></div><footer><Link href={`${href("learning")}&subject=${s.id}`}>查看章节<ArrowRight size={15}/></Link><Link href={`${href("knowledge")}&subject=${s.id}`}>知识库<Layers3 size={15}/></Link></footer></article>; })}<button className="lx-subject-add" onClick={() => setAdding(true)}><span><Plus size={29}/></span><strong>探索新的领域</strong><small>不限制学科，也不限制好奇心</small></button></div></>;
}
function Calendar({ data }: {
    data: WorkspaceData;
}) {
    const initial = useSearchParams().get("date");
    const localToday = new Intl.DateTimeFormat("en-CA", { timeZone: data.user.timezone, year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date());
    const [year, month] = (initial || localToday).split("-").map(Number);
    const [date, setDate] = useState({ year, month: month - 1 });
    const [selected, setSelected] = useState(initial || localToday);
    const [insights, setInsights] = useState<WorkspaceInsights | null>(null);
    const [error, setError] = useState("");
    useEffect(() => {
        let active = true;
        setInsights(null);
        setError("");
        webApi<WorkspaceInsights>(`/workspace/insights?from_date=${dayKey(date.year, date.month, 1)}&to_date=${dayKey(date.year, date.month, new Date(date.year, date.month + 1, 0).getDate())}`).then(d => {
            if (active)
                setInsights(d);
        }).catch(c => active && setError(c.message));
        return () => { active = false; };
    }, [date]);
    const offset = (new Date(date.year, date.month, 1).getDay() + 6) % 7;
    const count = new Date(date.year, date.month + 1, 0).getDate();
    const plan = insights?.scheduled.find(d => d.date === selected);
    const activity = insights?.activity.find(d => d.date === selected);
    const shift = (n: number) => { const next = new Date(date.year, date.month + n, 1); setDate({ year: next.getFullYear(), month: next.getMonth() }); setSelected(dayKey(next.getFullYear(), next.getMonth(), 1)); };
    return <><PageIntro eyebrow="A RHYTHM YOUR MEMORY CAN FOLLOW" title="把复习，安排在刚刚好的时候" detail="日历展示当前到期计划和实际复习记录，评分后未来日期会随记忆策略更新。"/><div className="lx-calendar-layout"><Panel title={`${date.year} 年 ${date.month + 1} 月`} action={<div className="lx-calendar-controls"><button aria-label="上个月" onClick={() => shift(-1)}><ChevronLeft size={18}/></button><button onClick={() => { const [y, m] = localToday.split("-").map(Number); setDate({ year: y, month: m - 1 }); setSelected(localToday); }}>今天</button><button aria-label="下个月" onClick={() => shift(1)}><ChevronRight size={18}/></button></div>}><div className="lx-calendar-week">{"一二三四五六日".split("").map(day => <span key={day}>周{day}</span>)}</div><div className="lx-calendar-grid">{Array.from({ length: offset }, (_, i) => <span key={`blank-${i}`}/>)}{Array.from({ length: count }, (_, i) => { const key = dayKey(date.year, date.month, i + 1); const planned = insights?.scheduled.find(d => d.date === key); const done = insights?.activity.find(d => d.date === key); return <button key={key} aria-label={key} aria-pressed={selected === key} className={(key === selected ? "selected " : "") + (key === localToday ? "today" : "")} onClick={() => setSelected(key)}><strong>{i + 1}</strong>{planned && <span>{planned.count} 个到期</span>}{!!done?.reviews && <small>已复习 {done.reviews}</small>}</button>; })}</div><p className="lx-help"><i className="lx-dot"/> 当前计划 · <i className="lx-dot green"/> 已完成记录 · 时间按 {data.user.timezone}</p>{error && <p role="alert" className="portal-error">{error}</p>}</Panel><div className="lx-calendar-side"><Panel title={`${selected.slice(5).replace("-", "月")}日 · 学习安排`}><div className="lx-calendar-illustration"><CalendarDays size={48}/><Sparkles size={22}/></div><div className="lx-big-number">{plan?.count ?? 0}<small>个知识点到期</small></div><p className="lx-help">{plan?.fsrs ? `FSRS：${plan.fsrs} 个` : ""}{plan?.ebbinghaus ? ` · 固定间隔：${plan.ebbinghaus} 个` : ""}</p><div className="lx-calendar-fact"><span>实际复习</span><strong>{activity?.reviews ?? 0} 次</strong></div><div className="lx-calendar-fact"><span>学习投入</span><strong>{minutes(activity?.study_seconds ?? 0)}</strong></div><Link className="portal-primary lx-full-button" href={href("review")}>进入复习<ArrowRight size={15}/></Link></Panel><div className="lx-tip"><Sparkles size={19}/><p>不要担心偶尔错过。到期的复习会保留，重新开始就很好。</p></div></div></div></>;
}
function Sources({ data, act, pending, onPoint }: Props) {
    const [progress, setProgress] = useState<ProcessingProgress | null>(null);
    const [error, setError] = useState("");
    useEffect(() => {
        let current = true;
        webApi<ProcessingProgress>("/workspace/processing")
            .then(value => {
                if (current) { setProgress(value); setError(""); }
            })
            .catch(cause => current && setError(cause.message));
        return () => { current = false; };
    }, [data]);
    const zone = data.user.timezone;
    const syncLabels: Record<string, string> = {
        pending: "已排队", running: "同步中", succeeded: "已完成", failed: "失败",
        partial: "部分完成", cancelled: "已取消",
    };
    return <>
        <PageIntro eyebrow="ONE HOME FOR ALL YOUR NOTES" title="知识自动整理"
            detail="跟进 Notion 原文、同步与 AI 提取，再查看生成的知识和卡片。"
            action={<Link className="portal-primary" href={href("settings")}><Settings2 size={16}/>资料库设置</Link>}/>
        {error && <p role="alert" className="portal-error">{error}</p>}
        {progress?.automatic_processing_enabled === false && <div className="lx-notice">
            自动后台已暂停。同步、重新分析和失败重试会先保存为排队任务。
        </div>}
        <Panel title="我的 Notion 资料库">
            {data.sources.length ? data.sources.map(source => <div className="lx-task-row" key={source.id}>
                <span className="lx-row-icon"><FileText size={19}/></span>
                <span><strong>{source.name}</strong><small>{source.last_sync_at ? `增量水位 ${dateText(source.last_sync_at, zone)}` : "等待首次同步"}</small></span>
                <button className="portal-secondary" disabled={pending} onClick={() => act(async () => {
                    await webApi(`/notion/data-sources/${source.id}/sync`, { method: "POST" });
                })}><RefreshCw size={15}/>排队同步</button>
            </div>) : <Empty title="连接你的 Notion 资料库" detail="选择已授权的资料库和学科，原笔记会通过同步保存在这里。"
                action={<More view="settings">连接 Notion</More>}/>}
        </Panel>
        <Panel title="章节与 AI 分析">
            {progress?.notes.map(note => {
                const archived = Boolean(note.notion_archived_at);
                const label = archived ? "Notion 已归档或移至垃圾箱"
                    : note.status === "blocked" && note.error_code === "CONFIG_MISSING" ? "等待 AI 配置或授权"
                    : note.status ? syncLabels[note.status] || statusNames[note.status] || note.status
                    : note.learning_status === "completed" ? "等待创建分析任务" : "等待完成章节";
                return <details className="portal-recall" key={note.chapter_id}>
                    <summary><strong>{note.title}</strong> · {label}</summary>
                    {note.source_url && /^https?:\/\//i.test(note.source_url) && <p><a className="portal-inline-link" href={note.source_url} target="_blank" rel="noreferrer">查看 Notion 原文</a></p>}
                    {note.note_summary && <p className="portal-prose">{note.note_summary}</p>}
                    {note.information_sufficient === false && <p>原笔记的信息不足，分析仅展示有依据的内容。</p>}
                    {note.limitations.map((item, index) => <p key={index}>{item}</p>)}
                    {note.evidence.map((evidence, index) => <details key={evidence.knowledge_point_id}>
                        <summary>知识点 {index + 1} 的原文与分析</summary>
                        <blockquote className="portal-prose">{evidence.source_quote}</blockquote>
                        <p className="lx-help">原始 Markdown 字符位置 {evidence.source_start + 1}–{evidence.source_end}</p>
                        <dl>{[
                            ["概念", evidence.concepts], ["术语", evidence.terms], ["知识关系", evidence.relationships],
                            ["前置知识", evidence.prerequisites], ["易错点", evidence.pitfalls],
                            ["重难点", evidence.key_points], ["应用场景", evidence.applications],
                            ["复习建议", [evidence.review_suggestion].filter(Boolean)],
                        ].filter(([, values]) => values.length > 0).map(([label, values]) => <div key={String(label)}>
                            <dt>{label}</dt><dd>{(values as string[]).join(" · ")}</dd>
                        </div>)}</dl>
                    </details>)}
                    {note.next_attempt_at && <p className="lx-help">预计重试 {dateText(note.next_attempt_at, zone)}</p>}
                    {note.error_code && note.error_code !== "CONFIG_MISSING" && <p className="lx-help">处理状态码 {note.error_code}</p>}
                    <div className="portal-inline">
                        {note.knowledge_point_ids.map((id, index) => <button key={id} className="portal-secondary" disabled={pending}
                            onClick={() => act(async () => onPoint(await webApi<Knowledge>(`/knowledge-points/${id}`)))}>
                            查看知识与卡片 {index + 1}
                        </button>)}
                        {!archived && note.learning_status === "completed" && !["pending", "running", "blocked"].includes(note.status || "") &&
                            <button className="portal-secondary" disabled={pending} onClick={() => act(async () => {
                                await webApi(`/chapters/${note.chapter_id}/reanalyze`, { method: "POST" });
                            })}>排队重新分析</button>}
                    </div>
                </details>;
            })}
            {!progress && !error && <p role="status">正在读取排队与分析状态…</p>}
            {progress?.notes.length === 0 && <p className="lx-help">首次同步之后，Notion 章节会显示在这里。</p>}
        </Panel>
        <Panel title="同步历史">
            {progress?.sync_runs.length ? <div className="lx-table-wrap"><table className="lx-table">
                <thead><tr><th>资料库</th><th>同步状态</th><th>导入版本</th><th>处理说明</th></tr></thead>
                <tbody>{progress.sync_runs.map(run => <tr key={run.id}>
                    <td>{data.sources.find(source => source.id === run.source_id)?.name || "Notion"}</td>
                    <td>{syncLabels[run.status] || run.status}</td><td>{run.imported}</td>
                    <td>{run.finished_at ? dateText(run.finished_at, zone) : "等待处理"}
                        {run.error_code && <small> · {run.error_code} · {run.attempt} 次尝试</small>}
                        {run.next_retry_at && <small> · 预计重试 {dateText(run.next_retry_at, zone)}</small>}
                        {run.status === "failed" && <button className="portal-secondary" disabled={pending} onClick={() => act(async () => {
                            await webApi(`/notion/sync-runs/${run.id}/retry`, { method: "POST" });
                        })}>排队重试</button>}
                    </td>
                </tr>)}</tbody>
            </table></div> : <p className="lx-help">尚无同步记录。</p>}
        </Panel>
    </>;
}
function Notifications({ data }: Props) { return <><PageIntro eyebrow="A GENTLE REMINDER TO GROW" title="让知识，准时来到你身边" detail="推送带上知识正文、主动回忆问题、答案解析、原始笔记和复习入口。" action={<Link className="portal-primary" href={href("settings")}><Settings2 size={16}/>通知设置</Link>}/><div className="lx-notification-grid"><Panel title="我的邮件陪伴"><div className="lx-mail-hero"><span><Mail size={29}/></span><div><h3>{data.profile.email_enabled ? "每日复习提醒已开启" : "让复习成为一个温柔的习惯"}</h3><p>{data.profile.email_enabled ? `每天 ${data.profile.reminder_time} · ${data.user.timezone}` : "开启邮件提醒，把当天需要回顾的知识送到邮箱。"}</p></div><Badge value={data.profile.email_enabled ? "active" : "not_started"}/></div><div className="lx-mail-details"><span>接收邮箱<strong>{data.profile.recipient_email || "待设置"}</strong></span><span>发件配置<strong>{data.smtp_configured ? "已保存授权配置" : "尚未配置"}</strong></span></div><More view="settings">修改邮箱与提醒时间</More></Panel><Panel title="一封完整的知识提醒"><div className="lx-template-preview"><span className="lx-template-line"/><h3>知识点标题 · 第 N 次复习</h3><p>学科与当前记忆阶段</p><div>主动回忆问题 → 知识正文 → 答案与解析</div><footer><span>Notion 原始笔记 ↗</span><span>进入复习 →</span></footer></div><p className="lx-help">内容结构示意，实际邮件来自你的知识库。</p></Panel></div><Panel title="通知渠道"><div className="lx-channel-grid">{data.channels.map(c => <Link href={href("settings")} key={c.id}><span><Mail size={23}/></span><strong>{c.name}</strong><small>{c.available ? "当前支持" : "后续接入"}</small></Link>)}</div></Panel><Panel title="邮件通知记录">{data.mail_history.length ? <div className="lx-table-wrap"><table className="lx-table"><thead><tr><th>消息内容</th><th>创建时间</th><th>状态</th><th>尝试次数</th></tr></thead><tbody>{data.mail_history.map(j => <tr key={j.id}><td><strong>{j.title}</strong>{j.error_code && <small>{j.error_code}</small>}</td><td>{dateText(j.created_at, data.user.timezone)}</td><td><Badge value={j.status}/></td><td>{j.attempts}</td></tr>)}</tbody></table></div> : <Empty title="等待送出的第一份知识" detail="配置邮箱后，可以在设置中发送测试邮件。真实发送结果会记录在这里。"/>}</Panel></>; }
function Assistant({ data, onPoint }: Props) {
    const [query, setQuery] = useState("");
    const [result, setResult] = useState<Knowledge[]>([]);
    const [searched, setSearched] = useState(false);
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState("");
    const generation = useRef(0);
    async function search(event: FormEvent) {
        event.preventDefault();
        const request = ++generation.current;
        setBusy(true);
        setError("");
        try {
            const page = await webApi<Page<Knowledge>>(`/knowledge-points?limit=20&q=${encodeURIComponent(query.trim())}`);
            if (request === generation.current) {
                setResult(page.items);
                setSearched(true);
            }
        }
        catch (cause) {
            if (request === generation.current)
                setError(cause instanceof Error ? cause.message : "检索失败");
        }
        finally {
            if (request === generation.current)
                setBusy(false);
        }
    }
    return <><div className="lx-assistant-welcome"><span className="lx-assistant-avatar"><Bot size={37}/></span><span className="lx-eyebrow">A LITTLE HELP FOR YOUR NEXT DISCOVERY</span><h2>今天，想弄懂什么？</h2><p>先从你自己的知识库找起，回到原文，把知识重新连起来。</p><form onSubmit={search} className="lx-assistant-search"><Search size={21}/><input aria-label="检索我的知识" value={query} onChange={e => setQuery(e.target.value)} maxLength={200} placeholder="输入一个知识点，寻找笔记里的线索…" required/><button className="portal-primary" disabled={busy}>{busy ? <LoaderCircle className="portal-spin" size={18}/> : <ArrowRight size={20}/>}<span>检索笔记</span></button></form><div className="lx-assistant-suggestions"><Link href={href("review")}><RefreshCw size={16}/>练习一次主动回忆</Link><Link href={href("knowledge")}><Layers3 size={16}/>浏览知识卡片</Link><Link href={href("statistics")}><TrendingUp size={16}/>看看学习轨迹</Link></div></div>{error && <p role="alert" className="portal-error">{error}</p>}{searched && <Panel title={`在我的知识库中找到 ${result.length} 条线索`}>{result.map(p => <button className="lx-task-row" key={p.id} onClick={() => onPoint(p)}><FileText size={19}/><span><strong>{p.title}</strong><small>{p.summary || p.body.slice(0, 110)}</small></span><ArrowUpRight size={17}/></button>)}{!result.length && <Empty title="这里暂时没有这条线索" detail="换一个标题关键词，或者先同步相关笔记。"/>}</Panel>}<div className="lx-two-col"><Panel title="你的模型配置"><div className="lx-model-status"><span className="lx-colored-icon"><Sparkles size={25}/></span><div><strong>{data.model ? `${data.model.provider} · ${data.model.model_name}` : "为笔记连接一个理解伙伴"}</strong><p>{data.model_key_configured ? "已保存模型凭据，章节完成后可用于知识整理。" : "支持 DeepSeek、Kimi、OpenAI 及兼容接口。"}</p></div></div><More view="settings">管理模型设置</More></Panel><Panel title="从理解，到真正记住"><div className="lx-assistant-flow"><span>检索原文</span><ArrowRight size={16}/><span>尝试回忆</span><ArrowRight size={16}/><span>对照解析</span></div><p className="lx-help">当前提供真实笔记检索与复习引导，开放式 AI 对话和自动评价仍待接入。</p></Panel></div></>;
}
function KnowledgeComposer({ data, onClose, onSaved }: {
    data: WorkspaceData;
    onClose: () => void;
    onSaved: () => Promise<void>;
}) {
    const dialog = useRef<HTMLDialogElement>(null);
    const [title, setTitle] = useState("");
    const [body, setBody] = useState("");
    const [summary, setSummary] = useState("");
    const [difficulty, setDifficulty] = useState("2");
    const [subject, setSubject] = useState(data.subjects[0]?.id || "");
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState("");
    const key = useRef<{
        body: string;
        key: string;
    } | null>(null);
    useEffect(() => { dialog.current?.showModal(); }, []);
    async function submit(e: FormEvent) {
        e.preventDefault();
        if (busy)
            return;
        setBusy(true);
        setError("");
        try {
            const payload = { title: title.trim(), body: body.trim(), summary: summary.trim(), difficulty: Number(difficulty), subject_id: subject, status: "draft" };
            const serialized = JSON.stringify(payload);
            if (key.current?.body !== serialized)
                key.current = { body: serialized, key: crypto.randomUUID() };
            await webApi("/knowledge-points", { method: "POST", key: key.current.key, body: payload });
            await onSaved();
        }
        catch (cause) {
            setError(cause instanceof Error ? cause.message : "保存失败");
        }
        finally {
            setBusy(false);
        }
    }
    return <dialog ref={dialog} className="portal portal-dialog lx-compose" onCancel={event => {
            if (busy)
                event.preventDefault();
            else
                onClose();
        }}><button className="portal-dialog-close" aria-label="关闭新建知识点" onClick={onClose} disabled={busy}><X size={19}/></button><span className="portal-eyebrow">CAPTURE A NEW IDEA</span><h2>留下一个新的发现</h2>{data.subjects.length ? <form onSubmit={submit}><label>知识点标题<input required maxLength={300} value={title} onChange={e => setTitle(e.target.value)} placeholder="用一句话，概括这个知识点"/></label><label>所属学科<select required value={subject} onChange={e => setSubject(e.target.value)}>{data.subjects.map(s => <option value={s.id} key={s.id}>{s.name}</option>)}</select></label><label>知识摘要<input maxLength={10000} value={summary} onChange={e => setSummary(e.target.value)} placeholder="用一句话留下核心线索（可选）"/></label><label>学习难度<select value={difficulty} onChange={e => setDifficulty(e.target.value)}>{[1, 2, 3, 4, 5].map(value => <option value={value} key={value}>{value} · {value === 1 ? "入门" : value === 5 ? "挑战" : "循序渐进"}</option>)}</select></label><label>知识正文<textarea required maxLength={200000} rows={7} value={body} onChange={e => setBody(e.target.value)} placeholder="写下原理、例子，以及你自己的理解…"/></label><p className="lx-help">保存为草稿。章节生成的卡片与调度继续使用现有记忆策略。</p>{error && <p className="portal-error" role="alert">{error}</p>}<button className="portal-primary" disabled={busy}>保存知识点</button></form> : <Empty title="先给这个发现一个归属" detail="创建一个学科，再把新的知识收藏进来。" action={<Link className="portal-primary" href={href("subjects")} onClick={onClose}>添加学科</Link>}/>}</dialog>;
}
