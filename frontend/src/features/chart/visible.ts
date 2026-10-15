import type { Candle } from '../../api/types';

/** Daily bars carry "YYYY-MM-DD", hourly bars UNIX seconds; `visible_from` uses the same encoding. */
export type BarTime = string | number;

/** True when `time` is at or after `from`; the API gives both the same encoding. */
export function onOrAfter(time: BarTime, from: BarTime): boolean {
  return typeof time === 'string' ? time >= (from as string) : time >= (from as number);
}

/**
 * Position of the first bar at or after `from`: where a range view starts. When every bar is
 * earlier than `from` the view starts at the latest bar, never at the oldest.
 */
export function startIndex(candles: Candle[], from: BarTime | undefined): number {
  // An older API without `visible_from` sends only the chosen range: show all of it.
  if (from === undefined) return 0;
  const i = candles.findIndex((c) => onOrAfter(c.time, from));
  return i === -1 ? Math.max(0, candles.length - 1) : i;
}

/** The bars of the range the viewer chose: everything before `visible_from` is only for panning. */
export function visibleCandles(candles: Candle[], visibleFrom: BarTime | undefined): Candle[] {
  if (visibleFrom === undefined) return candles;
  return candles.filter((c) => onOrAfter(c.time, visibleFrom));
}
