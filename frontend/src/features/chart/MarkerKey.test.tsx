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
    expect(screen.getByRole('button', { name: /^News\s*14$/ })).toBeEnabled();
    expect(screen.getByRole('button', { name: /^Earnings\s*3$/ })).toBeEnabled();
  });

  it('disables a kind with none in range and says why', async () => {
    const user = userEvent.setup();
    renderApp(<MarkerKey shown={['dividend']} counts={counts} onToggle={() => undefined} />);

    const dividends = screen.getByRole('button', { name: /^Dividends\s*0$/ });
    expect(dividends).toBeDisabled();
    expect(dividends).toHaveAttribute('aria-pressed', 'false');

    await user.hover(dividends.parentElement!);
    expect(await screen.findByText('No dividends in this range')).toBeInTheDocument();
  });

  it('leaves every kind usable while the chart has no data yet', () => {
    renderApp(<MarkerKey shown={[]} counts={undefined} onToggle={() => undefined} />);
    expect(screen.getByRole('button', { name: 'Dividends' })).toBeEnabled();
  });
});
