'use client';

/**
 * 学习统计与历史追踪（FE-06 / FR-09）。
 *
 * 真实端点：
 *  - GET /review-history   按 knowledge_point_id / subject_id / from / to / rating 筛选，
 *                           严格使用契约的 Page<T>（items / next_cursor / has_more）做游标分页，不用 offset。
 *  - GET /statistics/overview  同区间总览、留存趋势、热力图。
 *  - GET /subjects             学科筛选下拉。
 *
 * 历史条目可下钻到知识点详情；所有数据来自真实接口，空/错误/加载中状态如实反映。
 */

import Link from 'next/link';
import { useMemo, useState } from 'react';
import type { FormEvent } from 'react';
import { api } from '@/lib/api';
import { useQuery } from '@/lib/hooks';
import { QueryView } from '@/components/States';
import { HeatmapCalendar, TrendChart } from '@/components/dashboard/Charts';
import { formatDate, formatDateTime, formatPercent, localDateRange } from '@/lib/format';
import { RATING_LABELS, STRATEGY_LABELS } from '@/lib/labels';
import type {
  Page,
  ReviewHistoryRead,
  ReviewRating,
  StatisticsRead,
  SubjectRead,
} from '@/types/api';

interface Filters {
  knowledgePointId: string;
  subjectId: string;
  rating: ReviewRating | '';
  from: string;
  to: string;
}

const EMPTY_FILTERS: Filters = {
  knowledgePointId: '',
  subjectId: '',
  rating: '',
  from: '',
  to: '',
};

export default function StatisticsPage() {
  const defaultRange = useMemo(() => localDateRange(30), []);
  const [draft, setDraft] = useState<Filters>(EMPTY_FILTERS);
  const [applied, setApplied] = useState<Filters>(EMPTY_FILTERS);
  const [limit, setLimit] = useState(20);
  const [cursor, setCursor] = useState<string | null>(null);
  const [cursorStack, setCursorStack] = useState<(string | null)[]>([]);

  const subjectsQuery = useQuery<Page<SubjectRead>>(
    () => api.listSubjects({ limit: 100 }),
    [],
  );

  const historyQuery = useQuery<Page<ReviewHistoryRead>>(
    () =>
      api.listReviewHistory({
        knowledge_point_id: applied.knowledgePointId.trim() || undefined,
        subject_id: applied.subjectId || undefined,
        rating: applied.rating || undefined,
        from: applied.from || undefined,
        to: applied.to || undefined,
        limit,
        cursor: cursor || undefined,
      }),
    [
      applied.knowledgePointId,
      applied.subjectId,
      applied.rating,
      applied.from,
      applied.to,
      limit,
      cursor,
    ],
  );

  const statsFrom = applied.from || defaultRange.from;
  const statsTo = applied.to || defaultRange.to;
  const statsQuery = useQuery<StatisticsRead>(
    () =>
      api.getStatistics({
        from_date: statsFrom,
        to_date: statsTo,
        subject_id: applied.subjectId || undefined,
      }),
    [statsFrom, statsTo, applied.subjectId],
  );

  const applyFilters = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (draft.from && draft.to && draft.from > draft.to) {
      return;
    }
    setApplied({ ...draft });
    setCursor(null);
    setCursorStack([]);
  };

  const resetFilters = () => {
    setDraft({ ...EMPTY_FILTERS });
    setApplied({ ...EMPTY_FILTERS });
    setCursor(null);
    setCursorStack([]);
  };

  const goNext = (page: Page<ReviewHistoryRead>) => {
    if (!page.has_more || !page.next_cursor) return;
    setCursorStack((stack) => [...stack, cursor]);
    setCursor(page.next_cursor);
  };

  const goPrev = () => {
    if (cursorStack.length === 0) return;
    const previous = cursorStack[cursorStack.length - 1];
    setCursorStack((stack) => stack.slice(0, -1));
    setCursor(previous);
  };

  const subjectItems = subjectsQuery.state.status === 'success' ? subjectsQuery.state.data.items : [];

  return (
    <div className="page">
      <header className="page-head">
        <div className="page-head__row">
          <div>
            <h1 className="page-title">统计与复习历史</h1>
            <p className="page-sub">
              按知识点 / 学科 / 时间范围 / 掌握程度查询真实复习历史（FR-09）
            </p>
          </div>
          <div className="page-actions">
            <Link href="/dashboard" className="btn btn--ghost">返回仪表盘</Link>
          </div>
        </div>
        {subjectsQuery.state.status === 'error' && (
          <div className="notice notice--warn">学科下拉加载失败，可直接填写知识点 ID 或学科 ID 进行筛选。</div>
        )}
      </header>

      <div className="card">
        <div className="card__head"><span className="card__title">筛选条件</span></div>
        <div className="card__body">
          <form className="toolbar" onSubmit={applyFilters}>
            <div className="toolbar__group">
              <select
                className="select"
                value={draft.subjectId}
                onChange={(e) => setDraft({ ...draft, subjectId: e.target.value })}
                aria-label="按学科筛选"
              >
                <option value="">全部学科</option>
                {subjectItems.map((subject) => (
                  <option key={subject.id} value={subject.id}>{subject.name}</option>
                ))}
              </select>
              <select
                className="select"
                value={draft.rating}
                onChange={(e) => setDraft({ ...draft, rating: e.target.value as ReviewRating | '' })}
                aria-label="按掌握程度筛选"
              >
                <option value="">全部掌握程度</option>
                {(Object.keys(RATING_LABELS) as ReviewRating[]).map((value) => (
                  <option key={value} value={value}>{RATING_LABELS[value].label}</option>
                ))}
              </select>
            </div>
            <div className="toolbar__group">
              <input
                className="input"
                value={draft.knowledgePointId}
                onChange={(e) => setDraft({ ...draft, knowledgePointId: e.target.value })}
                placeholder="知识点 ID（UUID）"
                aria-label="按知识点 ID 筛选"
              />
              <label className="field field--inline">
                <span className="field__label">起始</span>
                <input className="input" type="date" value={draft.from} onChange={(e) => setDraft({ ...draft, from: e.target.value })} />
              </label>
              <label className="field field--inline">
                <span className="field__label">结束</span>
                <input className="input" type="date" value={draft.to} onChange={(e) => setDraft({ ...draft, to: e.target.value })} />
              </label>
            </div>
            <div className="toolbar__group">
              <label className="field field--inline">
                <span className="field__label">每页</span>
                <select className="select" value={limit} onChange={(e) => { setLimit(Number(e.target.value)); setCursor(null); setCursorStack([]); }}>
                  {[20, 50, 100].map((n) => <option key={n} value={n}>{n} 条</option>)}
                </select>
              </label>
              <button className="btn btn--primary" type="submit">应用筛选</button>
              <button className="btn btn--ghost" type="button" onClick={resetFilters}>重置</button>
            </div>
          </form>
          <p className="muted text-xs">
            时间筛选按 YYYY-MM-DD 日期传给 GET /review-history 的 from / to；统计总览使用
            {' '}{formatDate(statsFrom)} — {formatDate(statsTo)}（未填时默认最近 30 天）。
          </p>
        </div>
      </div>

      {/* 区间总览 */}
      <div className="card">
        <div className="card__head"><span className="card__title">区间总览</span></div>
        <div className="card__body">
          <QueryView state={statsQuery.state} onRetry={statsQuery.reload}>
            {(stats) => (
              <div className="stack">
                <div className="stat-grid">
                  <div className="card stat-card"><div className="card__body card__body--tight">
                    <p className="stat-card__label">任务总数</p><p className="stat-card__value">{stats.total_tasks}</p>
                  </div></div>
                  <div className="card stat-card"><div className="card__body card__body--tight">
                    <p className="stat-card__label">已完成</p><p className="stat-card__value">{stats.completed_tasks}</p>
                  </div></div>
                  <div className="card stat-card"><div className="card__body card__body--tight">
                    <p className="stat-card__label">完成率</p><p className="stat-card__value">{formatPercent(stats.completion_rate)}</p>
                  </div></div>
                </div>
                <div className="grid-2">
                  <div>
                    <p className="section-title">留存趋势</p>
                    <div className="mt-6"><TrendChart points={stats.retention_trend} /></div>
                  </div>
                  <div>
                    <p className="section-title">复习热力图</p>
                    <div className="mt-6"><HeatmapCalendar points={stats.heatmap} /></div>
                  </div>
                </div>
              </div>
            )}
          </QueryView>
        </div>
      </div>

      {/* 历史列表（游标分页） */}
      <div className="card">
        <div className="card__head">
          <span className="card__title">复习历史</span>
          <span className="badge">第 {cursorStack.length + 1} 页</span>
        </div>
        <QueryView
          state={historyQuery.state}
          onRetry={historyQuery.reload}
          isEmpty={(page) => page.items.length === 0}
          emptyText="没有符合条件的复习历史"
          emptyHint="可放宽筛选条件或切换时间范围；历史记录为追加写，完成一次复习产生一条。"
        >
          {(page) => (
            <div className="stack">
              <div className="list">
                {page.items.map((history) => (
                  <div className="list-item" key={history.id}>
                    <div className="list-item__title">
                      <span className={`badge badge--${history.rating === 'again' ? 'danger' : history.rating === 'easy' ? 'ok' : 'info'}`}>
                        {RATING_LABELS[history.rating].label}
                      </span>
                      {' '}
                      {STRATEGY_LABELS[history.strategy]} · {formatDateTime(history.reviewed_at)}
                    </div>
                    <div className="list-item__meta">
                      <span>用时 {history.duration_seconds} 秒</span>
                      <span>知识点 <code className="mono">{history.knowledge_point_id}</code></span>
                      {history.review_item_id && <span>题目版本 <code className="mono">{history.review_item_id}</code></span>}
                    </div>
                    {history.answer_self_assessment && (
                      <p className="muted text-sm mt-6">答案自评：{history.answer_self_assessment}</p>
                    )}
                    {history.notes && <p className="muted text-sm">备注：{history.notes}</p>}
                    <details className="mt-6">
                      <summary className="muted text-xs">查看调度状态快照（previous_schedule / result_schedule）</summary>
                      <pre className="json-block">{'上一次：'}{JSON.stringify(history.previous_schedule, null, 2)}{'\n\n结果：'}{JSON.stringify(history.result_schedule, null, 2)}</pre>
                    </details>
                    <div className="mini-actions mt-6">
                      <Link href={`/knowledge/${history.knowledge_point_id}`} className="btn btn--sm btn--ghost">
                        查看知识点详情 →
                      </Link>
                      <span className="muted text-xs">历史 ID <code className="mono">{history.id}</code></span>
                    </div>
                  </div>
                ))}
              </div>
              <div className="form-actions">
                <button type="button" className="btn btn--ghost" disabled={cursorStack.length === 0} onClick={goPrev}>
                  上一页
                </button>
                <button
                  type="button"
                  className="btn btn--primary"
                  disabled={!page.has_more || !page.next_cursor}
                  onClick={() => goNext(page)}
                >
                  下一页
                </button>
                <span className="muted text-xs">
                  本页 {page.items.length} 条 · has_more={String(page.has_more)} ·
                  {' '}next_cursor={page.next_cursor ? '已返回' : 'null'}
                </span>
              </div>
              <p className="muted text-xs">
                分页严格使用契约的不透明游标（cursor / next_cursor），不使用 offset；上一页通过已走过的游标栈回退。
              </p>
            </div>
          )}
        </QueryView>
      </div>
    </div>
  );
}
