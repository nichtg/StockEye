import { act, renderHook } from '@testing-library/react';
import type { ReactNode } from 'react';
import { MemoryRouter, useLocation, useNavigate } from 'react-router';
import { INDICATORS_STORAGE_KEY } from './indicators';
import { useChartSettings } from './useChartSettings';

function setup(route = '/stock/AAPL') {
  const wrapper = ({ children }: { children: ReactNode }) => (
    <MemoryRouter initialEntries={[route]}>{children}</MemoryRouter>
  );
  return renderHook(
    () => ({ settings: useChartSettings(), location: useLocation(), navigate: useNavigate() }),
    {
      wrapper,
    },
  );
}

describe('useChartSettings', () => {
  it('reads range and indicators from the URL', () => {
    const { result } = setup('/stock/AAPL?range=1Y&ind=vwap,sma50');
    expect(result.current.settings.range).toBe('1Y');
    expect(result.current.settings.selection).toEqual(['vwap', 'sma50']);
  });

  it('falls back to 6M, the remembered indicators and ignores junk', () => {
    localStorage.setItem(INDICATORS_STORAGE_KEY, '["rsi"]');
    const { result } = setup('/stock/AAPL?range=10Y');
    expect(result.current.settings.range).toBe('6M');
    expect(result.current.settings.selection).toEqual(['rsi']);
    expect(setup('/stock/AAPL?ind=bogus,ema9').result.current.settings.selection).toEqual(['ema9']);
  });

  it('writes toggles to the URL and storage, keeping the tab param', () => {
    const { result } = setup('/stock/AAPL?tab=macro&ind=sma50');
    act(() => {
      result.current.settings.toggleIndicator('vwap');
    });
    const search = new URLSearchParams(result.current.location.search);
    expect(search.get('ind')).toBe('vwap,sma50');
    expect(search.get('tab')).toBe('macro');
    expect(localStorage.getItem(INDICATORS_STORAGE_KEY)).toBe('["vwap","sma50"]');

    act(() => {
      result.current.settings.setRange('1M');
    });
    expect(new URLSearchParams(result.current.location.search).get('range')).toBe('1M');
    expect(result.current.settings.range).toBe('1M');
  });

  it('restores the remembered indicators when navigating to another symbol without ind', () => {
    const { result } = setup('/stock/AAPL?ind=sma50');
    act(() => {
      result.current.settings.toggleIndicator('rsi');
    });
    expect(result.current.settings.selection).toEqual(['sma50', 'rsi']);
    localStorage.setItem(INDICATORS_STORAGE_KEY, '["ema9"]');
    act(() => {
      void result.current.navigate('/stock/MSFT');
    });
    expect(result.current.settings.selection).toEqual(['ema9']);
  });

  it('keeps both of two toggles made before a re-render', () => {
    const { result } = setup('/stock/AAPL?ind=sma50');
    act(() => {
      result.current.settings.toggleIndicator('vwap');
      result.current.settings.toggleIndicator('rsi');
    });
    expect(result.current.settings.selection).toEqual(['vwap', 'sma50', 'rsi']);
  });

  it('toggles markers relative to the range default', () => {
    const { result } = setup('/stock/AAPL?range=6M');
    expect(result.current.settings.shownMarkers).not.toContain('pattern');
    act(() => {
      result.current.settings.toggleMarker('pattern');
    });
    expect(result.current.settings.shownMarkers).toContain('pattern');
    act(() => {
      result.current.settings.toggleMarker('earnings');
    });
    expect(result.current.settings.shownMarkers).not.toContain('earnings');
  });
});
