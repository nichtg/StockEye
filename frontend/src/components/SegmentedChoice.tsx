import Box from '@mui/material/Box';
import ButtonBase from '@mui/material/ButtonBase';
import type { Theme } from '@mui/material/styles';
import { useRef, type KeyboardEvent } from 'react';
import { segmentedStyles } from '../theme/segmented';
import type { Choice } from './Choice';
import { CountBadge } from './CountBadge';

/** The Newest/Biggest-move look, applied to a group of radio buttons. */
const groupSx = (theme: Theme) => {
  const seg = segmentedStyles(theme.palette);
  return {
    ...seg.track,
    display: 'flex',
    gap: 0.5,
    maxWidth: '100%',
    flexWrap: 'wrap',
    '& .choice': {
      ...seg.item,
      fontSize: '0.9375rem',
      fontWeight: 500,
      '&[aria-checked="true"]': seg.selected,
    },
  };
};

const STOCKS: readonly [string, string] = ['stock', 'stocks'];

/**
 * A single-choice radio group in a segmented track. Arrow keys move the choice (and the focus)
 * with wrap-around, and only the checked button is in the tab order, as in a native radio group.
 */
export function SegmentedChoice({
  label,
  choices,
  value,
  onChange,
  unit = STOCKS,
}: {
  label: string;
  choices: Choice[];
  value: string;
  onChange: (value: string) => void;
  /** What the counts count, singular then plural, for the spoken name ("42 articles"). */
  unit?: readonly [string, string];
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
    <Box role="radiogroup" aria-label={label} onKeyDown={onKeyDown} sx={groupSx}>
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
            aria-label={
              c.count === undefined
                ? c.name
                : `${c.name ?? c.label}, ${String(c.count)} ${c.count === 1 ? unit[0] : unit[1]}`
            }
            tabIndex={checked ? 0 : -1}
            onClick={() => {
              onChange(c.value);
            }}
          >
            {/* Its own baseline row, so the button can still centre it vertically. */}
            <Box
              component="span"
              sx={{ display: 'inline-flex', alignItems: 'baseline', gap: '6px' }}
            >
              {c.label}
              {c.count !== undefined && <CountBadge count={c.count} inverted={checked} />}
            </Box>
          </ButtonBase>
        );
      })}
    </Box>
  );
}
