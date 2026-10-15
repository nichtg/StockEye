import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { renderApp } from '../../test/render';
import { ChartNav } from './ChartNav';

const navigator = () => ({
  zoomIn: vi.fn(),
  zoomOut: vi.fn(),
  panLeft: vi.fn(),
  panRight: vi.fn(),
  reset: vi.fn(),
});

describe('ChartNav', () => {
  it('has a labelled group and a labelled button for each move', () => {
    renderApp(<ChartNav nav={navigator()} range="1Y" />);
    expect(screen.getByRole('group', { name: 'Chart navigation' })).toBeInTheDocument();
    for (const name of ['Zoom in', 'Zoom out', 'Pan left', 'Pan right', 'Reset to 1Y view']) {
      expect(screen.getByRole('button', { name })).toBeInTheDocument();
    }
  });

  it('calls the matching action on each click', async () => {
    const user = userEvent.setup();
    const nav = navigator();
    renderApp(<ChartNav nav={nav} range="6M" />);
    await user.click(screen.getByRole('button', { name: 'Zoom in' }));
    await user.click(screen.getByRole('button', { name: 'Zoom out' }));
    await user.click(screen.getByRole('button', { name: 'Pan left' }));
    await user.click(screen.getByRole('button', { name: 'Pan right' }));
    await user.click(screen.getByRole('button', { name: 'Reset to 6M view' }));
    for (const fn of Object.values(nav)) expect(fn).toHaveBeenCalledTimes(1);
  });

  it('disables the buttons while there is no chart', () => {
    renderApp(<ChartNav nav={null} range="6M" />);
    expect(screen.getByRole('button', { name: 'Zoom in' })).toBeDisabled();
  });

  it('shows the label as a tooltip on hover', async () => {
    const user = userEvent.setup();
    renderApp(<ChartNav nav={navigator()} range="6M" />);
    await user.hover(screen.getByRole('button', { name: 'Pan left' }));
    expect(await screen.findByRole('tooltip')).toHaveTextContent('Pan left');
  });
});
