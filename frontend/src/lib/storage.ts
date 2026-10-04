/** Reads a stored value through `parse`; blocked or missing storage yields the fallback. */
export function readStored<T>(key: string, parse: (raw: string | null) => T, fallback: T): T {
  try {
    return parse(localStorage.getItem(key));
  } catch {
    return fallback;
  }
}

/** Storage may be blocked; the value still works for this visit. */
export function writeStored(key: string, value: unknown): void {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    // Nothing to do: the choice just won't outlive the visit.
  }
}
