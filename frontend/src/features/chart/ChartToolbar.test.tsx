import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { renderApp } from '../../test/render';
import { ChartToolbar } from './ChartToolbar';
import { INDICATORS, vwapVariant } from './indicators';
import type { RangeKey } from '../../api/types';

function setup(range: RangeKey = '6M') {
  renderApp(
    <ChartToolbar
      range={range}
      onRangeChange={() => undefined}
      selection={[]}
      onToggleIndicator={() => undefined}
    />,
  );
}

/** Presses Tab until the element has focus, as a keyboard user would. */
async function tabTo(user: ReturnType<typeof userEvent.setup>, el: HTMLElement) {
  for (let i = 0; i < 30 && document.activeElement !== el; i += 1) await user.tab();
  expect(el).toHaveFocus();
}

describe('ChartToolbar indicator hints', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  /** jsdom reports :focus-visible as false after a keyboard focus; browsers report true. */
  function stubFocusVisible() {
    // Called back with the element as `this` below, so the unbound reference is safe.
    // eslint-disable-next-line @typescript-eslint/unbound-method
    const matches = Element.prototype.matches;
    vi.spyOn(Element.prototype, 'matches').mockImplementation(function (
      this: Element,
      sel: string,
    ) {
      return sel === ':focus-visible' ? true : matches.call(this, sel);
    });
  }

  it.each(INDICATORS.map((i) => [i.label, i] as const))(
    'shows the %s hint on hover',
    async (_label, ind) => {
      const user = userEvent.setup();
      setup();
      await user.hover(screen.getByRole('button', { name: ind.label }));
      expect(await screen.findByRole('tooltip')).toHaveTextContent(ind.hint('6M'));
    },
  );

  it.each(INDICATORS.map((i) => [i.label, i] as const))(
    'shows the %s hint on keyboard focus',
    async (_label, ind) => {
      stubFocusVisible();
      const user = userEvent.setup();
      setup();
      const chip = screen.getByRole('button', { name: ind.label });
      await tabTo(user, chip);
      // Tabbing past earlier chips can leave their tooltips fading out, so look for ours among them.
      await waitFor(() => {
        const texts = screen.queryAllByRole('tooltip').map((t) => t.textContent);
        expect(texts).toContain(ind.hint('6M'));
      });
    },
  );

  it('gives every indicator a non-empty hint', () => {
    for (const ind of INDICATORS) expect(ind.hint('6M').length).toBeGreaterThan(10);
  });

  it('changes the VWAP hint between 1W and 6M', async () => {
    const user = userEvent.setup();
    const short = vwapVariant('1W').hint;
    const long = vwapVariant('6M').hint;
    expect(short).not.toBe(long);
    setup('1W');
    await user.hover(screen.getByRole('button', { name: 'VWAP' }));
    expect(await screen.findByRole('tooltip')).toHaveTextContent(short);
    await user.unhover(screen.getByRole('button', { name: 'VWAP' }));
    await waitFor(() => {
      expect(screen.queryByRole('tooltip')).not.toBeInTheDocument();
    });
  });
});

describe('VWAP hint anchor', () => {
  it('names the start of the chosen range on daily ranges', () => {
    expect(vwapVariant('6M', '3 Apr 2026').hint).toBe(
      'Average price paid since 3 Apr 2026, weighted by volume.',
    );
    expect(vwapVariant('1M', '3 Apr 2026').hint).not.toContain('3 Apr');
  });

  it('shows the date in the toolbar tooltip', async () => {
    const user = userEvent.setup();
    renderApp(
      <ChartToolbar
        range="1Y"
        onRangeChange={() => undefined}
        selection={[]}
        onToggleIndicator={() => undefined}
        visibleFromLabel="3 Oct 2025"
      />,
    );
    await user.hover(screen.getByRole('button', { name: 'VWAP' }));
    expect(await screen.findByRole('tooltip')).toHaveTextContent('since 3 Oct 2025');
  });
});
