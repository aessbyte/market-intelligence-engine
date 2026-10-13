import { useEffect, useMemo, useRef, useState } from 'react';
import {
  CandlestickSeries, ColorType, createChart, createSeriesMarkers,
  HistogramSeries, LineSeries, LineStyle,
  type IChartApi, type LogicalRange, type SeriesMarker, type Time, type UTCTimestamp,
} from 'lightweight-charts';
import type { EngineEvent, Timeframe, WebAnalysis } from '../contracts';
import {
  candleForAvailability, eventLabel, eventMarkerLabel, eventOverlays, priceDecimals, priceLabel,
  TIMEFRAME_MS, utcLabel, visibleEvents, type ChartCandle,
} from '../chart/events';

interface Props {
  data: WebAnalysis;
  timeframe: Timeframe;
  onTimeframeChange: (timeframe: Timeframe) => void;
}

type Layers = {
  averages: boolean; volume: boolean; structure: boolean; wyckoff: boolean;
  levels: boolean; rsi: boolean; origins: boolean; provisional: boolean;
};
const INITIAL_LAYERS: Layers = {
  averages: true, volume: true, structure: true, wyckoff: true,
  levels: true, rsi: false, origins: false, provisional: false,
};
const LAYER_LABELS: Record<keyof Layers, string> = {
  averages: 'Médias', volume: 'Volume', structure: 'Estrutura',
  wyckoff: 'Wyckoff', levels: 'Níveis', rsi: 'RSI', origins: 'Origens retrospectivas',
  provisional: 'Candidatos / invalidados',
};
const asChartTime = (timeMs: number): UTCTimestamp => (timeMs / 1000) as UTCTimestamp;
const EMPTY_POINTS: { time_ms: number; value: number }[] = [];
const eventState = (event: EngineEvent): string => ({
  candidate: 'CANDIDATE · candidato', confirmed: 'CONFIRMED · confirmado por regra',
  invalidated: 'INVALIDATED · invalidado',
})[event.state];

export default function ChartPanel({ data, timeframe, onTimeframeChange }: Props) {
  const container = useRef<HTMLDivElement>(null);
  const inspector = useRef<HTMLDetailsElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const savedRange = useRef<LogicalRange | null>(null);
  const savedTimeframe = useRef<Timeframe>(timeframe);
  const [layers, setLayers] = useState(INITIAL_LAYERS);
  const [chartError, setChartError] = useState<string | null>(null);
  const [readout, setReadout] = useState<ChartCandle | null>(null);
  const [selectedId, setSelectedId] = useState<string>('');
  const [canvasWidth, setCanvasWidth] = useState(() => typeof window === 'undefined' ? 800 : window.innerWidth);
  const source = data.charts[timeframe];
  const rsiPoints = source.rsi14 ?? EMPTY_POINTS;
  const cutoff = data.analysis.as_of_ms;
  const tickSize = data.summary?.tick_size;
  const formatPrice = (value: number) => priceLabel(value, tickSize);
  const candles = useMemo(() => source.candles.filter((candle) =>
    candle.time_ms + TIMEFRAME_MS[timeframe] <= cutoff,
  ), [source.candles, timeframe, cutoff]);
  const events = useMemo(() => visibleEvents(source.events, cutoff, timeframe),
    [source.events, cutoff, timeframe]);
  const overlays = useMemo(() => eventOverlays(source.events, candles, cutoff, timeframe,
    { structure: layers.structure, wyckoff: layers.wyckoff, origins: layers.origins,
      limit: canvasWidth < 640 ? 4 : 8,
      minSpacingMs: Math.ceil(candles.length * 36 / Math.max(200, canvasWidth - 70)) * TIMEFRAME_MS[timeframe],
      states: layers.provisional ? ['confirmed', 'candidate', 'invalidated'] : ['confirmed'] }),
  [source.events, candles, cutoff, timeframe, canvasWidth, layers.structure, layers.wyckoff, layers.origins, layers.provisional]);
  const selected = events.find((event) => event.id === selectedId) ?? events.at(-1);
  const selectorEvents = events.slice(-100).reverse();
  if (selected && !selectorEvents.some((event) => event.id === selected.id)) selectorEvents.push(selected);
  const knownLevels = useMemo(() => source.levels.filter((level) =>
    Number.isFinite(level.price) && level.price > 0
      && Number.isFinite(level.available_at_ms) && level.available_at_ms <= cutoff,
  ), [source.levels, cutoff]);
  const indicators = data.analysis.timeframes[timeframe].indicators;
  const observedRange = data.analysis.timeframes[timeframe].wyckoff?.range;

  useEffect(() => {
    setReadout(candles.at(-1) ?? null);
    setSelectedId('');
  }, [timeframe, candles]);

  useEffect(() => {
    const host = container.current;
    if (!host || candles.length === 0) return;
    setChartError(null);
    let chart: IChartApi;
    try {
      const colors = getComputedStyle(document.documentElement);
      const background = colors.getPropertyValue('--surface').trim() || '#121923';
      const text = colors.getPropertyValue('--muted').trim() || '#9aabc2';
      chart = createChart(host, {
        width: Math.max(280, host.clientWidth), height: host.clientWidth < 600 ? 360 : 440,
        layout: { background: { type: ColorType.Solid, color: background },
          textColor: text, fontFamily: 'Inter, system-ui, sans-serif', fontSize: 11,
          attributionLogo: true },
        grid: { vertLines: { color: 'rgba(126,149,179,0.065)' },
          horzLines: { color: 'rgba(126,149,179,0.10)' } },
        crosshair: { vertLine: { color: '#8094b2', labelBackgroundColor: '#2c3b51' },
          horzLine: { color: '#8094b2', labelBackgroundColor: '#2c3b51' } },
        rightPriceScale: { borderColor: 'rgba(126,149,179,0.16)',
          scaleMargins: { top: 0.12, bottom: 0.08 } },
        timeScale: { borderColor: 'rgba(126,149,179,0.16)', timeVisible: timeframe !== 'D1',
          secondsVisible: false, rightOffset: 3, minBarSpacing: 2 },
        handleScroll: { mouseWheel: true, pressedMouseMove: true,
          horzTouchDrag: true, vertTouchDrag: false },
        handleScale: { mouseWheel: true, pinch: true,
          axisPressedMouseMove: { time: true, price: true } },
        localization: { locale: 'pt-BR', timeFormatter: (value: Time) =>
          typeof value === 'number' ? utcLabel(value * 1000) : String(value) },
      });
      chartRef.current = chart;
      const lastPrice = candles.at(-1)?.close ?? 1;
      const precision = priceDecimals(lastPrice, tickSize);
      const tick = tickSize == null ? NaN : Number(tickSize);
      const priceSeries = chart.addSeries(CandlestickSeries, {
        upColor: '#38cba0', downColor: '#f17888', borderVisible: false,
        wickUpColor: '#38cba0', wickDownColor: '#f17888',
        priceFormat: { type: 'price', precision,
          minMove: Number.isFinite(tick) && tick > 0 ? tick : 10 ** -precision },
      });
      priceSeries.setData(candles.map((candle) => ({
        time: asChartTime(candle.time_ms), open: candle.open, high: candle.high,
        low: candle.low, close: candle.close,
      })));
      if (layers.averages) {
        for (const [name, points, color] of [
          ['EMA 20', source.ema20, '#e9bc65'], ['EMA 50', source.ema50, '#88a8ff'],
        ] as const) {
          const series = chart.addSeries(LineSeries, { color, lineWidth: 1, title: name,
            priceLineVisible: false, lastValueVisible: false,
            crosshairMarkerVisible: false });
          const candleTimes = new Set(candles.map((candle) => candle.time_ms));
          series.setData(points.filter((point) => candleTimes.has(point.time_ms))
            .map((point) => ({ time: asChartTime(point.time_ms), value: point.value })));
        }
      }
      if (layers.volume) {
        const volume = chart.addSeries(HistogramSeries, { priceFormat: { type: 'volume' },
          priceLineVisible: false, lastValueVisible: false, title: 'Volume' }, 1);
        volume.setData(candles.map((candle) => ({ time: asChartTime(candle.time_ms),
          value: candle.volume, color: candle.close >= candle.open
            ? 'rgba(56,203,160,0.50)' : 'rgba(241,120,136,0.50)' })));
      }
      if (layers.rsi && rsiPoints.length > 0) {
        const pane = layers.volume ? 2 : 1;
        const rsi = chart.addSeries(LineSeries, { color: '#b7a0ee', lineWidth: 1,
          priceFormat: { type: 'price', precision: 1, minMove: 0.1 },
          title: 'RSI 14', priceLineVisible: false, lastValueVisible: false }, pane);
        const candleTimes = new Set(candles.map((candle) => candle.time_ms));
        rsi.setData(rsiPoints.filter((point) => candleTimes.has(point.time_ms))
          .map((point) => ({ time: asChartTime(point.time_ms), value: point.value })));
        rsi.createPriceLine({ price: 70, color: '#b7a0ee55', lineWidth: 1,
          lineStyle: LineStyle.Dashed, axisLabelVisible: false, title: '' });
        rsi.createPriceLine({ price: 30, color: '#b7a0ee55', lineWidth: 1,
          lineStyle: LineStyle.Dashed, axisLabelVisible: false, title: '' });
      }
      if (layers.levels) {
        for (const level of knownLevels) {
          const start = candleForAvailability(candles, level.available_at_ms, timeframe, cutoff);
          const last = candles.at(-1);
          if (!start || !last) continue;
          const line = chart.addSeries(LineSeries, {
            color: level.broken ? '#78889d' : level.kind === 'support' ? '#38cba099'
              : level.kind === 'resistance' ? '#f1788899' : '#91baff99',
            lineWidth: 1, lineStyle: LineStyle.Dashed,
            priceLineVisible: false, lastValueVisible: false,
            crosshairMarkerVisible: false,
          });
          line.setData(start.time_ms === last.time_ms
            ? [{ time: asChartTime(start.time_ms), value: level.price }]
            : [{ time: asChartTime(start.time_ms), value: level.price },
              { time: asChartTime(last.time_ms), value: level.price }]);
        }
      }
      if (layers.wyckoff && observedRange && observedRange.available_at_ms <= cutoff) {
        const start = candleForAvailability(candles, observedRange.available_at_ms, timeframe, cutoff);
        const last = candles.at(-1);
        if (start && last) {
          for (const value of [observedRange.lower, observedRange.upper]) {
            const boundary = chart.addSeries(LineSeries, {
              color: observedRange.state === 'confirmed' ? '#91baff99'
                : observedRange.state === 'candidate' ? '#e9bc6588' : '#78889d88',
              lineWidth: 1, lineStyle: LineStyle.Dotted,
              priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false,
            });
            boundary.setData(start.time_ms === last.time_ms
              ? [{ time: asChartTime(start.time_ms), value }]
              : [{ time: asChartTime(start.time_ms), value },
                { time: asChartTime(last.time_ms), value }]);
          }
        }
      }
      const markers: SeriesMarker<UTCTimestamp>[] = overlays.map((overlay) => ({
        time: asChartTime(overlay.time_ms), position: 'atPriceMiddle', price: overlay.price,
        color: overlay.color, shape: overlay.retrospective ? 'circle' : overlay.direction === 'up'
          ? 'arrowUp' : overlay.direction === 'down' ? 'arrowDown' : 'circle',
        text: eventMarkerLabel(overlay.event, overlay.retrospective),
        size: overlay.retrospective ? 0.4 : 0.65,
      }));
      createSeriesMarkers(priceSeries, markers);
      chart.subscribeCrosshairMove((parameter) => {
        if (typeof parameter.time !== 'number') { setReadout(candles.at(-1) ?? null); return; }
        const candle = candles.find((item) => asChartTime(item.time_ms) === parameter.time);
        setReadout(candle ?? candles.at(-1) ?? null);
      });
      chart.subscribeClick((parameter) => {
        if (typeof parameter.time !== 'number') return;
        const event = overlays.filter((overlay) => !overlay.retrospective
          && asChartTime(overlay.time_ms) === parameter.time).at(-1)?.event;
        if (event) {
          setSelectedId(event.id);
          if (inspector.current) inspector.current.open = true;
        }
      });
      if (savedTimeframe.current === timeframe && savedRange.current) {
        chart.timeScale().setVisibleLogicalRange(savedRange.current);
      } else chart.timeScale().fitContent();
      savedTimeframe.current = timeframe;
    } catch {
      chartRef.current?.remove();
      chartRef.current = null;
      setChartError('O gráfico não pôde ser iniciado neste navegador. Os candles e eventos continuam disponíveis abaixo.');
      return;
    }
    const resize = () => {
      const width = Math.max(280, host.clientWidth);
      setCanvasWidth(width);
      const height = (width < 600 ? 330 : 420) + (layers.volume ? 75 : 0) + (layers.rsi ? 85 : 0);
      chart.applyOptions({ width, height });
      const panes = chart.panes();
      panes[0]?.setHeight(width < 600 ? 300 : 390);
      if (layers.volume) panes[1]?.setHeight(75);
      if (layers.rsi) panes[layers.volume ? 2 : 1]?.setHeight(85);
    };
    const observer = typeof ResizeObserver !== 'undefined' ? new ResizeObserver(resize) : null;
    const updateTheme = () => {
      const colors = getComputedStyle(document.documentElement);
      chart.applyOptions({
        layout: {
          background: { type: ColorType.Solid,
            color: colors.getPropertyValue('--surface').trim() || '#121923' },
          textColor: colors.getPropertyValue('--muted').trim() || '#9aabc2',
        },
      });
    };
    const themeObserver = typeof MutationObserver !== 'undefined'
      ? new MutationObserver(updateTheme) : null;
    themeObserver?.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
    observer?.observe(host);
    window.addEventListener('resize', resize);
    resize();
    return () => {
      observer?.disconnect();
      themeObserver?.disconnect();
      window.removeEventListener('resize', resize);
      savedRange.current = chart.timeScale().getVisibleLogicalRange();
      chart.remove();
      chartRef.current = null;
    };
  }, [candles, source.ema20, source.ema50, rsiPoints, knownLevels, overlays, observedRange,
    timeframe, cutoff, tickSize, layers.averages, layers.volume, layers.levels, layers.rsi]);

  return <section className="chart-panel" aria-label="Gráfico financeiro interativo">
    <div className="chart-toolbar">
      <div className="timeframe-buttons" role="group" aria-label="Intervalo do gráfico">
        {(['H1', 'H4', 'D1'] as Timeframe[]).map((value) => <button type="button"
          key={value} aria-pressed={timeframe === value} className={timeframe === value ? 'selected' : ''}
          onClick={() => onTimeframeChange(value)}>{value}</button>)}
        <button type="button" disabled title="W1 não está disponível no motor atual">W1</button>
      </div>
      <button type="button" className="chart-fit-button" onClick={() => chartRef.current?.timeScale().fitContent()}
        disabled={!candles.length}>Ajustar visão</button>
    </div>
    <div className="chart-overlays" role="group" aria-label="Elementos do gráfico">
      {(Object.keys(LAYER_LABELS) as (keyof Layers)[]).map((key) => <label key={key}>
        <input type="checkbox" checked={layers[key]} onChange={(event) =>
          setLayers((current) => ({ ...current, [key]: event.target.checked }))} />
        <span>{LAYER_LABELS[key]}</span>
      </label>)}
    </div>
    {readout && <div className="chart-readout" aria-live="off" data-testid="chart-readout">
      <span>{utcLabel(readout.time_ms)}</span>
      <span>A <strong>{formatPrice(readout.open)}</strong></span>
      <span>Máx <strong>{formatPrice(readout.high)}</strong></span>
      <span>Mín <strong>{formatPrice(readout.low)}</strong></span>
      <span>F <strong>{formatPrice(readout.close)}</strong></span>
      <span>Vol <strong>{priceLabel(readout.volume)}</strong></span>
    </div>}
    {!candles.length && <p className="empty-state" role="status">
      INSUFFICIENT_EVIDENCE · Nenhum candle fechado válido neste intervalo.</p>}
    {chartError && <p className="notice warning" role="alert">{chartError}</p>}
    <div ref={container} className="chart-canvas" data-testid="financial-chart"
      role="img" aria-label={`Candlesticks ${timeframe}, volume e elementos conhecidos até ${utcLabel(cutoff)}. Dados em tabela abaixo.`} />
    <div className="chart-legend">
      <span><i className="legend-dot positive" /> Alta</span><span><i className="legend-dot negative" /> Queda</span>
      {layers.averages && <><span><i className="legend-dot" style={{ background: '#e9bc65' }} /> EMA 20</span>
        <span><i className="legend-dot" style={{ background: '#88a8ff' }} /> EMA 50</span></>}
      <span>{overlays.filter((overlay) => !overlay.retrospective).length} eventos em destaque</span>
      {layers.wyckoff && observedRange && observedRange.available_at_ms <= cutoff
        && <span><i className="legend-dot" style={{ background: '#91baff' }} />
          Range observado · {observedRange.state.toUpperCase()}</span>}
    </div>
    <p className="chart-causality-note">Os sinais ficam disponíveis <strong>após o fechamento do candle marcado</strong>.
      {' '}O marcador mostra o momento de confirmação, invalidação ou disponibilização do candidato; o preço vem do evento.
      {' '}Anotações reduzidas para legibilidade; todos os eventos permanecem no inspetor.
      {layers.origins && ' Origens históricas são retrospectivas e não eram sinais disponíveis naquele candle.'}
      {' '}Arraste para navegar e use pinça ou scroll para zoom. Toque em um candle anotado para inspecionar o evento. W1 indisponível.</p>
    <div className="chart-indicator-summary">
      <span>RSI 14 <strong>{indicators?.rsi14 == null ? 'Indisponível' : indicators.rsi14.toFixed(1)}</strong></span>
      <span>ATR 14 <strong>{indicators?.atr14 == null ? 'Indisponível' : priceLabel(indicators.atr14)}</strong></span>
      <span>ATR % <strong>{indicators?.atr_percent == null ? 'Indisponível' : `${indicators.atr_percent.toFixed(2)}%`}</strong></span>
    </div>
    <details ref={inspector} className="chart-event-inspector">
      <summary>Inspecionar eventos e disponibilidade · {events.length}</summary>
      {events.length > 0 ? <>
        <label className="field-label" htmlFor="chart-event-select">Evento do motor</label>
        <select id="chart-event-select" value={selected?.id ?? ''}
          onChange={(event) => setSelectedId(event.target.value)}>
          {selectorEvents.map((event) => <option key={event.id} value={event.id}>
            {eventLabel(event)} · {event.state.toUpperCase()} · {utcLabel(event.available_at_ms)}
          </option>)}
        </select>
        {selected && <div className="chart-event-details" data-testid="event-inspector">
          <p><strong>{eventLabel(selected)}</strong> <span className="muted">({eventMarkerLabel(selected)})</span>
            {' '}<span className={`badge ${selected.state}`}>{eventState(selected)}</span></p>
          <dl className="fact-grid">
            <div><dt>Preço registrado</dt><dd>{formatPrice(selected.price)}</dd></div>
            <div><dt>Posição histórica</dt><dd>{utcLabel(selected.event_time_ms)}</dd></div>
            <div><dt>Primeira detecção</dt><dd>{utcLabel(selected.detected_at_ms)}</dd></div>
            <div><dt>Confirmado em</dt><dd>{utcLabel(selected.confirmed_at_ms)}</dd></div>
            <div><dt>Invalidado em</dt><dd>{utcLabel(selected.invalidated_at_ms)}</dd></div>
            <div><dt>Revisão disponível em</dt><dd>{utcLabel(selected.available_at_ms)}</dd></div>
          </dl>
          <details><summary>Evidências e parâmetros registrados</summary><pre className="json-detail">
            {JSON.stringify({ evidence: selected.evidence, parameters: selected.parameters }, null, 2)}
          </pre></details>
        </div>}
      </> : <p className="empty-state">Nenhum evento conhecido neste intervalo.</p>}
    </details>
    <details className="chart-level-list">
      <summary>Níveis estruturais observados · {knownLevels.length}</summary>
      <p className="muted">Linhas começam no candle de disponibilidade. Níveis observados não são projeções estatísticas.</p>
      <div className="table-scroll"><table><thead><tr><th>Nível</th><th>Preço</th><th>Conhecido após</th><th>Estado</th></tr></thead>
        <tbody>{knownLevels.map((level, index) => <tr key={`${level.event_id}-${index}`}>
          <td>{level.kind === 'support' ? 'Suporte' : level.kind === 'resistance' ? 'Resistência' : level.kind}</td>
          <td>{formatPrice(level.price)}</td><td>{utcLabel(level.available_at_ms)}</td>
          <td>{level.broken ? 'Rompido' : 'Observado'}{level.label ? ` · ${level.label}` : ''}</td>
        </tr>)}</tbody></table></div>
      {!knownLevels.length && <p className="empty-state">Níveis indisponíveis.</p>}
    </details>
    <details className="chart-candle-table">
      <summary>Dados acessíveis · últimos 20 candles fechados</summary>
      <div className="table-scroll"><table><thead><tr><th>Timestamp UTC</th><th>Abertura</th><th>Máxima</th>
        <th>Mínima</th><th>Fechamento</th><th>Volume</th></tr></thead><tbody>
        {candles.slice(-20).reverse().map((candle) => <tr key={candle.time_ms}>
          <td>{utcLabel(candle.time_ms)}</td><td>{formatPrice(candle.open)}</td><td>{formatPrice(candle.high)}</td>
          <td>{formatPrice(candle.low)}</td><td>{formatPrice(candle.close)}</td><td>{priceLabel(candle.volume)}</td>
        </tr>)}
      </tbody></table></div>
    </details>
  </section>;
}
