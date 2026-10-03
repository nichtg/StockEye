import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderApp } from '../../test/render';
import { WeeklySentiment } from './WeeklySentiment';

const points = [
  { week_end: '2026-09-12', mean_score: 0.2, article_count: 5 },
  { week_end: '2026-09-19', mean_score: -0.1, article_count: 2 },
  { week_end: '2026-09-26', mean_score: 0.05, article_count: 4 },
];

describe('WeeklySentiment', () => {
  it('lists every week in the hidden table', () => {
    renderApp(<WeeklySentiment points={points} exchange="US" />);
    expect(screen.getAllByRole('row')).toHaveLength(points.length + 1);
    expect(screen.getByRole('cell', { name: 'Sep 12, 2026' })).toBeInTheDocument();
  });

  it('moves between weeks with the arrow keys and shows the active week', async () => {
    const user = userEvent.setup();
    renderApp(<WeeklySentiment points={points} exchange="US" />);
    const slider = screen.getByRole('slider');
    await user.tab();
    expect(slider).toHaveFocus();
    expect(slider).toHaveAttribute('aria-valuenow', '2');
    await user.keyboard('{ArrowLeft}');
    expect(slider).toHaveAttribute('aria-valuenow', '1');
    expect(slider).toHaveAttribute('aria-valuetext', expect.stringContaining('Sep 19, 2026'));
    expect(screen.getByTestId('sentiment-tooltip')).toHaveTextContent('2 articles');
    await user.keyboard('{Home}');
    expect(slider).toHaveAttribute('aria-valuenow', '0');
  });
});
