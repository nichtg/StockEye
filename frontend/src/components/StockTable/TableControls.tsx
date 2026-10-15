import ArrowDownward from '@mui/icons-material/ArrowDownward';
import ArrowUpward from '@mui/icons-material/ArrowUpward';
import Check from '@mui/icons-material/Check';
import Box from '@mui/material/Box';
import ButtonBase from '@mui/material/ButtonBase';
import Divider from '@mui/material/Divider';
import IconButton from '@mui/material/IconButton';
import MenuItem from '@mui/material/MenuItem';
import Select from '@mui/material/Select';
import Typography from '@mui/material/Typography';
import useMediaQuery from '@mui/material/useMediaQuery';
import { useTheme, type Theme } from '@mui/material/styles';
import { useId, useMemo, useRef, type KeyboardEvent, type ReactNode } from 'react';
import type { OverviewRow } from '../../api/types';
import { segmentedStyles } from '../../theme/segmented';
import { SORT_LABELS, countryOptions, parseSortKey, sortKeysFor } from './sortFilter';
import type { TableState } from './useTableState';

interface Props {
  /** Every row the controls govern (all lists on Discover); the country options come from these. */
  rows: readonly OverviewRow[];
  state: TableState;
}

/** Up to this many countries are shown as buttons; more would crowd the row, so they go in a menu. */
const SEGMENTED_MAX = 5;

interface Choice {
  /** '' is "all" (or the default order). */
  value: string;
  label: string;
  /** Undefined for "all": it has no meaningful count of its own. */
  count?: number;
}

const tabular = { fontVariantNumeric: 'tabular-nums' } as const;

/** The Newest/Biggest-move look, applied to a group of radio buttons. */
const segmentedGroupSx = (theme: Theme) => {
  const seg = segmentedStyles(theme.palette);
  return {
    ...seg.track,
    display: 'flex',
    flexWrap: 'wrap',
    gap: 0.5,
    maxWidth: '100%',
    '& .choice': {
      ...seg.item,
      display: 'inline-flex',
      alignItems: 'baseline',
      gap: 0.75,
      fontSize: '0.9375rem',
      fontWeight: 500,
      '&:focus-visible': { outline: `2px solid ${theme.palette.ink}`, outlineOffset: 2 },
      '&[aria-checked="true"]': seg.selected,
    },
  };
};

/**
 * A single-choice radio group in a segmented track. Arrow keys move the choice (and the focus)
 * with wrap-around, and only the checked button is in the tab order, as in a native radio group.
 */
function SegmentedChoice({
  label,
  choices,
  value,
  onChange,
}: {
  label: string;
  choices: Choice[];
  value: string;
  onChange: (value: string) => void;
}) {
  const refs = useRef<(HTMLButtonElement | null)[]>([]);

  const onKeyDown = (event: KeyboardEvent<HTMLElement>) => {
    const step =
      event.key === 'ArrowRight' || event.key === 'ArrowDown'
        ? 1
        : event.key === 'ArrowLeft' || event.key === 'ArrowUp'
          ? -1
          : 0;
    if (step === 0) return;
    event.preventDefault();
    const at = Math.max(
      0,
      choices.findIndex((c) => c.value === value),
    );
    const next = (at + step + choices.length) % choices.length;
    const choice = choices[next];
    if (!choice) return;
    onChange(choice.value);
    refs.current[next]?.focus();
  };

  return (
    <Box role="radiogroup" aria-label={label} onKeyDown={onKeyDown} sx={segmentedGroupSx}>
      {choices.map((c, i) => {
        const checked = c.value === value;
        return (
          <ButtonBase
            key={c.value}
            ref={(el: HTMLButtonElement | null) => {
              refs.current[i] = el;
            }}
            className="choice"
            role="radio"
            aria-checked={checked}
            aria-label={c.count === undefined ? undefined : `${c.label} ${String(c.count)}`}
            tabIndex={checked ? 0 : -1}
            onClick={() => {
              onChange(c.value);
            }}
          >
            {c.label}
            {c.count !== undefined && (
              <Box component="span" sx={{ color: 'ink3', fontSize: '0.8125rem', ...tabular }}>
                {c.count}
              </Box>
            )}
          </ButtonBase>
        );
      })}
    </Box>
  );
}

/**
 * A non-native single-choice menu in the app's look: static label above the field, ink-toned
 * highlight, a check on the chosen item, counts right-aligned. The first item is the "all" /
 * default entry and is followed by a divider.
 */
function ThemedSelect({
  label,
  choices,
  value,
  onChange,
  minWidth,
}: {
  label: string;
  choices: Choice[];
  value: string;
  onChange: (value: string) => void;
  minWidth: number;
}) {
  const labelId = useId();
  const current = choices.find((c) => c.value === value);
  const items: ReactNode[] = choices.flatMap((c, i) => [
    <MenuItem
      key={c.value}
      value={c.value}
      sx={{
        gap: 1,
        '&.Mui-selected, &.Mui-selected:hover, &.Mui-selected.Mui-focusVisible': {
          backgroundColor: 'raised',
          color: 'ink',
          fontWeight: 600,
        },
      }}
    >
      <Check
        fontSize="small"
        aria-hidden="true"
        sx={{ visibility: c.value === value ? 'visible' : 'hidden', flexShrink: 0 }}
      />
      <Box component="span" sx={{ flexGrow: 1 }}>
        {c.label}
      </Box>
      {c.count !== undefined && (
        <Box component="span" sx={{ color: 'ink3', ml: 2, ...tabular }}>
          {c.count}
        </Box>
      )}
    </MenuItem>,
    ...(i === 0 ? [<Divider key={`${c.value}-divider`} />] : []),
  ]);

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-start', gap: 0.5 }}>
      <Typography
        id={labelId}
        component="label"
        variant="caption"
        sx={{ color: 'ink2', fontWeight: 500 }}
      >
        {label}
      </Typography>
      <Select
        size="small"
        displayEmpty
        labelId={labelId}
        value={value}
        renderValue={() => current?.label ?? value}
        onChange={(e) => {
          onChange(e.target.value);
        }}
        MenuProps={{ slotProps: { paper: { sx: { maxHeight: 360, minWidth } } } }}
        sx={{ minWidth }}
      >
        {items}
      </Select>
    </Box>
  );
}

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
  const asButtons = countries.length <= SEGMENTED_MAX;
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
