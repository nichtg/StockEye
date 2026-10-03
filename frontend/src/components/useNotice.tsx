import Button from '@mui/material/Button';
import Snackbar from '@mui/material/Snackbar';
import { useState, type ReactNode } from 'react';

interface NoticeAction {
  label: string;
  onClick: () => void;
}

interface Notice {
  message: string;
  action?: NoticeAction;
}

/**
 * A toast with an optional action (Undo). Notices queue, so two in a row each get shown in full.
 * Render `element` once; call `show` from anywhere, including after the caller has unmounted.
 */
export function useNotice(): {
  show: (message: string, action?: NoticeAction) => void;
  element: ReactNode;
} {
  const [queue, setQueue] = useState<Notice[]>([]);
  const [dismissed, setDismissed] = useState(false);
  const current = queue[0];

  const element = (
    <Snackbar
      open={current !== undefined && !dismissed}
      autoHideDuration={6000}
      onClose={(_, reason) => {
        if (reason !== 'clickaway') setDismissed(true);
      }}
      slotProps={{
        transition: {
          onExited: () => {
            setQueue((q) => q.slice(1));
            setDismissed(false);
          },
        },
      }}
      message={current?.message}
      action={
        current?.action && (
          <Button
            color="inherit"
            size="small"
            onClick={() => {
              current.action?.onClick();
              setDismissed(true);
            }}
          >
            {current.action.label}
          </Button>
        )
      }
      anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
    />
  );

  return {
    show: (message, action) => {
      setQueue((q) => [...q, { message, action }]);
      // A notice already on screen makes way for the new one.
      if (queue.length > 0) setDismissed(true);
    },
    element,
  };
}
