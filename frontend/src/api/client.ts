import { ApiError } from './errors';
import { API_BASE_URL } from '../config';
import { tokenStore, type TokenStore } from './tokens';
import type { ErrorEnvelope, FieldIssue, Session } from './types';

export const RATE_LIMITED_CODE = 'rate_limited';
export const RATE_LIMITED_MESSAGE = 'Too many requests. Please wait a minute and try again.';
export const REFRESH_LOCK = 'stockeye-refresh';

export interface ApiClientOptions {
  baseUrl?: string;
  fetchImpl?: typeof fetch;
  tokens?: TokenStore;
  /**
   * Web Locks, used to serialise refreshes across tabs. Defaults to `navigator.locks`; pass `null`
   * to run without it (tests, or browsers that lack it).
   */
  locks?: Pick<LockManager, 'request'> | null;
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
  /** `body` is for the rare DELETE that must carry a confirmation, such as a password. */
  delete: <T = void>(path: string, opts?: RequestOptions & { body?: unknown }) => Promise<T>;
  /**
   * Call once at app start. With a stored refresh token, trades it for an access token; protected
   * requests wait for this, so the first call does not need a 401 round trip.
   */
  initSession: () => Promise<void>;
  setSessionExpiredHandler: (handler: (() => void) | undefined) => void;
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

type RefreshOutcome = 'ok' | 'rejected' | 'failed';

export function createApiClient(options: ApiClientOptions = {}): ApiClient {
  const baseUrl = options.baseUrl ?? API_BASE_URL;
  const tokens = options.tokens ?? tokenStore;
  let onSessionExpired = options.onSessionExpired;
  const doFetch: typeof fetch = (...args) => (options.fetchImpl ?? fetch)(...args);
  const getLocks = (): Pick<LockManager, 'request'> | null => {
    if (options.locks !== undefined) return options.locks;
    return typeof navigator !== 'undefined' && 'locks' in navigator ? navigator.locks : null;
  };

  // Concurrent callers in this tab share one refresh. Across tabs, the Web Lock below serialises
  // them. Without navigator.locks only this in-tab dedupe protects us, so two tabs that both hit
  // an expired access token at the same instant can send the same refresh token twice, and the
  // server would treat the second as reuse and revoke the session. Rare, and the user signs in again.
  let refreshInFlight: Promise<RefreshOutcome> | null = null;
  let startup: Promise<void> | null = null;

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
    access: string | null,
  ): Promise<Response> {
    const headers: Record<string, string> = { Accept: 'application/json' };
    if (body !== undefined) headers['Content-Type'] = 'application/json';
    if (access) headers.Authorization = `Bearer ${access}`;
    try {
      return await doFetch(buildUrl(path, opts?.query), {
        method,
        headers,
        credentials: 'omit',
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

  /**
   * Runs inside the cross-tab lock. The refresh token is re-read here, never taken from the
   * caller: another tab may have rotated it while we waited, and re-sending a rotated token is
   * treated by the server as theft (the whole session family is revoked).
   */
  async function refreshLocked(
    failedAccess: string | null,
    startedWith: string | null,
  ): Promise<RefreshOutcome> {
    const current = tokens.getRefresh();
    if (!current) {
      tokens.clear(); // signed out (here or in another tab)
      return 'rejected';
    }
    if (current !== startedWith) {
      // Another tab rotated the token while we waited. Its new token is valid; the only thing we
      // may still lack is an access token of our own.
      const access = tokens.getAccess();
      if (access && access !== failedAccess) return 'ok';
    }
    try {
      const res = await send('POST', '/auth/refresh', { refresh_token: current }, undefined, null);
      if (res.ok) {
        const session = (await res.json()) as Session;
        tokens.set({ access: session.access_token, refresh: session.refresh_token });
        return 'ok';
      }
      if (res.status === 401) {
        tokens.clear();
        return 'rejected';
      }
      return 'failed';
    } catch {
      return 'failed';
    }
  }

  function refreshSession(failedAccess: string | null): Promise<RefreshOutcome> {
    const startedWith = tokens.getRefresh();
    refreshInFlight ??= (async () => {
      try {
        const locks = getLocks();
        const run = () => refreshLocked(failedAccess, startedWith);
        return locks ? await locks.request(REFRESH_LOCK, run) : await run();
      } catch {
        return 'failed';
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
    const isAuthCall = path.startsWith('/auth/');
    if (!isAuthCall && startup) await startup;
    const usedAccess = tokens.getAccess();
    let res = await send(method, path, body, opts, usedAccess);

    // Refresh at most once and retry at most once; auth endpoints never trigger it.
    if (res.status === 401 && !isAuthCall) {
      const outcome = await refreshSession(usedAccess);
      if (outcome === 'ok') res = await send(method, path, body, opts, tokens.getAccess());
      if (outcome === 'rejected' || (outcome === 'ok' && res.status === 401)) onSessionExpired?.();
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
    delete: (path, opts) => request('DELETE', path, opts?.body, opts),
    initSession: () => {
      startup ??= tokens.getRefresh()
        ? refreshSession(null).then(() => undefined)
        : Promise.resolve();
      return startup;
    },
    setSessionExpiredHandler: (handler) => {
      onSessionExpired = handler;
    },
  };
}

export const api = createApiClient();
