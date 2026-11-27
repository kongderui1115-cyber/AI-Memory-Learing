/** 客户端数据获取与动作状态管理（真实请求，无假数据兜底）。 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { DependencyList } from 'react';
import { api, toApiError, type ApiError } from '@/lib/api';
import type { Page, SubjectRead, UUID } from '@/types/api';

export type QueryState<T> =
  | { status: 'loading' }
  | { status: 'success'; data: T }
  | { status: 'error'; error: ApiError };

export interface QueryResult<T> {
  state: QueryState<T>;
  /** 重新发起请求（刷新）。 */
  reload: () => void;
}

/**
 * 加载异步数据的通用 hook。
 * - status='loading'：真实请求进行中；
 * - status='error'：真实请求失败，error 为归一化后的 ApiError；
 * - status='success'：真实响应数据。
 * loader 始终取最新引用，但只在 deps 或 reload 变化时重新执行。
 */
export function useQuery<T>(loader: () => Promise<T>, deps: DependencyList): QueryResult<T> {
  const loaderRef = useRef(loader);
  loaderRef.current = loader;
  const [state, setState] = useState<QueryState<T>>({ status: 'loading' });
  const [nonce, setNonce] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setState({ status: 'loading' });
    loaderRef.current().then(
      (data) => {
        if (!cancelled) setState({ status: 'success', data });
      },
      (err: unknown) => {
        if (!cancelled) setState({ status: 'error', error: toApiError(err) });
      },
    );
    return () => {
      cancelled = true;
    };
    // deps 由调用方给出并保持不变；nonce 驱动手动刷新。
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, nonce]);

  const reload = useCallback(() => setNonce((n) => n + 1), []);
  return { state, reload };
}

/** 学科列表 + id→名称映射，供筛选与展示复用。 */
export function useSubjects() {
  const query = useQuery<Page<SubjectRead>>(() => api.listSubjects({ limit: 100 }), []);
  const map = useMemo(() => {
    const m = new Map<UUID, string>();
    if (query.state.status === 'success') {
      for (const subject of query.state.data.items) m.set(subject.id, subject.name);
    }
    return m;
  }, [query.state]);
  return { state: query.state, map, reload: query.reload };
}

export type ActionResult<T> = { ok: true; value: T } | { ok: false; error: ApiError };

/**
 * 提交类动作的状态管理：pending / error，以及不抛异常的 run。
 * run 返回判别联合，调用方用 `if (result.ok)` 判断成功，错误同时保留在 error 状态里供 UI 展示。
 */
export function useAsyncAction<TArgs extends unknown[], TResult>(
  action: (...args: TArgs) => Promise<TResult>,
) {
  const actionRef = useRef(action);
  actionRef.current = action;
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);

  const run = useCallback(async (...args: TArgs): Promise<ActionResult<TResult>> => {
    setPending(true);
    setError(null);
    try {
      const value = await actionRef.current(...args);
      return { ok: true, value };
    } catch (e) {
      const err = toApiError(e);
      setError(err);
      return { ok: false, error: err };
    } finally {
      setPending(false);
    }
  }, []);

  const reset = useCallback(() => setError(null), []);
  return { pending, error, run, reset };
}
