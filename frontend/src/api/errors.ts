import type { FieldIssue } from './types';

/** Every failed API call surfaces as this, including network failures (status 0). */
export class ApiError extends Error {
  readonly code: string;
  readonly status: number;
  readonly requestId: string;
  readonly details: FieldIssue[];

  constructor(init: {
    code: string;
    message: string;
    status: number;
    requestId?: string;
    details?: FieldIssue[] | null;
  }) {
    super(init.message);
    this.name = 'ApiError';
    this.code = init.code;
    this.status = init.status;
    this.requestId = init.requestId ?? '';
    this.details = init.details ?? [];
  }

  get isNetworkError(): boolean {
    return this.status === 0;
  }

  get isRateLimited(): boolean {
    return this.status === 429;
  }

  /** Server message for one form field, if the server flagged it. */
  fieldMessage(field: string): string | undefined {
    return this.details.find((d) => d.field === field)?.message;
  }
}

export function isApiError(value: unknown): value is ApiError {
  return value instanceof ApiError;
}

export const SERVER_PROBLEM_MESSAGE = 'Something went wrong on our side. Please try again.';

/**
 * The one policy for turning a failure into words for the user: rate limits and server-sent
 * 4xx messages are shown as written; network failures and 5xx get the generic sentence.
 */
export function userMessage(error: unknown, fallback = SERVER_PROBLEM_MESSAGE): string {
  if (!isApiError(error)) return fallback;
  if (error.isRateLimited) return error.message;
  if (error.isNetworkError || error.status >= 500) return SERVER_PROBLEM_MESSAGE;
  return error.message || fallback;
}
