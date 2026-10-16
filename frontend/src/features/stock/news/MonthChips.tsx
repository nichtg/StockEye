import useMediaQuery from '@mui/material/useMediaQuery';
import { useTheme } from '@mui/material/styles';
import { SegmentedChoice } from '../../../components/SegmentedChoice';
import { ThemedSelect } from '../../../components/ThemedSelect';
import { monthChoices, monthSelectChoices, type NewsMonth } from './months';

const ARTICLES = ['article', 'articles'] as const;

/**
 * "All" plus one chip per month; the counts are articles, not grouped stories. Below `sm` eight
 * chips don't fit, so the same choice is one themed select. Only one of the two is rendered
 * (useMediaQuery, not CSS hiding), so there is never a duplicate control for a screen reader.
 */
export function MonthChips({
  months,
  value,
  onChange,
}: {
  months: readonly NewsMonth[];
  value: string;
  onChange: (month: string) => void;
}) {
  const theme = useTheme();
  const phone = useMediaQuery(theme.breakpoints.down('sm'));
  if (phone) {
    return (
      <ThemedSelect
        label="Month"
        choices={monthSelectChoices(months)}
        value={value}
        onChange={onChange}
        minWidth={240}
        unit={ARTICLES}
      />
    );
  }
  return (
    <SegmentedChoice
      label="Filter by month"
      choices={monthChoices(months)}
      value={value}
      onChange={onChange}
      unit={ARTICLES}
    />
  );
}
