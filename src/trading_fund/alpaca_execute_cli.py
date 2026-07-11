from __future__ import annotations

import argparse
import json

from trading_fund.alpaca_execute import execute_alpaca_strategy


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Execute consensus strategy on Alpaca with risk caps and position limits."
    )
    parser.add_argument(
        "--symbols",
        default="AAPL,MSFT,NVDA,TSLA,AMD,AMZN,META,GOOGL",
        help="Comma-separated symbols to scan for new entries.",
    )
    parser.add_argument(
        "--max-new-positions",
        type=int,
        default=0,
        help="Maximum number of new positions to open. Use 0 for auto (strategy decides).",
    )
    parser.add_argument(
        "--max-risk-pct",
        type=float,
        default=0.05,
        help="Maximum portfolio risk budget for all new positions (0.05 = 5%%).",
    )
    parser.add_argument(
        "--trailing-stop-pct",
        type=float,
        default=0.03,
        help="Trailing stop distance as decimal (0.03 = 3%%). Use 0 to disable.",
    )
    parser.add_argument(
        "--no-trailing-on-existing",
        action="store_true",
        help="Do not auto-apply trailing stops to currently open positions.",
    )
    parser.add_argument(
        "--no-dust-cleanup",
        action="store_true",
        help="Disable automatic cleanup market orders for residual dust quantities.",
    )
    parser.add_argument(
        "--dust-cleanup-min-qty",
        type=float,
        default=0.0001,
        help="Minimum residual quantity required before placing a cleanup order.",
    )
    parser.add_argument(
        "--corr-soft-limit",
        type=float,
        default=0.75,
        help="Scale down position sizes when absolute return correlation exceeds this threshold.",
    )
    parser.add_argument(
        "--corr-hard-limit",
        type=float,
        default=0.9,
        help="Skip new positions when absolute return correlation exceeds this threshold.",
    )
    parser.add_argument(
        "--exposure-soft-multiplier",
        type=float,
        default=0.5,
        help="Size multiplier applied when the soft correlation limit is breached.",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually submit market orders. If omitted, runs a dry-run plan only.",
    )
    parser.add_argument(
        "--execute-rebalance-sells",
        action="store_true",
        help="When executing orders, also place strategy-driven exit orders for weak holdings.",
    )
    parser.add_argument(
        "--env",
        default=None,
        help="Optional path to env file.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    symbols = [token.strip().upper() for token in args.symbols.split(",") if token.strip()]
    result = execute_alpaca_strategy(
        symbols=symbols,
        env_path=args.env,
        max_new_positions=args.max_new_positions,
        max_risk_pct=args.max_risk_pct,
        trailing_stop_pct=args.trailing_stop_pct,
        apply_trailing_to_existing=not args.no_trailing_on_existing,
        enable_dust_cleanup=not args.no_dust_cleanup,
        dust_cleanup_min_qty=args.dust_cleanup_min_qty,
        correlation_soft_limit=args.corr_soft_limit,
        correlation_hard_limit=args.corr_hard_limit,
        exposure_soft_multiplier=args.exposure_soft_multiplier,
        execute_rebalance_sells=args.execute_rebalance_sells,
        execute_orders=args.execute,
    )
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())