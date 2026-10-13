import { useState } from 'react';
import { ArrowDownRight, ArrowUpRight, ArrowRight, GitBranch, ShieldCheck, Info, Layers3, Clock3 } from 'lucide-react';
import type { EngineEvent, Timeframe, WebAnalysis } from '../contracts';
import { Badge, Details, EmptyState, EvidenceList, humanize, number, numeric, price, ReasonList, record, records, SectionHeading, strings, text, TimeframePicker, timeframes, utc } from './ui';

type PanelProps = { data: WebAnalysis; timeframe: Timeframe; onTimeframeChange: (value: Timeframe) => void };

export function MarketReadout({ data }: { data: WebAnalysis }) {
  const engine = data.analysis;
  const conflicts = engine.multitimeframe.conflicts;
  return <section className="market-readout panel">
    <SectionHeading eyebrow="Diagnóstico multitemporal" title="O contexto de cada intervalo" />
    <div className="timeframe-readouts">{timeframes.map(frame => {
      const result = engine.timeframes[frame];
      return <div className="timeframe-readout" key={frame}>
        <div className="timeframe-readout-title"><strong>{frame}</strong><span>{frame === 'D1' ? 'Contexto amplo' : frame === 'H4' ? 'Desenvolvimento' : 'Detalhe'}</span></div>
        <div className="readout-row"><span>Estrutura</span><Badge value={result.structure?.trend ?? 'indeterminado'} /></div>
        <div className="readout-row"><span>Indicadores</span><Badge value={result.regime} /></div>
        <div className="readout-footer"><span className={result.quality.valid ? 'positive-text' : 'caution-text'}>{result.quality.closed == null ? 'Contagem indisponível' : `${result.quality.closed} candles fechados`}</span><span>{result.quality.valid ? 'Integridade verificada' : 'Dados insuficientes'}</span></div>
      </div>;
    })}</div>
    <div className={`context-note ${conflicts.length ? 'context-note-caution' : ''}`}><GitBranch size={18} aria-hidden="true" /><div>
      <strong>{conflicts.length ? `${conflicts.length} conflitos entre intervalos` : 'Sem conflitos estruturais registrados'}</strong>
      <p>{conflicts.length ? 'Os intervalos apresentam leituras diferentes. O motor preserva o conflito; nenhum timeframe recebe autoridade automática.' : 'Concordância estrutural é uma observação do motor e não implica capacidade preditiva.'}</p>
      {conflicts.length > 0 && <div className="conflict-pills">{conflicts.map((conflict, index) => <span key={index}>{strings(record(conflict).timeframes).join(' × ')}<span className="muted">{strings(record(conflict).observed).map(humanize).join(' / ')}</span></span>)}</div>}
    </div></div>
  </section>;
}

export function Synthesis({ data }: { data: WebAnalysis }) {
  const current = data.analysis.timeframes.H1;
  const active = data.analysis.scenarios.filter(scenario => scenario.state === 'active');
  const known = current.structure?.events.filter(event => event.state === 'confirmed').slice(-3) ?? [];
  return <section className="synthesis panel">
    <SectionHeading eyebrow="Síntese baseada em regras" title="Leitura do mercado" />
    <p className="synthesis-lead">{data.analysis.regime === 'indeterminado'
      ? 'Os indicadores não estabelecem um regime consensual entre H1, H4 e D1.'
      : `O regime consensual de indicadores é ${humanize(data.analysis.regime).toLowerCase()}.`}</p>
    <p className="muted">{active.length ? `Cenários ativos pelas regras: ${active.map(scenario => humanize(scenario.name)).join(', ')}.`
      : 'Nenhum cenário satisfaz todas as condições de ativação neste corte.'}</p>
    <div className="synthesis-events"><span className="eyebrow">Últimas observações confirmadas · H1</span>{known.length
      ? known.map(event => <div key={event.id}><span>{humanize(event.kind)}</span><strong>{price(event.price)}</strong><small>{utc(event.available_at_ms, true)}</small></div>)
      : <p className="muted small">Sem eventos confirmados disponíveis.</p>}</div>
    <p className="integrity-footnote"><Info size={14} aria-hidden="true" /> Confirmações de regras são observações. Não garantem movimentos futuros.</p>
  </section>;
}

export function IndicatorStrip({ data, timeframe }: { data: WebAnalysis; timeframe: Timeframe }) {
  const values = data.analysis.timeframes[timeframe].indicators;
  const metrics = [
    ['RSI 14', values?.rsi14, 'Momentum de Wilder'],
    ['ATR', values?.atr_percent, '% do fechamento'],
    ['Volume relativo', values?.volume_ratio20, '× média anterior de 20'],
    ['Eficiência', values?.efficiency20, 'Direcional · 20 candles'],
  ] as const;
  return <div className="indicator-strip" aria-label={`Indicadores ${timeframe}`}>{metrics.map(([name, value, hint]) =>
    <div key={name}><span>{name}<small>{timeframe}</small></span><strong>{number(value, 2)}{name === 'ATR' && value != null ? '%' : ''}{name === 'Volume relativo' && value != null ? '×' : ''}</strong><small>{hint}</small></div>)}</div>;
}

export function Scenarios({ data }: { data: WebAnalysis }) {
  return <section className="scenario-section"><SectionHeading eyebrow="Cenários condicionais" title="O que precisa acontecer" ><span className="small muted">Sem probabilidades arbitrárias</span></SectionHeading>
    <div className="scenario-grid">{data.analysis.scenarios.map(scenario => {
      const Icon = scenario.name === 'bullish' ? ArrowUpRight : scenario.name === 'bearish' ? ArrowDownRight : ArrowRight;
      return <article className={`scenario-card scenario-${scenario.name}`} key={scenario.name}>
        <div className="scenario-heading"><div><Icon size={19} aria-hidden="true" /><h3>{humanize(scenario.name)}</h3></div><Badge value={scenario.state} /></div>
        <p className="scenario-thesis">{scenario.thesis}</p>
        <details className="scenario-details"><summary>Gatilhos e invalidações <span>{scenario.activation_conditions.length + scenario.invalidation_conditions.length} critérios</span></summary>
          <h4>Ativação</h4><ConditionList conditions={scenario.activation_conditions} /><h4>Invalidação</h4><ConditionList conditions={scenario.invalidation_conditions} /></details>
        <details className="scenario-details"><summary>Evidências <span>{scenario.favorable_evidence.length} favoráveis · {scenario.contrary_evidence.length} contrárias</span></summary>
          <h4>A favor</h4><EvidenceList evidence={scenario.favorable_evidence} /><h4>Contra</h4><EvidenceList evidence={scenario.contrary_evidence} /></details>
        {scenario.insufficient_data.length > 0 && <ReasonList reasons={scenario.insufficient_data} />}
      </article>;
    })}</div>
    <p className="integrity-footnote"><GitBranch size={14} aria-hidden="true" /> Cenários dependem de eventos futuros. Não representam classes estatísticas de retorno nem projeções de preço.</p>
  </section>;
}

const conditionLabels: Record<string, string> = {
  two_structural_votes: 'Pelo menos dois intervalos com estrutura favorável',
  no_opposing_structural_vote: 'Ausência de voto estrutural contrário',
  fresh_confirmed_directional_event: 'Evento direcional confirmado e recente',
  H1_invalidation_boundary_available_and_holding: 'Limite estrutural H1 conhecido e preservado',
  all_timeframes_available: 'Todos os intervalos disponíveis',
  two_opposing_structural_votes: 'Pelo menos dois votos estruturais contrários',
  H1_close_below_support: 'Fechamento H1 abaixo do suporte',
  H1_close_above_resistance: 'Fechamento H1 acima da resistência',
  two_confirmed_ranges_containing_price: 'Duas faixas confirmadas contendo o preço',
  no_two_directional_structural_votes: 'Ausência de dois votos direcionais',
  no_directional_scenario_active: 'Nenhum cenário direcional ativo',
  directional_scenario_active: 'Cenário direcional ativo',
  two_confirmed_range_breakouts: 'Duas faixas com rompimento confirmado',
};

function ConditionList({ conditions }: { conditions: unknown }) {
  return <ul className="condition-list">{records(conditions).map((condition, index) =>
    <li key={index}><span className={`condition-icon ${condition.met === true ? 'condition-met' : ''}`} aria-hidden="true">{condition.met === true ? '✓' : '—'}</span><div>
      <span>{conditionLabels[String(condition.rule)] ?? humanize(String(condition.rule ?? 'Critério'))}</span>
      <small>{condition.met === true ? 'Atendida' : condition.available === false ? 'Dado indisponível' : condition.met === false ? 'Não atendida' : 'Não avaliada'}{typeof condition.observed === 'number' ? ` · observado ${number(condition.observed, 0)}` : ''}{typeof condition.required === 'number' ? ` / ${number(condition.required, 0)} requerido` : ''}{condition.level != null ? ` · ${text(condition.level)}` : ''}</small>
    </div></li>)}</ul>;
}

export function StructurePanel({ data, timeframe, onTimeframeChange }: PanelProps) {
  const structure = data.analysis.timeframes[timeframe].structure;
  return <div className="panel-page"><SectionHeading eyebrow="Market structure" title="Estrutura de mercado"><TimeframePicker value={timeframe} onChange={onTimeframeChange} /></SectionHeading>
    {!structure ? <EmptyState title="Estrutura indisponível" warning>O intervalo não contém histórico íntegro suficiente para o motor.</EmptyState> : <>
      <div className="structural-summary panel"><div><span className="eyebrow">Tendência estrutural · {timeframe}</span><h3>{humanize(structure.trend)}</h3><p className="muted small">Classificação determinística com pivôs e rompimentos conhecidos até o corte.</p></div><Badge value={structure.trend} /></div>
      <div className="level-grid">{['support', 'resistance'].map(kind => <section className="panel level-panel" key={kind}><h3>{kind === 'support' ? 'Suportes observados' : 'Resistências observadas'}</h3>
        {structure.levels.filter(level => level.kind === kind).map(level => <div className="level-row" key={level.event_id}>
          <div><strong className={level.broken ? 'level-broken' : ''}>{price(level.price)}</strong><span>{level.label ?? 'Pivô confirmado'}{level.broken ? ' · rompido' : ''}</span></div><small>Conhecido em<br />{utc(level.available_at_ms, true)}</small>
        </div>)}{!structure.levels.some(level => level.kind === kind) && <p className="muted">Nenhum nível disponível.</p>}</section>)}</div>
      <EventTable events={structure.events} title="Pivôs e eventos estruturais" />
      <ReasonList reasons={structure.insufficient_data} />
    </>}
    <p className="integrity-footnote"><Clock3 size={15} aria-hidden="true" /> A posição histórica de um pivô precede sua confirmação. A coluna “Disponível” registra quando seu estado atual passou a ser conhecido.</p>
  </div>;
}

export function EventTable({ events, title }: { events: EngineEvent[]; title: string }) {
  const [filter, setFilter] = useState('confirmed');
  const [limit, setLimit] = useState(20);
  const filtered = events.filter(event => filter === 'all' || event.state === filter).slice().reverse();
  return <section className="panel event-section"><div className="event-section-heading"><h3>{title}</h3><label>Estado<select aria-label={`Estado — ${title}`} value={filter} onChange={event => { setFilter(event.target.value); setLimit(20); }}>
    <option value="confirmed">Confirmados</option><option value="candidate">Candidatos</option><option value="invalidated">Invalidados</option><option value="all">Todos os estados</option></select></label></div>
    {!filtered.length ? <EmptyState title="Nenhum evento neste estado">A ausência de eventos não implica evidência de alta, baixa ou lateralização.</EmptyState>
      : <div className="table-scroll" tabIndex={0} aria-label={title}><table className="event-table"><thead><tr><th>Evento / preço</th><th>Estado</th><th>Posição histórica</th><th>Primeira detecção</th><th>Disponível</th><th>Evidências</th></tr></thead><tbody>{filtered.slice(0, limit).map(event => <tr key={event.id}>
        <td><strong>{humanize(event.kind)}</strong><span>{price(event.price)}</span></td><td><Badge value={event.state} />{event.confirmed_at_ms != null && <small>Confirmado: {utc(event.confirmed_at_ms, true)}</small>}{event.invalidated_at_ms != null && <small>Invalidado: {utc(event.invalidated_at_ms, true)}</small>}</td>
        <td>{utc(event.event_time_ms, true)}</td><td>{utc(event.detected_at_ms, true)}</td><td>{utc(event.available_at_ms, true)}</td><td><Details title="Ver critérios" value={{ evidence: event.evidence, parameters: event.parameters }} /></td>
      </tr>)}</tbody></table></div>}
    <div className="table-footer"><span>{filtered.length} eventos · estado conhecido no corte</span>{filtered.length > limit && <button type="button" className="text-button" onClick={() => setLimit(limit + 20)}>Exibir mais 20</button>}</div>
  </section>;
}

export function WyckoffPanel({ data, timeframe, onTimeframeChange }: PanelProps) {
  const wyckoff = data.analysis.timeframes[timeframe].wyckoff;
  const range = wyckoff?.range;
  return <div className="panel-page"><SectionHeading eyebrow="Regras operacionais de Wyckoff" title="Faixas, testes e hipóteses"><TimeframePicker value={timeframe} onChange={onTimeframeChange} /></SectionHeading>
    <div className="context-note"><Layers3 size={20} aria-hidden="true" /><div><strong>Observação e interpretação são coisas distintas</strong><p>Os eventos são reconhecidos por regras explícitas de preço, fechamento e volume. Acumulação e distribuição permanecem hipóteses; fases A–E não são atribuídas.</p></div></div>
    {!wyckoff ? <EmptyState title="Wyckoff indisponível" warning>Histórico íntegro insuficiente neste intervalo.</EmptyState> : <>
      {range ? <section className="panel range-panel"><div><span className="eyebrow">Trading range · {timeframe}</span><h3>{price(range.lower)} <span className="muted">—</span> {price(range.upper)}</h3><small className="muted">Disponível em {utc(range.available_at_ms)}</small></div><Badge value={range.state} /></section>
        : <EmptyState title="Nenhuma faixa operacional disponível">Os critérios de amplitude, permanência, testes e liquidez ainda não definiram uma trading range.</EmptyState>}
      {wyckoff.hypotheses.length > 0 && <section className="panel hypotheses"><h3>Interpretações condicionais</h3>{wyckoff.hypotheses.map((hypothesis, index) => { const item = record(hypothesis); return <div className="hypothesis" key={index}><div><strong>{humanize(String(item.interpretation ?? item.name ?? item.hypothesis ?? 'Hipótese Wyckoff'))}</strong><Badge value={String(item.state ?? 'candidate')} /></div><EvidenceList evidence={item.evidence} /><Details title="Registro da hipótese" value={hypothesis} /></div>; })}</section>}
      <EventTable events={wyckoff.events} title="Eventos Wyckoff" />
      {wyckoff.liquidity_warnings.length > 0 && <section className="panel"><h3>Alertas de liquidez</h3><EvidenceList evidence={wyckoff.liquidity_warnings} /></section>}
      <ReasonList reasons={wyckoff.insufficient_data} /><ReasonList reasons={wyckoff.limitations} />
    </>}
  </div>;
}

export function ForecastPanel({ data }: { data: WebAnalysis }) {
  return <div className="panel-page"><SectionHeading eyebrow="Motor preditivo probabilístico" title="Previsões e incerteza"><span className="muted small">Retorno ao final do horizonte</span></SectionHeading>
    <div className="context-note"><ShieldCheck size={20} aria-hidden="true" /><div><strong>Um número só é exibido quando o backend o disponibiliza</strong><p>Probabilidades públicas ausentes permanecem indisponíveis. Cenários condicionais, intervalos estatísticos e níveis estruturais são apresentados separadamente.</p></div></div>
    <div className="forecast-grid">{data.analysis.predictions.map(prediction => <article className="panel forecast-card" key={prediction.horizon_days}>
      <div className="forecast-heading"><h3>{prediction.horizon_days}<span>dias</span></h3><Badge value={prediction.status} /></div>
      <span className="eyebrow">Probabilidades de retorno final</span>
      {prediction.probabilities == null ? <div className="probability-unavailable"><span className="unavailable-symbol" aria-hidden="true">—</span><strong>Probabilidades indisponíveis</strong><p>O modelo não satisfez os critérios necessários para uma previsão pública.</p></div>
        : <ProbabilityBars probabilities={prediction.probabilities} publicForecast />}
      {prediction.return_distribution != null && <ReturnDistribution value={prediction.return_distribution} />}
      <ReasonList reasons={prediction.limitations} />
      <dl className="forecast-meta"><div><dt>Origem</dt><dd>{utc(prediction.prediction_origin_ms)}</dd></div><div><dt>Fim do horizonte</dt><dd>{utc(prediction.horizon_end_ms)}</dd></div><div><dt>Modelo</dt><dd>{prediction.model_version ?? 'Não configurado'}</dd></div><div><dt>Dataset</dt><dd>{prediction.dataset_version ?? 'Indisponível'}</dd></div></dl>
      {prediction.experimental_diagnostics != null && <details className="experimental-details"><summary>Diagnóstico experimental · pesquisa</summary><div className="experimental-warning">EXPERIMENTAL · NÃO VALIDADO<br />Estas estimativas não representam uma previsão pública elegível.</div>{prediction.experimental_diagnostics.probabilities != null ? <ProbabilityBars probabilities={prediction.experimental_diagnostics.probabilities} /> : <p className="muted small">Probabilidades experimentais indisponíveis.</p>}{prediction.experimental_diagnostics.return_distribution != null && <ReturnDistribution value={prediction.experimental_diagnostics.return_distribution} />}</details>}
    </article>)}</div>
    <Scenarios data={data} />
    <p className="integrity-footnote"><Info size={15} aria-hidden="true" /> A previsão estatística descreve classes e retornos finais. Não produz trajetórias garantidas nem autoriza execução de operações.</p>
  </div>;
}

function ProbabilityBars({ probabilities, publicForecast = false }: { probabilities: { bullish: number; neutral: number; bearish: number }; publicForecast?: boolean }) {
  return <div className="probability-bars" data-testid={publicForecast ? 'prediction-probabilities' : undefined}>{(['bullish', 'neutral', 'bearish'] as const).map(kind => <div key={kind} className={`probability-row probability-${kind}`}><div><span>{humanize(kind)}</span><strong>{number(probabilities[kind] * 100, 1)}%</strong></div><div className="probability-track"><span style={{ width: `${probabilities[kind] * 100}%` }} /></div></div>)}</div>;
}

function ReturnDistribution({ value }: { value: unknown }) {
  const distribution = record(value);
  const quantiles = record(distribution.quantiles);
  return <section className="return-distribution"><h4>Distribuição de retornos finais</h4><div className="return-median"><span>Mediana estimada</span><strong>{numeric(distribution.median) == null ? 'Indisponível' : `${number(numeric(distribution.median)! * 100, 2)}%`}</strong></div>
    <div className="quantile-grid">{Object.entries(quantiles).map(([quantile, val]) => <div key={quantile}><span>Q{number(Number(quantile) * 100, 0)}</span><strong>{numeric(val) == null ? 'Indisponível' : `${number(numeric(val)! * 100, 2)}%`}</strong></div>)}</div>
    <p className="muted small">Intervalo nominal {numeric(distribution.interval_nominal_coverage) != null ? `${number(numeric(distribution.interval_nominal_coverage)! * 100, 0)}%` : 'indisponível'}: {numeric(distribution.lower) != null ? `${number(numeric(distribution.lower)! * 100)}%` : 'indisponível'} a {numeric(distribution.upper) != null ? `${number(numeric(distribution.upper)! * 100)}%` : 'indisponível'}.</p>
    <p className="integrity-footnote">Quantis não são suportes, resistências ou limites garantidos de preço.</p>
  </section>;
}

export function AuditPanel({ data }: { data: WebAnalysis }) {
  const quality = data.model_quality;
  const horizons = record(quality.horizons);
  return <div className="panel-page"><SectionHeading eyebrow="Model quality" title="Auditoria e transparência"><Badge value={quality.configured ? 'neutral' : 'INSUFFICIENT_EVIDENCE'}>{quality.configured ? 'Artefato versionado' : 'Modelo não configurado'}</Badge></SectionHeading>
    <section className="panel provenance-panel"><div><span className="eyebrow">Proveniência</span><h3>{data.summary.symbol} · Binance Spot</h3><p className="muted small">{data.mode === 'replay' ? 'Reprodução de captura histórica. Não é cotação atual.' : 'Captura de dados públicos com corte temporal explícito.'}</p></div><dl><div><dt>Motor</dt><dd>{data.analysis.engine_version}</dd></div><div><dt>Modelo</dt><dd>{quality.model_version ?? 'Não configurado'}</dd></div><div><dt>Dados</dt><dd>{quality.dataset_version ?? 'Indisponível'}</dd></div><div><dt>Corte da análise</dt><dd>{utc(data.analysis.as_of_ms)}</dd></div></dl></section>
    {!quality.configured && <EmptyState title="Nenhum modelo previamente treinado configurado" warning>A análise descritiva continua disponível. A interface não treina modelos nem preenche probabilidades ausentes.</EmptyState>}
    {Object.entries(horizons).map(([horizon, raw]) => {
      const item = record(raw); const strategy = record(item.selected_strategy_metrics); const final = record(item.final_test_metrics);
      const calibration = record(item.calibration); const comparisons = records(item.comparisons);
      return <section key={horizon} className="panel audit-horizon"><div className="audit-horizon-heading"><h3>{horizon} dias <span>{humanize(String(item.model_kind ?? 'Modelo indisponível'))}</span></h3><Badge value={String(item.status ?? 'INSUFFICIENT_EVIDENCE')} /></div>
        <div className="audit-periods"><div><span>Treinamento</span><strong>{utc(numeric(item.training_start_ms), true)} — {utc(numeric(item.training_end_ms), true)}</strong></div><div><span>Teste final preservado</span><strong>{utc(numeric(item.final_test_start_ms), true)} — {utc(numeric(item.final_test_end_ms), true)}</strong></div></div>
        <div className="table-scroll" tabIndex={0} aria-label={`Métricas do horizonte ${horizon}`}><table className="metrics-table"><thead><tr><th>População avaliada</th><th>Observações</th><th>Brier ↓</th><th>Log loss ↓</th><th>ECE ↓</th><th>Cobertura</th></tr></thead><tbody>
          <MetricsRow name="Estratégia walk-forward · OOS agregado" metrics={strategy} coverage={numeric(record(item.coverage).coverage)} />
          <MetricsRow name="Modelo congelado · teste final" metrics={final} coverage={numeric(record(item.final_coverage).coverage)} />
        </tbody></table></div>
        {comparisons.length > 0 && <><h4>Modelos e baselines · fora da amostra</h4><div className="table-scroll" tabIndex={0} aria-label={`Comparação de modelos ${horizon}`}><table className="metrics-table"><thead><tr><th>Modelo / folds</th><th>Observações</th><th>Brier ↓</th><th>Log loss ↓</th><th>Baseline na mesma população · Brier</th></tr></thead><tbody>{comparisons.map((comparison, index) => { const metrics = record(comparison.metrics); const baseline = record(comparison.same_population_reference_baseline_metrics); return <tr key={index}><td><strong>{humanize(String(comparison.model_kind ?? 'Modelo'))}</strong><small>Folds {Array.isArray(comparison.fold_ids) ? comparison.fold_ids.join(', ') : 'indisponíveis'}</small></td><td>{number(numeric(metrics.observations), 0)}</td><td>{number(numeric(metrics.brier), 4)}</td><td>{number(numeric(metrics.log_loss), 4)}</td><td>{number(numeric(baseline.brier), 4)}</td></tr>; })}</tbody></table></div></>}
        {comparisons.length > 0 && <p className="integrity-footnote">Modelos podem ter folds diferentes. A coluna de baseline usa a mesma população do respectivo candidato.</p>}
        <div className="calibration-summary"><div><span>Calibração</span><strong>{humanize(String(calibration.status ?? 'INSUFFICIENT_EVIDENCE'))}</strong></div><div><span>Origens não sobrepostas</span><strong>{number(numeric(calibration.independent_observations ?? calibration.independent_origins), 0)}</strong></div></div>
        {Object.keys(record(strategy.calibration_bins)).length > 0 && <details className="calibration-details"><summary>Tabelas de calibração OOS por classe</summary><CalibrationTables bins={strategy.calibration_bins} /></details>}
        <Details title="Comparação pareada e incerteza estatística" value={item.paired_comparison} />
        <ReasonList reasons={strings(item.limitations)} />
      </section>;
    })}
    <section className="panel audit-notes"><h3>Limitações da análise</h3><ReasonList reasons={[...data.analysis.limitations, ...data.warnings]} /><p className="integrity-footnote"><ShieldCheck size={15} aria-hidden="true" /> Métricas históricas não garantem desempenho futuro. A classificação de validação vem do motor, sem alteração de resultados para apresentação.</p><Details title="Semântica de disponibilidade e modelo" value={quality.availability_semantics} /></section>
  </div>;
}

function MetricsRow({ name, metrics, coverage }: { name: string; metrics: Record<string, unknown>; coverage: number | null }) {
  return <tr><td>{name}</td><td>{number(numeric(metrics.observations), 0)}</td><td>{number(numeric(metrics.brier), 4)}</td><td>{number(numeric(metrics.log_loss), 4)}</td><td>{number(numeric(metrics.ece), 4)}</td><td>{coverage == null ? 'Indisponível' : `${number(coverage * 100, 1)}%`}</td></tr>;
}

function CalibrationTables({ bins }: { bins: unknown }) {
  return <div className="calibration-tables">{Object.entries(record(bins)).map(([kind, values]) => <section key={kind}><h4>{humanize(kind)}</h4><div className="table-scroll" tabIndex={0}><table className="metrics-table"><thead><tr><th>Faixa prevista</th><th>N</th><th>Média prevista</th><th>Frequência observada</th></tr></thead><tbody>{records(values).map((bin, index) => <tr key={index}><td>{numeric(bin.lower_probability) == null || numeric(bin.upper_probability) == null ? 'Indisponível' : `${number(numeric(bin.lower_probability)! * 100, 0)}–${number(numeric(bin.upper_probability)! * 100, 0)}%`}</td><td>{number(numeric(bin.observations), 0)}</td><td>{numeric(bin.mean_probability) == null ? 'Indisponível' : `${number(numeric(bin.mean_probability)! * 100, 1)}%`}</td><td>{numeric(bin.observed_frequency) == null ? 'Indisponível' : `${number(numeric(bin.observed_frequency)! * 100, 1)}%`}</td></tr>)}</tbody></table></div></section>)}</div>;
}
