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
      onClickAway={() => {
        setOpen(false);
      }}
    >
      <span>
        <Tooltip
          title={tip}
          open={open}
          onOpen={() => {
            setOpen(true);
          }}
          onClose={() => {
            setOpen(false);
          }}
          disableFocusListener={false}
          disableTouchListener
        >
          <ButtonBase
            aria-label={name}
            onClick={() => {
              setOpen((v) => !v);
            }}
            onBlur={() => {
              setOpen(false);
            }}
            onKeyDown={(e) => {
              if (e.key === 'Escape') setOpen(false);
            }}
            sx={{
              display: 'block',
              minHeight: 24,
              minWidth: 24,
              px: 0.5,
              ml: -0.5,
              borderRadius: 1,
              textAlign: 'left',
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
