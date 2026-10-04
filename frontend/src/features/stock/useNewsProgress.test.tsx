import { act, screen, waitFor } from '@testing-library/react';
import { stubFetch } from '../../test/mockApi';
import { renderApp } from '../../test/render';
import { MACRO_POLL_MS, useNewsProgress } from './useStockData';

function progress(done: boolean, monthsDone: number) {
  return {
    months_done: monthsDone,
    months_total: 24,
    in_progress: !done,
    updated_at: '2026-09-25T10:00:00Z',
    status: { state: 'ok' as const },
  };
}

function Poller({ symbol }: { symbol: string }) {
  const news = useNewsProgress(symbol);
  return <p>{news.data ? `${String(news.data.months_done)} months` : 'loading'}</p>;
}

const FINISHED = 'News collection finished. Results updated.';

describe('useNewsProgress', () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  async function tick() {
    await act(async () => {
      await vi.advanceTimersByTimeAsync(MACRO_POLL_MS + 100);
    });
  }

  it('polls while collecting, refreshes macro as months arrive, and announces the finish once', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    let calls = 0;
    const seen = stubFetch((req) => {
      if (req.path !== '/stocks/AAPL/news') return undefined;
      calls += 1;
      return { body: progress(calls >= 3, calls >= 3 ? 24 : calls * 8) };
    });
    const { client } = renderApp(<Poller symbol="AAPL" />);
    const spy = vi.spyOn(client, 'invalidateQueries');
    const invalidated = () => spy.mock.calls.map(([filters]) => String(filters?.queryKey?.[2]));

    expect(await screen.findByText('8 months')).toBeInTheDocument();
    expect(invalidated()).toEqual([]);
    expect(screen.queryByText(FINISHED)).not.toBeInTheDocument();

    await tick();
    expect(await screen.findByText('16 months')).toBeInTheDocument();
    expect(invalidated()).toEqual(['macro']);

    await tick();
    expect(await screen.findByText('24 months')).toBeInTheDocument();
    expect(invalidated()).toEqual(['macro', 'macro', 'chart']);
    expect(await screen.findByText(FINISHED)).toBeInTheDocument();

    // Done: polling stops.
    const before = seen.length;
    await tick();
    await tick();
    expect(seen.length).toBe(before);
  });

  it('stays quiet when a stock is already complete on first load', async () => {
    stubFetch((req) =>
      req.path === '/stocks/AAPL/news' ? { body: progress(true, 24) } : undefined,
    );
    renderApp(<Poller symbol="AAPL" />);
    expect(await screen.findByText('24 months')).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.queryByText(FINISHED)).not.toBeInTheDocument();
    });
  });
});
