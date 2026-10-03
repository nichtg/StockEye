import { useMemo } from 'react';
import { patternSentence } from './technicalText';
import { useTechnical } from './useStockData';

/**
 * Pattern key -> the plain-language reliability sentence for the patterns seen recently. Shares
 * the technical report's cached query, so asking for it costs no extra request.
 */
export function usePatternReliability(symbol: string): Record<string, string> {
  const { data } = useTechnical(symbol);
  return useMemo(
    () =>
      Object.fromEntries(
        (data?.recent_patterns ?? []).map((p) => [p.key, patternSentence(p.stats, p.bias)]),
      ),
    [data],
  );
}
