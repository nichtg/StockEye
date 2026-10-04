import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { renderApp } from '../../test/render';
import { MarkerKey } from './MarkerKey';

const counts = { earnings: 3, dividend: 0, split: 0, pattern: 2, news: 14 };

describe('MarkerKey', () => {
  it('shows how many markers of each kind are in range', () => {
    renderApp(
      <MarkerKey shown={['earnings', 'news']} counts={counts} onToggle={() => undefined} />,
    );
    expect(screen.getByRole('button', { name: 'News, 14 in this range' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Earnings, 3 in this range' })).toBeInTheDocument();
  });

  it('dims a kind with none in range, keeps it focusable and says why', async () => {
    const user = userEvent.setup();
    const onToggle = vi.fn();
    renderApp(<MarkerKey shown={['dividend']} counts={counts} onToggle={onToggle} />);

    const dividends = screen.getByRole('button', { name: 'Dividends, 0 in this range' });
    expect(dividends).toHaveAttribute('aria-disabled', 'true');
    expect(dividends).toHaveAttribute('aria-pressed', 'false');

    // Keyboard users can reach it by tabbing.
    while (document.activeElement !== dividends) await user.tab();
    await user.hover(dividends);
    expect(await screen.findByText('No dividends in this range')).toBeInTheDocument();
    await user.click(dividends);
    expect(onToggle).not.toHaveBeenCalled();
  });

  it('leaves every kind usable while the chart has no data yet', () => {
    renderApp(<MarkerKey shown={[]} counts={undefined} onToggle={() => undefined} />);
    expect(screen.getByRole('button', { name: 'Dividends' })).toBeEnabled();
  });
});
