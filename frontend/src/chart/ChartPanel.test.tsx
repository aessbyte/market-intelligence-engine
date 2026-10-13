import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { WebAnalysis } from '../contracts';
import ChartPanel from '../components/ChartPanel';

const api = vi.hoisted(() => {
  const setData = vi.fn();
  const series = { setData, createPriceLine: vi.fn() };
  const timeScale = { fitContent: vi.fn(), setVisibleLogicalRange: vi.fn(),
    getVisibleLogicalRange: vi.fn(() => null) };
  const chart = { addSeries: vi.fn(() => series), subscribeCrosshairMove: vi.fn(),
    subscribeClick: vi.fn(), timeScale: () => timeScale, applyOptions: vi.fn(),
    panes: () => [{ setHeight: vi.fn() }, { setHeight: vi.fn() }, { setHeight: vi.fn() }],
    remove: vi.fn() };
  return { chart, markers: vi.fn(), setData };
});
vi.mock('lightweight-charts', () => ({
  createChart: () => api.chart, createSeriesMarkers: api.markers,
  CandlestickSeries: 'candles', HistogramSeries: 'volume', LineSeries: 'line',
  ColorType: { Solid: 'solid' }, LineStyle: { Dashed: 2, Dotted: 1 },
}));

const HOUR = 3_600_000;
const event = { id: 'synthetic-pivot', kind: 'swing_high', state: 'confirmed',
  interval: '1h', event_time_ms: 0, detected_at_ms: HOUR,
  available_at_ms: 3 * HOUR, confirmed_at_ms: 3 * HOUR,
  invalidated_at_ms: null, price: 110, evidence: [{ fixture: 'simulated' }], parameters: {} };
const candle = { time_ms: 0, open: 100, high: 110, low: 90, close: 105, volume: 1000 };
const chart = { candles: Array.from({ length: 4 }, (_, index) => ({ ...candle, time_ms: index * HOUR })),
  events: [event], levels: [], ema20: [], ema50: [], rsi14: [] };
// Synthetic UI fixture; it is never submitted to the real public service.
const fixture = { analysis: { as_of_ms: 4 * HOUR,
  timeframes: { H1: { indicators: { atr14: 2, atr_percent: 2, rsi14: 55 } } } },
  charts: { H1: chart } } as unknown as WebAnalysis;

beforeEach(() => vi.clearAllMocks());
describe('painel financeiro', () => {
  it('consome os candles recebidos, mantém W1 indisponível e permite selecionar H4', () => {
    const change = vi.fn();
    render(<ChartPanel data={fixture} timeframe="H1" onTimeframeChange={change} />);
    expect(api.setData.mock.calls[0][0][0]).toEqual({ time: 0, open: 100, high: 110, low: 90, close: 105 });
    expect(screen.getByRole('button', { name: 'W1' })).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: 'H4' }));
    expect(change).toHaveBeenCalledWith('H4');
  });
  it('marca a confirmação tardia e identifica separadamente a origem retrospectiva', () => {
    render(<ChartPanel data={fixture} timeframe="H1" onTimeframeChange={vi.fn()} />);
    expect(api.markers.mock.calls[0][1]).toHaveLength(1);
    expect(api.markers.mock.calls[0][1][0].time).toBe(2 * HOUR / 1000);
    expect(api.markers.mock.calls[0][1][0].price).toBe(110);
    expect(api.markers.mock.calls[0][1][0].position).toBe('atPriceMiddle');
    fireEvent.click(screen.getByLabelText('Origens retrospectivas'));
    const markers = api.markers.mock.calls.at(-1)?.[1];
    expect(markers).toHaveLength(2);
    expect(markers[0].text).toBe('SH · origem');
    expect(markers[1].text).toBe('SH');
    expect(screen.getByText(/Origens históricas são retrospectivas/)).toBeInTheDocument();
  });
  it('exibe estado, preço e timestamps distintos no inspetor', () => {
    render(<ChartPanel data={fixture} timeframe="H1" onTimeframeChange={vi.fn()} />);
    expect(screen.getByText('CONFIRMED · confirmado por regra')).toBeInTheDocument();
    expect(screen.getByText('Posição histórica')).toBeInTheDocument();
    expect(screen.getByText('Primeira detecção')).toBeInTheDocument();
    expect(screen.getByText('Confirmado em')).toBeInTheDocument();
    expect(screen.getByText('Revisão disponível em')).toBeInTheDocument();
    expect(screen.getByLabelText('Evento do motor')).toHaveValue('synthetic-pivot');
  });
  it('trata candles ausentes sem desenhar dados substitutos', () => {
    const empty = { ...fixture, charts: { H1: { ...chart, candles: [], events: [] } } } as unknown as WebAnalysis;
    render(<ChartPanel data={empty} timeframe="H1" onTimeframeChange={vi.fn()} />);
    expect(screen.getByRole('status')).toHaveTextContent('INSUFFICIENT_EVIDENCE');
    expect(api.markers).not.toHaveBeenCalled();
  });
  it('atualiza as cores do canvas ao alternar o tema sem trocar os dados', async () => {
    const view = render(<ChartPanel data={fixture} timeframe="H1" onTimeframeChange={vi.fn()} />);
    document.documentElement.style.setProperty('--surface', '#ffffff');
    document.documentElement.style.setProperty('--muted', '#304050');
    document.documentElement.dataset.theme = 'light';
    await vi.waitFor(() => expect(api.chart.applyOptions).toHaveBeenCalledWith({
      layout: { background: { type: 'solid', color: '#ffffff' }, textColor: '#304050' },
    }));
    view.unmount();
    document.documentElement.style.removeProperty('--surface');
    document.documentElement.style.removeProperty('--muted');
    delete document.documentElement.dataset.theme;
  });
  it('desenha extremos de range recebidos apenas a partir da sua disponibilidade', () => {
    const withRange = { ...fixture, analysis: { ...fixture.analysis,
      timeframes: { H1: { ...fixture.analysis.timeframes.H1,
        wyckoff: { range: { lower: 90, upper: 110, state: 'candidate',
          available_at_ms: 3 * HOUR } } } } } } as unknown as WebAnalysis;
    render(<ChartPanel data={withRange} timeframe="H1" onTimeframeChange={vi.fn()} />);
    expect(api.setData.mock.calls.some(([points]) =>
      points[0]?.value === 90 && points[0]?.time === 2 * HOUR / 1000)).toBe(true);
    expect(api.setData.mock.calls.some(([points]) =>
      points[0]?.value === 110 && points[0]?.time === 2 * HOUR / 1000)).toBe(true);
    expect(screen.getByText('Range observado · CANDIDATE')).toBeInTheDocument();
  });
});
