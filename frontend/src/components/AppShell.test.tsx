import { act, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Route, Routes } from 'react-router';
import { stubFetch } from '../test/mockApi';
import { renderApp } from '../test/render';
import { AppShell } from './AppShell';

/** jsdom has no layout: this answers every `max-width` query (the phone breakpoint) with `phone`. */
function stubViewport(phone: boolean) {
  vi.stubGlobal(
    'matchMedia',
    (query: string): MediaQueryList =>
      ({
        matches: query.includes('max-width') ? phone : false,
        media: query,
        addEventListener: () => undefined,
        removeEventListener: () => undefined,
        addListener: () => undefined,
        removeListener: () => undefined,
        dispatchEvent: () => false,
        onchange: null,
      }) as MediaQueryList,
  );
}

function renderShell(route: string, role: 'user' | 'admin' = 'user') {
  stubFetch((req) =>
    req.path === '/me' ? { body: { id: '1', email: 'a@b.co', role, status: 'active' } } : undefined,
  );
  renderApp(
    <Routes>
      <Route element={<AppShell />}>
        <Route index element={<p>home</p>} />
        <Route path="/discover" element={<p>discover</p>} />
      </Route>
    </Routes>,
    { route },
  );
}

describe('AppShell navigation', () => {
  it('links Watchlist and Discover and marks the current page', async () => {
    stubViewport(false);
    renderShell('/discover');
    const nav = await screen.findByRole('navigation', { name: 'Main', hidden: true });
    const discover = within(nav).getByRole('link', { name: 'Discover', hidden: true });
    expect(discover).toHaveAttribute('href', '/discover');
    expect(discover).toHaveAttribute('aria-current', 'page');
    const watchlist = within(nav).getByRole('link', { name: 'Watchlist', hidden: true });
    expect(watchlist).toHaveAttribute('href', '/');
    expect(watchlist).not.toHaveAttribute('aria-current');
  });

  it('gives the active link the same font weight as an inactive one, so the row does not shift', async () => {
    stubViewport(false);
    renderShell('/discover');
    const nav = await screen.findByRole('navigation', { name: 'Main', hidden: true });
    const active = within(nav).getByRole('link', { name: 'Discover', hidden: true });
    const idle = within(nav).getByRole('link', { name: 'Watchlist', hidden: true });
    expect(active).toHaveAttribute('aria-current', 'page');
    // jsdom does not cascade emotion's rules, so read them: both links share one sx class, which sets
    // weight 500 once and never again for the [aria-current] state.
    const sxClass = (el: Element) => [...el.classList].find((c) => /^css-.*-MuiLink-root$/.test(c));
    expect(sxClass(active)).toBe(sxClass(idle));
    const css = [...document.querySelectorAll('style')].map((st) => st.textContent).join('');
    const pattern = new RegExp(String.raw`.${sxClass(active) ?? ''}([^{]*){([^}]*)}`, 'g');
    const weights = [...css.matchAll(pattern)].flatMap(([, selector, body]) =>
      [...(body ?? '').matchAll(/font-weight:(\d+)/g)].map((m) => [selector, m[1]]),
    );
    expect(weights).toEqual([['', '500']]);
  });

  it('keeps the links out of the account menu on a wide screen, so the arrow keys reach Log out', async () => {
    stubViewport(false);
    const user = userEvent.setup();
    renderShell('/', 'admin');
    await user.click(await screen.findByRole('button', { name: 'Account menu' }));
    const menu = await screen.findByRole('menu');
    expect(within(menu).queryByRole('menuitem', { name: 'Discover' })).toBeNull();
    expect(within(menu).queryByRole('menuitem', { name: 'Watchlist' })).toBeNull();
    // Walk the menu with the arrow keys: every action must be reachable.
    const first = within(menu).getAllByRole('menuitem')[0];
    expect(first).toHaveTextContent('Admin');
    act(() => {
      first?.focus();
    });
    const visited = new Set<string>(['Admin']);
    for (let i = 0; i < 3; i++) {
      await user.keyboard('{ArrowDown}');
      visited.add(document.activeElement?.textContent ?? '');
    }
    expect(visited).toContain('Admin');
    expect(visited).toContain('Log out');
    expect(visited).toContain('Delete account…');
  });

  it('puts the links in the account menu on a phone', async () => {
    stubViewport(true);
    const user = userEvent.setup();
    renderShell('/');
    await user.click(await screen.findByRole('button', { name: 'Account menu' }));
    const menu = await screen.findByRole('menu');
    expect(within(menu).getByRole('menuitem', { name: 'Discover' })).toHaveAttribute(
      'href',
      '/discover',
    );
    expect(within(menu).getByRole('menuitem', { name: 'Watchlist' })).toHaveAttribute(
      'aria-current',
      'page',
    );
  });
});
