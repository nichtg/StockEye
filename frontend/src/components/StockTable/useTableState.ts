import { useCallback } from 'react';
import { useSearchParams } from 'react-router';
import { sortKeysFor } from './columns';
import {
  nextSort,
  parseSortDir,
  parseSortKey,
  type SortKey,
  type SortState,
  type TableColumns,
} from './sortFilter';

/** Everything a table and its controls need: the view of the URL plus the ways to change it. */
export interface TableState {
  /** Which columns the table shows; decides which sort keys are valid. */
  columns: TableColumns;
  sort: SortState | null;
  country: string | null;
  toggleSort: (key: SortKey) => void;
  setSort: (next: SortState | null) => void;
  setCountry: (country: string | null) => void;
}

interface Options {
  /** Prefixes the URL keys when several views share one URL. */
  namespace?: string;
  columns: TableColumns;
}

/**
 * Sort and country filter kept in the URL (?sort=change&dir=desc&country=Singapore), so a reload
 * or a shared link restores the view. Unknown values, and sort keys the columns do not have, are
 * ignored rather than trusted.
 */
export function useTableState({ namespace = '', columns }: Options): TableState {
  const [params, setParams] = useSearchParams();
  const name = (base: string) =>
    namespace ? `${namespace}${base.charAt(0).toUpperCase()}${base.slice(1)}` : base;
  const sortParam = name('sort');
  const dirParam = name('dir');
  const countryParam = name('country');

  const readSort = useCallback(
    (p: URLSearchParams): SortState | null => {
      const key = parseSortKey(p.get(sortParam), sortKeysFor(columns));
      return key ? { key, dir: parseSortDir(p.get(dirParam)) } : null;
    },
    [sortParam, dirParam, columns],
  );
  const writeSort = useCallback(
    (out: URLSearchParams, next: SortState | null) => {
      if (next) {
        out.set(sortParam, next.key);
        out.set(dirParam, next.dir);
      } else {
        out.delete(sortParam);
        out.delete(dirParam);
      }
    },
    [sortParam, dirParam],
  );

  const sort = readSort(params);
  const rawCountry = params.get(countryParam);
  const country = rawCountry === '' ? null : rawCountry;

  const setSort = useCallback(
    (next: SortState | null) => {
      setParams(
        (prev) => {
          const out = new URLSearchParams(prev);
          writeSort(out, next);
          return out;
        },
        { replace: true },
      );
    },
    [setParams, writeSort],
  );

  // Reads the current sort from the URL itself, so the callback stays stable between renders.
  const toggleSort = useCallback(
    (key: SortKey) => {
      setParams(
        (prev) => {
          const out = new URLSearchParams(prev);
          writeSort(out, nextSort(readSort(prev), key));
          return out;
        },
        { replace: true },
      );
    },
    [setParams, writeSort, readSort],
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

  return { columns, sort, country, toggleSort, setSort, setCountry };
}
