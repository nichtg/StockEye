export const FOCUS_SEARCH_EVENT = 'stockeye:focus-search';

/** Asks the search box (desktop field or mobile sheet) to take focus. */
export function focusSearch(): void {
  window.dispatchEvent(new Event(FOCUS_SEARCH_EVENT));
}

export const SEARCH_DEBOUNCE_MS = 250;
