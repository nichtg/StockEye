import { useCallback } from 'react';
import { useSearchParams } from 'react-router';
import { nextSort, parseSortDir, parseSortKey, type SortKey, type SortState } from './sortFilter';

export interface TableState {
  sort: SortState | null;
  country: string | null;
  toggleSort: (key: SortKey) => void;
  setSort: (next: SortState | null) => void;
  setCountry: (country: string | null) => void;
}

/**
 * Sort and country filter kept in the URL (?sort=change&dir=desc&country=Singapore), so a reload
 * or a shared link restores the view. A namespace prefixes the keys when several views share a
 * URL. Unknown values are ignored rather than trusted.
 */
export function useTableState(namespace = ''): TableState {
  const [params, setParams] = useSearchParams();
  const name = (base: string) =>
    namespace ? `${namespace}${base.charAt(0).toUpperCase()}${base.slice(1)}` : base;
  const sortParam = name('sort');
  const dirParam = name('dir');
  const countryParam = name('country');

  const key = parseSortKey(params.get(sortParam));
  const sort: SortState | null = key ? { key, dir: parseSortDir(params.get(dirParam)) } : null;
  const rawCountry = params.get(countryParam);
  const country = rawCountry === '' ? null : rawCountry;

  const setSort = useCallback(
    (next: SortState | null) => {
      setParams(
        (prev) => {
          const out = new URLSearchParams(prev);
          if (next) {
            out.set(sortParam, next.key);
            out.set(dirParam, next.dir);
          } else {
            out.delete(sortParam);
            out.delete(dirParam);
          }
          return out;
        },
        { replace: true },
      );
    },
    [setParams, sortParam, dirParam],
  );

  const setCountry = useCallback(
    (value: string | null) => {
      setParams(
        (prev) => {
          const out = new URLSearchParams(prev);
          if (value) out.set(countryParam, value);
          else out.delete(countryParam);
          return out;
        },
        { replace: true },
      );
    },
    [setParams, countryParam],
  );

  const toggleSort = (next: SortKey) => {
    setSort(nextSort(sort, next));
  };

  return { sort, country, toggleSort, setSort, setCountry };
}
