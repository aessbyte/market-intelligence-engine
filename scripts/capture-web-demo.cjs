/** Capture the actual browser/API workflow. Never intercepts requests or supplies fixtures. */
const fs = require('node:fs');
const path = require('node:path');
const { createRequire } = require('node:module');
const root = path.resolve(__dirname, '..');
const { chromium } = createRequire(path.join(root, 'frontend/package.json'))('@playwright/test');
const baseURL = process.env.MIE_DEMO_URL || 'http://127.0.0.1:8000';
const output = path.resolve(process.env.MIE_DEMO_OUTPUT || path.join(root, 'examples/task05'));

async function run() {
  fs.mkdirSync(output, { recursive: true });
  const browser = await chromium.launch({ headless: true });
  const errors = [];
  const results = [];
  try {
    for (const mobile of [false, true]) {
      const context = await browser.newContext({
        viewport: mobile ? { width: 360, height: 800 } : { width: 1440, height: 1000 },
        isMobile: mobile, hasTouch: mobile, deviceScaleFactor: 1,
      });
      const page = await context.newPage();
      page.on('pageerror', error => errors.push(error.message));
      await page.goto(baseURL, { waitUntil: 'networkidle' });
      await page.getByRole('textbox', { name: 'Símbolo' }).fill('BTCUSDT');
      const response = page.waitForResponse(r => /^\/api\/v1\/analyses\/[^/]+$/.test(new URL(r.url()).pathname) && r.status() === 200, { timeout: 120000 });
      await page.getByRole('button', { name: 'Analisar', exact: true }).click();
      const data = await (await response).json();
      if (data.mode !== 'live' || data.analysis.provenance.simulated || data.analysis.provenance.source !== 'binance_public') {
        throw new Error('Real demonstration requires live Binance provenance.');
      }
      await page.locator(`[data-analysis-id="${data.analysis_id}"]`).waitFor({ timeout: 20000 });
      const device = mobile ? 'mobile' : 'desktop';
      for (const [tab, suffix] of [['Visão geral', 'overview'], ['Gráfico', 'chart'], ['Estrutura', 'structure'], ['Wyckoff', 'wyckoff'], ['Previsões', 'forecasts'], ['Auditoria', 'audit']]) {
        await page.getByRole('tab', { name: tab, exact: true }).click();
        if (suffix === 'chart' || suffix === 'overview') await page.locator('canvas').first().waitFor();
        await page.waitForTimeout(200);
        await page.screenshot({ path: path.join(output, `real-binance-${device}-${suffix}.png`), fullPage: true });
      }
      const overflow = await page.evaluate(() => ({ viewport: innerWidth, document: document.documentElement.scrollWidth }));
      results.push({ device, analysis_id: data.analysis_id, summary: data.summary, source: data.analysis.provenance, overflow,
        candles: Object.fromEntries(Object.entries(data.charts).map(([tf, chart]) => [tf, chart.candles.length])),
        predictions: data.analysis.predictions.map(p => ({ horizon_days: p.horizon_days, status: p.status, probabilities: p.probabilities, model_version: p.model_version, limitations: p.limitations })) });
      if (!mobile) fs.writeFileSync(path.join(output, 'live-web-analysis.json'), JSON.stringify(data));
      await page.getByRole('textbox', { name: 'Símbolo' }).fill('BAD/USDT');
      await page.getByRole('button', { name: 'Analisar', exact: true }).click();
      await page.getByRole('alert').waitFor();
      await page.screenshot({ path: path.join(output, `real-${device}-invalid-symbol.png`), fullPage: false });
      await context.close();
    }
    if (errors.length) throw new Error(`Browser errors: ${errors.join('; ')}`);
    const report = { captured_at_utc: new Date().toISOString(), base_url: baseURL, workflow: 'browser -> production API -> existing engine -> public Binance', results, browser_errors: errors,
      limitations: ['Android viewport/touch emulation; not a physical Android device.', 'Synthetic failure/short-history cases are exercised separately by E2E tests.'] };
    fs.writeFileSync(path.join(output, 'live-browser-run.json'), JSON.stringify(report, null, 2));
    console.log(JSON.stringify(report, null, 2));
  } finally { await browser.close(); }
}
run().catch(error => { console.error(error); process.exitCode = 1; });
