// Live walkthrough: registers a throwaway user against the local stack and saves screenshots.
// Usage: node scripts/screenshots.mjs   (backend on :8000, `npm run dev` on :5173)
import { chromium } from 'playwright';
import { mkdirSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

const BASE = process.env.BASE_URL ?? 'http://localhost:5173';
const OUT = fileURLToPath(new URL('../screenshots/', import.meta.url));
mkdirSync(OUT, { recursive: true });

const email = `shots-${Date.now()}@example.com`;
const password = `Test-pass-${Date.now()}-xyz`;

const browser = await chromium.launch();

async function session(viewport, mode) {
  const ctx = await browser.newContext({ viewport, colorScheme: mode, deviceScaleFactor: 1 });
  const page = await ctx.newPage();
  page.on('console', (m) => {
    if (m.type() === 'error') console.log(`[console ${viewport.width}] ${m.text()}`);
  });
  await page.goto(`${BASE}/login`);
  await page.locator('input[name=email]').fill(email);
  await page.locator('input[name=password]').fill(password);
  await page.locator('button[type=submit]').click();
  await page.waitForURL(`${BASE}/`, { timeout: 15000 }).catch(() => undefined);
  return { ctx, page };
}

// Register once.
{
  const ctx = await browser.newContext();
  const page = await ctx.newPage();
  await page.goto(`${BASE}/register`);
  await page.locator('input[name=email]').fill(email);
  await page.locator('input[name=password]').fill(password);
  await page.locator('button[type=submit]').click();
  await page.waitForURL(`${BASE}/`, { timeout: 15000 });
  // Seed the watchlist through the UI's own API calls.
  await page.evaluate(
    async ({ email, password }) => {
      // Tokens are not readable from the page, so sign in again for a bearer token.
      const login = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password }),
      });
      const { access_token } = await login.json();
      for (const s of ['AAPL', 'D05.SI', 'MSFT', 'ZZZZ']) {
        await fetch(`/api/watchlist/${s}`, {
          method: 'PUT',
          headers: { Authorization: `Bearer ${access_token}` },
        });
      }
    },
    { email, password },
  );
  await ctx.close();
}

const DESKTOP = { width: 1440, height: 900 };
const MOBILE = { width: 375, height: 812 };

// The curated set kept in screenshots/; anything else there is stale.
const SET = [
  { file: 'home-desktop-light', mode: 'light', viewport: DESKTOP, path: '/', wait: 6000 },
  { file: 'home-desktop-dark', mode: 'dark', viewport: DESKTOP, path: '/', wait: 6000 },
  { file: 'home-mobile-light', mode: 'light', viewport: MOBILE, path: '/', wait: 6000 },
  { file: 'stock-AAPL-desktop-light', mode: 'light', viewport: DESKTOP, path: '/stock/AAPL' },
  { file: 'stock-AAPL-desktop-dark', mode: 'dark', viewport: DESKTOP, path: '/stock/AAPL' },
  { file: 'stock-AAPL-mobile-dark', mode: 'dark', viewport: MOBILE, path: '/stock/AAPL' },
  {
    file: 'stock-D05.SI-macro-desktop-light',
    mode: 'light',
    viewport: DESKTOP,
    path: '/stock/D05.SI?tab=macro',
  },
];

for (const { file, mode, viewport, path, wait = 5000 } of SET) {
  const { ctx, page } = await session(viewport, mode);
  await page.goto(`${BASE}${path}`);
  await page.waitForTimeout(wait);
  if (path.includes('tab=macro')) {
    // First visit to a symbol collects two years of news; wait for it (up to 4 minutes).
    await page
      .getByText(/Collecting news/)
      .waitFor({ state: 'detached', timeout: 240000 })
      .catch(() => undefined);
    await page.waitForTimeout(1500);
  }
  await page.screenshot({ path: `${OUT}${file}.png`, fullPage: true });
  await ctx.close();
}

// Admin: needs SE_ADMIN_EMAIL and SE_ADMIN_PASSWORD in the environment (an existing admin account).
if (process.env.SE_ADMIN_EMAIL && process.env.SE_ADMIN_PASSWORD) {
  const ctx = await browser.newContext({ viewport: DESKTOP, colorScheme: 'light' });
  const page = await ctx.newPage();
  await page.goto(`${BASE}/login`);
  await page.locator('input[name=email]').fill(process.env.SE_ADMIN_EMAIL);
  await page.locator('input[name=password]').fill(process.env.SE_ADMIN_PASSWORD);
  await page.locator('button[type=submit]').click();
  await page.waitForURL(`${BASE}/`, { timeout: 15000 });
  await page.goto(`${BASE}/admin`);
  await page.waitForTimeout(3000);
  await page.screenshot({ path: `${OUT}admin-desktop-light.png`, fullPage: true });
  await ctx.close();
}

await browser.close();
console.log('saved to', OUT);
