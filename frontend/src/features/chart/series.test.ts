import { renderHook } from '@testing-library/react';
import type { IChartApi } from 'lightweight-charts';
import type { ChartData, SeriesPoint } from '../../api/types';
import { tokens } from '../../theme/tokens';
import { ALL_INDICATORS, INDICATORS, type IndicatorId } from './indicators';
import { SUB_PANE_HEIGHT, buildSeriesSpecs, withAlpha } from './model';
import { SeriesSet, useChartSeries, type Live } from './useChartSeries';

const p = tokens.light;
const points = (...values: number[]): SeriesPoint[] =>
  values.map((value, i) => ({ time: `2026-10-0${i + 1}`, value }));

const data: ChartData = {
  symbol: 'AAPL',
  range: '6M',
  interval: '1d',
  candles: [1, 2, 3].map((d) => ({
    time: `2026-10-0${d}`,
    open: 10,
    high: 12,
    low: 9,
    close: 11,
    volume: 100,
  })),
  indicators: {
    vwap: points(10, 11, 12),
    sma20: points(10, 11, 12),
    sma50: points(10, 11, 12),
    ema9: points(10, 11, 12),
    ema21: points(10, 11, 12),
    bollinger_upper: points(13, 14, 15),
    bollinger_middle: points(11, 12, 13),
    bollinger_lower: points(9, 10, 11),
    rsi: points(40, 55, 70),
    macd: points(0.1, 0.2, 0.3),
    macd_signal: points(0.1, 0.1, 0.2),
    macd_histogram: points(0.5, -0.4, 0),
  },
  markers: [],
  data_status: { overall: { state: 'ok' } } as ChartData['data_status'],
};

const keys = (selection: IndicatorId[]) =>
  buildSeriesSpecs(data, selection, p).map((s) => `${s.key}@${String(s.pane)}`);

describe('buildSeriesSpecs', () => {
  it('always draws candles and volume on the price pane', () => {
    expect(keys([])).toEqual(['candles@0', 'volume@0']);
  });

  it('puts overlays on the price pane and RSI and MACD in their own panes, in order', () => {
    expect(keys(['sma50', 'vwap', 'macd', 'rsi'])).toEqual([
      'candles@0',
      'volume@0',
      'vwap@0',
      'sma50@0',
      'rsi@1',
      'macd_histogram@2',
      'macd@2',
      'macd_signal@2',
    ]);
    // MACD alone takes the first sub-pane.
    expect(keys(['macd']).at(-1)).toBe('macd_signal@1');
  });

  it('styles every indicator from its definition: dash and weight, never hue', () => {
    const specs = buildSeriesSpecs(data, ['vwap', 'sma20', 'ema9'], p);
    for (const id of ['vwap', 'sma20', 'ema9'] as const) {
      const def = INDICATORS.find((i) => i.id === id);
      expect(specs.find((s) => s.key === id)?.options).toMatchObject({
        color: p[def?.tone ?? 'ink'],
        lineWidth: def?.width,
        lineStyle: def?.lineStyle,
      });
    }
  });

  it('shades the Bollinger bands at 6% and leaves the middle line out', () => {
    const specs = buildSeriesSpecs(data, ['bollinger'], p);
    expect(specs.map((s) => s.key)).toEqual([
      'candles',
      'volume',
      'bollinger_upper',
      'bollinger_lower',
    ]);
    const upper = specs.find((s) => s.key === 'bollinger_upper');
    expect(upper?.kind === 'Line' && upper.band?.color).toBe(withAlpha(p.ink, 0.06));
    expect(upper?.kind === 'Line' && upper.band?.lower).toHaveLength(3);
  });

  it('marks RSI 30 and 70 and colours the MACD histogram by sign at 60% opacity', () => {
    const specs = buildSeriesSpecs(data, ['rsi', 'macd'], p);
    const rsi = specs.find((s) => s.key === 'rsi');
    expect(rsi?.kind === 'Line' && rsi.levels).toEqual({ prices: [30, 70], color: p.ink3 });
    const hist = specs.find((s) => s.key === 'macd_histogram');
    expect(hist?.data.map((d) => 'color' in d && d.color)).toEqual([
      withAlpha(p.up, 0.6),
      withAlpha(p.down, 0.6),
      withAlpha(p.up, 0.6),
    ]);
  });

  it('tolerates a missing indicator series', () => {
    const bare = { ...data, indicators: {} };
    expect(buildSeriesSpecs(bare, ['sma20'], p).find((s) => s.key === 'sma20')?.data).toEqual([]);
  });

  it('asks the API for every indicator at once', () => {
    expect(ALL_INDICATORS.split(',').sort()).toEqual(INDICATORS.map((i) => i.id).sort());
  });

  it('gives no two price-pane indicators the same dash, weight and tone', () => {
    const looks = INDICATORS.filter((i) => i.pane === 'overlay').map(
      (i) => `${String(i.lineStyle)}|${String(i.width)}|${i.tone}`,
    );
    expect(new Set(looks).size).toBe(looks.length);
  });

  it('gives RSI breathing room above and below its 0-100 scale', () => {
    const rsi = buildSeriesSpecs(data, ['rsi'], p).find((s) => s.key === 'rsi');
    expect(rsi?.scaleMargins).toEqual({ top: 0.1, bottom: 0.1 });
  });
});

/** Just enough of a chart to watch what the diff does to it. */
function fakeChart() {
  const added: string[] = [];
  const removed: unknown[] = [];
  const series: unknown[] = [];
  const stretch = [1, 2, 3].map(() => vi.fn<(factor: number) => void>());
  const timeScale = {
    fitContent: vi.fn(),
    getVisibleLogicalRange: vi.fn(() => ({ from: 10, to: 40 })),
    setVisibleLogicalRange: vi.fn(),
  };
  const chart = {
    addSeries: vi.fn((_definition: unknown, _options: unknown, pane: number) => {
      const s = {
        pane,
        applyOptions: vi.fn(),
        setData: vi.fn(),
        priceScale: () => ({ applyOptions: vi.fn() }),
        getPane: () => ({ paneIndex: () => s.pane }),
        moveToPane: vi.fn((i: number) => {
          s.pane = i;
        }),
        createPriceLine: vi.fn(() => ({})),
        removePriceLine: vi.fn(),
        attachPrimitive: vi.fn(),
      };
      series.push(s);
      added.push(String(series.length));
      return s;
    }),
    removeSeries: vi.fn((s: unknown) => removed.push(s)),
    timeScale: () => timeScale,
    panes: () => stretch.map((s) => ({ setStretchFactor: s })),
  };
  return { chart: chart as unknown as IChartApi, raw: chart, timeScale, series, removed, stretch };
}

/** How many times a (fake) series had its data written. */
const writes = (api: Live['api'] | undefined) =>
  (api as unknown as { setData: { mock: { calls: unknown[] } } }).setData.mock.calls.length;

describe('SeriesSet.sync', () => {
  it('adds and removes only the series whose selection changed', () => {
    const set = new SeriesSet();
    const live = set.live;
    const { chart, raw, removed } = fakeChart();
    set.sync(chart, buildSeriesSpecs(data, ['sma20'], p));
    expect(raw.addSeries).toHaveBeenCalledTimes(3);
    const candles = live.get('candles')?.api;

    // Switching RSI on adds one series and touches nothing else.
    set.sync(chart, buildSeriesSpecs(data, ['sma20', 'rsi'], p));
    expect(raw.addSeries).toHaveBeenCalledTimes(4);
    expect(removed).toHaveLength(0);
    expect(live.get('candles')?.api).toBe(candles);
    expect(writes(candles)).toBe(1);

    // Switching SMA off removes only SMA.
    set.sync(chart, buildSeriesSpecs(data, ['rsi'], p));
    expect(removed).toHaveLength(1);
    expect([...live.keys()]).toEqual(['candles', 'volume', 'rsi']);
  });

  it('rewrites data when the theme changes, and moves a pane when one above it disappears', () => {
    const set = new SeriesSet();
    const live = set.live;
    const { chart } = fakeChart();
    set.sync(chart, buildSeriesSpecs(data, ['rsi', 'macd'], p));
    const macd = live.get('macd')?.api;
    expect(macd?.getPane().paneIndex()).toBe(2);

    set.sync(chart, buildSeriesSpecs(data, ['macd'], tokens.dark));
    expect(macd?.getPane().paneIndex()).toBe(1);
    expect(writes(macd)).toBe(2);
  });
});

describe('useChartSeries', () => {
  it('splits the panes 420:100:100 with stretch factors', () => {
    const { chart, stretch } = fakeChart();
    renderHook(() => useChartSeries(chart, buildSeriesSpecs(data, ['rsi', 'macd'], p), 420, 'k'));
    expect(stretch.map((s) => s.mock.calls.at(-1)?.[0])).toEqual([
      420,
      SUB_PANE_HEIGHT,
      SUB_PANE_HEIGHT,
    ]);
  });

  it('fits the chart for a new symbol or range, and keeps the zoom when only indicators change', () => {
    const { chart, timeScale } = fakeChart();
    const { rerender } = renderHook(
      ({ selection, fitKey }) =>
        useChartSeries(chart, buildSeriesSpecs(data, selection, p), 420, fitKey),
      { initialProps: { selection: [] as IndicatorId[], fitKey: 'AAPL|6M' } },
    );
    expect(timeScale.fitContent).toHaveBeenCalledTimes(1);

    rerender({ selection: ['rsi'], fitKey: 'AAPL|6M' });
    expect(timeScale.fitContent).toHaveBeenCalledTimes(1);
    expect(timeScale.setVisibleLogicalRange).toHaveBeenLastCalledWith({ from: 10, to: 40 });

    rerender({ selection: ['rsi'], fitKey: 'AAPL|1W' });
    expect(timeScale.fitContent).toHaveBeenCalledTimes(2);
  });
});
