import { describe, expect, it } from 'vitest';
import { frameGate } from './frameGate';

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
});
