/**
 * Axis maths for the bucket chart. Values are percent units. The axis is symmetric around zero so
 * a bar's length reads the same either side, and it ends on a tick so no bar touches the edge.
 */
export interface Axis {
  /** Half-width of the axis: it runs from -max to +max. */
  max: number;
  /** Tick values from -max to +max, including 0. */
  ticks: number[];
}

const STEPS = [1, 2, 2.5, 5];

/** The smallest "nice" step (1, 2, 2.5 or 5 times a power of ten) giving at most `perSide` ticks per side. */
function niceStep(extent: number, perSide: number): number {
  const raw = extent / perSide;
  const power = 10 ** Math.floor(Math.log10(raw));
  for (const m of STEPS) if (m * power >= raw) return m * power;
  return 10 * power;
}

/** Symmetric axis that covers `extent` (the largest absolute value to show, in percent). */
export function symmetricAxis(extent: number): Axis {
  const safe = Number.isFinite(extent) && extent > 0 ? extent : 1;
  const step = niceStep(safe, 2);
  const max = Math.ceil(safe / step - 1e-9) * step;
  const count = Math.round(max / step);
  const ticks: number[] = [];
  for (let i = -count; i <= count; i += 1) ticks.push(Math.round(i * step * 1e6) / 1e6);
  return { max, ticks };
}
