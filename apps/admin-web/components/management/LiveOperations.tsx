"use client";

import { useCallback, useEffect, useState } from "react";
import type { FormEvent, ReactNode } from "react";
import { AiChart } from "@/components/dashboard/Dashboard";
import { RingChart, TrendChart } from "@/components/dashboard/Chart";
import type { AdminClient, Page } from "@/lib/client";
import type {
  AdminOperations, Channel, Policy, PolicyParameters, Provider, Simulation, Source, Strategy,
} from "@/lib/operations";
import { Badge, Dialog, Field, FormFooter, Message, Panel, Table, formatTime } from "./ui";
import type { Feedback } from "./ui";
import styles from "./management.module.css";

const codeLabels: Record<string, string> = {
  pending: "待处理", blocked: "等待配置", running: "运行中", succeeded: "成功",
  success: "成功", failed: "失败", cancelled: "已取消", partial: "部分完成",
  ready: "已生成", completed: "已完成", sent: "已提交服务商", sending: "发送中",
  queued: "已排队", configured: "已配置", disabled: "已停用", unavailable: "不可用",
  paused: "已暂停", not_configured: "未配置", key_missing: "缺少密钥",
  billing_paused: "计费未放行", configuration_invalid: "配置有误", owner_inactive: "账户停用",
  notion: "Notion 同步", chapter: "章节知识提取", review_batch: "复习批次",
  notification: "通知作业", confirmed: "已确认送达", unconfirmed: "尚未确认送达",
};
const label = (value?: string | null) => value ? codeLabels[value] ?? value : "—";
const yes = (value?: boolean | null) => value === true ? "是" : value === false ? "否" : "—";
const stamp = (value?: string | null) => formatTime(value ?? "");
const count = (value?: number | null) => value == null ? "—" : value.toLocaleString("zh-CN");
const errorText = (error: unknown) => error instanceof Error ? error.message : "操作失败，请重试。";
const strategyName = (strategy: Strategy) => strategy === "fsrs" ? "FSRS" : "艾宾浩斯固定间隔";

function useLoad<T>(read: () => Promise<T>) {
  const [version, setVersion] = useState(0);
  const [state, setState] = useState<{ data?: T; feedback: Feedback | null; busy: boolean }>({ feedback: null, busy: true });
  useEffect(() => {
    let active = true;
    setState({ feedback: null, busy: true });
    void read().then(
      data => { if (active) setState({ data, feedback: null, busy: false }); },
      error => { if (active) setState({ feedback: { text: errorText(error), error: true }, busy: false }); },
    );
    return () => { active = false; };
  }, [read, version]);
  return { ...state, reload: () => setVersion(value => value + 1) };
}

function useAction() {
  const [busy, setBusy] = useState(false);
  const [feedback, setFeedback] = useState<Feedback | null>(null);
  async function run<T>(operation: () => Promise<T>, success: (data: T) => string) {
    setBusy(true);
    setFeedback(null);
    try {
      const data = await operation();
      setFeedback({ text: success(data), error: false });
    } catch (error) {
      setFeedback({ text: errorText(error), error: true });
    } finally {
      setBusy(false);
    }
  }
  return { busy, feedback, run };
}

function Loading({ busy, feedback }: { busy: boolean; feedback: Feedback | null }) {
  return <><Message feedback={feedback} />{busy && <p className={styles.dimText} role="status">读取后端数据中…</p>}</>;
}

function Rows<T>({ data, columns, row, empty }: {
  data?: Page<T>; columns: string[]; row: (record: T) => ReactNode; empty: string;
}) {
  if (!data) return null;
  if (!data.items.length) return <p className={styles.dimText}>{empty}</p>;
  return <Table columns={columns}>{data.items.map(row)}</Table>;
}

function Pages({ cursor, data, onChange }: {
  cursor?: string; data?: { next_cursor: string | null; has_more: boolean }; onChange: (cursor?: string) => void;
}) {
  if (!cursor && !data?.next_cursor) return null;
  return <div className={styles.panelFooter}>
    {cursor && <button type="button" className={styles.secondary} onClick={() => onChange()}>回到第一页</button>}
    {data?.has_more && data.next_cursor && <button type="button" className={styles.secondary}
      onClick={() => onChange(data.next_cursor ?? undefined)}>下一页</button>}
  </div>;
}

function Models({ api }: { api: AdminOperations }) {
  const [cursor, setCursor] = useState<string>();
  const [readiness, setReadiness] = useState<Provider>();
  const state = useLoad(useCallback(() => api.providers({ cursor, limit: 20 }), [api, cursor]));
  const usage = useLoad(useCallback(() => api.aiUsage(), [api]));
  const action = useAction();
  const update = (model: Provider, patch: Parameters<AdminOperations["updateProvider"]>[2]) =>
    void action.run(() => api.updateProvider(model.id, model.version, patch), result => {
      state.reload();
      return result.name + "已更新。";
    });

  return <>
    <Panel title="已配置模型" subtitle="查看学习者在各自工作区保存的模型。此处可启停或设为其默认模型。">
      <Loading {...state} />
      <Message feedback={action.feedback} />
      <Rows data={state.data} columns={["模型", "所属用户", "服务与域名", "状态", "操作"]} empty="暂无模型配置。"
        row={model => <tr key={model.id}>
          <td><strong>{model.name}</strong><br /><small>{model.model_name}</small></td>
          <td>{model.user_name}</td><td>{model.provider}<br /><small>{model.endpoint_host ?? "—"}</small></td>
          <td>{label(model.configuration_status)}{model.is_default && <> · 默认</>}</td>
          <td><div className={styles.rowActions}>
            <button type="button" className={styles.secondary} disabled={action.busy}
              onClick={() => void action.run(() => api.providerReadiness(model.id), result => {
                setReadiness(result);
                return "已检查本地配置。";
              })}>检查配置</button>
            <button type="button" className={styles.secondary} disabled={action.busy}
              onClick={() => update(model, { is_enabled: !model.is_enabled })}>{model.is_enabled ? "停用" : "启用"}</button>
            {model.is_enabled && !model.is_default && <button type="button" className={styles.secondary} disabled={action.busy}
              onClick={() => update(model, { is_default: true })}>设为默认</button>}
          </div></td>
        </tr>} />
      <Pages cursor={cursor} data={state.data} onChange={setCursor} />
    </Panel>
    <Message feedback={usage.feedback} />
    <AiChart item={usage.data} loading={usage.busy} mode="live" />
    {readiness && <Dialog title="模型配置检查" onClose={() => setReadiness(undefined)}>
      <dl className={styles.form}>
        <div><dt>检查结果</dt><dd>{label(readiness.configuration_status)}</dd></div>
        <div><dt>密钥已配置</dt><dd>{yes(readiness.key_configured)}</dd></div>
        <div><dt>系统允许计费</dt><dd>{yes(readiness.global_billing_approved)}</dd></div>
        <div><dt>用户允许计费</dt><dd>{yes(readiness.user_billing_approved)}</dd></div>
      </dl>
      <p className={styles.dimText}>仅验证本地配置，尚未向模型供应商发送请求。</p>
    </Dialog>}
  </>;
}

function SourceRuns({ api, source, onClose }: { api: AdminOperations; source: Source; onClose: () => void }) {
  const [cursor, setCursor] = useState<string>();
  const state = useLoad(useCallback(() => api.sourceRuns(source.id, { cursor }), [api, source.id, cursor]));
  return <Dialog title={source.name + "的同步历史"} onClose={onClose} wide>
    <Loading {...state} />
    <Rows data={state.data} columns={["创建时间", "状态", "处理条数", "导入条数", "失败条数", "错误代码"]}
      empty="该资料库暂无同步记录。" row={item => <tr key={item.id}>
        <td>{stamp(item.created_at)}</td><td>{label(item.status)}</td><td>{count(item.items_seen)}</td>
        <td>{count(item.items_imported)}</td><td>{count(item.items_failed)}</td><td>{item.error_code ?? "—"}</td>
      </tr>} />
    <Pages cursor={cursor} data={state.data} onChange={setCursor} />
  </Dialog>;
}

function Sources({ api }: { api: AdminOperations }) {
  const [cursor, setCursor] = useState<string>();
  const [history, setHistory] = useState<Source>();
  const [queue, setQueue] = useState<{ source: Source; key: string }>();
  const state = useLoad(useCallback(() => api.sources({ cursor, limit: 20 }), [api, cursor]));
  const action = useAction();
  return <Panel title="Notion 资料库" subtitle="查看用户连接、最近同步结果和运行记录。手动操作将任务加入队列。">
    <Loading {...state} />
    <Message feedback={action.feedback} />
    <Rows data={state.data} columns={["资料库", "所属用户", "状态", "间隔", "最近同步", "本次导入 / 失败", "操作"]} empty="暂无 Notion 资料库。"
      row={source => <tr key={source.id}>
        <td><strong>{source.name}</strong><br /><small>{source.integration_name}</small></td><td>{source.owner_name}</td>
        <td>{!source.is_enabled || !source.integration_enabled ? "已停用" : !source.credential_configured ? "等待授权" : label(source.last_status === null ? "configured" : source.last_status)}</td>
        <td>{source.sync_interval_minutes} 分钟</td><td>{stamp(source.last_synced_at)}</td>
        <td>{count(source.items_imported)} / {count(source.items_failed)}</td>
        <td><div className={styles.rowActions}>
          <button type="button" className={styles.secondary} onClick={() => setHistory(source)}>同步历史</button>
          <button type="button" className={styles.secondary} disabled={!source.is_enabled || !source.integration_enabled || !source.credential_configured}
            onClick={() => setQueue({ source, key: crypto.randomUUID() })}>手动同步</button>
        </div></td>
      </tr>} />
    <Pages cursor={cursor} data={state.data} onChange={setCursor} />
    {history && <SourceRuns api={api} source={history} onClose={() => setHistory(undefined)} />}
    {queue && <Dialog title="排队同步" onClose={() => { if (!action.busy) setQueue(undefined); }}>
      <form className={styles.form} onSubmit={event => {
        event.preventDefault();
        void action.run(() => api.queueSource(queue.source.id, queue.key), result => {
          setQueue(undefined);
          state.reload();
          return "同步任务已登记，当前状态为" + label(result.status) + "。";
        });
      }}>
        <p>为「{queue.source.name}」登记同步任务。任务由后台 Worker 处理。</p>
        <Message feedback={action.feedback} />
        <FormFooter submit="确认排队" busy={action.busy} onClose={() => { if (!action.busy) setQueue(undefined); }} />
      </form>
    </Dialog>}
  </Panel>;
}

function Notifications({ api }: { api: AdminOperations }) {
  const [channelCursor, setChannelCursor] = useState<string>();
  const [deliveryCursor, setDeliveryCursor] = useState<string>();
  const [channel, setChannel] = useState<Channel>();
  const [status, setStatus] = useState("");
  const channels = useLoad(useCallback(() => api.channels({ cursor: channelCursor }), [api, channelCursor]));
  const deliveries = useLoad(useCallback(() => api.deliveries({
    cursor: deliveryCursor, channel_id: channel?.id, status: status || undefined,
  }), [api, channel, deliveryCursor, status]));
  return <>
    <Panel title="通知渠道" subtitle="查看用户启用的通知渠道与最近发送结果。">
      <Loading {...channels} />
      <Rows data={channels.data} columns={["渠道", "所属用户", "启用", "凭据已配置", "最近发送", "结果", "操作"]} empty="暂无通知渠道。"
        row={item => <tr key={item.id}>
          <td><strong>{item.name}</strong><br /><small>{item.channel_type}</small></td><td>{item.owner_name}</td>
          <td>{yes(item.is_enabled)}{item.is_default && <> · 默认</>}</td><td>{yes(item.credential_configured)}</td>
          <td>{stamp(item.last_attempted_at)}</td><td>{label(item.last_status)}</td>
          <td><button type="button" className={styles.secondary} onClick={() => { setChannel(item); setDeliveryCursor(undefined); }}>投递记录</button></td>
        </tr>} />
      <Pages cursor={channelCursor} data={channels.data} onChange={setChannelCursor} />
    </Panel>
    <Panel title="投递记录" subtitle={channel ? "按渠道查看 · " + channel.name : "全站投递尝试，分别显示服务商接收与实际送达。"} action={
      channel && <button type="button" className={styles.secondary} onClick={() => { setChannel(undefined); setDeliveryCursor(undefined); }}>显示全部渠道</button>
    }>
      <div className={styles.form}><Field label="投递状态"><select value={status} onChange={event => {
        setStatus(event.target.value); setDeliveryCursor(undefined);
      }}><option value="">全部</option><option value="sending">发送中</option><option value="sent">已提交</option><option value="failed">失败</option></select></Field></div>
      <Loading {...deliveries} />
      <Rows data={deliveries.data} columns={["渠道", "所属用户", "尝试时间", "结果", "服务商接收", "最终送达", "错误代码"]}
        empty="此范围内暂无投递记录。" row={item => <tr key={item.id}>
          <td>{item.channel_name}</td><td>{item.owner_name}</td><td>{stamp(item.attempted_at)}</td>
          <td>{label(item.status)}</td><td>{yes(item.provider_accepted)}</td>
          <td>{typeof item.final_delivery === "string" ? label(item.final_delivery) : yes(item.final_delivery)}</td>
          <td>{item.error_code ?? "—"}</td>
        </tr>} />
      <Pages cursor={deliveryCursor} data={deliveries.data} onChange={setDeliveryCursor} />
    </Panel>
  </>;
}

const defaultValues: PolicyParameters = { strategy: "fsrs", intervals_days: [1, 3, 7], target_retention: 0.9 };

function PolicyForm({ values, submit, busy, onSubmit, onCancel }: {
  values: PolicyParameters; submit: string; busy: boolean; onSubmit: (values: PolicyParameters) => void; onCancel?: () => void;
}) {
  const [strategy, setStrategy] = useState(values.strategy);
  const [error, setError] = useState<Feedback | null>(null);
  function submitForm(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const intervals = String(form.get("intervals") ?? "").split(",").map(value => Number(value.trim()));
    const retention = Number(form.get("retention")) / 100;
    if (!intervals.length || intervals.length > 20 || intervals.some(value => !Number.isFinite(value) || value <= 0 || value > 36500)
      || intervals.some((value, index) => index > 0 && value <= intervals[index - 1])) {
      setError({ text: "请用英文逗号分隔 1 至 20 个严格递增的间隔天数。", error: true });
      return;
    }
    if (!Number.isFinite(retention) || retention <= 0 || retention >= 1) {
      setError({ text: "目标记忆保持率须大于 0% 且小于 100%。", error: true });
      return;
    }
    setError(null);
    onSubmit({ strategy, intervals_days: intervals, target_retention: retention });
  }
  return <form className={styles.form} onSubmit={submitForm}>
    <Message feedback={error} />
    <Field label="复习策略"><select value={strategy} onChange={event => setStrategy(event.target.value as Strategy)}>
      <option value="fsrs">FSRS</option><option value="ebbinghaus">艾宾浩斯固定间隔</option>
    </select></Field>
    <Field label="固定间隔天数" hint="固定间隔算法使用此参数。多个间隔用英文逗号分隔。"><input name="intervals" defaultValue={values.intervals_days.join(", ")} required /></Field>
    <Field label="目标记忆保持率（%）" hint="FSRS 使用此参数。"><input name="retention" type="number" step="any" min="1" max="99.99" defaultValue={values.target_retention * 100} required /></Field>
    {onCancel ? <FormFooter submit={submit} busy={busy} onClose={onCancel} /> : <div className={styles.formFooter}>
      <button type="submit" className={styles.primary} disabled={busy}>{busy ? "运行中…" : submit}</button>
    </div>}
  </form>;
}

function Memory({ api }: { api: AdminOperations }) {
  const [cursor, setCursor] = useState<string>();
  const [edit, setEdit] = useState<Policy>();
  const [simulation, setSimulation] = useState<Simulation>();
  const state = useLoad(useCallback(() => api.policies({ cursor }), [api, cursor]));
  const action = useAction();
  const simulate = useAction();
  const defaults = state.data?.defaults;
  return <>
    <Panel title="默认记忆策略">
      <Loading {...state} />
      {defaults && <div className={styles.detailList}>
        <div><span>默认算法</span><strong>{strategyName(defaults.strategy)}</strong></div>
        <div><span>固定间隔</span><strong>{defaults.intervals_days.join("、")} 天</strong></div>
        <div><span>目标记忆保持率</span><strong>{count(defaults.target_retention * 100)}%</strong></div>
      </div>}
    </Panel>
    <Panel title="学科复习策略" subtitle="编辑已配置的策略，更新用于后续生成的新记忆计划。">
      <Message feedback={action.feedback} />
      <Rows data={state.data} columns={["学科", "所属用户", "复习策略", "固定间隔", "保持率", "操作"]} empty="暂无学科策略配置。"
        row={policy => <tr key={policy.id}><td>{policy.subject_name}</td><td>{policy.user_name}</td><td>{strategyName(policy.strategy)}</td>
          <td>{policy.intervals_days.join("、")} 天</td><td>{count(policy.target_retention * 100)}%</td>
          <td><button type="button" className={styles.secondary} onClick={() => setEdit(policy)}>调整策略</button></td></tr>} />
      <Pages cursor={cursor} data={state.data} onChange={setCursor} />
    </Panel>
    {edit && <Dialog title={"调整策略 · " + edit.subject_name} onClose={() => { if (!action.busy) setEdit(undefined); }}>
      <Message feedback={action.feedback} />
      <PolicyForm values={edit} submit="保存策略" busy={action.busy} onCancel={() => { if (!action.busy) setEdit(undefined); }}
        onSubmit={values => void action.run(() => api.updatePolicy(edit.id, edit.version, values), () => {
          setEdit(undefined); state.reload(); return "已保存策略。";
        })} />
    </Dialog>}
    <Panel title="算法模拟" subtitle="按固定示例评分计算未来复习间隔，用户计划不受影响。">
      <Message feedback={simulate.feedback} />
      <PolicyForm key={defaults ? "loaded" : "fallback"} values={defaults ?? defaultValues} submit="运行模拟" busy={simulate.busy}
        onSubmit={values => void simulate.run(() => api.simulate(values), result => { setSimulation(result); return "已生成模拟结果。"; })} />
      {simulation && <>
        <p className={styles.dimText}>算法版本 {simulation.algorithm_version}</p>
        <Table columns={["次数", "评分", "复习日期", "下次复习", "间隔天数", "稳定性"]}>
          {simulation.steps.map(step => <tr key={step.review_count}>
            <td>{step.review_count}</td><td>{{ again: "重来", hard: "困难", good: "记得", easy: "简单" }[step.rating]}</td>
            <td>{stamp(step.reviewed_at)}</td><td>{stamp(step.due_at)}</td><td>{count(step.interval_days)}</td><td>{count(step.stability)}</td>
          </tr>)}
        </Table>
      </>}
    </Panel>
  </>;
}

function Jobs({ api }: { api: AdminOperations }) {
  const [cursor, setCursor] = useState<string>();
  const [kind, setKind] = useState("");
  const [status, setStatus] = useState("");
  const state = useLoad(useCallback(() => api.jobs({ cursor, kind: kind || undefined, status: status || undefined }), [api, cursor, kind, status]));
  return <Panel title="实际任务记录" subtitle="读取统一后端保存的后台任务和复习批次。" action={
    <button type="button" className={styles.secondary} disabled={state.busy} onClick={state.reload}>刷新任务</button>
  }>
    <div className={styles.form}>
      <Field label="任务类型"><select value={kind} onChange={event => { setKind(event.target.value); setCursor(undefined); }}>
        <option value="">全部</option>{["notion", "chapter", "review_batch", "notification"].map(value =>
          <option key={value} value={value}>{label(value)}</option>)}
      </select></Field>
      <Field label="执行状态"><select value={status} onChange={event => { setStatus(event.target.value); setCursor(undefined); }}>
        <option value="">全部</option>{["pending", "running", "blocked", "succeeded", "sent", "completed", "failed", "cancelled"].map(value =>
          <option key={value} value={value}>{label(value)}</option>)}
      </select></Field>
    </div>
    <Loading {...state} />
    <Rows data={state.data} columns={["任务", "类型", "所属用户", "状态", "创建时间", "完成时间", "下次尝试", "错误代码"]}
      empty="此范围内暂无任务。" row={job => <tr key={job.kind + job.id}>
        <td>{job.name}</td><td>{label(job.kind)}</td><td>{job.owner_name}</td><td>{label(job.status)}</td>
        <td>{stamp(job.created_at)}</td><td>{stamp(job.finished_at)}</td><td>{stamp(job.next_attempt_at)}</td><td>{job.error_code ?? "—"}</td>
      </tr>} />
    <Pages cursor={cursor} data={state.data} onChange={setCursor} />
  </Panel>;
}

function Monitoring({ api }: { api: AdminOperations }) {
  const [minutes, setMinutes] = useState(60);
  const telemetry = useLoad(useCallback(() => api.telemetry(minutes), [api, minutes]));
  const system = useLoad(useCallback(() => api.systemInfo(), [api]));
  const data = telemetry.data;
  return <>
    <Panel title="后台运行与资源采样" subtitle="主机资源为最新采样。请求、错误和延迟仅统计当前 API 进程。"
      action={<button type="button" className={styles.secondary} disabled={telemetry.busy || system.busy}
        onClick={() => { telemetry.reload(); system.reload(); }}>刷新运行指标</button>}>
      <Loading {...system} /><Loading {...telemetry} />
      {system.data && <div className={styles.detailList}>
        <div><span>后台 Worker</span><Badge tone={system.data.worker === "running" ? "ok" : "planned"}>{label(system.data.worker)}</Badge></div>
        <div><span>Redis</span><strong>{label(system.data.redis)}</strong></div>
        <div><span>后端启动</span><strong>{stamp(system.data.started_at)}</strong></div>
      </div>}
      {data && <div className={styles.rings}>
        {([
          ["CPU", data.cpu, "var(--cyan)"],
          ["内存", data.memory, "var(--blue)"],
          ["磁盘", data.disk, "var(--violet)"],
        ] as const).map(([name, value, color]) => value === null ? <p className={styles.dimText} key={name}>{name} 暂无采样</p> :
          <RingChart key={name} label={name} value={value} color={color} size={100} />)}
      </div>}
    </Panel>
    <Panel title="API 请求趋势">
      <div className={styles.form}><Field label="统计窗口"><select value={minutes} onChange={event => setMinutes(Number(event.target.value))}>
        <option value={15}>近 15 分钟</option><option value={60}>近 60 分钟</option><option value={1440}>近 24 小时</option>
      </select></Field></div>
      {data && <>
        <div className={styles.detailList}>
          <div><span>请求数</span><strong>{count(data.requests)}</strong></div>
          <div><span>服务端 5xx 错误</span><strong>{count(data.errors)}</strong></div>
          <div><span>平均延迟</span><strong>{data.latency_ms === null ? "—" : count(data.latency_ms) + " ms"}</strong></div>
          <div><span>近似 P95 延迟</span><strong>{data.p95_latency_ms === null ? "—" : count(data.p95_latency_ms) + " ms"}</strong></div>
        </div>
        {data.buckets.length ? <TrendChart label="API 请求趋势" data={data.buckets.map(row => ({
          ...row, date: stamp(row.date),
        }))} height={205} series={[
          { key: "requests", label: "请求数", color: "var(--blue)", kind: "bar", unit: " 次" },
          { key: "errors", label: "错误数", color: "var(--danger)", kind: "line", unit: " 次" },
        ]} /> : <p className={styles.dimText}>此窗口暂无已完成请求。</p>}
      </>}
    </Panel>
  </>;
}

export function LiveBackups({ api }: { api: AdminOperations }) {
  const [key, setKey] = useState<string>();
  const system = useLoad(useCallback(() => api.systemInfo(), [api]));
  const backup = useLoad(useCallback(() => api.backups(), [api]));
  const action = useAction();
  return <Panel title="系统信息与备份" subtitle="显示后端运行版本和服务器备份目录中的归档。">
    <Loading {...system} /><Loading {...backup} />
    <Message feedback={action.feedback} />
    {system.data && <div className={styles.detailList}>
      <div><span>后端版本</span><strong>{system.data.version}</strong></div>
      <div><span>后端启动</span><strong>{stamp(system.data.started_at)}</strong></div>
      <div><span>后台 Worker</span><strong>{label(system.data.worker)}</strong></div>
    </div>}
    {backup.data && <div className={styles.panelFooter}>
      <button type="button" className={styles.secondary} disabled={!backup.data.enabled || action.busy}
        onClick={() => setKey(crypto.randomUUID())}>创建备份</button>
      {!backup.data.enabled && <span className={styles.dimText}>服务器备份功能尚未配置。</span>}
    </div>}
    {backup.data?.enabled && (backup.data.items.length ? <Table columns={["归档", "创建时间", "大小"]}>
      {backup.data.items.map(item => <tr key={item.id}><td>{item.filename}</td><td>{stamp(item.created_at)}</td><td>{count(item.size_bytes)} B</td></tr>)}
    </Table> : <p className={styles.dimText}>暂无数据库备份。</p>)}
    {key && <Dialog title="创建数据库备份" onClose={() => { if (!action.busy) setKey(undefined); }}>
      <form className={styles.form} onSubmit={event => {
        event.preventDefault();
        void action.run(() => api.createBackup(key), item => {
          setKey(undefined); backup.reload(); return "已创建归档 " + item.filename;
        });
      }}>
        <p>将向服务器的私有备份目录写入新的 PostgreSQL 归档。</p>
        <Message feedback={action.feedback} />
        <FormFooter submit="确认创建" busy={action.busy} onClose={() => { if (!action.busy) setKey(undefined); }} />
      </form>
    </Dialog>}
  </Panel>;
}

export default function LiveOperations({ section, client }: {
  section: "models" | "sources" | "notifications" | "memory" | "jobs" | "monitoring";
  client: AdminClient;
}) {
  const api = client.operations;
  if (!api) return null;
  switch (section) {
    case "models": return <Models api={api} />;
    case "sources": return <Sources api={api} />;
    case "notifications": return <Notifications api={api} />;
    case "memory": return <Memory api={api} />;
    case "jobs": return <Jobs api={api} />;
    case "monitoring": return <Monitoring api={api} />;
  }
}

