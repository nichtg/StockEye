import { screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { renderApp } from '../../test/render';
import { ChartA11yTable } from './ChartA11yTable';
import { visibleCandles } from './visible';

const candles = Array.from({ length: 6 }, (_, i) => ({
  time: `2026-10-0${String(i + 1)}`,
  open: 10,
  high: 12,
  low: 9,
  close: 11,
  volume: 100,
}));

describe('ChartA11yTable', () => {
  it('lists the bars from the start of the chosen range, not the earlier history', () => {
    const from = '2026-10-03';
    renderApp(
      <ChartA11yTable
        candles={visibleCandles(candles, from)}
        visibleFrom={from}
        currency="USD"
        exchange="US"
        announcement=""
      />,
    );
    const rows = within(screen.getByRole('table')).getAllByRole('row');
    expect(rows).toHaveLength(1 + 4);
    expect(within(rows[1]!).getAllByRole('cell')[0]).toHaveTextContent('Oct 3, 2026');
    expect(screen.getByText(/^4 bars since Oct 3, 2026/)).toBeInTheDocument();
  });
});

describe('visibleCandles', () => {
  it('keeps all bars without a start, and compares hourly times as numbers', () => {
    expect(visibleCandles(candles, undefined)).toHaveLength(6);
    const hourly = [100, 200, 300].map((time) => ({ ...candles[0]!, time }));
    expect(visibleCandles(hourly, 200).map((c) => c.time)).toEqual([200, 300]);
  });
});
