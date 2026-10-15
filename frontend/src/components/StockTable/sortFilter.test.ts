import type { OverviewRow } from '../../api/types';
import { countryOptions, filterRows, nextSort, sortRows } from './sortFilter';

function row(symbol: string, over: Partial<OverviewRow> = {}): OverviewRow {
  return {
    symbol,
    name: null,
    exchange: 'US',
    currency: 'USD',
    last_price: 10,
    change_1w_pct: 1,
    sparkline: [],
    lean: 'neutral',
    country: 'United States',
    sector: null,
    market_cap: 1e9,
    status: 'ok',
    status_reason: null,
    ...over,
  };
}

const symbols = (rows: OverviewRow[]) => rows.map((r) => r.symbol);

describe('sortRows', () => {
  it('sorts numbers ascending and descending', () => {
    const rows = [row('B', { change_1w_pct: 5 }), row('A', { change_1w_pct: -2 })];
    expect(symbols(sortRows(rows, 'change', 'asc'))).toEqual(['A', 'B']);
    expect(symbols(sortRows(rows, 'change', 'desc'))).toEqual(['B', 'A']);
  });

  it('puts missing values last in both directions', () => {
    const rows = [
      row('N', { last_price: null }),
      row('A', { last_price: 3 }),
      row('B', { last_price: 9 }),
    ];
    expect(symbols(sortRows(rows, 'last', 'asc'))).toEqual(['A', 'B', 'N']);
    expect(symbols(sortRows(rows, 'last', 'desc'))).toEqual(['B', 'A', 'N']);
  });

  it('orders outlook bearish, neutral, bullish, with none last', () => {
    const rows = [
      row('U', { lean: 'bullish' }),
      row('X', { lean: null }),
      row('D', { lean: 'bearish' }),
      row('M', { lean: 'neutral' }),
    ];
    expect(symbols(sortRows(rows, 'outlook', 'asc'))).toEqual(['D', 'M', 'U', 'X']);
    expect(symbols(sortRows(rows, 'outlook', 'desc'))).toEqual(['U', 'M', 'D', 'X']);
  });

  it('sorts countries by locale, ignoring case and accents, with none last', () => {
    const rows = [
      row('1', { country: 'singapore' }),
      row('2', { country: null }),
      row('3', { country: 'Åland' }),
      row('4', { country: 'United States' }),
    ];
    expect(symbols(sortRows(rows, 'country', 'asc'))).toEqual(['3', '1', '4', '2']);
    expect(symbols(sortRows(rows, 'country', 'desc'))).toEqual(['4', '1', '3', '2']);
  });

  it('keeps the original order for ties and does not mutate the input', () => {
    const rows = [row('B'), row('A'), row('C')];
    expect(symbols(sortRows(rows, 'last', 'desc'))).toEqual(['B', 'A', 'C']);
    expect(symbols(sortRows(rows, null, 'asc'))).toEqual(['B', 'A', 'C']);
    expect(symbols(rows)).toEqual(['B', 'A', 'C']);
  });
});

describe('filterRows and countryOptions', () => {
  const rows = [
    row('A', { country: 'Singapore' }),
    row('B', { country: 'United States' }),
    row('C', { country: 'Singapore' }),
    row('D', { country: null }),
  ];

  it('keeps one country, or everything for null', () => {
    expect(symbols(filterRows(rows, 'Singapore'))).toEqual(['A', 'C']);
    expect(symbols(filterRows(rows, null))).toEqual(['A', 'B', 'C', 'D']);
    expect(filterRows(rows, 'Peru')).toEqual([]);
  });

  it('lists countries alphabetically with counts, skipping unknown ones', () => {
    expect(countryOptions(rows)).toEqual([
      { country: 'Singapore', count: 2 },
      { country: 'United States', count: 1 },
    ]);
  });
});

describe('nextSort', () => {
  it('cycles asc, desc, off, and restarts on a new column', () => {
    const a = nextSort(null, 'last');
    expect(a).toEqual({ key: 'last', dir: 'asc' });
    const b = nextSort(a, 'last');
    expect(b).toEqual({ key: 'last', dir: 'desc' });
    expect(nextSort(b, 'last')).toBeNull();
    expect(nextSort(b, 'symbol')).toEqual({ key: 'symbol', dir: 'asc' });
  });
});
