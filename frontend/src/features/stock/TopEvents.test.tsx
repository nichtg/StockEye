import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { TopEventOut } from '../../api/types';
import { renderApp } from '../../test/render';
import { TopEvents } from './TopEvents';

function event(date: string, car: number, title: string): TopEventOut {
  return {
    date,
    sentiment: 0,
    article_count: 1,
    car_0_1: car,
    car_0_5: null,
    near_earnings: false,
    headlines: [{ title, url: `https://example.com/${title}`, source: 'Wire' }],
  };
}

// Deliberately in neither order.
const EVENTS = [
  event('2026-03-01', -0.09, 'Middle date, biggest move'),
  event('2026-05-01', 0.02, 'Newest date, smallest move'),
  event('2026-01-01', 0.05, 'Oldest date, middle move'),
];

function titles() {
  return within(screen.getByRole('list'))
    .getAllByRole('link')
    .map((a) => a.textContent);
}

describe('TopEvents', () => {
  it('lists the newest day first, and re-orders the same events by move size on request', async () => {
    const user = userEvent.setup();
    renderApp(<TopEvents events={EVENTS} exchange="US" />);

    const group = screen.getByRole('group', { name: 'Order of the biggest news days' });
    expect(within(group).getByRole('button', { name: 'Newest' })).toHaveAttribute(
      'aria-pressed',
      'true',
    );
    expect(titles()).toEqual([
      'Newest date, smallest move',
      'Middle date, biggest move',
      'Oldest date, middle move',
    ]);

    await user.click(within(group).getByRole('button', { name: 'Biggest move' }));
    expect(titles()).toEqual([
      'Middle date, biggest move',
      'Oldest date, middle move',
      'Newest date, smallest move',
    ]);

    // Selecting the active option again keeps it selected.
    await user.click(within(group).getByRole('button', { name: 'Biggest move' }));
    expect(within(group).getByRole('button', { name: 'Biggest move' })).toHaveAttribute(
      'aria-pressed',
      'true',
    );
  });

  it('tags only the days near an earnings release, and explains the tag', () => {
    renderApp(
      <TopEvents
        events={[
          { ...event('2026-05-01', 0.02, 'Near results'), near_earnings: true },
          event('2026-03-01', 0.05, 'Ordinary day'),
        ]}
        exchange="US"
      />,
    );
    const tags = screen.getAllByText('Earnings');
    expect(tags).toHaveLength(1);
    expect(tags[0]?.closest('li')).toHaveTextContent('Near results');
    expect(screen.getAllByRole('button', { name: 'What is Earnings tag?' })).toHaveLength(1);
  });
});
