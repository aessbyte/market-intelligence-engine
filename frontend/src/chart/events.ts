import type { EngineEvent, Timeframe } from '../contracts';

export interface ChartCandle {
  time_ms: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface EventOverlay {
  event: EngineEvent;
  time_ms: number;
  price: number;
  color: string;
  direction: 'up' | 'down' | 'neutral';
  label: string;
  retrospective: boolean;
}

export const TIMEFRAME_MS: Record<Timeframe, number> = {
  H1: 3_600_000,
  H4: 14_400_000,
  D1: 86_400_000,
};

const INTERVAL: Record<Timeframe, string> = { H1: '1h', H4: '4h', D1: '1d' };
const WYCKOFF_KINDS = new Set([
  'trading_range', 'range_upper_test', 'range_lower_test',
  'Spring', 'Upthrust', 'SOS', 'SOW', 'LPS', 'LPSY',
]);
const UP_KINDS = new Set(['HH', 'HL', 'Spring', 'SOS', 'LPS']);
const DOWN_KINDS = new Set(['LH', 'LL', 'Upthrust', 'SOW', 'LPSY']);
const RELATION_KINDS = new Set(['HH', 'HL', 'LH', 'LL', 'EH', 'EL']);

export function isWyckoffEvent(event: EngineEvent): boolean {
  return WYCKOFF_KINDS.has(event.kind);
}

export function eventLabel(event: EngineEvent): string {
  const labels: Record<string, string> = {
    swing_high: 'Pivô de máxima', swing_low: 'Pivô de mínima',
    trading_range: 'Trading range', range_upper_test: 'Teste do topo',
    range_lower_test: 'Teste do fundo', false_break: 'Falsa ruptura',
    possible_false_break: 'Possível falsa ruptura',
  };
  return labels[event.kind] ?? event.kind;
}

export function eventMarkerLabel(event: EngineEvent, retrospective = false): string {
  const labels: Record<string, string> = {
    swing_high: 'SH', swing_low: 'SL', trading_range: 'TR',
    range_upper_test: 'RT↑', range_lower_test: 'RT↓',
    false_break: 'FR', possible_false_break: 'FR?', Upthrust: 'UT',
  };
  return `${labels[event.kind] ?? event.kind}${retrospective ? ' · origem' : ''}`;
}

export function eventDirection(event: EngineEvent): 'up' | 'down' | 'neutral' {
  if (UP_KINDS.has(event.kind)) return 'up';
  if (DOWN_KINDS.has(event.kind)) return 'down';
  for (const evidence of event.evidence) {
    if (typeof evidence === 'object' && evidence !== null && 'direction' in evidence) {
      const direction = (evidence as { direction?: unknown }).direction;
      if (direction === 'up' || direction === 'down') return direction;
    }
  }
  return 'neutral';
}

/** The current state is usable only after its revision became available. */
export function visibleEvents(
  events: EngineEvent[], asOfMs: number, timeframe: Timeframe,
): EngineEvent[] {
  return events.filter((event) => {
    if (event.interval !== INTERVAL[timeframe]) return false;
    if (![event.event_time_ms, event.detected_at_ms, event.available_at_ms, event.price]
      .every(Number.isFinite)) return false;
    if (event.price <= 0 || event.event_time_ms > event.detected_at_ms
      || event.detected_at_ms > event.available_at_ms
      || event.available_at_ms > asOfMs) return false;
    if (event.confirmed_at_ms !== null && (!Number.isFinite(event.confirmed_at_ms)
      || event.confirmed_at_ms < event.detected_at_ms
      || event.confirmed_at_ms > event.available_at_ms)) return false;
    if (event.invalidated_at_ms !== null && (!Number.isFinite(event.invalidated_at_ms)
      || event.invalidated_at_ms < event.detected_at_ms
      || event.invalidated_at_ms > event.available_at_ms)) return false;
    if (event.state === 'confirmed') {
      return event.confirmed_at_ms !== null && Number.isFinite(event.confirmed_at_ms)
        && event.confirmed_at_ms >= event.detected_at_ms
        && event.confirmed_at_ms <= event.available_at_ms;
    }
    if (event.state === 'invalidated') {
      return event.invalidated_at_ms !== null && Number.isFinite(event.invalidated_at_ms)
        && event.invalidated_at_ms >= event.detected_at_ms
        && event.invalidated_at_ms <= event.available_at_ms;
    }
    return event.state === 'candidate';
  }).sort((a, b) => a.available_at_ms - b.available_at_ms || a.id.localeCompare(b.id));
}

/** An availability at 14:00 belongs to the candle that closed at 13:59:59.999. */
export function candleForAvailability(
  candles: ChartCandle[], availableAtMs: number, timeframe: Timeframe, asOfMs: number,
): ChartCandle | undefined {
  const instant = availableAtMs - 1;
  const step = TIMEFRAME_MS[timeframe];
  let left = 0;
  let right = candles.length - 1;
  let index = -1;
  while (left <= right) {
    const middle = Math.floor((left + right) / 2);
    if (candles[middle].time_ms <= instant) { index = middle; left = middle + 1; }
    else right = middle - 1;
  }
  const candle = candles[index];
  return candle && instant < candle.time_ms + step
    && candle.time_ms + step <= asOfMs ? candle : undefined;
}

export interface OverlayOptions {
  structure: boolean;
  wyckoff: boolean;
  origins: boolean;
  limit?: number;
  states?: EngineEvent['state'][];
  minSpacingMs?: number;
}

export function eventOverlays(
  events: EngineEvent[], candles: ChartCandle[], asOfMs: number,
  timeframe: Timeframe, options: OverlayOptions,
): EventOverlay[] {
  const known = visibleEvents(events, asOfMs, timeframe).filter((event) =>
    (isWyckoffEvent(event) ? options.wyckoff : options.structure)
      && (options.states ?? ['confirmed']).includes(event.state),
  );
  // A relation and its confirmed pivot are the same observation, not two signals.
  const identity = (event: EngineEvent) =>
    `${event.state}:${event.event_time_ms}:${event.price}:${event.available_at_ms}`;
  const relations = new Set(known.filter((event) => RELATION_KINDS.has(event.kind)).map(identity));
  const distinct = known.filter((event) => !['swing_high', 'swing_low'].includes(event.kind)
    || !relations.has(identity(event)));
  const selected: EngineEvent[] = [];
  const stateAt = (event: EngineEvent) => (event.state === 'confirmed' ? event.confirmed_at_ms
    : event.state === 'invalidated' ? event.invalidated_at_ms : event.available_at_ms) ?? event.available_at_ms;
  for (const event of [...distinct].reverse()) {
    if (selected.some((other) => Math.abs(stateAt(other) - stateAt(event)) < (options.minSpacingMs ?? 0))) continue;
    selected.push(event);
    if (selected.length >= (options.limit ?? 20)) break;
  }
  const result: EventOverlay[] = [];
  for (const event of selected) {
    const candle = candleForAvailability(candles, stateAt(event), timeframe, asOfMs);
    if (!candle) continue;
    const direction = eventDirection(event);
    const color = event.state === 'invalidated' ? '#8c9aaa'
      : event.state === 'candidate' ? '#e9bc65'
      : direction === 'up' ? '#38cba0' : direction === 'down' ? '#f17888' : '#91baff';
    result.push({ event, time_ms: candle.time_ms, price: event.price, color,
      direction, label: eventLabel(event), retrospective: false });
    if (options.origins && event.event_time_ms !== candle.time_ms) {
      const origin = candles.find((item) => item.time_ms === event.event_time_ms);
      if (origin && origin.time_ms + TIMEFRAME_MS[timeframe] <= asOfMs) {
        result.push({ event, time_ms: origin.time_ms, price: event.price,
          direction: 'neutral', color: '#6c7c93',
          label: `${eventLabel(event)} · origem retrospectiva`, retrospective: true });
      }
    }
  }
  return result.sort((a, b) => a.time_ms - b.time_ms || a.event.id.localeCompare(b.event.id));
}

export function utcLabel(timestampMs: number | null | undefined): string {
  if (timestampMs == null || !Number.isFinite(timestampMs)) return 'Indisponível';
  return `${new Date(timestampMs).toISOString().replace('T', ' ').slice(0, 19)} UTC`;
}

export function priceDecimals(value: number, tickSize?: number | string | null): number {
  const tick = tickSize == null ? NaN : Number(tickSize);
  if (Number.isFinite(tick) && tick > 0) {
    const [coefficient, exponentText] = String(tick).toLowerCase().split('e');
    const decimals = (coefficient.split('.')[1] ?? '').length - Number(exponentText ?? 0);
    return Math.min(12, Math.max(0, decimals));
  }
  return Math.abs(value) < 1 ? 8 : Math.abs(value) < 10 ? 4 : 2;
}

export function priceLabel(value: number, tickSize?: number | string | null): string {
  return new Intl.NumberFormat('pt-BR', {
    minimumFractionDigits: priceDecimals(value, tickSize),
    maximumFractionDigits: priceDecimals(value, tickSize),
  }).format(value);
}
