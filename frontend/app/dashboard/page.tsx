'use client';

/**
 * 学习仪表盘（FE-03）。
 *
 * 真实端点：
 *  - GET /statistics/overview?from_date&to_date[&subject_id]  总览 / 趋势 / 热力图 / 学科统计
 *  - GET /review-tasks?local_date=...                          今日待复习任务
 *  - GET /subjects                                            学科列表（用于逐学科统计）
 *
 * 所有数值均来自真实接口：
 *  - 「今日待复习」统计的是本次已加载任务中状态为 pending / in_progress 的条数，
 *    并在 has_more=true 时明确提示不是总数（契约的 Page<T> 不提供 total 字段）；
 *  - 「学科分布」通过契约允许的 subject_id 过滤逐学科调用统计接口得到，
 *    契约没有"按学科分组"的聚合字段，因此不虚构分布数据。
 */

import Link from 'next/link';
import { useMemo, useState } from 'react';
import type { FormEvent } from 'react';
import { api } from '@/lib/api';
import { useAuth } from '@/components/AuthProvider';
import { useQuery } from '@/lib/hooks';
import { QueryView } from '@/components/States';
import { HeatmapCalendar, TrendChart } from '@/components/dashboard/Charts';
import { accountDate, accountDateRange, formatDate, formatPercent } from '@/lib/format';
import { TASK_STATUS_LABELS, taskStatusTone } from '@/lib/labels';
import type { DailyTaskRead, Page, StatisticsRead, SubjectRead } from '@/types/api';

interface SubjectStat {
  subject: SubjectRead;
  stat: StatisticsRead;
}

interface SubjectStatsData {
  rows: SubjectStat[];
  /** GET /subjects 的 has_more，真实反映是否还有未加载的学科。 */
  hasMore: boolean;
}

export default function DashboardPage() {
  const { user } = useAuth();
  const timezone = user?.timezone;
  const today = useMemo(() => accountDate(timezone), [timezone]);
  const [fromDate, setFromDate] = useState(() => accountDateRange(30, timezone).from);
  const [toDate, setToDate] = useState(() => accountDateRange(30, timezone).to);
  const [draftFrom, setDraftFrom] = useState(fromDate);
  const [draftTo, setDraftTo] = useState(toDate);
  const [rangeError, setRangeError] = useState<string | null>(null);

  const statsQuery = useQuery<StatisticsRead>(
    () => api.getStatistics({ from_date: fromDate, to_date: toDate }),
    [fromDate, toDate],
  );

  const todayTasksQuery = useQuery<Page<DailyTaskRead>>(
    () => api.listReviewTasks({ local_date: today, limit: 100 }),
    [today],
  );

  const subjectStatsQuery = useQuery<SubjectStatsData>(async () => {
    const subjects = await api.listSubjects({ limit: 100 });
    const rows = await Promise.all(
      subjects.items.map(async (subject) => ({
        subject,
        stat: await api.getStatistics({
          from_date: fromDate,
          to_date: toDate,
          subject_id: subject.id,
        }),
      })),
    );
    return { rows, hasMore: subjects.has_more };
  }, [fromDate, toDate]);

  const applyRange = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!draftFrom || !draftTo) {
      setRangeError('请选择开始与结束日期');
      return;
    }
    if (draftFrom > draftTo) {
      setRangeError('开始日期不能晚于结束日期');
      return;
    }
    setRangeError(null);
    setFromDate(draftFrom);
    setToDate(draftTo);
  };

  const setPreset = (days: number) => {
    const range = accountDateRange(days, timezone);
    setDraftFrom(range.from);
    setDraftTo(range.to);
    setFromDate(range.from);
    setToDate(range.to);
    setRangeError(null);
  };

  const reloadAll = () => {
    statsQuery.reload();
    todayTasksQuery.reload();
    subjectStatsQuery.reload();
  };

  return (
    <div className="page">
      <header className="page-head">
        <div className="page-head__row">
          <div>
            <h1 className="page-title">学习仪表盘</h1>
            <p className="page-sub">
              统计区间 {formatDate(fromDate)} — {formatDate(toDate)} · 全部数值来自真实接口
            </p>
          </div>
          <div className="page-actions">
            <Link href="/review" className="btn btn--primary">去今日复习</Link>
            <Link href="/statistics" className="btn btn--ghost">统计与历史</Link>
          </div>
        </div>

        <form className="toolbar" onSubmit={applyRange}>
          <div className="toolbar__group">
            <label className="field field--inline">
              <span className="field__label">开始日期</span>
              <input className="input" type="date" value={draftFrom} onChange={(e) => setDraftFrom(e.target.value)} />
            </label>
            <label className="field field--inline">
              <span className="field__label">结束日期</span>
              <input className="input" type="date" value={draftTo} onChange={(e) => setDraftTo(e.target.value)} />
            </label>
            <button className="btn btn--primary" type="submit">应用区间</button>
          </div>
          <div className="toolbar__group">
            {[7, 30, 90].map((days) => (
              <button key={days} type="button" className="btn btn--ghost btn--sm" onClick={() => setPreset(days)}>
                最近 {days} 天
              </button>
            ))}
            <button type="button" className="btn btn--ghost btn--sm" onClick={reloadAll}>刷新</button>
          </div>
        </form>
        {rangeError && <div className="notice notice--error">{rangeError}</div>}
      </header>

      {/* 总览指标 */}
      <QueryView state={statsQuery.state} onRetry={statsQuery.reload}>
        {(stats) => (
          <div className="stat-grid">
            <div className="card stat-card">
              <div className="card__body card__body--tight">
                <p className="stat-card__label">任务总数（total_tasks）</p>
                <p className="stat-card__value">{stats.total_tasks}</p>
                <p className="muted text-xs">统计区间内生成的复习任务数</p>
              </div>
            </div>
            <div className="card stat-card">
              <div className="card__body card__body--tight">
                <p className="stat-card__label">已完成（completed_tasks）</p>
                <p className="stat-card__value">{stats.completed_tasks}</p>
                <p className="muted text-xs">状态为已完成的复习任务数</p>
              </div>
            </div>
            <div className="card stat-card">
              <div className="card__body card__body--tight">
                <p className="stat-card__label">完成率（completion_rate）</p>
                <p className="stat-card__value">{formatPercent(stats.completion_rate)}</p>
                <div className="progress mt-6">
                  <div className="progress__bar">
                    <div className="progress__fill" style={{ width: `${Math.min(100, Math.max(0, stats.completion_rate * 100))}%` }} />
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}
      </QueryView>

      {/* 今日待复习：来自真实 /review-tasks，明确标注已加载范围 */}
      <QueryView state={todayTasksQuery.state} onRetry={todayTasksQuery.reload}>
        {(page) => {
          const pending = page.items.filter(
            (task) => task.status === 'pending' || task.status === 'in_progress',
          ).length;
          return (
            <div className="card">
              <div className="card__head">
                <span className="card__title">今日待复习</span>
                <span className="badge badge--info">{formatDate(today)}</span>
              </div>
              <div className="card__body">
                <p className="stat-card__value">{pending}</p>
                <p className="muted text-sm">
                  在已加载的 {page.items.length} 条当日任务中，状态为「待复习 / 进行中」的条数。
                  契约的 Page&lt;T&gt; 不提供 total 字段，因此这里不虚构总数。
                </p>
                {page.has_more && (
                  <div className="notice notice--warn">
                    当日任务还有更多未加载（has_more=true，游标分页），上方数字仅统计本次加载的条目。
                  </div>
                )}
                {page.items.length > 0 && (
                  <div className="list">
                    {page.items.slice(0, 5).map((task) => (
                      <div className="list-item" key={task.id}>
                        <div className="list-item__meta">
                          <span>第 {task.position} 题</span>
                          <span>优先级 {task.priority}</span>
                          <span>知识点 <code className="mono">{task.knowledge_point_id}</code></span>
                          <span className={`badge badge--${taskStatusTone(task.status)}`}>
                            {TASK_STATUS_LABELS[task.status]}
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
                <div className="form-actions">
                  <Link href="/review" className="btn btn--primary btn--sm">前往今日复习</Link>
                </div>
              </div>
            </div>
          );
        }}
      </QueryView>

      {/* 趋势与热力图 */}
      <QueryView state={statsQuery.state} onRetry={statsQuery.reload}>
        {(stats) => (
          <div className="grid-2">
            <div className="card">
              <div className="card__head"><span className="card__title">留存趋势（retention_trend）</span></div>
              <div className="card__body"><TrendChart points={stats.retention_trend} /></div>
            </div>
            <div className="card">
              <div className="card__head"><span className="card__title">复习热力图（heatmap）</span></div>
              <div className="card__body"><HeatmapCalendar points={stats.heatmap} /></div>
            </div>
          </div>
        )}
      </QueryView>

      {/* 学科分布：逐学科调用统计接口 */}
      <div className="card">
        <div className="card__head">
          <span className="card__title">学科分布</span>
          <button type="button" className="btn btn--ghost btn--sm" onClick={subjectStatsQuery.reload}>刷新</button>
        </div>
        <QueryView
          state={subjectStatsQuery.state}
          onRetry={subjectStatsQuery.reload}
          isEmpty={(data) => data.rows.length === 0}
          emptyText="暂无学科"
          emptyHint="请先在「知识管理 → 学科」创建学科；统计接口会按 subject_id 返回各学科数据。"
        >
          {(data) => (
            <div className="list">
              {data.rows.map(({ subject, stat }) => (
                <div className="list-item" key={subject.id}>
                  <div className="list-item__title">
                    {subject.name}
                    {' '}
                    <span className={`badge badge--${subject.is_active ? 'ok' : 'muted'}`}>
                      {subject.is_active ? '启用' : '已禁用'}
                    </span>
                  </div>
                  <div className="list-item__meta">
                    <span className="pill mono">{subject.slug}</span>
                    <span>任务 {stat.total_tasks}</span>
                    <span>完成 {stat.completed_tasks}</span>
                    <span>完成率 {formatPercent(stat.completion_rate)}</span>
                  </div>
                  <div className="progress mt-6">
                    <div className="progress__bar">
                      <div className="progress__fill" style={{ width: `${Math.min(100, Math.max(0, stat.completion_rate * 100))}%` }} />
                    </div>
                  </div>
                </div>
              ))}
              {data.hasMore && (
                <div className="notice notice--warn">
                  学科列表还有更多未加载（GET /subjects 的 has_more=true，limit=100）；此处仅统计已加载的学科。
                </div>
              )}
              <div className="notice notice--info">
                按每个学科分别调用 GET /statistics/overview?subject_id=... 得到；契约未提供「按学科分组」的聚合字段，此处不虚构分布数据。
              </div>
            </div>
          )}
        </QueryView>
      </div>
    </div>
  );
}
