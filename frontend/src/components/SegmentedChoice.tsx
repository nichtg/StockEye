import Box from '@mui/material/Box';
import ButtonBase from '@mui/material/ButtonBase';
import type { Theme } from '@mui/material/styles';
import { useRef, type KeyboardEvent } from 'react';
import { segmentedStyles } from '../theme/segmented';
import { countSx, type Choice } from './Choice';

/** The Newest/Biggest-move look, applied to a group of radio buttons. */
const groupSx = (scroll: boolean) => (theme: Theme) => {
  const seg = segmentedStyles(theme.palette);
  return {
    ...seg.track,
    display: 'flex',
    gap: 0.5,
    maxWidth: '100%',
    // A long row scrolls inside its own track instead of widening the page.
    ...(scroll
      ? {
          flexWrap: 'nowrap',
          overflowX: 'auto',
          width: 'fit-content',
          scrollbarWidth: 'none',
          '&::-webkit-scrollbar': { display: 'none' },
        }
      : { flexWrap: 'wrap' }),
    '& .choice': {
      ...(scroll ? { flexShrink: 0, whiteSpace: 'nowrap' } : {}),
      ...seg.item,
      display: 'inline-flex',
      alignItems: 'baseline',
      gap: 0.75,
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
  scroll = false,
}: {
  label: string;
  choices: Choice[];
  value: string;
  onChange: (value: string) => void;
  /** What the counts count, singular then plural, for the spoken name ("42 articles"). */
  unit?: readonly [string, string];
  /** One line that scrolls sideways when it is too long, rather than wrapping. */
  scroll?: boolean;
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
    <Box role="radiogroup" aria-label={label} onKeyDown={onKeyDown} sx={groupSx(scroll)}>
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
            {c.label}
            {c.count !== undefined && (
              <Box component="span" sx={countSx}>
                {c.count}
              </Box>
            )}
          </ButtonBase>
        );
      })}
    </Box>
  );
}
