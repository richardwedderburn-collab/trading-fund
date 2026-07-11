from __future__ import annotations

import argparse

from trading_fund.backtest import (
    export_backtest_csv,
    format_backtest_report,
    run_five_year_backtest,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a 5-year Alpaca backtest and evaluate gateway thresholds."
    )
    parser.add_argument(
        "--symbols",
        default="AAPL,MSFT,NVDA,TSLA",
        help="Comma-separated stock tickers to backtest.",
    )
    parser.add_argument(
        "--base-position-usd",
        type=float,
        default=1000.0,
        help="Base position size used by the consensus engine.",
    )
    parser.add_argument(
        "--env",
        default=None,
        help="Optional path to .env file.",
    )
    parser.add_argument(
        "--export-dir",
        default=None,
        help="Optional directory for CSV exports (summary, sensitivity, per-symbol, trades).",
    )
    parser.add_argument(
        "--walk-forward",
        action="store_true",
        help="Enable walk-forward optimization with rolling train/test windows.",
    )
    parser.add_argument(
        "--wf-train-years",
        type=int,
        default=3,
        help="Training window size in years for walk-forward mode.",
    )
    parser.add_argument(
        "--wf-test-months",
        type=int,
        default=6,
        help="Test window size in months for walk-forward mode.",
    )
    parser.add_argument(
        "--degradation-threshold",
        type=float,
        default=0.35,
        help="Warn when walk-forward PnL drops more than this fraction vs in-sample.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    symbols = [item.strip().upper() for item in args.symbols.split(",") if item.strip()]
    result = run_five_year_backtest(
        symbols=symbols,
        env_path=args.env,
        base_position_usd=args.base_position_usd,
        walk_forward=args.walk_forward,
        walk_forward_train_years=args.wf_train_years,
        walk_forward_test_months=args.wf_test_months,
        degradation_threshold=args.degradation_threshold,
    )
    print(format_backtest_report(result))
    if args.export_dir:
        exported = export_backtest_csv(result, args.export_dir)
        print("")
        print("CSV exports:")
        for key, path in exported.items():
            print(f"- {key}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())