import type { Candle, ChartMarker } from '../../api/types';
import { tokens } from '../../theme/tokens';
import {
  DEFAULT_INDICATORS,
  INDICATORS_STORAGE_KEY,
  loadIndicatorSelection,
  parseIndicatorSelection,
  saveIndicatorSelection,
} from './indicators';
import {
  emptyMarkerText,
  loadMarkerOverrides,
  markerCounts,
  markerVisible,
  parseMarkerOverrides,
  saveMarkerOverrides,
} from './markers';
import { candleData, lineData, markerData, volumeData, withAlpha } from './model';
import { chartSummary, eventText, tooltipContent } from './tooltip';

const candles: Candle[] = [
  { time: '2026-09-30', open: 10, high: 11, low: 9, close: 10.5, volume: 1_500_000 },
  { time: '2026-10-01', open: 10.5, high: 12, low: 10, close: 11.55, volume: 2_000_000 },
];
const ctx = { currency: 'USD', exchange: 'US' } as const;

describe('series mapping', () => {
  it('maps candles, volume and lines without changing values', () => {
    expect(candleData(candles)[1]).toEqual({
      time: '2026-10-01',
      open: 10.5,
      high: 12,
      low: 10,
      close: 11.55,
    });
    expect(volumeData(candles)[0]).toEqual({ time: '2026-09-30', value: 1_500_000 });
    expect(lineData([{ time: 1_700_000_000, value: 3 }])).toEqual([
      { time: 1_700_000_000, value: 3 },
    ]);
    expect(lineData(undefined)).toEqual([]);
  });

  it('adds alpha as a hex byte', () => {
    expect(withAlpha('#8C8C8C', 0.35)).toBe('#8C8C8C59');
    expect(withAlpha('#000000', 1)).toBe('#000000ff');
  });
});

describe('marker mapping', () => {
  const markers: ChartMarker[] = [
    { time: '2026-10-01', kind: 'pattern', label: 'Hammer', bias: 'bullish', pattern: 'hammer' },
    { time: '2026-09-30', kind: 'earnings', label: 'Earnings: EPS 1.52 vs est 1.43' },
    { time: '2026-09-30', kind: 'dividend', label: 'Dividend 0.24 USD' },
    { time: '2026-10-01', kind: 'split', label: 'Split 4:1' },
    {
      time: '2026-10-01',
      kind: 'pattern',
      label: 'Shooting star',
      bias: 'bearish',
      pattern: 'shooting_star',
    },
    { time: '2026-10-01', kind: 'pattern', label: 'Doji', bias: 'neutral', pattern: 'doji' },
    { time: '2026-10-01', kind: 'news', label: 'DBS beats', car_0_1: 0.021 },
  ];
  const mapped = markerData(markers, tokens.light);

  it('sorts by time and uses the specified glyphs and shapes', () => {
    expect(mapped.map((m) => m.time)).toEqual([...mapped.map((m) => m.time)].sort());
    const find = (shape: string, text?: string) =>
      mapped.find((m) => m.shape === shape && (text === undefined || m.text === text));
    expect(find('circle', 'E')).toMatchObject({ position: 'aboveBar', color: tokens.light.ink });
    expect(find('circle', 'D')).toMatchObject({ position: 'belowBar', color: tokens.light.ink2 });
    expect(find('square', 'S')).toBeDefined();
    expect(find('arrowUp')).toMatchObject({ color: tokens.light.up });
    expect(find('arrowDown')).toMatchObject({ color: tokens.light.down });
    // Neutral (doji) patterns are never drawn. A news beat is an up-toned dot.
    expect(mapped.some((m) => m.color === tokens.light.ink3)).toBe(false);
    expect(mapped).toHaveLength(6);
    expect(mapped.some((m) => m.shape === 'circle' && m.color === tokens.light.up && !m.text)).toBe(
      true,
    );
  });
});

describe('news marker size', () => {
  const news = (car: number | null): ChartMarker => ({
    time: '2026-10-01',
    kind: 'news',
    label: 'x',
    car_0_1: car,
  });
  const sizeOf = (car: number | null) => markerData([news(car)], tokens.light)[0]?.size;

  it('steps by the size of the move, whichever way it went', () => {
    expect(sizeOf(0.004)).toBe(0.6);
    expect(sizeOf(-0.004)).toBe(0.6);
    expect(sizeOf(0.01)).toBe(1);
    expect(sizeOf(-0.03)).toBe(1);
    expect(sizeOf(0.031)).toBe(1.6);
    expect(sizeOf(-0.08)).toBe(1.6);
    expect(sizeOf(null)).toBe(0.6);
  });

  it('colours by direction', () => {
    expect(markerData([news(0.02)], tokens.light)[0]?.color).toBe(tokens.light.up);
    expect(markerData([news(-0.02)], tokens.light)[0]?.color).toBe(tokens.light.down);
  });
});

describe('marker counts', () => {
  it('counts the markers drawn for each kind, leaving out neutral patterns', () => {
    const counts = markerCounts([
      { time: 'a', kind: 'news', label: 'x', car_0_1: 0.01 },
      { time: 'b', kind: 'news', label: 'y', car_0_1: -0.01 },
      { time: 'a', kind: 'pattern', label: 'Doji', bias: 'neutral', pattern: 'doji' },
      { time: 'b', kind: 'pattern', label: 'Hammer', bias: 'bullish', pattern: 'hammer' },
      { time: 'a', kind: 'dividend', label: 'Dividend' },
    ]);
    expect(counts).toEqual({ earnings: 0, dividend: 1, split: 0, pattern: 1, news: 2 });
  });

  it('words the empty case per kind', () => {
    expect(emptyMarkerText('news')).toBe('No news events in this range');
    expect(emptyMarkerText('dividend')).toBe('No dividends in this range');
  });
});

describe('marker visibility', () => {
  it('hides kinds that are switched off', () => {
    const all: ChartMarker[] = [
      { time: '2026-09-30', kind: 'earnings', label: 'Earnings' },
      { time: '2026-10-01', kind: 'pattern', label: 'Hammer', bias: 'bullish', pattern: 'hammer' },
    ];
    expect(markerData(all, tokens.light, (k) => k !== 'pattern')).toHaveLength(1);
  });

  it('shows patterns by default only on the short ranges, and overrides win', () => {
    expect(markerVisible('pattern', '1W', {})).toBe(true);
    expect(markerVisible('pattern', '1M', {})).toBe(true);
    expect(markerVisible('pattern', '6M', {})).toBe(false);
    expect(markerVisible('earnings', '2Y', {})).toBe(true);
    expect(markerVisible('pattern', '6M', { pattern: true })).toBe(true);
    expect(markerVisible('news', '1W', { news: false })).toBe(false);
  });

  it('round-trips overrides and ignores junk', () => {
    saveMarkerOverrides({ pattern: true, news: false });
    expect(loadMarkerOverrides()).toEqual({ pattern: true, news: false });
    expect(parseMarkerOverrides('{"pattern":1,"bogus":true,"split":false}')).toEqual({
      split: false,
    });
    expect(parseMarkerOverrides('[1]')).toEqual({});
    expect(parseMarkerOverrides('nope')).toEqual({});
  });
});

describe('tooltip text', () => {
  it('describes the bar, its change and OHLC in the stock currency', () => {
    const tip = tooltipContent(candles[1]!, candles[0], [], ctx);
    expect(tip.close).toBe('$11.55');
    expect(tip.change).toBe('+1.05');
    expect(tip.changePct).toBeCloseTo(10, 5);
    expect(tip.volume).toBe('2M');
  });

  it('writes events in plain language', () => {
    expect(
      eventText({ time: 'x', kind: 'earnings', label: 'Earnings: EPS 1.52 vs est 1.43' }),
    ).toBe('Earnings: EPS 1.52 vs 1.43 estimate');
    expect(eventText({ time: 'x', kind: 'dividend', label: 'Dividend 0.24 USD' })).toBe(
      'Dividend 0.24 USD',
    );
    expect(
      eventText(
        {
          time: 'x',
          kind: 'pattern',
          label: 'Bullish engulfing',
          pattern: 'bullish_engulfing',
          bias: 'bullish',
        },
        { bullish_engulfing: 'Seen 12 times in the past 3 years.' },
      ),
    ).toBe('Bullish engulfing. Seen 12 times in the past 3 years.');
    expect(
      eventText({
        time: 'x',
        kind: 'pattern',
        label: 'Hammer',
        pattern: 'hammer',
        bias: 'bullish',
      }),
    ).toBe('Hammer');
    expect(eventText({ time: 'x', kind: 'news', label: 'DBS beats', car_0_1: 0.021 })).toBe(
      'News: “DBS beats” (2.1% above its usual market-linked move over 2 days)',
    );
    expect(eventText({ time: 'x', kind: 'news', label: 'Probe', car_0_1: -0.014 })).toContain(
      '1.4% below its usual market-linked move',
    );
  });

  it('attaches only the events on that bar', () => {
    const tip = tooltipContent(
      candles[1]!,
      candles[0],
      [
        { time: '2026-10-01', kind: 'dividend', label: 'Dividend 0.24 USD' },
        { time: '2026-09-30', kind: 'split', label: 'Split 4:1' },
      ],
      ctx,
    );
    expect(tip.events).toEqual(['Dividend 0.24 USD']);
  });

  it('summarises the chart for screen readers', () => {
    expect(chartSummary('AAPL', '6M', candles, ctx)).toBe(
      'AAPL price chart for 6M. Last close $11.55, up 15.5% over the period.',
    );
    expect(chartSummary('AAPL', '6M', [], ctx)).toContain('no trading data');
  });
});

describe('indicator selection persistence', () => {
  it('defaults to SMA 50 and VWAP', () => {
    expect([...loadIndicatorSelection()].sort()).toEqual([...DEFAULT_INDICATORS].sort());
  });

  it('round-trips through localStorage', () => {
    saveIndicatorSelection(['rsi', 'macd', 'ema9']);
    expect(loadIndicatorSelection()).toEqual(['ema9', 'rsi', 'macd']);
  });

  it('ignores junk and unknown ids', () => {
    localStorage.setItem(INDICATORS_STORAGE_KEY, '{not json');
    expect(loadIndicatorSelection()).toEqual(DEFAULT_INDICATORS);
    expect(parseIndicatorSelection('["sma20","bogus",5]')).toEqual(['sma20']);
    expect(parseIndicatorSelection('{"a":1}')).toEqual(DEFAULT_INDICATORS);
  });

  it('survives storage that throws', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('blocked');
    });
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('blocked');
    });
    expect(loadIndicatorSelection()).toEqual(DEFAULT_INDICATORS);
    expect(() => {
      saveIndicatorSelection(['rsi']);
    }).not.toThrow();
  });
});
