import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { DiscoverOut, OverviewRow } from '../api/types';
import { stubFetch } from '../test/mockApi';
import { renderApp } from '../test/render';
import DiscoverPage from './DiscoverPage';

function row(symbol: string, over: Partial<OverviewRow> = {}): OverviewRow {
  return {
    symbol,
    name: `${symbol} Holdings`,
    exchange: 'US',
    currency: 'USD',
    last_price: 12.5,
    change_1w_pct: 2.5,
    sparkline: [1, 2, 3],
    lean: 'bullish',
    country: 'United States',
    sector: null,
    market_cap: 850e6,
    status: 'ok',
    status_reason: null,
    ...over,
  };
}

function page(over: Partial<DiscoverOut> = {}): DiscoverOut {
  return {
    lists: [
      {
        id: 'us_small_movers',
        title: 'Small caps on the move',
        description: 'Smaller US companies whose shares moved most today.',
        rows: [row('AAA'), row('BBB', { country: 'Canada', change_1w_pct: -1 })],
        status: { state: 'ok' },
      },
      {
        id: 'sg_under_radar',
        title: 'Under the radar in Singapore',
        description: 'Smaller Singapore-listed companies with steady trading.',
        rows: [row('CCC', { country: 'Singapore', exchange: 'SGX', currency: 'SGD' })],
        status: { state: 'ok' },
      },
    ],
    updated_at: new Date(Date.now() - 3 * 3600_000).toISOString(),
    data_status: { state: 'ok' },
    ...over,
  };
}

function serve(body: DiscoverOut, symbols: string[] = []) {
  return stubFetch((req) => {
    if (req.path === '/discover') return { body };
    if (req.path === '/watchlist' && req.method === 'GET') return { body: { symbols } };
    if (req.method === 'PUT') return { body: { symbols: [...symbols, 'AAA'] } };
    return undefined;
  });
}

describe('DiscoverPage', () => {
  it('renders the intro, the update time and one section per list', async () => {
    serve(page());
    renderApp(<DiscoverPage />, { route: '/discover' });

    expect(await screen.findByRole('heading', { level: 1, name: 'Discover' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /What is simple rules/ })).toBeInTheDocument();
    expect(await screen.findByText(/Updated 3 hours ago/)).toBeInTheDocument();
    expect(
      screen.getByRole('heading', { level: 2, name: 'Small caps on the move' }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('heading', { level: 2, name: 'Under the radar in Singapore' }),
    ).toBeInTheDocument();
    const table = screen.getByRole('table', { name: 'Small caps on the move' });
    expect(within(table).getAllByText('$850M')).toHaveLength(2);
    expect(screen.getByRole('table', { name: 'Under the radar in Singapore' })).toBeInTheDocument();
  });

  it('shares one country filter across every list', async () => {
    const user = userEvent.setup();
    serve(page());
    renderApp(<DiscoverPage />, { route: '/discover' });
    await screen.findByRole('table', { name: 'Small caps on the move' });
    expect(
      within(screen.getByRole('combobox', { name: 'Country' }))
        .getAllByRole('option')
        .map((o) => o.textContent),
    ).toEqual(['All countries', 'Canada (1)', 'Singapore (1)', 'United States (1)']);

    await user.selectOptions(screen.getByRole('combobox', { name: 'Country' }), 'Singapore');
    expect(screen.getByRole('table', { name: 'Under the radar in Singapore' })).toBeInTheDocument();
    expect(screen.getByText('No stocks from Singapore here.')).toBeInTheDocument();
  });

  it('adds a row to the watchlist with the star', async () => {
    const user = userEvent.setup();
    const seen = serve(page());
    renderApp(<DiscoverPage />, { route: '/discover' });
    const star = await screen.findByRole('button', { name: 'Add AAA to watchlist' });
    await waitFor(() => {
      expect(star).toBeEnabled();
    });
    await user.click(star);
    await waitFor(() => {
      expect(seen.some((r) => r.method === 'PUT' && r.path === '/watchlist/AAA')).toBe(true);
    });
  });

  it('shows a saved symbol as already in the watchlist', async () => {
    serve(page(), ['AAA']);
    renderApp(<DiscoverPage />, { route: '/discover' });
    expect(
      await screen.findByRole('button', { name: 'Remove AAA from watchlist' }),
    ).toBeInTheDocument();
  });

  it('says the lists are being prepared when nothing is cached yet', async () => {
    serve({
      lists: [],
      updated_at: null,
      data_status: {
        state: 'unavailable',
        reason: 'Discover lists are being prepared. Check back in a few minutes.',
      },
    });
    renderApp(<DiscoverPage />, { route: '/discover' });
    expect(
      await screen.findByText('Discover lists are being prepared. Check back in a few minutes.'),
    ).toBeInTheDocument();
    expect(screen.queryByRole('table')).not.toBeInTheDocument();
  });

  it('shows a quiet status line under a stale list only', async () => {
    const body = page();
    const [first, second] = body.lists;
    if (!first || !second) throw new Error('fixture');
    first.status = {
      state: 'stale',
      reason: 'This list could not be refreshed: Yahoo is busy. Showing the last saved version.',
    };
    serve(body);
    renderApp(<DiscoverPage />, { route: '/discover' });
    expect(
      await screen.findByText(/This list could not be refreshed: Yahoo is busy/),
    ).toBeInTheDocument();
    expect(screen.getAllByRole('status')).toHaveLength(1);
  });

  it('shows an error with retry, and recovers', async () => {
    let fail = true;
    stubFetch((req) => {
      if (req.path === '/discover') {
        return fail
          ? { status: 500, body: { error: { code: 'x', message: 'boom', request_id: '' } } }
          : { body: page() };
      }
      if (req.path === '/watchlist') return { body: { symbols: [] } };
      return undefined;
    });
    const user = userEvent.setup();
    renderApp(<DiscoverPage />, { route: '/discover' });
    const retry = await screen.findByRole('button', { name: 'Try again' });
    fail = false;
    await user.click(retry);
    expect(
      await screen.findByRole('table', { name: 'Small caps on the move' }),
    ).toBeInTheDocument();
  });
});
