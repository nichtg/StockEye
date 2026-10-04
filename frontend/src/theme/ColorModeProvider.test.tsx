import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { stubSystemColorScheme } from '../test/render';
import { COLOR_MODE_STORAGE_KEY, ColorModeProvider } from './ColorModeProvider';
import { useColorMode } from './colorModeContext';

function Probe() {
  const { mode, toggle } = useColorMode();
  return (
    <button type="button" onClick={toggle}>
      mode: {mode}
    </button>
  );
}

const renderProbe = () =>
  render(
    <ColorModeProvider>
      <Probe />
    </ColorModeProvider>,
  );

describe('ColorModeProvider', () => {
  it('follows the system colour scheme by default', () => {
    stubSystemColorScheme('dark');
    renderProbe();
    expect(screen.getByRole('button')).toHaveTextContent('mode: dark');
  });

  it('toggles and persists the choice', async () => {
    stubSystemColorScheme('light');
    const user = userEvent.setup();
    renderProbe();
    expect(screen.getByRole('button')).toHaveTextContent('mode: light');

    await user.click(screen.getByRole('button'));
    expect(screen.getByRole('button')).toHaveTextContent('mode: dark');
    expect(localStorage.getItem(COLOR_MODE_STORAGE_KEY)).toBe('dark');
  });

  it('prefers a stored choice over the system setting', () => {
    stubSystemColorScheme('dark');
    localStorage.setItem(COLOR_MODE_STORAGE_KEY, 'light');
    renderProbe();
    expect(screen.getByRole('button')).toHaveTextContent('mode: light');
  });

  it('still works when storage throws', async () => {
    stubSystemColorScheme('light');
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('blocked');
    });
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('blocked');
    });
    const user = userEvent.setup();
    renderProbe();
    await user.click(screen.getByRole('button'));
    expect(screen.getByRole('button')).toHaveTextContent('mode: dark');
  });
});
