import { describe, expect, it } from 'vitest';
import type { Candle } from '../../api/types';
import { onOrAfter, startIndex } from './visible';

const bar = (time: string): Candle => ({ time, open: 1, high: 1, low: 1, close: 1, volume: 1 });
const bars = ['2026-01-02', '2026-01-05', '2026-01-06'].map(bar);

describe('startIndex', () => {
  it('finds the first bar on or after the range start', () => {
    expect(startIndex(bars, '2026-01-03')).toBe(1);
    expect(startIndex(bars, '2026-01-05')).toBe(1);
  });

  it('starts at the oldest bar when the range starts before the data', () => {
    expect(startIndex(bars, '2025-06-01')).toBe(0);
  });

  it('starts at the latest bar when the range starts after the data', () => {
    expect(startIndex(bars, '2026-02-01')).toBe(2);
    expect(startIndex([], '2026-02-01')).toBe(0);
  });
});

describe('onOrAfter', () => {
  it('compares daily dates and hourly seconds', () => {
    expect(onOrAfter(200, 100)).toBe(true);
    expect(onOrAfter('2026-01-01', '2026-02-01')).toBe(false);
  });
});
