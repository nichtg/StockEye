import Button from '@mui/material/Button';
import Snackbar from '@mui/material/Snackbar';
import { useMemo, useReducer, type ReactNode } from 'react';
import { NoticeContext, type NoticeAction, type Show } from './useNotice';

interface Notice {
  message: string;
  action?: NoticeAction;
}

interface NoticeState {
  queue: Notice[];
  /** The head is closing (or about to). */
  dismissed: boolean;
  /** The head has started opening, so a closing animation (and its `exited`) will follow. */
  visible: boolean;
}

type NoticeEvent =
  { type: 'show'; notice: Notice } | { type: 'dismiss' } | { type: 'entered' } | { type: 'exited' };

function reduce(state: NoticeState, event: NoticeEvent): NoticeState {
  switch (event.type) {
    case 'show':
      // A notice already on screen makes way for the new one.
      return { ...state, queue: [...state.queue, event.notice], dismissed: state.visible };
    case 'dismiss':
      return { ...state, dismissed: true };
    case 'entered':
      // A head that opens with others already waiting gives way straight away.
      return { ...state, visible: true, dismissed: state.queue.length > 1 };
    case 'exited':
      return { queue: state.queue.slice(1), dismissed: false, visible: false };
  }
}

/**
 * Hosts the app's one toast, so a notice outlives the page that raised it. Notices queue, so two
 * in a row each get shown in full.
 */
export function NoticeProvider({ children }: { children: ReactNode }) {
  const [{ queue, dismissed }, dispatch] = useReducer(reduce, {
    queue: [],
    dismissed: false,
    visible: false,
  });
  const current = queue[0];
  const show = useMemo<Show>(
    () => (message, action) => {
      dispatch({ type: 'show', notice: { message, action } });
    },
    [],
  );

  return (
    <NoticeContext.Provider value={show}>
      {children}
      <Snackbar
        open={current !== undefined && !dismissed}
        autoHideDuration={6000}
        onClose={(_, reason) => {
          if (reason !== 'clickaway') dispatch({ type: 'dismiss' });
        }}
        slotProps={{
          transition: {
            onEnter: () => {
              dispatch({ type: 'entered' });
            },
            onExited: () => {
              dispatch({ type: 'exited' });
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
                dispatch({ type: 'dismiss' });
              }}
            >
              {current.action.label}
            </Button>
          )
        }
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
      />
    </NoticeContext.Provider>
  );
}
