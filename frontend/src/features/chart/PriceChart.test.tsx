import { fireEvent, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { ChartData } from '../../api/types';
import { renderApp } from '../../test/render';
import type * as NavigationModule from './navigation';

const nav = vi.hoisted(() => ({
  zoomIn: vi.fn(),
  zoomOut: vi.fn(),
  panLeft: vi.fn(),
  panRight: vi.fn(),
  reset: vi.fn(),
}));
const cursorKey = vi.hoisted(() => vi.fn());

// The chart itself needs a canvas; what is under test is how PriceChart routes keys.
vi.mock('./useLightweightChart', () => ({
  useLightweightChart: () => ({
    timeScale: () => ({
      getVisibleLogicalRange: () => ({ from: 0, to: 2 }),
      subscribeVisibleLogicalRangeChange: vi.fn(),
      unsubscribeVisibleLogicalRangeChange: vi.fn(),
    }),
  }),
}));
vi.mock('./useChartSeries', () => ({
  useChartSeries: () => null,
  useSeriesMarkers: () => undefined,
}));
vi.mock('./useChartCursor', () => ({
  useChartCursor: () => ({
    tip: null,
    announce: '',
    clear: vi.fn(),
    onKeyDown: cursorKey,
    onBlur: vi.fn(),
  }),
}));
vi.mock('./navigation', async (importOriginal) => ({
  ...(await importOriginal<typeof NavigationModule>()),
  createNavigator: () => nav,
}));

const { PriceChart } = await import('./PriceChart');

const data = {
  symbol: 'AAPL',
  range: '6M',
  interval: '1d',
  visible_from: '2026-10-02',
  candles: [1, 2, 3].map((d) => ({
    time: `2026-10-0${String(d)}`,
    open: 10,
    high: 12,
    low: 9,
    close: 11,
    volume: 100,
  })),
  indicators: {},
  markers: [],
  data_status: {},
} as unknown as ChartData;

function setup() {
  renderApp(
    <PriceChart
      data={data}
      selection={[]}
      currency="USD"
      exchange="US"
      baseHeight={300}
      sentences={{}}
      shownMarkers={[]}
    />,
  );
  return screen.getByRole('group', { name: /Price chart/ });
}

describe('PriceChart keyboard', () => {
  it('sends Shift+arrow to navigation and keeps it from the bar cursor', () => {
    const group = setup();
    fireEvent.keyDown(group, { key: 'ArrowLeft', shiftKey: true });
    expect(nav.panLeft).toHaveBeenCalledTimes(1);
    expect(cursorKey).not.toHaveBeenCalled();
  });

  it('sends a plain arrow to the bar cursor, not to navigation', () => {
    const group = setup();
    fireEvent.keyDown(group, { key: 'ArrowLeft' });
    expect(cursorKey).toHaveBeenCalledTimes(1);
    expect(nav.panLeft).not.toHaveBeenCalled();
  });

  it('zooms on plus', () => {
    const group = setup();
    fireEvent.keyDown(group, { key: '+' });
    expect(nav.zoomIn).toHaveBeenCalledTimes(1);
  });
});
