import ArrowDownward from '@mui/icons-material/ArrowDownward';
import ArrowUpward from '@mui/icons-material/ArrowUpward';
import Box from '@mui/material/Box';
import IconButton from '@mui/material/IconButton';
import TextField from '@mui/material/TextField';
import useMediaQuery from '@mui/material/useMediaQuery';
import { useTheme } from '@mui/material/styles';
import {
  SORT_KEYS,
  SORT_LABELS,
  parseSortKey,
  type CountryOption,
  type SortState,
} from './sortFilter';

interface Props {
  countries: CountryOption[];
  country: string | null;
  onCountry: (country: string | null) => void;
  sort: SortState | null;
  onSort: (next: SortState | null) => void;
  showMarketCap?: boolean;
}

/**
 * The country filter, plus a "Sort by" select on phones (where there are no column headers to
 * click). Native selects: they work well on touch and for screen readers.
 */
export function TableControls({
  countries,
  country,
  onCountry,
  sort,
  onSort,
  showMarketCap = false,
}: Props) {
  const theme = useTheme();
  const compact = useMediaQuery(theme.breakpoints.down('sm'));
  const keys = SORT_KEYS.filter((k) => showMarketCap || k !== 'cap');
  // A country from a shared link may not be in the rows; keep it selectable so the state is visible.
  const hasCountry = country != null && countries.some((c) => c.country === country);

  return (
    <Box sx={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 1.5, mb: 2 }}>
      <TextField
        select
        size="small"
        label="Country"
        value={country ?? ''}
        onChange={(e) => {
          onCountry(e.target.value || null);
        }}
        slotProps={{ select: { native: true }, inputLabel: { shrink: true } }}
        sx={{ minWidth: 200 }}
      >
        <option value="">All countries</option>
        {country && !hasCountry && <option value={country}>{country} (0)</option>}
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
              const key = parseSortKey(e.target.value);
              onSort(key ? { key, dir: sort?.dir ?? 'asc' } : null);
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
              aria-label={
                sort.dir === 'asc'
                  ? 'Ascending, switch to descending'
                  : 'Descending, switch to ascending'
              }
              onClick={() => {
                onSort({ key: sort.key, dir: sort.dir === 'asc' ? 'desc' : 'asc' });
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
