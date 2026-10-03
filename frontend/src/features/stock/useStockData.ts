import { useQuery } from '@tanstack/react-query';
import { api } from '../../api/client';
import { chartKey, macroKey, searchKey, stockKey, technicalKey } from '../../api/keys';
import { ALL_INDICATORS } from '../chart/indicators';
import type {
  ChartData,
  MacroResponse,
  RangeKey,
  StockOut,
  SymbolMatch,
  TechnicalReport,
} from '../../api/types';

export const MACRO_POLL_MS = 5000;

export function useStock(symbol: string) {
  return useQuery({
    queryKey: stockKey(symbol),
    queryFn: ({ signal }) => api.get<StockOut>(`/stocks/${encodeURIComponent(symbol)}`, { signal }),
  });
}

/** Every indicator is fetched with the bars, so toggling one never refetches or discards the chart. */
export function useChart(symbol: string, range: RangeKey) {
  return useQuery({
    queryKey: chartKey(symbol, range),
    queryFn: ({ signal }) =>
      api.get<ChartData>(`/stocks/${encodeURIComponent(symbol)}/chart`, {
        signal,
        query: { range, indicators: ALL_INDICATORS },
      }),
    // Keep the old bars while a new range loads, but never another symbol's under this header.
    placeholderData: (previous, previousQuery) =>
      previousQuery?.queryKey[1] === symbol ? previous : undefined,
  });
}

export function useTechnical(symbol: string) {
  return useQuery({
    queryKey: technicalKey(symbol),
    queryFn: ({ signal }) =>
      api.get<TechnicalReport>(`/stocks/${encodeURIComponent(symbol)}/technical`, { signal }),
  });
}

/** Polls every 5 seconds for as long as the backend says news is still being collected. */
export function useMacro(symbol: string) {
  return useQuery({
    queryKey: macroKey(symbol),
    queryFn: ({ signal }) =>
      api.get<MacroResponse>(`/stocks/${encodeURIComponent(symbol)}/macro`, { signal }),
    refetchInterval: (query) => (query.state.data?.ingestion.in_progress ? MACRO_POLL_MS : false),
  });
}

export function useSymbolSearch(q: string) {
  return useQuery({
    queryKey: searchKey(q),
    enabled: q.length > 0,
    queryFn: ({ signal }) => api.get<SymbolMatch[]>('/stocks/search', { signal, query: { q } }),
  });
}
