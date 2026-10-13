import { z } from 'zod';

export const timeframeSchema = z.enum(['H1', 'H4', 'D1']);
export type Timeframe = z.infer<typeof timeframeSchema>;
export type Market = 'spot' | 'futures';
const timestamp = z.number().int().nonnegative();
const finite = z.number().finite();
const record = z.record(z.string(), z.unknown());

export const eventSchema = z.object({
  id: z.string(), kind: z.string(), event_time_ms: timestamp,
  detected_at_ms: timestamp, available_at_ms: timestamp,
  confirmed_at_ms: timestamp.nullable(), invalidated_at_ms: timestamp.nullable(),
  price: finite.positive(), interval: z.string(),
  state: z.enum(['candidate', 'confirmed', 'invalidated']),
  evidence: z.array(record), parameters: record,
}).passthrough().superRefine((event, ctx) => {
  if (event.event_time_ms > event.detected_at_ms || event.detected_at_ms > event.available_at_ms
    || (event.confirmed_at_ms !== null && event.confirmed_at_ms > event.available_at_ms)
    || (event.invalidated_at_ms !== null && event.invalidated_at_ms > event.available_at_ms)) {
    ctx.addIssue({ code: 'custom', message: 'Evento com disponibilidade temporal inconsistente.' });
  }
});
export type EngineEvent = z.infer<typeof eventSchema>;
export const levelSchema = z.object({
  kind: z.string(), price: finite.positive(), event_id: z.string(), available_at_ms: timestamp,
  label: z.string().nullable().optional(), broken: z.boolean().optional(), timeframe: timeframeSchema.optional(),
}).passthrough();
export type StructuralLevel = z.infer<typeof levelSchema>;
const probabilities = z.object({ bearish: finite.min(0).max(1), neutral: finite.min(0).max(1), bullish: finite.min(0).max(1) })
  .refine(p => Math.abs(p.bearish + p.neutral + p.bullish - 1) <= 1e-8, 'Probabilidades devem somar 1.');
const distribution = z.object({
  method: z.string(), median: finite, lower: finite, upper: finite,
  quantiles: z.record(z.string(), finite), interval_nominal_coverage: finite.min(0).max(1),
  downside_probability: finite.min(0).max(1), downside_threshold_return: finite, observations: z.number().int().nonnegative(),
  interpretation: z.string().optional(),
}).passthrough().refine(d => d.lower <= d.median && d.median <= d.upper, 'Quantis fora de ordem.');
export const predictionSchema = z.object({
  horizon_days: z.union([z.literal(7), z.literal(30), z.literal(90)]), status: z.string(),
  prediction_origin_ms: timestamp.nullable(), as_of_ms: timestamp, horizon_end_ms: timestamp.nullable(),
  reference_price: finite.nullable(), probabilities: probabilities.nullable(),
  return_distribution: distribution.nullable(),
  experimental_diagnostics: z.object({
    status: z.string(), probabilities: probabilities.nullable(), return_distribution: distribution.nullable(), use: z.string(),
  }).nullable(),
  model_version: z.string().nullable(), model_available_at_ms: timestamp.nullable().optional(), dataset_version: z.string().nullable(),
  evidence: record.nullable(), max_feature_standardized_distance: finite.nullable(),
  limitations: z.array(z.string()), scenario_relationship: z.string(), reference_timing: z.string().optional(),
}).passthrough().refine(p => p.status === 'VALIDATED_MODEL' || (p.probabilities === null && p.return_distribution === null),
  'Modelo inelegível não pode fornecer previsão pública.');
export type Prediction = z.infer<typeof predictionSchema>;

const quality = z.object({
  valid: z.boolean(), errors: z.array(z.string()), closed: z.number().int().nonnegative().optional(),
  received: z.number().int().nonnegative().optional(), excluded_unclosed: z.number().int().nonnegative().optional(),
  first_open_ms: timestamp.nullable().optional(), last_close_ms: timestamp.nullable().optional(),
}).passthrough();
const structure = z.object({
  version: z.string(), trend: z.string(), events: z.array(eventSchema), levels: z.array(levelSchema),
  insufficient_data: z.array(z.string()), last_close: finite.nullable().optional(), last_close_time_ms: timestamp.nullable().optional(),
}).passthrough();
const wyckoff = z.object({
  version: z.string(), range: z.object({
    id: z.string(), lower: finite, upper: finite, state: z.string(), prior_trend: z.string(), available_at_ms: timestamp,
    breakout_direction: z.string().nullable(),
  }).passthrough().nullable(),
  events: z.array(eventSchema), hypotheses: z.array(record), liquidity_warnings: z.array(record),
  insufficient_data: z.array(z.string()), limitations: z.array(z.string()),
}).passthrough();
const frame = z.object({
  interval: z.string(), quality, regime: z.string(),
  indicators: z.record(z.string(), finite.nullable()).nullable(), evidence: z.array(record),
  structure: structure.nullable(), wyckoff: wyckoff.nullable(),
}).passthrough();
const scenario = z.object({
  name: z.enum(['bullish', 'bearish', 'neutral']), thesis: z.string(), state: z.string(),
  condition: z.string(), invalidation: z.string(), favorable_evidence: z.array(record), contrary_evidence: z.array(record),
  activation_conditions: z.array(record), invalidation_conditions: z.array(record), structural_levels: z.array(levelSchema),
  insufficient_data: z.array(z.string()), probability: z.null(), price_target: z.null(), as_of_ms: timestamp,
}).passthrough();
export type Scenario = z.infer<typeof scenario>;
const engine = z.object({
  schema_version: z.literal('3'), engine_version: z.string(), symbol: z.string(), as_of_ms: timestamp,
  status: z.enum(['ok', 'degraded']), regime: z.string(),
  provenance: z.object({ source: z.enum(['binance_public', 'simulated']), market: z.string(), simulated: z.boolean(), snapshot_sha256: z.string() }).passthrough(),
  timeframes: z.object({ H1: frame, H4: frame, D1: frame }),
  multitimeframe: z.object({
    observations: z.array(record), agreements: z.array(record), conflicts: z.array(record),
    indicator_structure_divergences: z.array(record), structural_consensus: z.string(), insufficient_data: z.array(z.string()),
  }).passthrough(),
  scenarios: z.array(scenario), predictions: z.array(predictionSchema), limitations: z.array(z.string()),
}).passthrough();
export type EngineAnalysis = z.infer<typeof engine>;
export const candleSchema = z.object({
  time_ms: timestamp, open: finite.positive(), high: finite.positive(), low: finite.positive(), close: finite.positive(), volume: finite.nonnegative(),
}).refine(c => c.high >= Math.max(c.open, c.close) && c.low <= Math.min(c.open, c.close) && c.high >= c.low, 'OHLC inconsistente.');
export type ChartCandle = z.infer<typeof candleSchema>;
const point = z.object({ time_ms: timestamp, value: finite });
export const chartSchema = z.object({
  candles: z.array(candleSchema), ema20: z.array(point), ema50: z.array(point), rsi14: z.array(point).optional(),
  events: z.array(eventSchema), levels: z.array(levelSchema),
});
export type ChartData = z.infer<typeof chartSchema>;
const metrics = z.object({
  observations: z.number().int().nonnegative(), brier: finite.nullable().optional(), log_loss: finite.nullable().optional(),
  accuracy: finite.nullable().optional(), ece: finite.nullable().optional(), calibration_bins: z.record(z.string(), z.array(record)).optional(),
}).passthrough();
export type MetricSet = z.infer<typeof metrics>;
const modelHorizon = z.object({
  status: z.string(), model_kind: z.string().nullable(),
  training_start_ms: timestamp.nullable(), training_end_ms: timestamp.nullable(),
  final_test_start_ms: timestamp.nullable(), final_test_end_ms: timestamp.nullable(),
  selected_strategy_metrics: metrics.nullable(), final_test_metrics: metrics.nullable(),
  comparisons: z.array(z.object({ model_kind: z.string(), metrics: metrics.nullable(), same_population_reference_baseline_metrics: metrics.nullable(), fold_ids: z.array(z.number().int()) })),
  calibration: record.nullable(), coverage: record.nullable(), final_coverage: record.nullable(), paired_comparison: record.nullable(),
  limitations: z.array(z.string()),
}).passthrough();
export type ModelHorizon = z.infer<typeof modelHorizon>;
export const webAnalysisSchema = z.object({
  api_version: z.literal('1'), analysis_id: z.string(), mode: z.enum(['live', 'replay']), market: z.literal('spot'), exchange: z.literal('binance'),
  summary: z.object({
    symbol: z.string(), reference_price: finite.nullable(), reference_time_ms: timestamp.nullable(), as_of_ms: timestamp,
    change_percent: finite.nullable(), change_basis: z.literal('previous_closed_H1'), volume: finite.nullable(),
    volume_basis: z.literal('base_asset_last_closed_H1'), atr_percent: finite.nullable(), quality: z.enum(['ok', 'degraded']),
    base_asset: z.string().nullable().optional(), quote_asset: z.string().nullable().optional(), tick_size: z.number().finite().positive().nullable().optional(),
  }),
  analysis: engine, charts: z.object({ H1: chartSchema, H4: chartSchema, D1: chartSchema }),
  model_quality: z.object({
    configured: z.boolean(), model_version: z.string().nullable(), dataset_version: z.string().nullable(),
    availability_semantics: z.string().nullable(), horizons: z.record(z.string(), modelHorizon),
  }),
  cache: z.object({ hit: z.boolean(), expires_at_ms: timestamp }), warnings: z.array(z.string()),
}).passthrough().superRefine((data, ctx) => {
  const steps: Record<Timeframe, number> = { H1: 3_600_000, H4: 14_400_000, D1: 86_400_000 };
  for (const tf of ['H1', 'H4', 'D1'] as const) {
    const c = data.charts[tf];
    if (c.candles.some((p, i) => p.time_ms + steps[tf] > data.analysis.as_of_ms || (i > 0 && p.time_ms <= c.candles[i - 1].time_ms))) {
      ctx.addIssue({ code: 'custom', message: 'Gráfico contém candle futuro, incompleto ou fora de ordem.', path: ['charts', tf] });
    }
    if (c.events.some(e => e.available_at_ms > data.analysis.as_of_ms) || c.levels.some(l => l.available_at_ms > data.analysis.as_of_ms)) {
      ctx.addIssue({ code: 'custom', message: 'Gráfico contém evento ainda indisponível.', path: ['charts', tf] });
    }
  }
  if (data.summary.symbol !== data.analysis.symbol || data.summary.as_of_ms !== data.analysis.as_of_ms) {
    ctx.addIssue({ code: 'custom', message: 'Referências da análise não coincidem.' });
  }
});
export type WebAnalysis = z.infer<typeof webAnalysisSchema>;
export interface ProgressUpdate { stage: string; status: 'queued' | 'running' | 'completed' | 'failed'; message: string }
export interface ApiFailure { code: string; message: string; request_id?: string }
