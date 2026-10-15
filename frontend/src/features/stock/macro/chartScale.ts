import type { MacroStatsOut } from '../../../api/types';

/**
 * Axis maths for the bucket chart. Values are percent units. The axis is symmetric around zero so
 * a bar's length reads the same either side. Only three ticks (-max, 0, +max) so the labels fit a
 * 375px phone.
 */
export interface Axis {
  /** Half-width of the axis: it runs from -max to +max. */
  max: number;
  /** Tick values: -max, 0 and +max. */
  ticks: number[];
}

/** Round numbers the axis end may take, as multiples of a power of ten. */
const NICE = [1, 1.2, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10];

/** Symmetric axis that covers `extent` (the largest absolute value to show, in percent). */
export function symmetricAxis(extent: number): Axis {
  const safe = Number.isFinite(extent) && extent > 0 ? extent : 1;
  const power = 10 ** Math.floor(Math.log10(safe));
  const max = (NICE.find((m) => m * power >= safe - 1e-9) ?? 10) * power;
  const rounded = Math.round(max * 1e6) / 1e6;
  return { max: rounded, ticks: [-rounded, 0, rounded] };
}

/** A bucket is tested when it has a mean and its 95% range (the backend sends both or neither). */
export function isTested(b: MacroStatsOut['buckets'][string] | undefined): boolean {
  return b?.mean_car_0_1 != null && b.ci_low_0_1 != null && b.ci_high_0_1 != null;
}

export function hasTestedBucket(stats: MacroStatsOut): boolean {
  return Object.values(stats.buckets).some(isTested);
}
