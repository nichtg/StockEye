import ExpandMore from '@mui/icons-material/ExpandMore';
import Accordion from '@mui/material/Accordion';
import AccordionDetails from '@mui/material/AccordionDetails';
import AccordionSummary from '@mui/material/AccordionSummary';
import Typography from '@mui/material/Typography';
import type { ReactNode } from 'react';
import { radius } from '../theme/tokens';

interface DetailsAccordionProps {
  title: string;
  /** Skip rendering the body until first opened. */
  unmountOnExit?: boolean;
  children: ReactNode;
}

/** The collapsible "Details" block that keeps secondary numbers out of the default view. */
export function DetailsAccordion({ title, unmountOnExit, children }: DetailsAccordionProps) {
  return (
    <Accordion
      disableGutters
      slotProps={unmountOnExit ? { transition: { unmountOnExit: true } } : undefined}
      sx={{
        border: 1,
        borderColor: 'line',
        borderRadius: radius.lg,
        '&::before': { display: 'none' },
      }}
    >
      <AccordionSummary expandIcon={<ExpandMore />}>
        <Typography variant="subtitle1" sx={{ color: 'ink' }}>
          {title}
        </Typography>
      </AccordionSummary>
      <AccordionDetails sx={{ p: 0 }} aria-label={title}>
        {children}
      </AccordionDetails>
    </Accordion>
  );
}
