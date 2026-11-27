'use client';

/**
 * AI Provider 配置入口（FE-07 / FR-02）。
 *
 * 真实端点：GET/POST /ai/providers、POST /ai/providers/{id}/validate、GET /ai/calls。
 *
 * 安全：credential_ref 只是环境变量名，页面只展示名称，绝不展示明文 API Key。
 * 未配置 Key 或计费未授权时 validate 返回真实的 CONFIG_MISSING / FORBIDDEN，
 * 页面如实展示错误，不伪造"已验证"或"已连接"状态。
 */

import { useRef, useState } from 'react';
import type { FormEvent } from 'react';
import { api, newIdempotencyKey } from '@/lib/api';
import { useAsyncAction, useQuery } from '@/lib/hooks';
import { ErrorView, QueryView } from '@/components/States';
import { formatDateTime } from '@/lib/format';
import { AI_CALL_STATUS_LABELS, AI_PROVIDER_LABELS, aiCallStatusTone } from '@/lib/labels';
import type {
  AIProviderConfigRead,
  AIProviderConfigWrite,
  AIProviderType,
  AICallLogRead,
  Page,
  ProviderValidation,
  UUID,
} from '@/types/api';

export function AIProvidersPanel() {
  const providersQuery = useQuery<Page<AIProviderConfigRead>>(
    () => api.listAIProviders({ limit: 100 }),
    [],
  );
  const callsQuery = useQuery<Page<AICallLogRead>>(
    () => api.listAICalls({ limit: 20 }),
    [],
  );
  const [creating, setCreating] = useState(false);
  const [validation, setValidation] = useState<Record<string, ProviderValidation>>({});
  const validateAction = useAsyncAction((id: UUID, key: string) =>
    api.validateAIProvider(id, key),
  );

  const handleValidate = async (provider: AIProviderConfigRead) => {
    const res = await validateAction.run(provider.id, newIdempotencyKey());
    if (res.ok) setValidation((current) => ({ ...current, [provider.id]: res.value }));
  };

  const handleCreate = async (body: AIProviderConfigWrite, key: string) => {
    await api.createAIProvider(body, key);
  };

  return (
    <div className="stack">
      <div className="notice notice--info">
        API Key 仅存环境变量，库里只保存 <code>credential_ref</code>（环境变量名），页面绝不展示明文密钥。
        未配置 Key 或 <code>AI_BILLING_APPROVED</code> 未授权时，验证接口返回
        {' '}<code>CONFIG_MISSING</code> / <code>FORBIDDEN</code>，不会返回假的理解结果（FR-02）。
      </div>

      <div className="card">
        <div className="card__head">
          <span className="card__title">AI Provider 配置</span>
          <button type="button" className="btn btn--primary btn--sm" onClick={() => setCreating((v) => !v)}>
            {creating ? '收起表单' : '新增 Provider'}
          </button>
        </div>
        <div className="card__body">
          {creating && (
            <ProviderCreateForm
              onSubmit={handleCreate}
              onDone={() => { setCreating(false); providersQuery.reload(); }}
              onCancel={() => setCreating(false)}
            />
          )}
          {validateAction.error && <ErrorView error={validateAction.error} />}
        </div>
      </div>

      <div className="card">
        <div className="card__head">
          <span className="card__title">Provider 列表</span>
          <button type="button" className="btn btn--ghost btn--sm" onClick={providersQuery.reload}>刷新</button>
        </div>
        <QueryView
          state={providersQuery.state}
          onRetry={providersQuery.reload}
          isEmpty={(page) => page.items.length === 0}
          emptyText="尚未配置 AI Provider"
          emptyHint="未配置 Key 时抽取与出题链路会明确报错（CONFIG_MISSING），此处不显示「已连接」。"
        >
          {(page) => (
            <div className="list">
              {page.items.map((config) => (
                <div className="list-item" key={config.id}>
                  <div className="list-item__title">
                    {config.name}
                    {' '}
                    <span className={`badge badge--${config.is_enabled ? 'ok' : 'muted'}`}>
                      {config.is_enabled ? '启用' : '已停用'}
                    </span>
                    {config.is_default && <span className="badge badge--info">默认</span>}
                  </div>
                  <div className="list-item__meta">
                    <span className="pill">{AI_PROVIDER_LABELS[config.provider]}</span>
                    <span>模型 {config.model_name}</span>
                    <span>环境变量名 <code className="mono">{config.credential_ref}</code></span>
                  </div>
                  <div className="list-item__meta mt-6">
                    <span>temperature {config.temperature}</span>
                    <span>超时 {config.timeout_seconds} 秒</span>
                    <span>重试 {config.max_retries} 次</span>
                    <span>限流 {config.rate_limit_per_minute ?? '未设置'} / 分钟</span>
                    <span>Base URL {config.base_url ?? '默认'}</span>
                  </div>
                  <div className="mini-actions mt-6">
                    <button
                      type="button"
                      className="btn btn--sm"
                      disabled={validateAction.pending}
                      onClick={() => handleValidate(config)}
                    >
                      验证配置
                    </button>
                    {validation[config.id] && (
                      <span className={`badge badge--${validation[config.id].valid ? 'ok' : 'danger'}`}>
                        验证结果：{validation[config.id].valid ? '有效' : '无效'}
                        （{validation[config.id].provider} / {validation[config.id].model}）
                      </span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </QueryView>
      </div>

      <div className="card">
        <div className="card__head">
          <span className="card__title">最近 AI 调用审计</span>
          <button type="button" className="btn btn--ghost btn--sm" onClick={callsQuery.reload}>刷新</button>
        </div>
        <QueryView
          state={callsQuery.state}
          onRetry={callsQuery.reload}
          isEmpty={(page) => page.items.length === 0}
          emptyText="暂无 AI 调用记录"
          emptyHint="真实调用后由 GET /ai/calls 返回；未配置 Key 时不会有假的调用日志。"
        >
          {(page) => (
            <div className="list">
              {page.items.map((call) => (
                <div className="list-item" key={call.id}>
                  <div className="list-item__title">
                    <span className={`badge badge--${aiCallStatusTone(call.status)}`}>
                      {AI_CALL_STATUS_LABELS[call.status]}
                    </span>
                    {' '}
                    {call.operation} · {AI_PROVIDER_LABELS[call.provider]} / {call.model_name}
                  </div>
                  <div className="list-item__meta">
                    <span>提示词版本 {call.prompt_version}</span>
                    <span>Token {call.total_tokens ?? '—'}</span>
                    <span>耗时 {call.duration_ms ?? '—'} ms</span>
                    <span>尝试 {call.attempt_count} 次</span>
                    <span>开始 {formatDateTime(call.started_at)}</span>
                  </div>
                  {(call.error_code || call.error_message) && (
                    <div className="notice notice--error mt-6">
                      错误码 {call.error_code ?? '—'}：{call.error_message ?? '无附加说明'}
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

interface ProviderCreateFormProps {
  onSubmit: (body: AIProviderConfigWrite, key: string) => Promise<unknown>;
  onDone: () => void;
  onCancel: () => void;
}

function ProviderCreateForm({ onSubmit, onDone, onCancel }: ProviderCreateFormProps) {
  const [name, setName] = useState('');
  const [provider, setProvider] = useState<AIProviderType>('deepseek');
  const [modelName, setModelName] = useState('');
  const [credentialRef, setCredentialRef] = useState('');
  const [baseUrl, setBaseUrl] = useState('');
  const [temperature, setTemperature] = useState('0.2');
  const [timeoutSeconds, setTimeoutSeconds] = useState('60');
  const [maxRetries, setMaxRetries] = useState('3');
  const [rateLimit, setRateLimit] = useState('');
  const [isEnabled, setIsEnabled] = useState(true);
  const [isDefault, setIsDefault] = useState(false);
  const [localError, setLocalError] = useState<string | null>(null);

  const submit = useAsyncAction((body: AIProviderConfigWrite, key: string) => onSubmit(body, key));
  const idempotencyKey = useRef(newIdempotencyKey());

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const temp = Number(temperature);
    const timeout = Number(timeoutSeconds);
    const retries = Number(maxRetries);
    if (!Number.isFinite(temp) || temp < 0 || temp > 2) {
      setLocalError('temperature 必须在 0..2 之间');
      return;
    }
    if (!Number.isInteger(timeout) || timeout <= 0) {
      setLocalError('timeout_seconds 必须是大于 0 的整数');
      return;
    }
    if (!Number.isInteger(retries) || retries < 0) {
      setLocalError('max_retries 必须是大于等于 0 的整数');
      return;
    }
    const rate = rateLimit.trim() === '' ? null : Number(rateLimit);
    if (rate !== null && (!Number.isInteger(rate) || rate <= 0)) {
      setLocalError('rate_limit_per_minute 必须是大于 0 的整数，或留空');
      return;
    }
    setLocalError(null);

    const body: AIProviderConfigWrite = {
      name: name.trim(),
      provider,
      model_name: modelName.trim(),
      credential_ref: credentialRef.trim(),
      base_url: baseUrl.trim() || null,
      temperature: temp,
      timeout_seconds: timeout,
      max_retries: retries,
      rate_limit_per_minute: rate,
      is_enabled: isEnabled,
      is_default: isDefault,
    };
    const res = await submit.run(body, idempotencyKey.current);
    if (res.ok) onDone();
  };

  return (
    <form className="form" onSubmit={handleSubmit}>
      <div className="grid-2">
        <label className="field">
          <span className="field__label">配置名称</span>
          <input className="input" required maxLength={120} value={name} onChange={(e) => setName(e.target.value)} placeholder="例如：DeepSeek 主配置" />
        </label>
        <label className="field">
          <span className="field__label">供应商（provider）</span>
          <select className="select" value={provider} onChange={(e) => setProvider(e.target.value as AIProviderType)}>
            {(Object.keys(AI_PROVIDER_LABELS) as AIProviderType[]).map((value) => (
              <option key={value} value={value}>{AI_PROVIDER_LABELS[value]}</option>
            ))}
          </select>
        </label>
      </div>

      <div className="grid-2">
        <label className="field">
          <span className="field__label">模型名（model_name）</span>
          <input className="input" required value={modelName} onChange={(e) => setModelName(e.target.value)} placeholder="例如 deepseek-chat" />
        </label>
        <label className="field">
          <span className="field__label">凭据环境变量名（credential_ref，不是密钥值）</span>
          <input className="input" required value={credentialRef} onChange={(e) => setCredentialRef(e.target.value)} placeholder="例如 AI_API_KEY" />
        </label>
      </div>

      <label className="field">
        <span className="field__label">自定义 Base URL（可选）</span>
        <input className="input" value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} placeholder="留空使用供应商默认地址" />
      </label>

      <div className="grid-2">
        <label className="field">
          <span className="field__label">temperature（0..2）</span>
          <input className="input" type="number" step="0.1" min="0" max="2" value={temperature} onChange={(e) => setTemperature(e.target.value)} />
        </label>
        <label className="field">
          <span className="field__label">超时秒数（&gt; 0）</span>
          <input className="input" type="number" min="1" value={timeoutSeconds} onChange={(e) => setTimeoutSeconds(e.target.value)} />
        </label>
        <label className="field">
          <span className="field__label">最大重试（≥ 0）</span>
          <input className="input" type="number" min="0" value={maxRetries} onChange={(e) => setMaxRetries(e.target.value)} />
        </label>
        <label className="field">
          <span className="field__label">每分钟限流（可选）</span>
          <input className="input" type="number" min="1" value={rateLimit} onChange={(e) => setRateLimit(e.target.value)} placeholder="留空表示不限" />
        </label>
      </div>

      <div className="row">
        <label className="row"><input type="checkbox" checked={isEnabled} onChange={(e) => setIsEnabled(e.target.checked)} /><span className="field__label">启用</span></label>
        <label className="row"><input type="checkbox" checked={isDefault} onChange={(e) => setIsDefault(e.target.checked)} /><span className="field__label">设为默认</span></label>
      </div>

      {localError && <div className="notice notice--error">{localError}</div>}
      {submit.error && <ErrorView error={submit.error} />}

      <div className="form-actions">
        <button className="btn btn--primary" type="submit" disabled={submit.pending}>
          {submit.pending ? '提交中…' : '创建 Provider'}
        </button>
        <button className="btn btn--ghost" type="button" onClick={onCancel}>取消</button>
      </div>
      <p className="muted text-xs">仅保存非敏感参数；是否允许产生计费调用由部署环境变量控制，不由前端决定。</p>
    </form>
  );
}
