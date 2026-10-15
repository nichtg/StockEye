import {
  exchangeDay,
  formatClock,
  formatCompactCurrency,
  formatCount,
  formatPriceRange,
  formatYield,
  formatMonthRange,
  formatMonthYear,
  moveText,
  formatPct,
  formatPoints,
  formatPrice,
  formatSigned,
} from './format';

describe('formatPrice', () => {
  it('shows USD as $ and SGD as S$', () => {
    expect(formatPrice(333.69, 'USD', 'US')).toBe('$333.69');
    expect(formatPrice(77.21, 'SGD', 'SGX')).toBe('S$77.21');
    expect(formatPrice(1234.5, 'SGD', 'SGX')).toBe('S$1,234.50');
  });

  it('keeps the symbol even when the exchange and currency differ', () => {
    expect(formatPrice(5, 'SGD', 'US')).toBe('S$5.00');
    expect(formatPrice(5, 'USD', 'SGX')).toBe('$5.00');
  });

  it('handles missing values and unknown currencies', () => {
    expect(formatPrice(null, 'USD', 'US')).toBe('–');
    expect(formatPrice(5, undefined, 'US')).toBe('$5.00');
    expect(formatPrice(5, 'EUR', 'US')).toBe('€5.00');
  });
});

describe('formatPct and friends', () => {
  it('signs with a true minus and drops the sign on a rounded zero', () => {
    expect(formatPct(0.86, { signed: true, digits: 2 })).toBe('+0.86%');
    expect(formatPct(-2.24, { signed: true })).toBe('−2.2%');
    expect(formatPct(-0.001, { signed: true, digits: 1 })).toBe('0.0%');
    expect(formatPct(63, { digits: 0 })).toBe('63%');
  });

  it('formats signed amounts and points in the exchange locale', () => {
    expect(formatSigned(1234.5, 2, 'US')).toBe('+1,234.50');
    expect(formatSigned(-0.36, 2)).toBe('−0.36');
    expect(formatPoints(12.4)).toBe('+12 pts');
    expect(formatPoints(-3)).toBe('−3 pts');
  });
});

describe('dateFormat and hour12For', () => {
  it('reuses one formatter per locale and options', async () => {
    const { dateFormat } = await import('./format');
    expect(dateFormat('en-US', { month: 'short' })).toBe(dateFormat('en-US', { month: 'short' }));
    expect(dateFormat('en-US', { month: 'short' })).not.toBe(
      dateFormat('en-SG', { month: 'short' }),
    );
  });

  it('uses a 24-hour clock only for Singapore', async () => {
    const { hour12For } = await import('./exchange');
    expect(hour12For('US')).toBe(true);
    expect(hour12For('SGX')).toBe(false);
  });
});

describe('moveText', () => {
  it('says above, below or in line with the stock’s usual market‑linked move', () => {
    expect(moveText(0.021)).toBe('2.1% above its usual market‑linked move');
    expect(moveText(-0.014)).toBe('1.4% below its usual market‑linked move');
    expect(moveText(0)).toBe('In line with its usual market‑linked move');
    expect(moveText(0.00001)).toBe('In line with its usual market‑linked move');
  });
});

describe('month and period formatting', () => {
  it('reads the month from the date as written, with no time zone shift', () => {
    expect(formatMonthYear('2024-10-01')).toBe('Oct 2024');
    expect(formatMonthYear('2026-01-31')).toBe('Jan 2026');
    expect(formatMonthYear('nonsense')).toBeNull();
  });

  it('gives a range, a single month, or nothing', () => {
    expect(formatMonthRange('2024-10-03', '2026-10-01')).toBe('Oct 2024 to Oct 2026');
    expect(formatMonthRange('2026-10-02', '2026-10-28')).toBe('Oct 2026');
    expect(formatMonthRange(null, '2026-10-28')).toBeNull();
    expect(formatMonthRange('2026-10-02', null)).toBeNull();
  });
});

describe('company fact formats', () => {
  it('compacts money to T, B, M and K in the stock currency', () => {
    expect(formatCompactCurrency(3.2e12, 'USD', 'US')).toBe('$3.2T');
    expect(formatCompactCurrency(208.9e9, 'SGD', 'SGX')).toBe('S$208.9B');
    expect(formatCompactCurrency(850e6, 'USD', 'US')).toBe('$850M');
    expect(formatCompactCurrency(12_500, 'USD', 'US')).toBe('$12.5K');
    expect(formatCompactCurrency(null, 'USD', 'US')).toBe('–');
  });

  it('shows a dividend yield fraction as a percent with 2 decimals', () => {
    expect(formatYield(0.0044)).toBe('0.44%');
    expect(formatYield(0.05)).toBe('5.00%');
  });

  it('joins the 52-week range, or gives null when an end is missing', () => {
    expect(formatPriceRange(164.08, 237.23, 'USD', 'US')).toBe('$164.08 – $237.23');
    expect(formatPriceRange(null, 237.23, 'USD', 'US')).toBeNull();
    expect(formatPriceRange(41.1, 44, 'SGD', 'SGX')).toBe('S$41.10 – S$44.00');
  });

  it('groups whole numbers', () => {
    expect(formatCount(164000, 'US')).toBe('164,000');
  });

  it('reads the day and clock in the exchange zone, not the browser zone', () => {
    // 02:30 UTC on Oct 4 is still Oct 3 in New York and already Oct 4 in Singapore.
    expect(exchangeDay('2026-10-04T02:30:00Z', 'US')).toBe('2026-10-03');
    expect(exchangeDay('2026-10-04T02:30:00Z', 'SGX')).toBe('2026-10-04');
    expect(formatClock('2026-10-03T20:05:00Z', 'US')).toBe('4:05 PM EDT');
  });
});
