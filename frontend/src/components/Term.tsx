import HelpOutline from '@mui/icons-material/HelpOutline';
import Box from '@mui/material/Box';
import IconButton from '@mui/material/IconButton';
import Tooltip from '@mui/material/Tooltip';
import Typography from '@mui/material/Typography';
import { useEffect, useRef, useState, type ReactNode } from 'react';
import { GLOSSARY, type TermId } from '../glossary';

interface TermProps {
  id: TermId;
  /** The jargon itself. Leave out to render just the "?" button, e.g. beside a chip. */
  children?: ReactNode;
}

/**
 * Jargon wrapper: renders the text plus a small "?" button. The explanation opens on hover, on
 * keyboard focus and on tap (touch), and closes on Escape, blur or a tap elsewhere.
 */
export function Term({ id, children }: TermProps) {
  const entry = GLOSSARY[id];
  const label = typeof children === 'string' ? children : entry.title;
  const [open, setOpen] = useState(false);
  const wrapperRef = useRef<HTMLSpanElement>(null);
  const touching = useRef(false);

  // Touch has no hover or blur, so dismiss on a tap anywhere outside the button and tooltip.
  useEffect(() => {
    if (!open) return;
    const onPointerDown = (e: PointerEvent) => {
      const target = e.target;
      if (!(target instanceof Element)) return;
      if (wrapperRef.current?.contains(target) || target.closest('[role="tooltip"]')) return;
      setOpen(false);
    };
    document.addEventListener('pointerdown', onPointerDown);
    return () => {
      document.removeEventListener('pointerdown', onPointerDown);
    };
  }, [open]);

  return (
    <Box
      ref={wrapperRef}
      component="span"
      // Baseline, so the text stays on the surrounding line; only the taller "?" is centred.
      sx={{ display: 'inline-flex', alignItems: 'baseline', gap: 0.25, verticalAlign: 'baseline' }}
    >
      {children}
      <Tooltip
        open={open}
        onOpen={() => {
          // On touch the tap itself toggles; ignore the hover/focus emulation that precedes it.
          if (!touching.current) setOpen(true);
        }}
        onClose={() => {
          setOpen(false);
        }}
        disableTouchListener
        describeChild
        placement="top"
        title={
          <Box>
            <Typography variant="subtitle2" component="p" sx={{ color: 'ink', mb: 0.25 }}>
              {entry.title}
            </Typography>
            <Typography variant="body2" component="p">
              {entry.body}
            </Typography>
          </Box>
        }
      >
        <IconButton
          size="small"
          aria-label={`What is ${label}?`}
          onPointerDown={(e) => {
            touching.current = e.pointerType === 'touch';
          }}
          onBlur={() => {
            touching.current = false;
          }}
          onClick={() => {
            setOpen((wasOpen) => (touching.current ? !wasOpen : true));
          }}
          sx={{
            alignSelf: 'center',
            width: 24,
            height: 24,
            ml: 0.25,
            color: 'ink3',
            '&:hover': { color: 'ink', bgcolor: 'transparent' },
          }}
        >
          <HelpOutline sx={{ fontSize: 16 }} />
        </IconButton>
      </Tooltip>
    </Box>
  );
}
