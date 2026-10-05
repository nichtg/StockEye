/**
 * The single owner of the session tokens.
 *
 * - The access token lives in memory only and dies with the tab.
 * - The refresh token lives in localStorage under one key, stored together with the user id as
 *   one JSON value, so a reload (or another tab) can continue the session and a tab can notice
 *   that another tab signed in as someone else. Every storage call is wrapped: storage can throw
 *   (blocked, quota). If it does, a memory copy keeps the current visit signed in.
 * - `epoch` counts sign-outs in this tab. An in-flight refresh remembers the epoch it started in
 *   and may only store its result if it is unchanged, so a refresh can never undo a sign-out.
 *
 * localStorage is readable by any script on this origin, which is why the CSP forbids inline and
 * third-party scripts and why refresh tokens rotate.
 */
export const REFRESH_KEY = 'stockeye.session';

interface Stored {
  t: string; // refresh token
  u: string; // user id
}

let access: string | null = null;
let memory: Stored | null = null;
let epoch = 0;

function parse(raw: string | null): Stored | null {
  if (raw === null) return null;
  try {
    const v: unknown = JSON.parse(raw);
    if (typeof v === 'object' && v !== null) {
      const { t, u } = v as Record<string, unknown>;
      if (typeof t === 'string' && t && typeof u === 'string' && u) return { t, u };
    }
  } catch {
    // fall through: unparsable
  }
  return null;
}

function removeStorage(): void {
  try {
    localStorage.removeItem(REFRESH_KEY);
  } catch {
    // Nothing more to clear.
  }
}

/** The stored session; `undefined` when storage is unavailable. Unparsable values are removed. */
function readStorage(): Stored | null | undefined {
  let raw: string | null;
  try {
    raw = localStorage.getItem(REFRESH_KEY);
  } catch {
    return undefined;
  }
  const stored = parse(raw);
  if (raw !== null && !stored) removeStorage();
  return stored;
}

function current(): Stored | null {
  const stored = readStorage();
  return stored === undefined ? memory : stored;
}

function write(refresh: string, userId: string): void {
  memory = { t: refresh, u: userId };
  try {
    localStorage.setItem(REFRESH_KEY, JSON.stringify(memory));
  } catch {
    // The memory copy keeps this visit signed in; it just will not survive a reload.
  }
}

export interface OtherTabHandlers {
  /** The refresh token was removed: logout, expiry or deletion elsewhere. */
  onSignedOut: () => void;
  /** Another tab signed in as a different user. */
  onIdentityChange: () => void;
}

export const tokenStore = {
  getAccess: (): string | null => access,

  /** Always reads storage, so a rotation by another tab is seen immediately. */
  getRefresh: (): string | null => current()?.t ?? null,

  getUserId: (): string | null => current()?.u ?? null,

  getEpoch: (): number => epoch,

  set(tokens: { access: string; refresh: string; userId: string }): void {
    access = tokens.access;
    write(tokens.refresh, tokens.userId);
  },

  /**
   * Stores a refresh result only if no sign-out happened since it started (`epoch`) and storage
   * still holds the token it was started with (another tab has not rotated or replaced it).
   * Returns whether it was stored; otherwise the result must be discarded.
   */
  setIfCurrent(
    expected: { refresh: string; epoch: number },
    tokens: { access: string; refresh: string; userId: string },
  ): boolean {
    if (epoch !== expected.epoch || current()?.t !== expected.refresh) return false;
    this.set(tokens);
    return true;
  },

  /** Signs out everywhere: this tab's memory and the shared storage. */
  clear(): void {
    this.forgetLocal();
    removeStorage();
  },

  /** Signs out this tab only; leaves storage to whoever else owns it (another tab's new login). */
  forgetLocal(): void {
    epoch += 1;
    access = null;
    memory = null;
  },

  /** Reacts to other tabs' changes through the `storage` event. Returns an unsubscribe. */
  watchOtherTabs(handlers: OtherTabHandlers): () => void {
    const listener = (event: StorageEvent) => {
      if (event.key !== null && event.key !== REFRESH_KEY) return;
      const now = event.key === null ? current() : parse(event.newValue);
      if (!now) {
        if (event.key !== null && event.newValue !== null) {
          removeStorage(); // unparsable value: drop it and sign out
        }
        handlers.onSignedOut();
        return;
      }
      const before = memory?.u ?? parse(event.oldValue)?.u;
      if (before && before !== now.u) handlers.onIdentityChange();
      else memory = now;
    };
    window.addEventListener('storage', listener);
    return () => {
      window.removeEventListener('storage', listener);
    };
  },
};

export type TokenStore = typeof tokenStore;
