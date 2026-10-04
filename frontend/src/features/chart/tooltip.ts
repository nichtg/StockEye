import type { Candle, ChartMarker } from '../../api/types';
import { exchangeTimeZone, hour12For, type Exchange } from '../../lib/exchange';
import { formatDate, formatPct, formatPrice, formatSigned, formatVolume } from '../../lib/format';
import { moveText } from '../stock/macroText';

/** Pattern key -> plain-language reliability sentence (see `usePatternReliability`). */
export type PatternSentences = Record<string, string | undefined>;

export function eventText(marker: ChartMarker, sentences?: PatternSentences): string {
  switch (marker.kind) {
    case 'earnings':
      return marker.label.replace(/vs est ([\d.,-]+)/, 'vs $1 estimate');
    case 'dividend':
    case 'split':
      return marker.label;
    case 'pattern': {
      const sentence = marker.pattern ? sentences?.[marker.pattern] : undefined;
      return sentence ? `${marker.label}. ${sentence}` : marker.label;
    }
    case 'news': {
      const car = marker.car_0_1;
      if (car == null) return `News: “${marker.label}”`;
      return `News: “${marker.label}” (${moveText(car)} over 2 days)`;
    }
  }
}

export interface TooltipContent {
  open: string;
  high: string;
  low: string;
  close: string;
  volume: string;
  change: string;
  changePct: number;
  events: string[];
}

export function tooltipContent(
  candle: Candle,
  previous: Candle | undefined,
  markers: ChartMarker[],
  ctx: { currency: string; exchange: Exchange },
  sentences?: PatternSentences,
): TooltipContent {
  const base = previous?.close ?? candle.open;
  const delta = candle.close - base;
  const pct = base ? (delta / base) * 100 : 0;
  const money = (v: number) => formatPrice(v, ctx.currency, ctx.exchange);
  const key = String(candle.time);
  return {
    open: money(candle.open),
    high: money(candle.high),
    low: money(candle.low),
    close: money(candle.close),
    volume: formatVolume(candle.volume),
    change: formatSigned(delta, 2, ctx.exchange),
    changePct: pct,
    events: markers.filter((m) => String(m.time) === key).map((m) => eventText(m, sentences)),
  };
}

/** Screen-reader summary of what the chart currently shows. */
export function chartSummary(
  symbol: string,
  range: string,
  candles: Candle[],
  ctx: { currency: string; exchange: Exchange },
): string {
  const first = candles[0];
  const last = candles.at(-1);
  if (!first || !last) return `${symbol} price chart, ${range}: no trading data.`;
  const pct = first.open ? (last.close / first.open - 1) * 100 : 0;
  const word = pct >= 0 ? 'up' : 'down';
  return `${symbol} price chart for ${range}. Last close ${formatPrice(last.close, ctx.currency, ctx.exchange)}, ${word} ${formatPct(Math.abs(pct))} over the period.`;
}

/** "3 Oct 2026" for daily bars, "3 Oct, 10:00 AM" in the exchange's zone for hourly bars. */
export function barLabel(time: string | number | undefined, exchange: Exchange): string {
  if (time === undefined) return '';
  if (typeof time === 'string') return formatDate(time, exchange);
  return formatDate(new Date(time * 1000), exchange, {
    day: 'numeric',
    month: 'short',
    hour: 'numeric',
    minute: '2-digit',
    hour12: hour12For(exchange),
    timeZone: exchangeTimeZone(exchange),
  });
}
