import Box from '@mui/material/Box';
import Chip from '@mui/material/Chip';
import ToggleButton from '@mui/material/ToggleButton';
import ToggleButtonGroup from '@mui/material/ToggleButtonGroup';
import Tooltip from '@mui/material/Tooltip';
import { useEffect, useRef, useState, type ReactNode } from 'react';
import type { RangeKey } from '../../api/types';
import { radius } from '../../theme/tokens';
import { INDICATORS, vwapVariant, type IndicatorId } from './indicators';
import { RANGES } from './useChartSettings';

/**
 * One horizontally scrollable row of chips on phones. A fade on the right edge appears only while
 * there is more to scroll to, so a clipped chip never looks like the end of the list.
 */
function ChipRow({ children }: { children: ReactNode }) {
  const ref = useRef<HTMLDivElement>(null);
  const [more, setMore] = useState(false);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const update = () => {
      setMore(el.scrollWidth - el.clientWidth - el.scrollLeft > 1);
    };
    update();
    if (typeof ResizeObserver === 'undefined') return;
    const observer = new ResizeObserver(update);
    observer.observe(el);
    el.addEventListener('scroll', update, { passive: true });
    return () => {
      observer.disconnect();
      el.removeEventListener('scroll', update);
    };
  }, []);

  return (
    <Box
      sx={{
        position: 'relative',
        minWidth: 0,
        width: { xs: '100%', sm: 'auto' },
        '&::after': {
          content: '""',
          position: 'absolute',
          top: 0,
          right: 0,
          bottom: 0,
          width: 32,
          pointerEvents: 'none',
          background: 'linear-gradient(to right, transparent, var(--se-bg))',
          opacity: more ? 1 : 0,
          transition: 'opacity 150ms ease',
          display: { xs: 'block', sm: 'none' },
        },
      }}
    >
      <Box
        ref={ref}
        role="group"
        aria-label="Indicators"
        sx={{
          display: 'flex',
          gap: 0.75,
          flexWrap: { xs: 'nowrap', sm: 'wrap' },
          overflowX: { xs: 'auto', sm: 'visible' },
          scrollSnapType: { xs: 'x proximity', sm: 'none' },
          scrollbarWidth: 'none',
          '&::-webkit-scrollbar': { display: 'none' },
          '& > *': { flexShrink: 0, scrollSnapAlign: 'start' },
        }}
      >
        {children}
      </Box>
    </Box>
  );
}

const RANGE_BUTTON_SX = {
  '& .MuiToggleButton-root': {
    borderRadius: radius.sm,
    border: 1,
    borderColor: 'line',
    color: 'ink2',
    px: 1.5,
    py: 0.5,
    fontWeight: 500,
    fontVariantNumeric: 'tabular-nums',
    textTransform: 'none',
    '&:hover': { bgcolor: 'raised' },
    '&.Mui-selected, &.Mui-selected:hover': { bgcolor: 'ink', color: 'bg', borderColor: 'ink' },
    '&:not(:first-of-type)': {
      ml: 0.5,
      borderLeft: 1,
      borderColor: 'line',
      borderRadius: radius.sm,
    },
    '&:not(:last-of-type)': { borderRadius: radius.sm },
    '&.Mui-selected:not(:first-of-type)': { borderColor: 'ink' },
  },
} as const;

interface ChartToolbarProps {
  range: RangeKey;
  onRangeChange: (range: RangeKey) => void;
  selection: IndicatorId[];
  onToggleIndicator: (id: IndicatorId) => void;
}

/** Range selector on the left, indicator toggles on the right. */
export function ChartToolbar({
  range,
  onRangeChange,
  selection,
  onToggleIndicator,
}: ChartToolbarProps) {
  return (
    <Box
      sx={{
        display: 'flex',
        flexWrap: 'wrap',
        alignItems: 'center',
        justifyContent: 'space-between',
        gap: 1.5,
        mb: 1.5,
        minWidth: 0,
      }}
    >
      <ToggleButtonGroup
        exclusive
        size="small"
        value={range}
        aria-label="Chart range"
        onChange={(_e, value: RangeKey | null) => {
          if (value) onRangeChange(value);
        }}
        sx={RANGE_BUTTON_SX}
      >
        {RANGES.map((r) => (
          <ToggleButton key={r} value={r} aria-label={`${r} range`}>
            {r}
          </ToggleButton>
        ))}
      </ToggleButtonGroup>

      <ChipRow>
        {INDICATORS.map((ind) => {
          const on = selection.includes(ind.id);
          const chip = (
            <Chip
              key={ind.id}
              label={ind.label}
              clickable
              size="small"
              variant={on ? 'filled' : 'outlined'}
              aria-pressed={on}
              onClick={() => {
                onToggleIndicator(ind.id);
              }}
              sx={{
                borderRadius: '999px',
                height: 28,
                px: 0.5,
                fontSize: '0.8125rem',
                ...(on
                  ? {
                      bgcolor: 'ink',
                      color: 'bg',
                      borderColor: 'ink',
                      '&:hover': { bgcolor: 'ink2' },
                    }
                  : { bgcolor: 'transparent', color: 'ink2', borderColor: 'line' }),
              }}
            />
          );
          return ind.id === 'vwap' ? (
            <Tooltip key={ind.id} title={vwapVariant(range).hint} describeChild>
              {chip}
            </Tooltip>
          ) : (
            chip
          );
        })}
      </ChipRow>
    </Box>
  );
}
