import Check from '@mui/icons-material/Check';
import Box from '@mui/material/Box';
import MenuItem from '@mui/material/MenuItem';
import Select from '@mui/material/Select';
import Typography from '@mui/material/Typography';
import { useId } from 'react';
import type { Choice } from './Choice';
import { visuallyHidden } from '../lib/a11y';
import { LabelWithCount } from './LabelWithCount';

/**
 * A non-native single-choice menu in the app's look: static label above the field, ink-toned
 * highlight, a check on the chosen item, count badges after the label. The first item is the "all" /
 * default entry and carries a bottom border as its divider (a Divider child would become a
 * bogus, clickable option).
 */
export function ThemedSelect({
  label,
  choices,
  value,
  onChange,
  minWidth,
  unit,
}: {
  label: string;
  choices: Choice[];
  value: string;
  onChange: (value: string) => void;
  minWidth: number;
  /** What the counts count (singular, plural): gives each option a spoken "42 articles". */
  unit?: readonly [string, string];
}) {
  const labelId = useId();
  const current = choices.find((c) => c.value === value);

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-start', gap: 0.5 }}>
      <Typography
        id={labelId}
        component="span"
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
        renderValue={() => {
          const text = current?.label ?? value;
          if (current?.count === undefined) return text;
          return (
            <>
              <LabelWithCount count={current.count} hideBadgeFromSpeech>
                {text}
              </LabelWithCount>
              {unit && (
                <Box component="span" sx={visuallyHidden}>
                  , {current.count} {current.count === 1 ? unit[0] : unit[1]}
                </Box>
              )}
            </>
          );
        }}
        onChange={(e) => {
          onChange(e.target.value);
        }}
        MenuProps={{ slotProps: { paper: { sx: { maxHeight: 360, minWidth } } } }}
        sx={{ minWidth }}
      >
        {choices.map((c, i) => (
          <MenuItem
            key={c.value}
            value={c.value}
            aria-label={
              unit && c.count !== undefined
                ? `${c.label}, ${String(c.count)} ${c.count === 1 ? unit[0] : unit[1]}`
                : undefined
            }
            sx={{
              gap: 1,
              ...(i === 0 && { borderBottom: 1, borderColor: 'line', mb: 0.5 }),
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
            {c.count === undefined ? (
              c.label
            ) : (
              <LabelWithCount count={c.count} inverted={c.value === value}>
                {c.label}
              </LabelWithCount>
            )}
          </MenuItem>
        ))}
      </Select>
    </Box>
  );
}
