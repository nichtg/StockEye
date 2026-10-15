import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { DiscoverOut } from '../api/types';
import { stubFetch } from '../test/mockApi';
import { renderApp } from '../test/render';
import DiscoverPage from './DiscoverPage';

type DiscoverRow = DiscoverOut['lists'][number]['rows'][number];

function row(symbol: string, over: Partial<DiscoverRow> = {}): DiscoverRow {
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
    pe_ratio: 10,
    avg_traded_value: 1.2e6,
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
        order_label: 'Biggest 1-week move first',
        rows: [row('AAA'), row('BBB', { country: 'Canada', change_1w_pct: -1 })],
        status: { state: 'ok' },
      },
      {
        id: 'us_value_small',
        title: 'Lower-priced small caps',
        description: 'Smaller US companies valued at under 15 times their earnings.',
        order_label: 'Lowest price-to-earnings first',
        rows: [
          row('VAL1', { pe_ratio: 8.44, last_price: 30 }),
          row('VAL2', { pe_ratio: 12.3, last_price: 10 }),
          row('VAL3', { pe_ratio: 14.9, last_price: 20 }),
        ],
        status: { state: 'ok' },
      },
      {
        id: 'sg_under_radar',
        title: 'Under the radar in Singapore',
        description: 'Smaller Singapore-listed companies with steady trading.',
        order_label: 'Most traded first',
        rows: [
          row('CCC', {
            country: 'Singapore',
            exchange: 'SGX',
            currency: 'SGD',
            avg_traded_value: 1.2e6,
          }),
        ],
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

  it('shows the page-level status when the whole cache is stale', async () => {
    serve(
      page({
        data_status: {
          state: 'stale',
          reason: 'These lists did not refresh overnight. Showing the last saved version.',
        },
      }),
    );
    renderApp(<DiscoverPage />, { route: '/discover' });
    expect(await screen.findByText(/These lists did not refresh overnight/)).toBeInTheDocument();
  });

  it('explains an unknown country in the link once, with a way back', async () => {
    const user = userEvent.setup();
    serve(page());
    renderApp(<DiscoverPage />, { route: '/discover?discoverCountry=Peru' });
    expect(await screen.findByText('No stocks from Peru here.')).toBeInTheDocument();
    expect(screen.getAllByText(/No stocks from Peru/)).toHaveLength(1);
    expect(screen.queryByText(/None from Peru in this list/)).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Show all countries' }));
    expect(
      await screen.findByRole('table', { name: 'Small caps on the move' }),
    ).toBeInTheDocument();
  });

  it('says so quietly in a list with nothing from the chosen country', async () => {
    serve(page());
    renderApp(<DiscoverPage />, { route: '/discover?discoverCountry=Singapore' });
    // The movers and value lists have nothing from Singapore; the Singapore list does.
    expect(await screen.findAllByText('None from Singapore in this list.')).toHaveLength(2);
    expect(screen.getAllByText(/None from Singapore in this list/)).toHaveLength(2);
    expect(screen.queryByText(/No stocks from/)).not.toBeInTheDocument();
  });

  it('shares one country filter across every list', async () => {
    const user = userEvent.setup();
    serve(page());
    renderApp(<DiscoverPage />, { route: '/discover' });
    await screen.findByRole('table', { name: 'Small caps on the move' });
    const group = screen.getByRole('radiogroup', { name: 'Filter by country' });
    expect(
      within(group)
        .getAllByRole('radio')
        .map((r) => r.textContent),
    ).toEqual(['All', 'Canada1', 'Singapore1', 'United States4']);

    await user.click(within(group).getByRole('radio', { name: 'Singapore, 1 stock' }));
    expect(screen.getByRole('radio', { name: 'Singapore, 1 stock' })).toBeChecked();
    expect(screen.getByRole('table', { name: 'Under the radar in Singapore' })).toBeInTheDocument();
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

  describe('list order', () => {
    const symbolsIn = (name: string) =>
      within(screen.getByRole('table', { name }))
        .getAllByRole('link')
        .map((a) => a.textContent);

    it('shows each list in server order with its Ordered by line', async () => {
      serve(page());
      renderApp(<DiscoverPage />, { route: '/discover' });
      await screen.findByRole('table', { name: 'Lower-priced small caps' });
      expect(symbolsIn('Lower-priced small caps')).toEqual(['VAL1', 'VAL2', 'VAL3']);
      expect(screen.getByText('Ordered by: Biggest 1-week move first')).toBeInTheDocument();
      expect(screen.getByText('Ordered by: Lowest price-to-earnings first')).toBeInTheDocument();
      expect(screen.getByText('Ordered by: Most traded first')).toBeInTheDocument();
      expect(screen.queryByText(/Reset to list order/)).not.toBeInTheDocument();
    });

    it('sorts every list by a chosen column and resets to the server order', async () => {
      const user = userEvent.setup();
      serve(page());
      renderApp(<DiscoverPage />, { route: '/discover' });
      const table = await screen.findByRole('table', { name: 'Lower-priced small caps' });
      // Price is a shared column: ascending puts VAL2 (10) first.
      await user.click(within(table).getByRole('button', { name: 'Last' }));
      expect(symbolsIn('Lower-priced small caps')).toEqual(['VAL2', 'VAL3', 'VAL1']);
      expect(screen.getAllByText(/Sorted by Last price, ascending/)).toHaveLength(3);
      expect(screen.queryByText(/Ordered by:/)).not.toBeInTheDocument();

      await user.click(screen.getAllByRole('button', { name: 'Reset to list order' })[0]!);
      expect(symbolsIn('Lower-priced small caps')).toEqual(['VAL1', 'VAL2', 'VAL3']);
      expect(screen.getByText('Ordered by: Lowest price-to-earnings first')).toBeInTheDocument();
    });

    it('shows P/E only on the value list and Avg daily trading only on Singapore', async () => {
      const user = userEvent.setup();
      serve(page());
      renderApp(<DiscoverPage />, { route: '/discover' });
      const value = await screen.findByRole('table', { name: 'Lower-priced small caps' });
      const sg = screen.getByRole('table', { name: 'Under the radar in Singapore' });
      const movers = screen.getByRole('table', { name: 'Small caps on the move' });

      expect(within(value).getByRole('button', { name: 'P/E' })).toBeInTheDocument();
      expect(within(value).getByRole('button', { name: /What is P.E ratio/ })).toBeInTheDocument();
      expect(within(value).getByText('8.4')).toBeInTheDocument();
      expect(within(value).queryByText('Avg daily trading')).not.toBeInTheDocument();
      expect(within(sg).getByRole('button', { name: 'Avg daily trading' })).toBeInTheDocument();
      expect(
        within(sg).getByRole('button', { name: /What is Avg daily trading/ }),
      ).toBeInTheDocument();
      expect(within(sg).getByText('S$1.2M')).toBeInTheDocument();
      expect(within(sg).queryByRole('button', { name: 'P/E' })).not.toBeInTheDocument();
      expect(within(movers).queryByRole('button', { name: 'P/E' })).not.toBeInTheDocument();
      expect(
        within(movers).queryByRole('button', { name: 'Avg daily trading' }),
      ).not.toBeInTheDocument();

      // Both sort: P/E descending puts the highest first.
      await user.click(within(value).getByRole('button', { name: 'P/E' }));
      await user.click(within(value).getByRole('button', { name: 'P/E' }));
      expect(
        within(value)
          .getAllByRole('link')
          .map((a) => a.textContent),
      ).toEqual(['VAL3', 'VAL2', 'VAL1']);
      await user.click(within(sg).getByRole('button', { name: 'Avg daily trading' }));
      expect(screen.getAllByText(/Sorted by Avg daily trading, ascending/)).toHaveLength(3);
    });
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
