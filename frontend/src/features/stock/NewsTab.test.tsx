import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { NewsProgress } from '../../api/types';
import { articleFixture, articlesPageFixture } from '../../test/fixtures';
import { stubFetch } from '../../test/mockApi';
import { renderApp } from '../../test/render';
import { NewsTab } from './NewsTab';

const idle: NewsProgress = {
  months_done: 6,
  months_total: 6,
  in_progress: false,
  status: { state: 'ok' },
};

function show(news: NewsProgress | undefined = idle) {
  return renderApp(<NewsTab symbol="AAPL" name="Apple Inc." exchange="US" news={news} />);
}

describe('NewsTab', () => {
  it('groups articles under exchange-local day headings and labels each sentiment', async () => {
    stubFetch((req) =>
      req.path === '/stocks/AAPL/news/articles'
        ? {
            body: articlesPageFixture([
              articleFixture({ published_at: '2026-10-04T02:30:00Z', title: 'Late news' }),
              articleFixture({
                published_at: '2026-10-03T15:00:00Z',
                title: 'Afternoon news',
                url: 'https://example.com/a',
                sentiment_label: 'negative',
              }),
              articleFixture({
                published_at: '2026-10-01T15:00:00Z',
                title: 'Older news',
                url: 'https://example.com/b',
                sentiment_label: 'neutral',
              }),
              articleFixture({
                published_at: '2026-10-01T14:00:00Z',
                title: 'Unscored news',
                url: 'https://example.com/c',
                sentiment_label: 'not_scored',
                sentiment: null,
              }),
            ]),
          }
        : undefined,
    );
    show();

    expect(await screen.findByText(/News about Apple Inc\. from the past 6 months/)).toBeVisible();
    // 02:30 UTC on Oct 4 is still Oct 3 in New York, so it joins the Oct 3 group.
    const headings = screen.getAllByRole('heading', { level: 3 }).map((h) => h.textContent);
    expect(headings).toEqual(['Sat, Oct 3, 2026', 'Thu, Oct 1, 2026']);
    const first = screen.getByRole('region', { name: 'Oct 3, 2026' });
    expect(within(first).getAllByRole('listitem')).toHaveLength(2);
    expect(within(first).getByText('Negative')).toBeInTheDocument();
    expect(within(first).getByText('Positive')).toBeInTheDocument();
    const second = screen.getByRole('region', { name: 'Oct 1, 2026' });
    expect(within(second).getByText('Neutral')).toBeInTheDocument();
    expect(within(second).getByText('Not scored yet')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'What is What the labels mean?' })).toBeVisible();

    const link = screen.getByRole('link', { name: 'Afternoon news' });
    expect(link).toHaveAttribute('href', 'https://example.com/a');
    expect(link).toHaveAttribute('target', '_blank');
    expect(link).toHaveAttribute('rel', 'noopener noreferrer');
  });

  it('loads the next page with the cursor and hides Load more at the end', async () => {
    const user = userEvent.setup();
    const seen = stubFetch((req) => {
      if (req.path !== '/stocks/AAPL/news/articles') return undefined;
      return req.search.get('before') === 'cursor-1'
        ? {
            body: articlesPageFixture([
              articleFixture({ title: 'Second page', url: 'https://example.com/2' }),
            ]),
          }
        : { body: articlesPageFixture([articleFixture({ title: 'First page' })], 'cursor-1') };
    });
    show();
    await screen.findByText('First page');
    expect(seen[0]?.search.get('limit')).toBe('30');
    expect(seen[0]?.search.has('before')).toBe(false);

    await user.click(screen.getByRole('button', { name: 'Load more' }));
    expect(await screen.findByText('Second page')).toBeInTheDocument();
    expect(screen.getByText('First page')).toBeInTheDocument();
    expect(seen.at(-1)?.search.get('before')).toBe('cursor-1');
    expect(screen.queryByRole('button', { name: 'Load more' })).not.toBeInTheDocument();
  });

  it('keeps unique rows even when two articles share a URL', async () => {
    const dupe = { url: 'https://example.com/same', published_at: '2026-10-03T15:00:00Z' };
    stubFetch((req) =>
      req.path === '/stocks/AAPL/news/articles'
        ? {
            body: articlesPageFixture([
              articleFixture({ ...dupe, title: 'Title one' }),
              articleFixture({ ...dupe, title: 'Title two' }),
            ]),
          }
        : undefined,
    );
    const error = vi.spyOn(console, 'error').mockImplementation(() => undefined);
    show();
    await screen.findByText('Title one');
    expect(screen.getByText('Title two')).toBeInTheDocument();
    expect(error).not.toHaveBeenCalled();
    error.mockRestore();
  });

  it('says so when there is no news, and mentions collection when it is running', async () => {
    stubFetch((req) =>
      req.path === '/stocks/AAPL/news/articles' ? { body: articlesPageFixture([]) } : undefined,
    );
    show({ months_done: 2, months_total: 6, in_progress: true, status: { state: 'ok' } });
    expect(await screen.findByText('No news found for the past 6 months yet.')).toBeVisible();
    expect(screen.getByText('Still collecting older news: 2 of 6 months.')).toBeVisible();
  });

  it('shows no collecting line when collection is not running', async () => {
    stubFetch((req) =>
      req.path === '/stocks/AAPL/news/articles'
        ? { body: articlesPageFixture([articleFixture()]) }
        : undefined,
    );
    show();
    await screen.findByText('Apple unveils a new chip');
    expect(screen.queryByText(/Still collecting/)).not.toBeInTheDocument();
  });

  it('shows an error with retry when the first load fails', async () => {
    const user = userEvent.setup();
    let fail = true;
    stubFetch((req) => {
      if (req.path !== '/stocks/AAPL/news/articles') return undefined;
      return fail
        ? { status: 500, body: { error: { code: 'boom', message: 'Server error' } } }
        : { body: articlesPageFixture([articleFixture()]) };
    });
    show();
    expect(await screen.findByRole('alert')).toHaveTextContent('We couldn’t load the news');
    fail = false;
    await user.click(screen.getByRole('button', { name: 'Try again' }));
    expect(await screen.findByText('Apple unveils a new chip')).toBeInTheDocument();
  });

  it('shows the status line when the data is not fully fresh', async () => {
    stubFetch((req) =>
      req.path === '/stocks/AAPL/news/articles'
        ? {
            body: {
              ...articlesPageFixture([articleFixture()]),
              status: { state: 'stale', reason: 'News is 3 hours old.' },
            },
          }
        : undefined,
    );
    show();
    expect(await screen.findByText('News is 3 hours old.')).toBeInTheDocument();
  });
});
