import Typography from '@mui/material/Typography';
import type { ReactNode } from 'react';

/** A section heading inside a page: h2, below the page's h1. */
export function SectionTitle({ id, children }: { id?: string; children: ReactNode }) {
  return (
    <Typography id={id} variant="h2" component="h2" sx={{ mb: 1.5 }}>
      {children}
    </Typography>
  );
}
