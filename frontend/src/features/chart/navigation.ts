import type { IChartApi, Time } from 'lightweight-charts';
import type { BarTime } from './visible';

/** Empty space kept right of the latest bar. */
export const RIGHT_OFFSET = 2;
/** Zooming in never shows fewer bars than this. */
export const MIN_SPAN = 10;
/** One zoom step multiplies or divides the visible span by this. */
export const ZOOM_STEP = 1.5;
/** One pan step moves the view by this share of the visible span. */
export const PAN_FRACTION = 0.25;

/** A range of bar positions (logical indices), as the chart reports them. */
export interface Span {
  from: number;
  to: number;
}

/** The first and last positions the view may show: bar 0 to the latest bar plus the right offset. */
export function dataBounds(barCount: number): Span {
  return { from: 0, to: Math.max(0, barCount - 1) + RIGHT_OFFSET };
}

/** Slides `range` the least needed to sit inside `bounds`; its span is kept. */
function inside(range: Span, bounds: Span): Span {
  const span = range.to - range.from;
  if (range.from < bounds.from) return { from: bounds.from, to: bounds.from + span };
  if (range.to > bounds.to) return { from: bounds.to - span, to: bounds.to };
  return range;
}

/**
 * Scales the span of `range` by `factor` (below 1 zooms in) around its centre. The result is
 * never narrower than MIN_SPAN bars, never wider than the data, and stays inside `bounds`.
 */
export function zoomRange(range: Span, factor: number, bounds: Span): Span {
  const total = bounds.to - bounds.from;
  const floor = Math.min(MIN_SPAN, total);
  const span = Math.min(total, Math.max(floor, (range.to - range.from) * factor));
  const centre = (range.from + range.to) / 2;
  return inside({ from: centre - span / 2, to: centre + span / 2 }, bounds);
}

/** Moves `range` by `fraction` of its span (negative goes back in time), stopping at `bounds`. */
export function panRange(range: Span, fraction: number, bounds: Span): Span {
  const shift = (range.to - range.from) * fraction;
  return inside({ from: range.from + shift, to: range.to + shift }, bounds);
}

/** What the viewer's first look at a symbol and range shows: from `visible_from` to the last bar. */
export interface View {
  from: BarTime;
  to: BarTime;
}

/** Shows `view`, keeping the usual empty space right of the latest bar. */
export function showView(chart: IChartApi, view: View): void {
  const scale = chart.timeScale();
  scale.setVisibleRange({ from: view.from as Time, to: view.to as Time });
  const shown = scale.getVisibleLogicalRange();
  if (shown) scale.setVisibleLogicalRange({ from: shown.from, to: shown.to + RIGHT_OFFSET });
}

export interface ChartNavigator {
  zoomIn: () => void;
  zoomOut: () => void;
  panLeft: () => void;
  panRight: () => void;
  reset: () => void;
}

/** Moves the chart's logical range with the pure helpers; a chart without data is left alone. */
export function createNavigator(
  chart: IChartApi,
  barCount: () => number,
  view: () => View | undefined,
): ChartNavigator {
  const move = (next: (range: Span, bounds: Span) => Span) => () => {
    const scale = chart.timeScale();
    const range = scale.getVisibleLogicalRange();
    if (!range || barCount() === 0) return;
    const { from, to } = next(range, dataBounds(barCount()));
    scale.setVisibleLogicalRange({ from, to });
  };
  return {
    zoomIn: move((r, b) => zoomRange(r, 1 / ZOOM_STEP, b)),
    zoomOut: move((r, b) => zoomRange(r, ZOOM_STEP, b)),
    panLeft: move((r, b) => panRange(r, -PAN_FRACTION, b)),
    panRight: move((r, b) => panRange(r, PAN_FRACTION, b)),
    reset: () => {
      const v = view();
      if (v) showView(chart, v);
      else chart.timeScale().fitContent();
    },
  };
}

export type NavAction = keyof ChartNavigator;

interface KeyLike {
  key: string;
  shiftKey: boolean;
  ctrlKey: boolean;
  metaKey: boolean;
  altKey: boolean;
}

/**
 * The navigation a key press asks for, or null. Plain arrows are left to the bar cursor, which
 * reads out one bar at a time; Shift+arrow scrolls. Browser shortcuts (Ctrl/Cmd + and -) are not ours.
 */
export function navKeyAction(e: KeyLike): NavAction | null {
  if (e.ctrlKey || e.metaKey || e.altKey) return null;
  if (e.key === 'ArrowLeft') return e.shiftKey ? 'panLeft' : null;
  if (e.key === 'ArrowRight') return e.shiftKey ? 'panRight' : null;
  if (e.key === '+' || e.key === '=') return 'zoomIn';
  if (e.key === '-' || e.key === '_') return 'zoomOut';
  if (e.key === '0') return 'reset';
  return null;
}

interface KeyEventLike extends KeyLike {
  preventDefault: () => void;
  stopPropagation: () => void;
}

/** Runs the navigation a key asks for and keeps the key from reaching the page. True when handled. */
export function handleNavKey(e: KeyEventLike, nav: ChartNavigator | null): boolean {
  const action = navKeyAction(e);
  if (!action || !nav) return false;
  e.preventDefault();
  e.stopPropagation();
  nav[action]();
  return true;
}
