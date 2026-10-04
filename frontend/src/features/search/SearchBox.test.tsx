import { act, fireEvent, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Route, Routes, useLocation } from 'react-router';
import { stubFetch } from '../../test/mockApi';
import { renderApp } from '../../test/render';
import { SEARCH_DEBOUNCE_MS } from './focusSearch';
import { SearchBox } from './SearchBox';

function Where() {
  return <div data-testid="where">{useLocation().pathname}</div>;
}

function setup() {
  return renderApp(
    <>
      <SearchBox />
      <Routes>
        <Route path="*" element={<Where />} />
      </Routes>
    </>,
  );
}

const matches = [
  { symbol: 'D05.SI', name: 'DBS Group Holdings Ltd', exchange: 'SGX' },
  { symbol: 'DBSDF', name: 'DBS Group (OTC)', exchange: 'US' },
];

describe('SearchBox', () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it('searches after a pause, lists symbol, name and exchange, and Enter opens the stock', async () => {
    const seen = stubFetch((req) => {
      if (req.path === '/stocks/search') return { body: matches };
      return undefined;
    });
    // Fake timers make the debounce deterministic: on real timers a slow keystroke under load can
    // outlast the 250 ms window and fire an extra request. (user-event stalls on RTL's own
    // setTimeout under vitest fake timers, so the keystrokes are fired as change events.)
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });
    setup();
    const input = screen.getByRole('combobox', { name: 'Search for a stock' });
    act(() => {
      input.focus();
    });
    for (const text of ['d', 'db', 'dbs']) {
      fireEvent.change(input, { target: { value: text } });
      act(() => {
        vi.advanceTimersByTime(SEARCH_DEBOUNCE_MS - 1);
      });
    }
    expect(seen.filter((r) => r.path === '/stocks/search')).toHaveLength(0);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1); // the debounce fires and the request goes out
    });
    // Let the response settle: React Query notifies through setTimeout, so keep ticking the clock.
    await vi.waitFor(async () => {
      await act(async () => {
        await vi.advanceTimersByTimeAsync(10);
      });
      expect(screen.getAllByRole('option')).toHaveLength(2);
    });
    vi.useRealTimers();
    const user = userEvent.setup();
    const first = await screen.findByRole('option', { name: /D05\.SI/ });
    expect(first).toHaveTextContent('DBS Group Holdings Ltd');
    expect(first).toHaveTextContent('SGX');
    // Debounced: typing three characters produced one request, for the full text.
    const searches = seen.filter((r) => r.path === '/stocks/search');
    expect(searches).toHaveLength(1);
    expect(searches[0]?.search.get('q')).toBe('dbs');

    await user.keyboard('{Enter}');
    await waitFor(() => {
      expect(screen.getByTestId('where')).toHaveTextContent('/stock/D05.SI');
    });
  });

  it('focuses with Ctrl+K', async () => {
    stubFetch(() => undefined);
    const user = userEvent.setup();
    setup();
    await user.keyboard('{Control>}k{/Control}');
    expect(screen.getByRole('combobox', { name: 'Search for a stock' })).toHaveFocus();
  });

  it('says so when nothing matches', async () => {
    stubFetch((req) => (req.path === '/stocks/search' ? { body: [] } : undefined));
    const user = userEvent.setup();
    setup();
    await user.type(screen.getByRole('combobox', { name: 'Search for a stock' }), 'zzzz');
    expect(await screen.findByText(/No US or SGX stocks match “zzzz”/)).toBeInTheDocument();
  });

  it('shows an inline error when the search fails', async () => {
    stubFetch((req) =>
      req.path === '/stocks/search'
        ? { status: 500, body: { error: { code: 'x', message: 'boom', request_id: '' } } }
        : undefined,
    );
    const user = userEvent.setup();
    setup();
    await user.type(screen.getByRole('combobox', { name: 'Search for a stock' }), 'dbs');
    expect(await screen.findByRole('alert')).toHaveTextContent(/something went wrong on our side/i);
  });
});
