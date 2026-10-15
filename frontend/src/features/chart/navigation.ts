import type { IChartApi } from 'lightweight-charts';

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

/** The first and last positions the view may show. fixRightEdge keeps the latest bar the limit. */
export function dataBounds(barCount: number): Span {
  return { from: 0, to: Math.max(0, barCount - 1) };
}

/** Which moves still change the view; the buttons are disabled when theirs does not. */
export interface NavLimits {
  canZoomIn: boolean;
  canZoomOut: boolean;
  canPanLeft: boolean;
  canPanRight: boolean;
}

export const NO_LIMITS: NavLimits = {
  canZoomIn: false,
  canZoomOut: false,
  canPanLeft: false,
  canPanRight: false,
};

/** Half a bar of slack, since the chart reports fractional positions. */
const SLACK = 0.5;

export function navLimits(range: Span | null, barCount: number): NavLimits {
  if (!range || barCount === 0) return NO_LIMITS;
  const bounds = dataBounds(barCount);
  const span = range.to - range.from;
  return {
    canZoomIn: span > Math.min(MIN_SPAN, bounds.to - bounds.from) + SLACK,
    canZoomOut: span < bounds.to - bounds.from - SLACK,
    canPanLeft: range.from > bounds.from + SLACK,
    canPanRight: range.to < bounds.to - SLACK,
  };
}

/** Scrolls `range` the least needed to include bar `index`; a range that already does stays. */
export function revealIndex(range: Span, index: number, bounds: Span): Span {
  if (index < range.from)
    return inside({ from: index, to: index + (range.to - range.from) }, bounds);
  if (index > range.to) return inside({ from: index - (range.to - range.from), to: index }, bounds);
  return range;
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

/** The viewer's first look at a symbol and range, in bar positions: from where the chosen range starts to the last bar. */
export interface View {
  startIndex: number;
  barCount: number;
}

/**
 * Shows `view` with one logical-range call. Going through times would not work: the chart only
 * applies a time range on its next frame, so a following read or write would see the old range.
 */
export function showView(chart: IChartApi, view: View): void {
  chart.timeScale().setVisibleLogicalRange({ from: view.startIndex, to: view.barCount - 1 });
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
