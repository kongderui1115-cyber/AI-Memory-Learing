'use client';

/**
 * 通用状态视图：加载中 / 错误 / 空状态。
 * 三者都对应真实请求状态，不提供任何硬编码的假数据兜底。
 */

import type { ReactNode } from 'react';
import type { ApiError } from '@/lib/api';
import type { QueryState } from '@/lib/hooks';
import { useAuth } from './AuthProvider';

export function Loading({ text = '加载中…' }: { text?: string }) {
  return (
    <div className="state state--loading" role="status">
      <span className="spinner" aria-hidden="true" />
      <span>{text}</span>
    </div>
  );
}

export function EmptyView({
  text,
  hint,
  action,
}: {
  text: string;
  hint?: string;
  action?: ReactNode;
}) {
  return (
    <div className="state state--empty">
      <p className="state__title">{text}</p>
      {hint && <p className="state__hint">{hint}</p>}
      {action && <div className="state__action">{action}</div>}
    </div>
  );
}

export function ErrorView({
  error,
  onRetry,
  showRelogin = true,
}: {
  error: ApiError;
  onRetry?: () => void;
  showRelogin?: boolean;
}) {
  const { signOut } = useAuth();
  return (
    <div className="state state--error" role="alert">
      <p className="state__title">请求失败</p>
      <p className="state__hint">{error.message}</p>
      <dl className="error-meta">
        <div>
          <dt>错误码</dt>
          <dd><code>{error.code}</code></dd>
        </div>
        <div>
          <dt>状态</dt>
          <dd>{error.status ? `HTTP ${error.status}` : '网络 / 本地错误'}</dd>
        </div>
        {error.requestId && (
          <div>
            <dt>请求 ID</dt>
            <dd><code>{error.requestId}</code></dd>
          </div>
        )}
      </dl>
      {error.details.length > 0 && (
        <ul className="error-details">
          {error.details.map((detail, index) => (
            <li key={`${detail.field}-${index}`}>
              <code>{detail.field ?? '请求体'}</code>：{detail.reason}
            </li>
          ))}
        </ul>
      )}
      <div className="state__action">
        {onRetry && (
          <button type="button" className="btn btn--primary" onClick={onRetry}>
            重试
          </button>
        )}
        {showRelogin && error.isAuthError && (
          <button type="button" className="btn btn--ghost" onClick={signOut}>
            重新登录
          </button>
        )}
      </div>
    </div>
  );
}

/** 把 QueryState 映射为加载中 / 错误 / 空 / 真实数据四种视图。 */
export function QueryView<T>({
  state,
  onRetry,
  isEmpty,
  emptyText = '暂无数据',
  emptyHint,
  emptyAction,
  children,
}: {
  state: QueryState<T>;
  onRetry?: () => void;
  isEmpty?: (data: T) => boolean;
  emptyText?: string;
  emptyHint?: string;
  emptyAction?: ReactNode;
  children: (data: T) => ReactNode;
}) {
  if (state.status === 'loading') return <Loading />;
  if (state.status === 'error') return <ErrorView error={state.error} onRetry={onRetry} />;
  if (isEmpty && isEmpty(state.data)) {
    return <EmptyView text={emptyText} hint={emptyHint} action={emptyAction} />;
  }
  return <>{children(state.data)}</>;
}
