import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useRef } from 'react';
import { api } from '../../api/client';
import {
  chartKey,
  chartRootKey,
  macroKey,
  newsKey,
  searchKey,
  stockKey,
  technicalKey,
} from '../../api/keys';
import { useNotice } from '../../components/useNotice';
import { ALL_INDICATORS } from '../chart/indicators';
import type {
  ChartData,
  MacroResponse,
  NewsProgress,
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
    placeholderData: (previous) => (previous?.symbol === symbol ? previous : undefined),
  });
}

export function useTechnical(symbol: string) {
  return useQuery({
    queryKey: technicalKey(symbol),
    queryFn: ({ signal }) =>
      api.get<TechnicalReport>(`/stocks/${encodeURIComponent(symbol)}/technical`, { signal }),
  });
}

export function useMacro(symbol: string) {
  return useQuery({
    queryKey: macroKey(symbol),
    queryFn: ({ signal }) =>
      api.get<MacroResponse>(`/stocks/${encodeURIComponent(symbol)}/macro`, { signal }),
  });
}

/**
 * The single news poller. Asking for it starts collection, so mount it once on the stock page, on
 * every tab. It polls every 5 seconds while collection runs, refreshes the macro results as each
 * batch of months lands, and refreshes the chart and tells the user when collection finishes.
 */
export function useNewsProgress(symbol: string) {
  const client = useQueryClient();
  const notice = useNotice();
  const query = useQuery({
    queryKey: newsKey(symbol),
    queryFn: ({ signal }) =>
      api.get<NewsProgress>(`/stocks/${encodeURIComponent(symbol)}/news`, { signal }),
    refetchInterval: (q) => (q.state.data?.in_progress ? MACRO_POLL_MS : false),
  });

  const previous = useRef<{ symbol: string; monthsDone: number; inProgress: boolean } | undefined>(
    undefined,
  );
  const data = query.data;
  useEffect(() => {
    if (!data) return;
    const before = previous.current;
    previous.current = {
      symbol,
      monthsDone: data.months_done,
      inProgress: data.in_progress,
    };
    // The first answer for a stock is a baseline, never a change.
    if (before?.symbol !== symbol) return;
    const finished = before.inProgress && !data.in_progress;
    if (finished || data.months_done > before.monthsDone) {
      void client.invalidateQueries({ queryKey: macroKey(symbol) });
    }
    if (finished) {
      void client.invalidateQueries({ queryKey: chartRootKey(symbol) });
      notice('News collection finished. Results updated.');
    }
  }, [data, symbol, client, notice]);

  return query;
}

export function useSymbolSearch(q: string) {
  return useQuery({
    queryKey: searchKey(q),
    enabled: q.length > 0,
    queryFn: ({ signal }) => api.get<SymbolMatch[]>('/stocks/search', { signal, query: { q } }),
  });
}
