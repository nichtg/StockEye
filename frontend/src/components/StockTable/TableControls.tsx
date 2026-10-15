import ArrowDownward from '@mui/icons-material/ArrowDownward';
import ArrowUpward from '@mui/icons-material/ArrowUpward';
import Box from '@mui/material/Box';
import IconButton from '@mui/material/IconButton';
import useMediaQuery from '@mui/material/useMediaQuery';
import { useTheme } from '@mui/material/styles';
import { useMemo } from 'react';
import type { OverviewRow } from '../../api/types';
import type { Choice } from '../Choice';
import { SegmentedChoice } from '../SegmentedChoice';
import { ThemedSelect } from '../ThemedSelect';
import { sortKeysFor } from './columns';
import { SORT_LABELS, countryOptions, parseSortKey } from './sortFilter';
import type { TableState } from './useTableState';

interface Props {
  /** Every row the controls govern (all lists on Discover); the country options come from these. */
  rows: readonly OverviewRow[];
  state: TableState;
}

/** Up to this many countries are shown as buttons; more would crowd the row, so they go in a menu. */
const SEGMENTED_MAX = 5;
/** On a phone the buttons wrap into several rows sooner, so fewer fit. */
const SEGMENTED_MAX_COMPACT = 3;

/**
 * The country filter, plus a "Sort by" select on phones (where there are no column headers to
 * click). Few countries are shown as buttons so every choice is visible; many go in a themed menu.
 */
export function TableControls({ rows, state }: Props) {
  const { columns, country, sort, setCountry, setSort } = state;
  const theme = useTheme();
  const compact = useMediaQuery(theme.breakpoints.down('sm'));
  const countries = useMemo(() => countryOptions(rows), [rows]);
  const keys = sortKeysFor(columns);

  const countryChoices: Choice[] = [
    { value: '', label: 'All countries' },
    // A country from a shared link may match no row; keep it visible, selected, rather than blank.
    ...(country && !countries.some((c) => c.country === country)
      ? [{ value: country, label: country, count: 0 }]
      : []),
    ...countries.map((c) => ({ value: c.country, label: c.country, count: c.count })),
  ];
  const showCountry = countryChoices.length > 1;
  const asButtons = countries.length <= (compact ? SEGMENTED_MAX_COMPACT : SEGMENTED_MAX);
  const onCountry = (value: string) => {
    setCountry(value || null);
  };

  const sortChoices: Choice[] = [
    { value: '', label: 'Default order' },
    ...keys.map((k) => ({ value: k, label: SORT_LABELS[k] })),
  ];

  return (
    <Box sx={{ display: 'flex', flexWrap: 'wrap', alignItems: 'flex-end', gap: 2, mb: 2 }}>
      {showCountry &&
        (asButtons ? (
          <SegmentedChoice
            label="Filter by country"
            choices={countryChoices.map((c) => (c.value === '' ? { ...c, label: 'All' } : c))}
            value={country ?? ''}
            onChange={onCountry}
          />
        ) : (
          <ThemedSelect
            label="Country"
            choices={countryChoices}
            value={country ?? ''}
            onChange={onCountry}
            minWidth={220}
          />
        ))}
      {compact && (
        <Box sx={{ display: 'flex', alignItems: 'flex-end', gap: 0.5 }}>
          <ThemedSelect
            label="Sort by"
            choices={sortChoices}
            value={sort?.key ?? ''}
            onChange={(value) => {
              const key = parseSortKey(value, keys);
              setSort(key ? { key, dir: sort?.dir ?? 'asc' } : null);
            }}
            minWidth={170}
          />
          {sort && (
            <IconButton
              aria-label={sort.dir === 'asc' ? 'Sort descending' : 'Sort ascending'}
              title={sort.dir === 'asc' ? 'Sort descending' : 'Sort ascending'}
              onClick={() => {
                setSort({ key: sort.key, dir: sort.dir === 'asc' ? 'desc' : 'asc' });
              }}
            >
              {sort.dir === 'asc' ? (
                <ArrowUpward fontSize="small" />
              ) : (
                <ArrowDownward fontSize="small" />
              )}
            </IconButton>
          )}
        </Box>
      )}
    </Box>
  );
}
