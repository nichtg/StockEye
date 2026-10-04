import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '../../api/client';
import { overviewKey, watchlistKey, watchlistRootKey } from '../../api/keys';
import type { OverviewRow, WatchlistOut } from '../../api/types';

export function useWatchlistOverview() {
  return useQuery({
    queryKey: overviewKey,
    queryFn: ({ signal }) => api.get<OverviewRow[]>('/watchlist/overview', { signal }),
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
