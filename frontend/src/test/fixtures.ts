import type { MacroResponse, StockOut, TechnicalReport } from '../api/types';

export const stockFixture: StockOut = {
  symbol: 'AAPL',
  name: 'Apple Inc.',
  exchange: 'US',
  currency: 'USD',
  price: 333.69,
  previous_close: 330.8,
  change_pct: 0.87,
  as_of: '2026-10-03T09:40:00Z',
  data_status: { state: 'ok' },
};

const okStatus = { state: 'ok' } as const;

export const technicalFixture: TechnicalReport = {
  symbol: 'AAPL',
  outlook: {
    lean: 'bullish',
    score: 0.42,
    signals: [
      {
        key: 'rsi14',
        label: 'RSI (14)',
        direction: 0,
        weight: 1,
        detail: 'RSI is 54.7, between 30 and 70.',
      },
      {
        key: 'ema_cross',
        label: 'EMA 9/21',
        direction: 1,
        weight: 1,
        detail: '9-day EMA is above the 21-day EMA.',
      },
      {
        key: 'patterns',
        label: 'Candlestick patterns',
        direction: 0,
        weight: 0,
        detail: 'No directional signal.',
      },
    ],
    expected_range: { low: 317.96, high: 349.42 },
    expected_range_coverage: 0.9,
    last_close: 333.69,
    as_of: '2026-10-02',
  },
  recent_patterns: [
    {
      key: 'bullish_engulfing',
      label: 'Bullish engulfing',
      bias: 'bullish',
      date: '2026-10-01',
      stats: {
        n: 12,
        up_count: 9,
        hit_rate: 0.75,
        base_rate: 0.55,
        edge: 0.2,
        base_down_rate: 0.45,
        base_n: 500,
        sufficient: true,
        label: 'backend sentence n=12 p=0.04',
        bias: 'bullish',
      },
    },
    {
      key: 'hammer',
      label: 'Hammer',
      bias: 'bullish',
      date: '2026-09-30',
      stats: {
        n: 4,
        up_count: 3,
        hit_rate: 0.75,
        base_rate: 0.55,
        edge: 0.2,
        base_down_rate: 0.45,
        base_n: 500,
        sufficient: false,
        label: 'too few',
        bias: 'bullish',
      },
    },
  ],
  data_status: { prices: okStatus, overall: okStatus },
};

export function macroFixture(overrides: Partial<MacroResponse> = {}): MacroResponse {
  const emptyStats = {
    exclude_near_earnings: true,
    min_n: 10,
    n_used: 34,
    correlation: { rho: 0.31, p_value: 0.0123, n: 34, label: 'weak_evidence' as const },
    buckets: {},
    difference: null,
  };
  return {
    symbol: 'AAPL',
    name: 'Apple Inc.',
    report: {
      top_events: [
        {
          date: '2026-02-12',
          sentiment: 0.4,
          article_count: 3,
          car_0_1: 0.033,
          car_0_5: null,
          near_earnings: false,
          headlines: [
            {
              title: 'Apple to Bring TV+ to Android',
              url: 'https://example.com/a',
              source: 'Bloomberg',
            },
          ],
        },
      ],
      headline_findings: [],
      primary_findings: [
        {
          text: 'More positive news tended to go with better-than-expected moves.',
          based_on_events: 34,
          reliability: null,
          p_value: null,
        },
        {
          text: 'Weak evidence: a pattern this strong would appear by chance about 4 in 100 times.',
          based_on_events: 34,
          reliability: 'weak_evidence',
          p_value: 0.0412,
        },
      ],
      primary_scope: 'excluding_earnings',
      secondary_scope: null,
      secondary_findings: [],
      stats_all: emptyStats,
      stats_ex_earnings: emptyStats,
      regime: {
        recent_mean: 0.2,
        baseline_mean: 0.05,
        z: 1.8,
        recent_articles: 30,
        label: 'more_positive_than_usual',
      },
      timeline: [
        { week_end: '2026-09-18', mean_score: 0.2, article_count: 6 },
        { week_end: '2026-09-25', mean_score: -0.1, article_count: 3 },
      ],
      events_total: 36,
      events_insufficient: 2,
    },
    ingestion: { months_done: 24, months_total: 24, in_progress: false },
    data_status: { prices: okStatus, events: okStatus, news: okStatus, overall: okStatus },
    ...overrides,
  };
}
