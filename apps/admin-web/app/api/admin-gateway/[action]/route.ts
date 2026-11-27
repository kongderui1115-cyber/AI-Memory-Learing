import { NextRequest, NextResponse } from "next/server";

export const dynamic = "force-dynamic";

const COOKIE = "memory_admin_session";
const COOKIE_PATH = "/api/admin-gateway";
const userIdPattern = /^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i;
const readRoutes = {
  session: ["/me", []],
  overview: ["/admin/overview", []],
  analytics: ["/admin/analytics", ["days", "from_date", "to_date"]],
  audit: ["/admin/audit-events", ["limit", "cursor", "user_id", "severity", "action", "from", "to"]],
  users: ["/admin/users", ["limit", "cursor", "q"]],
  sessions: ["/admin/sessions", ["limit", "cursor", "user_id", "online", "from", "to"]],
  health: ["/health/ready", []],
  "model-providers": ["/admin/model-providers", ["limit", "cursor", "user_id"]],
  "memory-policies": ["/admin/memory/policies", ["limit", "cursor", "user_id"]],
  sources: ["/admin/sources", ["limit", "cursor", "user_id"]],
  "notification-channels": ["/admin/notification-channels", ["limit", "cursor", "user_id"]],
  "notification-deliveries": ["/admin/notification-deliveries", ["limit", "cursor", "user_id", "channel_id", "status"]],
  jobs: ["/admin/jobs", ["limit", "cursor", "user_id", "kind", "status"]],
  telemetry: ["/admin/telemetry", ["minutes"]],
  "system-info": ["/admin/system/info", []],
  backups: ["/admin/backups", []],
} as const;
const resourceReads = {
  "model-readiness": ["/admin/model-providers/", "/readiness", []],
  "source-runs": ["/admin/sources/", "/runs", ["limit", "cursor"]],
} as const;
const userRoutes = {
  "user-overview": "overview",
  "user-knowledge": "knowledge-points",
  "user-history": "review-history",
} as const;
const noCache = { "Cache-Control": "no-store" };

function reply(body: unknown, status = 200) {
  return NextResponse.json(body, { status, headers: noCache });
}

function failure(status: number) {
  const messages: Record<number, string> = {
    400: "请检查表单内容。",
    401: "登录凭据无效或会话已过期。",
    403: "需要管理员权限或同源控制台请求。",
    404: "此管理员接口尚未开放。",
    409: "该邮箱已存在或记录已更新，请刷新后核对。",
    412: "记录已更新，请刷新后重试。",
    413: "表单内容过长。",
    422: "表单或筛选参数不符合要求。",
    429: "登录尝试过多，请稍后再试。",
    502: "统一 API 返回了无法处理的响应。",
    503: "统一 API 暂时无法连接，请稍后重试。",
  };
  return reply({ error: { message: messages[status] ?? messages[502] } }, status in messages ? status : 502);
}

type RouteContext = { params: Promise<{ action: string }> };

function cookieSettings(request: NextRequest) {
  return {
    name: COOKIE,
    httpOnly: true,
    secure: process.env.ADMIN_COOKIE_SECURE === "true" || request.nextUrl.protocol === "https:",
    sameSite: "strict" as const,
    path: COOKIE_PATH,
  };
}

function clearCookie(request: NextRequest, response: NextResponse) {
  response.cookies.set({ ...cookieSettings(request), value: "", maxAge: 0 });
  return response;
}

function backend(path: string, options: {
  token?: string;
  body?: unknown;
  method?: "GET" | "POST" | "PATCH";
  userAgent?: string;
  idempotencyKey?: string;
  ifMatch?: string;
  timeout?: number;
} = {}) {
  const base = new URL(process.env.ADMIN_BACKEND_URL ?? "http://127.0.0.1:8000");
  if (!["http:", "https:"].includes(base.protocol) || base.username || base.password) throw new Error("Invalid backend origin");
  const headers = new Headers({ Accept: "application/json" });
  if (options.token) headers.set("Authorization", "Bearer " + options.token);
  if (options.userAgent) headers.set("User-Agent", options.userAgent);
  if (options.idempotencyKey) headers.set("Idempotency-Key", options.idempotencyKey);
  if (options.ifMatch) headers.set("If-Match", options.ifMatch);
  if (options.body !== undefined) headers.set("Content-Type", "application/json");
  return fetch(new URL("/api/v1" + path, base.origin), {
    method: options.method ?? "GET",
    headers,
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
    cache: "no-store",
    redirect: "error",
    signal: AbortSignal.timeout(options.timeout ?? 8000),
  });
}

async function requireAdmin(token: string) {
  const upstream = await backend("/me", { token });
  if (!upstream.ok) return { error: failure(upstream.status) };
  const user = await upstream.json();
  if (user.role !== "admin" || user.is_active !== true) return { error: failure(403) };
  const { id, email, display_name, timezone, role, is_active, created_at, updated_at, version } = user;
  return { user: { id, email, display_name, timezone, role, is_active, created_at, updated_at, version } };
}

async function parseBody(request: NextRequest) {
  if (!request.headers.get("content-type")?.toLowerCase().startsWith("application/json")) return undefined;
  if (Number(request.headers.get("content-length")) > 8192 || !request.body) return undefined;
  const reader = request.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let length = 0;
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      length += value.byteLength;
      if (length > 8192) {
        await reader.cancel();
        return undefined;
      }
      buffer += decoder.decode(value, { stream: true });
    }
    const body: unknown = JSON.parse(buffer + decoder.decode());
    if (body && typeof body === "object" && !Array.isArray(body)) return body as Record<string, unknown>;
  } catch {
    return undefined;
  } finally {
    reader.releaseLock();
  }
}

function isPassword(value: unknown, minimum: number): value is string {
  return typeof value === "string" && value.length >= minimum && value.length <= 256;
}

function consoleOrigin(request: NextRequest) {
  if (process.env.ADMIN_PUBLIC_ORIGIN) return process.env.ADMIN_PUBLIC_ORIGIN;
  const host = request.headers.get("host");
  if (host && /^(localhost|127\.0\.0\.1)(:\d{1,5})?$/i.test(host)) return "http://" + host;
  return null;
}

function isConsoleMutation(request: NextRequest) {
  const expectedOrigin = consoleOrigin(request);
  return Boolean(expectedOrigin && request.headers.get("origin") === expectedOrigin && request.headers.get("x-admin-client") === "console");
}

function displayName(value: unknown): string | undefined {
  if (typeof value !== "string") return undefined;
  const name = value.trim();
  return name && name.length <= 120 ? name : undefined;
}

function resourceId(request: NextRequest) {
  const id = request.nextUrl.searchParams.get("resource_id");
  return id && userIdPattern.test(id) ? id : null;
}

function operationKey(request: NextRequest) {
  const key = request.headers.get("idempotency-key");
  return key && key.length <= 128 && key.trim() ? key : undefined;
}

async function createUser(request: NextRequest, token: string) {
  const body = await parseBody(request);
  const key = operationKey(request);
  const name = displayName(body?.display_name);
  if (!body || !name || !key ||
      typeof body.email !== "string" || !body.email.trim() || body.email.length > 254 ||
      !isPassword(body.password, 10) || body.password.trim().length < 10 ||
      typeof body.timezone !== "string" || !body.timezone.trim() || body.timezone.length > 100) return failure(400);
  const upstream = await backend("/admin/users", {
    method: "POST",
    token,
    idempotencyKey: key,
    body: { display_name: name, email: body.email.trim(), password: body.password, timezone: body.timezone.trim(), role: "user" },
  });
  return upstream.ok ? reply(await upstream.json(), upstream.status) : failure(upstream.status);
}

export async function GET(request: NextRequest, { params }: RouteContext) {
  const { action } = await params;
  const userRoute = Object.hasOwn(userRoutes, action) ? userRoutes[action as keyof typeof userRoutes] : undefined;
  const resourceRoute = Object.hasOwn(resourceReads, action) ? resourceReads[action as keyof typeof resourceReads] : undefined;
  if (!userRoute && !resourceRoute && !Object.hasOwn(readRoutes, action)) return failure(404);
  const token = request.cookies.get(COOKIE)?.value;
  if (!token) return failure(401);
  try {
    if (action === "session" || action === "health") {
      const result = await requireAdmin(token);
      if (result.error) return result.error;
      if (action === "session") return reply(result.user);

      const upstream = await backend("/health/ready");
      if (!upstream.ok && upstream.status !== 503) return failure(upstream.status);
      const state = await upstream.json();
      const config = state.checks?.config;
      const database = state.checks?.database;
      return reply({
        status: upstream.ok ? "ready" : "unavailable",
        checks: {
          config: config ? { status: config.status === "ok" ? "ok" : "error" } : undefined,
          database: database ? { status: database.status === "ok" ? "ok" : "error", migration: database.migration } : undefined,
        },
      }, upstream.status);
    }

    let path: string;
    let allowed: readonly string[];
    if (userRoute) {
      const userId = request.nextUrl.searchParams.get("user_id");
      if (!userId || !userIdPattern.test(userId)) return failure(400);
      path = "/admin/users/" + userId + "/" + userRoute;
      allowed = userRoute === "overview" ? [] : ["limit", "cursor"];
    } else if (resourceRoute) {
      const id = resourceId(request);
      if (!id) return failure(400);
      path = resourceRoute[0] + id + resourceRoute[1];
      allowed = resourceRoute[2];
    } else {
      [path, allowed] = readRoutes[action as keyof typeof readRoutes];
    }
    const query = new URLSearchParams();
    for (const key of allowed) {
      const value = request.nextUrl.searchParams.get(key);
      if (value && value.length <= 4096) query.set(key, value);
    }
    const upstream = await backend(path + (query.size ? "?" + query.toString() : ""), { token });
    return upstream.ok ? reply(await upstream.json(), upstream.status) : failure(upstream.status);
  } catch {
    return failure(503);
  }
}

export async function POST(request: NextRequest, { params }: RouteContext) {
  const { action } = await params;
  if (!["login", "logout", "password", "users", "memory-simulations", "source-sync", "backups"].includes(action)) return failure(404);
  if (!isConsoleMutation(request)) return failure(403);

  try {
    if (action === "login") {
      const body = await parseBody(request);
      if (!body || typeof body.email !== "string" || body.email.length > 254 || !isPassword(body.password, 8)) return failure(400);
      const response = await backend("/auth/token", {
        method: "POST",
        body: { email: body.email.trim(), password: body.password },
        userAgent: request.headers.get("user-agent") ?? undefined,
      });
      if (!response.ok) return failure(response.status);
      const { access_token: token, expires_in_seconds: seconds } = await response.json();
      if (typeof token !== "string" || !Number.isSafeInteger(seconds) || seconds < 1) return failure(502);

      const result = await requireAdmin(token);
      if (result.error) {
        await backend("/auth/logout", { method: "POST", token }).catch(() => undefined);
        return result.error;
      }

      const login = reply(result.user);
      login.cookies.set({ ...cookieSettings(request), value: token, maxAge: seconds });
      return login;
    }

    const token = request.cookies.get(COOKIE)?.value;
    if (action === "logout") {
      const upstream = token ? await backend("/auth/logout", { method: "POST", token }) : undefined;
      if (upstream && !upstream.ok && upstream.status !== 401 && upstream.status !== 403) return failure(upstream.status);
      return clearCookie(request, new NextResponse(null, { status: 204, headers: noCache }));
    }

    if (!token) return failure(401);
    if (action === "users") return await createUser(request, token);
    if (action === "memory-simulations") {
      const body = await parseBody(request);
      if (!body) return failure(400);
      const { strategy, intervals_days, target_retention, ratings } = body;
      const upstream = await backend("/admin/memory/simulations", { method: "POST", token, body: { strategy, intervals_days, target_retention, ratings } });
      return upstream.ok ? reply(await upstream.json(), upstream.status) : failure(upstream.status);
    }
    if (action === "source-sync" || action === "backups") {
      const key = operationKey(request);
      if (!key) return failure(400);
      const id = action === "source-sync" ? resourceId(request) : null;
      if (action === "source-sync" && !id) return failure(400);
      const path = id ? "/admin/sources/" + id + "/sync" : "/admin/backups";
      const upstream = await backend(path, { method: "POST", token, idempotencyKey: key, timeout: id ? undefined : 120000 });
      return upstream.ok ? reply(await upstream.json(), upstream.status) : failure(upstream.status);
    }
    const result = await requireAdmin(token);
    if (result.error) return result.error;
    const body = await parseBody(request);
    if (!body || !isPassword(body.current_password, 1) || !isPassword(body.new_password, 10) || body.new_password.trim().length < 10) return failure(400);
    const upstream = await backend("/auth/password", {
      method: "POST",
      token,
      body: { current_password: body.current_password, new_password: body.new_password },
    });
    if (!upstream.ok) return failure(upstream.status);
    return clearCookie(request, new NextResponse(null, { status: 204, headers: noCache }));
  } catch {
    return failure(503);
  }
}

export async function PATCH(request: NextRequest, { params }: RouteContext) {
  const { action } = await params;
  if (!["users", "model-providers", "memory-policies"].includes(action)) return failure(404);
  if (!isConsoleMutation(request)) return failure(403);
  const token = request.cookies.get(COOKIE)?.value;
  if (!token) return failure(401);
  const ifMatch = request.headers.get("if-match");
  if (!ifMatch || !/^"[1-9]\d{0,9}"$/.test(ifMatch)) return failure(400);

  try {
    const body = await parseBody(request);
    if (!body) return failure(400);
    if (action === "model-providers" || action === "memory-policies") {
      const id = resourceId(request);
      if (!id) return failure(400);
      const path = action === "model-providers" ? "/admin/model-providers/" : "/admin/memory/policies/";
      const patch = action === "model-providers" ? { is_enabled: body.is_enabled, is_default: body.is_default }
        : { strategy: body.strategy, intervals_days: body.intervals_days, target_retention: body.target_retention };
      const upstream = await backend(path + id, { method: "PATCH", token, ifMatch, body: patch });
      return upstream.ok ? reply(await upstream.json(), upstream.status) : failure(upstream.status);
    }

    const userId = request.nextUrl.searchParams.get("user_id");
    if (!userId || !userIdPattern.test(userId)) return failure(400);
    const name = displayName(body?.display_name);
    if (!name || typeof body.is_active !== "boolean") return failure(400);

    const path = "/admin/users/" + userId;
    const current = await backend(path + "/overview", { token });
    if (!current.ok) return failure(current.status);
    if ((await current.json()).user?.role !== "user") return failure(403);

    const upstream = await backend(path, {
      method: "PATCH",
      token,
      ifMatch,
      body: { display_name: name, is_active: body.is_active },
    });
    return upstream.ok ? reply(await upstream.json(), upstream.status) : failure(upstream.status);
  } catch {
    return failure(503);
  }
}
