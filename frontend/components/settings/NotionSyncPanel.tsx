'use client';

/**
 * Notion 同步状态（FE-07 / FR-01）。
 *
 * 真实端点：GET /notion/integrations、GET /notion/data-sources、GET /notion/sync-runs、
 *           POST /notion/data-sources/{id}/sync（Idempotency-Key，202 返回 SyncRunRead）。
 *
 * 未授权 / 未配置 Token 时同步接口返回 CONFIG_MISSING，页面如实展示错误，不伪造同步结果。
 * credential_ref 仅为环境变量名，页面绝不展示明文 Token。
 */

import { useState } from 'react';
import { api, newIdempotencyKey } from '@/lib/api';
import { useAsyncAction, useQuery } from '@/lib/hooks';
import { ErrorView, QueryView } from '@/components/States';
import { formatDateTime } from '@/lib/format';
import {
  NOTION_SOURCE_TYPE_LABELS,
  RUN_STATUS_LABELS,
  SYNC_TRIGGER_LABELS,
  runStatusTone,
} from '@/lib/labels';
import type {
  NotionDataSourceRead,
  NotionIntegrationRead,
  Page,
  SyncRunRead,
  UUID,
} from '@/types/api';

export function NotionSyncPanel() {
  const integrationsQuery = useQuery<Page<NotionIntegrationRead>>(
    () => api.listNotionIntegrations({ limit: 100 }),
    [],
  );
  const dataSourcesQuery = useQuery<Page<NotionDataSourceRead>>(
    () => api.listNotionDataSources({ limit: 100 }),
    [],
  );
  const syncRunsQuery = useQuery<Page<SyncRunRead>>(
    () => api.listSyncRuns({ limit: 20 }),
    [],
  );
  const syncAction = useAsyncAction((id: UUID, key: string) =>
    api.syncNotionDataSource(id, key),
  );
  const [lastRun, setLastRun] = useState<SyncRunRead | null>(null);

  const handleSync = async (source: NotionDataSourceRead) => {
    setLastRun(null);
    const res = await syncAction.run(source.id, newIdempotencyKey());
    if (res.ok) {
      setLastRun(res.value);
      syncRunsQuery.reload();
    }
  };

  return (
    <div className="stack">
      <div className="notice notice--info">
        Notion Integration 与数据源均为数据驱动配置。credential_ref 只是环境变量名，页面不展示明文 Token；
        未配置 Token 时触发同步会返回 <code>CONFIG_MISSING</code>，不会返回假的成功结果（FR-01）。
      </div>

      {syncAction.error && <ErrorView error={syncAction.error} />}
      {lastRun && (
        <div className="notice notice--info">
          已提交同步任务：operation 状态 <strong>{RUN_STATUS_LABELS[lastRun.status]}</strong>，
          运行 ID <code className="mono">{lastRun.id}</code>，触发方式 {SYNC_TRIGGER_LABELS[lastRun.trigger_type]}。
          202 仅代表任务已创建，最终结果以同步运行记录为准。
        </div>
      )}

      <div className="card">
        <div className="card__head">
          <span className="card__title">Notion 集成</span>
          <button type="button" className="btn btn--ghost btn--sm" onClick={integrationsQuery.reload}>刷新</button>
        </div>
        <QueryView
          state={integrationsQuery.state}
          onRetry={integrationsQuery.reload}
          isEmpty={(page) => page.items.length === 0}
          emptyText="尚未配置 Notion 集成"
          emptyHint="未配置时同步与抽取链路会明确报错（CONFIG_MISSING），此处不显示「已连接」。"
        >
          {(page) => (
            <div className="list">
              {page.items.map((integration) => (
                <div className="list-item" key={integration.id}>
                  <div className="list-item__title">
                    {integration.name}
                    {' '}
                    <span className={`badge badge--${integration.is_enabled ? 'ok' : 'muted'}`}>
                      {integration.is_enabled ? '启用' : '已停用'}
                    </span>
                  </div>
                  <div className="list-item__meta">
                    <span>环境变量名 <code className="mono">{integration.credential_ref}</code></span>
                    <span>API 版本 {integration.api_version}</span>
                    <span>上次校验 {formatDateTime(integration.last_validated_at)}</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </QueryView>
      </div>

      <div className="card">
        <div className="card__head">
          <span className="card__title">数据源与手动同步</span>
          <button type="button" className="btn btn--ghost btn--sm" onClick={dataSourcesQuery.reload}>刷新</button>
        </div>
        <QueryView
          state={dataSourcesQuery.state}
          onRetry={dataSourcesQuery.reload}
          isEmpty={(page) => page.items.length === 0}
          emptyText="尚未配置数据源"
          emptyHint="配置集成与数据源后，可在此手动触发增量同步。"
        >
          {(page) => (
            <div className="list">
              {page.items.map((source) => (
                <div className="list-item" key={source.id}>
                  <div className="list-item__title">
                    {source.name}
                    {' '}
                    <span className={`badge badge--${source.is_enabled ? 'ok' : 'muted'}`}>
                      {source.is_enabled ? '启用' : '已停用'}
                    </span>
                  </div>
                  <div className="list-item__meta">
                    <span className="pill">{NOTION_SOURCE_TYPE_LABELS[source.source_type]}</span>
                    <span>外部 ID <code className="mono">{source.external_source_id}</code></span>
                    <span>间隔 {source.sync_interval_minutes} 分钟</span>
                  </div>
                  <div className="list-item__meta mt-6">
                    <span>同步水位 {formatDateTime(source.last_edited_watermark)}</span>
                    <span>下次同步 {formatDateTime(source.next_sync_at)}</span>
                  </div>
                  <div className="mini-actions mt-6">
                    <button
                      type="button"
                      className="btn btn--sm"
                      disabled={syncAction.pending}
                      onClick={() => handleSync(source)}
                    >
                      立即同步
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </QueryView>
      </div>

      <div className="card">
        <div className="card__head">
          <span className="card__title">同步运行记录</span>
          <button type="button" className="btn btn--ghost btn--sm" onClick={syncRunsQuery.reload}>刷新</button>
        </div>
        <QueryView
          state={syncRunsQuery.state}
          onRetry={syncRunsQuery.reload}
          isEmpty={(page) => page.items.length === 0}
          emptyText="暂无同步运行记录"
          emptyHint="手动或定时触发同步后，运行记录由 GET /notion/sync-runs 返回。"
        >
          {(page) => (
            <div className="list">
              {page.items.map((run) => (
                <div className="list-item" key={run.id}>
                  <div className="list-item__title">
                    <span className={`badge badge--${runStatusTone(run.status)}`}>
                      {RUN_STATUS_LABELS[run.status]}
                    </span>
                    {' '}
                    {SYNC_TRIGGER_LABELS[run.trigger_type]} · 第 {run.attempt} 次尝试
                  </div>
                  <div className="list-item__meta">
                    <span>读取 {run.items_seen}</span>
                    <span>导入 {run.items_imported}</span>
                    <span>失败 {run.items_failed}</span>
                    <span>开始 {formatDateTime(run.started_at)}</span>
                    <span>结束 {formatDateTime(run.finished_at)}</span>
                  </div>
                  {(run.error_code || run.error_message) && (
                    <div className="notice notice--error mt-6">
                      错误码 {run.error_code ?? '—'}：{run.error_message ?? '无附加说明'}
                    </div>
                  )}
                  <div className="list-item__meta mt-6">
                    <span>水位 {formatDateTime(run.watermark_from)} → {formatDateTime(run.watermark_to)}</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </QueryView>
      </div>
    </div>
  );
}
