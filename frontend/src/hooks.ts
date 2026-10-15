import { useEffect, useState } from 'react';

/** Matches the static title in index.html, so the landing page and a fresh load agree. */
export const DEFAULT_TITLE = 'StockEye – plain-English stock analysis';

export function useDocumentTitle(title = ''): void {
  useEffect(() => {
    document.title = title ? `${title} – StockEye` : DEFAULT_TITLE;
  }, [title]);
}

export function useDebouncedValue<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const id = setTimeout(() => {
      setDebounced(value);
    }, delayMs);
    return () => {
      clearTimeout(id);
    };
  }, [value, delayMs]);
  return debounced;
}
