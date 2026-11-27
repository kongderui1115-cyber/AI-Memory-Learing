'use client';

/**
 * 学科策略配置（FE-07 / FR-10）。
 * 真实端点：GET /subjects、GET /subjects/{id}/strategy、PUT /subjects/{id}/strategy（首次可无 If-Match）。
 * 学科策略是数据驱动扩展点：抽取提示词、题型偏好、术语表、调度覆盖、通知模板覆盖。
 */

import { useState } from 'react';
import type { FormEvent } from 'react';
import { api, ApiError } from '@/lib/api';
import { useAsyncAction, useQuery } from '@/lib/hooks';
import { ErrorView, QueryView } from '@/components/States';
import { parseJsonObject, parseStringMap, stringifyJson } from '@/lib/format';
import { QUESTION_TYPE_LABELS } from '@/lib/labels';
import type { Page, QuestionType, SubjectRead, SubjectStrategyRead, SubjectStrategyWrite } from '@/types/api';

export function SubjectStrategyPanel() {
  const subjectsQuery = useQuery<Page<SubjectRead>>(
    () => api.listSubjects({ limit: 100 }),
    [],
  );
  const [selectedId, setSelectedId] = useState('');

  const strategyQuery = useQuery<SubjectStrategyRead | null>(async () => {
    if (!selectedId) return null;
    try {
      return await api.getSubjectStrategy(selectedId);
    } catch (e) {
      // 首次尚未配置策略时后端可能返回 404；如实解释为"未配置"，不伪造默认策略。
      if (e instanceof ApiError && e.isNotFound) return null;
      throw e;
    }
  }, [selectedId]);

  return (
    <div className="stack">
      <div className="notice notice--info">
        学科策略为数据驱动配置（FR-10）：新增或修改策略后，抽取、出题、调度与通知链路通过配置生效，无需改代码。
      </div>

      <div className="card">
        <div className="card__head"><span className="card__title">选择学科</span></div>
        <div className="card__body">
          <QueryView state={subjectsQuery.state} onRetry={subjectsQuery.reload}
            isEmpty={(page) => page.items.length === 0}
            emptyText="暂无学科"
            emptyHint="请先在「知识管理 → 学科」创建学科，再配置策略。">
            {(page) => (
              <label className="field">
                <span className="field__label">学科</span>
                <select className="select" value={selectedId} onChange={(e) => setSelectedId(e.target.value)}>
                  <option value="">请选择学科</option>
                  {page.items.map((subject) => (
                    <option key={subject.id} value={subject.id}>{subject.name}（{subject.slug}）</option>
                  ))}
                </select>
                {page.has_more && <span className="field__hint">学科超过 100 条，下拉仅显示已加载部分。</span>}
              </label>
            )}
          </QueryView>
        </div>
      </div>

      {!selectedId ? (
        <div className="notice">请选择一个学科以查看或配置其策略。</div>
      ) : (
        <QueryView state={strategyQuery.state} onRetry={strategyQuery.reload}>
          {(strategy) => (
            <div className="card">
              <div className="card__head">
                <span className="card__title">{strategy ? '编辑学科策略' : '创建学科策略'}</span>
                <span className={`badge badge--${strategy ? 'info' : 'warn'}`}>
                  {strategy ? '已配置' : '未配置'}
                </span>
              </div>
              <div className="card__body">
                {strategy && (
                  <dl className="kv">
                    <div className="kv__row"><dt className="kv__key">版本</dt><dd className="kv__value">{strategy.version}（PUT 时作为 If-Match）</dd></div>
                    <div className="kv__row"><dt className="kv__key">学科 ID</dt><dd className="kv__value mono">{strategy.subject_id}</dd></div>
                    <div className="kv__row"><dt className="kv__key">更新时间</dt><dd className="kv__value">{strategy.updated_at}</dd></div>
                  </dl>
                )}
                {!strategy && (
                  <div className="notice notice--warn">
                    该学科尚未配置策略（GET 返回 404）。首次创建时不带 If-Match；保存后由后端生成版本。
                  </div>
                )}
                <StrategyForm
                  key={selectedId}
                  subjectId={selectedId}
                  strategy={strategy}
                  onSaved={strategyQuery.reload}
                />
              </div>
            </div>
          )}
        </QueryView>
      )}
    </div>
  );
}

interface StrategyFormProps {
  subjectId: string;
  strategy: SubjectStrategyRead | null;
  onSaved: () => void;
}

function StrategyForm({ subjectId, strategy, onSaved }: StrategyFormProps) {
  const [extractionPrompt, setExtractionPrompt] = useState(strategy?.extraction_prompt ?? '');
  const [promptVersion, setPromptVersion] = useState(strategy?.prompt_version ?? 'v1');
  const [questionTypes, setQuestionTypes] = useState<QuestionType[]>(strategy?.question_type_preferences ?? []);
  const [glossaryText, setGlossaryText] = useState(stringifyJson(strategy?.glossary ?? {}));
  const [schedulerText, setSchedulerText] = useState(stringifyJson(strategy?.scheduler_overrides ?? {}));
  const [templateText, setTemplateText] = useState(stringifyJson(strategy?.notification_template_overrides ?? {}));
  const [isActive, setIsActive] = useState(strategy?.is_active ?? true);
  const [localError, setLocalError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  const submit = useAsyncAction((body: SubjectStrategyWrite, ifMatch?: number) =>
    api.putSubjectStrategy(subjectId, body, ifMatch),
  );

  const toggleType = (type: QuestionType) => {
    setQuestionTypes((current) =>
      current.includes(type) ? current.filter((t) => t !== type) : [...current, type],
    );
  };

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    let body: SubjectStrategyWrite;
    try {
      body = {
        extraction_prompt: extractionPrompt.trim(),
        prompt_version: promptVersion.trim(),
        question_type_preferences: questionTypes,
        glossary: parseStringMap(glossaryText),
        scheduler_overrides: parseJsonObject(schedulerText),
        notification_template_overrides: parseJsonObject(templateText),
        is_active: isActive,
      };
    } catch (e) {
      setLocalError(e instanceof Error ? e.message : String(e));
      return;
    }
    if (!body.extraction_prompt || !body.prompt_version) {
      setLocalError('抽取提示词与提示词版本为必填项');
      return;
    }
    setLocalError(null);
    setSaved(false);
    const res = await submit.run(body, strategy?.version);
    if (res.ok) {
      setSaved(true);
      onSaved();
    }
  };

  return (
    <form className="form" onSubmit={handleSubmit}>
      <label className="field">
        <span className="field__label">抽取提示词（extraction_prompt）</span>
        <textarea className="textarea" required value={extractionPrompt} onChange={(e) => setExtractionPrompt(e.target.value)} placeholder="用于从笔记中抽取结构化知识点的提示词" />
      </label>

      <div className="grid-2">
        <label className="field">
          <span className="field__label">提示词版本（prompt_version）</span>
          <input className="input" required maxLength={40} value={promptVersion} onChange={(e) => setPromptVersion(e.target.value)} placeholder="例如 v1" />
        </label>
        <label className="row">
          <input type="checkbox" checked={isActive} onChange={(e) => setIsActive(e.target.checked)} />
          <span className="field__label">启用该策略（is_active）</span>
        </label>
      </div>

      <div className="field">
        <span className="field__label">题型偏好（question_type_preferences）</span>
        <div className="row">
          {(Object.keys(QUESTION_TYPE_LABELS) as QuestionType[]).map((type) => (
            <label className="check-chip" key={type}>
              <input type="checkbox" checked={questionTypes.includes(type)} onChange={() => toggleType(type)} />
              <span>{QUESTION_TYPE_LABELS[type]}</span>
            </label>
          ))}
        </div>
      </div>

      <label className="field">
        <span className="field__label">术语表（glossary，JSON 对象，值须为字符串）</span>
        <textarea className="textarea mono" value={glossaryText} onChange={(e) => setGlossaryText(e.target.value)} />
      </label>
      <label className="field">
        <span className="field__label">调度参数覆盖（scheduler_overrides，JSON 对象）</span>
        <textarea className="textarea mono" value={schedulerText} onChange={(e) => setSchedulerText(e.target.value)} />
      </label>
      <label className="field">
        <span className="field__label">通知模板覆盖（notification_template_overrides，JSON 对象）</span>
        <textarea className="textarea mono" value={templateText} onChange={(e) => setTemplateText(e.target.value)} />
      </label>

      {localError && <div className="notice notice--error">{localError}</div>}
      {submit.error && <ErrorView error={submit.error} />}
      {saved && <div className="notice notice--info">策略已保存。</div>}

      <div className="form-actions">
        <button className="btn btn--primary" type="submit" disabled={submit.pending}>
          {submit.pending ? '保存中…' : strategy ? '保存策略（带 If-Match）' : '创建策略（首次无 If-Match）'}
        </button>
      </div>
    </form>
  );
}
