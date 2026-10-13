import { describe, expect, it } from 'vitest';
import { webAnalysisSchema } from './contracts';
import { testFixture } from './test/fixture';

describe('Contrato web com dados explicitamente sintéticos', () => {
  it('preserva a origem, o corte e as probabilidades ausentes', () => {
    const value = webAnalysisSchema.parse(structuredClone(testFixture));
    expect(value.analysis.provenance.simulated).toBe(true);
    expect(value.analysis.predictions.map(p => p.probabilities)).toEqual([null, null, null]);
    expect(value.summary.as_of_ms).toBe(value.analysis.as_of_ms);
  });
  it('aceita classificação de pivô ainda indisponível', () => {
    const value = structuredClone(testFixture);
    const level = value.charts.H1.levels[0];
    expect(level).toBeDefined();
    level.label = null;
    expect(webAnalysisSchema.parse(value).charts.H1.levels[0].label).toBeNull();
  });
  it('rejeita uma probabilidade pública de modelo inelegível', () => {
    const value = structuredClone(testFixture);
    value.analysis.predictions[0].probabilities = { bearish: 0.2, neutral: 0.5, bullish: 0.3 };
    expect(webAnalysisSchema.safeParse(value).success).toBe(false);
  });
  it('rejeita probabilidades que não somam um', () => {
    const value = structuredClone(testFixture);
    value.analysis.predictions[0].status = 'VALIDATED_MODEL';
    value.analysis.predictions[0].probabilities = { bearish: 0.2, neutral: 0.2, bullish: 0.3 };
    expect(webAnalysisSchema.safeParse(value).success).toBe(false);
  });
  it('rejeita eventos cuja revisão depende do futuro', () => {
    const value = structuredClone(testFixture);
    value.charts.H1.events[0].available_at_ms = value.analysis.as_of_ms + 1;
    expect(webAnalysisSchema.safeParse(value).success).toBe(false);
  });
  it('rejeita candles incompletos e duplicados', () => {
    const value = structuredClone(testFixture);
    value.charts.H1.candles[0].time_ms = value.analysis.as_of_ms;
    expect(webAnalysisSchema.safeParse(value).success).toBe(false);
    const duplicate = structuredClone(testFixture);
    duplicate.charts.H1.candles[1].time_ms = duplicate.charts.H1.candles[0].time_ms;
    expect(webAnalysisSchema.safeParse(duplicate).success).toBe(false);
  });
  it('rejeita símbolos e referências inconsistentes', () => {
    const value = structuredClone(testFixture);
    value.summary.symbol = 'OUTROUSDT';
    expect(webAnalysisSchema.safeParse(value).success).toBe(false);
  });
});
