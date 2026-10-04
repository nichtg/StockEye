/**
 * Plain-English definitions for every piece of jargon in the app. `TermId` is a closed union, so
 * `<Term id="rsii">` is a compile error, and `GLOSSARY` must define every id (and nothing else).
 */
export const TERM_IDS = [
  'candlestick',
  'volume',
  'doji',
  'hammer',
  'hanging_man',
  'inverted_hammer',
  'shooting_star',
  'bullish_engulfing',
  'bearish_engulfing',
  'bullish_harami',
  'bearish_harami',
  'piercing_line',
  'dark_cloud_cover',
  'morning_star',
  'evening_star',
  'three_white_soldiers',
  'three_black_crows',
  'sma',
  'ema',
  'vwap',
  'anchored_vwap',
  'rsi',
  'macd',
  'bollinger',
  'atr',
  'expected_range',
  'outlook',
  'signal',
  'pattern_reliability',
  'base_rate',
  'sentiment',
  'finbert',
  'sentiment_regime',
  'market_adjusted_return',
  'benchmark',
  'news_event',
  'p_value',
  'statistical_reliability',
  'earnings',
  'dividend',
  'split',
  'stale_data',
  'quota',
  'circuit_breaker',
] as const;

export type TermId = (typeof TERM_IDS)[number];

export interface GlossaryEntry {
  title: string;
  /** One to three plain sentences, aimed at a beginner. */
  body: string;
}

export const GLOSSARY: Record<TermId, GlossaryEntry> = {
  candlestick: {
    title: 'Candlestick',
    body: 'One bar on the chart that summarises a period of trading. The body spans the open and close price, and the thin lines (wicks) reach the period’s high and low.',
  },
  volume: {
    title: 'Volume',
    body: 'How many shares changed hands in a period. Big moves on high volume usually carry more weight than the same moves on low volume.',
  },
  doji: {
    title: 'Doji',
    body: 'A candle that opened and closed at almost the same price. It signals indecision: buyers and sellers cancelled each other out.',
  },
  hammer: {
    title: 'Hammer',
    body: 'A small body with a long lower wick, seen after a fall. Sellers pushed the price down but buyers pulled it back, which can hint that the fall is running out of steam.',
  },
  hanging_man: {
    title: 'Hanging man',
    body: 'The same shape as a hammer, but after a rise. It warns that buyers are losing control, though it needs a down day afterwards to confirm.',
  },
  inverted_hammer: {
    title: 'Inverted hammer',
    body: 'A small body with a long upper wick, seen after a fall. Buyers tried to push higher, which can hint at a turn upward if the next day agrees.',
  },
  shooting_star: {
    title: 'Shooting star',
    body: 'A small body with a long upper wick, seen after a rise. The price spiked up and was pushed back down, which can hint that buyers are tiring.',
  },
  bullish_engulfing: {
    title: 'Bullish engulfing',
    body: 'A large up candle that completely covers the previous down candle. It suggests buyers have taken over after a decline.',
  },
  bearish_engulfing: {
    title: 'Bearish engulfing',
    body: 'A large down candle that completely covers the previous up candle. It suggests sellers have taken over after a rise.',
  },
  bullish_harami: {
    title: 'Bullish harami',
    body: 'A small up candle sitting inside the body of the previous large down candle. Selling pressure is fading, which can precede a rebound.',
  },
  bearish_harami: {
    title: 'Bearish harami',
    body: 'A small down candle sitting inside the body of the previous large up candle. Buying momentum is fading, which can precede a pullback.',
  },
  piercing_line: {
    title: 'Piercing line',
    body: 'After a down candle, the next day opens lower but closes above the halfway point of that candle. It hints that buyers are stepping in.',
  },
  dark_cloud_cover: {
    title: 'Dark cloud cover',
    body: 'After an up candle, the next day opens higher but closes below the halfway point of that candle. It hints that sellers are stepping in.',
  },
  morning_star: {
    title: 'Morning star',
    body: 'Three candles: a big down day, a small indecisive day, then a big up day. It often marks the end of a decline.',
  },
  evening_star: {
    title: 'Evening star',
    body: 'Three candles: a big up day, a small indecisive day, then a big down day. It often marks the end of a rise.',
  },
  three_white_soldiers: {
    title: 'Three white soldiers',
    body: 'Three up days in a row, each closing higher than the last. It shows steady buying and can signal the start of an uptrend.',
  },
  three_black_crows: {
    title: 'Three black crows',
    body: 'Three down days in a row, each closing lower than the last. It shows steady selling and can signal the start of a downtrend.',
  },
  sma: {
    title: 'Simple moving average (SMA)',
    body: 'The average closing price over the last N days, drawn as a smooth line. Price above the line suggests an uptrend; below suggests a downtrend.',
  },
  ema: {
    title: 'Exponential moving average (EMA)',
    body: 'Like a simple moving average, but recent days count for more, so it reacts faster to new moves.',
  },
  vwap: {
    title: 'VWAP',
    body: 'Volume-weighted average price: the average price paid, giving more weight to days with more trading. Traders use it as a fair-price reference.',
  },
  anchored_vwap: {
    title: 'Anchored VWAP',
    body: 'VWAP measured from a chosen starting point, such as an earnings date. It shows the average price paid by everyone who bought since that event.',
  },
  rsi: {
    title: 'Relative strength index (RSI)',
    body: 'A 0 to 100 gauge of how fast the price has been rising or falling. Above 70 is often called overbought; below 30, oversold. Neither guarantees a reversal.',
  },
  macd: {
    title: 'MACD',
    body: 'Compares a fast and a slow moving average to show momentum. When its line crosses above its signal line, momentum is turning up; below, turning down.',
  },
  bollinger: {
    title: 'Bollinger Bands',
    body: 'Two lines drawn above and below a moving average, widening when the price swings more. Price near the outer band is stretched compared with its recent range.',
  },
  atr: {
    title: 'Average true range (ATR)',
    body: 'The typical size of a day’s price move, including gaps. A higher ATR means a more volatile stock.',
  },
  expected_range: {
    title: 'Expected range',
    body: 'A rough band for where the price may land over the next week, based on recent volatility. About 9 in 10 weeks fall inside this range. It is a guide to normal movement, not a forecast.',
  },
  outlook: {
    title: 'Outlook',
    body: 'A one-line summary of whether the recent signals lean up, down or neutral. It is a reading of the chart, not a prediction or advice.',
  },
  signal: {
    title: 'Signal',
    body: 'One indicator’s current reading, such as RSI being high. Each signal leans bullish, bearish or neutral, and the outlook combines them.',
  },
  pattern_reliability: {
    title: 'Pattern reliability',
    body: 'How often this chart pattern was followed by a rise (or fall) a week later in this stock’s past. A pattern only counts as reliable when it has clearly beaten a typical week in the same kind of trend.',
  },
  base_rate: {
    title: 'Base rate',
    body: 'How often the price rose over the same period at any time, with no pattern at all. A pattern only helps if it beats this baseline.',
  },
  sentiment: {
    title: 'Sentiment',
    body: 'Whether news headlines about the stock read as positive, negative or neutral, scored automatically by a language model.',
  },
  finbert: {
    title: 'FinBERT',
    body: 'A language model trained on financial text. It reads each headline and rates it positive, negative or neutral.',
  },
  sentiment_regime: {
    title: 'Sentiment regime',
    body: 'The prevailing tone of recent news compared with this stock’s own usual tone: for example more positive than normal, or unusually negative.',
  },
  market_adjusted_return: {
    title: 'Market-adjusted move',
    body: 'How much better or worse the stock did than expected, given how the overall market moved that day and how this stock usually tracks the market.',
  },
  benchmark: {
    title: 'Benchmark',
    body: 'The market index the stock is compared against, such as the S&P 500 for US stocks or the Straits Times Index for Singapore.',
  },
  news_event: {
    title: 'News event',
    body: 'A day with a cluster of notable headlines about the stock. We check what the price did around these days to see whether news moved it.',
  },
  p_value: {
    title: 'P-value',
    body: 'How likely a gap this large would appear by pure chance if news had no effect. Smaller means the effect is less likely to be luck; below 0.05 is the usual cutoff.',
  },
  statistical_reliability: {
    title: 'Statistical reliability',
    body: 'How much to trust a finding, based on how many events it rests on and how clear the result is. Few events or a noisy result means low reliability.',
  },
  earnings: {
    title: 'Earnings',
    body: 'A company’s quarterly report of profit and revenue. Prices often jump or drop on the announcement, so it is marked on the chart.',
  },
  dividend: {
    title: 'Dividend',
    body: 'A cash payment a company makes to shareholders. The share price usually drops by about the dividend amount on the ex-dividend date.',
  },
  split: {
    title: 'Stock split',
    body: 'A company divides each share into several, cutting the price per share without changing the company’s value. Past prices are adjusted so the chart stays continuous.',
  },
  stale_data: {
    title: 'Stale data',
    body: 'Information that is older than expected, usually because a data source was unavailable. The app shows the last saved results and says how old they are.',
  },
  quota: {
    title: 'Quota',
    body: 'The number of requests a data source allows per day on our plan. When it runs out, that source pauses until the limit resets.',
  },
  circuit_breaker: {
    title: 'Circuit breaker',
    body: 'A safety switch that stops calling a data source after repeated failures, then retries after a cooldown. It prevents one broken source from slowing everything else.',
  },
};
