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

  // Glue the "?" to the last word so it never wraps onto a line of its own.
  let lead: ReactNode = null;
  let tail: ReactNode = children;
  if (typeof children === 'string') {
    const m = /^([\s\S]*\s)(\S+)$/.exec(children);
    if (m) {
      lead = m[1];
      tail = m[2];
    }
  }

  return (
    <Box ref={wrapperRef} component="span">
      {lead}
      <Box component="span" sx={{ whiteSpace: 'nowrap' }}>
        {tail}
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
            disableRipple
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
              // Inline-level box sized by the surrounding text and centred on its middle; never grows the line.
              display: 'inline-block',
              verticalAlign: 'middle',
              position: 'relative',
              width: '1.1em',
              height: '1.1em',
              minWidth: 0,
              p: 0,
              ml: children === undefined ? 0 : '0.25em',
              fontSize: 'inherit',
              lineHeight: 1,
              borderRadius: '50%',
              color: 'ink3',
              '&:hover': { color: 'ink', bgcolor: 'transparent' },
              // Invisible tap target of at least 24x24 px centred on the glyph; adds no layout size.
              '&::after': {
                content: '""',
                position: 'absolute',
                top: '50%',
                left: '50%',
                width: 'max(100%, 24px)',
                height: 'max(100%, 24px)',
                transform: 'translate(-50%, -50%)',
              },
            }}
          >
            <HelpOutline sx={{ display: 'block', width: '100%', height: '100%' }} />
          </IconButton>
        </Tooltip>
      </Box>
    </Box>
  );
}
