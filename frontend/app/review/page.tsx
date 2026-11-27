'use client';

/**
 * 今日复习页（FE-04 / FR-06 / FR-09）。
 *
 * 真实端点：
 *  - GET  /review-tasks?local_date=...       加载当日任务（加载中/错误/空状态如实反映）
 *  - POST /review-batches/generate           生成今日复习（Idempotency-Key）
 *  - GET  /subjects                         学科名称映射（可选增强）
 *  - 具体作答与完成标记见 components/review/ReviewCard.tsx
 *
 * 不使用任何硬编码兜底数据。
 */

import { useMemo, useState } from 'react';
import { api, newIdempotencyKey } from '@/lib/api';
import { useAuth } from '@/components/AuthProvider';
import { useAsyncAction, useQuery, useSubjects } from '@/lib/hooks';
import { EmptyView, ErrorView, QueryView } from '@/components/States';
import { ReviewCard } from '@/components/review/ReviewCard';
import { accountDate, formatDate, formatDateTime } from '@/lib/format';
import { TASK_STATUS_LABELS, taskStatusTone } from '@/lib/labels';
import type { DailyTaskRead, Page } from '@/types/api';

/** 每日期望任务上限，契约约束 1..500。 */
const DAILY_LIMIT = 30;

export default function ReviewPage() {
  const { user } = useAuth();
  const timezone = user?.timezone;
  const localDate = useMemo(() => accountDate(timezone), [timezone]);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const tasksQuery = useQuery<Page<DailyTaskRead>>(
    () => api.listReviewTasks({ local_date: localDate, limit: 100 }),
    [localDate],
  );
  const subjects = useSubjects();
  const generate = useAsyncAction((key: string) => {
    if (!timezone) return Promise.reject(new Error('账号时区尚未载入'));
    return api.generateReviewBatch(
      { local_date: localDate, timezone, daily_limit: DAILY_LIMIT },
      key,
    );
  });

  const handleGenerate = async () => {
    if (!timezone) return;
    const res = await generate.run(newIdempotencyKey());
    if (res.ok) {
      setSelectedId(null);
      tasksQuery.reload();
    }
  };

  return (
    <div className="page">
      <header className="page-head">
        <div className="page-head__row">
          <div>
            <h1 className="page-title">今日复习</h1>
            <p className="page-sub">
              账号日期 {formatDate(localDate)} · 时区 {timezone ?? '—'} · 任务来自真实接口
            </p>
          </div>
          <div className="page-actions">
            <button
              type="button"
              className="btn btn--primary"
              disabled={generate.pending || !timezone}
              onClick={handleGenerate}
            >
              {generate.pending ? '生成中…' : '生成今日复习'}
            </button>
            <button type="button" className="btn btn--ghost" onClick={tasksQuery.reload}>
              刷新
            </button>
          </div>
        </div>
        {generate.error && <ErrorView error={generate.error} />}
        {subjects.state.status === 'error' && (
          <div className="notice notice--warn">
            学科名称加载失败，卡片将直接显示学科 ID；复习与完成功能不受影响。
          </div>
        )}
      </header>

      <QueryView
        state={tasksQuery.state}
        onRetry={tasksQuery.reload}
        isEmpty={(page) => page.items.length === 0}
        emptyText="今日暂无复习任务"
        emptyHint="可点击上方「生成今日复习」，按到期知识点创建当日任务清单；生成结果由后端按调度规则真实计算。"
      >
        {(page) => {
          const tasks = page.items;
          const completed = tasks.filter((t) => t.status === 'completed').length;
          const percent = tasks.length ? (completed / tasks.length) * 100 : 0;
          const current =
            tasks.find((t) => t.id === selectedId) ??
            tasks.find((t) => t.status === 'pending' || t.status === 'in_progress') ??
            tasks[0];

          return (
            <>
              <div className="card">
                <div className="card__body card__body--tight">
                  <div className="progress">
                    <div className="progress__text">
                      今日进度：{completed} / {tasks.length} 已完成
                    </div>
                    <div className="progress__bar">
                      <div className="progress__fill" style={{ width: `${percent}%` }} />
                    </div>
                  </div>
                </div>
              </div>

              <div className="review-layout">
                <div className="card">
                  <div className="card__head">
                    <span className="card__title">任务清单（{tasks.length}）</span>
                  </div>
                  <div className="task-list" style={{ padding: 10 }}>
                    {tasks.map((task, index) => (
                      <button
                        key={task.id}
                        type="button"
                        className={`task-list__item ${current?.id === task.id ? 'task-list__item--active' : ''}`}
                        onClick={() => setSelectedId(task.id)}
                      >
                        第 {index + 1} 题 · 优先级 {task.priority}
                        <small>
                          <span className={`badge badge--${taskStatusTone(task.status)}`}>
                            {TASK_STATUS_LABELS[task.status]}
                          </span>
                          {' '}计划时间 {formatDateTime(task.scheduled_due_at)}
                        </small>
                      </button>
                    ))}
                  </div>
                </div>

                <div className="review-card-area">
                  {current ? (
                    <ReviewCard
                      key={current.id}
                      task={current}
                      subjectMap={subjects.map}
                      onChanged={() => {
                        setSelectedId(null);
                        tasksQuery.reload();
                      }}
                    />
                  ) : (
                    <EmptyView text="没有可展示的题目" />
                  )}
                </div>
              </div>
            </>
          );
        }}
      </QueryView>
    </div>
  );
}
