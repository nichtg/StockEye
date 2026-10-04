import type { Exchange } from './exchange';
import { exchangeLocale, exchangeTimeZone, hour12For, zoneLabel } from './exchange';

const priceFormats = new Map<string, Intl.NumberFormat>();

/** Symbols shown instead of the locale's: "$" alone is ambiguous between USD and SGD. */
const CURRENCY_SYMBOLS: Record<string, string> = { USD: '$', SGD: 'S$' };

function priceFormat(locale: string, currency: string): Intl.NumberFormat {
  const key = `${locale}|${currency}`;
  let fmt = priceFormats.get(key);
  if (!fmt) {
    try {
      fmt = new Intl.NumberFormat(locale, {
        style: 'currency',
        currency,
        currencyDisplay: 'narrowSymbol',
      });
    } catch {
      fmt = new Intl.NumberFormat(locale, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    }
    priceFormats.set(key, fmt);
  }
  return fmt;
}

/** "$333.69" for USD, "S$77.21" for SGD, in the exchange's number format. */
export function formatPrice(
  value: number | null | undefined,
  currency: string | null | undefined,
  exchange: Exchange | null | undefined,
): string {
  if (value == null) return '–';
  const code = currency ?? 'USD';
  const parts = priceFormat(exchangeLocale(exchange), code).formatToParts(value);
  const symbol = CURRENCY_SYMBOLS[code];
  if (!symbol) return parts.map((p) => p.value).join('');
  return parts.map((p) => (p.type === 'currency' ? symbol : p.value)).join('');
}

const numberFormats = new Map<string, Intl.NumberFormat>();

function numberFormat(locale: string, options: Intl.NumberFormatOptions): Intl.NumberFormat {
  const key = `${locale}|${JSON.stringify(options)}`;
  let fmt = numberFormats.get(key);
  if (!fmt) {
    fmt = new Intl.NumberFormat(locale, options);
    numberFormats.set(key, fmt);
  }
  return fmt;
}

/** Unicode minus keeps signed numbers aligned and unambiguous; Intl emits a hyphen. */
function withTrueMinus(fmt: Intl.NumberFormat, value: number): string {
  return fmt
    .formatToParts(value)
    .map((p) => (p.type === 'minusSign' ? '−' : p.value))
    .join('');
}

interface DigitOptions {
  /** Show "+" for positive values and "−" for negative ones; zero stays bare. */
  signed?: boolean;
  digits?: number;
}

function fixed({ signed = false, digits = 2 }: DigitOptions, extra: Intl.NumberFormatOptions = {}) {
  return {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
    signDisplay: signed ? ('exceptZero' as const) : ('auto' as const),
    ...extra,
  };
}

/** Plain number with fixed decimals in the exchange's locale (no currency symbol). */
export function formatNumber(
  value: number,
  exchange: Exchange | null | undefined,
  opts: DigitOptions = {},
): string {
  return withTrueMinus(numberFormat(exchangeLocale(exchange), fixed(opts)), value);
}

/** "+0.36" / "−0.36": a signed amount in the exchange's number format. */
export function formatSigned(value: number, digits: number, exchange?: Exchange | null): string {
  return formatNumber(value, exchange, { signed: true, digits });
}

/** Percent from percent units: `0.86` is "0.86%". The one place percentages are formatted. */
export function formatPct(value: number, opts: DigitOptions = {}): string {
  const { digits = 1 } = opts;
  return withTrueMinus(
    numberFormat('en-US', fixed({ ...opts, digits }, { style: 'percent' })),
    value / 100,
  );
}

/** Percentage points, e.g. the edge of a pattern over a typical week: "+12 pts". */
export function formatPoints(value: number, opts: DigitOptions = {}): string {
  return `${formatNumber(value, null, { signed: true, digits: 0, ...opts })} pts`;
}

export function formatVolume(value: number, exchange?: Exchange | null): string {
  return numberFormat(exchangeLocale(exchange), {
    notation: 'compact',
    maximumFractionDigits: 2,
  }).format(value);
}

export type Direction = 'up' | 'down' | 'flat';

export function directionOf(value: number | null | undefined, digits = 2): Direction {
  if (value == null) return 'flat';
  const rounded = Number(value.toFixed(digits));
  if (rounded > 0) return 'up';
  if (rounded < 0) return 'down';
  return 'flat';
}

export const DIRECTION_GLYPH: Record<Direction, string> = { up: '▲', down: '▼', flat: '' };

const dateFormats = new Map<string, Intl.DateTimeFormat>();

/** Cached `Intl.DateTimeFormat`: constructing one per call is the slow part of formatting. */
export function dateFormat(locale: string, options: Intl.DateTimeFormatOptions) {
  const key = `${locale}|${JSON.stringify(options)}`;
  let fmt = dateFormats.get(key);
  if (!fmt) {
    fmt = new Intl.DateTimeFormat(locale, options);
    dateFormats.set(key, fmt);
  }
  return fmt;
}

export function formatDate(
  value: string | Date,
  exchange: Exchange | null | undefined,
  opts: Intl.DateTimeFormatOptions = { day: 'numeric', month: 'short', year: 'numeric' },
): string {
  // A bare YYYY-MM-DD is a calendar date, not an instant: pin it to UTC so no zone shifts it.
  const date =
    typeof value === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(value)
      ? new Date(`${value}T00:00:00Z`)
      : new Date(value);
  const timeZone =
    opts.timeZone ?? (typeof value === 'string' && value.length === 10 ? 'UTC' : undefined);
  return dateFormat(exchangeLocale(exchange), { ...opts, timeZone }).format(date);
}

/** "16:05 SGT" / "4:05 PM EDT" for an instant, in the exchange's own zone. */
export function formatAsOf(iso: string, exchange: Exchange | null | undefined): string {
  const date = new Date(iso);
  const timeZone = exchangeTimeZone(exchange);
  const time = dateFormat(exchangeLocale(exchange), {
    hour: 'numeric',
    minute: '2-digit',
    hour12: hour12For(exchange),
    timeZone,
  }).format(date);
  const day = dateFormat(exchangeLocale(exchange), {
    day: 'numeric',
    month: 'short',
    timeZone,
  }).format(date);
  return `${day}, ${time} ${zoneLabel(exchange, date)}`;
}

const rtf = new Intl.RelativeTimeFormat('en', { numeric: 'auto' });

const UNITS: [Intl.RelativeTimeFormatUnit, number][] = [
  ['year', 365 * 24 * 3600],
  ['month', 30 * 24 * 3600],
  ['week', 7 * 24 * 3600],
  ['day', 24 * 3600],
  ['hour', 3600],
  ['minute', 60],
];

/** "3 hours ago", "yesterday". Anything under a minute reads "just now". */
export function formatRelative(iso: string, now: number = Date.now()): string {
  const seconds = Math.round((new Date(iso).getTime() - now) / 1000);
  const abs = Math.abs(seconds);
  for (const [unit, size] of UNITS) {
    if (abs >= size) return rtf.format(Math.round(seconds / size), unit);
  }
  return 'just now';
}

/** Market-adjusted 2-day move from a fraction (0.021 means 2.1% better than expected). */
export function moveText(fraction: number): string {
  const size = formatPct(Math.abs(fraction) * 100);
  if (size === formatPct(0)) return 'In line with expectations';
  return `${size} ${fraction > 0 ? 'better' : 'worse'} than expected`;
}
