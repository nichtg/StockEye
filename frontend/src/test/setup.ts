import '@testing-library/jest-dom/vitest';
import { cleanup, configure } from '@testing-library/react';
import { afterEach } from 'vitest';
import { tokenStore } from '../api/tokens';

// Full-suite runs load the CPU; a generous async timeout avoids false failures.
configure({ asyncUtilTimeout: 3000 });

afterEach(() => {
  cleanup();
  localStorage.clear();
  tokenStore.clear();
});
