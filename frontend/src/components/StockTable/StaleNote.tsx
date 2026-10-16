import ButtonBase from '@mui/material/ButtonBase';
import ClickAwayListener from '@mui/material/ClickAwayListener';
import Tooltip from '@mui/material/Tooltip';
import { useState } from 'react';
import { formatAsOfShort } from '../../lib/asOf';
import type { StockRow } from './sortFilter';

const REFRESH_FAILED = "Couldn't refresh just now; showing the last saved price.";

export function StaleNote({ row, locale }: { row: StockRow; locale?: string }) {
  const [open, setOpen] = useState(false);
  if (row.status === 'ok' || row.status === 'unavailable') return null;

  const stale = row.status === 'stale';
  const when =
    stale && row.status_as_of ? formatAsOfShort(row.status_as_of, new Date(), locale) : null;
  const label = !stale ? 'Partial data' : when ? `As of ${when}` : 'Last saved price';
  const tip = stale
    ? [REFRESH_FAILED, row.status_reason].filter(Boolean).join(' ')
    : (row.status_reason ?? 'This data may be out of date.');
  const name = stale
    ? `${when ? `Price as of ${when}` : 'Last saved price'}, couldn't refresh`
    : 'Partial data';

  return (
    <ClickAwayListener
      mouseEvent={open ? 'onClick' : false}
      touchEvent={open ? 'onTouchEnd' : false}
      onClickAway={() => {
        setOpen(false);
      }}
    >
      <span style={{ display: 'block' }}>
        <Tooltip
          title={tip}
          open={open}
          onOpen={() => {
            setOpen(true);
          }}
          onClose={() => {
            setOpen(false);
          }}
          describeChild
          enterDelay={0}
          disableTouchListener
        >
          <ButtonBase
            aria-label={name}
            onClick={() => {
              setOpen(true);
            }}
            onBlur={() => {
              setOpen(false);
            }}
            onKeyDown={(e) => {
              if (e.key === 'Escape') setOpen(false);
            }}
            sx={{
              display: 'inline-flex',
              alignItems: 'center',
              verticalAlign: 'top',
              minHeight: 24,
              minWidth: 24,
              px: 0.5,
              mr: -0.5,
              my: -0.25,
              borderRadius: 1,
              color: 'ink3',
              typography: 'caption',
              cursor: 'help',
            }}
          >
            {label}
          </ButtonBase>
        </Tooltip>
      </span>
    </ClickAwayListener>
  );
}
