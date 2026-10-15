import AddIcon from '@mui/icons-material/Add';
import ChevronLeftIcon from '@mui/icons-material/ChevronLeft';
import ChevronRightIcon from '@mui/icons-material/ChevronRight';
import RemoveIcon from '@mui/icons-material/Remove';
import RestartAltIcon from '@mui/icons-material/RestartAlt';
import Box from '@mui/material/Box';
import IconButton from '@mui/material/IconButton';
import Tooltip from '@mui/material/Tooltip';
import type { ReactElement } from 'react';
import type { RangeKey } from '../../api/types';
import { radius } from '../../theme/tokens';
import type { ChartNavigator, NavAction, NavLimits } from './navigation';

interface Props {
  /** Absent while the chart has no data; the buttons are then disabled. */
  nav: ChartNavigator | null;
  range: RangeKey;
  /** Which moves still do something; the others are disabled. */
  limits: NavLimits;
}

/** Zoom, pan and reset buttons for the chart; the same moves are on the keyboard. */
export function ChartNav({ nav, range, limits }: Props) {
  const items: { label: string; icon: ReactElement; run: NavAction; enabled: boolean }[] = [
    {
      label: 'Zoom in',
      icon: <AddIcon fontSize="small" />,
      run: 'zoomIn',
      enabled: limits.canZoomIn,
    },
    {
      label: 'Zoom out',
      icon: <RemoveIcon fontSize="small" />,
      run: 'zoomOut',
      enabled: limits.canZoomOut,
    },
    {
      label: 'Pan left',
      icon: <ChevronLeftIcon fontSize="small" />,
      run: 'panLeft',
      enabled: limits.canPanLeft,
    },
    {
      label: 'Pan right',
      icon: <ChevronRightIcon fontSize="small" />,
      run: 'panRight',
      enabled: limits.canPanRight,
    },
    {
      label: `Reset to ${range} view`,
      icon: <RestartAltIcon fontSize="small" />,
      run: 'reset',
      enabled: true,
    },
  ];
  return (
    <Box role="group" aria-label="Chart navigation" sx={{ display: 'flex', gap: 0.5 }}>
      {items.map(({ label, icon, run, enabled }) => (
        <Tooltip key={run} title={label} describeChild>
          <span>
            <IconButton
              size="small"
              aria-label={label}
              disabled={!nav || !enabled}
              onClick={() => {
                nav?.[run]();
              }}
              sx={{
                width: 32,
                height: 32,
                borderRadius: radius.sm,
                border: 1,
                borderColor: 'line',
                color: 'ink3',
                '&:hover': { bgcolor: 'raised', color: 'ink' },
                '&:focus-visible': { outline: '2px solid var(--se-ink)', outlineOffset: 2 },
              }}
            >
              {icon}
            </IconButton>
          </span>
        </Tooltip>
      ))}
    </Box>
  );
}
