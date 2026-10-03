import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { GLOSSARY, TERM_IDS } from '../glossary';
import { renderApp } from '../test/render';
import { Term } from './Term';

describe('Term', () => {
  it('renders a labelled help button next to the text', () => {
    renderApp(<Term id="rsi">RSI</Term>);
    expect(screen.getByText('RSI')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'What is RSI?' })).toBeInTheDocument();
  });

  it('opens the explanation on keyboard focus and closes it on Escape', async () => {
    const user = userEvent.setup();
    renderApp(<Term id="rsi">RSI</Term>);

    await user.tab();
    expect(screen.getByRole('button', { name: 'What is RSI?' })).toHaveFocus();
    const tip = await screen.findByRole('tooltip');
    expect(tip).toHaveTextContent(GLOSSARY.rsi.body);

    await user.keyboard('{Escape}');
    await waitFor(() => {
      expect(screen.queryByRole('tooltip')).not.toBeInTheDocument();
    });
  });

  it('opens on hover', async () => {
    const user = userEvent.setup();
    renderApp(<Term id="vwap">VWAP</Term>);
    await user.hover(screen.getByRole('button', { name: 'What is VWAP?' }));
    expect(await screen.findByRole('tooltip')).toHaveTextContent(GLOSSARY.vwap.title);
  });

  it('has a short plain-English entry for every term', () => {
    for (const id of TERM_IDS) {
      const { title, body } = GLOSSARY[id];
      expect(title.length).toBeGreaterThan(0);
      expect(body.split(/\s+/).length).toBeLessThanOrEqual(45);
    }
  });
});
