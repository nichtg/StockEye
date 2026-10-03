import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { chartKey } from '../../api/keys';
import type { ChartData, RangeKey } from '../../api/types';
import { useChart } from './useStockData';

const bars = (symbol: string, range: RangeKey) =>
  ({ symbol, range, candles: [] }) as unknown as ChartData;

function setup() {
  // Every request hangs, so only what is cached or kept as a placeholder can show.
  vi.stubGlobal(
    'fetch',
    vi.fn(() => new Promise<Response>(() => undefined)),
  );
  document.cookie = 'se_csrf=test; path=/';
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  client.setQueryData(chartKey('AAPL', '6M'), bars('AAPL', '6M'));
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  return renderHook(({ symbol, range }) => useChart(symbol, range), {
    wrapper,
    initialProps: { symbol: 'AAPL', range: '6M' as RangeKey },
  });
}

describe('useChart placeholder', () => {
  it('keeps the previous bars while another range of the same symbol loads', async () => {
    const { result, rerender } = setup();
    rerender({ symbol: 'AAPL', range: '1M' });
    await waitFor(() => {
      expect(result.current.isPlaceholderData).toBe(true);
    });
    expect(result.current.data?.symbol).toBe('AAPL');
  });

  it('never shows another symbol’s bars while a new symbol loads', () => {
    const { result, rerender } = setup();
    expect(result.current.data?.symbol).toBe('AAPL');
    rerender({ symbol: 'MSFT', range: '6M' });
    expect(result.current.data).toBeUndefined();
  });
});
