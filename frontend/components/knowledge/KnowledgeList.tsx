'use client';

/**
 * 知识点列表（FE-05 / FR-03 / FR-10）：
 *  - GET /knowledge-points 支持 subject_id / status / tag / q / limit / cursor 真实筛选；
 *  - POST /knowledge-points 人工创建知识点（Idempotency-Key）；
 *  - 列表项链接到详情页。
 */

import { useState } from 'react';
import type { FormEvent } from 'react';
import Link from 'next/link';
import { api } from '@/lib/api';
import { useQuery } from '@/lib/hooks';
import { QueryView } from '@/components/States';
import { KnowledgeForm } from './KnowledgeForm';
import { formatDateTime } from '@/lib/format';
import {
  KNOWLEDGE_STATUS_LABELS,
  difficultyStars,
  statusTone,
} from '@/lib/labels';
import type {
  KnowledgePointRead,
  KnowledgePointStatus,
  KnowledgePointWrite,
  Page,
  SubjectRead,
  UUID,
} from '@/types/api';

interface KnowledgeListProps {
  subjects: SubjectRead[];
  subjectMap: Map<UUID, string>;
  subjectsFailed: boolean;
}

interface Filters {
  subjectId: string;
  status: KnowledgePointStatus | '';
  tag: string;
  q: string;
}

const EMPTY_FILTERS: Filters = { subjectId: '', status: '', tag: '', q: '' };

export function KnowledgeList({ subjects, subjectMap, subjectsFailed }: KnowledgeListProps) {
  const [draft, setDraft] = useState<Filters>(EMPTY_FILTERS);
  const [applied, setApplied] = useState<Filters>(EMPTY_FILTERS);
  const [creating, setCreating] = useState(false);

  const query = useQuery<Page<KnowledgePointRead>>(
    () =>
      api.listKnowledgePoints({
        limit: 100,
        subject_id: applied.subjectId || undefined,
        status: applied.status || undefined,
        tag: applied.tag.trim() || undefined,
        q: applied.q.trim() || undefined,
      }),
    [applied.subjectId, applied.status, applied.tag, applied.q],
  );

  // 直接抛错，由 KnowledgeForm 内部的 useAsyncAction 捕获并展示；
  // 只有真正成功时表单才会调用 onDone（关闭并刷新）。
  const handleCreate = async (body: KnowledgePointWrite, key: string) => {
    await api.createKnowledgePoint(body, key);
  };

  const applyFilters = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setApplied({ ...draft });
  };

  const resetFilters = () => {
    setDraft({ ...EMPTY_FILTERS });
    setApplied({ ...EMPTY_FILTERS });
  };

  return (
    <div className="stack">
      <div className="card">
        <div className="card__head">
          <span className="card__title">筛选与新建</span>
          <button
            type="button"
            className="btn btn--primary btn--sm"
            onClick={() => setCreating((v) => !v)}
          >
            {creating ? '收起表单' : '新建知识点'}
          </button>
        </div>
        <div className="card__body">
          {subjectsFailed && (
            <div className="notice notice--warn">
              学科列表加载失败，学科下拉可能为「请选择学科」状态；知识点列表与筛选仍可正常使用。
            </div>
          )}

          <form className="toolbar" onSubmit={applyFilters}>
            <div className="toolbar__group">
              <select
                className="select"
                value={draft.subjectId}
                onChange={(e) => setDraft({ ...draft, subjectId: e.target.value })}
                aria-label="按学科筛选"
              >
                <option value="">全部学科</option>
                {subjects.map((subject) => (
                  <option key={subject.id} value={subject.id}>{subject.name}</option>
                ))}
              </select>
              <select
                className="select"
                value={draft.status}
                onChange={(e) => setDraft({ ...draft, status: e.target.value as KnowledgePointStatus | '' })}
                aria-label="按状态筛选"
              >
                <option value="">全部状态</option>
                {(Object.keys(KNOWLEDGE_STATUS_LABELS) as KnowledgePointStatus[]).map((value) => (
                  <option key={value} value={value}>{KNOWLEDGE_STATUS_LABELS[value]}</option>
                ))}
              </select>
            </div>
            <div className="toolbar__group">
              <input
                className="input"
                value={draft.tag}
                onChange={(e) => setDraft({ ...draft, tag: e.target.value })}
                placeholder="按标签筛选"
                aria-label="按标签筛选"
              />
              <input
                className="input"
                value={draft.q}
                onChange={(e) => setDraft({ ...draft, q: e.target.value })}
                placeholder="关键词搜索"
                aria-label="关键词搜索"
              />
              <button className="btn btn--primary" type="submit">应用筛选</button>
              <button className="btn btn--ghost" type="button" onClick={resetFilters}>重置</button>
            </div>
          </form>

          {creating && (
            <div className="card">
              <div className="card__head"><span className="card__title">新建知识点</span></div>
              <div className="card__body">
                <KnowledgeForm
                  subjects={subjects}
                  submitLabel="创建知识点"
                  onSubmit={handleCreate}
                  onDone={() => {
                    setCreating(false);
                    query.reload();
                  }}
                  onCancel={() => setCreating(false)}
                />
              </div>
            </div>
          )}
        </div>
      </div>

      <div className="card">
        <div className="card__head">
          <span className="card__title">知识点列表</span>
          <button type="button" className="btn btn--ghost btn--sm" onClick={query.reload}>刷新</button>
        </div>
        <QueryView
          state={query.state}
          onRetry={query.reload}
          isEmpty={(page) => page.items.length === 0}
          emptyText="暂无知识点"
          emptyHint="可调整筛选条件，或点击「新建知识点」人工创建；也可等待 Notion 同步与 AI 抽取（FR-01/03）。"
        >
          {(page) => (
            <div className="list">
              {page.items.map((kp) => (
                <Link key={kp.id} href={`/knowledge/${kp.id}`} className="list-item">
                  <div className="list-item__title">{kp.title}</div>
                  <div className="list-item__meta">
                    <span className={`badge badge--${statusTone(kp.status)}`}>
                      {KNOWLEDGE_STATUS_LABELS[kp.status]}
                    </span>
                    <span className="pill">{subjectMap.get(kp.subject_id) ?? kp.subject_id}</span>
                    <span>难度 {difficultyStars(kp.difficulty)}</span>
                    <span>{formatDateTime(kp.created_at)}</span>
                    {kp.manual_revision && <span className="badge">人工修订</span>}
                  </div>
                  {kp.tags.length > 0 && (
                    <div className="tag-list mt-6">
                      {kp.tags.map((tag) => <span className="tag" key={tag}>{tag}</span>)}
                    </div>
                  )}
                  <p className="muted text-sm mt-6">{kp.summary}</p>
                </Link>
              ))}
            </div>
          )}
        </QueryView>
      </div>
    </div>
  );
}
