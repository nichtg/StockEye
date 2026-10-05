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
  /** How long the lock holder keeps the lock after storing a rotated token. Default 250 ms. */
  lockHoldMs?: number;
  /** How long a refresh waits for the lock before giving up. Default 15 s. */
  lockWaitMs?: number;
}

const FETCH_TIMEOUT_MS = 10_000;

/** `AbortSignal.timeout` is missing before Safari 16; without this, every refresh would fail there. */
export function timeoutSignal(ms: number): AbortSignal {
  if (typeof AbortSignal.timeout === 'function') return AbortSignal.timeout(ms);
  const controller = new AbortController();
  setTimeout(() => {
    controller.abort(new DOMException('The operation timed out.', 'TimeoutError'));
  }, ms);
  return controller.signal;
}

export interface RequestOptions {
  signal?: AbortSignal;
  /** Let the request finish after the page unloads (used for logout). */
  keepalive?: boolean;
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
  /**
   * Signs this tab out at once, then (under the refresh lock, so it sends the newest token and
   * never interleaves with a rotation) revokes the session server-side and clears storage.
   * Resolves when that is done; callers need not wait.
   */
  logout: () => Promise<void>;
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
        ...(opts?.keepalive && { keepalive: true }),
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

  const holdMs = options.lockHoldMs ?? 250;
  const lockWaitMs = options.lockWaitMs ?? 15_000;
  const sleep = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms));

  /**
   * Runs `fn` under the cross-tab lock. The caller gets `fn`'s value as soon as it returns; if
   * `hold` is set the lock is kept a little longer (see refreshLocked). Waiting for the lock is
   * bounded, so nothing can hang forever on a stuck lock: the caller gets a rejection instead.
   */
  function underLock<T>(fn: () => Promise<{ value: T; hold: boolean }>): Promise<T> {
    const locks = getLocks();
    if (!locks) return fn().then((r) => r.value);
    return new Promise<T>((resolve, reject) => {
      const controller = new AbortController();
      const timer = setTimeout(() => {
        controller.abort();
        reject(new Error('lock wait timed out'));
      }, lockWaitMs);
      locks
        .request(REFRESH_LOCK, { signal: controller.signal }, async () => {
          clearTimeout(timer);
          if (controller.signal.aborted) return;
          try {
            const r = await fn();
            resolve(r.value);
            // Hold on, so the localStorage write reaches the other tabs before any of them can
            // acquire the lock and read the token. Without this a tab could read the already
            // rotated-away token, send it, and get the whole session revoked as reuse.
            if (r.hold && holdMs > 0) await sleep(holdMs);
          } catch (error) {
            reject(error instanceof Error ? error : new Error('refresh failed'));
          }
        })
        .catch((error: unknown) => {
          clearTimeout(timer);
          reject(error instanceof Error ? error : new Error('lock failed'));
        });
    });
  }

  /**
   * Runs inside the cross-tab lock. The refresh token is re-read here, never taken from the
   * caller: another tab may have rotated it while we waited, and re-sending a rotated token is
   * treated by the server as theft (the whole session family is revoked).
   */
  async function refreshLocked(
    failedAccess: string | null,
    startedWith: string | null,
  ): Promise<{ value: RefreshOutcome; hold: boolean }> {
    const rejected = { value: 'rejected' as const, hold: false };
    const failed = { value: 'failed' as const, hold: false };
    const refresh = tokens.getRefresh();
    if (!refresh) {
      tokens.clear(); // signed out (here or in another tab)
      return rejected;
    }
    if (refresh !== startedWith) {
      // Another tab rotated the token while we waited. Its new token is valid; the only thing we
      // may still lack is an access token of our own.
      const access = tokens.getAccess();
      if (access && access !== failedAccess) return { value: 'ok', hold: false };
    }
    const epoch = tokens.getEpoch();
    try {
      const res = await send(
        'POST',
        '/auth/refresh',
        { refresh_token: refresh },
        { signal: timeoutSignal(FETCH_TIMEOUT_MS) },
        null,
      );
      if (res.ok) {
        const session = (await res.json()) as Session;
        // Compare-and-set: a sign-out (or another tab's new login) during the fetch wins.
        const stored = tokens.setIfCurrent(
          { refresh, epoch },
          {
            access: session.access_token,
            refresh: session.refresh_token,
            userId: session.user.id,
          },
        );
        return stored ? { value: 'ok', hold: true } : rejected;
      }
      if (res.status === 401) {
        if (tokens.getEpoch() === epoch && tokens.getRefresh() === refresh) tokens.clear();
        return rejected;
      }
      return failed;
    } catch {
      return failed;
    }
  }

  function refreshSession(failedAccess: string | null): Promise<RefreshOutcome> {
    const startedWith = tokens.getRefresh();
    refreshInFlight ??= (async () => {
      try {
        return await underLock(() => refreshLocked(failedAccess, startedWith));
      } catch {
        return 'failed' as const; // lock timeout or abort: keep the session, surface the error
      } finally {
        refreshInFlight = null;
      }
    })();
    return refreshInFlight;
  }

  async function logout(): Promise<void> {
    const before = tokens.getRefresh();
    tokens.forgetLocal();
    try {
      await underLock(async () => {
        const newest = tokens.getRefresh() ?? before;
        tokens.clear();
        if (newest) {
          await send(
            'POST',
            '/auth/logout',
            { refresh_token: newest },
            // keepalive: a sign-out followed by closing the tab must still revoke the session.
            { signal: timeoutSignal(FETCH_TIMEOUT_MS), keepalive: true },
            null,
          ).catch(() => undefined);
        }
        return { value: undefined, hold: false };
      });
    } catch {
      tokens.clear(); // could not get the lock in time: still end the local session
    }
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
      if (outcome === 'ok' && res.status === 401) tokens.clear();
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
    logout,
    setSessionExpiredHandler: (handler) => {
      onSessionExpired = handler;
    },
  };
}

export const api = createApiClient();
