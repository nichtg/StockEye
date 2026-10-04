import type { Lean, PatternStatsOut } from '../../api/types';
import { GLOSSARY, type TermId } from '../../glossary';
import { formatPct } from '../../lib/format';

export const LEAN_WORD: Record<Lean, string> = {
  bullish: 'Bullish',
  neutral: 'Neutral',
  bearish: 'Bearish',
};

/** "Bullish lean", "Neutral": the single wording for an outlook, wherever it appears. */
export function leanLabel(lean: Lean): string {
  return lean === 'neutral' ? LEAN_WORD.neutral : `${LEAN_WORD[lean]} lean`;
}

/** A 0..1 fraction as a whole percent. */
export const pct = (fraction: number) => formatPct(fraction * 100, { digits: 0 });

/** Plain-language reliability of a pattern. Never shows raw sample sizes as "n=". */
export function patternSentence(stats: PatternStatsOut | null, bias: Lean): string {
  if (!stats || stats.n === 0)
    return 'No past occurrences yet, so there is nothing to judge it by.';
  if (!stats.sufficient) return `Only seen ${String(stats.n)} times; not enough history to judge.`;
  if (stats.hit_rate == null || bias === 'neutral') {
    return `Seen ${String(stats.n)} times in the past 3 years; this pattern does not point up or down.`;
  }
  const wins = Math.round(stats.hit_rate * stats.n);
  const direction = bias === 'bearish' ? 'lower' : 'higher';
  let text = `Seen ${String(stats.n)} times in the past 3 years; price was ${direction} a week later ${String(wins)} of ${String(stats.n)} times (${pct(stats.hit_rate)})`;
  if (stats.base_rate != null) text += `, versus ${pct(stats.base_rate)} for a typical week`;
  text += '.';
  if (stats.edge != null && stats.edge <= 0) text += ' That is no better than a typical week.';
  return text;
}

/** Wilson score interval for a proportion, 95% by default. */
export function wilsonInterval(successes: number, total: number, z = 1.96): [number, number] {
  if (total <= 0) return [0, 0];
  const p = successes / total;
  const z2 = z * z;
  const denom = 1 + z2 / total;
  const centre = (p + z2 / (2 * total)) / denom;
  const margin = (z * Math.sqrt((p * (1 - p)) / total + z2 / (4 * total * total))) / denom;
  return [Math.max(0, centre - margin), Math.min(1, centre + margin)];
}

export function isTermId(key: string): key is TermId {
  return key in GLOSSARY;
}

const SIGNAL_TERMS: Record<string, TermId> = {
  patterns: 'pattern_reliability',
  rsi14: 'rsi',
  ema_cross: 'ema',
  macd_momentum: 'macd',
  vwap: 'vwap',
};

export function signalTerm(key: string): TermId {
  return SIGNAL_TERMS[key] ?? 'signal';
}
