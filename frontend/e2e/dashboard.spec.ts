import { expect, test, type Page, type TestInfo } from '@playwright/test';

/** These tests exercise the real API/engine with explicitly synthetic candles.
 * They do not demonstrate live Binance access or predictive performance. */
interface TestAnalysis {
  analysis_id: string;
  market: string;
  summary: { symbol: string; quality: string; reference_price: number | null };
  cache: { hit: boolean };
  analysis: {
    as_of_ms: number;
    provenance: { source: string; simulated: boolean };
    predictions: Array<{
      horizon_days: number;
      status: string;
      probabilities: Record<string, number> | null;
      return_distribution: unknown | null;
    }>;
  };
  charts: Record<
    string,
    {
      candles: Array<{ time_ms: number; close: number }>;
      events: Array<{
        event_time_ms: number;
        available_at_ms: number;
        detected_at_ms: number;
        confirmed_at_ms: number | null;
      }>;
    }
  >;
}

const tabNames = ['Visão geral', 'Gráfico', 'Estrutura', 'Wyckoff', 'Previsões', 'Auditoria'];

async function analyze(page: Page, symbol = 'BTCUSDT'): Promise<TestAnalysis> {
  await page.getByRole('textbox', { name: 'Símbolo', exact: true }).fill(symbol);
  const resultResponse = page.waitForResponse((response) =>
    /^\/api\/v1\/analyses\/[^/]+$/.test(new URL(response.url()).pathname)
    && response.request().method() === 'GET'
    && response.status() === 200,
  );
  await page.getByRole('button', { name: 'Analisar', exact: true }).click();
  const result = await (await resultResponse).json() as TestAnalysis;
  await expect(page.locator(`[data-analysis-id="${result.analysis_id}"]`)).toBeVisible();
  return result;
}

async function selectTab(page: Page, name: string): Promise<void> {
  await page.getByRole('tab', { name, exact: true }).click();
  await expect(page.getByRole('tab', { name, exact: true })).toHaveAttribute('aria-selected', 'true');
}

async function screenshot(page: Page, testInfo: TestInfo, name: string): Promise<void> {
  await page.screenshot({
    path: testInfo.outputPath(`synthetic-${testInfo.project.name}-${name}.png`),
    fullPage: true,
  });
}

test.beforeEach(async ({ page }) => {
  await page.goto('/');
});

test('symbol entry calls the Python engine and discloses synthetic provenance', async ({ page }, testInfo) => {
  const result = await analyze(page);
  expect(result.market).toBe('spot');
  expect(result.summary.symbol).toBe('BTCUSDT');
  expect(result.summary.reference_price).toBe(109);
  expect(result.analysis.provenance.source).toBe('simulated');
  expect(result.analysis.provenance.simulated).toBe(true);
  await expect(page.getByText('SIMULATED · DADOS SINTÉTICOS DE TESTE', { exact: true })).toBeVisible();
  await expect(page.getByRole('tab', { name: 'Visão geral', exact: true })).toHaveAttribute('aria-selected', 'true');
  await screenshot(page, testInfo, 'overview');
});

test('all panels preserve the result instead of fetching or fitting again', async ({ page }) => {
  const result = await analyze(page);
  let submissions = 0;
  page.on('request', (request) => {
    if (new URL(request.url()).pathname === '/api/v1/analyses' && request.method() === 'POST') submissions += 1;
  });
  for (const name of tabNames) {
    await selectTab(page, name);
    await expect(page.locator('[data-analysis-id]')).toHaveAttribute('data-analysis-id', result.analysis_id);
  }
  expect(submissions).toBe(0);
});

test('chart renders actual OHLCV for H1 H4 and D1 without invented weekly bars', async ({ page }, testInfo) => {
  const result = await analyze(page);
  await selectTab(page, 'Gráfico');
  for (const interval of ['H1', 'H4', 'D1']) {
    await page.getByRole('button', { name: interval, exact: true }).click();
    expect(result.charts[interval].candles).toHaveLength(250);
    expect(result.charts[interval].candles.at(-1)?.close).toBe(109);
    await expect(page.locator('canvas').first()).toBeVisible();
    const size = await page.locator('canvas').first().boundingBox();
    expect(size?.width).toBeGreaterThan(100);
    expect(size?.height).toBeGreaterThan(100);
  }
  await expect(page.getByRole('button', { name: 'W1', exact: true })).toBeDisabled();
  await screenshot(page, testInfo, 'chart');
});

test('chart events retain chart, detection and confirmation availability separately', async ({ page }) => {
  const result = await analyze(page);
  const events = Object.values(result.charts).flatMap((chart) => chart.events);
  expect(events.length).toBeGreaterThan(0);
  expect(events.some((event) => event.available_at_ms > event.event_time_ms)).toBe(true);
  for (const event of events) {
    expect(event.detected_at_ms).toBeGreaterThanOrEqual(event.event_time_ms);
    expect(event.available_at_ms).toBeGreaterThanOrEqual(event.detected_at_ms);
    expect(event.available_at_ms).toBeLessThanOrEqual(result.analysis.as_of_ms);
    if (event.confirmed_at_ms !== null) expect(event.confirmed_at_ms).toBeLessThanOrEqual(result.analysis.as_of_ms);
  }
  await selectTab(page, 'Estrutura');
  await expect(page.getByText(/Disponível|Detectado|Detecção|Confirmação/).first()).toBeVisible();
});

test('chart layers and event inspector remain interactive', async ({ page }) => {
  await analyze(page);
  await selectTab(page, 'Gráfico');
  for (const label of ['Médias', 'Estrutura', 'Wyckoff']) {
    const toggle = page.getByRole('checkbox', { name: label, exact: true });
    await expect(toggle).toBeChecked();
    await toggle.uncheck();
    await expect(toggle).not.toBeChecked();
    await toggle.check();
  }
  await page.getByRole('checkbox', { name: 'Origens retrospectivas', exact: true }).check();
  await expect(page.getByText(/Origens históricas são retrospectivas/)).toBeVisible();
  await page.getByText(/^Inspecionar eventos e disponibilidade/).click();
  await expect(page.getByTestId('event-inspector')).toBeVisible();
  await expect(page.getByText('Posição histórica', { exact: true }).first()).toBeVisible();
  await expect(page.getByText('Primeira detecção', { exact: true }).first()).toBeVisible();
  await expect(page.getByText('Revisão disponível em', { exact: true })).toBeVisible();
  await expect(page.getByTestId('financial-chart').locator('canvas').first()).toBeVisible();
});

test('Wyckoff interpretations display their confirmation state', async ({ page }) => {
  await analyze(page);
  await selectTab(page, 'Wyckoff');
  await expect(page.getByText(/hipóteses|interpretações/i).first()).toBeVisible();
  await expect(page.getByText(/Candidato|Confirmado|Invalidado|Evidência insuficiente/).first()).toBeVisible();
});

test('unavailable probabilities never become zero or fifty percent forecasts', async ({ page }) => {
  const result = await analyze(page);
  expect(result.analysis.predictions.map((prediction) => prediction.horizon_days)).toEqual([7, 30, 90]);
  for (const prediction of result.analysis.predictions) {
    expect(prediction.status).toBe('INSUFFICIENT_EVIDENCE');
    expect(prediction.probabilities).toBeNull();
    expect(prediction.return_distribution).toBeNull();
  }
  await selectTab(page, 'Previsões');
  await expect(page.getByText('Evidência insuficiente', { exact: true }).first()).toBeVisible();
  await expect(page.getByRole('tabpanel').getByText('Probabilidades indisponíveis', { exact: true })).toHaveCount(3);
  await expect(page.getByRole('tabpanel').getByText('Probabilidades indisponíveis', { exact: true }).first()).toBeVisible();
  await expect(page.getByTestId('prediction-probabilities')).toHaveCount(0);
  await expect(page.getByText(/^0\s?%$|^50\s?%$/)).toHaveCount(0);
});

test('audit explicitly explains absence of a configured validated model', async ({ page }) => {
  await analyze(page);
  await selectTab(page, 'Auditoria');
  await expect(page.getByRole('heading', { name: 'Nenhum modelo previamente treinado configurado', exact: true })).toBeVisible();
  await expect(page.getByRole('tabpanel').getByText(/Métricas históricas não garantem desempenho futuro/)).toBeVisible();
});

test('invalid symbol format is rejected before submitting an analysis', async ({ page }) => {
  let submitted = false;
  page.on('request', (request) => {
    if (new URL(request.url()).pathname === '/api/v1/analyses' && request.method() === 'POST') submitted = true;
  });
  await page.getByRole('textbox', { name: 'Símbolo', exact: true }).fill('BTC/USDT');
  await page.getByRole('button', { name: 'Analisar', exact: true }).click();
  await expect(page.getByRole('alert')).toBeVisible();
  expect(submitted).toBe(false);
  await expect(page.locator('[data-analysis-id]')).toHaveCount(0);
});

test('unlisted spot symbol returns a clear provider error', async ({ page }) => {
  await page.getByRole('textbox', { name: 'Símbolo', exact: true }).fill('NOTLISTEDUSDT');
  await page.getByRole('button', { name: 'Analisar', exact: true }).click();
  await expect(page.getByRole('alert')).toBeVisible();
  await expect(page.locator('[data-analysis-id]')).toHaveCount(0);
});

test('insufficient history stays usable and exposes degraded data quality', async ({ page }) => {
  const result = await analyze(page, 'SHORTUSDT');
  expect(result.summary.quality).toBe('degraded');
  expect(result.charts.H1.candles).toHaveLength(5);
  expect(result.analysis.predictions.every((prediction) => prediction.probabilities === null)).toBe(true);
  await expect(page.getByText(/insuficiente|degradada|incomplet/i).first()).toBeVisible();
  await selectTab(page, 'Previsões');
  await expect(page.getByText('Evidência insuficiente', { exact: true }).first()).toBeVisible();
});

test('temporary source failure does not masquerade as the prior successful result', async ({ page }) => {
  const previous = await analyze(page);
  await page.getByRole('textbox', { name: 'Símbolo', exact: true }).fill('FAILUSDT');
  await page.getByRole('button', { name: 'Analisar', exact: true }).click();
  await expect(page.getByRole('alert')).toBeVisible();
  await expect(page.locator('[data-analysis-id]')).toHaveAttribute('data-analysis-id', previous.analysis_id);
  await expect(page.getByText(/análise anterior foi preservada/i)).toBeVisible();
  await expect(page.getByRole('heading', { name: /FAILUSDT/ })).toHaveCount(0);
  await expect(page.getByRole('alert')).toContainText(/fonte|Binance|indisponível|falha/i);
});

test('analysis cache returns the same versioned result', async ({ page }) => {
  const first = await analyze(page);
  const second = await analyze(page);
  expect(second.analysis_id).toBe(first.analysis_id);
  expect(second.cache.hit).toBe(true);
});

test('keyboard can activate navigation without losing analysis', async ({ page }) => {
  const result = await analyze(page);
  const predictionTab = page.getByRole('tab', { name: 'Previsões', exact: true });
  await predictionTab.focus();
  await page.keyboard.press('Enter');
  await expect(predictionTab).toHaveAttribute('aria-selected', 'true');
  await expect(page.locator('[data-analysis-id]')).toHaveAttribute('data-analysis-id', result.analysis_id);
  await page.keyboard.press('ArrowRight');
  await expect(page.getByRole('tab', { name: 'Auditoria', exact: true })).toBeFocused();
  await page.keyboard.press('Home');
  await expect(page.getByRole('tab', { name: 'Visão geral', exact: true })).toBeFocused();
  await page.keyboard.press('End');
  await expect(page.getByRole('tab', { name: 'Auditoria', exact: true })).toHaveAttribute('aria-selected', 'true');
});

test('small viewports retain touch targets and contain horizontal scrolling', async ({ page }) => {
  await analyze(page);
  for (const name of tabNames) {
    await selectTab(page, name);
    const overflowing = await page.evaluate(() =>
      document.documentElement.scrollWidth > document.documentElement.clientWidth + 1,
    );
    expect(overflowing, `body overflow in ${name}`).toBe(false);
  }
  const search = await page.getByRole('button', { name: 'Analisar', exact: true }).boundingBox();
  expect(search?.height).toBeGreaterThanOrEqual(44);
  expect(search?.width).toBeGreaterThanOrEqual(44);
  for (const name of tabNames) {
    const box = await page.getByRole('tab', { name, exact: true }).boundingBox();
    expect(box?.height).toBeGreaterThanOrEqual(44);
  }
});
