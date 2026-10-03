import type { UseQueryResult } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryRegion } from './QueryRegion';

function result(partial: Partial<UseQueryResult<string>>) {
  return partial as UseQueryResult<string>;
}

const props = {
  skeleton: <p>loading</p>,
  errorTitle: 'Can’t load',
  children: (d: string) => <p>{d}</p>,
};

describe('QueryRegion', () => {
  it('shows the skeleton while pending and a retryable error on a failed first load', () => {
    const { rerender } = render(<QueryRegion query={result({ isError: false })} {...props} />);
    expect(screen.getByText('loading')).toBeInTheDocument();
    rerender(
      <QueryRegion
        query={result({ isError: true, error: new Error('x'), refetch: vi.fn() })}
        {...props}
      />,
    );
    expect(screen.getByRole('button', { name: 'Try again' })).toBeInTheDocument();
  });

  it('keeps the last data when a refresh fails, with a note and Retry', async () => {
    const refetch = vi.fn();
    render(<QueryRegion query={result({ data: 'old rows', isError: true, refetch })} {...props} />);
    expect(screen.getByText('old rows')).toBeInTheDocument();
    expect(screen.getByText('Couldn’t refresh. Showing the last loaded data.')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Retry' }));
    expect(refetch).toHaveBeenCalled();
  });

  it('shows no note when the data is fresh', () => {
    render(<QueryRegion query={result({ data: 'rows', isError: false })} {...props} />);
    expect(screen.queryByText(/Couldn’t refresh/)).not.toBeInTheDocument();
  });
});
