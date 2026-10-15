import { SegmentedChoice } from '../../../components/SegmentedChoice';
import { monthChoices, type NewsMonth } from './months';

const ARTICLES = ['article', 'articles'] as const;

/** "All" plus one chip per month; the counts are articles, not grouped stories. */
export function MonthChips({
  months,
  value,
  onChange,
}: {
  months: readonly NewsMonth[];
  value: string;
  onChange: (month: string) => void;
}) {
  return (
    <SegmentedChoice
      label="Filter by month"
      choices={monthChoices(months)}
      value={value}
      onChange={onChange}
      unit={ARTICLES}
      scroll
    />
  );
}
