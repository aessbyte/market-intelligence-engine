import { describe, expect, it } from 'vitest';
import { humanize, numeric, price, record, utc } from './ui';

describe('Formatação de valores observados', () => {
  it('mantém campos ausentes como indisponíveis', () => {
    expect(price(null)).toBe('Indisponível');
    expect(price(Number.NaN)).toBe('Indisponível');
    expect(utc(null)).toBe('Indisponível');
    expect(numeric(null)).toBeNull();
  });

  it('usa a precisão de tick informada pelo backend inclusive para ativos pequenos', () => {
    expect(price(.00012345, '0.00000001')).toBe('0,00012345');
    expect(price(82341.52, '0.01000000')).toBe('82.341,52');
  });

  it('não converte quantidades ausentes em zero nem aceita escala infinita', () => {
    expect(numeric(Number.POSITIVE_INFINITY)).toBeNull();
    expect(price(.00012345, 'invalid')).toBe('0,00012345');
    expect(record(null)).toEqual({});
  });

  it('mantém o fuso UTC e descreve abstinência explicitamente', () => {
    expect(utc(Date.UTC(2026, 9, 12, 3, 45))).toContain('03:45 UTC');
    expect(humanize('UNVALIDATED_MODEL')).toBe('Modelo não validado');
  });
});
