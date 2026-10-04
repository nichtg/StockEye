import { fireEvent, screen, waitFor } from '@testing-library/react';
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

  it('toggles on touch tap and closes on an outside tap', async () => {
    renderApp(
      <div>
        <Term id="rsi">RSI</Term>
        <p>elsewhere</p>
      </div>,
    );
    const btn = screen.getByRole('button', { name: 'What is RSI?' });
    fireEvent.pointerDown(btn, { pointerType: 'touch' });
    fireEvent.click(btn);
    expect(await screen.findByRole('tooltip')).toBeInTheDocument();

    fireEvent.pointerDown(btn, { pointerType: 'touch' });
    fireEvent.click(btn);
    await waitFor(() => {
      expect(screen.queryByRole('tooltip')).not.toBeInTheDocument();
    });

    fireEvent.pointerDown(btn, { pointerType: 'touch' });
    fireEvent.click(btn);
    expect(await screen.findByRole('tooltip')).toBeInTheDocument();
    fireEvent.pointerDown(screen.getByText('elsewhere'));
    await waitFor(() => {
      expect(screen.queryByRole('tooltip')).not.toBeInTheDocument();
    });
  });

  it('names the button after multi-word text and works without children', () => {
    renderApp(
      <>
        <Term id="earnings">earnings releases</Term>
        <Term id="near_earnings" />
      </>,
    );
    expect(screen.getByRole('button', { name: 'What is earnings releases?' })).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: `What is ${GLOSSARY.near_earnings.title}?` }),
    ).toBeInTheDocument();
  });

  it('names the button from `label` when given, else from text children, else the entry title', () => {
    renderApp(
      <>
        <Term id="rsi" label="Relative strength">
          some words
        </Term>
        <Term id="vwap">VWAP</Term>
        <Term id="sma" />
      </>,
    );
    expect(screen.getByRole('button', { name: 'What is Relative strength?' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'What is VWAP?' })).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: `What is ${GLOSSARY.sma.title}?` }),
    ).toBeInTheDocument();
  });

  it('keeps the suffix and the last word together with the "?" in one no-wrap span', () => {
    renderApp(
      <p data-testid="p">
        <Term id="rsi" suffix=".">
          {'see the words  '}
        </Term>
      </p>,
    );
    const btn = screen.getByRole('button', { name: /^What is see the words/u });
    const nowrap = btn.parentElement;
    expect(nowrap?.textContent).toBe('words.');
    expect(screen.getByTestId('p').textContent).toBe('see the words.');
  });

  it('has a short plain-English entry for every term', () => {
    for (const id of TERM_IDS) {
      const { title, body } = GLOSSARY[id];
      expect(title.length).toBeGreaterThan(0);
      expect(body.split(/\s+/).length).toBeLessThanOrEqual(45);
    }
  });
});
