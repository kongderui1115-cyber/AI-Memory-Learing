'use client';

/** 知识点新建 / 编辑表单（FE-05）。字段严格对齐 KnowledgePointWrite。 */

import { useRef, useState } from 'react';
import type { FormEvent } from 'react';
import { useAsyncAction } from '@/lib/hooks';
import { ErrorView } from '@/components/States';
import { newIdempotencyKey } from '@/lib/api';
import { splitList } from '@/lib/format';
import { KNOWLEDGE_STATUS_LABELS } from '@/lib/labels';
import type {
  KnowledgePointRead,
  KnowledgePointStatus,
  KnowledgePointWrite,
  SubjectRead,
} from '@/types/api';

interface KnowledgeFormProps {
  subjects: SubjectRead[];
  /** 有值时为编辑模式（PATCH + If-Match 由调用方处理）。 */
  initial?: KnowledgePointRead;
  submitLabel: string;
  onSubmit: (body: KnowledgePointWrite, idempotencyKey: string) => Promise<unknown>;
  onDone: () => void;
  onCancel?: () => void;
}

export function KnowledgeForm({
  subjects,
  initial,
  submitLabel,
  onSubmit,
  onDone,
  onCancel,
}: KnowledgeFormProps) {
  // 同一次表单打开只使用一个幂等键，重试时复用，避免创建出重复知识点。
  const idempotencyKey = useRef(newIdempotencyKey());
  const [subjectId, setSubjectId] = useState(initial?.subject_id ?? subjects[0]?.id ?? '');
  const [title, setTitle] = useState(initial?.title ?? '');
  const [bodyText, setBodyText] = useState(initial?.body ?? '');
  const [summary, setSummary] = useState(initial?.summary ?? '');
  const [difficulty, setDifficulty] = useState(String(initial?.difficulty ?? 3));
  const [keywords, setKeywords] = useState(initial?.keywords.join('、') ?? '');
  const [tags, setTags] = useState(initial?.tags.join('、') ?? '');
  const [status, setStatus] = useState<KnowledgePointStatus>(initial?.status ?? 'draft');

  const submit = useAsyncAction((body: KnowledgePointWrite, key: string) => onSubmit(body, key));

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const body: KnowledgePointWrite = {
      subject_id: subjectId,
      title: title.trim(),
      body: bodyText.trim(),
      summary: summary.trim(),
      difficulty: Number(difficulty),
      keywords: splitList(keywords),
      tags: splitList(tags),
      status,
    };
    const res = await submit.run(body, idempotencyKey.current);
    if (res.ok) onDone();
  };

  return (
    <form className="form" onSubmit={handleSubmit}>
      <div className="grid-2">
        <label className="field">
          <span className="field__label">所属学科</span>
          <select
            className="select"
            required
            value={subjectId}
            onChange={(e) => setSubjectId(e.target.value)}
          >
            <option value="" disabled>请选择学科</option>
            {subjects.map((subject) => (
              <option key={subject.id} value={subject.id}>{subject.name}</option>
            ))}
          </select>
          {subjects.length === 0 && (
            <span className="field__hint">尚无学科，请先在「学科」标签页创建。</span>
          )}
        </label>
        <label className="field">
          <span className="field__label">状态</span>
          <select
            className="select"
            value={status}
            onChange={(e) => setStatus(e.target.value as KnowledgePointStatus)}
          >
            {(Object.keys(KNOWLEDGE_STATUS_LABELS) as KnowledgePointStatus[]).map((value) => (
              <option key={value} value={value}>{KNOWLEDGE_STATUS_LABELS[value]}</option>
            ))}
          </select>
        </label>
      </div>

      <label className="field">
        <span className="field__label">标题</span>
        <input
          className="input"
          required
          maxLength={300}
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="例如：Windows 内核的 IRQL 级别"
        />
      </label>

      <label className="field">
        <span className="field__label">正文</span>
        <textarea
          className="textarea"
          required
          value={bodyText}
          onChange={(e) => setBodyText(e.target.value)}
          placeholder="知识点的完整内容"
        />
      </label>

      <label className="field">
        <span className="field__label">摘要</span>
        <textarea
          className="textarea"
          required
          value={summary}
          onChange={(e) => setSummary(e.target.value)}
          placeholder="用于推送与复习卡片的简短摘要"
        />
      </label>

      <div className="grid-2">
        <label className="field">
          <span className="field__label">难度（1..5）</span>
          <select className="select" value={difficulty} onChange={(e) => setDifficulty(e.target.value)}>
            {[1, 2, 3, 4, 5].map((n) => (
              <option key={n} value={n}>{n} · {['', '入门', '基础', '进阶', '较难', '困难'][n]}</option>
            ))}
          </select>
        </label>
        <label className="field">
          <span className="field__label">关键词</span>
          <input
            className="input"
            value={keywords}
            onChange={(e) => setKeywords(e.target.value)}
            placeholder="用顿号或逗号分隔"
          />
        </label>
      </div>

      <label className="field">
        <span className="field__label">标签</span>
        <input
          className="input"
          value={tags}
          onChange={(e) => setTags(e.target.value)}
          placeholder="用顿号或逗号分隔，例如：内核、中断"
        />
      </label>

      {submit.error && <ErrorView error={submit.error} />}

      <div className="form-actions">
        <button className="btn btn--primary" type="submit" disabled={submit.pending || subjects.length === 0}>
          {submit.pending ? '提交中…' : submitLabel}
        </button>
        {onCancel && (
          <button className="btn btn--ghost" type="button" onClick={onCancel}>
            取消
          </button>
        )}
      </div>
    </form>
  );
}
