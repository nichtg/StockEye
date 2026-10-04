import ErrorOutline from '@mui/icons-material/ErrorOutline';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Typography from '@mui/material/Typography';
import type { UseQueryResult } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { userMessage } from '../api/errors';
import { ErrorState } from './ErrorState';

interface QueryRegionProps<T> {
  query: UseQueryResult<T>;
  skeleton: ReactNode;
  errorTitle: string;
  children: (data: T) => ReactNode;
}

/** A data region's three states in one place: skeleton while pending, error with retry, content. */
export function QueryRegion<T>({ query, skeleton, errorTitle, children }: QueryRegionProps<T>) {
  if (query.data !== undefined) {
    // A failed refresh keeps what we have, with a quiet note; only a first load fails loudly.
    return (
      <>
        {children(query.data)}
        {query.isError && (
          <Box
            role="status"
            sx={{ display: 'flex', alignItems: 'center', gap: 1, mt: 1.5, color: 'ink2' }}
          >
            <ErrorOutline aria-hidden="true" sx={{ fontSize: 16 }} />
            <Typography variant="body2" sx={{ color: 'inherit' }}>
              Couldn’t refresh. Showing the last loaded data.
            </Typography>
            <Button
              size="small"
              onClick={() => {
                void query.refetch();
              }}
            >
              Retry
            </Button>
          </Box>
        )}
      </>
    );
  }
  if (!query.isError) return skeleton;
  return (
    <ErrorState
      title={errorTitle}
      message={userMessage(query.error)}
      onRetry={() => void query.refetch()}
    />
  );
}
