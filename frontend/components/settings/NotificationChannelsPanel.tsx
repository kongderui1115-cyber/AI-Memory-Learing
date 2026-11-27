'use client';

/**
 * 通知渠道配置入口（FE-07 / FR-07 / FR-08）。
 *
 * 真实端点：GET/POST /notification/channels、POST /notification/channels/{id}/validate、
 *           GET /notification/templates。
 *
 * 安全：credential_ref 只是「环境变量名」，不是密钥值；页面只展示该名称，绝不展示或接收明文密钥。
 * 未配置凭据时 validate 返回真实的 CONFIG_MISSING，本页如实展示错误，不伪造"已连接"。
 */

import { useRef, useState } from 'react';
import type { FormEvent } from 'react';
import { api, newIdempotencyKey } from '@/lib/api';
import { useAsyncAction, useQuery } from '@/lib/hooks';
import { ErrorView, QueryView } from '@/components/States';
import { parseJsonObject } from '@/lib/format';
import { CHANNEL_TYPE_LABELS } from '@/lib/labels';
import type {
  ChannelConfigRead,
  ChannelConfigWrite,
  ChannelValidation,
  NotificationChannelType,
  Page,
  TemplateRead,
  UUID,
} from '@/types/api';

export function NotificationChannelsPanel() {
  const channelsQuery = useQuery<Page<ChannelConfigRead>>(
    () => api.listNotificationChannels({ limit: 100 }),
    [],
  );
  const templatesQuery = useQuery<Page<TemplateRead>>(
    () => api.listTemplates({ limit: 100 }),
    [],
  );
  const [creating, setCreating] = useState(false);
  const [validation, setValidation] = useState<Record<string, ChannelValidation>>({});
  const validateAction = useAsyncAction((id: UUID, key: string) =>
    api.validateNotificationChannel(id, key),
  );

  const handleValidate = async (channel: ChannelConfigRead) => {
    const res = await validateAction.run(channel.id, newIdempotencyKey());
    if (res.ok) setValidation((current) => ({ ...current, [channel.id]: res.value }));
  };

  const handleCreate = async (body: ChannelConfigWrite, key: string) => {
    await api.createNotificationChannel(body, key);
  };

  return (
    <div className="stack">
      <div className="notice notice--info">
        密钥仅存环境变量 / 密钥文件，页面只展示 <code>credential_ref</code>（环境变量名），绝不展示或接收明文密钥。
        个人微信没有官方主动推送 API；未配置凭据时验证接口返回 <code>CONFIG_MISSING</code>，不会伪发送、也不会显示「已连接」。
      </div>

      <div className="card">
        <div className="card__head">
          <span className="card__title">通知渠道</span>
          <button type="button" className="btn btn--primary btn--sm" onClick={() => setCreating((v) => !v)}>
            {creating ? '收起表单' : '新增渠道'}
          </button>
        </div>
        <div className="card__body">
          {creating && (
            <ChannelCreateForm
              onSubmit={handleCreate}
              onDone={() => { setCreating(false); channelsQuery.reload(); }}
              onCancel={() => setCreating(false)}
            />
          )}
          {validateAction.error && <ErrorView error={validateAction.error} />}
        </div>
      </div>

      <div className="card">
        <div className="card__head">
          <span className="card__title">渠道列表</span>
          <button type="button" className="btn btn--ghost btn--sm" onClick={channelsQuery.reload}>刷新</button>
        </div>
        <QueryView
          state={channelsQuery.state}
          onRetry={channelsQuery.reload}
          isEmpty={(page) => page.items.length === 0}
          emptyText="尚未配置任何通知渠道"
          emptyHint="未配置凭据时相关功能会明确报错（CONFIG_MISSING），此处不伪造「已连接」状态。"
        >
          {(page) => (
            <div className="list">
              {page.items.map((channel) => (
                <div className="list-item" key={channel.id}>
                  <div className="list-item__title">
                    {channel.name}
                    {' '}
                    <span className={`badge badge--${channel.is_enabled ? 'ok' : 'muted'}`}>
                      {channel.is_enabled ? '启用' : '已停用'}
                    </span>
                    {channel.is_default && <span className="badge badge--info">默认</span>}
                  </div>
                  <div className="list-item__meta">
                    <span className="pill">{CHANNEL_TYPE_LABELS[channel.channel_type]}</span>
                    <span>环境变量名 <code className="mono">{channel.credential_ref}</code></span>
                    <span>版本 {channel.version}</span>
                  </div>
                  <p className="muted text-xs mt-6">
                    settings（非密钥）：<code className="mono">{JSON.stringify(channel.settings)}</code>
                  </p>
                  <div className="mini-actions mt-6">
                    <button
                      type="button"
                      className="btn btn--sm"
                      disabled={validateAction.pending}
                      onClick={() => handleValidate(channel)}
                    >
                      验证配置
                    </button>
                    {validation[channel.id] && (
                      <span className={`badge badge--${validation[channel.id].valid ? 'ok' : 'danger'}`}>
                        验证结果：{validation[channel.id].valid ? '有效' : '无效'}（{validation[channel.id].channel_type}）
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
          <span className="card__title">通知模板</span>
          <button type="button" className="btn btn--ghost btn--sm" onClick={templatesQuery.reload}>刷新</button>
        </div>
        <QueryView
          state={templatesQuery.state}
          onRetry={templatesQuery.reload}
          isEmpty={(page) => page.items.length === 0}
          emptyText="暂无通知模板"
          emptyHint="模板由 GET /notification/templates 返回；未配置时如实显示为空。"
        >
          {(page) => (
            <div className="list">
              {page.items.map((template) => (
                <div className="list-item" key={template.id}>
                  <div className="list-item__title">
                    <code className="mono">{template.template_key}</code>
                    {' '}
                    <span className={`badge badge--${template.is_active ? 'ok' : 'muted'}`}>
                      {template.is_active ? '启用' : '停用'}
                    </span>
                  </div>
                  <div className="list-item__meta">
                    <span className="pill">{CHANNEL_TYPE_LABELS[template.channel_type]}</span>
                    <span>标题模板：{template.title_template}</span>
                    {template.max_length != null && <span>长度上限 {template.max_length}</span>}
                  </div>
                  {template.schema_variables.length > 0 && (
                    <div className="tag-list mt-6">
                      {template.schema_variables.map((variable) => <span className="tag" key={variable}>{variable}</span>)}
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

interface ChannelCreateFormProps {
  onSubmit: (body: ChannelConfigWrite, key: string) => Promise<unknown>;
  onDone: () => void;
  onCancel: () => void;
}

function ChannelCreateForm({ onSubmit, onDone, onCancel }: ChannelCreateFormProps) {
  const [name, setName] = useState('');
  const [channelType, setChannelType] = useState<NotificationChannelType>('wecom_app');
  const [credentialRef, setCredentialRef] = useState('');
  const [settingsText, setSettingsText] = useState('{}');
  const [isEnabled, setIsEnabled] = useState(true);
  const [isDefault, setIsDefault] = useState(false);
  const [localError, setLocalError] = useState<string | null>(null);

  const submit = useAsyncAction((body: ChannelConfigWrite, key: string) => onSubmit(body, key));
  const idempotencyKey = useRef(newIdempotencyKey());

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    let settings: Record<string, unknown>;
    try {
      settings = parseJsonObject(settingsText);
    } catch (e) {
      setLocalError(e instanceof Error ? e.message : String(e));
      return;
    }
    setLocalError(null);
    const body: ChannelConfigWrite = {
      name: name.trim(),
      channel_type: channelType,
      credential_ref: credentialRef.trim(),
      settings,
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
          <span className="field__label">渠道名称</span>
          <input className="input" required maxLength={120} value={name} onChange={(e) => setName(e.target.value)} placeholder="例如：企业微信复习提醒" />
        </label>
        <label className="field">
          <span className="field__label">渠道类型</span>
          <select className="select" value={channelType} onChange={(e) => setChannelType(e.target.value as NotificationChannelType)}>
            {(Object.keys(CHANNEL_TYPE_LABELS) as NotificationChannelType[]).map((value) => (
              <option key={value} value={value}>{CHANNEL_TYPE_LABELS[value]}</option>
            ))}
          </select>
        </label>
      </div>

      <label className="field">
        <span className="field__label">凭据环境变量名（credential_ref，不是密钥值）</span>
        <input className="input" required value={credentialRef} onChange={(e) => setCredentialRef(e.target.value)} placeholder="例如 WECOM_AGENT_SECRET" />
        <span className="field__hint">只填环境变量名；真实密钥由部署环境提供，绝不写入数据库或本表单。</span>
      </label>

      <label className="field">
        <span className="field__label">渠道设置（settings，JSON 对象，不得含密钥）</span>
        <textarea className="textarea mono" value={settingsText} onChange={(e) => setSettingsText(e.target.value)} />
      </label>

      <div className="row">
        <label className="row"><input type="checkbox" checked={isEnabled} onChange={(e) => setIsEnabled(e.target.checked)} /><span className="field__label">启用</span></label>
        <label className="row"><input type="checkbox" checked={isDefault} onChange={(e) => setIsDefault(e.target.checked)} /><span className="field__label">设为默认</span></label>
      </div>

      {localError && <div className="notice notice--error">{localError}</div>}
      {submit.error && <ErrorView error={submit.error} />}

      <div className="form-actions">
        <button className="btn btn--primary" type="submit" disabled={submit.pending}>
          {submit.pending ? '提交中…' : '创建渠道'}
        </button>
        <button className="btn btn--ghost" type="button" onClick={onCancel}>取消</button>
      </div>
      <p className="muted text-xs">settings 初始值可通过 JSON 编辑；此处仅保存非敏感参数。</p>
    </form>
  );
}
