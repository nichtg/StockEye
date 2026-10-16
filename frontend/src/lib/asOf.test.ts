import { formatAsOfShort } from './asOf';

describe('formatAsOfShort', () => {
  const now = new Date(2026, 9, 16, 18, 0); // local time, so "today" holds in any zone

  it('shows the time for an instant on the same local day', () => {
    expect(formatAsOfShort(new Date(2026, 9, 16, 15, 58).toISOString(), now, 'en-US')).toBe(
      '3:58 PM',
    );
  });

  it('shows month and day for an earlier day', () => {
    expect(formatAsOfShort(new Date(2026, 9, 14, 15, 58).toISOString(), now, 'en-US')).toBe(
      'Oct 14',
    );
  });

  it('shows the date when over 12 hours old, even on the same calendar day', () => {
    const late = new Date(2026, 9, 16, 23, 0);
    expect(formatAsOfShort(new Date(2026, 9, 16, 1, 0).toISOString(), late, 'en-US')).toBe(
      'Oct 16',
    );
  });

  it('returns null for an unparseable value', () => {
    expect(formatAsOfShort('nope', now, 'en-US')).toBeNull();
  });
});
