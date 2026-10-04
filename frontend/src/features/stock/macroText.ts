import type { MacroReportOut, Reliability } from '../../api/types';

export const NOT_ENOUGH_NEWS = 'Not enough news yet to analyse this stock.';

export const RELIABILITY_LABEL: Record<Reliability, string> = {
  clear_effect: 'Clear news effect',
  possible_effect: 'Possible news effect',
  no_clear_effect: 'No clear news effect',
};

const LEAD = /^(?:Clear|Possible|No clear) news effect: ?(\S)/;

/**
 * The backend writes reliability sentences as "Possible news effect: if news had no influence ...".
 * The UI shows that label as a chip instead, so drop it from the text and keep the rest.
 */
export function stripReliabilityLead(text: string): string {
  return text.replace(LEAD, (_m, first: string) => first.toUpperCase());
}

export function regimeSentence(label: NonNullable<MacroReportOut['regime']>['label']): string {
  switch (label) {
    case 'more_positive_than_usual':
      return 'News over the last 30 days is more positive than usual.';
    case 'more_negative_than_usual':
      return 'News over the last 30 days is more negative than usual.';
    case 'typical':
      return 'News over the last 30 days is about as positive as usual.';
  }
}

export function pValueText(p: number | null): string {
  if (p == null) return '–';
  return p < 0.001 ? 'under 0.001' : p.toFixed(3);
}

export function newsDaysPhrase(count: number): string {
  return `Based on ${String(count)} news ${count === 1 ? 'day' : 'days'}`;
}

export type Scope = NonNullable<MacroReportOut['primary_scope']>;
