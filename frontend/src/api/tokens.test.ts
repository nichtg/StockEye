import { describe, expect, it, vi } from 'vitest';
import { REFRESH_KEY, tokenStore } from './tokens';

const stored = (t: string, u: string) => JSON.stringify({ t, u });

describe('token store', () => {
  it('keeps the access token in memory and the refresh token with the user id in localStorage', () => {
    tokenStore.set({ access: 'a', refresh: 'r', userId: 'u1' });
    expect(tokenStore.getAccess()).toBe('a');
    expect(tokenStore.getRefresh()).toBe('r');
    expect(tokenStore.getUserId()).toBe('u1');
    expect(JSON.parse(localStorage.getItem(REFRESH_KEY) ?? '')).toEqual({ t: 'r', u: 'u1' });
    expect(Object.values(localStorage).join()).not.toContain('"a"');
    tokenStore.clear();
    expect(tokenStore.getAccess()).toBeNull();
    expect(localStorage.getItem(REFRESH_KEY)).toBeNull();
  });

  it('survives storage that throws on every access', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('blocked');
    });
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('blocked');
    });
    vi.spyOn(Storage.prototype, 'removeItem').mockImplementation(() => {
      throw new Error('blocked');
    });
    expect(() => {
      tokenStore.set({ access: 'a', refresh: 'r', userId: 'u1' });
    }).not.toThrow();
    expect(tokenStore.getRefresh()).toBe('r'); // memory copy for this visit
    expect(() => {
      tokenStore.clear();
    }).not.toThrow();
    expect(tokenStore.getRefresh()).toBeNull();
    expect(tokenStore.getAccess()).toBeNull();
  });

  it('ignores and clears an unparsable stored value', () => {
    for (const bad of ['not json', '{"t":1}', '{"t":"r"}', 'null']) {
      localStorage.setItem(REFRESH_KEY, bad);
      expect(tokenStore.getRefresh()).toBeNull();
      expect(localStorage.getItem(REFRESH_KEY)).toBeNull();
    }
  });

  it('refuses a refresh result after a sign-out or when storage moved on', () => {
    tokenStore.set({ access: 'a', refresh: 'r1', userId: 'u1' });
    const epoch = tokenStore.getEpoch();
    const next = { access: 'b', refresh: 'r2', userId: 'u1' };

    localStorage.setItem(REFRESH_KEY, stored('rX', 'u1')); // another tab rotated
    expect(tokenStore.setIfCurrent({ refresh: 'r1', epoch }, next)).toBe(false);

    localStorage.setItem(REFRESH_KEY, stored('r1', 'u1'));
    tokenStore.forgetLocal(); // sign-out in this tab
    expect(tokenStore.setIfCurrent({ refresh: 'r1', epoch }, next)).toBe(false);

    expect(tokenStore.setIfCurrent({ refresh: 'r1', epoch: tokenStore.getEpoch() }, next)).toBe(
      true,
    );
    expect(tokenStore.getRefresh()).toBe('r2');
  });

  describe('storage event', () => {
    function setup() {
      const handlers = { onSignedOut: vi.fn(), onIdentityChange: vi.fn() };
      const off = tokenStore.watchOtherTabs(handlers);
      return { handlers, off };
    }
    function fire(init: StorageEventInit) {
      window.dispatchEvent(new StorageEvent('storage', init));
    }

    it('signs this tab out when another tab removes the refresh token', () => {
      tokenStore.set({ access: 'a', refresh: 'r', userId: 'u1' });
      const { handlers, off } = setup();
      const before = localStorage.getItem(REFRESH_KEY);
      localStorage.removeItem(REFRESH_KEY);
      fire({ key: REFRESH_KEY, oldValue: before, newValue: null });
      expect(handlers.onSignedOut).toHaveBeenCalledTimes(1);
      off();
    });

    it('treats a clear() of all storage as a sign-out', () => {
      tokenStore.set({ access: 'a', refresh: 'r', userId: 'u1' });
      const { handlers, off } = setup();
      localStorage.clear();
      fire({ key: null });
      expect(handlers.onSignedOut).toHaveBeenCalledTimes(1);
      off();
    });

    it('signs out on an unparsable value written by another tab, and removes it', () => {
      tokenStore.set({ access: 'a', refresh: 'r', userId: 'u1' });
      const { handlers, off } = setup();
      localStorage.setItem(REFRESH_KEY, 'garbage');
      fire({ key: REFRESH_KEY, newValue: 'garbage' });
      expect(handlers.onSignedOut).toHaveBeenCalledTimes(1);
      expect(localStorage.getItem(REFRESH_KEY)).toBeNull();
      off();
    });

    it('ignores a rotation for the same user and unrelated keys', () => {
      tokenStore.set({ access: 'a', refresh: 'r', userId: 'u1' });
      const { handlers, off } = setup();
      fire({ key: REFRESH_KEY, newValue: stored('r2', 'u1') });
      fire({ key: 'other', oldValue: 'x', newValue: null });
      expect(handlers.onSignedOut).not.toHaveBeenCalled();
      expect(handlers.onIdentityChange).not.toHaveBeenCalled();
      off();
    });

    it('reports another tab signing in as a different user', () => {
      tokenStore.set({ access: 'a', refresh: 'r', userId: 'u1' });
      const { handlers, off } = setup();
      localStorage.setItem(REFRESH_KEY, stored('r9', 'u2'));
      fire({ key: REFRESH_KEY, newValue: stored('r9', 'u2') });
      expect(handlers.onIdentityChange).toHaveBeenCalledTimes(1);
      expect(handlers.onSignedOut).not.toHaveBeenCalled();
      off();
    });

    it('compares with the old value when this tab has not loaded a user yet', () => {
      const { handlers, off } = setup();
      fire({ key: REFRESH_KEY, oldValue: stored('r', 'u1'), newValue: stored('r9', 'u2') });
      expect(handlers.onIdentityChange).toHaveBeenCalledTimes(1);
      off();
    });
  });
});
