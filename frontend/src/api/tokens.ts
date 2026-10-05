/**
 * The single owner of the session tokens.
 *
 * - The access token lives in memory only and dies with the tab.
 * - The refresh token lives in localStorage under one key, so a reload (or another tab) can
 *   continue the session. Every storage call is wrapped: storage can throw (blocked, quota).
 *   If it does, the refresh token still works for this tab from a memory copy.
 *
 * localStorage is readable by any script on this origin, which is why the CSP forbids inline and
 * third-party scripts and why refresh tokens rotate.
 */
export const REFRESH_KEY = 'stockeye.refresh';

let access: string | null = null;
let refreshMemory: string | null = null;

function readStorage(): string | null | undefined {
  try {
    return localStorage.getItem(REFRESH_KEY);
  } catch {
    return undefined; // storage unavailable
  }
}

export const tokenStore = {
  getAccess: (): string | null => access,

  /** Always reads storage, so a rotation by another tab is seen immediately. */
  getRefresh: (): string | null => {
    const stored = readStorage();
    return stored === undefined ? refreshMemory : stored;
  },

  set(tokens: { access: string; refresh: string }): void {
    access = tokens.access;
    refreshMemory = tokens.refresh;
    try {
      localStorage.setItem(REFRESH_KEY, tokens.refresh);
    } catch {
      // The memory copy keeps this visit signed in; it just will not survive a reload.
    }
  },

  clear(): void {
    access = null;
    refreshMemory = null;
    try {
      localStorage.removeItem(REFRESH_KEY);
    } catch {
      // Nothing more to clear.
    }
  },

  /**
   * Calls `onSignedOut` when another tab removes the refresh token (logout, expiry, deletion).
   * A different value is a rotation by another tab and is not a sign-out. Returns an unsubscribe.
   */
  onSignedOutElsewhere(onSignedOut: () => void): () => void {
    const listener = (event: StorageEvent) => {
      if (event.key !== null && event.key !== REFRESH_KEY) return;
      if (event.key !== null && event.newValue !== null) return;
      if (event.key === null && readStorage()) return;
      access = null;
      refreshMemory = null;
      onSignedOut();
    };
    window.addEventListener('storage', listener);
    return () => {
      window.removeEventListener('storage', listener);
    };
  },
};

export type TokenStore = typeof tokenStore;
