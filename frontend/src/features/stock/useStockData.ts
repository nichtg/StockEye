import { useInfiniteQuery, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useRef } from 'react';
import { api } from '../../api/client';
import {
  chartKey,
  chartRootKey,
  macroKey,
  newsArticlesKey,
  newsArticlesMonthKey,
  newsKey,
  profileKey,
  searchKey,
  stockKey,
  technicalKey,
} from '../../api/keys';
import { useNotice } from '../../components/useNotice';
import { ALL_INDICATORS } from '../chart/indicators';
import type {
  ChartData,
  MacroResponse,
  NewsArticlesPage,
  NewsProgress,
  Profile,
  RangeKey,
  StockOut,
  SymbolMatch,
  TechnicalReport,
} from '../../api/types';

export const NEWS_POLL_MS = 5000;
/** Newest months arrive first, so by now there are news dots worth drawing; later months just wait for the finish. */
export const CHART_REFRESH_MONTHS = 3;

export function useStock(symbol: string) {
  return useQuery({
    queryKey: stockKey(symbol),
    queryFn: ({ signal }) => api.get<StockOut>(`/stocks/${encodeURIComponent(symbol)}`, { signal }),
  });
}

/** The server caches the profile for 24 h, so a long staleTime saves round trips. */
export const PROFILE_STALE_MS = 60 * 60 * 1000;
export const NEWS_PAGE_SIZE = 30;

export function useProfile(symbol: string) {
  return useQuery({
    queryKey: profileKey(symbol),
    staleTime: PROFILE_STALE_MS,
    queryFn: ({ signal }) =>
      api.get<Profile>(`/stocks/${encodeURIComponent(symbol)}/profile`, { signal }),
  });
}

/**
 * The News tab's articles, newest first, one cursor page at a time. `month` ("YYYY-MM") narrows
 * them to one month; the first page of the unfiltered list also carries the month chips' counts. Reads only: collection is
 * started by useNewsProgress, which also refetches these pages as months land.
 */
export function useNewsArticles(symbol: string, month?: string, enabled = true) {
  return useInfiniteQuery({
    queryKey: newsArticlesMonthKey(symbol, month),
    enabled,
    initialPageParam: undefined as string | undefined,
    queryFn: ({ signal, pageParam }) =>
      api.get<NewsArticlesPage>(`/stocks/${encodeURIComponent(symbol)}/news/articles`, {
        signal,
        query: { limit: NEWS_PAGE_SIZE, before: pageParam, month },
      }),
    getNextPageParam: (last) => last.next_cursor ?? undefined,
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
    refetchInterval: (q) => (q.state.data?.in_progress ? NEWS_POLL_MS : false),
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
      void client.invalidateQueries({ queryKey: newsArticlesKey(symbol) });
    }
    // The backend rebuilds markers on every month, so refresh the chart once early, not each time.
    const firstDots =
      before.monthsDone < CHART_REFRESH_MONTHS && data.months_done >= CHART_REFRESH_MONTHS;
    if (finished || firstDots) {
      void client.invalidateQueries({ queryKey: chartRootKey(symbol) });
    }
    if (finished) {
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
