import { describe, expect, it, vi } from 'vitest';
import { REFRESH_KEY, tokenStore } from './tokens';

describe('token store', () => {
  it('keeps the access token in memory and the refresh token in localStorage', () => {
    tokenStore.set({ access: 'a', refresh: 'r' });
    expect(tokenStore.getAccess()).toBe('a');
    expect(localStorage.getItem(REFRESH_KEY)).toBe('r');
    expect(Object.values(localStorage)).not.toContain('a');
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
      tokenStore.set({ access: 'a', refresh: 'r' });
    }).not.toThrow();
    expect(tokenStore.getRefresh()).toBe('r'); // memory copy for this visit
    expect(() => {
      tokenStore.clear();
    }).not.toThrow();
    expect(tokenStore.getRefresh()).toBeNull();
    expect(tokenStore.getAccess()).toBeNull();
  });

  describe('storage event', () => {
    function fire(init: StorageEventInit) {
      window.dispatchEvent(new StorageEvent('storage', init));
    }

    it('signs this tab out when another tab removes the refresh token', () => {
      tokenStore.set({ access: 'a', refresh: 'r' });
      const onSignedOut = vi.fn();
      const off = tokenStore.onSignedOutElsewhere(onSignedOut);
      localStorage.removeItem(REFRESH_KEY);
      fire({ key: REFRESH_KEY, oldValue: 'r', newValue: null });
      expect(onSignedOut).toHaveBeenCalledTimes(1);
      expect(tokenStore.getAccess()).toBeNull();
      off();
    });

    it('treats a clear() of all storage as a sign-out', () => {
      tokenStore.set({ access: 'a', refresh: 'r' });
      const onSignedOut = vi.fn();
      const off = tokenStore.onSignedOutElsewhere(onSignedOut);
      localStorage.clear();
      fire({ key: null });
      expect(onSignedOut).toHaveBeenCalledTimes(1);
      off();
    });

    it('ignores a rotation and unrelated keys', () => {
      tokenStore.set({ access: 'a', refresh: 'r' });
      const onSignedOut = vi.fn();
      const off = tokenStore.onSignedOutElsewhere(onSignedOut);
      fire({ key: REFRESH_KEY, oldValue: 'r', newValue: 'r2' });
      fire({ key: 'other', oldValue: 'x', newValue: null });
      expect(onSignedOut).not.toHaveBeenCalled();
      expect(tokenStore.getAccess()).toBe('a');
      off();
    });
  });
});
