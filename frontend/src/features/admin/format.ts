import type { AdminUser } from '../../api/types';

const STATUS_LABELS: Record<AdminUser['status'], string> = {
  active: 'Active',
  disabled: 'Disabled',
  deleting: 'Being deleted',
};

/** Exhaustive on purpose: a new status from the API fails typecheck until it is worded here. */
export function statusLabel(status: AdminUser['status']): string {
  return STATUS_LABELS[status];
}

export function formatAbsolute(iso: string): string {
  return new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' }).format(
    new Date(iso),
  );
}

export function formatAdminDate(iso: string): string {
  return new Intl.DateTimeFormat(undefined, { dateStyle: 'medium' }).format(new Date(iso));
}

/** Local time of day; adds the date when the moment is not today. */
export function formatReset(iso: string, now: number = Date.now()): string {
  const date = new Date(iso);
  const sameDay = date.toDateString() === new Date(now).toDateString();
  return new Intl.DateTimeFormat(
    undefined,
    sameDay ? { timeStyle: 'short' } : { dateStyle: 'medium', timeStyle: 'short' },
  ).format(date);
}
