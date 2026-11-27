/** 与契约无关的纯展示格式化工具（全中文输出）。 */

import type { DateTime, DateOnly } from '@/types/api';

/** 以浏览器本地时区生成 YYYY-MM-DD。复习与统计的“今天”应优先使用账号时区。 */
export function todayLocalDate(): DateOnly {
  const now = new Date();
  const y = now.getFullYear();
  const m = String(now.getMonth() + 1).padStart(2, '0');
  const d = String(now.getDate()).padStart(2, '0');
  return `${y}-${m}-${d}`;
}

/** 浏览器 IANA 时区名，用于 timezone 参数。 */
export function localTimezone(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC';
  } catch {
    return 'UTC';
  }
}

/** 当前 UTC RFC3339 时间，用于 reviewed_at 等字段。 */
export function nowIso(): DateTime {
  return new Date().toISOString();
}

/** UTC RFC3339 → 本地时区的中文可读时间；空值返回破折号。 */
export function formatDateTime(value: DateTime | null | undefined): string {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date);
}

/** YYYY-MM-DD（或 RFC3339）→ 中文日期。 */
export function formatDate(value: DateOnly | DateTime | null | undefined): string {
  if (!value) return '—';
  const date = new Date(value.length === 10 ? `${value}T00:00:00` : value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(date);
}

export function formatDuration(seconds: number): string {
  const s = Math.max(0, Math.round(seconds));
  if (s < 60) return `${s} 秒`;
  const m = Math.floor(s / 60);
  const rest = s % 60;
  return rest === 0 ? `${m} 分钟` : `${m} 分 ${rest} 秒`;
}

export function formatPercent(value: number): string {
  return `${(value * 100).toFixed(1)}%`;
}

/** 把逗号/顿号/空白分隔的输入拆成去重后的数组，用于 tags / keywords。 */
export function splitList(input: string): string[] {
  const parts = input.split(/[,，、;；\s]+/).map((s) => s.trim()).filter(Boolean);
  return Array.from(new Set(parts));
}

/** 账号时区的 YYYY-MM-DD。未配置或时区名无效时回退到浏览器本地日期。 */
export function accountDate(timeZone: string | null | undefined, now = new Date()): DateOnly {
  if (!timeZone) return todayLocalDate();
  try {
    return new Intl.DateTimeFormat('en-CA', {
      timeZone,
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
    }).format(now);
  } catch {
    return todayLocalDate();
  }
}

function shiftIsoDate(iso: DateOnly, deltaDays: number): DateOnly {
  const [year, month, day] = iso.split('-').map(Number);
  const utc = new Date(Date.UTC(year, (month || 1) - 1, day || 1));
  utc.setUTCDate(utc.getUTCDate() + deltaDays);
  const y = utc.getUTCFullYear();
  const m = String(utc.getUTCMonth() + 1).padStart(2, '0');
  const d = String(utc.getUTCDate()).padStart(2, '0');
  return `${y}-${m}-${d}`;
}

/** 以账号时区的今天为结束日期，按日历天返回最近 days 天。 */
export function accountDateRange(
  days: number,
  timeZone: string | null | undefined,
  now = new Date(),
): { from: DateOnly; to: DateOnly } {
  const to = accountDate(timeZone, now);
  const span = Math.max(1, Math.floor(days)) - 1;
  return { from: shiftIsoDate(to, -span), to };
}

/** 以今天为结束日期，返回最近 days 天的 [from, to]（均为 YYYY-MM-DD，本地时区）。 */
export function localDateRange(days: number): { from: DateOnly; to: DateOnly } {
  const to = todayLocalDate();
  const end = new Date();
  const start = new Date(end);
  start.setDate(start.getDate() - (Math.max(1, Math.floor(days)) - 1));
  const from = `${start.getFullYear()}-${String(start.getMonth() + 1).padStart(2, '0')}-${String(start.getDate()).padStart(2, '0')}`;
  return { from, to };
}

/** 解析 JSON 对象文本；空串视为 {}；非对象或格式错误时抛出中文错误。 */
export function parseJsonObject(input: string): Record<string, unknown> {
  const trimmed = input.trim();
  if (!trimmed) return {};
  let parsed: unknown;
  try {
    parsed = JSON.parse(trimmed) as unknown;
  } catch {
    throw new Error('请输入合法的 JSON，例如 {"key": "value"}');
  }
  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
    throw new Error('请输入 JSON 对象（不能是数组或标量）');
  }
  return parsed as Record<string, unknown>;
}

/** 解析 dict[str, str] 形态的 JSON（如术语表），值必须是字符串。 */
export function parseStringMap(input: string): Record<string, string> {
  const obj = parseJsonObject(input);
  const out: Record<string, string> = {};
  for (const [key, value] of Object.entries(obj)) {
    if (typeof value !== 'string') {
      throw new Error(`术语「${key}」的值必须是字符串`);
    }
    out[key] = value;
  }
  return out;
}

/** 把对象格式化为便于阅读/编辑的 JSON 文本。 */
export function stringifyJson(value: unknown): string {
  return JSON.stringify(value ?? {}, null, 2);
}
