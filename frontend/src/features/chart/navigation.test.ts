import type { IChartApi } from 'lightweight-charts';
import { describe, expect, it, vi } from 'vitest';
import {
  MIN_SPAN,
  ZOOM_STEP,
  createNavigator,
  dataBounds,
  handleNavKey,
  navKeyAction,
  panRange,
  zoomRange,
} from './navigation';

// 100 bars: positions 0 to 99, plus the 2 bars of empty space on the right.
const bounds = dataBounds(100);

describe('zoomRange', () => {
  it('zooms in around the centre by the factor', () => {
    expect(zoomRange({ from: 30, to: 60 }, 1 / ZOOM_STEP, bounds)).toEqual({ from: 35, to: 55 });
  });

  it('zooms out around the centre by the factor', () => {
    expect(zoomRange({ from: 30, to: 60 }, ZOOM_STEP, bounds)).toEqual({ from: 22.5, to: 67.5 });
  });

  it('never shows fewer than the minimum number of bars', () => {
    const r = zoomRange({ from: 40, to: 52 }, 0.1, bounds);
    expect(r.to - r.from).toBe(MIN_SPAN);
    expect((r.from + r.to) / 2).toBe(46);
  });

  it('never shows more than the data holds, and slides back inside at the edges', () => {
    expect(zoomRange({ from: 10, to: 90 }, 5, bounds)).toEqual(bounds);
    // Zooming out near the left edge keeps its span but stops at bar 0.
    expect(zoomRange({ from: 2, to: 32 }, ZOOM_STEP, bounds)).toEqual({ from: 0, to: 45 });
  });

  it('copes with data shorter than the minimum span', () => {
    expect(zoomRange({ from: 0, to: 4 }, 0.1, dataBounds(3))).toEqual({ from: 0, to: 4 });
  });
});

describe('panRange', () => {
  it('moves by a share of the span in either direction', () => {
    expect(panRange({ from: 40, to: 60 }, 0.25, bounds)).toEqual({ from: 45, to: 65 });
    expect(panRange({ from: 40, to: 60 }, -0.25, bounds)).toEqual({ from: 35, to: 55 });
  });

  it('stops at the oldest bar and at the latest one, keeping the span', () => {
    expect(panRange({ from: 3, to: 23 }, -0.25, bounds)).toEqual({ from: 0, to: 20 });
    expect(panRange({ from: 80, to: 100 }, 0.25, bounds)).toEqual({ from: 81, to: 101 });
  });
});

function fakeChart(range: { from: number; to: number } | null = { from: 40, to: 60 }) {
  const timeScale = {
    getVisibleLogicalRange: vi.fn(() => range),
    setVisibleLogicalRange: vi.fn(),
    setVisibleRange: vi.fn(),
    fitContent: vi.fn(),
  };
  return { chart: { timeScale: () => timeScale } as unknown as IChartApi, timeScale };
}

describe('createNavigator', () => {
  it('applies each move to the visible logical range', () => {
    const { chart, timeScale } = fakeChart();
    const nav = createNavigator(
      chart,
      () => 100,
      () => undefined,
    );
    nav.zoomIn();
    expect(timeScale.setVisibleLogicalRange).toHaveBeenLastCalledWith(
      zoomRange({ from: 40, to: 60 }, 1 / ZOOM_STEP, bounds),
    );
    nav.zoomOut();
    expect(timeScale.setVisibleLogicalRange).toHaveBeenLastCalledWith(
      zoomRange({ from: 40, to: 60 }, ZOOM_STEP, bounds),
    );
    nav.panLeft();
    expect(timeScale.setVisibleLogicalRange).toHaveBeenLastCalledWith({ from: 35, to: 55 });
    nav.panRight();
    expect(timeScale.setVisibleLogicalRange).toHaveBeenLastCalledWith({ from: 45, to: 65 });
  });

  it('does nothing without data or a visible range', () => {
    const empty = fakeChart();
    createNavigator(
      empty.chart,
      () => 0,
      () => undefined,
    ).zoomIn();
    expect(empty.timeScale.setVisibleLogicalRange).not.toHaveBeenCalled();
    const none = fakeChart(null);
    createNavigator(
      none.chart,
      () => 100,
      () => undefined,
    ).panLeft();
    expect(none.timeScale.setVisibleLogicalRange).not.toHaveBeenCalled();
  });

  it('resets to the chosen range, or fits the content when there is none', () => {
    const { chart, timeScale } = fakeChart();
    const view = { from: '2026-04-01', to: '2026-10-01' };
    createNavigator(
      chart,
      () => 100,
      () => view,
    ).reset();
    expect(timeScale.setVisibleRange).toHaveBeenCalledWith(view);
    createNavigator(
      chart,
      () => 100,
      () => undefined,
    ).reset();
    expect(timeScale.fitContent).toHaveBeenCalledTimes(1);
  });
});

const key = (k: string, extra: Partial<Parameters<typeof navKeyAction>[0]> = {}) => ({
  key: k,
  shiftKey: false,
  ctrlKey: false,
  metaKey: false,
  altKey: false,
  ...extra,
});

describe('navKeyAction', () => {
  it('maps zoom and reset keys', () => {
    expect(navKeyAction(key('+'))).toBe('zoomIn');
    expect(navKeyAction(key('='))).toBe('zoomIn');
    expect(navKeyAction(key('-'))).toBe('zoomOut');
    expect(navKeyAction(key('0'))).toBe('reset');
  });

  it('pans on Shift+arrow and leaves plain arrows to the bar cursor', () => {
    expect(navKeyAction(key('ArrowLeft', { shiftKey: true }))).toBe('panLeft');
    expect(navKeyAction(key('ArrowRight', { shiftKey: true }))).toBe('panRight');
    expect(navKeyAction(key('ArrowLeft'))).toBeNull();
  });

  it('leaves browser shortcuts alone', () => {
    expect(navKeyAction(key('=', { ctrlKey: true }))).toBeNull();
    expect(navKeyAction(key('0', { metaKey: true }))).toBeNull();
    expect(navKeyAction(key('a'))).toBeNull();
  });
});

describe('handleNavKey', () => {
  const nav = {
    zoomIn: vi.fn(),
    zoomOut: vi.fn(),
    panLeft: vi.fn(),
    panRight: vi.fn(),
    reset: vi.fn(),
  };

  it('runs the action and keeps the key from reaching the page', () => {
    const e = { ...key('+'), preventDefault: vi.fn(), stopPropagation: vi.fn() };
    expect(handleNavKey(e, nav)).toBe(true);
    expect(nav.zoomIn).toHaveBeenCalledTimes(1);
    expect(e.preventDefault).toHaveBeenCalled();
    expect(e.stopPropagation).toHaveBeenCalled();
  });

  it('ignores other keys and a missing chart', () => {
    const other = { ...key('x'), preventDefault: vi.fn(), stopPropagation: vi.fn() };
    expect(handleNavKey(other, nav)).toBe(false);
    expect(other.preventDefault).not.toHaveBeenCalled();
    const zoom = { ...key('-'), preventDefault: vi.fn(), stopPropagation: vi.fn() };
    expect(handleNavKey(zoom, null)).toBe(false);
  });
});
