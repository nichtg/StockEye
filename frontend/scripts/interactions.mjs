// Interaction screenshots: indicators, hover tooltip, search dropdown, mobile sheet.
import { chromium } from 'playwright';
import { fileURLToPath } from 'node:url';

const BASE = process.env.BASE_URL ?? 'http://localhost:5173';
const OUT = fileURLToPath(new URL('../screenshots/', import.meta.url));
const email = `inter-${Date.now()}@example.com`;
const password = `Test-pass-${Date.now()}-xyz`;

const browser = await chromium.launch();
{
  const ctx = await browser.newContext();
  const page = await ctx.newPage();
  await page.goto(`${BASE}/register`);
  await page.locator('input[name=email]').fill(email);
  await page.locator('input[name=password]').fill(password);
  await page.locator('button[type=submit]').click();
  await page.waitForURL(`${BASE}/`);
  await ctx.close();
}

async function login(viewport, scheme) {
  const ctx = await browser.newContext({ viewport, colorScheme: scheme });
  const page = await ctx.newPage();
  page.on('console', (m) => {
    if (m.type() === 'error' && !m.text().includes('401')) console.log('[console]', m.text());
  });
  await page.goto(`${BASE}/login`);
  await page.locator('input[name=email]').fill(email);
  await page.locator('input[name=password]').fill(password);
  await page.locator('button[type=submit]').click();
  await page.waitForURL(`${BASE}/`);
  return page;
}

{
  const page = await login({ width: 1440, height: 1000 }, 'light');
  await page.goto(`${BASE}/stock/AAPL`);
  await page.waitForTimeout(4000);
  for (const name of ['RSI', 'MACD', 'Bollinger'])
    await page.getByRole('button', { name, exact: true }).click();
  await page.waitForTimeout(2500);
  const box = await page.locator('[role=img]').first().boundingBox();
  await page.mouse.move(box.x + box.width * 0.5, box.y + 150);
  await page.waitForTimeout(500);
  await page.screenshot({
    path: `${OUT}chart-panes-hover-light.png`,
    clip: { x: 0, y: 250, width: 1440, height: 950 },
    fullPage: true,
  });
  await page
    .getByRole('button', { name: '1W range' })
    .click()
    .catch(() => page.getByRole('button', { name: '1W' }).first().click());
  await page.waitForTimeout(3000);
  await page.screenshot({
    path: `${OUT}chart-1w-light.png`,
    clip: { x: 0, y: 250, width: 1440, height: 950 },
    fullPage: true,
  });
  await page.locator('input[aria-label="Search for a stock"]').fill('dbs');
  await page.waitForTimeout(2500);
  await page.screenshot({
    path: `${OUT}search-light.png`,
    clip: { x: 0, y: 0, width: 1440, height: 400 },
  });
  // keyboard: arrow through bars
  await page.keyboard.press('Escape');
  await page.getByRole('group', { name: /Price chart/ }).focus();
  await page.keyboard.press('ArrowLeft');
  await page.keyboard.press('ArrowLeft');
  await page.waitForTimeout(400);
  await page.screenshot({
    path: `${OUT}chart-keyboard-light.png`,
    clip: { x: 0, y: 250, width: 1440, height: 950 },
    fullPage: true,
  });
  await page.context().close();
}

{
  const page = await login({ width: 375, height: 812 }, 'dark');
  await page.waitForTimeout(5000);
  await page.screenshot({ path: `${OUT}home-mobile-dark2.png` });
  await page
    .getByRole('button', { name: /search/i })
    .first()
    .click();
  await page.locator('input[aria-label="Search for a stock"]').fill('dbs');
  await page.waitForTimeout(2500);
  await page.screenshot({ path: `${OUT}search-sheet-mobile-dark.png` });
  await page.context().close();
}
await browser.close();
