import { useRef } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '../../api/client';
import { overviewKey, watchlistKey, watchlistRootKey } from '../../api/keys';
import type { OverviewRow, WatchlistOut } from '../../api/types';

const STALE_REFETCH_MS = 30_000;
const STALE_REFETCH_MAX = 3;

/**
 * Stale rows usually clear once the background refresh finishes, so quietly refetch every ~30 s,
 * at most 3 times in a row. Background refetches keep the previous data, so nothing flickers.
 */
export function useWatchlistOverview() {
  // dataUpdateCount when the current run of stale responses began.
  const staleSince = useRef<number | null>(null);
  return useQuery({
    queryKey: overviewKey,
    queryFn: ({ signal }) => api.get<OverviewRow[]>('/watchlist/overview', { signal }),
    refetchInterval: (query) => {
      if (!query.state.data?.some((r) => r.status === 'stale')) {
        staleSince.current = null;
        return false;
      }
      staleSince.current ??= query.state.dataUpdateCount;
      return query.state.dataUpdateCount - staleSince.current >= STALE_REFETCH_MAX
        ? false
        : STALE_REFETCH_MS;
    },
  });
}

export function useWatchlistSymbols() {
  return useQuery({
    queryKey: watchlistKey,
    queryFn: ({ signal }) => api.get<WatchlistOut>('/watchlist', { signal }),
    select: (data) => data.symbols,
  });
}

interface ToggleVars {
  symbol: string;
  add: boolean;
}

interface Snapshot {
  symbols: WatchlistOut | undefined;
  overview: OverviewRow[] | undefined;
}

/**
 * Adds or removes a symbol. The caches update immediately and roll back if the server refuses
 * (for example a 409 when the list is full); either way the real state is refetched afterwards.
 */
export function useWatchlistMutation() {
  const qc = useQueryClient();
  return useMutation<WatchlistOut, Error, ToggleVars, Snapshot>({
    mutationFn: ({ symbol, add }) =>
      add
        ? api.put<WatchlistOut>(`/watchlist/${encodeURIComponent(symbol)}`)
        : api.delete<WatchlistOut>(`/watchlist/${encodeURIComponent(symbol)}`),
    onMutate: async ({ symbol, add }) => {
      await qc.cancelQueries({ queryKey: watchlistRootKey });
      const snapshot: Snapshot = {
        symbols: qc.getQueryData<WatchlistOut>(watchlistKey),
        overview: qc.getQueryData<OverviewRow[]>(overviewKey),
      };
      qc.setQueryData<WatchlistOut>(watchlistKey, (old) => {
        const current = old?.symbols ?? [];
        const next = add
          ? current.includes(symbol)
            ? current
            : [...current, symbol]
          : current.filter((s) => s !== symbol);
        return { symbols: next };
      });
      if (!add) {
        qc.setQueryData<OverviewRow[]>(overviewKey, (old) =>
          old?.filter((row) => row.symbol !== symbol),
        );
      }
      return snapshot;
    },
    onError: (_error, _vars, snapshot) => {
      if (!snapshot) return;
      qc.setQueryData(watchlistKey, snapshot.symbols);
      qc.setQueryData(overviewKey, snapshot.overview);
    },
    onSettled: () => qc.invalidateQueries({ queryKey: watchlistRootKey }),
  });
}
