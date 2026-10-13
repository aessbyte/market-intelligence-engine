import type { ReactNode } from 'react';
import { AlertCircle, ChevronRight, Info } from 'lucide-react';
import type { Timeframe } from '../contracts';

export const timeframes: Timeframe[] = ['D1', 'H4', 'H1'];
export const label: Record<string, string> = {
  alta: 'Alta', baixa: 'Baixa', lateralizacao: 'Lateral', indeterminado: 'Indeterminado',
  bullish: 'Bullish', bearish: 'Bearish', neutral: 'Neutral / Range',
  candidate: 'Candidato', confirmed: 'Confirmado', invalidated: 'Invalidado',
  active: 'Ativo', awaiting_confirmation: 'Aguardando confirmação',
  INSUFFICIENT_EVIDENCE: 'Evidência insuficiente', UNVALIDATED_MODEL: 'Modelo não validado',
  VALIDATED_MODEL: 'Modelo elegível', VALIDATED: 'Modelo elegível',
  CALIBRATED: 'Calibrado no bloco reservado', EXPERIMENTAL_NOT_VALIDATED: 'Experimental • não validado',
  ok: 'Dados íntegros', degraded: 'Dados incompletos', support: 'Suporte', resistance: 'Resistência',
  swing_high: 'Swing high', swing_low: 'Swing low', possible_false_break: 'Possível falsa ruptura',
  false_break: 'Falsa ruptura', trading_range: 'Trading range', range_test: 'Teste da faixa',
  spring: 'Spring', upthrust: 'Upthrust', SOS: 'SOS', SOW: 'SOW', LPS: 'LPS', LPSY: 'LPSY',
  accumulation: 'Hipótese de acumulação', distribution: 'Hipótese de distribuição',
  reaccumulation: 'Hipótese de reacumulação', redistribution: 'Hipótese de redistribuição',
  frequency: 'Frequências históricas', unconditional: 'Frequências históricas',
  momentum: 'Momentum', logistic: 'Regressão logística', gradient_boosting: 'Gradient boosting',
  structure: 'Estrutura', indicators: 'Indicadores',
};

const explanations: Record<string, string> = {
  frozen_final_model_has_no_supported_holdout_improvement: 'O modelo congelado não demonstrou melhoria sustentada no teste final.',
  insufficient_independent_frozen_final_model_tests: 'Poucas origens não sobrepostas no teste final.',
  no_supported_improvement_over_validation_selected_simple_baseline: 'Não houve melhoria sustentada sobre o baseline simples escolhido na validação.',
  terminal_simple_baseline_has_no_supported_predictive_edge: 'O baseline final não demonstrou vantagem preditiva.',
  insufficient_independent_tests: 'Quantidade insuficiente de testes não sobrepostos.',
  insufficient_calibration_observations: 'Amostra insuficiente para calibrar probabilidades.',
  poorly_calibrated_probabilities: 'Probabilidades com qualidade de calibração insuficiente.',
  feature_distribution_shift: 'Distribuição de features diferente da população histórica.',
  model_not_configured: 'Nenhum modelo previamente treinado está configurado para este símbolo.',
  prediction_model_not_configured: 'Nenhum modelo previamente treinado está configurado para este símbolo.',
  no_model_bundle_supplied: 'Nenhum artefato de modelo foi fornecido.',
  no_prediction_dataset_supplied: 'Dataset histórico de previsão indisponível.',
  model_not_available: 'Modelo indisponível neste instante.',
  model_available_after_prediction_origin: 'O modelo foi criado após a origem histórica da previsão.',
  missing_or_incompatible_dataset: 'Dataset ausente ou incompatível com o modelo.',
  insufficient_history: 'Histórico insuficiente para esta análise.',
};

export function humanize(value: string): string {
  return label[value] ?? explanations[value] ?? value.replaceAll('_', ' ');
}

export function number(value: number | null | undefined, digits = 2): string {
  if (value == null || !Number.isFinite(value)) return 'Indisponível';
  return new Intl.NumberFormat('pt-BR', { maximumFractionDigits: digits, minimumFractionDigits: digits }).format(value);
}

export function compact(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return 'Indisponível';
  return new Intl.NumberFormat('pt-BR', { notation: 'compact', maximumFractionDigits: 2 }).format(value);
}

export function price(value: number | null | undefined, tickSize?: number | string | null): string {
  if (value == null || !Number.isFinite(value)) return 'Indisponível';
  const tick = tickSize == null ? null : Number(tickSize);
  const decimals = tick != null && Number.isFinite(tick) && tick > 0 ? Math.min(12, Math.max(0, Math.ceil(-Math.log10(tick))))
    : value >= 10 ? 2 : value >= 1 ? 4 : value >= 0.001 ? 6 : 8;
  return number(value, decimals);
}

export function utc(value: number | null | undefined, short = false): string {
  if (value == null || !Number.isFinite(value)) return 'Indisponível';
  const date = new Intl.DateTimeFormat('pt-BR', { timeZone: 'UTC', day: '2-digit', month: '2-digit',
    ...(short ? {} : { year: 'numeric' }), hour: '2-digit', minute: '2-digit', hour12: false }).format(value);
  return `${date} UTC`;
}

export function record(value: unknown): Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

export function records(value: unknown): Record<string, unknown>[] {
  return Array.isArray(value) ? value.map(record) : [];
}

export function strings(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string') : [];
}

export function numeric(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

export function text(value: unknown): string {
  if (value == null) return 'Indisponível';
  if (typeof value === 'string') return humanize(value);
  if (typeof value === 'number') return number(value, Math.abs(value) < 1 ? 4 : 2);
  if (typeof value === 'boolean') return value ? 'Sim' : 'Não';
  if (Array.isArray(value)) return value.map(text).join(' · ');
  const obj = record(value);
  if (typeof obj.price === 'number') return `${price(obj.price)}${typeof obj.kind === 'string' ? ` · ${humanize(obj.kind)}` : ''}`;
  return Object.entries(obj).map(([key, val]) => `${humanize(key)}: ${text(val)}`).join(' · ');
}

export function Badge({ value, children }: { value: string; children?: ReactNode }) {
  const tone = ['alta', 'bullish', 'confirmed', 'active', 'ok', 'VALIDATED', 'VALIDATED_MODEL'].includes(value) ? 'positive'
    : ['baixa', 'bearish', 'invalidated'].includes(value) ? 'negative'
      : ['candidate', 'awaiting_confirmation', 'degraded', 'UNVALIDATED_MODEL', 'INSUFFICIENT_EVIDENCE'].includes(value) ? 'caution' : 'neutral';
  return <span className={`badge badge-${tone}`}><span className="badge-dot" aria-hidden="true" />{children ?? humanize(value)}</span>;
}

export function SectionHeading({ eyebrow, title, children }: { eyebrow?: string; title: string; children?: ReactNode }) {
  return <div className="section-heading"><div>{eyebrow && <span className="eyebrow">{eyebrow}</span>}<h2>{title}</h2></div>{children}</div>;
}

export function TimeframePicker({ value, onChange }: { value: Timeframe; onChange: (value: Timeframe) => void }) {
  return <div className="segmented" aria-label="Intervalo da análise">{timeframes.map(frame =>
    <button key={frame} type="button" aria-pressed={frame === value} onClick={() => onChange(frame)}>{frame}</button>)}</div>;
}

export function EmptyState({ title, children, warning = false }: { title: string; children?: ReactNode; warning?: boolean }) {
  const Icon = warning ? AlertCircle : Info;
  return <div className={`empty-state${warning ? ' empty-state-warning' : ''}`}><Icon size={21} aria-hidden="true" /><div><h3>{title}</h3>{children && <p>{children}</p>}</div></div>;
}

export function ReasonList({ reasons }: { reasons: string[] }) {
  if (!reasons.length) return null;
  return <ul className="reason-list">{reasons.map((reason, index) => <li key={`${reason}-${index}`}><ChevronRight size={14} aria-hidden="true" /><span>{humanize(reason)}</span></li>)}</ul>;
}

export function Details({ title, value }: { title: string; value: unknown }) {
  return <details className="json-details"><summary>{title}</summary><pre>{JSON.stringify(value, null, 2)}</pre></details>;
}

export function EvidenceList({ evidence, empty }: { evidence: unknown; empty?: string }) {
  const items = records(evidence);
  if (!items.length) return <p className="muted small">{empty ?? 'Nenhuma evidência registrada.'}</p>;
  return <ul className="evidence-list">{items.map((item, index) => <li key={index}>
    <span className="evidence-index">{String(index + 1).padStart(2, '0')}</span><div>
      <strong>{typeof item.timeframe === 'string' ? `${item.timeframe} · ` : ''}{humanize(String(item.kind ?? item.observation ?? item.rule ?? item.candidate ?? 'observação'))}</strong>
      <p>{Object.entries(item).filter(([key]) => !['timeframe', 'kind', 'observation', 'rule', 'parameters', 'checks'].includes(key)).map(([key, value]) =>
        key.endsWith('_ms') && typeof value === 'number' ? `${humanize(key)}: ${utc(value)}` : `${humanize(key)}: ${text(value)}`).join(' · ')}</p>
      {item.checks !== undefined && <Details title="Critérios da regra" value={item.checks} />}
    </div>
  </li>)}</ul>;
}
