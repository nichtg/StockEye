import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Link, Route, Routes } from 'react-router';
import { renderApp } from '../test/render';
import { useNotice } from './useNotice';

function Source() {
  const showNotice = useNotice();
  return (
    <>
      <button
        type="button"
        onClick={() => {
          showNotice('First', { label: 'Undo first', onClick: () => undefined });
        }}
      >
        Show first
      </button>
      <button
        type="button"
        onClick={() => {
          showNotice('Second', { label: 'Undo second', onClick: () => undefined });
        }}
      >
        Show second
      </button>
      <button
        type="button"
        onClick={() => {
          showNotice('First', { label: 'Undo first', onClick: () => undefined });
          showNotice('Second', { label: 'Undo second', onClick: () => undefined });
        }}
      >
        Show both
      </button>
      <Link to="/elsewhere">Leave</Link>
    </>
  );
}

function renderRoutes() {
  renderApp(
    <Routes>
      <Route path="/" element={<Source />} />
      <Route path="/elsewhere" element={<p>Elsewhere</p>} />
    </Routes>,
  );
}

describe('notice host', () => {
  it('keeps a toast on screen after the page that raised it is gone', async () => {
    const user = userEvent.setup();
    renderRoutes();
    await user.click(screen.getByRole('button', { name: 'Show first' }));
    await user.click(screen.getByRole('link', { name: 'Leave' }));
    expect(await screen.findByText('Elsewhere')).toBeInTheDocument();
    expect(screen.getByText('First')).toBeInTheDocument();
  });

  it('makes a notice on screen give way to the next', async () => {
    const user = userEvent.setup();
    renderRoutes();
    await user.click(screen.getByRole('button', { name: 'Show first' }));
    expect(await screen.findByRole('button', { name: 'Undo first' })).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Show second' }));
    expect(await screen.findByRole('button', { name: 'Undo second' })).toBeInTheDocument();
    expect(screen.queryByText('First')).not.toBeInTheDocument();
  });

  it('makes the current notice give way at once, then shows the next in full', async () => {
    const user = userEvent.setup();
    renderRoutes();
    await user.click(screen.getByRole('button', { name: 'Show both' }));
    expect(await screen.findByRole('button', { name: 'Undo second' })).toBeInTheDocument();
    expect(screen.queryByText('First')).not.toBeInTheDocument();
  });
});
