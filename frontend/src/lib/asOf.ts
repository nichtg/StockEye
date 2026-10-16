/**
 * "3:58 PM" when `iso` falls on today's calendar date in the viewer's time zone, else "Oct 14".
 * The locale is the viewer's own (undefined = browser default); tests pin it.
 */
export function formatAsOfShort(
  iso: string,
  now: Date = new Date(),
  locale?: string,
): string | null {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return null;
  const day = (d: Date) =>
    new Intl.DateTimeFormat(locale, { year: 'numeric', month: 'numeric', day: 'numeric' }).format(
      d,
    );
  if (day(date) === day(now)) {
    return new Intl.DateTimeFormat(locale, { hour: 'numeric', minute: '2-digit' }).format(date);
  }
  return new Intl.DateTimeFormat(locale, { month: 'short', day: 'numeric' }).format(date);
}
