'use client';

/**
 * 知识点详情 / 编辑（FE-05 / FR-03）。
 *
 * 真实端点：
 *  - GET   /knowledge-points/{id}
 *  - PATCH /knowledge-points/{id}                （If-Match: "<version>"）
 *  - POST  /knowledge-points/{id}/activate      （Idempotency-Key）
 *  - POST  /knowledge-points/{id}/archive       （Idempotency-Key）
 *  - POST  /knowledge-points/{id}/merge         （Idempotency-Key）
 *  - GET   /knowledge-points/{id}/review-items  （展示 FR-04 题目）
 *  - GET   /knowledge-points/{id}/schedule      （展示 FR-05 调度状态）
 *
 * 调度状态不存在时后端返回真实 404，这里解释为"尚未激活"，不伪造数据。
 */

import Link from 'next/link';
import { useParams } from 'next/navigation';
import { useState } from 'react';
import { api, ApiError, newIdempotencyKey } from '@/lib/api';
import { useAsyncAction, useQuery, useSubjects } from '@/lib/hooks';
import { ErrorView, QueryView } from '@/components/States';
import { KnowledgeForm } from '@/components/knowledge/KnowledgeForm';
import { formatDateTime } from '@/lib/format';
import {
  KNOWLEDGE_STATUS_LABELS,
  QUESTION_TYPE_LABELS,
  STRATEGY_LABELS,
  difficultyStars,
  statusTone,
} from '@/lib/labels';
import type { Page, ReviewItemRead, ScheduleStateRead } from '@/types/api';

export default function KnowledgeDetailPage() {
  const params = useParams();
  const id = String(params.id ?? '');

  const query = useQuery(() => api.getKnowledgePoint(id), [id]);
  const subjects = useSubjects();
  const itemsQuery = useQuery<Page<ReviewItemRead>>(
    () => api.listReviewItems(id, { current_only: true, limit: 100 }),
    [id],
  );
  const scheduleQuery = useQuery<ScheduleStateRead | null>(async () => {
    try {
      return await api.getSchedule(id);
    } catch (e) {
      // 把真实的「无调度状态」404 解释为暂无，而非制造假数据。
      if (e instanceof ApiError && e.isNotFound) return null;
      throw e;
    }
  }, [id]);

  const [editing, setEditing] = useState(false);
  const [mergeOpen, setMergeOpen] = useState(false);
  const [mergeTarget, setMergeTarget] = useState('');
  const [mergeReason, setMergeReason] = useState('');
  const [notice, setNotice] = useState<string | null>(null);

  const lifecycle = useAsyncAction((kind: 'activate' | 'archive', key: string) =>
    kind === 'activate'
      ? api.activateKnowledgePoint(id, key)
      : api.archiveKnowledgePoint(id, key),
  );
  const mergeAction = useAsyncAction((target: string, reason: string, key: string) =>
    api.mergeKnowledgePoint(id, { target_id: target, reason: reason || null }, key),
  );

  const refreshAll = () => {
    query.reload();
    itemsQuery.reload();
    scheduleQuery.reload();
  };

  const handleLifecycle = async (kind: 'activate' | 'archive') => {
    const res = await lifecycle.run(kind, newIdempotencyKey());
    if (res.ok) {
      setNotice(
        kind === 'activate'
          ? '知识点已激活，后端已初始化独立调度状态。'
          : '知识点已归档。',
      );
      refreshAll();
    }
  };

  const handleMerge = async () => {
    const target = mergeTarget.trim();
    if (!target) return;
    const res = await mergeAction.run(target, mergeReason.trim(), newIdempotencyKey());
    if (res.ok) {
      setNotice('合并已完成，接口返回的是目标知识点资源。');
      setMergeOpen(false);
      setMergeTarget('');
      setMergeReason('');
      refreshAll();
    }
  };

  const subjectItems = subjects.state.status === 'success' ? subjects.state.data.items : [];

  return (
    <QueryView state={query.state} onRetry={query.reload}>
      {(kp) => (
        <div className="page">
          <div>
            <Link href="/knowledge" className="btn btn--ghost btn--sm">← 返回知识管理</Link>
          </div>

          <div className="card">
            <div className="card__head">
              <span className="card__title">{kp.title}</span>
              <span className={`badge badge--${statusTone(kp.status)}`}>
                {KNOWLEDGE_STATUS_LABELS[kp.status]}
              </span>
            </div>
            <div className="card__body">
              <div className="row">
                <span className="badge badge--info">{subjects.map.get(kp.subject_id) ?? kp.subject_id}</span>
                <span className="pill">难度 {difficultyStars(kp.difficulty)}</span>
                <span className="pill">版本 {kp.version}</span>
                {kp.manual_revision && <span className="badge badge--warn">人工修订（不会被同步覆盖）</span>}
              </div>

              {kp.tags.length > 0 && (
                <div className="tag-list">
                  {kp.tags.map((tag) => <span className="tag" key={tag}>{tag}</span>)}
                </div>
              )}
              {kp.keywords.length > 0 && (
                <div className="row">
                  <span className="muted text-sm">关键词：</span>
                  {kp.keywords.map((word) => <span className="pill" key={word}>{word}</span>)}
                </div>
              )}

              <dl className="kv">
                <div className="kv__row"><dt className="kv__key">创建时间</dt><dd className="kv__value">{formatDateTime(kp.created_at)}</dd></div>
                <div className="kv__row"><dt className="kv__key">更新时间</dt><dd className="kv__value">{formatDateTime(kp.updated_at)}</dd></div>
                <div className="kv__row"><dt className="kv__key">知识点 ID</dt><dd className="kv__value mono">{kp.id}</dd></div>
                <div className="kv__row"><dt className="kv__key">合并目标</dt><dd className="kv__value mono">{kp.merged_into_id || '—'}</dd></div>
                <div className="kv__row"><dt className="kv__key">内容指纹</dt><dd className="kv__value mono">{kp.canonical_hash}</dd></div>
              </dl>

              <div className="answer-box">
                <div className="answer-box__label">摘要</div>
                <p className="text-pre">{kp.summary}</p>
              </div>
              <div className="answer-box">
                <div className="answer-box__label">正文</div>
                <p className="text-pre">{kp.body}</p>
              </div>

              {subjects.state.status === 'error' && (
                <div className="notice notice--warn">学科名称加载失败，上方直接显示学科 ID。</div>
              )}
              {notice && <div className="notice notice--info">{notice}</div>}
              {lifecycle.error && <ErrorView error={lifecycle.error} />}
              {mergeAction.error && <ErrorView error={mergeAction.error} />}

              <div className="form-actions">
                <button
                  type="button"
                  className="btn btn--ghost"
                  onClick={() => setEditing((v) => !v)}
                >
                  {editing ? '取消编辑' : '编辑知识点'}
                </button>
                <button
                  type="button"
                  className="btn"
                  disabled={lifecycle.pending}
                  onClick={() => handleLifecycle('activate')}
                >
                  激活
                </button>
                <button
                  type="button"
                  className="btn"
                  disabled={lifecycle.pending}
                  onClick={() => handleLifecycle('archive')}
                >
                  归档
                </button>
                <button
                  type="button"
                  className="btn btn--ghost"
                  onClick={() => setMergeOpen((v) => !v)}
                >
                  合并到…
                </button>
              </div>
              <p className="muted text-xs">
                状态流转由后端校验，非法流转会返回真实的 INVALID_STATE 等错误，不由前端猜测状态机。
              </p>

              {editing && (
                <div className="card">
                  <div className="card__head">
                    <span className="card__title">编辑知识点（PATCH + If-Match）</span>
                  </div>
                  <div className="card__body">
                    <KnowledgeForm
                      initial={kp}
                      subjects={subjectItems}
                      submitLabel="保存修改"
                      onSubmit={(body) => api.updateKnowledgePoint(id, body, kp.version)}
                      onDone={() => {
                        setEditing(false);
                        setNotice('修改已保存；PATCH 会设置 manual_revision=true，保护人工修订内容。');
                        refreshAll();
                      }}
                      onCancel={() => setEditing(false)}
                    />
                  </div>
                </div>
              )}

              {mergeOpen && (
                <div className="card">
                  <div className="card__head"><span className="card__title">合并到其它知识点</span></div>
                  <div className="card__body">
                    <div className="inline-form">
                      <label className="field">
                        <span className="field__label">目标知识点 ID（UUID）</span>
                        <input
                          className="input"
                          value={mergeTarget}
                          onChange={(e) => setMergeTarget(e.target.value)}
                          placeholder="合并后保留的目标知识点 ID"
                        />
                      </label>
                      <label className="field">
                        <span className="field__label">合并原因（可选）</span>
                        <input
                          className="input"
                          value={mergeReason}
                          onChange={(e) => setMergeReason(e.target.value)}
                          placeholder="例如：内容重复"
                        />
                      </label>
                      <div className="form-actions">
                        <button
                          type="button"
                          className="btn btn--danger"
                          disabled={!mergeTarget.trim() || mergeAction.pending}
                          onClick={handleMerge}
                        >
                          {mergeAction.pending ? '提交中…' : '确认合并'}
                        </button>
                        <button type="button" className="btn btn--ghost" onClick={() => setMergeOpen(false)}>
                          取消
                        </button>
                      </div>
                    </div>
                  </div>
                </div>
              )}
            </div>
          </div>

          <div className="card">
            <div className="card__head"><span className="card__title">当前复习题目</span></div>
            <div className="card__body">
              <QueryView
                state={itemsQuery.state}
                onRetry={itemsQuery.reload}
                isEmpty={(page) => page.items.length === 0}
                emptyText="该知识点暂无复习题目"
                emptyHint="题目由出题服务生成或人工创建（FR-04），本页只读展示真实数据。"
              >
                {(page) => (
                  <div className="stack">
                    {page.items.map((item) => <ReviewItemBlock key={item.id} item={item} />)}
                  </div>
                )}
              </QueryView>
            </div>
          </div>

          <div className="card">
            <div className="card__head"><span className="card__title">调度状态</span></div>
            <div className="card__body">
              <QueryView
                state={scheduleQuery.state}
                onRetry={scheduleQuery.reload}
                isEmpty={(schedule) => schedule === null}
                emptyText="该知识点尚未激活，暂无调度状态"
                emptyHint="激活知识点后，后端会初始化独立的复习计划（艾宾浩斯固定间隔 / FSRS）。"
              >
                {(schedule) =>
                  schedule ? (
                    <dl className="kv">
                      <div className="kv__row"><dt className="kv__key">调度策略</dt><dd className="kv__value">{STRATEGY_LABELS[schedule.strategy]}</dd></div>
                      <div className="kv__row"><dt className="kv__key">下次到期</dt><dd className="kv__value">{formatDateTime(schedule.due_at)}</dd></div>
                      <div className="kv__row"><dt className="kv__key">上次复习</dt><dd className="kv__value">{formatDateTime(schedule.last_reviewed_at)}</dd></div>
                      <div className="kv__row"><dt className="kv__key">复习次数</dt><dd className="kv__value">{schedule.review_count}</dd></div>
                      <div className="kv__row"><dt className="kv__key">遗忘次数</dt><dd className="kv__value">{schedule.lapse_count}</dd></div>
                      <div className="kv__row"><dt className="kv__key">间隔天数</dt><dd className="kv__value">{schedule.interval_days ?? '—'}</dd></div>
                      <div className="kv__row"><dt className="kv__key">稳定性</dt><dd className="kv__value">{schedule.stability ?? '—'}</dd></div>
                      <div className="kv__row"><dt className="kv__key">难度（算法）</dt><dd className="kv__value">{schedule.difficulty ?? '—'}</dd></div>
                      <div className="kv__row"><dt className="kv__key">可提取性</dt><dd className="kv__value">{schedule.retrievability ?? '—'}</dd></div>
                      <div className="kv__row"><dt className="kv__key">目标留存率</dt><dd className="kv__value">{schedule.target_retention ?? '—'}</dd></div>
                      <div className="kv__row"><dt className="kv__key">算法版本</dt><dd className="kv__value mono">{schedule.algorithm_version}</dd></div>
                    </dl>
                  ) : null
                }
              </QueryView>
            </div>
          </div>
        </div>
      )}
    </QueryView>
  );
}

function ReviewItemBlock({ item }: { item: ReviewItemRead }) {
  return (
    <div className="card">
      <div className="card__head">
        <span className="card__title">{QUESTION_TYPE_LABELS[item.question_type]}</span>
        <span className="badge">第 {item.item_version} 版{item.is_current ? ' · 当前' : ''}</span>
      </div>
      <div className="card__body card__body--tight">
        <p className="question" style={{ fontSize: 15 }}>{item.question}</p>
        {item.question_type === 'multiple_choice' && item.options && item.options.length > 0 && (
          <ul className="option-list">
            {item.options.map((option, index) => (
              <li className="option" key={`${index}-${option}`}>
                <span className="option__key">{String.fromCharCode(65 + index)}</span>
                <span>{option}</span>
              </li>
            ))}
          </ul>
        )}
        <div className="answer-box">
          <div className="answer-box__label">参考答案</div>
          <p className="text-pre">{item.answer}</p>
        </div>
        {item.explanation && (
          <div className="answer-box">
            <div className="answer-box__label">解析</div>
            <p className="text-pre">{item.explanation}</p>
          </div>
        )}
        {item.summary && (
          <div className="answer-box">
            <div className="answer-box__label">摘要</div>
            <p className="text-pre">{item.summary}</p>
          </div>
        )}
        <div className="list-item__meta">
          {item.manual_revision && <span className="badge">人工修订</span>}
          {item.model_name && <span>模型 {item.model_name}</span>}
          {item.prompt_version && <span>提示词 {item.prompt_version}</span>}
          <span>版本 {item.item_version}</span>
        </div>
      </div>
    </div>
  );
}
