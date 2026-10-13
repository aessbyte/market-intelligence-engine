import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import App from './App';
import { analyzeSymbol } from './api';
import type { Timeframe, WebAnalysis } from './contracts';
import { testFixture } from './test/fixture';
import { AuditPanel, ForecastPanel } from './components/Panels';

vi.mock('./api', () => ({ analyzeSymbol: vi.fn() }));
vi.mock('./components/ChartPanel', () => ({ default: ({ timeframe, onTimeframeChange }: { timeframe: Timeframe; onTimeframeChange: (frame: Timeframe) => void }) =>
  <section aria-label={`Gráfico integrado ${timeframe}`}><button type="button" onClick={() => onTimeframeChange('H1')}>Usar intervalo H1</button></section> }));

function fixture(): WebAnalysis { return structuredClone(testFixture); }
async function load(data = fixture()) {
  vi.mocked(analyzeSymbol).mockResolvedValue(data);
  const user = userEvent.setup();
  render(<App />);
  await user.click(screen.getByRole('button', { name: 'Analisar' }));
  await screen.findByRole('tab', { name: 'Visão geral' });
  return user;
}

beforeEach(() => { vi.mocked(analyzeSymbol).mockReset(); localStorage.clear(); });

describe('Dashboard integrado ao motor', () => {
  it('abre com busca e explicação, sem fabricar uma análise inicial', () => {
    render(<App />);
    expect(screen.getByRole('textbox', { name: 'Símbolo' })).toHaveValue('BTCUSDT');
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('O mercado, através das evidências.');
    expect(screen.queryByRole('tab')).not.toBeInTheDocument();
    expect(analyzeSymbol).not.toHaveBeenCalled();
    expect(screen.getByRole('option', { name: 'Futuros indisponíveis' })).toBeDisabled();
  });

  it('rejeita símbolos com caracteres inválidos antes de chamar a API', async () => {
    const user = userEvent.setup(); render(<App />);
    const input = screen.getByRole('textbox', { name: 'Símbolo' });
    await user.clear(input); await user.type(input, '../BTC');
    await user.click(screen.getByRole('button', { name: 'Analisar' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('5 a 30 letras ou números');
    expect(analyzeSymbol).not.toHaveBeenCalled();
  });

  it('consome a resposta estruturada e identifica dados sintéticos', async () => {
    const data = fixture(); await load(data);
    expect(analyzeSymbol).toHaveBeenCalledWith('BTCUSDT', 'spot', expect.any(Function));
    expect(screen.getByText('SIMULATED · DADOS SINTÉTICOS DE TESTE')).toBeVisible();
    expect(document.querySelector('[data-analysis-id]')).toHaveAttribute('data-analysis-id', data.analysis_id);
    expect(screen.getByRole('region', { name: 'Gráfico integrado H4' })).toBeInTheDocument();
  });

  it('mostra progresso recebido do backend sem percentual inventado', async () => {
    let finish: (value: WebAnalysis) => void = () => {};
    vi.mocked(analyzeSymbol).mockImplementation((_symbol, _market, onProgress) => {
      onProgress?.({ stage: 'fetching', status: 'running', message: 'Obtendo candles fechados da Binance' });
      return new Promise(resolve => { finish = resolve; });
    });
    const user = userEvent.setup(); render(<App />);
    await user.click(screen.getByRole('button', { name: 'Analisar' }));
    expect(screen.getByRole('status')).toHaveTextContent('Obtendo candles fechados da Binance');
    expect(screen.getByRole('status')).not.toHaveTextContent('%');
    finish(fixture()); await screen.findByRole('tab', { name: 'Visão geral' });
  });

  it('preserva a análise e o intervalo durante a navegação sem novas consultas', async () => {
    const user = await load();
    await user.click(screen.getByRole('button', { name: 'Usar intervalo H1' }));
    await user.click(screen.getByRole('tab', { name: 'Estrutura' }));
    expect(screen.getByRole('heading', { name: 'Estrutura de mercado' })).toBeVisible();
    await user.click(screen.getByRole('tab', { name: 'Gráfico' }));
    expect(screen.getByRole('region', { name: 'Gráfico integrado H1' })).toBeVisible();
    expect(analyzeSymbol).toHaveBeenCalledTimes(1);
  });

  it('mantém probabilidades públicas indisponíveis e não as substitui por defaults', async () => {
    const user = await load();
    await user.click(screen.getByRole('tab', { name: 'Previsões' }));
    expect(screen.getAllByText('Probabilidades indisponíveis')).toHaveLength(3);
    expect(screen.queryByTestId('prediction-probabilities')).not.toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Previsões e incerteza' })).toBeVisible();
  });

  it('trata falha da fonte sem fallback fictício e preserva o resultado anterior', async () => {
    const user = await load();
    vi.mocked(analyzeSymbol).mockRejectedValue(new Error('Binance temporariamente indisponível.'));
    await user.click(screen.getByRole('button', { name: 'Analisar' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Binance temporariamente indisponível.');
    expect(screen.getByRole('alert')).toHaveTextContent('A análise anterior foi preservada');
    expect(document.querySelector('[data-analysis-id]')).toHaveAttribute('data-analysis-id', testFixture.analysis_id);
  });

  it('identifica uma captura histórica como replay em vez de cotação atual', async () => {
    const data = fixture(); data.mode = 'replay'; await load(data);
    expect(screen.getByText('REPLAY HISTÓRICO')).toBeVisible();
    expect(screen.getByText(/Não é uma cotação atual/)).toBeVisible();
  });

  it('permite navegar pelas abas usando teclado e conserva a análise', async () => {
    const user = await load();
    screen.getByRole('tab', { name: 'Visão geral' }).focus();
    await user.keyboard('{ArrowRight}');
    expect(screen.getByRole('tab', { name: 'Gráfico' })).toHaveFocus();
    expect(screen.getByRole('tab', { name: 'Gráfico' })).toHaveAttribute('aria-selected', 'true');
    await user.keyboard('{End}');
    expect(screen.getByRole('tab', { name: 'Auditoria' })).toHaveFocus();
    expect(analyzeSymbol).toHaveBeenCalledTimes(1);
  });

  it('oferece tema claro persistido localmente', async () => {
    const user = userEvent.setup(); render(<App />);
    await user.click(screen.getByRole('button', { name: 'Ativar tema claro' }));
    expect(document.documentElement.dataset.theme).toBe('light');
    expect(localStorage.getItem('mie-theme')).toBe('light');
  });

  it('exibe insuficiência do intervalo sem quebrar o painel de estrutura', async () => {
    const data = fixture(); data.analysis.timeframes.H4.structure = null; data.analysis.timeframes.H4.indicators = null;
    data.analysis.timeframes.H4.quality.valid = false;
    const user = await load(data);
    await user.click(screen.getByRole('tab', { name: 'Estrutura' }));
    expect(screen.getByRole('heading', { name: 'Estrutura indisponível' })).toBeVisible();
  });
});

describe('Painéis de previsão e auditoria', () => {
  it('tolera probabilidades experimentais ausentes sem preencher números', async () => {
    const data = fixture();
    data.analysis.predictions[0].experimental_diagnostics = { status: 'EXPERIMENTAL_NOT_VALIDATED', probabilities: null, return_distribution: null, use: 'research_only_not_a_validated_forecast' };
    const user = userEvent.setup(); render(<ForecastPanel data={data} />);
    await user.click(screen.getByText('Diagnóstico experimental · pesquisa'));
    expect(screen.getByText('Probabilidades experimentais indisponíveis.')).toBeVisible();
    expect(screen.queryByTestId('prediction-probabilities')).not.toBeInTheDocument();
  });

  it('exibe a cobertura real contida no objeto de métricas sem confundi-la com treinamento', () => {
    const data = fixture();
    data.model_quality.configured = true;
    data.model_quality.horizons = { '7': {
      status: 'UNVALIDATED_MODEL', model_kind: 'frequency', training_start_ms: data.analysis.as_of_ms - 2000,
      training_end_ms: data.analysis.as_of_ms - 1000, final_test_start_ms: data.analysis.as_of_ms - 1000,
      final_test_end_ms: data.analysis.as_of_ms, selected_strategy_metrics: { observations: 100, brier: .65, log_loss: 1.07, ece: .03 },
      final_test_metrics: { observations: 18, brier: .63, log_loss: 1.05, ece: .005 }, comparisons: [],
      calibration: { status: 'CALIBRATED', independent_observations: 26 }, coverage: { coverage: .8176593521421107 },
      final_coverage: { coverage: .871 }, paired_comparison: null, limitations: [],
    } };
    render(<AuditPanel data={data} />);
    const row = screen.getByText('Estratégia walk-forward · OOS agregado').closest('tr');
    expect(row).not.toBeNull(); expect(within(row!).getByText('81,8%')).toBeVisible();
    expect(screen.getByText('87,1%')).toBeVisible();
    expect(screen.getByText('Modelo congelado · teste final')).toBeVisible();
  });
});
