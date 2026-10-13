import { describe, expect, it } from 'vitest';
import type { EngineEvent } from '../contracts';
import { candleForAvailability, eventOverlays, priceDecimals, priceLabel, visibleEvents } from './events';

const HOUR = 3_600_000;
const candles = Array.from({ length: 6 }, (_, index) => ({
  time_ms: index * HOUR, open: 100, high: 110, low: 90, close: 102, volume: 500,
}));
function pivot(overrides: Partial<EngineEvent> = {}): EngineEvent {
  return { id: 'H1:swing_high:0', kind: 'swing_high', interval: '1h',
    event_time_ms: 0, detected_at_ms: HOUR, available_at_ms: 3 * HOUR,
    confirmed_at_ms: 3 * HOUR, invalidated_at_ms: null, price: 110,
    state: 'confirmed', evidence: [], parameters: {}, ...overrides };
}

describe('overlays causais', () => {
  it('marca um pivô no candle da confirmação e não na origem histórica', () => {
    const markers = eventOverlays([pivot()], candles, 6 * HOUR, 'H1',
      { structure: true, wyckoff: true, origins: false });
    expect(markers).toHaveLength(1);
    expect(markers[0].time_ms).toBe(2 * HOUR);
    expect(markers[0].price).toBe(110);
    expect(markers[0].retrospective).toBe(false);
  });
  it('uma origem opcional é explicitamente retrospectiva', () => {
    const markers = eventOverlays([pivot()], candles, 6 * HOUR, 'H1',
      { structure: true, wyckoff: true, origins: true });
    expect(markers[0].time_ms).toBe(0);
    expect(markers[0].retrospective).toBe(true);
    expect(markers[0].label).toContain('retrospectiva');
  });
  it('oculta confirmação futura e revisões ainda indisponíveis', () => {
    expect(visibleEvents([pivot()], 2 * HOUR, 'H1')).toEqual([]);
    const futureRevision = pivot({ available_at_ms: 7 * HOUR,
      state: 'invalidated', invalidated_at_ms: 7 * HOUR });
    expect(visibleEvents([futureRevision], 6 * HOUR, 'H1')).toEqual([]);
    expect(visibleEvents([pivot({ confirmed_at_ms: 7 * HOUR })], 6 * HOUR, 'H1')).toEqual([]);
  });
  it('posiciona o estado invalidado no candle da invalidação', () => {
    const invalidated = pivot({ state: 'invalidated', invalidated_at_ms: 5 * HOUR,
      available_at_ms: 5 * HOUR });
    const markers = eventOverlays([invalidated], candles, 6 * HOUR, 'H1',
      { structure: true, wyckoff: true, origins: false, states: ['invalidated'] });
    expect(markers[0].time_ms).toBe(4 * HOUR);
    expect(markers[0].color).toBe('#8c9aaa');
  });
  it('não coloca sinais em candles abertos, lacunas ou outro intervalo', () => {
    expect(candleForAvailability(candles, 6 * HOUR, 'H1', 5.5 * HOUR)).toBeUndefined();
    expect(candleForAvailability(candles.filter((_, index) => index !== 2),
      3 * HOUR, 'H1', 6 * HOUR)).toBeUndefined();
    expect(visibleEvents([pivot({ interval: '4h' })], 6 * HOUR, 'H1')).toEqual([]);
  });
  it('respeita grupos e usa o preço original do evento Wyckoff', () => {
    const spring = pivot({ id: 'spring', kind: 'Spring', price: 90 });
    const markers = eventOverlays([pivot(), spring], candles, 6 * HOUR, 'H1',
      { structure: false, wyckoff: true, origins: false });
    expect(markers.map((marker) => marker.event.id)).toEqual(['spring']);
    expect(markers[0].price).toBe(90);
  });
  it('sem eventos disponíveis produz nenhuma anotação', () => {
    expect(eventOverlays([], candles, 6 * HOUR, 'H1',
      { structure: true, wyckoff: true, origins: false })).toEqual([]);
  });
  it('evita representar a relação HH e seu pivô como dois sinais independentes', () => {
    const relation = pivot({ id: 'H1:HH:0', kind: 'HH' });
    const markers = eventOverlays([pivot(), relation], candles, 6 * HOUR, 'H1',
      { structure: true, wyckoff: true, origins: false });
    expect(markers).toHaveLength(1);
    expect(markers[0].event.kind).toBe('HH');
  });
  it('respeita a precisão de preços baixos e o tick size sem alterar o valor do evento', () => {
    expect(priceDecimals(0.0351, '0.0001')).toBe(4);
    expect(priceLabel(0.0351, '0.0001')).toBe('0,0351');
    expect(priceDecimals(1.25, '0.25')).toBe(2);
    expect(priceDecimals(0.00000001, '1e-8')).toBe(8);
  });
  it('reduz anotações próximas para legibilidade sem remover eventos disponíveis', () => {
    const input = [3, 4, 5].map((hour) => pivot({ id: `pivot-${hour}`,
      available_at_ms: hour * HOUR, confirmed_at_ms: hour * HOUR }));
    const markers = eventOverlays(input, candles, 6 * HOUR, 'H1',
      { structure: true, wyckoff: true, origins: false, limit: 4, minSpacingMs: 2 * HOUR });
    expect(markers.map((marker) => marker.event.id)).toEqual(['pivot-3', 'pivot-5']);
    expect(visibleEvents(input, 6 * HOUR, 'H1')).toHaveLength(3);
    expect(input).toHaveLength(3);
  });
});
