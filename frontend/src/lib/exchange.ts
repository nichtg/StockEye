export type Exchange = 'US' | 'SGX';

export function exchangeLocale(exchange: Exchange | null | undefined): string {
  return exchange === 'SGX' ? 'en-SG' : 'en-US';
}

export function exchangeTimeZone(exchange: Exchange | null | undefined): string {
  return exchange === 'SGX' ? 'Asia/Singapore' : 'America/New_York';
}

/** The US shows 12-hour clock times; Singapore shows 24-hour. */
export function hour12For(exchange: Exchange | null | undefined): boolean {
  return exchange !== 'SGX';
}

/** Short zone abbreviation. Intl only gives "GMT+8" for Singapore, so name it ourselves. */
export function zoneLabel(exchange: Exchange | null | undefined, at: Date): string {
  if (exchange === 'SGX') return 'SGT';
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone: exchangeTimeZone(exchange),
    timeZoneName: 'short',
  }).formatToParts(at);
  return parts.find((p) => p.type === 'timeZoneName')?.value ?? 'ET';
}

/** Trading currency implied by the exchange, for places that have no quote yet. */
export function exchangeCurrency(exchange: Exchange | null | undefined): string {
  return exchange === 'SGX' ? 'SGD' : 'USD';
}

/** Exchange implied by a Yahoo-style ticker, for places that have no quote yet. */
export function exchangeOfSymbol(symbol: string): Exchange {
  return symbol.toUpperCase().endsWith('.SI') ? 'SGX' : 'US';
}
