import { describe, expect, it, vi } from 'vitest';
import { frameGate, startIfTopLevel } from './frameGate';

function fakeWindow(framed: boolean) {
  const topLocation = { href: 'https://top.example/' };
  const self = {
    document: { documentElement: { style: { visibility: '' } } },
    location: { href: 'https://app.example/StockEye/' },
    self: undefined as unknown,
    top: undefined as unknown,
  };
  self.self = self;
  self.top = framed ? { location: topLocation } : self;
  return { win: self as unknown as Window, self, topLocation };
}

describe('frameGate', () => {
  it('reveals the page when it is the top-level window', () => {
    const { win, self } = fakeWindow(false);
    frameGate(win);
    expect(self.document.documentElement.style.visibility).toBe('visible');
  });

  it('stays hidden and tries to break out when framed', () => {
    const { win, self, topLocation } = fakeWindow(true);
    frameGate(win);
    expect(self.document.documentElement.style.visibility).toBe('');
    expect(topLocation.href).toBe('https://app.example/StockEye/');
  });

  it('stays hidden when the browser forbids navigating the top window', () => {
    const { win, self } = fakeWindow(true);
    Object.defineProperty(self.top, 'location', {
      get: () => {
        throw new Error('SecurityError');
      },
    });
    expect(() => {
      frameGate(win);
    }).not.toThrow();
    expect(self.document.documentElement.style.visibility).toBe('');
  });

  it('reveals the page in jsdom, which is not framed', () => {
    frameGate();
    expect(document.documentElement.style.visibility).toBe('visible');
    document.documentElement.style.visibility = '';
  });

  it('returns whether the page may run', () => {
    expect(frameGate(fakeWindow(false).win)).toBe(true);
    expect(frameGate(fakeWindow(true).win)).toBe(false);
  });

  it('a framed page neither starts (render, session init) nor calls the API', () => {
    const start = vi.fn();
    const fetchSpy = vi.fn();
    vi.stubGlobal('fetch', fetchSpy);
    expect(startIfTopLevel(start, fakeWindow(true).win)).toBe(false);
    expect(start).not.toHaveBeenCalled();
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it('a top-level page starts', () => {
    const start = vi.fn();
    expect(startIfTopLevel(start, fakeWindow(false).win)).toBe(true);
    expect(start).toHaveBeenCalledTimes(1);
  });
});
