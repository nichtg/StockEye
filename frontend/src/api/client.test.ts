import { describe, expect, it, vi } from 'vitest';
import { createApiClient } from './client';
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

function setup(handler: (url: string, init: RequestInit) => Response | Promise<Response>) {
  const calls: { url: string; init: RequestInit }[] = [];
  const fetchImpl = vi.fn((input: string, init?: RequestInit) => {
    const call = { url: input, init: init ?? {} };
    calls.push(call);
    return Promise.resolve(handler(call.url, call.init));
  });
  const cookies: Record<string, string> = { se_csrf: 'tok-123' };
  const onSessionExpired = vi.fn();
  const client = createApiClient({
    fetchImpl: fetchImpl as unknown as typeof fetch,
    readCookie: (name) => cookies[name],
    onSessionExpired,
  });
  return { client, calls, cookies, onSessionExpired };
}

describe('api client', () => {
  it('sends credentials on every request', async () => {
    const { client, calls } = setup(() => json({ ok: true }));
    await client.get('/me');
    expect(calls[0]?.init.credentials).toBe('include');
    expect(calls[0]?.url).toBe('/api/me');
  });

  it('adds the CSRF header to unsafe methods but not to GET', async () => {
    const { client, calls } = setup(() => json({}));
    await client.get('/me');
    await client.post('/auth/logout');
    await client.patch('/admin/users/1', { role: 'admin' });
    await client.delete('/admin/users/1');

    const header = (i: number) =>
      (calls[i]?.init.headers as Record<string, string>)['X-CSRF-Token'];
    expect(header(0)).toBeUndefined();
    expect(header(1)).toBe('tok-123');
    expect(header(2)).toBe('tok-123');
    expect(header(3)).toBe('tok-123');
  });

  it('fetches the CSRF cookie first when it is missing', async () => {
    const { client, calls, cookies } = setup((url) => {
      if (url === '/api/auth/csrf') {
        cookies.se_csrf = 'fresh';
        return json({ csrf_token: 'fresh' });
      }
      return json({});
    });
    delete cookies.se_csrf;
    await client.post('/auth/login', { email: 'a@b.co', password: 'x' });
    expect(calls.map((c) => c.url)).toEqual(['/api/auth/csrf', '/api/auth/login']);
    expect((calls[1]?.init.headers as Record<string, string>)['X-CSRF-Token']).toBe('fresh');
  });

  it('refreshes once and retries the original request after a 401', async () => {
    let meCalls = 0;
    const { client, calls } = setup((url) => {
      if (url === '/api/auth/refresh') return json({ user: {} });
      meCalls += 1;
      return meCalls === 1 ? envelope(401, 'unauthenticated', 'Expired') : json({ id: '1' });
    });
    await expect(client.get('/me')).resolves.toEqual({ id: '1' });
    expect(calls.map((c) => c.url)).toEqual(['/api/me', '/api/auth/refresh', '/api/me']);
  });

  it('shares one in-flight refresh across concurrent 401s', async () => {
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
        return json({ user: {} });
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

  it('signals session expiry and throws when the refresh fails', async () => {
    const { client, onSessionExpired } = setup((url) =>
      url === '/api/auth/refresh'
        ? envelope(401, 'unauthenticated', 'Your session has expired.')
        : envelope(401, 'unauthenticated', 'Expired'),
    );
    await expect(client.get('/me')).rejects.toMatchObject({ status: 401 });
    expect(onSessionExpired).toHaveBeenCalledTimes(1);
  });

  it('does not try to refresh for /auth/* endpoints', async () => {
    const { client, calls, onSessionExpired } = setup(() =>
      envelope(401, 'unauthenticated', 'Email or password is incorrect.'),
    );
    await expect(
      client.post('/auth/login', { email: 'a@b.co', password: 'x' }),
    ).rejects.toBeInstanceOf(ApiError);
    expect(calls.some((c) => c.url.endsWith('/auth/refresh'))).toBe(false);
    expect(onSessionExpired).not.toHaveBeenCalled();
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
      readCookie: () => 'x',
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
