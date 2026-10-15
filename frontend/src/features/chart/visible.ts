import type { Candle } from '../../api/types';

/** Daily bars carry "YYYY-MM-DD", hourly bars UNIX seconds; `visible_from` uses the same encoding. */
export type BarTime = string | number;

/**
 * True when `time` is at or after `from`. Times of different encodings cannot be compared, so
 * they count as visible rather than silently hiding data.
 */
export function onOrAfter(time: BarTime, from: BarTime): boolean {
  return typeof time === typeof from ? time >= from : true;
}

/** The bars of the range the viewer chose: everything before `visible_from` is only for panning. */
export function visibleCandles(candles: Candle[], visibleFrom: BarTime | undefined): Candle[] {
  if (visibleFrom === undefined) return candles;
  return candles.filter((c) => onOrAfter(c.time, visibleFrom));
}
