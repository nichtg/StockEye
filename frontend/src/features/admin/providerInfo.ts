import type { ProviderLevel } from '../../api/types';

const NAMES: Record<string, string> = {
  yahoo: 'Yahoo Finance',
  googlenews: 'Google News',
  finnhub: 'Finnhub',
  marketaux: 'Marketaux',
  alphavantage: 'Alpha Vantage',
};

/** Human name for a backend provider id (yahoo, google_news, finnhub, marketaux, alpha_vantage). */
export function providerName(id: string): string {
  const key = id.toLowerCase().replace(/[^a-z0-9]/g, '');
  return NAMES[key] ?? id;
}

export const LEVEL_LABEL: Record<ProviderLevel, string> = {
  ok: 'OK',
  warning: 'Near limit',
  blocked: 'Blocked',
};
