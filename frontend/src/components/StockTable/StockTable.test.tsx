import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useLocation } from 'react-router';
import type { OverviewRow } from '../../api/types';
import { RemoveButton } from '../../features/watchlist/RemoveButton';
import { WatchStar } from '../../features/discover/WatchStar';
import { renderApp } from '../../test/render';
import { StockTable } from './StockTable';
import { TableControls } from './TableControls';
import { useTableState } from './useTableState';

function row(symbol: string, over: Partial<OverviewRow> = {}): OverviewRow {
  return {
    symbol,
    name: `${symbol} Corp`,
    exchange: 'US',
    currency: 'USD',
    last_price: 10,
    change_1w_pct: 1,
    sparkline: [1, 2, 3],
    lean: 'neutral',
    country: 'United States',
    sector: null,
    market_cap: 1e9,
    status: 'ok',
    status_reason: null,
    ...over,
  };
}

const ROWS = [
  row('AAA', {
    country: 'Singapore',
    exchange: 'SGX',
    currency: 'SGD',
    change_1w_pct: 5,
    last_price: 30,
  }),
  row('BBB', { country: 'United States', change_1w_pct: -3, last_price: 10 }),
  row('CCC', {
    country: 'Singapore',
    exchange: 'SGX',
    currency: 'SGD',
    change_1w_pct: 1,
    last_price: 20,
  }),
  row('DDD', { country: null, change_1w_pct: null, last_price: 5 }),
];

function Probe() {
  return <output data-testid="loc">{useLocation().search}</output>;
}

function Harness({
  rows = ROWS,
  namespace = '',
  marketCap = false,
  star = false,
}: {
  rows?: OverviewRow[];
  namespace?: string;
  marketCap?: boolean;
  star?: boolean;
}) {
  const table = useTableState({ namespace, columns: marketCap ? 'discover' : 'watchlist' });
  return (
    <>
      <Probe />
      <TableControls rows={rows} state={table} />
      <StockTable
        rows={rows}
        ariaLabel="Test list"
        state={table}
        actionLabel={star ? 'Watchlist' : 'Remove'}
        renderAction={(r) =>
          star ? (
            <WatchStar
              symbol={r.symbol}
              inList={false}
              disabled={false}
              onToggle={() => undefined}
            />
          ) : (
            <RemoveButton symbol={r.symbol} onRemove={() => undefined} />
          )
        }
      />
    </>
  );
}

const order = () =>
  within(screen.getByRole('table', { name: 'Test list' }))
    .getAllByRole('link')
    .map((a) => a.textContent);

describe('StockTable sorting', () => {
  it('cycles ascending, descending, off and sets aria-sort on the active header', async () => {
    const user = userEvent.setup();
    renderApp(<Harness />);
    const header = screen.getByRole('columnheader', { name: /1W change/ });
    expect(header).not.toHaveAttribute('aria-sort');
    expect(order()).toEqual(['AAA', 'BBB', 'CCC', 'DDD']);

    await user.click(within(header).getByRole('button'));
    expect(header).toHaveAttribute('aria-sort', 'ascending');
    expect(order()).toEqual(['BBB', 'CCC', 'AAA', 'DDD']);
    expect(screen.getByTestId('loc')).toHaveTextContent('?sort=change&dir=asc');

    await user.click(within(header).getByRole('button'));
    expect(header).toHaveAttribute('aria-sort', 'descending');
    // The row with no change stays last even when descending.
    expect(order()).toEqual(['AAA', 'CCC', 'BBB', 'DDD']);

    await user.click(within(header).getByRole('button'));
    expect(header).not.toHaveAttribute('aria-sort');
    expect(order()).toEqual(['AAA', 'BBB', 'CCC', 'DDD']);
    expect(screen.getByTestId('loc')).toHaveTextContent('');
  });

  it('restores sort and country from the URL and ignores invalid values', () => {
    renderApp(<Harness />, { route: '/?sort=last&dir=desc&country=Singapore' });
    expect(order()).toEqual(['AAA', 'CCC']);
    expect(screen.getByRole('columnheader', { name: /^Last/ })).toHaveAttribute(
      'aria-sort',
      'descending',
    );
  });

  it('ignores a sort key the columns do not have', () => {
    renderApp(<Harness />, { route: '/?sort=cap&dir=desc' });
    expect(order()).toEqual(['AAA', 'BBB', 'CCC', 'DDD']);
    expect(document.querySelector('[aria-sort]')).toBeNull();
  });

  it('ignores an unknown sort key', () => {
    renderApp(<Harness />, { route: '/?sort=bogus&dir=sideways' });
    expect(order()).toEqual(['AAA', 'BBB', 'CCC', 'DDD']);
    expect(document.querySelector('[aria-sort]')).toBeNull();
  });

  it('keeps a namespaced state under its own keys', async () => {
    const user = userEvent.setup();
    renderApp(<Harness namespace="discover" />, { route: '/?sort=symbol&keep=1' });
    // The plain ?sort belongs to someone else and is not ours to read.
    expect(document.querySelector('[aria-sort]')).toBeNull();
    await user.click(
      within(screen.getByRole('columnheader', { name: /Symbol/ })).getByRole('button'),
    );
    const search = screen.getByTestId('loc').textContent;
    expect(search).toContain('discoverSort=symbol');
    expect(search).toContain('keep=1');
  });
});

describe('StockTable country filter', () => {
  it('shows few countries as buttons with counts and filters the rows', async () => {
    const user = userEvent.setup();
    renderApp(<Harness />);
    const group = screen.getByRole('radiogroup', { name: 'Filter by country' });
    expect(
      within(group)
        .getAllByRole('radio')
        .map((r) => r.textContent),
    ).toEqual(['All', 'Singapore2', 'United States1']);
    expect(within(group).getByRole('radio', { name: 'All' })).toBeChecked();
    await user.click(within(group).getByRole('radio', { name: 'Singapore 2' }));
    expect(order()).toEqual(['AAA', 'CCC']);
    expect(screen.getByTestId('loc')).toHaveTextContent('?country=Singapore');
    expect(within(group).getByRole('radio', { name: 'Singapore 2' })).toBeChecked();
    await user.click(within(group).getByRole('radio', { name: 'All' }));
    expect(screen.getByTestId('loc')).not.toHaveTextContent('country');
  });

  it('uses the namespaced URL key when several views share one URL', async () => {
    const user = userEvent.setup();
    renderApp(<Harness namespace="discover" />);
    await user.click(screen.getByRole('radio', { name: 'Singapore 2' }));
    expect(screen.getByTestId('loc')).toHaveTextContent('?discoverCountry=Singapore');
  });

  it('moves the choice with the arrow keys', async () => {
    const user = userEvent.setup();
    renderApp(<Harness />);
    screen.getByRole('radio', { name: 'All' }).focus();
    await user.keyboard('{ArrowRight}');
    expect(screen.getByRole('radio', { name: 'Singapore 2' })).toHaveFocus();
    expect(order()).toEqual(['AAA', 'CCC']);
    await user.keyboard('{ArrowLeft}{ArrowLeft}');
    expect(screen.getByRole('radio', { name: 'United States 1' })).toHaveFocus();
    expect(order()).toEqual(['BBB']);
  });

  it('shows an empty line with a way back when the filter hides every row', async () => {
    const user = userEvent.setup();
    renderApp(<Harness />, { route: '/?country=Peru' });
    expect(screen.getByText('No stocks from Peru here.')).toBeInTheDocument();
    // The unknown country still shows as the selected choice, with a count of 0.
    expect(screen.getByRole('radio', { name: 'Peru 0' })).toBeChecked();
    await user.click(screen.getByRole('button', { name: 'Show all countries' }));
    expect(order()).toEqual(['AAA', 'BBB', 'CCC', 'DDD']);
  });
});

describe('StockTable columns and actions', () => {
  it('shows country, the exchange tag and a remove action for the watchlist', () => {
    renderApp(<Harness />);
    const table = screen.getByRole('table', { name: 'Test list' });
    expect(within(table).queryByRole('columnheader', { name: /Market cap/ })).toBeNull();
    const aaa = within(table).getByRole('link', { name: 'AAA' }).closest('tr');
    if (!aaa) throw new Error('row missing');
    expect(within(aaa).getByText('Singapore')).toBeInTheDocument();
    expect(within(aaa).getByText('SGX')).toBeInTheDocument();
    expect(
      within(aaa).getByRole('button', { name: 'Remove AAA from watchlist' }),
    ).toBeInTheDocument();
    const ddd = within(table).getByRole('link', { name: 'DDD' }).closest('tr');
    if (!ddd) throw new Error('row missing');
    expect(within(ddd).getAllByRole('cell')[1]).toHaveTextContent('–');
  });

  it('shows market cap and a star toggle on Discover', () => {
    renderApp(<Harness marketCap star />);
    const table = screen.getByRole('table', { name: 'Test list' });
    expect(within(table).getByRole('columnheader', { name: /Market cap/ })).toBeInTheDocument();
    const aaa = within(table).getByRole('link', { name: 'AAA' }).closest('tr');
    if (!aaa) throw new Error('row missing');
    expect(within(aaa).getByText('S$1B')).toBeInTheDocument();
    expect(within(aaa).getByRole('button', { name: 'Add AAA to watchlist' })).toBeInTheDocument();
  });

  it('encodes the symbol in the stock link and renders names as plain text', () => {
    const evil = row('A/B?<x>', { name: '<img src=x onerror=alert(1)>' });
    renderApp(<Harness rows={[evil]} />);
    expect(screen.getByRole('link', { name: 'A/B?<x>' })).toHaveAttribute(
      'href',
      '/stock/A%2FB%3F%3Cx%3E',
    );
    expect(screen.getByText('<img src=x onerror=alert(1)>')).toBeInTheDocument();
    expect(document.querySelector('img')).toBeNull();
  });
});

describe('StockTable on a phone', () => {
  beforeEach(() => {
    vi.stubGlobal(
      'matchMedia',
      (query: string): MediaQueryList =>
        ({
          matches: query.includes('max-width'),
          media: query,
          addEventListener: () => undefined,
          removeEventListener: () => undefined,
          addListener: () => undefined,
          removeListener: () => undefined,
          dispatchEvent: () => false,
          onchange: null,
        }) as MediaQueryList,
    );
  });

  it('shows the country under the name and a Sort by select', async () => {
    const user = userEvent.setup();
    renderApp(<Harness />);
    const list = screen.getByRole('list', { name: 'Test list' });
    expect(within(list).getAllByText('Singapore')).toHaveLength(2);
    await user.click(screen.getByRole('combobox', { name: /Sort by/ }));
    await user.click(screen.getByRole('option', { name: 'Last price' }));
    expect(
      within(screen.getByRole('list', { name: 'Test list' }))
        .getAllByRole('link')
        .map((a) => a.textContent),
    ).toEqual(['DDD', 'BBB', 'CCC', 'AAA']);
    expect(screen.getByTestId('loc')).toHaveTextContent('?sort=last&dir=asc');
    await user.click(screen.getByRole('button', { name: 'Sort descending' }));
    expect(screen.getByTestId('loc')).toHaveTextContent('dir=desc');
  });
});
