import type {
  MacroResponse,
  NewsArticle,
  NewsArticlesPage,
  Profile,
  StockOut,
  TechnicalReport,
} from '../api/types';

export const profileFixture: Profile = {
  description: 'Apple designs, makes and sells smartphones, computers and services worldwide.',
  sector: 'Technology',
  industry: 'Consumer Electronics',
  country: 'United States',
  website: 'https://www.apple.com',
  employees: 164000,
  market_cap: 3.2e12,
  pe_ratio: 31.46,
  dividend_yield: 0.0044,
  week52_low: 164.08,
  week52_high: 237.23,
  avg_volume: 55_300_000,
  currency: 'USD',
  data_status: { state: 'ok' },
};

export function articleFixture(overrides: Partial<NewsArticle> = {}): NewsArticle {
  return {
    published_at: '2026-10-03T15:00:00Z',
    title: 'Apple unveils a new chip',
    url: 'https://example.com/chip',
    source: 'Wire',
    sentiment_label: 'positive',
    sentiment: 0.6,
    similar: [],
    ...overrides,
  };
}

export function articlesPageFixture(
  articles: NewsArticle[],
  nextCursor: string | null = null,
  months: NewsArticlesPage['months'] = null,
): NewsArticlesPage {
  return {
    articles,
    next_cursor: nextCursor,
    since: '2026-04-03T00:00:00Z',
    status: { state: 'ok' },
    months,
  };
}

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
    first_event: '2024-10-03',
    last_event: '2026-02-12',
    correlation: { rho: 0.31, p_value: 0.0123, n: 34, label: 'possible_effect' as const },
    buckets: {},
    difference: null,
  };
  const bucketStats = (
    bucket: 'positive' | 'neutral' | 'negative',
    n: number,
    mean: number | null,
    ci: [number, number] | null,
    label: 'clear_effect' | 'possible_effect' | 'no_clear_effect' | null,
    p: number | null,
  ) => ({
    bucket,
    n,
    mean_car_0_1: mean,
    median_car_0_1: mean,
    n_car_0_5: n,
    mean_car_0_5: null,
    median_car_0_5: null,
    mean_car_pre_5: null,
    n_car_pre_5: n,
    t: null,
    p_value: p,
    label,
    ci_low_0_1: ci?.[0] ?? null,
    ci_high_0_1: ci?.[1] ?? null,
  });
  const primaryStats = {
    ...emptyStats,
    n_used: 37,
    buckets: {
      positive: bucketStats('positive', 21, 0.01, [-0.004, 0.024], 'no_clear_effect', 0.31),
      neutral: bucketStats('neutral', 12, -0.012, [-0.02, -0.004], 'clear_effect', 0.002),
      negative: bucketStats('negative', 4, null, null, null, null),
    },
  };
  return {
    symbol: 'AAPL',
    name: 'Apple Inc.',
    report: {
      top_events_since: '2025-11-12',
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
      events: [],
      headline_findings: [],
      primary_findings: [
        {
          text: 'Across 34 news days studied, more positive news tended to go with better-than-expected moves (that day and the next).',
          based_on_events: 34,
          reliability: null,
          p_value: null,
        },
        {
          text: 'Possible news effect: a pattern this strong would appear by chance about 4 in 100 times.',
          based_on_events: 34,
          reliability: 'possible_effect',
          p_value: 0.0412,
        },
      ],
      earnings_note: null,
      primary_scope: 'excluding_earnings',
      secondary_scope: null,
      secondary_findings: [],
      stats_all: emptyStats,
      stats_ex_earnings: primaryStats,
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
      value_statement:
        'Shows whether news days for this stock moved its price more than the market alone would explain.',
      verdicts: [
        {
          id: 'good_news',
          question: 'Does good news lift the price?',
          answer: 'Not clearly',
          answer_kind: 'none',
          detail:
            'On average +1.0% versus what the market predicted over 2 days, across 21 days with positive news.',
        },
        {
          id: 'bad_news',
          question: 'Does bad news drag it down?',
          answer: 'Not enough data',
          answer_kind: 'insufficient',
          detail: 'Only 4 days with negative news so far; at least 10 are needed.',
        },
        {
          id: 'overall',
          question: 'Do good-news days beat bad-news days?',
          answer: 'Possibly',
          answer_kind: 'possible',
          detail: 'On average, positive-news days did 1.0% better than negative-news days.',
        },
      ],
    },
    ingestion: {
      months_done: 24,
      months_total: 24,
      in_progress: false,
      updated_at: '2026-09-25T10:00:00Z',
    },
    data_status: { prices: okStatus, events: okStatus, news: okStatus, overall: okStatus },
    ...overrides,
  };
}
