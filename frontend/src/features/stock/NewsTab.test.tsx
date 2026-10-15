import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { NewsProgress } from '../../api/types';
import { articleFixture, articlesPageFixture } from '../../test/fixtures';
import { stubFetch } from '../../test/mockApi';
import { renderApp } from '../../test/render';
import { useLocation } from 'react-router';
import { NewsTab } from './NewsTab';

const idle: NewsProgress = {
  months_done: 6,
  months_total: 6,
  in_progress: false,
  status: { state: 'ok' },
};

function Where() {
  return <output data-testid="search">{useLocation().search}</output>;
}

function show(news: NewsProgress | undefined = idle, route = '/') {
  return renderApp(
    <>
      <NewsTab symbol="AAPL" name="Apple Inc." exchange="US" news={news} />
      <Where />
    </>,
    { route },
  );
}

const MONTHS = [
  { month: '2026-10', label: 'Oct 2026', count: 42 },
  { month: '2026-09', label: 'Sep 2026', count: 1 },
];

/** First page of "All" carries the chips; a month page (and later pages) has none. */
function monthsApi(
  extra?: (req: { search: URLSearchParams }) => ReturnType<typeof articlesPageFixture> | undefined,
) {
  return stubFetch((req) => {
    if (req.path !== '/stocks/AAPL/news/articles') return undefined;
    const month = req.search.get('month');
    const custom = extra?.(req);
    if (custom) return { body: custom };
    if (month) {
      return {
        body: articlesPageFixture([
          articleFixture({ title: `Month ${month}`, url: `https://example.com/${month}` }),
        ]),
      };
    }
    return { body: articlesPageFixture([articleFixture({ title: 'All news' })], null, MONTHS) };
  });
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
    const first = screen.getByRole('region', { name: 'Sat, Oct 3, 2026' });
    expect(within(first).getAllByRole('listitem')).toHaveLength(2);
    expect(within(first).getByText('Negative')).toBeInTheDocument();
    expect(within(first).getByText('Positive')).toBeInTheDocument();
    const second = screen.getByRole('region', { name: 'Thu, Oct 1, 2026' });
    expect(within(second).getByText('Neutral')).toBeInTheDocument();
    expect(within(second).getByText('Not scored yet')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'What is a sentiment label?' })).toBeVisible();

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

  it('does not claim there is no news while an empty page still has a cursor', async () => {
    const seen = stubFetch((req) => {
      if (req.path !== '/stocks/AAPL/news/articles') return undefined;
      return req.search.get('before') === 'c1'
        ? { body: articlesPageFixture([articleFixture({ title: 'Found later' })]) }
        : { body: articlesPageFixture([], 'c1') };
    });
    show();
    expect(await screen.findByText('Found later')).toBeInTheDocument();
    expect(screen.queryByText('No news found for the past 6 months yet.')).not.toBeInTheDocument();
    expect(seen.filter((r) => r.path.endsWith('/articles'))).toHaveLength(2);
  });

  it('stops auto-fetching after a few empty pages and offers Load more', async () => {
    const seen = stubFetch((req) =>
      req.path === '/stocks/AAPL/news/articles'
        ? { body: articlesPageFixture([], 'again') }
        : undefined,
    );
    show();
    expect(await screen.findByRole('button', { name: 'Load more' })).toBeInTheDocument();
    await vi.waitFor(() => {
      expect(seen.filter((r) => r.path.endsWith('/articles'))).toHaveLength(4);
    });
    expect(screen.queryByText('No news found for the past 6 months yet.')).not.toBeInTheDocument();
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

  describe('month chips', () => {
    it('renders from months with article counts and loads one month', async () => {
      const user = userEvent.setup();
      const seen = monthsApi();
      show();
      await screen.findByText('All news');
      const group = screen.getByRole('radiogroup', { name: 'Filter by month' });
      expect(within(group).getByRole('radio', { name: 'All months' })).toBeChecked();
      expect(within(group).getByRole('radio', { name: 'October 2026, 42 articles' })).toBeVisible();
      expect(within(group).getByRole('radio', { name: 'September 2026, 1 article' })).toBeVisible();

      await user.click(within(group).getByRole('radio', { name: 'October 2026, 42 articles' }));
      expect(await screen.findByText('Month 2026-10')).toBeInTheDocument();
      expect(screen.getByTestId('search')).toHaveTextContent('?month=2026-10');
      expect(seen.at(-1)?.search.get('month')).toBe('2026-10');
      expect(
        screen.getByText(/News about Apple Inc. in October 2026, newest first./),
      ).toBeVisible();
      expect(screen.getByRole('radio', { name: 'October 2026, 42 articles' })).toBeChecked();

      await user.click(screen.getByRole('radio', { name: 'All months' }));
      expect(await screen.findByText('All news')).toBeInTheDocument();
      expect(screen.getByTestId('search')).toHaveTextContent('');
      expect(screen.getByTestId('search').textContent).toBe('');
    });

    it('starts from a month in the URL, and falls back to All for an unknown one', async () => {
      const seen = monthsApi();
      const first = show(idle, '/?tab=news&month=2026-09');
      expect(await screen.findByText('Month 2026-09')).toBeInTheDocument();
      expect(screen.getByRole('radio', { name: 'September 2026, 1 article' })).toBeChecked();
      first.unmount();

      seen.length = 0;
      show(idle, '/?month=1999-01');
      expect(await screen.findByText('All news')).toBeInTheDocument();
      expect(screen.getByRole('radio', { name: 'All months' })).toBeChecked();
      expect(seen.some((r) => r.search.has('month'))).toBe(false);
    });

    it('keeps the chip row on the second page of a month', async () => {
      const user = userEvent.setup();
      monthsApi((req) =>
        req.search.get('before') === 'c2'
          ? articlesPageFixture([
              articleFixture({ title: 'Month page two', url: 'https://example.com/p2' }),
            ])
          : req.search.get('month')
            ? articlesPageFixture([articleFixture({ title: 'Month page one' })], 'c2')
            : undefined,
      );
      show(idle, '/?month=2026-10');
      await screen.findByText('Month page one');
      await user.click(screen.getByRole('button', { name: 'Load more' }));
      expect(await screen.findByText('Month page two')).toBeInTheDocument();
      expect(screen.getByRole('radio', { name: 'October 2026, 42 articles' })).toBeChecked();
      expect(screen.getByRole('radio', { name: 'All months' })).toBeVisible();
    });
  });

  describe('grouped stories', () => {
    it('expands and collapses the similar stories as links', async () => {
      const user = userEvent.setup();
      stubFetch((req) =>
        req.path === '/stocks/AAPL/news/articles'
          ? {
              body: articlesPageFixture([
                articleFixture({
                  title: 'Main story',
                  similar: [
                    {
                      title: 'Same story, outlet B',
                      url: 'https://example.com/b',
                      source: 'B',
                      published_at: '2026-10-03T16:00:00Z',
                    },
                    {
                      title: 'Same story, outlet C',
                      url: 'https://example.com/c',
                      source: 'C',
                      published_at: '2026-10-03T17:00:00Z',
                    },
                  ],
                }),
              ]),
            }
          : undefined,
      );
      show();
      const button = await screen.findByRole('button', { name: '+2 similar stories' });
      expect(button).toHaveAttribute('aria-expanded', 'false');
      expect(screen.queryByRole('link', { name: 'Same story, outlet B' })).not.toBeInTheDocument();
      expect(screen.getByRole('button', { name: 'What is grouped stories?' })).toBeVisible();

      await user.click(button);
      expect(button).toHaveAttribute('aria-expanded', 'true');
      const link = screen.getByRole('link', { name: 'Same story, outlet B' });
      expect(link).toHaveAttribute('href', 'https://example.com/b');
      expect(link).toHaveAttribute('rel', 'noopener noreferrer');

      await user.click(button);
      expect(button).toHaveAttribute('aria-expanded', 'false');
      expect(screen.queryByRole('link', { name: 'Same story, outlet B' })).not.toBeInTheDocument();
    });
  });
});
