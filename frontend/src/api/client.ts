import { ApiError } from './errors';
import type { ErrorEnvelope, FieldIssue } from './types';

const CSRF_COOKIE = 'se_csrf';
export const RATE_LIMITED_CODE = 'rate_limited';
export const RATE_LIMITED_MESSAGE = 'Too many requests. Please wait a minute and try again.';
const UNSAFE = new Set(['POST', 'PUT', 'PATCH', 'DELETE']);

export interface ApiClientOptions {
  baseUrl?: string;
  fetchImpl?: typeof fetch;
  readCookie?: (name: string) => string | undefined;
  /** Called when a 401 could not be recovered by refreshing the session. */
  onSessionExpired?: () => void;
}

export interface RequestOptions {
  signal?: AbortSignal;
  query?: Record<string, string | number | undefined>;
}

export interface ApiClient {
  get: <T>(path: string, opts?: RequestOptions) => Promise<T>;
  post: <T>(path: string, body?: unknown, opts?: RequestOptions) => Promise<T>;
  put: <T>(path: string, body?: unknown, opts?: RequestOptions) => Promise<T>;
  patch: <T>(path: string, body?: unknown, opts?: RequestOptions) => Promise<T>;
  delete: <T = void>(path: string, opts?: RequestOptions) => Promise<T>;
  /** Fetches the CSRF cookie. Call once at app start; unsafe requests also self-heal. */
  initCsrf: () => Promise<void>;
  setSessionExpiredHandler: (handler: (() => void) | undefined) => void;
}

function defaultReadCookie(name: string): string | undefined {
  for (const part of document.cookie.split('; ')) {
    const eq = part.indexOf('=');
    if (eq > 0 && part.slice(0, eq) === name) {
      return decodeURIComponent(part.slice(eq + 1));
    }
  }
  return undefined;
}

function isRecord(v: unknown): v is Record<string, unknown> {
  return typeof v === 'object' && v !== null;
}

function parseIssues(raw: unknown): FieldIssue[] | null {
  if (!Array.isArray(raw)) return null;
  const issues: FieldIssue[] = [];
  for (const item of raw as unknown[]) {
    if (isRecord(item) && typeof item.field === 'string' && typeof item.message === 'string') {
      issues.push({ field: item.field, message: item.message });
    }
  }
  return issues;
}

/** Turns any non-2xx response into an ApiError, tolerating bodies that are not our envelope. */
async function toApiError(res: Response): Promise<ApiError> {
  // nginx answers 429 with an HTML page on /api/auth/*, so the status alone decides.
  if (res.status === 429) {
    let requestId = '';
    try {
      const body: unknown = await res.json();
      if (isRecord(body) && isRecord(body.error) && typeof body.error.request_id === 'string') {
        requestId = body.error.request_id;
      }
    } catch {
      // HTML or empty body: nothing to read.
    }
    return new ApiError({
      code: RATE_LIMITED_CODE,
      message: RATE_LIMITED_MESSAGE,
      status: 429,
      requestId,
    });
  }
  let body: unknown;
  try {
    body = await res.json();
  } catch {
    body = undefined;
  }
  if (isRecord(body) && isRecord(body.error)) {
    const e = body.error as Partial<ErrorEnvelope['error']>;
    return new ApiError({
      code: typeof e.code === 'string' ? e.code : 'http_error',
      message: typeof e.message === 'string' ? e.message : 'Something went wrong.',
      status: res.status,
      requestId: typeof e.request_id === 'string' ? e.request_id : '',
      details: parseIssues(e.details),
    });
  }
  return new ApiError({
    code: 'http_error',
    message:
      res.status >= 500 ? 'The server had a problem. Try again shortly.' : 'The request failed.',
    status: res.status,
  });
}

export function createApiClient(options: ApiClientOptions = {}): ApiClient {
  const baseUrl = options.baseUrl ?? '/api';
  const readCookie = options.readCookie ?? defaultReadCookie;
  let onSessionExpired = options.onSessionExpired;
  const doFetch: typeof fetch = (...args) => (options.fetchImpl ?? fetch)(...args);

  // Concurrent callers share one in-flight promise, so a burst of 401s triggers one refresh.
  let csrfInFlight: Promise<void> | null = null;
  let refreshInFlight: Promise<boolean> | null = null;

  function buildUrl(path: string, query?: RequestOptions['query']): string {
    let url = `${baseUrl}${path}`;
    if (query) {
      const params = new URLSearchParams();
      for (const [k, v] of Object.entries(query)) {
        if (v !== undefined && v !== '') params.set(k, String(v));
      }
      const qs = params.toString();
      if (qs) url += `?${qs}`;
    }
    return url;
  }

  async function send(
    method: string,
    path: string,
    body: unknown,
    opts: RequestOptions | undefined,
  ): Promise<Response> {
    const headers: Record<string, string> = { Accept: 'application/json' };
    if (body !== undefined) headers['Content-Type'] = 'application/json';
    if (UNSAFE.has(method)) {
      if (!readCookie(CSRF_COOKIE)) await initCsrf();
      const token = readCookie(CSRF_COOKIE);
      if (token) headers['X-CSRF-Token'] = token;
    }
    try {
      return await doFetch(buildUrl(path, opts?.query), {
        method,
        headers,
        credentials: 'include',
        ...(body !== undefined && { body: JSON.stringify(body) }),
        ...(opts?.signal && { signal: opts.signal }),
      });
    } catch (cause) {
      if (cause instanceof DOMException && cause.name === 'AbortError') throw cause;
      throw new ApiError({
        code: 'network_error',
        message: "Can't reach StockEye. Check your connection and try again.",
        status: 0,
      });
    }
  }

  function initCsrf(): Promise<void> {
    csrfInFlight ??= (async () => {
      try {
        const res = await send('GET', '/auth/csrf', undefined, undefined);
        if (!res.ok) throw await toApiError(res);
      } finally {
        csrfInFlight = null;
      }
    })();
    return csrfInFlight;
  }

  function refreshSession(): Promise<boolean> {
    refreshInFlight ??= (async () => {
      try {
        const res = await send('POST', '/auth/refresh', undefined, undefined);
        return res.ok;
      } catch {
        return false;
      } finally {
        refreshInFlight = null;
      }
    })();
    return refreshInFlight;
  }

  async function request<T>(
    method: string,
    path: string,
    body?: unknown,
    opts?: RequestOptions,
  ): Promise<T> {
    let res = await send(method, path, body, opts);

    if (res.status === 401 && !path.startsWith('/auth/')) {
      if (await refreshSession()) res = await send(method, path, body, opts);
      if (res.status === 401) onSessionExpired?.();
    }

    if (!res.ok) throw await toApiError(res);
    if (res.status === 204) return undefined as T;
    const text = await res.text();
    return (text ? JSON.parse(text) : undefined) as T;
  }

  return {
    get: (path, opts) => request('GET', path, undefined, opts),
    post: (path, body, opts) => request('POST', path, body, opts),
    put: (path, body, opts) => request('PUT', path, body, opts),
    patch: (path, body, opts) => request('PATCH', path, body, opts),
    delete: (path, opts) => request('DELETE', path, undefined, opts),
    initCsrf,
    setSessionExpiredHandler: (handler) => {
      onSessionExpired = handler;
    },
  };
}

export const api = createApiClient();
