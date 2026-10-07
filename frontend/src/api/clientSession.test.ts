import { afterEach, describe, expect, it, vi } from 'vitest';
import { createApiClient, timeoutSignal } from './client';
import { REFRESH_KEY, tokenStore } from './tokens';

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });
const unauthorized = () => json({ error: { code: 'unauthenticated', message: 'x' } }, 401);
const sessionBody = (access: string, refresh: string) => ({
  access_token: access,
  access_expires_in: 900,
  refresh_token: refresh,
  user: { id: 'u1' },
});
const stored = (t: string, u = 'u1') => JSON.stringify({ t, u });

type Locks = Pick<LockManager, 'request'>;

/** Queues callers like Web Locks do. */
function queueLocks(): Locks {
  let tail: Promise<unknown> = Promise.resolve();
  return {
    request: ((_n: string, _o: unknown, cb: () => unknown) => {
      const run = tail.then(() => cb());
      tail = run.catch(() => undefined);
      return run;
    }) as unknown as LockManager['request'],
  };
}

const hungLocks: Locks = {
  request: () => new Promise(() => undefined),
};

function build(
  handler: (url: string, init: RequestInit) => Response | Promise<Response>,
  extra: Partial<Parameters<typeof createApiClient>[0]> = {},
) {
  const calls: { url: string; init: RequestInit }[] = [];
  const client = createApiClient({
    fetchImpl: ((url: string, init: RequestInit) => {
      calls.push({ url, init });
      return Promise.resolve(handler(url, init));
    }) as unknown as typeof fetch,
    locks: queueLocks(),
    lockHoldMs: 0,
    onSessionExpired: vi.fn(),
    ...extra,
  });
  return { client, calls };
}

const bodyOf = (c?: { init: RequestInit }) => JSON.parse(c?.init.body as string) as unknown;
const bearer = (c?: { init: RequestInit }) =>
  (c?.init.headers as Record<string, string>).Authorization;

afterEach(() => {
  vi.useRealTimers();
});

describe('sign-out versus refresh', () => {
  it('a logout during a pending refresh is not undone by the refresh result', async () => {
    tokenStore.set({ access: 'old', refresh: 'ref-1', userId: 'u1' });
    let release: () => void = () => undefined;
    const gate = new Promise<void>((r) => {
      release = r;
    });
    const { client, calls } = build(async (url) => {
      if (url === '/api/auth/refresh') {
        await gate;
        return json(sessionBody('new', 'ref-2'));
      }
      return url === '/api/auth/logout' ? new Response(null, { status: 204 }) : unauthorized();
    });
    const request = client.get('/me').catch((e: unknown) => e);
    await vi.waitFor(() => {
      expect(calls.some((c) => c.url === '/api/auth/refresh')).toBe(true);
    });
    const loggedOut = client.logout();
    release();
    await request;
    await loggedOut;
    expect(localStorage.getItem(REFRESH_KEY)).toBeNull();
    expect(tokenStore.getAccess()).toBeNull();
    expect(tokenStore.getRefresh()).toBeNull();
    // The refresh result was discarded; the server still learns of the logout.
    expect(calls.filter((c) => c.url === '/api/auth/logout')).toHaveLength(1);
  });

  it('the logout request survives the page closing (keepalive)', async () => {
    tokenStore.set({ access: 'a', refresh: 'ref-1', userId: 'u1' });
    const { client, calls } = build(() => new Response(null, { status: 204 }));

    await client.logout();

    const logout = calls.find((c) => c.url === '/api/auth/logout');
    expect(logout?.init.keepalive).toBe(true);
  });

  it('storage removed by another tab during a pending refresh stays removed', async () => {
    tokenStore.set({ access: 'old', refresh: 'ref-1', userId: 'u1' });
    const expired = vi.fn();
    const { client } = build(
      (url) => {
        if (url === '/api/auth/refresh') {
          localStorage.removeItem(REFRESH_KEY); // the other tab signs out mid-flight
          return json(sessionBody('new', 'ref-2'));
        }
        return unauthorized();
      },
      { onSessionExpired: expired },
    );
    await expect(client.get('/me')).rejects.toMatchObject({ status: 401 });
    expect(localStorage.getItem(REFRESH_KEY)).toBeNull();
    expect(tokenStore.getRefresh()).toBeNull();
    expect(expired).toHaveBeenCalledTimes(1);
  });

  it('logout sends the newest stored token, not the one from before a rotation', async () => {
    tokenStore.set({ access: 'a', refresh: 'ref-1', userId: 'u1' });
    const { client, calls } = build(() => new Response(null, { status: 204 }));
    localStorage.setItem(REFRESH_KEY, stored('ref-9')); // rotated by another tab
    await client.logout();
    expect(bodyOf(calls[0])).toEqual({ refresh_token: 'ref-9' });
    expect(localStorage.getItem(REFRESH_KEY)).toBeNull();
  });
});

describe('timeouts', () => {
  it('gives the refresh request a timeout signal', async () => {
    tokenStore.set({ access: 'old', refresh: 'ref-1', userId: 'u1' });
    const { client, calls } = build((url) =>
      url === '/api/auth/refresh' ? json(sessionBody('n', 'r2')) : unauthorized(),
    );
    await client.get('/me').catch(() => undefined);
    expect(calls.find((c) => c.url === '/api/auth/refresh')?.init.signal).toBeInstanceOf(
      AbortSignal,
    );
  });

  it('a lock that never resolves ends in a kept session and a surfaced error', async () => {
    vi.useFakeTimers();
    tokenStore.set({ access: 'old', refresh: 'ref-1', userId: 'u1' });
    const expired = vi.fn();
    const { client } = build(() => unauthorized(), { locks: hungLocks, onSessionExpired: expired });
    const result = client.get('/me').catch((e: unknown) => e);
    await vi.advanceTimersByTimeAsync(15_001);
    expect(await result).toMatchObject({ status: 401 });
    expect(expired).not.toHaveBeenCalled();
    expect(tokenStore.getRefresh()).toBe('ref-1');
  });

  it('startup never blocks protected requests forever', async () => {
    vi.useFakeTimers();
    localStorage.setItem(REFRESH_KEY, stored('ref-1'));
    const { client } = build(() => json({ ok: true }), { locks: hungLocks });
    void client.initSession();
    const result = client.get('/me');
    await vi.advanceTimersByTimeAsync(15_001);
    await expect(result).resolves.toEqual({ ok: true });
  });
});

describe('cross-tab ordering', () => {
  it('keeps the lock for the hold period after storing a rotated token', async () => {
    vi.useFakeTimers();
    tokenStore.set({ access: 'old', refresh: 'ref-1', userId: 'u1' });
    let held = false;
    const locks: Locks = {
      request: (async (_n: string, _o: unknown, cb: () => Promise<unknown>) => {
        held = true;
        await cb();
        held = false;
      }) as unknown as LockManager['request'],
    };
    let meCalls = 0;
    const { client } = build(
      (url) => {
        if (url === '/api/auth/refresh') return json(sessionBody('new', 'ref-2'));
        meCalls += 1;
        return meCalls === 1 ? unauthorized() : json({ ok: true });
      },
      { locks, lockHoldMs: 250 },
    );
    await expect(client.get('/me')).resolves.toEqual({ ok: true }); // not delayed by the hold
    expect(held).toBe(true);
    await vi.advanceTimersByTimeAsync(249);
    expect(held).toBe(true);
    await vi.advanceTimersByTimeAsync(2);
    expect(held).toBe(false);
  });

  it('sends nothing when another tab rotated and this tab already has a fresh access token', async () => {
    tokenStore.set({ access: 'old', refresh: 'stale', userId: 'u1' });
    const locks: Locks = {
      request: ((_n: string, _o: unknown, cb: () => unknown) => {
        // While we waited, this tab obtained a fresh pair.
        tokenStore.set({ access: 'fresh', refresh: 'rotated', userId: 'u1' });
        return cb();
      }) as unknown as LockManager['request'],
    };
    const { client, calls } = build(
      (_url, init) =>
        (init.headers as Record<string, string>).Authorization === 'Bearer old'
          ? unauthorized()
          : json({ ok: true }),
      { locks },
    );
    await expect(client.get('/me')).resolves.toEqual({ ok: true });
    expect(calls.map((c) => c.url)).toEqual(['/api/me', '/api/me']);
    expect(bearer(calls[1])).toBe('Bearer fresh');
  });
});

describe('timeoutSignal', () => {
  it('aborts after the delay when AbortSignal.timeout is missing (Safari before 16)', () => {
    vi.useFakeTimers();
    const original = Object.getOwnPropertyDescriptor(AbortSignal, 'timeout');
    Object.defineProperty(AbortSignal, 'timeout', { value: undefined, configurable: true });
    try {
      const signal = timeoutSignal(10_000);
      expect(signal.aborted).toBe(false);

      vi.advanceTimersByTime(10_000);

      expect(signal.aborted).toBe(true);
    } finally {
      if (original) Object.defineProperty(AbortSignal, 'timeout', original);
    }
  });
});
