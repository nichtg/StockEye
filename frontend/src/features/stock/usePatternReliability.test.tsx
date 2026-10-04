import { screen } from '@testing-library/react';
import { stubFetch } from '../../test/mockApi';
import { technicalFixture } from '../../test/fixtures';
import { renderApp } from '../../test/render';
import { patternSentence } from './technicalText';
import { usePatternReliability } from './usePatternReliability';

function Probe() {
  const sentences = usePatternReliability('AAPL');
  return <pre data-testid="out">{JSON.stringify(sentences)}</pre>;
}

describe('usePatternReliability', () => {
  it('maps each recent pattern to the shared reliability sentence', async () => {
    stubFetch((req) =>
      req.path === '/stocks/AAPL/technical' ? { body: technicalFixture } : undefined,
    );
    renderApp(<Probe />);
    const first = technicalFixture.recent_patterns[0];
    if (!first) throw new Error('fixture has no patterns');
    const expected = patternSentence(first.stats, first.bias);
    expect(await screen.findByText(new RegExp(first.key))).toBeInTheDocument();
    const out = JSON.parse(screen.getByTestId('out').textContent) as Record<string, string>;
    expect(out[first.key]).toBe(expected);
  });
});
