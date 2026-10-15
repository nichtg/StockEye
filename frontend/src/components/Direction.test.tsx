import { screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { renderApp } from '../test/render';
import { Direction } from './Direction';

function pill(value: number | null) {
  const { container } = renderApp(<Direction value={value} variant="pill" />);
  return container.querySelector<HTMLElement>('[data-variant]') ?? screen.getByText('–');
}

describe('Direction', () => {
  it('keeps the plain text variant by default', () => {
    renderApp(<Direction value={1.5} />);
    expect(screen.getByText('+1.5%').parentElement).toHaveAttribute('data-variant', 'text');
  });

  it('draws an up pill with glyph, sign and the up colour', () => {
    const el = pill(2.4);
    expect(el).toHaveAttribute('data-variant', 'pill');
    expect(el).toHaveTextContent('▲');
    expect(el).toHaveTextContent('+2.4%');
    expect(el).toHaveStyle({ color: '#12784A', display: 'inline-flex' });
  });

  it('draws a down pill with glyph, sign and the down colour', () => {
    const el = pill(-3.1);
    expect(el).toHaveTextContent('▼');
    expect(el).toHaveTextContent(/[-−]3.1%/);
    expect(el).toHaveStyle({ color: '#C2342B' });
  });

  it('draws a flat pill in the neutral ink2 text', () => {
    const el = pill(0);
    expect(el).toHaveAttribute('data-variant', 'pill');
    expect(el).toHaveStyle({ color: '#3F3F3F' });
  });

  it('renders a null value as a plain dash with no pill', () => {
    const el = pill(null);
    expect(el).toHaveTextContent('–');
    expect(el).not.toHaveAttribute('data-variant');
  });
});
