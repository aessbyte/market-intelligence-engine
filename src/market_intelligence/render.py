"""Deterministic plain text presentation of the structured analysis."""

from datetime import datetime, timezone
from typing import Any

STATE_LABELS = {
    "candidate": "candidato",
    "confirmed": "confirmado por regra",
    "invalidated": "invalidado",
    "active": "ativo",
    "awaiting_confirmation": "aguardando confirmacao",
}
RULE_LABELS = {
    "two_structural_votes": "estrutura direcional em pelo menos dois intervalos",
    "no_opposing_structural_vote": "nenhum intervalo com estrutura oposta",
    "fresh_confirmed_directional_event": "evento direcional confirmado recente",
    "H1_invalidation_boundary_available_and_holding": "nivel de invalidacao H1 conhecido e preservado",
    "all_timeframes_available": "tres intervalos disponiveis e liquidez recente suficiente",
    "two_opposing_structural_votes": "estrutura oposta em pelo menos dois intervalos",
    "H1_close_below_support": "fechamento H1 abaixo do suporte",
    "H1_close_above_resistance": "fechamento H1 acima da resistencia",
    "inside_confirmed_ranges_on_two_timeframes": "preco dentro de faixas confirmadas em dois intervalos",
    "no_two_directional_structural_votes": "ausencia de concordancia direcional em dois intervalos",
    "confirmed_directional_scenario": "ativacao de cenario direcional",
    "two_confirmed_range_breaks": "rompimento confirmado de faixa em dois intervalos",
}


def _time(value: int) -> str:
    return datetime.fromtimestamp(value / 1000, timezone.utc).isoformat()


def _readable(item: dict[str, Any]) -> str:
    if "rule" in item:
        detail = RULE_LABELS.get(item["rule"], str(item["rule"]))
        detail += " — " + ("satisfeita" if item.get("met") else "nao satisfeita")
        if isinstance(item.get("observed"), (int, float)):
            detail += f"; observado: {item['observed']}"
        if item.get("required") is not None:
            detail += f"; necessario: {item['required']}"
        if item.get("level"):
            detail += f"; nivel: {item['level']['price']:.8g}"
        return detail
    name = item.get("timeframe", "")
    if item.get("kind"):
        return f"{name}: {item['kind']} confirmado em {_time(item['confirmed_at_ms'])}"
    if item.get("structural_trend"):
        return f"{name}: estrutura {item['structural_trend']}; fechamento {item['close']:.8g}"
    if item.get("range_id"):
        return f"{name}: fechamento dentro da faixa {item['lower']:.8g}–{item['upper']:.8g}"
    return str(item.get("observation", "evidencia registrada no JSON"))


def render_text(result: dict[str, Any]) -> str:
    date = datetime.fromtimestamp(result["as_of_ms"] / 1000, timezone.utc).isoformat()
    lines = [
        f"{result['symbol']} | {date}",
        f"Origem: {result['provenance']['source']} | status: {result['status']}",
        f"Regime de indicadores: {result['regime']}",
    ]
    for name in ("D1", "H4", "H1"):
        frame = result["timeframes"][name]
        structure, wyckoff = frame.get("structure"), frame.get("wyckoff")
        if not frame["quality"]["valid"]:
            lines.append(f"{name}: dados indisponiveis — {'; '.join(frame['quality']['errors'])}")
            continue
        lines.append(
            f"{name}: regime {frame['regime']} | estrutura {structure['trend'] if structure else 'indisponivel'}"
        )
        if structure:
            lines.append(
                "  Niveis: "
                + ", ".join(
                    f"{level['kind']}={level['price']:.8g}" for level in structure["levels"]
                )
            )
            events = [
                e for e in structure["events"] if e["kind"] in ("BOS", "CHoCH", "false_break")
            ]
            for event in events[-4:]:
                lines.append(
                    f"  {event['kind']}: {STATE_LABELS[event['state']]} | preco {event['price']:.8g} | grafico {_time(event['event_time_ms'])} | detectado {_time(event['detected_at_ms'])} | disponivel {_time(event['available_at_ms'])}"
                )
        if wyckoff:
            trading_range = wyckoff["range"]
            if trading_range:
                lines.append(
                    f"  Faixa: {trading_range['lower']:.8g}–{trading_range['upper']:.8g} ({STATE_LABELS[trading_range['state']]})"
                )
            else:
                lines.append("  Faixa: evidencia insuficiente")
            events = [
                e
                for e in wyckoff["events"]
                if e["kind"] in ("Spring", "Upthrust", "SOS", "SOW", "LPS", "LPSY")
            ]
            for event in events[-5:]:
                lines.append(
                    f"  Possivel {event['kind']}: {STATE_LABELS[event['state']]} | grafico {_time(event['event_time_ms'])}; fase nao estabelecida"
                )
                evidence = event["evidence"][0]
                lines.append(
                    f"    Observacao: minimo {evidence['low']:.8g}, maximo {evidence['high']:.8g}, fechamento {evidence['close']:.8g}; faixa {evidence['lower']:.8g}–{evidence['upper']:.8g}"
                )
            for hypothesis in wyckoff["hypotheses"][-3:]:
                lines.append(f"  Hipotese: {hypothesis['interpretation']} ({hypothesis['state']})")
            if wyckoff["liquidity_warnings"]:
                lines.append(
                    f"  Avisos de liquidez observada: {len(wyckoff['liquidity_warnings'])}"
                )
    comparison = result.get("multitimeframe")
    if comparison:
        lines.append(f"Consenso estrutural: {comparison['structural_consensus']}")
        for conflict in comparison["conflicts"]:
            lines.append(
                f"Conflito: {' / '.join(conflict['timeframes'])}: {' / '.join(conflict['observed'])}"
            )
    for scenario in result["scenarios"]:
        state = scenario.get("state", "descritivo")
        lines.append(f"Cenario {scenario['name']}: {STATE_LABELS.get(state, state)}")
        lines.append("  Tese: " + scenario.get("thesis", scenario["condition"]))
        for key, label in (
            ("favorable_evidence", "Favoravel"),
            ("contrary_evidence", "Contraria"),
            ("activation_conditions", "Ativacao"),
            ("invalidation_conditions", "Invalidacao"),
        ):
            for condition in scenario.get(key, []):
                lines.append(f"  {label}: {_readable(condition)}")
        if scenario.get("insufficient_data"):
            lines.append("  Dados insuficientes: " + ", ".join(scenario["insufficient_data"]))
    lines.append(
        "Probabilidades e retornos esperados: indisponiveis; modelo estatistico nao validado."
    )
    lines.extend("Limitacao: " + limitation for limitation in result["limitations"])
    return "\n".join(lines) + "\n"
