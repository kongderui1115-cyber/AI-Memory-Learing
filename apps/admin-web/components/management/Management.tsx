"use client";

import {
  Activity, ArrowDownUp, ArrowRight, Bell, BrainCircuit, Check, ChevronRight,
  Clock3, Cloud, Cpu, Database, History, KeyRound, Layers3, Mail, Pencil, Play,
  Plus, Radio, RefreshCw, Server, Settings2, ShieldCheck, Terminal, Trash2, X,
} from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useId, useRef, useState } from "react";
import type { FormEvent, ReactNode } from "react";
import { RingChart, TrendChart } from "@/components/dashboard/Chart";
import type { AdminClient, AdminUser, AuditEvent, JobAnalytics, LearnerKnowledge, LearnerOverview, LearnerReview, ManagementRecord, ManagementSection, SystemHealth } from "@/lib/client";
import { deliveryExamples, memoryExample, modelCalls, resources, taskRuns } from "./data";
import type { RecordStatus } from "./data";
import styles from "./management.module.css";
import { Badge, Panel, Message, formatTime, Table, Dialog, Field, FormFooter } from "./ui";
import type { Feedback } from "./ui";
import LiveOperations, { LiveBackups } from "./LiveOperations";

type Mode = "live" | "demo";
type EditableSection = "models" | "sources" | "notifications" | "memory";
type RecordInput = Omit<ManagementRecord, "id" | "updatedAt">;

const sections = {
  models: { title: "AI 模型管理", description: "配置模型供应商、默认模型及任务分配，跟踪运行消耗。", icon: BrainCircuit },
  sources: { title: "数据源管理", description: "管理知识来源、同步频率及导入结果。", icon: Database },
  notifications: { title: "通知管理", description: "管理复习提醒的投递渠道、历史和消息模板。", icon: Bell },
  memory: { title: "记忆策略管理", description: "比较 FSRS 与固定间隔复习，为不同学科配置策略。", icon: BrainCircuit },
  jobs: { title: "任务调度中心", description: "跟踪同步、提取、复习和投递任务的执行情况。", icon: Layers3 },
  monitoring: { title: "系统监控", description: "查看 API、数据库与后台服务的可用情况。", icon: Activity },
  settings: { title: "系统设置", description: "管理账户安全，查阅日志、系统版本和备份入口。", icon: Settings2 },
} satisfies Record<ManagementSection, { title: string; description: string; icon: typeof Bell }>;

const statusLabels: Record<RecordStatus, string> = {
  ok: "正常", paused: "已停用", failed: "失败", queued: "已排队", planned: "待接入", running: "运行中",
};
const modelUses = ["未分配", "知识提取", "复习题生成", "答案评价", "学习问答", "学习报告"];
const memoryDefaults = { retention: "90", interval: "1,3,7,14,30", maxInterval: "365", difficulty: "5" };
const channels = ["Bark", "QQ 邮箱", "企业微信", "钉钉", "Telegram", "其他通知渠道"];

function Status({ status }: { status: RecordStatus }) {
  return <Badge tone={status}>{statusLabels[status]}</Badge>;
}

function Stat({ title, value, detail, tone = "blue", icon: Icon }: {
  title: string; value: string; detail?: string; tone?: string; icon: typeof Bell;
}) {
  return <div className={styles.stat} data-color={tone}>
    <span className={styles.statIcon}><Icon size={18} aria-hidden="true" /></span>
    <div><span className={styles.statLabel}>{title}</span><strong>{value}</strong>{detail && <small>{detail}</small>}</div>
  </div>;
}

function Entry({ record }: { record: ManagementRecord }) {
  return <div className={styles.entry}><span>{record.name}</span><small>{record.detail}</small></div>;
}

function Bars({ entries, label }: { entries: { name: string; value: number; color: string }[]; label: string }) {
  return <div className={styles.bars} aria-label={label}>{entries.map(item =>
    <div className={styles.barItem} key={item.name}><div><span>{item.name}</span><strong>{item.value}%</strong></div>
      <div className={styles.barTrack}><div style={{ width: item.value + "%", background: item.color }} /></div>
    </div>,
  )}</div>;
}

function RecordForm({ section, record, mode, busy, onClose, onSave }: {
  section: EditableSection; record: ManagementRecord | null; mode: Mode; busy: boolean;
  onClose: () => void; onSave: (input: RecordInput) => Promise<boolean>;
}) {
  const [error, setError] = useState("");
  const meta = record?.meta ?? {};
  const isModel = section === "models";
  const isSource = section === "sources";
  const isNotification = section === "notifications";
  const isMemory = section === "memory";
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    const form = new FormData(event.currentTarget);
    const value = (name: string) => String(form.get(name) ?? "").trim();
    const name = isModel ? value("name") : record?.name;
    const detail = value("detail");
    if (!name || !detail) { setError("请填写名称和配置内容。"); return; }
    let nextMeta = { ...meta };
    let status = form.has("enabled") ? "ok" as const : "paused" as const;
    if (isModel) {
      const endpoint = parseUrl(value("baseUrl"));
      if (!endpoint || !["http:", "https:"].includes(endpoint.protocol) || endpoint.username || endpoint.password || endpoint.search || endpoint.hash) {
        setError("请输入 HTTP 或 HTTPS API 地址。请移除登录凭据、查询参数及片段。");
        return;
      }
      nextMeta = {
        ...meta, provider: value("provider"), baseUrl: endpoint.toString(), assigned: value("assigned"),
        default: String(form.has("default") && status === "ok"),
        credential: String(Boolean(value("secret")) || meta.credential === "true"),
      };
    }
    if (isSource) {
      nextMeta = {
        ...meta, frequency: value("frequency"), automatic: String(form.has("automatic")),
        credential: String(Boolean(value("secret")) || meta.credential === "true"),
      };
    }
    if (isNotification) {
      nextMeta = { ...meta, credential: String(Boolean(value("secret")) || meta.credential === "true") };
    }
    if (isMemory) {
      const intervals = value("interval").split(/[,，]/).map(item => Number(item.trim()));
      const maximum = Number(value("maxInterval"));
      if (intervals.some((interval, index) => !Number.isInteger(interval) || interval <= 0 || interval > maximum || (index > 0 && interval <= intervals[index - 1]))) {
        setError("间隔必须为严格递增的正整数天数，且不超过最大间隔。");
        return;
      }
      status = "ok";
      nextMeta = { ...meta, interval: intervals.join(","), retention: value("retention"), maxInterval: value("maxInterval"), difficulty: value("difficulty") };
    }
    if (await onSave({ name, detail, status, meta: nextMeta })) onClose();
    else setError("配置未保存，请检查服务状态后重试。");
  }
  return <Dialog title={(record ? "配置" : "添加") + (isModel ? "模型供应商" : " " + (record?.name ?? ""))} onClose={onClose}>
    <form className={styles.form} onSubmit={submit}>
      {mode === "demo" && <p className={styles.formNote}>演示配置只在当前访问期间有效。请使用测试内容。</p>}
      <div className={styles.fields}>
        {isModel && <>
          <Field label="显示名称"><input name="name" required maxLength={80} defaultValue={record?.name ?? ""} /></Field>
          <Field label="供应商"><select name="provider" defaultValue={meta.provider ?? "DeepSeek"}>{["DeepSeek", "OpenAI", "Anthropic", "Moonshot", "兼容服务"].map(provider => <option key={provider}>{provider}</option>)}</select></Field>
          <Field label="模型名称"><input name="detail" required maxLength={100} defaultValue={record?.detail ?? ""} placeholder="deepseek-chat" /></Field>
          <Field label="用途"><select name="assigned" defaultValue={meta.assigned ?? "未分配"}>{modelUses.map(use => <option key={use}>{use}</option>)}</select></Field>
          <Field label="Base URL"><input name="baseUrl" type="url" required defaultValue={meta.baseUrl ?? ""} placeholder="https://api.example.com/v1" /></Field>
          {mode === "demo" && <Field label="API Key" hint={meta.credential === "true" ? "已标记为配置，留空保留该状态。" : "输入框使用遮罩，演示仅保存有无密钥。"}><input name="secret" type="password" autoComplete="off" /></Field>}
        </>}
        {isSource && <>
          <Field label="资料库或来源名称"><input name="detail" required maxLength={120} defaultValue={record?.detail} /></Field>
          <Field label="同步频率（分钟）"><input name="frequency" type="number" required min={5} max={1440} defaultValue={meta.frequency ?? "30"} /></Field>
          {mode === "demo" && <Field label="授权 Token"><input name="secret" type="password" autoComplete="off" /></Field>}
          <label className={styles.check}><input name="automatic" type="checkbox" defaultChecked={meta.automatic === "true"} />自动同步</label>
        </>}
        {isNotification && <>
          <Field label="渠道用途"><input name="detail" required maxLength={120} defaultValue={record?.detail} /></Field>
          {mode === "demo" && <Field label="渠道密钥或 Webhook" hint="演示仅保存配置状态。"><input name="secret" type="password" autoComplete="off" /></Field>}
        </>}
        {isMemory && <>
          <Field label="算法"><select name="detail" defaultValue={record?.detail ?? "FSRS"}><option>FSRS</option><option>艾宾浩斯</option></select></Field>
          <Field label="目标记忆保持率（%）"><input name="retention" type="number" required min={70} max={99} defaultValue={meta.retention ?? memoryDefaults.retention} /></Field>
          <Field label="固定复习间隔（天）" hint="使用逗号分隔，例如 1,3,7,14,30。"><input name="interval" required maxLength={90} defaultValue={meta.interval ?? memoryDefaults.interval} /></Field>
          <Field label="最大间隔（天）"><input name="maxInterval" type="number" required min={1} max={36500} defaultValue={meta.maxInterval ?? memoryDefaults.maxInterval} /></Field>
          <Field label="默认难度（1–10）"><input name="difficulty" type="number" required min={1} max={10} defaultValue={meta.difficulty ?? memoryDefaults.difficulty} /></Field>
        </>}
      </div>
      {!isMemory && <div className={styles.checks}>
        <label className={styles.check}><input name="enabled" type="checkbox" defaultChecked={record ? record.status === "ok" : true} />启用{isModel ? "模型" : isSource ? "数据源" : "渠道"}</label>
        {isModel && <label className={styles.check}><input name="default" type="checkbox" defaultChecked={meta.default === "true"} />设置为默认模型</label>}
      </div>}
      {error && <Message feedback={{ text: error, error: true }} />}
      <FormFooter busy={busy} onClose={onClose} />
    </form>
  </Dialog>;
}

const templateTokens = [
  ["title", "知识点标题", "主动回忆与间隔复习"], ["subject", "学科名称", "学习方法"],
  ["review_count", "复习次数", "第 3 次"], ["stage", "记忆阶段", "巩固期"],
  ["content", "知识点正文", "先尝试回忆，再查看资料，最后为回忆表现评分。"],
  ["explanation", "知识点解析", "主动回忆的难度可以帮助你识别哪些内容需要再次复习。"],
  ["question", "主动回忆问题", "为什么应该先回忆再对照笔记？"],
  ["notion_url", "Notion 原始链接", "https://www.notion.so/example"],
  ["review_url", "复习入口", "/review/example"],
] as const;
const defaultTemplate = templateTokens.map(([key, label]) => label + "  {{" + key + "}}").join("\n");

function TemplateEditor({ client, mode }: { client: AdminClient; mode: Mode }) {
  const [draft, setDraft] = useState(defaultTemplate);
  const [feedback, setFeedback] = useState<Feedback | null>(null);
  const [busy, setBusy] = useState(false);
  const input = useRef<HTMLTextAreaElement>(null);
  useEffect(() => {
    let active = true;
    client.collection("notifications").then(result => {
      if (active && result.data) {
        const template = result.data.find(record => record.id === "review-template");
        if (template) setDraft(template.detail);
      }
    }).catch(() => undefined);
    return () => { active = false; };
  }, [client]);
  const preview = draft.replace(/\{\{([a-z_]+)\}\}/g, (token, key) => templateTokens.find(([name]) => name === key)?.[2] ?? token);
  function insertToken(key: string) {
    const textarea = input.current;
    if (!textarea) return;
    const token = "{{" + key + "}}";
    const { selectionStart, selectionEnd } = textarea;
    setDraft(value => value.slice(0, selectionStart) + token + value.slice(selectionEnd));
    requestAnimationFrame(() => {
      textarea.focus();
      textarea.setSelectionRange(selectionStart + token.length, selectionStart + token.length);
    });
  }
  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFeedback(null);
    const unknown = [...draft.matchAll(/\{\{([^{}]+)\}\}/g)].map(match => match[1]).filter(key => !templateTokens.some(([name]) => name === key));
    if (!draft.trim() || unknown.length) {
      setFeedback({ error: true, text: unknown.length ? "存在无效变量 " + unknown.join("、") : "请输入模板内容。" });
      return;
    }
    setBusy(true);
    try {
      const result = await client.saveRecord("notifications", { name: "复习通知模板", detail: draft, status: "ok" }, "review-template");
      setFeedback({ error: result.source === "unavailable", text: result.message ?? (mode === "demo" ? "演示模板已保存。" : "模板已保存。") });
    } catch {
      setFeedback({ error: true, text: "保存失败，请稍后重试。" });
    } finally { setBusy(false); }
  }
  return <Panel title="复习通知模板" subtitle={mode === "demo" ? "使用演示知识点检查通知内容和变量。" : "检查通知内容和变量。"}>
    <form className={styles.templateGrid} onSubmit={save}>
      <div className={styles.form}>
        <Field label="模板正文"><textarea ref={input} value={draft} onChange={event => setDraft(event.target.value)} rows={8} maxLength={2500} required /></Field>
        <div className={styles.tokens} aria-label="插入模板变量">{templateTokens.map(([key, label]) =>
          <button type="button" className={styles.token} onClick={() => insertToken(key)} key={key}>{label}</button>,
        )}</div>
        <div><button className={styles.primary} type="submit" disabled={busy}>{busy ? "保存中…" : "保存模板"}</button></div>
        <Message feedback={feedback} />
      </div>
      <div className={styles.templatePreview}><strong><Mail size={17} /> 消息预览 · 示例内容</strong><p>{preview || "输入模板后可查看结果。"}</p></div>
    </form>
  </Panel>;
}

function MemoryCharts({ records, demo }: { records: ManagementRecord[]; demo: boolean }) {
  const [subject, setSubject] = useState("global");
  const record = records.find(item => item.id === subject) ?? records[0];
  const [preset, setPreset] = useState<{ subject: string; value: number } | null>(null);
  const target = Number(record?.meta?.retention ?? 90);
  const result = preset?.subject === subject ? preset.value : target;
  return <Panel title="记忆曲线" subtitle={demo ? "实测示例与预测示意采用不同线型。演示曲线仅用于验证交互。" : "等待后端提供预测结果与学科复习表现。"}>
    {demo ? <>
      <form className={styles.simulator} onSubmit={event => {
        event.preventDefault();
        const value = new FormData(event.currentTarget).get("target");
        setPreset({ subject, value: Number(value) });
      }}>
        <Field label="学科策略"><select value={subject} onChange={event => setSubject(event.target.value)}>{records.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</select></Field>
        <Field label="目标保持率（%）"><input key={subject + "-" + target} type="number" min={70} max={99} name="target" required defaultValue={target} /></Field>
        <button type="submit" className={styles.secondary}><Play size={15} />模拟预览</button>
      </form>
      <TrendChart label="保持率模拟曲线" data={memoryExample(result, subject)} height={230} percentAxis series={[
        { key: "observed", label: "实际表现示例", color: "var(--cyan)", kind: "line", axis: "percent" },
        { key: "predicted", label: "预测示意", color: "var(--violet)", kind: "line", axis: "percent", dashed: true },
      ]} />
    </> : <p className={styles.dimText}>算法模拟服务待接入。</p>}
  </Panel>;
}
function ModelsCharts({ demo }: { demo: boolean }) {
  return <div className={styles.split}>
    <Panel title="模型调用趋势" subtitle={demo ? "最近 7 天 · 演示用量" : "等待模型用量服务接入。"}>
      {demo && <TrendChart label="调用次数与 Token 消耗" data={modelCalls} height={236} series={[
        { key: "calls", label: "调用次数", color: "var(--blue)", kind: "bar", unit: " 次" },
        { key: "tokens", label: "Token 消耗（千）", color: "var(--cyan)", kind: "line", unit: " 千 Token" },
      ]} />}
    </Panel>
    <Panel title="调用分布" subtitle={demo ? "各模型与任务的调用占比 · 演示" : "等待模型用量服务接入。"}>
      {demo && <div className={styles.distribution}>
        <Bars label="模型调用占比" entries={[
          { name: "DeepSeek", value: 56, color: "var(--blue)" }, { name: "OpenAI", value: 28, color: "var(--cyan)" }, { name: "Moonshot", value: 16, color: "var(--violet)" },
        ]} />
        <Bars label="用途调用占比" entries={[
          { name: "知识提取", value: 48, color: "var(--blue)" }, { name: "复习题生成", value: 32, color: "var(--violet)" }, { name: "答案评价", value: 20, color: "var(--cyan)" },
        ]} />
      </div>}
    </Panel>
    {demo && <>
      <Panel title="费用趋势" subtitle="估算金额 · 演示"><TrendChart label="费用趋势" data={modelCalls} height={190} series={[
        { key: "cost", label: "估算费用", color: "var(--violet)", kind: "area", unit: " USD" },
      ]} /></Panel>
      <Panel title="模型错误率" subtitle="失败请求占比 · 演示"><TrendChart label="模型错误率" data={modelCalls} height={190} series={[
        { key: "error", label: "错误率", color: "var(--danger)", kind: "line", unit: "%" },
      ]} /></Panel>
    </>}
  </div>;
}

function DeliveryHistory() {
  return <Panel title="消息发送记录" subtitle="最近投递结果 · 演示记录">
    <Table columns={["模板", "渠道", "时间", "结果"]}>
      {deliveryExamples.map(event => <tr key={event.id}><td>{event.name}</td><td>{event.channel}</td><td>{event.time}</td><td><Status status={event.result} /></td></tr>)}
    </Table>
  </Panel>;
}

function SourceHistory({ records }: { records: ManagementRecord[] }) {
  const entries = records.filter(record => record.meta?.history);
  return <Panel title="同步历史" subtitle="演示记录 · 尚无真实同步历史数据">
    <Table columns={["来源", "同步时间", "结果"]}>
      {entries.map(record => <tr key={record.id}><td>{record.name}</td><td>{formatTime(record.meta?.lastSync ?? record.updatedAt)}</td><td>{record.meta?.history}</td></tr>)}
    </Table>
  </Panel>;
}

function JobTrend() {
  return <Panel title="任务执行趋势" subtitle="近期执行量 · 演示">
    <TrendChart label="各任务每日执行次数" data={taskRuns} height={246} series={[
      { key: "sync", label: "Notion 同步", color: "var(--blue)", kind: "bar", unit: " 次" },
      { key: "extraction", label: "知识提取", color: "var(--violet)", kind: "line", unit: " 次" },
      { key: "review", label: "复习生成", color: "var(--cyan)", kind: "line", unit: " 次" },
      { key: "delivery", label: "通知发送", color: "var(--green)", kind: "line", unit: " 次" },
    ]} />
  </Panel>;
}

const jobNumber = new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 2 });
const jobRecordScopes: Record<string, string> = {
  notion: "每条同步记录的最近结果",
  chapter: "每个章节修订的最近处理结果",
  review_batch: "已生成的复习批次",
  notification: "每次通知投递尝试",
};

function LiveJobs({ client }: { client: AdminClient }) {
  const [data, setData] = useState<JobAnalytics | null>(null);
  const [refresh, setRefresh] = useState(0);
  const [loading, setLoading] = useState(true);
  const [feedback, setFeedback] = useState<Feedback | null>(null);

  useEffect(() => {
    let current = true;
    client.jobAnalytics().then(result => {
      if (!current) return;
      if (result.source === "live" && result.data) {
        setData(result.data);
        return;
      }
      setData(null);
      setFeedback({ error: true, text: result.message ?? "任务统计暂不可用，请重试。" });
    }).catch(() => {
      if (current) {
        setData(null);
        setFeedback({ error: true, text: "读取任务统计失败，请重试。" });
      }
    }).finally(() => {
      if (current) setLoading(false);
    });
    return () => { current = false; };
  }, [client, refresh]);

  const totals = data?.kinds.reduce((counts, kind) => ({
    success: counts.success + kind.success,
    failure: counts.failure + kind.failure,
    partial: counts.partial + (kind.partial ?? 0),
  }), { success: 0, failure: 0, partial: 0 });
  const plotted = data?.days.map(day => ({ ...day, partial: day.partial ?? 0, durationSamples: day.durationSamples ?? 0 })) ?? [];
  const start = plotted[0]?.date;
  const end = plotted.at(-1)?.date;
  const window = start && end ? "最近 30 天 · " + start + " 至 " + end : "最近 30 天";
  const hasActivity = totals && totals.success + totals.failure + totals.partial > 0;

  return <>
    <Panel title="任务运行汇总" subtitle={window} action={
      <button type="button" className={styles.secondary} disabled={loading} onClick={() => {
        setFeedback(null);
        setLoading(true);
        setRefresh(value => value + 1);
      }}>
        <RefreshCw size={15} aria-hidden="true" />{loading ? "读取中…" : "刷新统计"}
      </button>
    }>
      <Message feedback={feedback} />
      {loading && <p className={styles.dimText} role="status">正在读取统一后端的任务统计。</p>}
      {totals && <div className={styles.stats}>
        <Stat title="成功记录" value={jobNumber.format(totals.success)} icon={Check} tone="cyan" />
        <Stat title="失败记录" value={jobNumber.format(totals.failure)} icon={X} />
        <Stat title="部分完成" value={jobNumber.format(totals.partial)} icon={Activity} tone="violet" />
      </div>}
    </Panel>
    {data && <>
      <Panel title="按任务类型统计" subtitle="作业结果和测量样本按来源统计。">
        <Table columns={["任务", "成功", "失败", "部分完成", "平均耗时", "耗时样本"]}>
          {data.kinds.map(kind => <tr key={kind.key ?? kind.name}>
            <td><div className={styles.entry}><span>{kind.name}</span>{kind.key && <small>{jobRecordScopes[kind.key]}</small>}</div></td>
            <td className={styles.jobValue}>{jobNumber.format(kind.success)}</td>
            <td className={styles.jobValue}>{jobNumber.format(kind.failure)}</td>
            <td className={styles.jobValue}>{jobNumber.format(kind.partial ?? 0)}</td>
            <td className={styles.jobValue}>{kind.averageMs === null ? "暂无测量" : jobNumber.format(kind.averageMs) + " ms"}</td>
            <td className={styles.jobValue}>{jobNumber.format(kind.durationSamples ?? 0)}</td>
          </tr>)}
        </Table>
      </Panel>
      <div className={styles.split}>
        <Panel title="每日任务结果" subtitle="管理账号时区 · 按日期显示记录数量">
          {hasActivity ? <TrendChart label="每日任务结果" data={plotted} height={230} countUnit="记录 · 条" series={[
            { key: "success", label: "成功", color: "var(--cyan)", kind: "bar", unit: " 条" },
            { key: "failure", label: "失败", color: "var(--danger)", kind: "bar", unit: " 条" },
            { key: "partial", label: "部分完成", color: "var(--warning)", kind: "bar", unit: " 条" },
          ]} /> : <p className={styles.jobEmpty}>这段时间暂无任务结果。</p>}
        </Panel>
        <Panel title="每日平均耗时" subtitle="每条实测耗时记录计入当天平均值">
          {plotted.some(day => day.averageMs !== null) ? <TrendChart label="每日平均耗时" data={plotted} height={230} countUnit="时间 · ms"
            series={[{ key: "averageMs", label: "平均耗时", color: "var(--violet)", kind: "bar", unit: " ms" }]}
            noteForPoint={point => "耗时样本 " + jobNumber.format(Number(point.durationSamples)) + " 条"} /> :
            <p className={styles.jobEmpty}>这段时间暂无实测耗时。</p>}
        </Panel>
      </div>
    </>}
  </>;
}

function JobDetails({ record, onClose }: { record: ManagementRecord; onClose: () => void }) {
  return <Dialog title={record.name + " · 最近执行"} onClose={onClose}>
    <div className={styles.form}>
      <div className={styles.detailList}>
        <div><span>最近更新时间</span><strong>{formatTime(record.updatedAt)}</strong></div>
        <div><span>状态</span><Status status={record.status} /></div>
        <div><span>平均耗时</span><strong>{record.meta?.duration ?? "—"}</strong></div>
        <div><span>成功率</span><strong>{record.meta?.success ?? "—"}</strong></div>
        <div><span>失败率</span><strong>{record.meta?.failure ?? "—"}</strong></div>
        <div><span>失败原因</span><strong>{record.meta?.error ?? "无记录"}</strong></div>
      </div>
    </div>
  </Dialog>;
}

function ConnectionList({ records }: { records: ManagementRecord[] }) {
  const icons: Record<string, typeof Bell> = { notion: Database, obsidian: Layers3, files: Terminal, pdf: Layers3, web: Cloud, video: Play, github: Terminal, bark: Bell, qq: Mail, wechat: Radio, dingtalk: Radio, telegram: Radio };
  return <div className={styles.connectionGrid}>{records.map(record => {
    const Icon = icons[record.id] ?? Cloud;
    return <div className={styles.connection} key={record.id}>
      <div><span className={styles.connectionIcon}><Icon size={18} /></span><Status status={record.status} /></div>
      <strong>{record.name}</strong><small>{record.detail}</small>
    </div>;
  })}</div>;
}

function RecordsView({ section, mode, client }: { section: Exclude<ManagementSection, "settings" | "monitoring">; mode: Mode; client: AdminClient }) {
  const [records, setRecords] = useState<ManagementRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [unavailable, setUnavailable] = useState("");
  const [filter, setFilter] = useState("all");
  const [feedback, setFeedback] = useState<Feedback | null>(null);
  const [editor, setEditor] = useState<{ record: ManagementRecord | null } | null>(null);
  const [removing, setRemoving] = useState<ManagementRecord | null>(null);
  const [details, setDetails] = useState<ManagementRecord | null>(null);
  const [busy, setBusy] = useState(false);
  const demo = mode === "demo";
  const load = useCallback(async () => {
    try {
      const result = await client.collection(section);
      setRecords(result.data?.filter(record => record.id !== "review-template") ?? []);
      setUnavailable(result.source === "unavailable" ? result.message || "服务尚未提供此功能。" : "");
    } catch {
      setUnavailable("无法获取管理数据，请稍后重试。");
      setRecords([]);
    } finally { setLoading(false); }
  }, [client, section]);
  useEffect(() => { void load(); }, [load]);
  const onSave = async (input: RecordInput) => {
    setBusy(true);
    try {
      const result = await client.saveRecord(section, input, editor?.record?.id);
      if (result.source === "unavailable" || !result.data) return false;
      setFeedback({ error: false, text: demo ? "演示配置已保存。" : "配置已保存。" });
      await load();
      return true;
    } catch { return false; }
    finally { setBusy(false); }
  };
  const remove = async (id: string) => {
    setBusy(true);
    try {
      const result = await client.deleteRecord(section, id);
      setFeedback({ error: result.source === "unavailable", text: result.message ?? (demo ? "演示模型已删除。" : "模型已删除。") });
      setRemoving(null);
      await load();
    } catch {
      setRemoving(null);
      setFeedback({ error: true, text: "删除失败，请重试。" });
    } finally { setBusy(false); }
  };
  const run = async (id: string, action: string) => {
    setBusy(true);
    try {
      const result = await client.runAction(section, id, action);
      setFeedback({ error: result.source === "unavailable", text: result.data?.message ?? result.message ?? "没有服务回执。" });
      await load();
    } catch { setFeedback({ error: true, text: "请求失败，请重试。" }); }
    finally { setBusy(false); }
  };
  const visible = records.filter(record => filter === "all" || record.status === filter);
  const showTable = !unavailable && !loading;
  const isModel = section === "models";
  const isSource = section === "sources";
  const isNotification = section === "notifications";
  const isMemory = section === "memory";
  const isJob = section === "jobs";
  const columns = {
    models: ["供应商 / 模型", "用途", "凭据", "状态", "操作"],
    sources: ["来源", "自动同步", "成功 / 失败", "最近同步", "状态", "操作"],
    notifications: ["通知渠道", "成功 / 尝试", "成功率", "状态", "操作"],
    memory: ["学科 / 策略", "目标保持率", "固定间隔（天）", "最大间隔（天）", "操作"],
    jobs: ["任务", "成功率", "失败率", "平均用时", "最近运行", "状态", "操作"],
  }[section];
  const tableTitle = {
    models: "模型供应商", sources: "已登记的数据源", notifications: "通知渠道",
    memory: "全局与学科策略", jobs: "任务与执行记录",
  }[section];
  return <>
    {isModel && demo && <div className={styles.stats}>
      <Stat title="启用模型" value={String(records.filter(record => record.status === "ok").length)} icon={BrainCircuit} />
      <Stat title="最近 7 天调用" value={modelCalls.reduce((total, day) => total + day.calls, 0).toLocaleString()} icon={Activity} tone="cyan" />
      <Stat title="最近 7 天 Token" value={modelCalls.reduce((total, day) => total + day.tokens, 0) + "k"} icon={Layers3} tone="violet" />
    </div>}
    {(isSource || isNotification) && showTable && <ConnectionList records={records} />}
    {isMemory && <div className={styles.split}>
      <Panel title="艾宾浩斯固定间隔" subtitle="从首次学习开始按配置的天数安排复习。">
        <div className={styles.algorithm}><Clock3 size={21} /><div><strong>固定日程</strong><p>适用于希望按统一节奏复习的学科或课程。</p></div></div>
      </Panel>
      <Panel title="FSRS 自适应调度" subtitle="根据复习评分更新记忆状态和下次复习时间。">
        <div className={styles.algorithm} data-violet="true"><BrainCircuit size={21} /><div><strong>可配置目标保持率</strong><p>可以按学科分别设置保持率和最大复习间隔。</p></div></div>
      </Panel>
    </div>}
    <Panel title={tableTitle} action={<div className={styles.rowActions}>
      {isJob && showTable && <label className={styles.filter}><ArrowDownUp size={14} /><select aria-label="任务状态" value={filter} onChange={event => setFilter(event.target.value)}><option value="all">全部状态</option>{Object.entries(statusLabels).map(([key, label]) => <option value={key} key={key}>{label}</option>)}</select></label>}
      {isModel && showTable && <button type="button" className={styles.primary} onClick={() => setEditor({ record: null })}><Plus size={16} />添加模型</button>}
    </div>}>
      <Message feedback={feedback} />
      {loading && <p className={styles.dimText} role="status">加载数据中…</p>}
      {unavailable && <div className={styles.empty}>
        <Database size={22} /><strong>此模块的管理数据暂不可用</strong><p>{unavailable}</p>
        <Link href={"/demo/" + section} className={styles.secondary}>查看演示<ArrowRight size={15} /></Link>
      </div>}
      {showTable && <Table columns={columns}>
        {visible.length === 0 && <tr><td colSpan={columns.length} className={styles.dimText}>暂无符合条件的记录。</td></tr>}
        {visible.map(record => {
          const meta = record.meta ?? {};
          const isDefault = meta.default === "true";
          return <tr key={record.id}>
            <td><Entry record={record} />{isDefault && <Badge tone="running">默认</Badge>}</td>
            {isModel && <><td>{meta.assigned ?? "未分配"}</td><td>{meta.credential === "true" ? "已配置" : "未配置"}</td></>}
            {isSource && <><td>{meta.automatic === "true" ? "每 " + (meta.frequency ?? "30") + " 分钟" : "已关闭"}</td><td>{meta.success ?? "—"} / {meta.failed ?? "—"}</td><td>{meta.history ? formatTime(meta.lastSync ?? record.updatedAt) : "—"}</td></>}
            {isNotification && <><td>{meta.delivery ?? "—"}</td><td>{meta.rate ?? "—"}</td></>}
            {isMemory && <><td>{record.detail === "FSRS" ? (meta.retention ?? "—") + "%" : "—"}</td><td>{record.detail === "艾宾浩斯" ? meta.interval?.split(",").join(" · ") ?? "—" : "—"}</td><td>{meta.maxInterval ?? "—"}</td></>}
            {isJob && <><td>{meta.success ?? "—"}</td><td>{meta.failure ?? "—"}</td><td>{meta.duration ?? "—"}</td><td>{formatTime(record.updatedAt)}</td></>}
            {!isMemory && <td><Status status={record.status} /></td>}
            <td><div className={styles.rowActions}>
              {!isJob && <button type="button" className={styles.smallButton} onClick={() => setEditor({ record })}><Pencil size={13} />{isSource && record.id === "notion" ? "授权与配置" : "配置"}</button>}
              {isModel && <><button type="button" className={styles.smallButton} disabled={busy} onClick={() => void run(record.id, "test")}>连接测试</button><button type="button" aria-label={"删除 " + record.name} className={styles.iconButton} onClick={() => setRemoving(record)}><Trash2 size={15} /></button></>}
              {isSource && <button type="button" className={styles.smallButton} disabled={busy || record.status === "planned"} onClick={() => void run(record.id, "sync")}><RefreshCw size={13} />手动同步</button>}
              {isNotification && <button type="button" className={styles.smallButton} disabled={busy || record.status === "planned"} onClick={() => void run(record.id, "test")}>测试发送</button>}
              {isJob && <><button type="button" className={styles.smallButton} onClick={() => setDetails(record)}>详情</button><button type="button" className={styles.smallButton} disabled={busy || record.status === "running" || record.status === "queued"} onClick={() => void run(record.id, "trigger")}><Play size={13} />{record.status === "failed" ? "重试" : "触发"}</button></>}
            </div></td>
          </tr>;
        })}
      </Table>}
    </Panel>
    {isModel && <ModelsCharts demo={demo} />}
    {isSource && demo && <SourceHistory records={records} />}
    {isNotification && showTable && <TemplateEditor client={client} mode={mode} />}
    {isNotification && demo && <DeliveryHistory />}
    {isMemory && <MemoryCharts records={records} demo={demo} />}
    {isJob && demo && <JobTrend />}
    {editor && !isJob && <RecordForm record={editor.record} section={section} busy={busy} mode={mode} onClose={() => setEditor(null)} onSave={onSave} />}
    {details && <JobDetails record={details} onClose={() => setDetails(null)} />}
    {removing && <Dialog title="删除模型配置" onClose={() => setRemoving(null)}>
      <form className={styles.form} onSubmit={event => { event.preventDefault(); void remove(removing.id); }}>
        <p>确认删除 {removing.name} 的{demo ? "演示" : ""}配置？</p>
        <FormFooter submit="确认删除" busy={busy} onClose={() => setRemoving(null)} />
      </form>
    </Dialog>}
  </>;
}
function Monitor({ client, mode }: { client: AdminClient; mode: Mode }) {
  const [health, setHealth] = useState<SystemHealth | null>(null);
  const [loading, setLoading] = useState(true);
  const [feedback, setFeedback] = useState<Feedback | null>(null);
  const demo = mode === "demo";
  const load = useCallback(async () => {
    setLoading(true);
    setFeedback(null);
    try {
      const result = await client.health();
      setHealth(result.data);
      if (result.source === "unavailable") setFeedback({ text: result.message ?? "无法查询后端服务健康。", error: true });
    } catch {
      setHealth(null);
      setFeedback({ text: "无法查询后端服务健康。", error: true });
    } finally { setLoading(false); }
  }, [client]);
  useEffect(() => { void load(); }, [load]);
  const last = resources[resources.length - 1];
  return <>
    <Panel title="服务健康检查" subtitle={health ? "最新检查 " + formatTime(health.checkedAt) : "查询统一后端的健康检查接口。"} action={
      <button type="button" className={styles.secondary} disabled={loading} onClick={() => void load()}><RefreshCw size={15} />{loading ? "检查中…" : "刷新服务状态"}</button>
    }>
      <Message feedback={feedback} />
      <div className={styles.healthGrid}>
        {[
          { title: "API 服务", Icon: Server, status: health?.status, detail: "后端 HTTP 健康检查" },
          { title: "PostgreSQL", Icon: Database, status: health?.database, detail: health?.migration ? "迁移版本 " + health.migration : "数据库连接" },
          ...(demo ? [
            { title: "Redis", Icon: Layers3, status: undefined, detail: "演示状态" },
            { title: "后台 Worker", Icon: Cpu, status: "paused", detail: "演示状态" },
          ] : []),
        ].map(({ title, Icon, status, detail }) => <div className={styles.health} key={title}>
          <Icon size={19} /><div><strong>{title}</strong><small>{detail}</small></div>
          <Badge tone={status === "ready" ? "ok" : status === "unavailable" ? "failed" : "planned"}>{status === "ready" ? "可用" : status === "unavailable" ? "不可用" : status === "paused" ? "已暂停" : "无采集数据"}</Badge>
        </div>)}
      </div>
    </Panel>
    {demo ? <>
      <div className={styles.stats}>
        <Stat title="API 响应时间" value={last.latency + " ms"} detail="最新采样" icon={Activity} tone="cyan" />
        <Stat title="API 请求数量" value={last.requests.toLocaleString()} detail="最近 24 小时" icon={Server} />
        <Stat title="API 错误率" value={(100 * last.errors / last.requests).toFixed(2) + "%"} detail={last.errors + " 次错误"} icon={Radio} tone="violet" />
      </div>
      <div className={styles.split}>
        <Panel title="系统资源使用率" subtitle="最新资源采样 · 演示">
          <div className={styles.rings}>
            <RingChart label="CPU" value={last.cpu} color="var(--cyan)" size={100} />
            <RingChart label="内存" value={last.memory} color="var(--blue)" size={100} />
            <RingChart label="磁盘" value={last.disk} color="var(--violet)" size={100} />
          </div>
        </Panel>
        <Panel title="计算资源趋势" subtitle="最近 7 天 · 演示">
          <TrendChart label="CPU、内存与磁盘使用率" data={resources} height={230} percentAxis series={[
            { key: "cpu", label: "CPU", color: "var(--cyan)", kind: "line", axis: "percent" },
            { key: "memory", label: "内存", color: "var(--blue)", kind: "line", axis: "percent" },
            { key: "disk", label: "磁盘", color: "var(--violet)", kind: "line", axis: "percent" },
          ]} />
        </Panel>
        <Panel title="API 响应时间" subtitle="最近 7 天 · 演示"><TrendChart label="API 响应时间" data={resources} height={205} series={[
          { key: "latency", label: "响应时间", color: "var(--cyan)", kind: "area", unit: " ms" },
        ]} /></Panel>
        <Panel title="API 请求与错误" subtitle="最近 7 天 · 演示"><TrendChart label="API 请求与错误" data={resources} height={205} series={[
          { key: "requests", label: "请求数", color: "var(--blue)", kind: "bar", unit: " 次" },
          { key: "errors", label: "错误数", color: "var(--danger)", kind: "line", unit: " 次" },
        ]} /></Panel>
      </div>
    </> : <LiveOperations section="monitoring" client={client} />}
  </>;
}

function PasswordForm({ client, mode, onClose }: { client: AdminClient; mode: Mode; onClose: () => void }) {
  const [feedback, setFeedback] = useState<Feedback | null>(null);
  const [busy, setBusy] = useState(false);
  const demo = mode === "demo";
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const fields = new FormData(form);
    const current = String(fields.get("current") ?? "");
    const password = String(fields.get("password") ?? "");
    const confirmation = String(fields.get("confirmation") ?? "");
    if (password.trim().length < 10 || current === password || confirmation !== password) {
      setFeedback({ text: confirmation !== password ? "两次输入的新密码不一致。" : current === password ? "请输入与当前密码不同的新密码。" : "新密码至少需要 10 个字符。", error: true });
      return;
    }
    setBusy(true);
    setFeedback(null);
    try {
      if (demo) {
        form.reset();
        setFeedback({ text: "演示校验通过，真实账户密码保持原样。", error: false });
      } else {
        await client.changePassword({ current_password: current, new_password: password });
        form.reset();
        window.location.replace("/login");
      }
    } catch (error) {
      setFeedback({ text: error instanceof Error ? error.message : "修改密码失败，请重试。", error: true });
    } finally { setBusy(false); }
  }
  return <Dialog title="修改管理员密码" onClose={onClose}>
    <form className={styles.form} onSubmit={submit}>
      <p className={styles.formNote}>{demo ? "仅演示密码校验，请使用测试内容。" : "修改成功后需要重新登录。"}</p>
      <Field label="当前密码"><input type="password" name="current" required maxLength={256} autoComplete="current-password" /></Field>
      <Field label="新密码" hint="至少 10 个字符。"><input type="password" name="password" required minLength={10} maxLength={256} autoComplete="new-password" /></Field>
      <Field label="确认新密码"><input type="password" name="confirmation" required minLength={10} maxLength={256} autoComplete="new-password" /></Field>
      <Message feedback={feedback} />
      <FormFooter busy={busy} onClose={onClose} submit="修改密码" />
    </form>
  </Dialog>;
}

function AuditPanel({ client, demo }: { client: AdminClient; demo: boolean }) {
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [severity, setSeverity] = useState<AuditEvent["severity"] | "all">("all");
  const [cursor, setCursor] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<Feedback | null>(null);
  const [loading, setLoading] = useState(true);
  const load = useCallback(async (next?: string) => {
    setLoading(true);
    setFeedback(null);
    try {
      const result = await client.audit({ limit: 12, severity: severity === "all" ? undefined : severity, cursor: next });
      if (result.source === "unavailable") throw new Error(result.message ?? "日志接口暂不可用。");
      const page = result.data;
      setEvents(previous => next ? [...previous, ...(page?.items ?? [])] : page?.items ?? []);
      setCursor(page?.next_cursor ?? null);
    } catch (error) {
      setFeedback({ text: error instanceof Error ? error.message : "读取审计日志失败。", error: true });
      if (!next) setEvents([]);
      setCursor(null);
    } finally { setLoading(false); }
  }, [client, severity]);
  useEffect(() => { void load(); }, [load]);
  return <Panel title="系统日志与操作审计" subtitle={demo ? "示例日志，可按严重性筛选。" : "当前账户有权访问的后端审计事件。"} action={
    <label className={styles.filter}><ShieldCheck size={15} /><select aria-label="日志严重性" value={severity} onChange={event => setSeverity(event.target.value as typeof severity)}><option value="all">全部级别</option><option value="info">信息</option><option value="warning">警告</option><option value="high">高风险</option></select></label>
  }>
    <Message feedback={feedback} />
    <Table columns={["事件", "操作人", "资源", "结果", "级别", "时间"]}>
      {events.map(event => <tr key={event.id}>
        <td><code>{event.action}</code></td><td>{event.actor_label}</td><td>{event.resource}</td><td>{event.outcome}</td>
        <td><Badge tone={event.severity === "info" ? "ok" : event.severity === "warning" ? "queued" : "failed"}>{({ info: "信息", warning: "警告", high: "高风险" })[event.severity]}</Badge></td><td>{formatTime(event.created_at)}</td>
      </tr>)}
      {events.length === 0 && <tr><td colSpan={6}>{loading ? "读取日志中…" : "暂无记录。"}</td></tr>}
    </Table>
    {cursor && <div className={styles.panelFooter}><button type="button" className={styles.secondary} disabled={loading} onClick={() => void load(cursor)}>加载更多<ChevronRight size={15} /></button></div>}
  </Panel>;
}
function AccountForm({ account, client, onSave, onClose }: {
  account: Account | null;
  client: AdminClient;
  onSave: (account: Account) => void;
  onClose: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [feedback, setFeedback] = useState<Feedback | null>(null);
  const requestKey = useRef<string | null>(null);
  const inFlight = useRef(false);
  const title = account ? "编辑学习者" : "新增学习者";
  function close() {
    if (!inFlight.current) onClose();
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (inFlight.current) return;
    const form = new FormData(event.currentTarget);
    const name = String(form.get("display_name") ?? "").trim();
    const password = String(form.get("password") ?? "");
    if (!name) {
      setFeedback({ text: "请输入用户称呼。", error: true });
      return;
    }
    if (!account && (password.trim().length < 10 || password !== form.get("confirmation"))) {
      setFeedback({ text: "两次密码须一致，且至少包含 10 个有效字符。", error: true });
      return;
    }
    inFlight.current = true;
    setBusy(true);
    setFeedback(null);
    try {
      if (account) {
        onSave(await client.updateUser(account.id, account.version, {
          display_name: name,
          is_active: form.has("is_active"),
        }));
      } else {
        requestKey.current ??= crypto.randomUUID();
        onSave(await client.createUser({
          display_name: name,
          email: String(form.get("email") ?? "").trim(),
          password,
          timezone: String(form.get("timezone") ?? "").trim(),
        }, requestKey.current));
      }
    } catch (error) {
      setFeedback({ text: error instanceof Error ? error.message : "保存失败，请重试。", error: true });
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
  }

  return <Dialog title={title} onClose={close}>
    <form className={styles.form} onSubmit={submit} onChange={() => { requestKey.current = null; }}>
      <fieldset className={styles.formFields} disabled={busy}>
        <Field label="用户称呼"><input name="display_name" defaultValue={account?.display_name} required maxLength={120} /></Field>
        {account ? <>
          <Field label="用户邮箱"><input value={account.email} readOnly /></Field>
          <label className={styles.check}><input type="checkbox" name="is_active" defaultChecked={account.is_active} />启用学习者账号</label>
          <p className={styles.formNote}>停用账号将结束该学习者的现有登录会话。</p>
        </> : <>
          <Field label="用户邮箱"><input name="email" type="email" required maxLength={254} /></Field>
          <Field label="用户时区" hint="使用 IANA 时区名称，例如 Asia/Shanghai。"><input name="timezone" required maxLength={100} defaultValue="Asia/Shanghai" /></Field>
          <Field label="初始密码" hint="至少 10 个有效字符。"><input name="password" type="password" required minLength={10} maxLength={256} autoComplete="new-password" /></Field>
          <Field label="确认初始密码"><input name="confirmation" type="password" required minLength={10} maxLength={256} autoComplete="new-password" /></Field>
        </>}
      </fieldset>
      <Message feedback={feedback} />
      <FormFooter busy={busy} onClose={close} submit={account ? "保存学习者" : "创建学习者"} />
    </form>
  </Dialog>;
}

function Accounts({ client, demo }: { client: AdminClient; demo: boolean }) {
  const [users, setUsers] = useState<Account[]>([]);
  const [sessions, setSessions] = useState<Session[]>([]);
  const [next, setNext] = useState<string | null>(null);
  const [sessionNext, setSessionNext] = useState<string | null>(null);
  const [filters, setFilters] = useState({ online: false, from: "", to: "" });
  const [selected, setSelected] = useState<Account | null>(null);
  const [learner, setLearner] = useState<Account | null>(null);
  const [editor, setEditor] = useState<{ account: Account | null } | null>(null);
  const [search, setSearch] = useState("");
  const [accountsFeedback, setAccountsFeedback] = useState<Feedback | null>(null);
  const [savedFeedback, setSavedFeedback] = useState<Feedback | null>(null);
  const [sessionsFeedback, setSessionsFeedback] = useState<Feedback | null>(null);
  const [loading, setLoading] = useState(true);
  const [sessionsLoading, setSessionsLoading] = useState(true);
  const accountRequest = useRef(0);
  const sessionRequest = useRef(0);
  const readUsers = useCallback(async (cursor?: string) => {
    const request = ++accountRequest.current;
    setLoading(true);
    setAccountsFeedback(null);
    try {
      const result = await client.users({ limit: 12, q: search || undefined, cursor });
      if (request !== accountRequest.current) return;
      if (result.source === "unavailable") throw new Error(result.message ?? "账号列表暂不可用。");
      setUsers(existing => cursor ? [...existing, ...(result.data?.items ?? [])] : result.data?.items ?? []);
      setNext(result.data?.next_cursor ?? null);
    } catch (error) {
      if (request !== accountRequest.current) return;
      if (!cursor) setUsers([]);
      setNext(null);
      setAccountsFeedback({ text: error instanceof Error ? error.message : "读取账号列表失败。", error: true });
    } finally { if (request === accountRequest.current) setLoading(false); }
  }, [client, search]);
  const readSessions = useCallback(async (cursor?: string) => {
    const request = ++sessionRequest.current;
    setSessionsLoading(true);
    setSessionsFeedback(null);
    try {
      const result = await client.sessions({
        cursor, limit: 12, online_only: filters.online ? true : undefined, user_id: selected?.id,
        from: filters.from ? new Date(filters.from + "T00:00:00").toISOString() : undefined,
        to: filters.to ? new Date(filters.to + "T23:59:59.999").toISOString() : undefined,
      });
      if (request !== sessionRequest.current) return;
      if (result.source === "unavailable") throw new Error(result.message ?? "登录记录暂不可用。");
      setSessions(existing => cursor ? [...existing, ...(result.data?.items ?? [])] : result.data?.items ?? []);
      setSessionNext(result.data?.next_cursor ?? null);
    } catch (error) {
      if (request !== sessionRequest.current) return;
      if (!cursor) setSessions([]);
      setSessionNext(null);
      setSessionsFeedback({ text: error instanceof Error ? error.message : "读取登录记录失败。", error: true });
    } finally { if (request === sessionRequest.current) setSessionsLoading(false); }
  }, [client, filters, selected]);
  useEffect(() => { void readUsers(); }, [readUsers]);
  useEffect(() => { void readSessions(); }, [readSessions]);
  function accountSaved(account: Account) {
    setEditor(null);
    setSelected(current => current?.id === account.id ? account : current);
    setSavedFeedback({ text: editor?.account ? "学习者资料已保存。" : "学习者账号已创建，可使用初始密码登录学习网站。", error: false });
    void readUsers();
    void readSessions();
  }
  return <>
    <Panel title="账号列表" subtitle={demo ? "演示账户与角色。" : "统一后端的用户账户和角色。"} action={
      <div className={styles.rowActions}>
        <form className={styles.rowActions} onSubmit={event => {
          event.preventDefault();
          setSearch(String(new FormData(event.currentTarget).get("account") ?? "").trim());
        }}>
          <input name="account" className={styles.search} aria-label="姓名或邮箱" placeholder="姓名或邮箱" maxLength={100} /><button type="submit" className={styles.secondary}>搜索</button>
        </form>
        {!demo && <>
          <button type="button" className={styles.secondary} disabled={loading} onClick={() => void readUsers()}><RefreshCw size={14} />刷新账号</button>
          <button type="button" className={styles.primary} onClick={() => { setSavedFeedback(null); setEditor({ account: null }); }}><Plus size={15} />新增学习者</button>
        </>}
      </div>
    }>
      <Message feedback={accountsFeedback} />
      <Message feedback={savedFeedback} />
      <Table columns={["用户", "角色", "账号状态", "操作"]}>
        {users.map(user => <tr key={user.id}>
          <td><div className={styles.entry}><span>{user.display_name}</span><small>{user.email}</small></div></td>
          <td>{user.role === "admin" ? "管理员" : "学习者"}</td><td><Badge tone={user.is_active ? "ok" : "paused"}>{user.is_active ? "已启用" : "已停用"}</Badge></td>
          <td><div className={styles.rowActions}>
            <button type="button" className={styles.smallButton} onClick={() => { setSelected(user); document.getElementById("account-sessions")?.scrollIntoView({ block: "start" }); }}>查看登录<ChevronRight size={13} /></button>
            <button type="button" className={styles.smallButton} onClick={() => setLearner(user)}>学习档案<ChevronRight size={13} /></button>
            {!demo && user.role === "user" && <button type="button" className={styles.smallButton} onClick={() => { setSavedFeedback(null); setEditor({ account: user }); }}><Pencil size={13} />编辑学习者</button>}
          </div></td>
        </tr>)}
        {!users.length && <tr><td colSpan={4}>{loading ? "读取账户中…" : "暂无记录。"}</td></tr>}
      </Table>
      {next && <div className={styles.panelFooter}><button type="button" className={styles.secondary} disabled={loading} onClick={() => void readUsers(next)}>加载更多<ChevronRight size={15} /></button></div>}
    </Panel>
    <div id="account-sessions" className={styles.anchor}>
      <Panel title="登录记录与在线状态" subtitle={(selected ? "用户 " + selected.display_name : "所有账户") + " · 在线状态根据近期会话活动判定。时间按浏览器时区显示。"} action={
        <div className={styles.rowActions}>
          {selected && <button type="button" className={styles.secondary} onClick={() => setSelected(null)}>查看全部账户</button>}
          <button type="button" className={styles.secondary} disabled={sessionsLoading} onClick={() => void readSessions()}><RefreshCw size={14} />刷新</button>
        </div>
      }>
        <form className={styles.simulator} onSubmit={event => {
          event.preventDefault();
          const values = new FormData(event.currentTarget);
          const from = String(values.get("from") ?? "");
          const to = String(values.get("to") ?? "");
          if (from && to && from > to) {
            setSessionsFeedback({ text: "开始日期必须早于或等于结束日期。", error: true });
            return;
          }
          setFilters({ online: values.has("online"), from, to });
        }}>
          <Field label="登录开始日期"><input name="from" type="date" /></Field>
          <Field label="登录结束日期"><input name="to" type="date" /></Field>
          <label className={styles.check}><input type="checkbox" name="online" />仅在线</label>
          <button type="submit" className={styles.secondary}>应用筛选</button>
        </form>
        <Message feedback={sessionsFeedback} />
        <Table columns={["用户", "登录时间", "最后活动", "退出时间", "在线状态"]}>
          {sessions.map(session => <tr key={session.id}>
            <td><div className={styles.entry}><span>{session.display_name}</span><small>{session.email}</small></div></td>
            <td>{formatTime(session.created_at, true)}</td><td>{formatTime(session.last_seen_at, true)}</td>
            <td>{session.logged_out_at ? formatTime(session.logged_out_at, true) : "—"}</td>
            <td><Badge tone={session.online ? "ok" : "planned"}>{session.online ? "在线" : "离线"}</Badge></td>
          </tr>)}
          {!sessions.length && <tr><td colSpan={5}>{sessionsLoading ? "读取登录记录中…" : "暂无符合条件的登录记录。"}</td></tr>}
        </Table>
        {sessionNext && <div className={styles.panelFooter}><button type="button" className={styles.secondary} disabled={sessionsLoading} onClick={() => void readSessions(sessionNext)}>加载更多<ChevronRight size={15} /></button></div>}
      </Panel>
    </div>
    {learner && <LearnerDetails client={client} account={learner} onClose={() => setLearner(null)} />}
    {editor && <AccountForm account={editor.account} client={client} onSave={accountSaved} onClose={() => setEditor(null)} />}
  </>;
}

type Account = NonNullable<Awaited<ReturnType<AdminClient["users"]>>["data"]>["items"][number];
type Session = NonNullable<Awaited<ReturnType<AdminClient["sessions"]>>["data"]>["items"][number];

type LearnerTab = "overview" | "knowledge" | "review";
const learnerTabs = { overview: "学习概况", knowledge: "知识库", review: "复习历史" } satisfies Record<LearnerTab, string>;

function LearnerDetails({ client, account, onClose }: { client: AdminClient; account: Account; onClose: () => void }) {
  const [tab, setTab] = useState<LearnerTab>("overview");
  const [overview, setOverview] = useState<LearnerOverview | null>(null);
  const [knowledge, setKnowledge] = useState<LearnerKnowledge[]>([]);
  const [reviews, setReviews] = useState<LearnerReview[]>([]);
  const [next, setNext] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [feedback, setFeedback] = useState<Feedback | null>(null);
  const requestId = useRef(0);
  const load = useCallback(async (cursor?: string) => {
    const current = ++requestId.current;
    setLoading(true);
    setFeedback(null);
    try {
      if (tab === "overview") {
        const result = await client.userOverview(account.id);
        if (current !== requestId.current) return;
        if (result.source === "unavailable") throw new Error(result.message ?? "学习概况尚不可用。");
        setOverview(result.data);
        setNext(null);
      } else if (tab === "knowledge") {
        const result = await client.userKnowledge(account.id, { limit: 8, cursor });
        if (current !== requestId.current) return;
        if (result.source === "unavailable") throw new Error(result.message ?? "知识库尚不可用。");
        setKnowledge(existing => cursor ? [...existing, ...(result.data?.items ?? [])] : result.data?.items ?? []);
        setNext(result.data?.next_cursor ?? null);
      } else {
        const result = await client.userHistory(account.id, { limit: 8, cursor });
        if (current !== requestId.current) return;
        if (result.source === "unavailable") throw new Error(result.message ?? "复习历史尚不可用。");
        setReviews(existing => cursor ? [...existing, ...(result.data?.items ?? [])] : result.data?.items ?? []);
        setNext(result.data?.next_cursor ?? null);
      }
    } catch (error) {
      if (current !== requestId.current) return;
      setFeedback({ text: error instanceof Error ? error.message : "无法读取学习数据。", error: true });
      if (!cursor) setNext(null);
    } finally { if (current === requestId.current) setLoading(false); }
  }, [account.id, client, tab]);
  useEffect(() => { void load(); }, [load]);
  return <Dialog title={account.display_name + " · 学习档案"} onClose={onClose} wide>
    <div className={styles.form}>
      <div className={styles.rowActions} aria-label="学习档案视图">
        {Object.entries(learnerTabs).map(([key, label]) => <button type="button" key={key} aria-pressed={tab === key} className={tab === key ? styles.primary : styles.secondary} onClick={() => setTab(key as LearnerTab)}>{label}</button>)}
      </div>
      {client.mode === "demo" && <p className={styles.formNote}>当前内容来自演示账户。</p>}
      <Message feedback={feedback} />
      {loading && <p className={styles.dimText} role="status">读取数据中…</p>}
      {tab === "overview" && overview && <div className={styles.detailList}>
        <div><span>用户本地日期</span><strong>{overview.local_date}</strong></div>
        <div><span>知识点</span><strong>{overview.knowledge_count}</strong></div>
        <div><span>学习章节</span><strong>{overview.chapter_count}</strong></div>
        <div><span>当日已复习</span><strong>{overview.today_completed}</strong></div>
        <div><span>当日待复习</span><strong>{overview.today_remaining}</strong></div>
        <div><span>逾期复习</span><strong>{overview.overdue}</strong></div>
      </div>}
      {tab === "knowledge" && <div className={styles.knowledge}>
        {knowledge.map(item => {
          const url = item.source_url ? parseUrl(item.source_url) : null;
          return <details key={item.id}>
            <summary>{item.title}</summary>
            <p>{item.summary || "暂无摘要。"}</p>
            {item.body && <pre>{item.body}</pre>}
            {url && ["http:", "https:"].includes(url.protocol) && !url.username && !url.password &&
              <a href={url.toString()} target="_blank" rel="noreferrer noopener">查看原始资料<ArrowRight size={13} /></a>}
          </details>;
        })}
        {!loading && !knowledge.length && !feedback && <p className={styles.dimText}>暂无知识点。</p>}
      </div>}
      {tab === "review" && <Table columns={["知识点", "策略", "评分", "用时", "复习时间"]}>
        {reviews.map(review => <tr key={review.id}><td>{review.knowledge_title}</td><td>{review.strategy}</td><td>{review.rating}</td><td>{review.duration_seconds} 秒</td><td>{formatTime(review.reviewed_at, true)}</td></tr>)}
        {!loading && !reviews.length && !feedback && <tr><td colSpan={5}>暂无复习历史。</td></tr>}
      </Table>}
      {next && tab !== "overview" && !loading && <div className={styles.panelFooter}><button type="button" className={styles.secondary} onClick={() => void load(next)}>加载更多<ChevronRight size={15} /></button></div>}
    </div>
  </Dialog>;
}


function Settings({ client, mode }: { client: AdminClient; mode: Mode }) {
  const [user, setUser] = useState<AdminUser | null>(null);
  const [feedback, setFeedback] = useState<Feedback | null>(null);
  const [profileLoading, setProfileLoading] = useState(true);
  const [password, setPassword] = useState(false);
  const [backup, setBackup] = useState(false);
  const demo = mode === "demo";
  useEffect(() => {
    let active = true;
    client.session().then(result => { if (active) setUser(result); }).catch(() => {
      if (active) setFeedback({ text: "无法读取管理员资料，请确认会话仍然有效。", error: true });
    }).finally(() => { if (active) setProfileLoading(false); });
    return () => { active = false; };
  }, [client]);
  return <>
    <div className={styles.split}>
      <Panel title="管理员资料" subtitle={demo ? "当前演示账户。" : "当前管理员会话。"}>
        <Message feedback={feedback} />
        {profileLoading && <p className={styles.dimText} role="status">读取会话中…</p>}
        {user && <div className={styles.detailList}>
          <div><span>名称</span><strong>{user.display_name}</strong></div>
          <div><span>邮箱</span><strong>{user.email}</strong></div>
          <div><span>角色</span><strong>管理员</strong></div>
          <div><span>账户时区</span><strong>{user.timezone}</strong></div>
        </div>}
        <div className={styles.panelFooter}><button type="button" className={styles.secondary} onClick={() => setPassword(true)} disabled={!user}><KeyRound size={15} />修改密码</button></div>
      </Panel>
      {client.operations ? <LiveBackups api={client.operations} /> : <Panel title="系统信息与备份" subtitle="了解管理应用版本与备份状态。">
        <div className={styles.detailList}>
          <div><span>产品</span><strong>AI Learning Memory OS</strong></div>
          <div><span>管理前端版本</span><strong>0.1.0</strong></div>
          <div><span>当前模式</span><strong>{demo ? "演示模式" : "后端数据模式"}</strong></div>
          <div><span>服务备份</span><Badge tone="planned">备份 API 待接入</Badge></div>
        </div>
        <div className={styles.panelFooter}><button type="button" className={styles.secondary} onClick={() => setBackup(true)}><Database size={15} />备份入口</button></div>
      </Panel>}
    </div>
    <Accounts client={client} demo={demo} />
    <AuditPanel client={client} demo={demo} />
    {password && <PasswordForm client={client} mode={mode} onClose={() => setPassword(false)} />}
    {backup && <Dialog title="数据备份" onClose={() => setBackup(false)}>
      <div className={styles.form}><p className={styles.dimText}>备份接口接入后，这里将显示备份任务、保存位置和最近完成时间。</p>
      <div className={styles.formFooter}><button type="button" className={styles.secondary} onClick={() => setBackup(false)}>关闭</button></div></div>
    </Dialog>}
  </>;
}

export default function Management({ section, mode, client }: { section: ManagementSection; mode: Mode; client: AdminClient }) {
  const { title, description, icon: Icon } = sections[section];
  return <div className={styles.main}>
    <header className={styles.header}>
      <div className={styles.headerIcon}><Icon size={24} aria-hidden="true" /></div>
      <div className={styles.heading}><h1>{title}</h1><p>{description}</p></div>
      <Badge tone={mode === "demo" ? "queued" : "running"}>{mode === "demo" ? "演示数据" : "后端数据模式"}</Badge>
    </header>
    {section === "monitoring"
      ? <Monitor client={client} mode={mode} />
      : section === "settings"
        ? <Settings client={client} mode={mode} />
        : mode === "live"
          ? <>{section === "jobs" && <LiveJobs client={client} />}<LiveOperations key={section} section={section} client={client} /></>
          : <RecordsView key={section} section={section} client={client} mode={mode} />}
  </div>;
}

function parseUrl(value: string) {
  try {
    return new URL(value);
  } catch {
    return null;
  }
}




