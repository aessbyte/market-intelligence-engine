"""JSON on stdout, operational errors on stderr, never silent simulated fallback."""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from .binance import BASE_URLS, BinanceClient, PublicHTTP
from .engine import analyze
from .config import AnalysisConfig
from .models import MarketError
from .render import render_text


def parse_cutoff(value: str) -> int:
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            raise ValueError("timezone required")
        return int(dt.timestamp() * 1000)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "Use ISO 8601 with timezone, e.g. 2026-01-01T00:00:00Z"
        ) from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Auditable Binance spot market analysis")
    commands = parser.add_subparsers(dest="command", required=True)
    live = commands.add_parser("analyze", help="Fetch real public Binance data")
    live.add_argument("symbol")
    live.add_argument("--bars", type=int, default=250)
    live.add_argument("--as-of", type=parse_cutoff)
    live.add_argument("--base-url", choices=BASE_URLS, default=BASE_URLS[0])
    live.add_argument("--snapshot", type=Path, help="Save raw input for exact replay")
    replay = commands.add_parser("replay", help="Analyze an explicitly labeled saved snapshot")
    replay.add_argument("input", type=Path)
    for command in (live, replay):
        command.add_argument("--output", type=Path, help="Write JSON instead of stdout")
        command.add_argument("--format", choices=("json", "text"), default="json")
        command.add_argument("--config", type=Path, help="JSON analysis configuration")
        command.add_argument("--schema-version", type=int, choices=(1, 2), default=2)
    args = parser.parse_args(argv)
    try:
        if args.command == "analyze":
            client = BinanceClient(PublicHTTP(args.base_url))
            snapshot = client.snapshot(args.symbol, args.bars, args.as_of)
            if args.snapshot:
                args.snapshot.write_text(
                    json.dumps(snapshot, allow_nan=False, indent=2) + "\n", encoding="utf-8"
                )
        else:
            snapshot = json.loads(args.input.read_text(encoding="utf-8"))
        if not isinstance(snapshot, dict):
            raise MarketError("Snapshot must be a JSON object")
        config = (
            AnalysisConfig.from_dict(json.loads(args.config.read_text(encoding="utf-8")))
            if args.config
            else AnalysisConfig()
        )
        result = analyze(snapshot, config, result_version=args.schema_version)
        output = (
            render_text(result)
            if args.format == "text"
            else json.dumps(result, ensure_ascii=False, allow_nan=False, indent=2) + "\n"
        )
        if args.output:
            args.output.write_text(output, encoding="utf-8")
        else:
            sys.stdout.write(output)
        return 0 if result["status"] == "ok" else 2
    except (MarketError, OSError, ValueError) as exc:
        sys.stderr.write(json.dumps({"error": str(exc)}, ensure_ascii=False) + "\n")
        return 1
