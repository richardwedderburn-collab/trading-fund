# Multi-Agent Quantitative Trading Fund Blueprint

This project provides a concrete starting point for a modular trading fund architecture centered on:

- a consensus-driven trade evaluation engine
- market-specific gate validation for crypto, stock, and polymarket signals
- deployment and safety scaffolding for CI/CD, canary rollout, and kill-switch behavior

## Components

- `src/trading_fund/consensus.py` implements the gate evaluation and consensus logic.
- `src/trading_fund/ledger.py` fetches and aggregates on-chain ERC-20 transfer activity for polymarket monitoring.
- `src/trading_fund/backtest.py` runs 5-year Alpaca historical backtests and gateway sensitivity analysis.
- `tests/test_consensus_engine.py` exercises the main decision paths.
- `tests/test_ledger.py` validates ledger metric aggregation and configuration behavior.
- `tests/test_backtest.py` validates backtest metrics and report output.
- `deploy/` contains infrastructure and workflow templates.

## Verification

Run:

```bash
pytest -q
```

## Environment setup

Copy the sample file and add your real keys:

```bash
copy .env.example .env
```

Then edit [.env](.env) and fill in the values for the services you want to use for live testing.

## Five-year Alpaca backtest

Add your Alpaca credentials in `.env`:

- `ALPACA_API_KEY`
- `ALPACA_API_SECRET`

Run a five-year backtest and print strategy/gateway diagnostics:

```bash
python run_backtest.py --symbols AAPL,MSFT,NVDA,TSLA --base-position-usd 1000
```

To export trade logs and summary tables to CSV:

```bash
python run_backtest.py --symbols AAPL,MSFT,NVDA,TSLA --base-position-usd 1000 --export-dir outputs/backtest
```

The output includes:

- trade count, win rate, total PnL, and average PnL per trade
- max drawdown, Sharpe ratio, and worst trade size
- a gateway sensitivity table for candidate stock volume floors
- per-symbol best gateway threshold recommendations
- the best-performing gateway threshold to guide logic improvements

## Alpaca live strategy execution

Plan up to 5 new Alpaca positions with a total risk cap of 5% equity:

```bash
python run_alpaca_strategy.py --max-new-positions 5 --max-risk-pct 0.05
```

Submit live paper orders (execute mode):

```bash
python run_alpaca_strategy.py --max-new-positions 5 --max-risk-pct 0.05 --execute
```

Submit live paper orders with 3% trailing stops for current and newly opened positions:

```bash
python run_alpaca_strategy.py --max-new-positions 5 --max-risk-pct 0.05 --trailing-stop-pct 0.03 --execute
```

Notes:

- Existing held symbols are skipped.
- Orders are ranked by consensus votes and momentum.
- Total new notional is capped by the risk budget.
- Existing open positions get a trailing stop if one is not already open.
- Default trailing stop is 3% (`--trailing-stop-pct 0.03`).
- Set `--trailing-stop-pct 0` to disable trailing stops.
- Use `--no-trailing-on-existing` to skip existing positions.
- Residual dust left after whole-share fallback is auto-cleaned with market orders.
- Use `--no-dust-cleanup` to disable dust cleanup or `--dust-cleanup-min-qty` to tune the threshold.

## Polymarket ledger monitoring

The backend now exposes a ledger snapshot endpoint:

- `GET /api/polymarket-ledger`

Required .env keys:

- `POLYMARKET_RPC_URL` (EVM RPC endpoint)
- `POLYMARKET_TOKEN_CONTRACT` (contract used for transfer-log activity)

Optional .env keys:

- `POLYMARKET_FROM_BLOCK` (default `0`)
- `POLYMARKET_TO_BLOCK` (default latest block)
- `POLYMARKET_TOKEN_DECIMALS` (default `6`)
- `POLYMARKET_TOKEN_PRICE_USD` (default `1.0`)

## Egress IP watchdog for exchange whitelisting

The backend now tracks your outbound public IP so you can keep exchange whitelists in sync.

At startup, `server.py` prints:

- current public IPv4 and IPv6 (when available)
- whitelist-ready entries (`/32` for IPv4 and `/128` for IPv6)
- a warning if the public IP changed since the last run

For on-demand checks while troubleshooting, call:

- `GET /api/network/egress-ip`

The response includes:

- `current` and `previous` IPs
- per-family change flags in `changed`
- ready-to-paste whitelist entries in `whitelist_entries`
- a warning string when a change is detected
