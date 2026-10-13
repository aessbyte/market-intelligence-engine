import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from 'react';
import { Activity, ArrowRight, ChartCandlestick, ChevronRight, FileSearch, GitBranch, Layers3, LoaderCircle, Moon, Search, ShieldCheck, Sun, X, Download, ExternalLink } from 'lucide-react';
import { analyzeSymbol } from './api';
import type { ProgressUpdate, Timeframe, WebAnalysis } from './contracts';
import ChartPanel from './components/ChartPanel';
import { AuditPanel, ForecastPanel, IndicatorStrip, MarketReadout, Scenarios, StructurePanel, Synthesis, WyckoffPanel } from './components/Panels';
import { Badge, compact, humanize, number, price, utc } from './components/ui';

const tabs = [
  { id: 'overview', title: 'Visão geral', icon: Activity },
  { id: 'chart', title: 'Gráfico', icon: ChartCandlestick },
  { id: 'structure', title: 'Estrutura', icon: GitBranch },
  { id: 'wyckoff', title: 'Wyckoff', icon: Layers3 },
  { id: 'forecast', title: 'Previsões', icon: ArrowRight },
  { id: 'audit', title: 'Auditoria', icon: ShieldCheck },
] as const;
type TabId = typeof tabs[number]['id'];

function startingTheme(): 'dark' | 'light' {
  try { return localStorage.getItem('mie-theme') === 'light' ? 'light' : 'dark'; } catch { return 'dark'; }
}

export default function App() {
  const [symbol, setSymbol] = useState('BTCUSDT');
  const [data, setData] = useState<WebAnalysis | null>(null);
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState<ProgressUpdate | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<TabId>('overview');
  const [timeframe, setTimeframe] = useState<Timeframe>('H4');
  const [theme, setTheme] = useState<'dark' | 'light'>(startingTheme);
  const tabRefs = useRef<(HTMLButtonElement | null)[]>([]);
  const resultRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    try { localStorage.setItem('mie-theme', theme); } catch { /* Session continues when storage is unavailable. */ }
  }, [theme]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    const normalized = symbol.trim().toUpperCase();
    if (!/^[A-Z0-9]{5,30}$/.test(normalized)) {
      setError('Informe um símbolo Binance com 5 a 30 letras ou números, como BTCUSDT.');
      return;
    }
    setSymbol(normalized); setError(null); setBusy(true); setProgress(null);
    try {
      const result = await analyzeSymbol(normalized, 'spot', setProgress);
      setData(result); setTab('overview');
      requestAnimationFrame(() => resultRef.current?.focus({ preventScroll: true }));
    } catch (problem) {
      setError(problem instanceof Error ? problem.message : 'Não foi possível concluir a análise. Tente novamente.');
    } finally { setBusy(false); }
  }

  function changeTab(event: KeyboardEvent<HTMLButtonElement>, index: number) {
    let next = index;
    if (event.key === 'ArrowRight') next = (index + 1) % tabs.length;
    else if (event.key === 'ArrowLeft') next = (index - 1 + tabs.length) % tabs.length;
    else if (event.key === 'Home') next = 0;
    else if (event.key === 'End') next = tabs.length - 1;
    else return;
    event.preventDefault(); setTab(tabs[next].id); tabRefs.current[next]?.focus();
  }

  function downloadResult() {
    if (!data) return;
    const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' }));
    const link = document.createElement('a'); link.href = url; link.download = `${data.summary.symbol}-${data.analysis_id}.json`; link.click(); URL.revokeObjectURL(url);
  }

  return <div className="app-shell">
    <a href="#main" className="skip-link">Ir para o conteúdo</a>
    <header className="app-header"><div className="header-inner">
      <a href="#" className="wordmark" aria-label="Market Intelligence — início"><span className="brand-mark" aria-hidden="true"><i /><i /><i /></span><span>MARKET<span>INTELLIGENCE</span></span><span className="wordmark-engine">ENGINE</span></a>
      <div className="header-actions"><span className="source-label"><span aria-hidden="true" /> Binance · dados públicos</span><button className="icon-button" type="button" aria-label={theme === 'dark' ? 'Ativar tema claro' : 'Ativar tema escuro'} onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}>{theme === 'dark' ? <Sun size={19} /> : <Moon size={19} />}</button><a className="icon-button docs-link" href="/docs" target="_blank" rel="noreferrer" aria-label="Documentação da API"><FileSearch size={19} /></a></div>
    </div></header>

    <main id="main" className="main-container">
      <section className={`search-section ${data ? 'search-section-compact' : ''}`} aria-label="Pesquisar ativo">
        <div className="search-intro"><span className="eyebrow">INTELIGÊNCIA QUANTITATIVA / BINANCE SPOT</span><h1>{data ? 'Análise de mercado' : <>O mercado, através<br />{' '}das evidências.</>}</h1>{!data && <p>Estrutura, cenários e qualidade estatística.<br className="desktop-break" /> Uma análise completa, com limites explícitos.</p>}</div>
        <div className="search-form-wrap"><form onSubmit={submit} className="symbol-form"><label className="symbol-field"><span className="sr-only">Símbolo</span><Search size={19} aria-hidden="true" /><input name="symbol" value={symbol} maxLength={30} placeholder="BTCUSDT" autoComplete="off" autoCapitalize="characters" spellCheck={false} onChange={event => { setSymbol(event.target.value.toUpperCase()); setError(null); }} aria-invalid={error != null} aria-describedby="symbol-hint" /></label>
          <label className="market-field"><span className="sr-only">Mercado</span><select aria-label="Mercado" defaultValue="spot"><option value="spot">Spot</option><option value="futures" disabled>Futuros indisponíveis</option></select></label>
          <button type="submit" className="primary-button" disabled={busy}>{busy ? <LoaderCircle size={18} className="spin" aria-hidden="true" /> : <ArrowRight size={18} aria-hidden="true" />}<span>{busy ? 'Analisando' : 'Analisar'}</span></button>
        </form><p id="symbol-hint" className="search-hint">{data ? 'Somente consultas públicas. Futuros ainda não são suportados pelo motor.' : 'BTCUSDT, ETHUSDT, JUPUSDT ou outro par spot. Sem chave de API.'}</p></div>
      </section>

      {error && <div className="error-banner" role="alert"><div><strong>A análise não foi concluída</strong><p>{error}</p>{data && <p>A análise anterior foi preservada. Confira seu timestamp antes de utilizá-la.</p>}</div><button type="button" className="icon-button" aria-label="Fechar mensagem de erro" onClick={() => setError(null)}><X size={18} /></button></div>}
      {busy && <div className="processing-banner" role="status" aria-live="polite"><LoaderCircle size={21} className="spin" aria-hidden="true" /><div><strong>{progress?.message ?? 'Enviando símbolo para validação…'}</strong><p>{progress ? `${humanize(progress.stage)} · ${progress.status === 'queued' ? 'na fila' : progress.status === 'running' ? 'em processamento' : progress.status === 'completed' ? 'etapa concluída' : 'interrompido'}` : 'Aguardando a confirmação do backend.'}</p></div><span className="processing-note">Sem treinamento nesta consulta</span></div>}

      {data ? <div ref={resultRef} tabIndex={-1} className="analysis-result" data-analysis-id={data.analysis_id}>
        {data.analysis.provenance.simulated && <div className="simulation-banner" role="note"><strong>SIMULATED · DADOS SINTÉTICOS DE TESTE</strong><span>Esta análise não representa um mercado real e não valida capacidade preditiva.</span></div>}
        {data.mode === 'replay' && <div className="replay-banner" role="note"><ClockIcon /><div><strong>REPLAY HISTÓRICO</strong><span>Captura arquivada em {utc(data.analysis.as_of_ms)}. Não é uma cotação atual.</span></div></div>}
        <section className="asset-header"><div className="asset-title"><span className="asset-emblem" aria-hidden="true">{data.summary.symbol.slice(0, 1)}</span><div><h2>{data.summary.symbol}<span>BINANCE / SPOT</span></h2><div className="asset-quality"><Badge value={data.summary.quality} /><span>{utc(data.summary.reference_time_ms)} · candle fechado H1</span></div></div></div><button type="button" className="secondary-button download-button" onClick={downloadResult}><Download size={17} aria-hidden="true" /><span>Exportar JSON</span></button></section>
        <section className="market-metrics" aria-label="Resumo do mercado"><div className="reference-price"><span>Preço de referência · H1</span><strong>{price(data.summary.reference_price, data.summary.tick_size)}<small>{data.summary.quote_asset ?? 'cotação'}</small></strong></div>
          <div><span>Variação · último H1</span><strong className={data.summary.change_percent == null ? '' : data.summary.change_percent >= 0 ? 'positive-text' : 'negative-text'}>{data.summary.change_percent == null ? 'Indisponível' : `${data.summary.change_percent > 0 ? '+' : ''}${number(data.summary.change_percent)}%`}</strong><small>Fechamento anterior</small></div>
          <div><span>Volume · último H1</span><strong>{compact(data.summary.volume)}</strong><small>{data.summary.base_asset ?? 'Ativo base'}</small></div><div><span>Volatilidade · ATR H1</span><strong>{data.summary.atr_percent == null ? 'Indisponível' : `${number(data.summary.atr_percent)}%`}</strong><small>14 candles · Wilder</small></div><div><span>Regime de indicadores</span><strong className="regime-value">{humanize(data.analysis.regime)}</strong><small>Consenso H1 / H4 / D1</small></div>
        </section>
        <nav className="tab-navigation" aria-label="Painéis da análise"><div role="tablist" aria-label="Análise de mercado">{tabs.map(({ id, title, icon: Icon }, index) => <button key={id} id={`tab-${id}`} type="button" role="tab" aria-selected={tab === id} aria-controls={`panel-${id}`} tabIndex={tab === id ? 0 : -1} ref={element => { tabRefs.current[index] = element; }} onKeyDown={event => changeTab(event, index)} onClick={() => setTab(id)}><Icon size={17} aria-hidden="true" />{title}{id === 'audit' && <span className="audit-tab-dot" aria-hidden="true" />}</button>)}</div><span className="analysis-stamp">CORTE {new Date(data.analysis.as_of_ms).toISOString().slice(11, 16)} UTC</span></nav>
        <div className="tab-content" role="tabpanel" id={`panel-${tab}`} aria-labelledby={`tab-${tab}`} tabIndex={0}>
          {tab === 'overview' && <><div className="overview-main"><div className="overview-chart"><div className="overview-chart-heading"><div><span className="eyebrow">Preço e eventos observados</span><h2>{data.summary.symbol}<span> / {timeframe}</span></h2></div><button type="button" className="text-button" onClick={() => setTab('chart')}>Abrir gráfico <ExternalLink size={14} aria-hidden="true" /></button></div><ChartPanel data={data} timeframe={timeframe} onTimeframeChange={setTimeframe} /></div><Synthesis data={data} /></div><IndicatorStrip data={data} timeframe={timeframe} /><MarketReadout data={data} /><Scenarios data={data} /></>}
          {tab === 'chart' && <div className="panel-page"><div className="section-heading"><div><span className="eyebrow">Candles e anotações causais</span><h2>Gráfico interativo</h2></div></div><ChartPanel data={data} timeframe={timeframe} onTimeframeChange={setTimeframe} /><IndicatorStrip data={data} timeframe={timeframe} /></div>}
          {tab === 'structure' && <StructurePanel data={data} timeframe={timeframe} onTimeframeChange={setTimeframe} />}
          {tab === 'wyckoff' && <WyckoffPanel data={data} timeframe={timeframe} onTimeframeChange={setTimeframe} />}
          {tab === 'forecast' && <ForecastPanel data={data} />}
          {tab === 'audit' && <AuditPanel data={data} />}
        </div>
      </div> : <Welcome />}
      <footer className="app-footer"><span>MARKET INTELLIGENCE ENGINE <span className="footer-separator">/</span> Dados públicos. Regras reproduzíveis.</span><span>Análise de mercado · sem execução de operações</span></footer>
    </main>
  </div>;
}

function ClockIcon() { return <span className="replay-clock" aria-hidden="true">◷</span>; }

function Welcome() {
  return <section className="welcome" aria-label="Sobre a plataforma"><div className="welcome-feature"><ChartCandlestick size={26} aria-hidden="true" /><span className="eyebrow">01 / OBSERVAR</span><h2>A estrutura, em contexto.</h2><p>H1, H4 e D1. Pivôs, rompimentos e conflitos entre intervalos com confirmação temporal explícita.</p></div><div className="welcome-feature"><GitBranch size={26} aria-hidden="true" /><span className="eyebrow">02 / INTERPRETAR</span><h2>Cenários com condições.</h2><p>Trading ranges, eventos Wyckoff, gatilhos e invalidações. Hipóteses distintas de observações.</p></div><div className="welcome-feature"><ShieldCheck size={26} aria-hidden="true" /><span className="eyebrow">03 / AUDITAR</span><h2>A incerteza, à vista.</h2><p>Modelos versionados, testes fora da amostra e abstinência quando as evidências são insuficientes.</p></div><div className="welcome-bottom"><span><ShieldCheck size={16} aria-hidden="true" /> Sem credenciais privadas</span><span><Activity size={16} aria-hidden="true" /> Sem ordens ou treinamento a cada consulta</span><span><ChevronRight size={16} aria-hidden="true" /> Somente resultados do motor analítico</span></div></section>;
}
