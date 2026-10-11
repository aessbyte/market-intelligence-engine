"""Versioned descriptive rules. Thresholds are heuristics, not learned forecasts."""

from dataclasses import asdict, dataclass

from .models import Features, Regime


@dataclass(frozen=True)
class Rules:
    version: str = "regime-v1"
    trend_gap_atr: float = 0.5
    trend_slope_atr: float = 0.05
    bull_rsi: float = 55.0
    bear_rsi: float = 45.0
    sideways_gap_atr: float = 0.5
    sideways_slope_atr: float = 0.05
    sideways_efficiency: float = 0.3


RULES = Rules()


def classify(f: Features, rules: Rules = RULES) -> tuple[Regime, list[dict[str, object]]]:
    checks = {
        "alta": {
            "close_above_ema20": f.close > f.ema20,
            "ema_gap_atr": f.ema_gap_atr >= rules.trend_gap_atr,
            "ema20_slope5_atr": f.ema20_slope5_atr >= rules.trend_slope_atr,
            "rsi14": f.rsi14 >= rules.bull_rsi,
        },
        "baixa": {
            "close_below_ema20": f.close < f.ema20,
            "ema_gap_atr": f.ema_gap_atr <= -rules.trend_gap_atr,
            "ema20_slope5_atr": f.ema20_slope5_atr <= -rules.trend_slope_atr,
            "rsi14": f.rsi14 <= rules.bear_rsi,
        },
        "lateralizacao": {
            "ema_gap_atr": abs(f.ema_gap_atr) < rules.sideways_gap_atr,
            "ema20_slope5_atr": abs(f.ema20_slope5_atr) < rules.sideways_slope_atr,
            "efficiency20": f.efficiency20 <= rules.sideways_efficiency,
        },
    }
    regime = next(
        (Regime(name) for name, group in checks.items() if all(group.values())), Regime.UNKNOWN
    )
    evidence: list[dict[str, object]] = [
        {"candidate": name, "checks": group, "matched": all(group.values())}
        for name, group in checks.items()
    ]
    evidence.append({"observed": asdict(f), "thresholds": asdict(rules)})
    return regime, evidence


def aggregate(regimes: list[Regime]) -> Regime:
    # Conservative agreement: all three timeframes must support the same regime.
    return regimes[0] if len(regimes) == 3 and len(set(regimes)) == 1 else Regime.UNKNOWN


def scenarios(regime: Regime) -> list[dict[str, object]]:
    return [
        {
            "name": "persistencia_descritiva",
            "current_regime": regime.value,
            "condition": "Novos candles fechados continuam satisfazendo todas as regras atuais.",
            "invalidation": "Qualquer regra deixa de ser satisfeita; recalcular com dados fechados.",
            "probability": None,
            "price_target": None,
        },
        {
            "name": "transicao",
            "condition": "Novos candles fechados satisfazem outro regime.",
            "invalidation": "As regras do regime alternativo nao sao satisfeitas.",
            "probability": None,
            "price_target": None,
        },
    ]
