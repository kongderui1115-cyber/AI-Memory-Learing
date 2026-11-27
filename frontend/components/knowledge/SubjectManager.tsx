'use client';

/**
 * 学科管理（FE-05 / FR-10）：学科为数据驱动，新增学科无需改代码。
 * 真实端点：
 *  - GET    /subjects
 *  - POST   /subjects            （Idempotency-Key）
 *  - PATCH  /subjects/{id}      （If-Match: "<version>"）
 *  - DELETE /subjects/{id}      （If-Match，归档/禁用，204）
 */

import { useRef, useState } from 'react';
import type { FormEvent } from 'react';
import { api, newIdempotencyKey } from '@/lib/api';
import { useAsyncAction } from '@/lib/hooks';
import type { QueryState } from '@/lib/hooks';
import { ErrorView, QueryView } from '@/components/States';
import { splitList } from '@/lib/format';
import type { Page, SubjectRead, SubjectWrite, UUID } from '@/types/api';

interface SubjectManagerProps {
  state: QueryState<Page<SubjectRead>>;
  reload: () => void;
}

export function SubjectManager({ state, reload }: SubjectManagerProps) {
  const [creating, setCreating] = useState(false);
  const [editingId, setEditingId] = useState<UUID | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const deleteAction = useAsyncAction((id: UUID, version: number) => api.deleteSubject(id, version));

  const finish = (message: string) => {
    setNotice(message);
    setCreating(false);
    setEditingId(null);
    reload();
  };

  const handleCreate = async (body: SubjectWrite, key: string) => {
    await api.createSubject(body, key);
  };

  const handleDelete = async (subject: SubjectRead) => {
    if (!window.confirm(`确定要禁用学科「${subject.name}」吗？该操作为归档/禁用（返回 204）。`)) return;
    const res = await deleteAction.run(subject.id, subject.version);
    if (res.ok) finish(`已禁用学科「${subject.name}」`);
  };

  return (
    <div className="stack">
      <div className="card">
        <div className="card__head">
          <span className="card__title">学科管理</span>
          <button
            type="button"
            className="btn btn--primary btn--sm"
            onClick={() => setCreating((v) => !v)}
          >
            {creating ? '收起表单' : '新增学科'}
          </button>
        </div>
        <div className="card__body">
          <p className="muted text-sm">
            学科为数据驱动配置（FR-10）：新增学科后，抽取、出题、调度与通知链路通过配置即可生效，无需重新部署代码。
          </p>
          {notice && <div className="notice notice--info">{notice}</div>}
          {deleteAction.error && <ErrorView error={deleteAction.error} />}
          {creating && (
            <div className="card">
              <div className="card__head"><span className="card__title">新增学科</span></div>
              <div className="card__body">
                <SubjectForm
                  subjects={state.status === 'success' ? state.data.items : []}
                  submitLabel="创建学科"
                  onSubmit={(body, key) => handleCreate(body, key)}
                  onDone={() => finish('学科已创建')}
                  onCancel={() => setCreating(false)}
                />
              </div>
            </div>
          )}
        </div>
      </div>

      <div className="card">
        <div className="card__head">
          <span className="card__title">学科列表</span>
          <button type="button" className="btn btn--ghost btn--sm" onClick={reload}>刷新</button>
        </div>
        <QueryView
          state={state}
          onRetry={reload}
          isEmpty={(page) => page.items.length === 0}
          emptyText="暂无学科"
          emptyHint="点击「新增学科」创建第一个学科。"
        >
          {(page) => (
            <div className="list">
              {page.items.map((subject) => (
                <div key={subject.id} className="list-item">
                  <div className="list-item__title">
                    {subject.name}
                    {' '}
                    <span className={`badge badge--${subject.is_active ? 'ok' : 'muted'}`}>
                      {subject.is_active ? '启用' : '已禁用'}
                    </span>
                  </div>
                  <div className="list-item__meta">
                    <span className="pill mono">{subject.slug}</span>
                    <span>语言 {subject.language_code}</span>
                    {subject.parent_id && <span>上级 {subject.parent_id}</span>}
                    <span>版本 {subject.version}</span>
                  </div>
                  {subject.description && <p className="muted text-sm mt-6">{subject.description}</p>}
                  {subject.tags.length > 0 && (
                    <div className="tag-list mt-6">
                      {subject.tags.map((tag) => <span className="tag" key={tag}>{tag}</span>)}
                    </div>
                  )}
                  <div className="mini-actions mt-8">
                    <button
                      type="button"
                      className="btn btn--sm"
                      onClick={() => setEditingId(editingId === subject.id ? null : subject.id)}
                    >
                      {editingId === subject.id ? '收起编辑' : '编辑'}
                    </button>
                    <button
                      type="button"
                      className="btn btn--sm btn--ghost"
                      disabled={deleteAction.pending}
                      onClick={() => handleDelete(subject)}
                    >
                      禁用
                    </button>
                  </div>
                  {editingId === subject.id && (
                    <div className="card mt-8">
                      <div className="card__head"><span className="card__title">编辑「{subject.name}」</span></div>
                      <div className="card__body">
                        <SubjectForm
                          initial={subject}
                          subjects={page.items.filter((s) => s.id !== subject.id)}
                          submitLabel="保存修改"
                          onSubmit={(body) => api.updateSubject(subject.id, body, subject.version)}
                          onDone={() => finish(`已保存学科「${subject.name}」`)}
                          onCancel={() => setEditingId(null)}
                        />
                      </div>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </QueryView>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------

interface SubjectFormProps {
  initial?: SubjectRead;
  subjects: SubjectRead[];
  submitLabel: string;
  onSubmit: (body: SubjectWrite, idempotencyKey: string) => Promise<unknown>;
  onDone: () => void;
  onCancel?: () => void;
}

function SubjectForm({ initial, subjects, submitLabel, onSubmit, onDone, onCancel }: SubjectFormProps) {
  const idempotencyKey = useRef(newIdempotencyKey());
  const [name, setName] = useState(initial?.name ?? '');
  const [slug, setSlug] = useState(initial?.slug ?? '');
  const [parentId, setParentId] = useState(initial?.parent_id ?? '');
  const [description, setDescription] = useState(initial?.description ?? '');
  const [languageCode, setLanguageCode] = useState(initial?.language_code ?? 'zh-CN');
  const [tags, setTags] = useState(initial?.tags.join('、') ?? '');
  const [isActive, setIsActive] = useState(initial?.is_active ?? true);

  const submit = useAsyncAction((body: SubjectWrite, key: string) => onSubmit(body, key));

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const body: SubjectWrite = {
      name: name.trim(),
      slug: slug.trim(),
      parent_id: parentId || null,
      description: description.trim() || null,
      language_code: languageCode.trim() || 'zh-CN',
      tags: splitList(tags),
      is_active: isActive,
    };
    const res = await submit.run(body, idempotencyKey.current);
    if (res.ok) onDone();
  };

  return (
    <form className="form" onSubmit={handleSubmit}>
      <div className="grid-2">
        <label className="field">
          <span className="field__label">学科名称</span>
          <input className="input" required maxLength={120} value={name} onChange={(e) => setName(e.target.value)} placeholder="例如：Windows 内核" />
        </label>
        <label className="field">
          <span className="field__label">标识 slug</span>
          <input
            className="input"
            required
            pattern="^[a-z0-9][a-z0-9-]{0,79}$"
            value={slug}
            onChange={(e) => setSlug(e.target.value)}
            placeholder="例如：windows-kernel"
          />
          <span className="field__hint">仅小写字母、数字与连字符，且以字母或数字开头。</span>
        </label>
      </div>

      <div className="grid-2">
        <label className="field">
          <span className="field__label">上级学科（可选）</span>
          <select className="select" value={parentId} onChange={(e) => setParentId(e.target.value)}>
            <option value="">无（顶层学科）</option>
            {subjects.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select>
        </label>
        <label className="field">
          <span className="field__label">语言代码</span>
          <input className="input" value={languageCode} onChange={(e) => setLanguageCode(e.target.value)} placeholder="zh-CN" />
        </label>
      </div>

      <label className="field">
        <span className="field__label">描述（可选）</span>
        <textarea className="textarea" value={description} onChange={(e) => setDescription(e.target.value)} placeholder="学科说明" />
      </label>

      <label className="field">
        <span className="field__label">标签</span>
        <input className="input" value={tags} onChange={(e) => setTags(e.target.value)} placeholder="用顿号或逗号分隔" />
      </label>

      <label className="row">
        <input type="checkbox" checked={isActive} onChange={(e) => setIsActive(e.target.checked)} />
        <span className="field__label">启用该学科</span>
      </label>

      {submit.error && <ErrorView error={submit.error} />}

      <div className="form-actions">
        <button className="btn btn--primary" type="submit" disabled={submit.pending}>
          {submit.pending ? '提交中…' : submitLabel}
        </button>
        {onCancel && <button className="btn btn--ghost" type="button" onClick={onCancel}>取消</button>}
      </div>
    </form>
  );
}
