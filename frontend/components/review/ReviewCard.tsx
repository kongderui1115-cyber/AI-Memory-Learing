'use client';

/**
 * 今日复习卡片（FE-04 / FR-09）：题目展示 → 作答自评 → 掌握程度评分 → 完成标记。
 *
 * 全部调用真实端点：
 *  - GET /knowledge-points/{id}
 *  - GET /knowledge-points/{id}/review-items?current_only=true
 *  - POST /review-tasks/{id}/start   （标记开始）
 *  - POST /review-tasks/{id}/skip    （跳过，附原因）
 *  - POST /review-tasks/{id}/complete（完成标记 + 掌握程度 + 耗时 + 自评 + 备注，Idempotency-Key）
 *
 * 无假数据：加载中 / 错误 / 空题目都如实呈现；空题目时允许依据知识点正文自评完成。
 */

import { useRef, useState } from 'react';
import {
  api,
  newIdempotencyKey,
} from '@/lib/api';
import { useAsyncAction, useQuery } from '@/lib/hooks';
import { QueryView, ErrorView } from '@/components/States';
import { formatDateTime, nowIso } from '@/lib/format';
import {
  QUESTION_TYPE_LABELS,
  RATING_LABELS,
  RATING_ORDER,
  STRATEGY_LABELS,
  TASK_STATUS_LABELS,
  difficultyStars,
  taskStatusTone,
} from '@/lib/labels';
import type {
  DailyTaskRead,
  KnowledgePointRead,
  ReviewCompleteRequest,
  ReviewCompleteResponse,
  ReviewItemRead,
  ReviewRating,
  UUID,
} from '@/types/api';

interface CardData {
  kp: KnowledgePointRead;
  items: ReviewItemRead[];
}

interface ReviewCardProps {
  task: DailyTaskRead;
  /** 学科 id → 名称，来自真实 GET /subjects，加载失败时为空，展示时回退到 UUID。 */
  subjectMap: Map<UUID, string>;
  onChanged: () => void;
}

export function ReviewCard({ task, subjectMap, onChanged }: ReviewCardProps) {
  const query = useQuery<CardData>(
    () =>
      api.getKnowledgePoint(task.knowledge_point_id).then((kp) =>
        api.listReviewItems(kp.id, { current_only: true, limit: 100 }).then((page) => ({
          kp,
          items: page.items,
        })),
      ),
    [task.id, task.knowledge_point_id],
  );

  return (
    <QueryView state={query.state} onRetry={query.reload}>
      {(data) => {
        // 优先使用任务指定的题目版本，否则取当前版本，最后回退到第一条。
        const item =
          data.items.find((i) => i.id === task.review_item_id) ??
          data.items.find((i) => i.is_current) ??
          data.items[0];
        return (
          <ReviewCardInner
            task={task}
            kp={data.kp}
            item={item}
            itemCount={data.items.length}
            subjectName={subjectMap.get(data.kp.subject_id)}
            onChanged={onChanged}
          />
        );
      }}
    </QueryView>
  );
}

interface InnerProps {
  task: DailyTaskRead;
  kp: KnowledgePointRead;
  item: ReviewItemRead | undefined;
  itemCount: number;
  subjectName?: string;
  onChanged: () => void;
}

function ReviewCardInner({ task, kp, item, itemCount, subjectName, onChanged }: InnerProps) {
  const [showAnswer, setShowAnswer] = useState(false);
  const [rating, setRating] = useState<ReviewRating | null>(null);
  const [selfAssessment, setSelfAssessment] = useState('');
  const [notes, setNotes] = useState('');
  const [skipReason, setSkipReason] = useState('');
  const [startResult, setStartResult] = useState<DailyTaskRead | null>(null);
  const [result, setResult] = useState<ReviewCompleteResponse | null>(null);

  /** 卡片打开时刻，用于计算 duration_seconds。 */
  const startedAt = useRef<number>(Date.now());
  /** 每个动作一个固定幂等键，重试时复用，符合契约 §1。 */
  const keys = useRef<Record<string, string>>({});
  const keyFor = (action: string) => {
    if (!keys.current[action]) keys.current[action] = newIdempotencyKey();
    return keys.current[action];
  };

  const startAction = useAsyncAction((key: string) => api.startTask(task.id, key));
  const skipAction = useAsyncAction((key: string, reason?: string) =>
    api.skipTask(task.id, { reason }, key),
  );
  const completeAction = useAsyncAction((key: string, body: ReviewCompleteRequest) =>
    api.completeTask(task.id, body, key),
  );

  const currentStatus = startResult?.status ?? task.status;

  const handleStart = async () => {
    const res = await startAction.run(keyFor('start'));
    if (res.ok) setStartResult(res.value);
  };

  const handleSkip = async () => {
    const res = await skipAction.run(keyFor('skip'), skipReason.trim() || undefined);
    if (res.ok) onChanged();
  };

  const handleComplete = async () => {
    if (!rating) return;
    const body: ReviewCompleteRequest = {
      rating,
      duration_seconds: Math.max(0, Math.round((Date.now() - startedAt.current) / 1000)),
      answer_self_assessment: selfAssessment.trim() || null,
      notes: notes.trim() || null,
      reviewed_at: nowIso(),
    };
    const res = await completeAction.run(keyFor('complete'), body);
    if (res.ok) setResult(res.value);
  };

  // 已完成 / 已跳过 / 已取消的任务不重复作答。
  if (result) {
    return <CompletionResult result={result} onNext={onChanged} />;
  }

  if (task.status === 'completed' || task.status === 'skipped' || task.status === 'cancelled') {
    return (
      <div className="card">
        <div className="card__head">
          <span className="card__title">本题状态</span>
          <span className={`badge badge--${taskStatusTone(task.status)}`}>
            {TASK_STATUS_LABELS[task.status]}
          </span>
        </div>
        <div className="card__body">
          <div className="notice notice--info">
            该任务当前状态为「{TASK_STATUS_LABELS[task.status]}」，无需重复提交完成标记。
          </div>
          <div>
            <p className="section-title">{kp.title}</p>
            <p className="muted text-sm">学科：{subjectName ?? kp.subject_id}</p>
          </div>
          <div className="form-actions">
            <button type="button" className="btn btn--primary" onClick={onChanged}>
              复习下一题
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="card">
      <div className="card__head">
        <span className="card__title">复习卡片</span>
        <span className={`badge badge--${taskStatusTone(currentStatus)}`}>
          {TASK_STATUS_LABELS[currentStatus]}
        </span>
      </div>
      <div className="card__body">
        <div className="row">
          <span className="badge badge--info">{subjectName ?? kp.subject_id}</span>
          {item && <span className="badge">{QUESTION_TYPE_LABELS[item.question_type]}</span>}
          <span className="pill">难度 {difficultyStars(kp.difficulty)}</span>
        </div>

        <div>
          <h3 className="section-title">{kp.title}</h3>
          {kp.tags.length > 0 && (
            <div className="tag-list mt-6">
              {kp.tags.map((tag) => <span className="tag" key={tag}>{tag}</span>)}
            </div>
          )}
        </div>

        <div className="divider" />

        {item ? (
          <>
            <div className="answer-box">
              <div className="answer-box__label">
                题目（{QUESTION_TYPE_LABELS[item.question_type]} · 第 {item.item_version} 版）
              </div>
              <p className="question">{item.question}</p>
            </div>
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
          </>
        ) : (
          <div className="notice notice--warn">
            该知识点当前没有可用题目（本次查询到 {itemCount} 条题目）。你仍可依据下方知识点正文自评，并完成本次复习。
          </div>
        )}

        <div className="form-actions">
          <button
            type="button"
            className="btn btn--ghost"
            disabled={!item}
            onClick={() => setShowAnswer((v) => !v)}
          >
            {showAnswer ? '隐藏答案与解析' : '显示答案与解析'}
          </button>
        </div>

        {showAnswer && (
          <div className="stack">
            {item && (
              <>
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
                    <div className="answer-box__label">题目摘要</div>
                    <p className="text-pre">{item.summary}</p>
                  </div>
                )}
                {item.model_name && (
                  <p className="muted text-xs">
                    生成来源：{item.model_name}
                    {item.prompt_version ? ` · 提示词版本 ${item.prompt_version}` : ''}
                    {item.provider_config_id ? ` · 配置 ${item.provider_config_id}` : ''}
                  </p>
                )}
              </>
            )}
            <div className="answer-box">
              <div className="answer-box__label">知识点正文（参考）</div>
              <p className="text-pre">{kp.body}</p>
              {kp.summary && (
                <>
                  <div className="divider divider--tight" />
                  <div className="answer-box__label">知识点摘要</div>
                  <p className="text-pre">{kp.summary}</p>
                </>
              )}
            </div>
          </div>
        )}

        <div className="divider" />

        <div className="mini-actions">
          <button
            type="button"
            className="btn btn--sm"
            disabled={task.status !== 'pending' || Boolean(startResult) || startAction.pending}
            onClick={handleStart}
          >
            {startAction.pending ? '标记中…' : startResult ? '已标记开始' : '标记开始'}
          </button>
          <span className="muted text-xs">调用真实端点记录开始时间 started_at。</span>
        </div>
        {startAction.error && <ErrorView error={startAction.error} />}

        <div>
          <p className="field__label">掌握程度评分（与 FSRS 的 again / hard / good / easy 对齐）</p>
          <div className="rating-grid mt-8">
            {RATING_ORDER.map((value) => (
              <button
                key={value}
                type="button"
                className={`rating-btn ${rating === value ? 'rating-btn--active' : ''}`}
                onClick={() => setRating(value)}
              >
                <span className="rating-btn__label">{RATING_LABELS[value].label}</span>
                <span className="rating-btn__hint">{RATING_LABELS[value].hint}</span>
              </button>
            ))}
          </div>
        </div>

        <div className="grid-2">
          <label className="field">
            <span className="field__label">答案自评（可选）</span>
            <textarea
              className="textarea"
              value={selfAssessment}
              onChange={(e) => setSelfAssessment(e.target.value)}
              placeholder="例如：要点基本答出，但遗漏了第二个原因"
            />
          </label>
          <label className="field">
            <span className="field__label">复习备注（可选）</span>
            <textarea
              className="textarea"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="记录本次复习的想法"
            />
          </label>
        </div>

        {completeAction.error && <ErrorView error={completeAction.error} />}
        <div className="form-actions">
          <button
            type="button"
            className="btn btn--primary"
            disabled={!rating || completeAction.pending}
            onClick={handleComplete}
          >
            {completeAction.pending ? '提交中…' : '完成并标记掌握程度'}
          </button>
          <span className="muted text-xs">评分后提交：历史 + 调度状态 + 任务单事务更新。</span>
        </div>

        <div className="divider" />

        <label className="field">
          <span className="field__label">跳过此题（原因可选）</span>
          <input
            className="input"
            value={skipReason}
            onChange={(e) => setSkipReason(e.target.value)}
            placeholder="例如：今天时间不够，明天再复习"
          />
        </label>
        {skipAction.error && <ErrorView error={skipAction.error} />}
        <div className="form-actions">
          <button
            type="button"
            className="btn btn--ghost"
            disabled={skipAction.pending}
            onClick={handleSkip}
          >
            {skipAction.pending ? '提交中…' : '跳过此题'}
          </button>
          <span className="muted text-xs">跳过不会丢失该知识点的到期计划。</span>
        </div>
      </div>
    </div>
  );
}

/** 完成后的结果面板：展示后端单事务返回的历史与更新后的调度状态。 */
function CompletionResult({
  result,
  onNext,
}: {
  result: ReviewCompleteResponse;
  onNext: () => void;
}) {
  const { history, schedule, task } = result;
  return (
    <div className="card result-panel">
      <div className="card__head">
        <span className="card__title">已完成本题</span>
        <span className="badge badge--ok">{RATING_LABELS[history.rating].label}</span>
      </div>
      <div className="card__body">
        <div className="notice notice--info">
          完成标记、掌握程度与历史由后端单事务写入，调度状态与下次到期时间已同步更新（FR-09）。
        </div>

        <div className="result-panel__grid">
          <div className="card">
            <div className="card__head"><span className="card__title">复习历史</span></div>
            <div className="card__body card__body--tight">
              <dl className="kv">
                <div className="kv__row"><dt className="kv__key">掌握程度</dt><dd className="kv__value">{RATING_LABELS[history.rating].label}</dd></div>
                <div className="kv__row"><dt className="kv__key">用时</dt><dd className="kv__value">{history.duration_seconds} 秒</dd></div>
                <div className="kv__row"><dt className="kv__key">答案自评</dt><dd className="kv__value">{history.answer_self_assessment || '—'}</dd></div>
                <div className="kv__row"><dt className="kv__key">备注</dt><dd className="kv__value">{history.notes || '—'}</dd></div>
                <div className="kv__row"><dt className="kv__key">复习时间</dt><dd className="kv__value">{formatDateTime(history.reviewed_at)}</dd></div>
                <div className="kv__row"><dt className="kv__key">历史 ID</dt><dd className="kv__value mono">{history.id}</dd></div>
              </dl>
            </div>
          </div>

          <div className="card">
            <div className="card__head"><span className="card__title">更新后的调度状态</span></div>
            <div className="card__body card__body--tight">
              <dl className="kv">
                <div className="kv__row"><dt className="kv__key">任务状态</dt><dd className="kv__value">{TASK_STATUS_LABELS[task.status]}</dd></div>
                <div className="kv__row"><dt className="kv__key">调度策略</dt><dd className="kv__value">{STRATEGY_LABELS[schedule.strategy]}</dd></div>
                <div className="kv__row"><dt className="kv__key">下次复习</dt><dd className="kv__value">{formatDateTime(schedule.due_at)}</dd></div>
                <div className="kv__row"><dt className="kv__key">已复习次数</dt><dd className="kv__value">{schedule.review_count}</dd></div>
                <div className="kv__row"><dt className="kv__key">间隔天数</dt><dd className="kv__value">{schedule.interval_days ?? '—'}</dd></div>
                <div className="kv__row"><dt className="kv__key">算法版本</dt><dd className="kv__value mono">{schedule.algorithm_version}</dd></div>
              </dl>
            </div>
          </div>
        </div>

        <div className="form-actions">
          <button type="button" className="btn btn--primary" onClick={onNext}>
            复习下一题
          </button>
        </div>
      </div>
    </div>
  );
}
