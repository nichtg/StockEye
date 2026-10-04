import { moveText, formatPct, formatPoints, formatPrice, formatSigned } from './format';

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
  it('says above, below or in line with the stock’s usual market-linked move', () => {
    expect(moveText(0.021)).toBe('2.1% above its usual market-linked move');
    expect(moveText(-0.014)).toBe('1.4% below its usual market-linked move');
    expect(moveText(0)).toBe('In line with its usual market-linked move');
    expect(moveText(0.00001)).toBe('In line with its usual market-linked move');
  });
});
