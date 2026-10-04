import { ApiError, SERVER_PROBLEM_MESSAGE, userMessage } from './errors';

const err = (status: number, message = 'from server') =>
  new ApiError({ code: 'x', message, status });

describe('userMessage', () => {
  it('shows rate-limit and server-sent 4xx messages as written', () => {
    expect(userMessage(err(429, 'Slow down.'))).toBe('Slow down.');
    expect(userMessage(err(409, 'Watchlist is full.'))).toBe('Watchlist is full.');
  });

  it('uses one generic sentence for network failures and 5xx', () => {
    expect(userMessage(err(0, 'Can’t reach StockEye.'))).toBe(SERVER_PROBLEM_MESSAGE);
    expect(userMessage(err(503, 'upstream exploded'))).toBe(SERVER_PROBLEM_MESSAGE);
  });

  it('falls back for anything that is not an API error', () => {
    expect(userMessage(new Error('boom'))).toBe(SERVER_PROBLEM_MESSAGE);
    expect(userMessage('nope', 'Custom.')).toBe('Custom.');
  });
});
