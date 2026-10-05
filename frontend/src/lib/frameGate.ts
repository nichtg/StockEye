/**
 * Clickjacking defence for hosts that cannot send frame-ancestors (GitHub Pages). index.html hides
 * the page with CSS; only a top-level window reveals it. A framed copy stays hidden and tries to
 * break out of the frame.
 */
export function frameGate(win: Window = window): boolean {
  if (win.top === win.self) {
    win.document.documentElement.style.visibility = 'visible';
    return true;
  }
  try {
    if (win.top) win.top.location.href = win.self.location.href;
  } catch {
    // A sandboxed frame may forbid navigating the top window; the page simply stays hidden.
  }
  return false;
}

/** Runs `start` (session init, render) only in a top-level window; a framed copy does nothing. */
export function startIfTopLevel(start: () => void, win: Window = window): boolean {
  if (!frameGate(win)) return false;
  start();
  return true;
}
