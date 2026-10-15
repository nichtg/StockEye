import ArrowDownward from '@mui/icons-material/ArrowDownward';
import ArrowUpward from '@mui/icons-material/ArrowUpward';
import Box from '@mui/material/Box';
import IconButton from '@mui/material/IconButton';
import TextField from '@mui/material/TextField';
import useMediaQuery from '@mui/material/useMediaQuery';
import { useTheme } from '@mui/material/styles';
import { useMemo } from 'react';
import type { OverviewRow } from '../../api/types';
import { SORT_LABELS, countryOptions, parseSortKey, sortKeysFor } from './sortFilter';
import type { TableState } from './useTableState';

interface Props {
  /** Every row the controls govern (all lists on Discover); the country options come from these. */
  rows: readonly OverviewRow[];
  state: TableState;
}

/**
 * The country filter, plus a "Sort by" select on phones (where there are no column headers to
 * click). Native selects: they work well on touch and for screen readers.
 */
export function TableControls({ rows, state }: Props) {
  const { columns, country, sort, setCountry, setSort } = state;
  const theme = useTheme();
  const compact = useMediaQuery(theme.breakpoints.down('sm'));
  const countries = useMemo(() => countryOptions(rows), [rows]);
  const keys = sortKeysFor(columns);

  return (
    <Box sx={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 1.5, mb: 2 }}>
      <TextField
        select
        size="small"
        label="Country"
        value={country ?? ''}
        onChange={(e) => {
          setCountry(e.target.value || null);
        }}
        slotProps={{ select: { native: true }, inputLabel: { shrink: true } }}
        sx={{ minWidth: 200 }}
      >
        <option value="">All countries</option>
        {/* A country from a shared link may match no row; keep it visible rather than blank. */}
        {country && !countries.some((c) => c.country === country) && (
          <option value={country}>{country} (0)</option>
        )}
        {countries.map((c) => (
          <option key={c.country} value={c.country}>
            {c.country} ({c.count})
          </option>
        ))}
      </TextField>
      {compact && (
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
          <TextField
            select
            size="small"
            label="Sort by"
            value={sort?.key ?? ''}
            onChange={(e) => {
              const key = parseSortKey(e.target.value, keys);
              setSort(key ? { key, dir: sort?.dir ?? 'asc' } : null);
            }}
            slotProps={{ select: { native: true }, inputLabel: { shrink: true } }}
            sx={{ minWidth: 150 }}
          >
            <option value="">Default order</option>
            {keys.map((k) => (
              <option key={k} value={k}>
                {SORT_LABELS[k]}
              </option>
            ))}
          </TextField>
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
