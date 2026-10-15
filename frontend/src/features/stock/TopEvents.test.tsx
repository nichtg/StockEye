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
    renderApp(<TopEvents events={EVENTS} since="2026-02-01" exchange="US" />);

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
        since="2026-02-01"
        exchange="US"
      />,
    );
    const tags = screen.getAllByText('Earnings');
    expect(tags).toHaveLength(1);
    expect(tags[0]?.closest('li')).toHaveTextContent('Near results');
    expect(screen.getAllByRole('button', { name: 'What is Earnings tag?' })).toHaveLength(1);
  });

  it('titles the section as the past 3 months and says where the window starts', () => {
    renderApp(<TopEvents events={EVENTS} since="2026-02-01" exchange="US" />);
    expect(
      screen.getByRole('heading', { name: 'Biggest news days, past 3 months' }),
    ).toBeInTheDocument();
    expect(screen.getByText(/News days since Feb 1, 2026./)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'What is the 3-month window?' })).toBeInTheDocument();
  });

  it('keeps the section with a plain empty state and no controls when there are no events', () => {
    renderApp(<TopEvents events={[]} since="2026-02-01" exchange="US" />);
    expect(
      screen.getByRole('heading', { name: 'Biggest news days, past 3 months' }),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        'No news days to show from the past 3 months: none were found, or they are too recent to measure yet.',
      ),
    ).toBeInTheDocument();
    expect(screen.queryByRole('group', { name: 'Order of the biggest news days' })).toBeNull();
    expect(screen.queryByRole('button', { name: /Show all/ })).toBeNull();
  });

  it('makes no claim about the findings above when there are no events', () => {
    // The findings may be missing too (not enough news, or still collecting), so the text must not mention them.
    renderApp(<TopEvents events={[]} since="2026-02-01" exchange="US" />);
    expect(screen.queryByText(/findings/i)).toBeNull();
    expect(screen.queryByText(/2 years/)).toBeNull();
  });

  it('renders without the date when the report predates the window field', () => {
    renderApp(<TopEvents events={EVENTS} exchange="US" />);
    expect(screen.queryByText(/News days since/)).toBeNull();
    expect(
      screen.getByRole('heading', { name: 'Biggest news days, past 3 months' }),
    ).toBeInTheDocument();
    expect(titles()).toHaveLength(3);
  });
});
