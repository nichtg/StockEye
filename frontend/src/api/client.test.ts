import { describe, expect, it, vi } from 'vitest';
import { createApiClient } from './client';
import { REFRESH_KEY, tokenStore } from './tokens';
import { shouldRetry } from '../queryClient';
import { ApiError } from './errors';

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

function envelope(status: number, code: string, message: string, details: unknown = null) {
  return json({ error: { code, message, request_id: 'req-1', details } }, status);
}

function session(access: string, refresh: string) {
  return { access_token: access, access_expires_in: 900, refresh_token: refresh, user: {} };
}

type Locks = Pick<LockManager, 'request'>;

/** A single-process lock: callers queue, like Web Locks do across tabs. */
function fakeLocks(beforeRun?: () => void): Locks {
  let tail: Promise<unknown> = Promise.resolve();
  return {
    request: ((_name: string, cb: () => unknown) => {
      const run = tail.then(() => {
        beforeRun?.();
        return cb();
      });
      tail = run.catch(() => undefined);
      return run;
    }) as unknown as LockManager['request'],
  };
}

function setup(
  handler: (url: string, init: RequestInit) => Response | Promise<Response>,
  locks: Locks | null = fakeLocks(),
) {
  const calls: { url: string; init: RequestInit }[] = [];
  const fetchImpl = vi.fn((input: string, init?: RequestInit) => {
    const call = { url: input, init: init ?? {} };
    calls.push(call);
    return Promise.resolve(handler(call.url, call.init));
  });
  const onSessionExpired = vi.fn();
  const client = createApiClient({
    fetchImpl: fetchImpl as unknown as typeof fetch,
    locks,
    onSessionExpired,
  });
  return { client, calls, onSessionExpired };
}

const authHeader = (c?: { init: RequestInit }) =>
  (c?.init.headers as Record<string, string> | undefined)?.Authorization;
const bodyOf = (c?: { init: RequestInit }) => JSON.parse(c?.init.body as string) as unknown;

describe('api client', () => {
  it('sends no ambient credentials and attaches the bearer token when present', async () => {
    const { client, calls } = setup(() => json({ ok: true }));
    await client.get('/me');
    tokenStore.set({ access: 'acc-1', refresh: 'ref-1' });
    await client.get('/me');
    expect(calls[0]?.init.credentials).toBe('omit');
    expect(calls[0]?.url).toBe('/api/me');
    expect(authHeader(calls[0])).toBeUndefined();
    expect(authHeader(calls[1])).toBe('Bearer acc-1');
  });

  it('refreshes once with the stored token, rotates it, and retries the request', async () => {
    tokenStore.set({ access: 'old', refresh: 'ref-1' });
    let meCalls = 0;
    const { client, calls } = setup((url) => {
      if (url === '/api/auth/refresh') return json(session('new', 'ref-2'));
      meCalls += 1;
      return meCalls === 1 ? envelope(401, 'unauthenticated', 'Expired') : json({ id: '1' });
    });
    await expect(client.get('/me')).resolves.toEqual({ id: '1' });
    expect(calls.map((c) => c.url)).toEqual(['/api/me', '/api/auth/refresh', '/api/me']);
    expect(bodyOf(calls[1])).toEqual({ refresh_token: 'ref-1' });
    expect(authHeader(calls[1])).toBeUndefined();
    expect(authHeader(calls[2])).toBe('Bearer new');
    expect(tokenStore.getRefresh()).toBe('ref-2');
  });

  it('retries exactly once: a 401 after a good refresh ends the session without looping', async () => {
    tokenStore.set({ access: 'old', refresh: 'ref-1' });
    const { client, calls, onSessionExpired } = setup((url) =>
      url === '/api/auth/refresh'
        ? json(session('new', 'ref-2'))
        : envelope(401, 'unauthenticated', 'Expired'),
    );
    await expect(client.get('/me')).rejects.toMatchObject({ status: 401 });
    expect(calls.map((c) => c.url)).toEqual(['/api/me', '/api/auth/refresh', '/api/me']);
    expect(onSessionExpired).toHaveBeenCalledTimes(1);
  });

  it('shares one in-flight refresh across concurrent 401s', async () => {
    tokenStore.set({ access: 'old', refresh: 'ref-1' });
    const seen = new Set<string>();
    let refreshes = 0;
    let releaseRefresh: () => void = () => undefined;
    const gate = new Promise<void>((resolve) => {
      releaseRefresh = resolve;
    });
    const { client } = setup(async (url) => {
      if (url === '/api/auth/refresh') {
        refreshes += 1;
        await gate;
        return json(session('new', 'ref-2'));
      }
      if (!seen.has(url)) {
        seen.add(url);
        return envelope(401, 'unauthenticated', 'Expired');
      }
      return json({ url });
    });

    const all = Promise.all([client.get('/a'), client.get('/b'), client.get('/c')]);
    await vi.waitFor(() => {
      expect(refreshes).toBe(1);
    });
    releaseRefresh();
    await expect(all).resolves.toHaveLength(3);
    expect(refreshes).toBe(1);
  });

  it('never sends a refresh token another tab already rotated', async () => {
    tokenStore.set({ access: 'old', refresh: 'stale-ref' });
    // The "other tab" rotates the token while this tab waits for the lock.
    const locks = fakeLocks(() => {
      localStorage.setItem(REFRESH_KEY, 'fresh-ref');
    });
    const { client, calls } = setup(
      (url, init) =>
        url === '/api/auth/refresh'
          ? json(session('new', 'fresh-ref-2'))
          : (init.headers as Record<string, string>).Authorization === 'Bearer old'
            ? envelope(401, 'unauthenticated', 'Expired')
            : json({ ok: true }),
      locks,
    );
    await expect(client.get('/me')).resolves.toEqual({ ok: true });
    const refreshes = calls.filter((c) => c.url === '/api/auth/refresh');
    expect(refreshes).toHaveLength(1);
    expect(bodyOf(refreshes[0])).toEqual({ refresh_token: 'fresh-ref' });
    expect(calls.some((c) => JSON.stringify(c.init.body ?? '').includes('stale-ref'))).toBe(false);
    expect(tokenStore.getRefresh()).toBe('fresh-ref-2');
  });

  it('treats a token removed by another tab as a sign-out and sends nothing', async () => {
    tokenStore.set({ access: 'old', refresh: 'ref-1' });
    const locks = fakeLocks(() => {
      localStorage.removeItem(REFRESH_KEY);
    });
    const { client, calls, onSessionExpired } = setup(
      () => envelope(401, 'unauthenticated', 'Expired'),
      locks,
    );
    await expect(client.get('/me')).rejects.toMatchObject({ status: 401 });
    expect(calls.some((c) => c.url === '/api/auth/refresh')).toBe(false);
    expect(onSessionExpired).toHaveBeenCalledTimes(1);
  });

  it('still refreshes (in-tab dedupe only) when navigator.locks is missing', async () => {
    tokenStore.set({ access: 'old', refresh: 'ref-1' });
    let meCalls = 0;
    const { client, calls } = setup((url) => {
      if (url === '/api/auth/refresh') return json(session('new', 'ref-2'));
      meCalls += 1;
      return meCalls === 1 ? envelope(401, 'unauthenticated', 'Expired') : json({});
    }, null);
    await client.get('/me');
    expect(calls.filter((c) => c.url === '/api/auth/refresh')).toHaveLength(1);
  });

  it('clears the tokens and signals expiry when the refresh is rejected', async () => {
    tokenStore.set({ access: 'old', refresh: 'ref-1' });
    const { client, onSessionExpired } = setup((url) =>
      url === '/api/auth/refresh'
        ? envelope(401, 'unauthenticated', 'Your session has expired.')
        : envelope(401, 'unauthenticated', 'Expired'),
    );
    await expect(client.get('/me')).rejects.toMatchObject({ status: 401 });
    expect(onSessionExpired).toHaveBeenCalledTimes(1);
    expect(tokenStore.getRefresh()).toBeNull();
    expect(tokenStore.getAccess()).toBeNull();
  });

  it('keeps the session when the refresh fails for a transient reason', async () => {
    tokenStore.set({ access: 'old', refresh: 'ref-1' });
    const { client, onSessionExpired } = setup((url) =>
      url === '/api/auth/refresh'
        ? new Response('', { status: 503 })
        : envelope(401, 'unauthenticated', 'Expired'),
    );
    await expect(client.get('/me')).rejects.toMatchObject({ status: 401 });
    expect(onSessionExpired).not.toHaveBeenCalled();
    expect(tokenStore.getRefresh()).toBe('ref-1');
  });

  it('does not try to refresh for /auth/* endpoints', async () => {
    tokenStore.set({ access: 'old', refresh: 'ref-1' });
    const { client, calls, onSessionExpired } = setup(() =>
      envelope(401, 'unauthenticated', 'Email or password is incorrect.'),
    );
    await expect(
      client.post('/auth/login', { email: 'a@b.co', password: 'x' }),
    ).rejects.toBeInstanceOf(ApiError);
    expect(calls).toHaveLength(1);
    expect(onSessionExpired).not.toHaveBeenCalled();
  });

  describe('initSession', () => {
    it('trades a stored refresh token for an access token before protected calls', async () => {
      localStorage.setItem(REFRESH_KEY, 'ref-1');
      const { client, calls } = setup((url) =>
        url === '/api/auth/refresh' ? json(session('acc', 'ref-2')) : json({ id: '1' }),
      );
      void client.initSession();
      await client.get('/me');
      expect(calls.map((c) => c.url)).toEqual(['/api/auth/refresh', '/api/me']);
      expect(authHeader(calls[1])).toBe('Bearer acc');
      expect(tokenStore.getRefresh()).toBe('ref-2');
    });

    it('does nothing without a stored refresh token', async () => {
      const { client, calls } = setup(() => json({}));
      await client.initSession();
      expect(calls).toHaveLength(0);
    });
  });

  it('parses the error envelope into an ApiError', async () => {
    const { client } = setup(() =>
      envelope(422, 'validation_error', 'Too short.', [
        { field: 'password', message: 'Too short.' },
      ]),
    );
    const error = await client.post('/auth/register', {}).catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({
      code: 'validation_error',
      message: 'Too short.',
      status: 422,
      requestId: 'req-1',
    });
    expect((error as ApiError).fieldMessage('password')).toBe('Too short.');
  });

  it('turns non-envelope failures into a generic ApiError', async () => {
    const { client } = setup(() => new Response('<html>bad gateway</html>', { status: 502 }));
    await expect(client.get('/me')).rejects.toMatchObject({ status: 502, code: 'http_error' });
  });

  it('turns network failures into an ApiError with status 0', async () => {
    const client = createApiClient({
      fetchImpl: (() =>
        Promise.reject(new TypeError('Failed to fetch'))) as unknown as typeof fetch,
    });
    const error = await client.get('/me').catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).isNetworkError).toBe(true);
  });

  it('resolves 204 responses to undefined and serialises query params', async () => {
    const { client, calls } = setup(() => new Response(null, { status: 204 }));
    await expect(client.delete('/admin/users/1')).resolves.toBeUndefined();
    await client.get('/admin/users', {
      query: { query: 'ann', page: 2, page_size: 20, empty: '' },
    });
    expect(calls[1]?.url).toBe('/api/admin/users?query=ann&page=2&page_size=20');
  });

  describe('rate limits', () => {
    const MESSAGE = 'Too many requests. Please wait a minute and try again.';

    it('maps the JSON 429 envelope to rate_limited', async () => {
      const { client } = setup(() => envelope(429, 'rate_limited', 'Slow down, server wording.'));
      const error = await client.get('/stocks/AAPL').catch((e: unknown) => e);
      expect(error).toBeInstanceOf(ApiError);
      expect(error).toMatchObject({ code: 'rate_limited', status: 429, message: MESSAGE });
      expect((error as ApiError).requestId).toBe('req-1');
    });

    it('maps an nginx HTML 429 page to rate_limited', async () => {
      const { client } = setup(
        () =>
          new Response('<html><body><h1>429 Too Many Requests</h1></body></html>', {
            status: 429,
            headers: { 'Content-Type': 'text/html' },
          }),
      );
      const error = await client.post('/auth/login', { email: 'a@b.co' }).catch((e: unknown) => e);
      expect(error).toBeInstanceOf(ApiError);
      expect(error).toMatchObject({ code: 'rate_limited', status: 429, message: MESSAGE });
    });

    it('is never retried by the query client', () => {
      const limited = new ApiError({ code: 'rate_limited', message: MESSAGE, status: 429 });
      expect(shouldRetry(0, limited)).toBe(false);
      expect(shouldRetry(0, new ApiError({ code: 'not_found', message: 'x', status: 404 }))).toBe(
        false,
      );
      expect(shouldRetry(0, new ApiError({ code: 'x', message: 'x', status: 503 }))).toBe(true);
      expect(shouldRetry(1, new ApiError({ code: 'x', message: 'x', status: 503 }))).toBe(false);
    });
  });
});
