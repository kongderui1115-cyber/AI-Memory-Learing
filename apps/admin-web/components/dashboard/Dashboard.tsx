"use client";

import { useEffect, useState } from "react";
import type { FormEvent, ReactNode } from "react";
import Link from "next/link";
import {
  Activity, ArrowRight, BookOpen, BrainCircuit, CalendarDays, CheckCircle2, CircleAlert,
  Clock3, Database, Layers3, Plus, Radio, RefreshCw, Server, Workflow,
} from "lucide-react";
import type { AdminClient, DashboardData, DateRange, Resource } from "@/lib/client";
import { sectionPath } from "@/lib/routes";
import { RingChart, TrendChart } from "./Chart";
import type { ChartPoint, ChartSeries } from "./Chart";
import styles from "./dashboard.module.css";

type Mode = "live" | "demo";
type Preset = 7 | 30 | 90 | "custom";
type TrendView = "activity" | "time" | "completion";

const palette = {
  blue: "var(--blue, #6094ff)",
  cyan: "var(--cyan, #3bd9eb)",
  violet: "var(--violet, #a58aff)",
  green: "var(--green, #53dfb2)",
  warning: "var(--warning, #f5be7c)",
  danger: "var(--danger, #ff829c)",
};

const trendSeries: Record<TrendView, ChartSeries[]> = {
  activity: [
    { key: "knowledge", label: "新增知识点", color: palette.violet, kind: "bar", unit: " 个" },
    { key: "reviews", label: "复习数量", color: palette.cyan, kind: "area", unit: " 次" },
  ],
  time: [
    { key: "studyMinutes", label: "学习时长", color: palette.blue, kind: "area", unit: " 分钟" },
  ],
  completion: [
    { key: "completionRate", label: "复习完成率", color: palette.cyan, kind: "area", axis: "percent" },
  ],
};

const trendTabs: Array<{ id: TrendView; label: string; unit?: string }> = [
  { id: "activity", label: "知识与复习", unit: "数量 · 项" },
  { id: "time", label: "学习时长", unit: "分钟" },
  { id: "completion", label: "完成率" },
];

const percent = (value: number) => `${value.toLocaleString("zh-CN", { maximumFractionDigits: 1 })}%`;
const integer = (value: number) => value.toLocaleString("zh-CN", { maximumFractionDigits: 0 });

function dateKey(date: Date, timeZone = "Asia/Shanghai") {
  const values = new Intl.DateTimeFormat("en-CA", {
    timeZone, year: "numeric", month: "2-digit", day: "2-digit",
  }).formatToParts(date);
  const lookup = Object.fromEntries(values.map(item => [item.type, item.value]));
  return `${lookup.year}-${lookup.month}-${lookup.day}`;
}

function makeRange(days: number, timeZone: string): DateRange {
  const to = dateKey(new Date(), timeZone);
  const from = new Date(`${to}T00:00:00.000Z`);
  from.setUTCDate(from.getUTCDate() - days + 1);
  return { from: from.toISOString().slice(0, 10), to };
}

function timeLabel(value: string | undefined, timeZone = "Asia/Shanghai") {
  if (!value) return "—";
  const time = new Date(value);
  return Number.isNaN(time.valueOf()) ? "—" : new Intl.DateTimeFormat("zh-CN", {
    timeZone, month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hourCycle: "h23",
  }).format(time);
}

function SourceBadge({ source }: { source: Resource<unknown>["source"] }) {
  const labels = { live: "真实数据", demo: "演示数据", unavailable: "待接入" };
  return <span className={`${styles.source} ${styles[source]}`}>{labels[source]}</span>;
}

function Panel({
  title,
  subtitle,
  source,
  action,
  children,
  className,
}: {
  title: string;
  subtitle?: string;
  source: Resource<unknown>["source"];
  action?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`${styles.panel} ${className ?? ""}`}>
      <div className={styles.panelHeader}>
        <div>
          <h2>{title}</h2>
          {subtitle && <p>{subtitle}</p>}
        </div>
        <div className={styles.panelTools}><SourceBadge source={source} />{action}</div>
      </div>
      {children}
    </section>
  );
}

function DataGap({ resource, label, loading }: { resource?: Resource<unknown>; label: string; loading: boolean }) {
  return (
    <div className={styles.dataGap}>
      <Activity size={24} aria-hidden="true" />
      <strong>{loading ? "正在读取…" : label}</strong>
      {!loading && resource?.message && <p>{resource.message}</p>}
    </div>
  );
}

function More({ section, mode, label }: { section: "jobs" | "monitoring" | "models"; mode: Mode; label: string }) {
  return <Link className={styles.more} href={sectionPath(section, mode === "demo")}>{label}<ArrowRight size={14} aria-hidden="true" /></Link>;
}

function LearningTrend({ item, loading }: { item?: DashboardData["learning"]; loading: boolean }) {
  const [metric, setMetric] = useState<TrendView>("activity");
  const days = item?.data ?? [];
  const data: ChartPoint[] = days.map(value => ({
    ...value, assigned: value.assigned ?? null, completed: value.completed ?? null,
  }));
  const hasMeasurements = metric !== "completion" || days.some(day => day.completionRate !== null);
  return (
    <Panel title="学习与复习趋势" subtitle="按日聚合的学习活动" source={item?.source ?? "unavailable"}>
      {data.length ? <>
        <div className={styles.smallTabs} role="group" aria-label="学习趋势指标">
          {trendTabs.map(tab => <button key={tab.id} type="button" aria-pressed={metric === tab.id} onClick={() => setMetric(tab.id)}>{tab.label}</button>)}
        </div>
        {hasMeasurements ? <TrendChart
          data={data}
          series={trendSeries[metric]}
          countUnit={trendTabs.find(tab => tab.id === metric)?.unit}
          label="学习与复习趋势"
          noteForPoint={metric === "completion" ? point =>
            typeof point.assigned === "number" && typeof point.completed === "number"
              ? `已完成 ${integer(point.completed)} / 已分派 ${integer(point.assigned)}`
              : undefined : undefined}
          height={224}
        /> : <DataGap label="该区间没有可计算完成率的任务" loading={loading} />}
        {item?.source === "live" && metric === "completion" && <p className={styles.chartNote}>按复习批次的本地日期统计。完成率为当前已完成任务占当日分派任务的比例，取消的任务不计入。</p>}
      </> : <DataGap resource={item} label={item?.data ? "该区间暂无学习活动" : "学习趋势暂不可用"} loading={loading} />}
    </Panel>
  );
}

function SubjectChart({ item, loading }: { item?: DashboardData["subjects"]; loading: boolean }) {
  const rows = item?.data ?? [];
  const sum = rows.reduce((value, row) => value + row.knowledge, 0);
  const live = item?.source === "live";
  const measured = rows.filter(row => row.mastery !== null && (live ? Boolean(row.recallSamples) : row.knowledge > 0));
  const sampleCount = measured.reduce((count, row) => count + (live ? row.recallSamples ?? 0 : row.knowledge), 0);
  const mastery = sampleCount ? measured.reduce((value, row) =>
    value + (row.mastery ?? 0) * (live ? row.recallSamples ?? 0 : row.knowledge), 0) / sampleCount : null;
  const weak = rows.some(row => row.weak !== null) ? rows.reduce((count, row) => count + (row.weak ?? 0), 0) : null;
  return (
    <Panel title="学科知识掌握度" subtitle={live ? "按活跃知识点数列出最多 12 个学科" : "按学科查看复习表现与薄弱点"} source={item?.source ?? "unavailable"}>
      {rows.length ? <>
        <div className={styles.masterySummary}>
          {mastery !== null && <RingChart value={Math.round(mastery)} label={live ? "样本回忆率" : "综合掌握"} size={100} />}
          <div>
            <strong>{integer(sum)}</strong><span>{live ? " 个所列学科的活跃知识点" : " 个知识点"}</span>
            <p>{weak === null ? "暂无薄弱点样本" : `${integer(weak)} 个薄弱知识点`}</p>
            {live && <p>{sampleCount ? `${integer(sampleCount)} 次复习评分` : "暂无回忆评分样本"}</p>}
          </div>
        </div>
        <div className={styles.subjectTableWrap}>
          <table className={styles.subjectTable}>
            <thead><tr><th scope="col">学科</th><th scope="col">知识点</th><th scope="col">复习完成率</th><th scope="col">{live ? "回忆率" : "掌握度"}</th><th scope="col">薄弱</th></tr></thead>
            <tbody>
              {rows.map((row, index) => (
                <tr key={row.id}>
                  <th scope="row"><i style={{ background: Object.values(palette)[index % Object.values(palette).length] }} />{row.name}</th>
                  <td>{integer(row.knowledge)}</td>
                  <td>{row.completionRate === null ? "—" : percent(row.completionRate)}</td>
                  <td>{row.mastery === null ? "—" : <span className={styles.masteryValue}><i aria-hidden="true"><i style={{ inlineSize: `${row.mastery}%` }} /></i>{percent(row.mastery)}</span>}</td>
                  <td>{row.weak === null ? "—" : integer(row.weak)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {live && <p className={styles.chartNote}>回忆率按「记得／熟练」评分占比计算。薄弱点以区间内最后一次评分为「忘记／困难」的活跃知识点计数。</p>}
      </> : <DataGap resource={item} label={item?.data ? "暂无活跃学科" : "学科复习数据暂不可用"} loading={loading} />}
    </Panel>
  );
}

const intervalNames: Record<string, string> = {
  D0: "0 天", D1: "1–2 天", D3: "3–6 天", D7: "7–13 天", D14: "14–20 天", D21: "21–29 天", D30: "30 天以上",
};

function RetentionChart({ item, loading }: { item?: DashboardData["retention"]; loading: boolean }) {
  const [subject, setSubject] = useState("");
  const values = item?.data ?? [];
  const live = item?.source === "live";
  const groupKey = (value: (typeof values)[number]) => value.subjectId ?? value.subject;
  const subjects = new Map(values.map(value => [groupKey(value), value.subject]));
  const selected = subjects.has(subject) ? subject : subjects.keys().next().value ?? "";
  const filtered = values.filter(value => groupKey(value) === selected);
  const data: ChartPoint[] = filtered.map(value => ({
    date: live ? intervalNames[value.stage] ?? value.stage : value.stage,
    predicted: value.predicted,
    observed: value.observed,
    sampleSize: value.sampleSize,
    predictionSampleSize: value.predictionSampleSize ?? null,
    predictionVersions: value.predictionVersions?.join("、") || null,
  }));
  return (
    <Panel
      title="记忆保持率"
      subtitle={live ? "按两次复习间隔对照 FSRS 预测与自评回忆率" : "按复习阶段对照 FSRS 预测与观察值"}
      source={item?.source ?? "unavailable"}
      action={subjects.size > 1 && <select aria-label="记忆保持率学科" value={selected} onChange={event => setSubject(event.target.value)}>
        {Array.from(subjects, ([value, name]) => <option value={value} key={value}>{name}</option>)}
      </select>}
    >
      {data.some(point => point.observed !== null || point.predicted !== null) ? <>
        <TrendChart
          label="FSRS 预测与复习表现"
          data={data}
          series={[
            { key: "observed", label: "复习观察值", color: palette.cyan, kind: "area", axis: "percent" },
            { key: "predicted", label: "FSRS 预测值", color: palette.violet, kind: "line", axis: "percent", dashed: true },
          ]}
          noteForPoint={point => {
            const observed = typeof point.sampleSize === "number" ? `观察样本 ${integer(point.sampleSize)} 次` : "";
            const predicted = typeof point.predictionSampleSize === "number" ? `预测样本 ${integer(point.predictionSampleSize)} 次` : "";
            return [observed, predicted, point.predictionVersions].filter(Boolean).join(" · ") || undefined;
          }}
          height={192}
        />
        <p className={styles.chartNote}>{live ? "虚线根据复习前的算法版本和记忆状态重放。实线来自用户自评，缺少样本的区间留空。" : "虚线为算法预测。观察值来自复习样本，缺少样本的阶段留空。"}</p>
      </> : <DataGap resource={item} label={item?.data ? "该区间暂无重复复习样本" : "记忆预测与观察数据暂不可用"} loading={loading} />}
    </Panel>
  );
}

const chapterStatus: Record<string, string> = {
  pending: "等待中", running: "运行中", blocked: "已阻塞", succeeded: "已成功", completed: "已完成", failed: "失败", cancelled: "已取消",
};

function JobsChart({ item, loading, mode }: { item?: DashboardData["jobs"]; loading: boolean; mode: Mode }) {
  const data = item?.data;
  const points: ChartPoint[] = (data?.days ?? []).map(day => ({
    ...day, partial: day.partial ?? null, durationSamples: day.durationSamples ?? null,
  }));
  const success = (data?.days ?? []).reduce((sum, value) => sum + value.success, 0);
  const failures = (data?.days ?? []).reduce((sum, value) => sum + value.failure, 0);
  const partial = (data?.days ?? []).reduce((sum, value) => sum + (value.partial ?? 0), 0);
  const total = success + failures + partial;
  const live = item?.source === "live";
  const series: ChartSeries[] = [
    { key: "success", label: "成功", color: palette.blue, kind: "bar", unit: " 次" },
    { key: "failure", label: "失败", color: palette.danger, kind: "line", unit: " 次" },
  ];
  if (live && points.length) series.push({ key: "partial", label: "部分成功", color: palette.warning, kind: "line", unit: " 次" });
  return (
    <Panel title="任务执行趋势" subtitle={live ? "按持久化完成记录统计" : "同步、提取、生成与通知"} source={item?.source ?? "unavailable"}>
      {points.length ? <>
        {total > 0 ? <TrendChart
          label={live ? "任务执行结果" : "任务成功与失败"}
          data={points}
          series={series}
          noteForPoint={point => typeof point.averageMs === "number" && typeof point.durationSamples === "number" ?
            `平均 ${integer(point.averageMs)} ms · 耗时样本 ${integer(point.durationSamples)} 次` : undefined}
          countUnit="数量 · 次"
          height={155}
        /> : <DataGap label="该区间暂无已记录的任务结果" loading={loading} />}
        <div className={styles.detailRow}>
          <span>成功率 <strong>{total ? percent(success * 100 / total) : "—"}</strong></span>
          <span>失败率 <strong>{total ? percent(failures * 100 / total) : "—"}</strong></span>
          {live && <span>部分成功 <strong>{integer(partial)} 次</strong></span>}
          <More section="jobs" mode={mode} label={live ? "任务汇总" : "任务明细"} />
        </div>
        <div className={styles.jobKinds}>{data?.kinds.map(row => (
          <div key={row.key ?? row.name}>
            <span>{row.name}</span>
            <strong>{row.averageMs === null ? "—" : `${integer(row.averageMs)} ms`}</strong>
            <small>{typeof row.durationSamples === "number" ? `平均耗时 · ${integer(row.durationSamples)} 个样本` : "平均耗时"}</small>
            {live && <small>成功 {integer(row.success)} · 失败 {integer(row.failure)} · 部分 {integer(row.partial ?? 0)}</small>}
          </div>
        ))}</div>
        {live && <p className={styles.chartNote}>按同步批次、章节处理、复习批次和通知投递尝试分别计数。耗时均值仅使用有记录的样本。</p>}
      </> : <DataGap resource={item} label={data ? "任务执行趋势暂未获取" : "任务执行数据暂不可用"} loading={loading} />}
      {data?.chapterStatus && live && <>
        <p className={styles.chartNote}>当前章节任务状态</p>
        <div className={styles.jobStatuses}>
          {Object.entries(data.chapterStatus).map(([status, count]) => <div key={status}><span>{chapterStatus[status] ?? status}</span><strong>{integer(count)}</strong></div>)}
          {!Object.keys(data.chapterStatus).length && <p>暂无已登记的章节提取任务。</p>}
        </div>
      </>}
    </Panel>
  );
}

function ResourceChart({ item, health, loading, mode }: { item?: DashboardData["resources"]; health?: DashboardData["health"]; loading: boolean; mode: Mode }) {
  const resources = item?.data;
  const service = health?.data;
  const readings: ChartPoint[] = (resources?.days ?? []).map(day => ({ ...day }));
  return (
    <Panel title="系统资源" subtitle={resources?.windowMinutes ? `最近 ${resources.windowMinutes} 分钟 · 当前 API 进程` : "主机遥测与服务就绪探针"} source={item?.source ?? "unavailable"}>
      {resources ? <>
        <div className={styles.resourceRings}>
          {[
            { value: resources.cpu, label: "CPU", color: palette.blue },
            { value: resources.memory, label: "内存", color: palette.cyan },
            { value: resources.disk, label: "磁盘", color: palette.violet },
          ].map(gauge => gauge.value === null ? <span key={gauge.label}>{gauge.label} —</span>
            : <RingChart key={gauge.label} value={gauge.value} label={gauge.label} color={gauge.color} size={85} />)}
        </div>
        <div className={styles.resourceFacts}>
          <div><span>API 响应时间</span><strong>{resources.latencyMs === null ? "—" : `${integer(resources.latencyMs)} ms`}</strong></div>
          <div><span>请求数量</span><strong>{integer(resources.requests)}</strong></div>
          <div><span>错误数量</span><strong>{integer(resources.errors)}</strong></div>
        </div>
        {readings.length > 1 && <div className={styles.resourceHistory}>
          <TrendChart
            label={mode === "live" ? "API 请求趋势" : "主机资源使用率趋势"}
            data={readings}
            series={mode === "live" ? [
              { key: "requests", label: "请求", color: palette.blue, kind: "bar" },
              { key: "errors", label: "错误", color: palette.violet, kind: "line" },
            ] : [
              { key: "cpu", label: "CPU", color: palette.blue, kind: "line", axis: "percent" },
              { key: "memory", label: "内存", color: palette.cyan, kind: "line", axis: "percent" },
              { key: "disk", label: "磁盘", color: palette.violet, kind: "line", axis: "percent" },
            ]}
            height={128}
          />
        </div>}
      </> : <DataGap resource={item} label="主机遥测接口待接入" loading={loading} />}
      <div className={styles.serviceStatus}>
        <span><Database size={15} aria-hidden="true" />数据库 <b>{service ? service.database === "ready" ? "就绪" : "不可用" : "待确认"}</b></span>
        <SourceBadge source={health?.source ?? "unavailable"} />
        <More section="monitoring" mode={mode} label="监控详情" />
      </div>
    </Panel>
  );
}

export function AiChart({ item, loading, mode }: { item?: DashboardData["ai"]; loading: boolean; mode: Mode }) {
  const values = item?.data;
  const [selected, setSelected] = useState<"calls" | "tokens" | "cost">("calls");
  const data: ChartPoint[] = (values?.days ?? []).map(value => ({ ...value }));
  const live = item?.source === "live";
  const total = (values?.days ?? []).reduce((sum, row) => sum + (row.terminalCalls ?? row.calls), 0);
  const errors = (values?.days ?? []).reduce((sum, row) => sum + row.errors, 0);
  const tokenSamples = (values?.days ?? []).reduce((sum, row) => sum + (row.tokenSamples ?? 0), 0);
  const tabs = [
    { id: "calls", label: "调用", unit: "次数" },
    { id: "tokens", label: "Token", unit: "Token" },
    { id: "cost", label: "费用", unit: values?.currency ?? "费用" },
  ] as const;
  const visibleTabs = tabs.filter(tab => !live || tab.id !== "cost");
  const meta = tabs.find(tab => tab.id === selected) ?? tabs[0];
  return (
    <Panel title="AI 模型调用" subtitle={live ? "已记录的调用、Token 与失败率" : "用量、费用与错误率"} source={item?.source ?? "unavailable"}>
      {data.length ? <>
        <div className={styles.smallTabs} role="group" aria-label="模型用量指标">
          {visibleTabs.map(tab => <button type="button" key={tab.id} onClick={() => setSelected(tab.id)} aria-pressed={tab.id === selected}>{tab.label}</button>)}
        </div>
        <TrendChart data={data} label="AI 模型调用趋势" countUnit={meta.unit} height={148} series={[{ key: meta.id, label: meta.label, color: palette.violet, kind: "area", unit: ` ${meta.unit}` }]} />
        <div className={styles.detailRow}><span>错误率 <strong>{total ? percent(errors * 100 / total) : "—"}</strong></span><More section="models" mode={mode} label="模型分析" /></div>
        {live && <p className={styles.chartNote}>失败率以已结束调用为分母。Token 实测样本 {integer(tokenSamples)} 条，缺失值留空。费用待账单接入。</p>}
        <div className={styles.modelMix}>
          {([["模型占比", values?.models ?? []], ["任务用途占比", values?.tasks ?? []]] as const).map(([group, rows]) => {
            const all = rows.reduce((sum, row) => sum + row.value, 0);
            return <div key={group}><h3>{group}</h3>{rows.map(row => <div key={row.name}><span>{row.name}</span><strong>{all ? percent(row.value * 100 / all) : "—"}</strong></div>)}</div>;
          })}
        </div>
      </> : <DataGap resource={item} label="AI 聚合用量接口待接入" loading={loading} />}
    </Panel>
  );
}

function ActivityList({ item, loading, timeZone }: { item?: DashboardData["activity"]; loading: boolean; timeZone: string }) {
  const rows = item?.data ?? [];
  return (
    <Panel title="最近系统活动" subtitle="按时间查看作业与审计事件" source={item?.source ?? "unavailable"}>
      {rows.length ? <ol className={styles.timeline}>
        {rows.slice(0, 6).map(row => (
          <li key={row.id} className={styles[row.severity]}>
            <span className={styles.eventDot} aria-hidden="true" />
            <div><strong>{row.label}</strong><p>{row.detail}</p></div>
            <time dateTime={row.time}>{timeLabel(row.time, timeZone)}</time>
          </li>
        ))}
      </ol> : item?.data ? <p className={styles.chartNote}>暂无系统活动。</p> : <DataGap resource={item} label="系统活动暂不可用" loading={loading} />}
    </Panel>
  );
}

export default function Dashboard({ mode, client, accountTimezone = "Asia/Shanghai" }: { mode: Mode; client: AdminClient; accountTimezone?: string }) {
  const [preset, setPreset] = useState<Preset>(30);
  const [range, setRange] = useState<DateRange>(() => makeRange(30, accountTimezone));
  const [custom, setCustom] = useState<DateRange>(range);
  const [customOpen, setCustomOpen] = useState(false);
  const [rangeError, setRangeError] = useState("");
  const [request, setRequest] = useState(0);
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError("");
    client.dashboard(range).then(value => {
      if (active) setData(value);
    }).catch(cause => {
      if (active) setError(cause instanceof Error ? cause.message : "无法读取管理员指标");
    }).finally(() => {
      if (active) setLoading(false);
    });
    return () => { active = false; };
  }, [client, range, request]);

  function selectRange(days: 7 | 30 | 90) {
    setPreset(days);
    setCustomOpen(false);
    setRangeError("");
    const next = makeRange(days, accountTimezone);
    if (next.from !== range.from || next.to !== range.to) setData(null);
    setRange(next);
  }

  function applyRange(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const from = Date.parse(`${custom.from}T00:00:00Z`);
    const to = Date.parse(`${custom.to}T00:00:00Z`);
    if (!Number.isFinite(from) || !Number.isFinite(to) || from > to || custom.from < "1970-01-01" || custom.to > today) {
      setRangeError("请选择 1970 年起至今天的有效日期，起始日期需早于或等于截止日期。");
      return;
    }
    if ((to - from) / 86_400_000 >= 366) {
      setRangeError("自定义区间最多 366 天。");
      return;
    }
    setRangeError("");
    setPreset("custom");
    if (custom.from !== range.from || custom.to !== range.to) setData(null);
    setRange({ ...custom });
    setCustomOpen(false);
  }

  const summary = data?.summary.data;
  const health = data?.health.data;
  const timeZone = data?.window?.timezone ?? summary?.timezone ?? accountTimezone;
  const displayedRange = data?.window ?? range;
  const today = dateKey(new Date(), timeZone);
  const metrics = [
    { label: "知识点总数", value: summary?.knowledgePoints, icon: Layers3, tone: "blue", note: "全部学科", unit: "项" },
    { label: "学科数量", value: summary?.subjects, icon: BookOpen, tone: "violet", note: "登记学科", unit: "个" },
    { label: "今日新增知识点", value: summary?.todayNew, icon: Plus, tone: "cyan", note: "当天创建", unit: "项" },
    { label: "今日待复习", value: summary?.todayDue, icon: Clock3, tone: "warning", note: mode === "live" ? "待办、进行中与已到期未排队" : "尚未完成", unit: "项" },
    { label: "今日已完成", value: summary?.todayCompleted, icon: CheckCircle2, tone: "green", note: "已提交复习", unit: "次" },
    { label: "AI 调用量", value: summary?.aiCalls, icon: BrainCircuit, tone: "violet", note: mode === "live" ? "当日记录调用" : "记录调用", unit: "次" },
  ];

  return (
    <div className={styles.dashboard}>
      <header className={styles.hero}>
        <div className={styles.heroContent}>
          <span className={styles.heroLabel}><Radio size={13} aria-hidden="true" /> 系统总览</span>
          <h1>系统运行总览</h1>
          <p>学习、记忆与后台服务的运行状态。</p>
        </div>
        <div className={styles.heroGraphic} aria-hidden="true"><div /><div /><div /><BrainCircuit size={45} strokeWidth={1.25} /></div>
        <span className={`${styles.healthPill} ${mode === "live" && health ? styles[health.status === "ready" ? "ready" : "unhealthy"] : ""}`}>
          <span />
          {mode === "demo" ? "演示环境" : loading && !health ? "检查服务" : health?.status === "ready" ? "API 与数据库已就绪" : health ? "服务未就绪" : "服务尚未确认"}
        </span>
      </header>

      <div className={styles.toolbar}>
        <div className={styles.snapshot}>
          <CalendarDays size={15} aria-hidden="true" />
          <span>趋势区间 <strong>{displayedRange.from} — {displayedRange.to}</strong></span>
          {summary?.asOf && <span className={styles.updated}>快照 {timeLabel(summary.asOf, timeZone)}</span>}
        </div>
        <div className={styles.toolbarControls}>
          <div className={styles.rangeTabs} role="group" aria-label="统计时间范围">
            {([7, 30, 90] as const).map(days => <button key={days} type="button" aria-pressed={preset === days} onClick={() => selectRange(days)}>近 {days} 天</button>)}
            <button type="button" aria-expanded={customOpen} aria-pressed={preset === "custom"} onClick={() => {
              setCustom({ ...range });
              setCustomOpen(previous => !previous);
              setRangeError("");
            }}>自定义</button>
          </div>
          <button className={styles.refresh} type="button" title="刷新数据" aria-label="刷新数据" disabled={loading} onClick={() => setRequest(value => value + 1)}><RefreshCw size={16} aria-hidden="true" /></button>
        </div>
      </div>
      {customOpen && <form className={styles.rangeForm} onSubmit={applyRange}>
        <label>开始日期<input type="date" required min="1970-01-01" max={custom.to || today} value={custom.from} onChange={event => setCustom(value => ({ ...value, from: event.target.value }))} /></label>
        <label>结束日期<input type="date" required min={custom.from || "1970-01-01"} max={today} value={custom.to} onChange={event => setCustom(value => ({ ...value, to: event.target.value }))} /></label>
        <button type="submit">应用范围</button>
        {rangeError && <p role="alert">{rangeError}</p>}
      </form>}
      {error && <p className={styles.error} role="alert"><CircleAlert size={16} aria-hidden="true" />{error}</p>}

      <section className={styles.metrics} aria-label="系统关键指标" aria-busy={loading}>
        {metrics.map(metric => (
          <article key={metric.label} className={`${styles.metric} ${styles[metric.tone]}`}>
            <div className={styles.metricTop}><span className={styles.metricIcon}><metric.icon size={17} aria-hidden="true" /></span><span>{metric.label}</span></div>
            <strong>{metric.value == null ? "—" : integer(metric.value)}{metric.value != null && <small>{metric.unit}</small>}</strong>
            <span className={styles.metricFoot}>{metric.value == null ? loading ? "读取中" : "指标待接入" : metric.note}</span>
          </article>
        ))}
      </section>

      <div className={styles.mainGrid} aria-busy={loading}>
        <LearningTrend item={data?.learning} loading={loading} />
        <SubjectChart item={data?.subjects} loading={loading} />
      </div>
      <div className={styles.secondaryGrid}>
        <RetentionChart item={data?.retention} loading={loading} />
        <JobsChart item={data?.jobs} loading={loading} mode={mode} />
        {data?.workflow && <Panel title="知识自动整理" source="live">
          <div className={styles.jobStatuses}>
            {[
              ["区间导入原文版本", data.workflow.imported_versions],
              ["区间 AI 整理知识点", data.workflow.generated_points],
              ["同步等待或处理中", data.workflow.sync_queued],
              ["提取等待或处理中", data.workflow.extraction_queued],
              ["提取阻塞", data.workflow.extraction_blocked],
              ["待发送或发送中", data.workflow.notification_queued],
            ].map(([label, value]) => <div key={label}><span>{label}</span><strong>{value}</strong></div>)}
          </div>
        </Panel>}
      </div>
      <div className={styles.tertiaryGrid}>
        <ResourceChart item={data?.resources} health={data?.health} loading={loading} mode={mode} />
        <AiChart item={data?.ai} loading={loading} mode={mode} />
        <ActivityList item={data?.activity} loading={loading} timeZone={timeZone} />
      </div>
      <footer className={styles.footer}><Server size={14} aria-hidden="true" /><span>AI Learning Memory OS</span><i /><span>{mode === "demo" ? "演示快照" : `统计时区 ${timeZone}`}</span><Workflow size={14} aria-hidden="true" /></footer>
    </div>
  );
}
