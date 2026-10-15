import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Route, Routes } from 'react-router';
import { stubFetch } from '../test/mockApi';
import { renderApp } from '../test/render';
import { AppShell } from './AppShell';

function renderShell(route: string) {
  stubFetch((req) =>
    req.path === '/me'
      ? { body: { id: '1', email: 'a@b.co', role: 'user', status: 'active' } }
      : undefined,
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
    renderShell('/discover');
    const nav = await screen.findByRole('navigation', { name: 'Main', hidden: true });
    const discover = within(nav).getByRole('link', { name: 'Discover', hidden: true });
    expect(discover).toHaveAttribute('href', '/discover');
    expect(discover).toHaveAttribute('aria-current', 'page');
    const watchlist = within(nav).getByRole('link', { name: 'Watchlist', hidden: true });
    expect(watchlist).toHaveAttribute('href', '/');
    expect(watchlist).not.toHaveAttribute('aria-current');
  });

  it('marks Watchlist on the home page', async () => {
    renderShell('/');
    const nav = await screen.findByRole('navigation', { name: 'Main', hidden: true });
    expect(within(nav).getByRole('link', { name: 'Watchlist', hidden: true })).toHaveAttribute(
      'aria-current',
      'page',
    );
  });

  it('repeats the links in the account menu for phones', async () => {
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
