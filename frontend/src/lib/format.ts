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

/**
 * Swaps the currency part for our own symbol when we have one ("S$" for SGD). Other currencies
 * keep what Intl produced, and a code Intl rejects was already replaced by a bare number.
 */
function withCurrencySymbol(parts: Intl.NumberFormatPart[], code: string): string {
  const symbol = CURRENCY_SYMBOLS[code];
  return parts.map((p) => (p.type === 'currency' && symbol ? symbol : p.value)).join('');
}

/** "$333.69" for USD, "S$77.21" for SGD, in the exchange's number format. */
export function formatPrice(
  value: number | null | undefined,
  currency: string | null | undefined,
  exchange: Exchange | null | undefined,
): string {
  if (value == null) return '–';
  const code = currency ?? 'USD';
  return withCurrencySymbol(priceFormat(exchangeLocale(exchange), code).formatToParts(value), code);
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

/**
 * Uses a non-breaking hyphen (U+2011) in "market‑linked" so a wrapping line never splits it.
 * Market-adjusted 2-day move from a fraction (0.021 means 2.1% above its usual market-linked
 * move), split so a row can keep the figure on one line and let the rest wrap.
 */
export function moveParts(fraction: number): { figure: string | null; rest: string } {
  const size = formatPct(Math.abs(fraction) * 100);
  if (size === formatPct(0))
    return { figure: null, rest: 'In line with its usual market‑linked move' };
  return {
    figure: size,
    rest: `${fraction > 0 ? 'above' : 'below'} its usual market‑linked move`,
  };
}

export function moveText(fraction: number): string {
  const { figure, rest } = moveParts(fraction);
  return figure ? `${figure} ${rest}` : rest;
}

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

/** "Oct 2024" from an ISO date ("2024-10-01"), read as written so no time zone can shift the month. */
export function formatMonthYear(iso: string): string | null {
  const m = /^(\d{4})-(\d{2})-\d{2}/.exec(iso);
  const month = m ? MONTHS[Number(m[2]) - 1] : undefined;
  return m && month ? `${month} ${m[1]}` : null;
}

/** "Oct 2024 to Oct 2026", or just "Oct 2026" when both fall in one month; null when either end is missing. */
export function formatMonthRange(
  first: string | null | undefined,
  last: string | null | undefined,
): string | null {
  if (!first || !last) return null;
  const a = formatMonthYear(first);
  const b = formatMonthYear(last);
  if (!a || !b) return null;
  return a === b ? a : `${a} to ${b}`;
}

/** "$3.2T", "S$208.9B", "$850M": a large money amount in compact form, in the stock's own currency. */
export function formatCompactCurrency(
  value: number | null | undefined,
  currency: string | null | undefined,
  exchange: Exchange | null | undefined,
): string {
  if (value == null) return '–';
  const code = currency ?? 'USD';
  let fmt: Intl.NumberFormat;
  try {
    fmt = numberFormat(exchangeLocale(exchange), {
      style: 'currency',
      currency: code,
      currencyDisplay: 'narrowSymbol',
      notation: 'compact',
      // Three significant digits: "$5.05T" rather than a rounded "$5T", "S$209B".
      maximumSignificantDigits: 3,
    });
  } catch {
    // Intl rejects a code it doesn't know: show the bare compact number rather than fail.
    return formatVolume(value, exchange);
  }
  return withCurrencySymbol(fmt.formatToParts(value), code);
}

/** A yield from a fraction: `0.0044` is "0.44%". */
export function formatYield(fraction: number): string {
  return formatPct(fraction * 100, { digits: 2 });
}

/** "$164.08 – $237.23"; null unless both ends are known. */
export function formatPriceRange(
  low: number | null | undefined,
  high: number | null | undefined,
  currency: string | null | undefined,
  exchange: Exchange | null | undefined,
): string | null {
  if (low == null || high == null) return null;
  return `${formatPrice(low, currency, exchange)} – ${formatPrice(high, currency, exchange)}`;
}

/** A whole number with thousands separators: 164,000. */
export function formatCount(value: number, exchange?: Exchange | null): string {
  return formatNumber(value, exchange, { digits: 0 });
}

/** The calendar day of an instant in the exchange's own zone, as "2026-10-03" (sorts and groups). */
export function exchangeDay(iso: string, exchange: Exchange | null | undefined): string {
  return dateFormat('en-CA', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    timeZone: exchangeTimeZone(exchange),
  }).format(new Date(iso));
}

/** "4:05 PM EDT" / "16:05 SGT": the time of day of an instant in the exchange's zone. */
export function formatClock(iso: string, exchange: Exchange | null | undefined): string {
  const date = new Date(iso);
  const time = dateFormat(exchangeLocale(exchange), {
    hour: 'numeric',
    minute: '2-digit',
    hour12: hour12For(exchange),
    timeZone: exchangeTimeZone(exchange),
  }).format(date);
  return `${time} ${zoneLabel(exchange, date)}`;
}
