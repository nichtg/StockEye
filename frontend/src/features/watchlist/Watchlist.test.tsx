import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { OverviewRow } from '../../api/types';
import HomePage from '../../pages/HomePage';
import { stubFetch } from '../../test/mockApi';
import { renderApp } from '../../test/render';
import { StockHeader } from '../stock/StockHeader';
import { stockFixture } from '../../test/fixtures';

const aapl: OverviewRow = {
  symbol: 'AAPL',
  name: 'Apple Inc.',
  exchange: 'US',
  currency: 'USD',
  last_price: 333.69,
  change_1w_pct: -2.2,
  sparkline: [1, 2, 3, 2, 3, 4],
  lean: 'bullish',
  status: 'ok',
  status_reason: null,
};
const broken: OverviewRow = {
  symbol: 'ZZZZ',
  name: null,
  exchange: null,
  currency: null,
  last_price: null,
  change_1w_pct: null,
  sparkline: [],
  lean: null,
  status: 'unavailable',
  status_reason: 'Yahoo Finance could not find this symbol.',
};

describe('watchlist overview', () => {
  it('links the symbol, shows the lean as text, and flags unavailable rows', async () => {
    stubFetch((req) => (req.path === '/watchlist/overview' ? { body: [aapl, broken] } : undefined));
    renderApp(<HomePage />);

    const link = await screen.findByRole('link', { name: 'AAPL' });
    expect(link).toHaveAttribute('href', '/stock/AAPL');
    const row = link.closest('tr');
    expect(row).not.toBeNull();
    if (!row) return;
    expect(within(row).getByText('$333.69')).toBeInTheDocument();
    expect(within(row).getByText(/2\.2%/)).toHaveTextContent('−2.2%');
    expect(within(row).getByText('Bullish lean')).toBeInTheDocument();
    // Only the header carries the outlook explainer.
    expect(screen.getAllByRole('button', { name: /What is Outlook/ })).toHaveLength(1);

    const bad = screen.getByRole('link', { name: 'ZZZZ' }).closest('tr');
    if (!bad) throw new Error('row missing');
    expect(within(bad).getByText('Data unavailable')).toBeInTheDocument();
    expect(within(bad).queryByText(/Bullish|Neutral|Bearish/)).not.toBeInTheDocument();
  });

  it('shows the empty state with a next step', async () => {
    stubFetch((req) => (req.path === '/watchlist/overview' ? { body: [] } : undefined));
    renderApp(<HomePage />);
    expect(
      await screen.findByText('Your watchlist is empty. Search for a stock to add it.'),
    ).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Search for a stock' })).toBeInTheDocument();
  });

  it('shows an error with retry', async () => {
    stubFetch(() => ({
      status: 500,
      body: { error: { code: 'x', message: 'boom', request_id: '' } },
    }));
    renderApp(<HomePage />);
    expect(await screen.findByRole('button', { name: 'Try again' })).toBeInTheDocument();
  });

  it('removes a row immediately and puts it back if the server refuses', async () => {
    let release: () => void = () => undefined;
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    stubFetch((req) => {
      if (req.path === '/watchlist/overview') return { body: [aapl] };
      if (req.method === 'DELETE')
        return { status: 500, body: { error: { code: 'x', message: 'no', request_id: '' } } };
      return undefined;
    });
    // Hold the DELETE response so the optimistic state is observable.
    const base = globalThis.fetch;
    vi.stubGlobal('fetch', async (input: RequestInfo | URL, init?: RequestInit) => {
      if (init?.method === 'DELETE') await gate;
      return base(input, init);
    });

    const user = userEvent.setup();
    renderApp(<HomePage />);
    await user.click(await screen.findByRole('button', { name: 'Remove AAPL from watchlist' }));
    await waitFor(() => {
      expect(screen.queryByRole('link', { name: 'AAPL' })).not.toBeInTheDocument();
    });
    release();
    expect(await screen.findByRole('link', { name: 'AAPL' })).toBeInTheDocument();
  });

  it('offers Undo after a removal, which puts the symbol back', async () => {
    let saved = ['AAPL'];
    const seen = stubFetch((req) => {
      if (req.path === '/watchlist/overview') return { body: saved.length ? [aapl] : [] };
      if (req.path === '/watchlist' && req.method === 'GET') return { body: { symbols: saved } };
      if (req.method === 'DELETE') {
        saved = [];
        return { body: { symbols: saved } };
      }
      if (req.method === 'PUT') {
        saved = ['AAPL'];
        return { body: { symbols: saved } };
      }
      return undefined;
    });
    const user = userEvent.setup();
    renderApp(<HomePage />);
    await user.click(await screen.findByRole('button', { name: 'Remove AAPL from watchlist' }));
    expect(await screen.findByText('Removed AAPL')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Undo' }));
    await waitFor(() => {
      expect(seen.some((r) => r.method === 'PUT')).toBe(true);
    });
    expect(await screen.findByRole('link', { name: 'AAPL' })).toBeInTheDocument();
  });

  it('gives each of two quick removals its own Undo', async () => {
    const msft: OverviewRow = { ...aapl, symbol: 'MSFT', name: 'Microsoft Corp.' };
    let saved = ['AAPL', 'MSFT'];
    const seen = stubFetch((req) => {
      if (req.path === '/watchlist/overview')
        return { body: [aapl, msft].filter((r) => saved.includes(r.symbol)) };
      if (req.path === '/watchlist' && req.method === 'GET') return { body: { symbols: saved } };
      if (req.method === 'DELETE') {
        saved = saved.filter((symbol) => !req.path.endsWith(`/${symbol}`));
        return { body: { symbols: saved } };
      }
      if (req.method === 'PUT') {
        const added = /\/([^/]+)$/.exec(req.path)?.[1];
        if (added) saved = [...saved, added];
        return { body: { symbols: saved } };
      }
      return undefined;
    });
    const user = userEvent.setup();
    renderApp(<HomePage />);
    const removeAapl = await screen.findByRole('button', { name: 'Remove AAPL from watchlist' });
    const removeMsft = screen.getByRole('button', { name: 'Remove MSFT from watchlist' });
    // Back to back: the first toast is still arriving when the second removal lands.
    fireEvent.click(removeAapl);
    fireEvent.click(removeMsft);
    // The two DELETEs may settle in either order; each removal still gets its toast, in turn.
    const first = await screen.findByText(/^Removed (AAPL|MSFT)$/);
    const other = first.textContent === 'Removed AAPL' ? 'MSFT' : 'AAPL';
    expect(await screen.findByText(`Removed ${other}`)).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Undo' }));
    await waitFor(() => {
      expect(seen.some((r) => r.method === 'PUT' && r.path.endsWith(`/${other}`))).toBe(true);
    });
    expect(await screen.findByRole('link', { name: other })).toBeInTheDocument();
  });
});

describe('watchlist toggle on the stock header', () => {
  it('adds optimistically, then shows the server message on a 409', async () => {
    const symbols: string[] = [];
    stubFetch((req) => {
      if (req.path === '/watchlist' && req.method === 'GET') return { body: { symbols } };
      if (req.method === 'PUT') {
        return {
          status: 409,
          body: {
            error: {
              code: 'conflict',
              message: 'Your watchlist is full (50 symbols maximum).',
              request_id: '',
            },
          },
        };
      }
      return undefined;
    });
    const user = userEvent.setup();
    renderApp(<StockHeader symbol="AAPL" stock={stockFixture} loading={false} statuses={[]} />);

    const button = await screen.findByRole('button', { name: 'Add to watchlist' });
    await waitFor(() => {
      expect(button).toBeEnabled();
    });
    await user.click(button);
    expect(
      await screen.findByText('Your watchlist is full (50 symbols maximum).'),
    ).toBeInTheDocument();
    // Rolled back to the real state.
    expect(await screen.findByRole('button', { name: 'Add to watchlist' })).toBeInTheDocument();
  });

  it('shows the server message on a 404 for an unknown symbol and rolls back', async () => {
    stubFetch((req) => {
      if (req.path === '/watchlist' && req.method === 'GET') return { body: { symbols: [] } };
      if (req.method === 'PUT') {
        return {
          status: 404,
          body: {
            error: { code: 'not_found', message: 'We couldn’t find that stock.', request_id: '' },
          },
        };
      }
      return undefined;
    });
    const user = userEvent.setup();
    renderApp(<StockHeader symbol="NOPE" stock={stockFixture} loading={false} statuses={[]} />);
    const button = await screen.findByRole('button', { name: 'Add to watchlist' });
    await waitFor(() => {
      expect(button).toBeEnabled();
    });
    await user.click(button);
    expect(await screen.findByText('We couldn’t find that stock.')).toBeInTheDocument();
    expect(await screen.findByRole('button', { name: 'Add to watchlist' })).toBeInTheDocument();
  });

  it('flips to In watchlist right away when the add succeeds', async () => {
    let saved: string[] = [];
    stubFetch((req) => {
      if (req.path === '/watchlist' && req.method === 'GET') return { body: { symbols: saved } };
      if (req.method === 'PUT') {
        saved = ['AAPL'];
        return { body: { symbols: saved } };
      }
      return undefined;
    });
    const user = userEvent.setup();
    renderApp(<StockHeader symbol="AAPL" stock={stockFixture} loading={false} statuses={[]} />);
    const button = await screen.findByRole('button', { name: 'Add to watchlist' });
    await waitFor(() => {
      expect(button).toBeEnabled();
    });
    await user.click(button);
    expect(
      await screen.findByRole('button', {
        name: /^(In watchlist\W*activate to remove|Remove from watchlist)$/,
      }),
    ).toBeInTheDocument();
  });
});
