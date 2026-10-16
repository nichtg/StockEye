import { act, screen } from '@testing-library/react';
import type { OverviewRow } from '../../api/types';
import { stubFetch } from '../../test/mockApi';
import { renderApp } from '../../test/render';
import { overviewKey } from '../../api/keys';
import { useWatchlistOverview } from './useWatchlist';

function Probe() {
  const { data } = useWatchlistOverview();
  return <p>{data ? `rows ${data.length}` : 'loading'}</p>;
}

const base: OverviewRow = {
  symbol: 'AAPL',
  name: 'Apple',
  exchange: 'US',
  currency: 'USD',
  last_price: 1,
  change_1w_pct: 0,
  sparkline: [],
  lean: null,
  country: null,
  sector: null,
  market_cap: null,
  status: 'ok',
  status_reason: null,
};

const overviewCalls = (seen: { path: string }[]) =>
  seen.filter((r) => r.path === '/watchlist/overview').length;

describe('useWatchlistOverview refetch', () => {
  beforeEach(() => vi.useFakeTimers({ shouldAdvanceTime: true }));
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it('refetches stale data after 30 s, at most 3 times', async () => {
    const seen = stubFetch(() => ({ body: [{ ...base, status: 'stale' }] }));
    renderApp(<Probe />);
    await screen.findByText('rows 1');
    expect(overviewCalls(seen)).toBe(1);
    for (let i = 2; i <= 4; i++) {
      await act(() => vi.advanceTimersByTimeAsync(30_000));
      expect(overviewCalls(seen)).toBe(i);
    }
    await act(() => vi.advanceTimersByTimeAsync(120_000));
    expect(overviewCalls(seen)).toBe(4);
  });

  it('starts a fresh run of 3 after a stale, ok, stale sequence', async () => {
    let n = 0;
    const seen = stubFetch(() => {
      n += 1;
      return { body: [{ ...base, status: n === 2 ? 'ok' : 'stale' }] };
    });
    const { client } = renderApp(<Probe />);
    await screen.findByText('rows 1');
    await act(() => vi.advanceTimersByTimeAsync(30_000)); // call 2 is ok: polling stops
    await act(() => vi.advanceTimersByTimeAsync(120_000));
    expect(overviewCalls(seen)).toBe(2);
    await act(() => client.refetchQueries({ queryKey: overviewKey })); // call 3 is stale again
    expect(overviewCalls(seen)).toBe(3);
    for (let i = 4; i <= 6; i++) {
      await act(() => vi.advanceTimersByTimeAsync(30_000));
      expect(overviewCalls(seen)).toBe(i);
    }
    await act(() => vi.advanceTimersByTimeAsync(120_000));
    expect(overviewCalls(seen)).toBe(6);
  });

  it('stops polling when the refetch keeps failing', async () => {
    let n = 0;
    const seen = stubFetch(() => {
      n += 1;
      return n === 1 ? { body: [{ ...base, status: 'stale' }] } : { status: 500, body: {} };
    });
    renderApp(<Probe />);
    await screen.findByText('rows 1');
    await act(() => vi.advanceTimersByTimeAsync(300_000));
    expect(overviewCalls(seen)).toBe(4);
  });

  it('does not refetch when every row is ok', async () => {
    const seen = stubFetch(() => ({ body: [base] }));
    renderApp(<Probe />);
    await screen.findByText('rows 1');
    await act(() => vi.advanceTimersByTimeAsync(120_000));
    expect(overviewCalls(seen)).toBe(1);
  });
});
