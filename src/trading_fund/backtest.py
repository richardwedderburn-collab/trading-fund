from __future__ import annotations

import csv
import datetime as dt
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
from urllib import parse, request

from trading_fund.config import load_env_file
from trading_fund.consensus import ConsensusEngine, TradeSignal


ALPACA_BARS_URL = "https://data.alpaca.markets/v2/stocks/bars"
CANDIDATE_VOLUME_GATES = (250_000, 500_000, 750_000, 1_000_000)


class TrendAgent:
    def vote(self, signal: TradeSignal) -> int:
        close = float(signal.raw_data.get("close", 0))
        sma20 = float(signal.raw_data.get("sma20", 0))
        return 1 if close > sma20 > 0 else 0


class BreakoutAgent:
    def vote(self, signal: TradeSignal) -> int:
        close = float(signal.raw_data.get("close", 0))
        recent_high = float(signal.raw_data.get("recent_high_10", 0))
        return 1 if close >= recent_high > 0 else 0


class VolumeAgent:
    def vote(self, signal: TradeSignal) -> int:
        volume = float(signal.raw_data.get("volume", 0))
        avg_volume = float(signal.raw_data.get("average_volume_10d", 0))
        return 1 if volume >= (avg_volume * 1.2) and avg_volume > 0 else 0


class RegimeDetectionAgent:
    def vote(self, signal: TradeSignal) -> int:
        close = float(signal.raw_data.get("close", 0.0))
        sma20 = float(signal.raw_data.get("sma20", 0.0))
        trend_strength = float(signal.raw_data.get("trend_strength", 0.0))
        vol_ratio = float(signal.raw_data.get("volatility_ratio", 1.0))
        return 1 if close > sma20 > 0 and trend_strength > 0.01 and 0.6 <= vol_ratio <= 1.8 else 0


class VolatilityTargetingAgent:
    def vote(self, signal: TradeSignal) -> int:
        short_vol = float(signal.raw_data.get("short_volatility_10d", 0.0))
        long_vol = float(signal.raw_data.get("long_volatility_20d", 0.0))
        if short_vol <= 0.0:
            return 0
        if long_vol <= 0.0:
            return 1
        return 1 if short_vol <= (long_vol * 1.75) else 0

    def position_size_multiplier(self, signal: TradeSignal) -> float:
        short_vol = float(signal.raw_data.get("short_volatility_10d", 0.0))
        long_vol = float(signal.raw_data.get("long_volatility_20d", 0.0))
        if short_vol <= 0.0 or long_vol <= 0.0:
            return 0.75
        ratio = short_vol / long_vol
        if ratio >= 1.75:
            return 0.5
        if ratio >= 1.25:
            return 0.75
        return 1.0


class MeanReversionAgent:
    def vote(self, signal: TradeSignal) -> int:
        zscore = float(signal.raw_data.get("zscore_20d", 0.0))
        volatility_ratio = float(signal.raw_data.get("volatility_ratio", 1.0))
        trend_strength = float(signal.raw_data.get("trend_strength", 0.0))
        return 1 if -2.5 <= zscore <= -1.0 and volatility_ratio <= 1.5 and trend_strength >= -0.03 else 0


class MeanReversionRegimeAgent:
    def vote(self, signal: TradeSignal) -> int:
        regime_label = str(signal.raw_data.get("regime_label", ""))
        return 1 if regime_label in {"mean_revert", "compression"} else 0


@dataclass
class BacktestResult:
    symbols: List[str]
    start_date: str
    end_date: str
    trades: int
    win_rate: float
    total_pnl_usd: float
    avg_pnl_per_trade: float
    best_gateway_min_volume: int
    max_drawdown_usd: float
    sharpe_ratio: float
    max_loss_trade_usd: float
    gateway_sensitivity: List[Dict[str, Any]]
    per_symbol_gateway: List[Dict[str, Any]]
    trade_rows: List[Dict[str, Any]]
    walk_forward_enabled: bool
    walk_forward_train_years: int
    walk_forward_test_months: int
    walk_forward_folds: List[Dict[str, Any]]
    in_sample_trades: int
    in_sample_win_rate: float
    in_sample_total_pnl_usd: float
    in_sample_avg_pnl_per_trade: float
    oos_vs_insample_pnl_ratio: float
    degradation_threshold: float
    degradation_warning: bool
    degradation_message: str
    drift_score: float
    drift_warning: bool
    drift_message: str
    drift_monitor: List[Dict[str, Any]]


def _iso_day(value: dt.date) -> str:
    return value.isoformat() + "T00:00:00Z"


def _request_json(url: str, headers: Dict[str, str]) -> Dict[str, Any]:
    req = request.Request(url, headers=headers)
    with request.urlopen(req, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def fetch_alpaca_bars(
    symbols: Iterable[str],
    start_date: dt.date,
    end_date: dt.date,
    api_key: str,
    api_secret: str,
    timeframe: str = "1Day",
) -> Dict[str, List[Dict[str, Any]]]:
    symbols_csv = ",".join(sorted({s.strip().upper() for s in symbols if s.strip()}))
    params: Dict[str, str] = {
        "symbols": symbols_csv,
        "timeframe": timeframe,
        "start": _iso_day(start_date),
        "end": _iso_day(end_date),
        "limit": "10000",
        "adjustment": "raw",
        "feed": "iex",
    }
    headers = {
        "APCA-API-KEY-ID": api_key,
        "APCA-API-SECRET-KEY": api_secret,
    }

    bars_by_symbol: Dict[str, List[Dict[str, Any]]] = {
        symbol: [] for symbol in symbols_csv.split(",") if symbol
    }
    page_token: Optional[str] = None

    while True:
        query_params = dict(params)
        if page_token:
            query_params["page_token"] = page_token
        url = ALPACA_BARS_URL + "?" + parse.urlencode(query_params)
        payload = _request_json(url, headers=headers)

        for symbol, bars in (payload.get("bars") or {}).items():
            bars_by_symbol.setdefault(symbol, []).extend(bars)

        page_token = payload.get("next_page_token")
        if not page_token:
            break

    for symbol in list(bars_by_symbol.keys()):
        bars_by_symbol[symbol] = sorted(bars_by_symbol[symbol], key=lambda bar: bar.get("t", ""))

    return bars_by_symbol


def _mean(values: List[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


def _safe_ratio(numerator: float, denominator: float, default: float = 0.0) -> float:
    if abs(float(denominator)) <= 1e-12:
        return float(default)
    return float(numerator) / float(denominator)


def _pct_returns(values: List[float]) -> List[float]:
    returns: List[float] = []
    for prev, current in zip(values, values[1:]):
        if abs(prev) <= 1e-12:
            continue
        returns.append((current - prev) / prev)
    return returns


def _std(values: List[float]) -> float:
    if len(values) < 2:
        return 0.0
    avg = _mean(values)
    variance = sum((value - avg) ** 2 for value in values) / (len(values) - 1)
    return variance ** 0.5


def _realized_volatility(closes: List[float]) -> float:
    return _std(_pct_returns(closes))


def build_default_agents() -> List[Any]:
    return [
        TrendAgent(),
        BreakoutAgent(),
        VolumeAgent(),
        RegimeDetectionAgent(),
        VolatilityTargetingAgent(),
    ]


def build_mean_reversion_agents() -> List[Any]:
    return [
        MeanReversionAgent(),
        MeanReversionRegimeAgent(),
        VolumeAgent(),
        VolatilityTargetingAgent(),
    ]


def build_stock_signal(symbol: str, bars: List[Dict[str, Any]], idx: Optional[int] = None) -> Optional[TradeSignal]:
    if len(bars) < 22:
        return None

    signal_index = len(bars) - 1 if idx is None else int(idx)
    if signal_index < 20 or signal_index >= len(bars):
        return None

    closes = [float(item.get("c", 0.0)) for item in bars]
    volumes = [float(item.get("v", 0.0)) for item in bars]

    close = closes[signal_index]
    sma20 = _mean(closes[signal_index - 20 : signal_index])
    avg_volume_10d = _mean(volumes[signal_index - 10 : signal_index])
    recent_high_10 = max(closes[signal_index - 10 : signal_index])
    std20 = _std(closes[signal_index - 20 : signal_index])
    short_vol = _realized_volatility(closes[signal_index - 10 : signal_index + 1])
    long_vol = _realized_volatility(closes[signal_index - 20 : signal_index + 1])
    trend_strength = _safe_ratio(close - sma20, sma20, 0.0)
    volatility_ratio = _safe_ratio(short_vol, long_vol, 1.0)
    zscore_20d = _safe_ratio(close - sma20, std20, 0.0)

    if close > sma20 > 0 and 0.6 <= volatility_ratio <= 1.8:
        regime_label = "trend"
    elif volatility_ratio > 1.8:
        regime_label = "shock"
    elif zscore_20d <= -1.0:
        regime_label = "mean_revert"
    else:
        regime_label = "compression"

    return TradeSignal(
        asset=symbol,
        market_type="stock",
        direction="LONG",
        raw_data={
            "average_volume_10d": avg_volume_10d,
            "close": close,
            "volume": volumes[signal_index],
            "sma20": sma20,
            "recent_high_10": recent_high_10,
            "short_volatility_10d": short_vol,
            "long_volatility_20d": long_vol,
            "volatility_ratio": volatility_ratio,
            "trend_strength": trend_strength,
            "zscore_20d": zscore_20d,
            "stddev_20d": std20,
            "regime_label": regime_label,
        },
    )


def build_strategy_engines() -> List[tuple[str, ConsensusEngine]]:
    return [
        ("trend_following", ConsensusEngine(*build_default_agents())),
        (
            "mean_reversion",
            ConsensusEngine(
                *build_mean_reversion_agents(),
                full_position_threshold=2,
                half_position_threshold=1,
            ),
        ),
    ]


def evaluate_stock_signal(signal: TradeSignal, base_position_usd: float) -> Dict[str, Any] | str:
    best_decision: Dict[str, Any] | None = None
    best_pack = ""
    for pack_name, engine in build_strategy_engines():
        decision = engine.process_trade(signal, base_position_usd=base_position_usd)
        if isinstance(decision, str):
            continue
        if best_decision is None:
            best_decision = dict(decision)
            best_pack = pack_name
            continue
        current_allocated = float(decision.get("allocated_capital", 0.0))
        best_allocated = float(best_decision.get("allocated_capital", 0.0))
        current_score = int(decision.get("consensus_score", 0))
        best_score = int(best_decision.get("consensus_score", 0))
        if current_allocated > best_allocated or (
            abs(current_allocated - best_allocated) <= 1e-9 and current_score > best_score
        ):
            best_decision = dict(decision)
            best_pack = pack_name

    if best_decision is None:
        return "REJECTED_BY_GATES"

    best_decision["strategy_pack"] = best_pack
    return best_decision


def _build_drift_monitor(rows: List[Dict[str, Any]], window: int = 20) -> tuple[List[Dict[str, Any]], float, bool, str]:
    if len(rows) < max(5, window):
        return [], 0.0, False, "Insufficient trades for drift monitoring."

    monitor_rows: List[Dict[str, Any]] = []
    rolling_totals: List[float] = []
    rolling_win_rates: List[float] = []
    rolling_avg_pnls: List[float] = []

    for end_idx in range(window, len(rows) + 1):
        window_rows = rows[end_idx - window : end_idx]
        metrics = _aggregate_trade_metrics(window_rows)
        monitor_rows.append(
            {
                "window_end_trade": int(end_idx),
                "end_date": str(window_rows[-1].get("date", "")),
                "trades_in_window": int(metrics["trades"]),
                "window_total_pnl_usd": round(float(metrics["total_pnl_usd"]), 2),
                "window_win_rate": round(float(metrics["win_rate"]), 4),
                "window_avg_pnl_per_trade": round(float(metrics["avg_pnl_per_trade"]), 4),
                "window_max_drawdown_usd": round(float(metrics["max_drawdown_usd"]), 2),
            }
        )
        rolling_totals.append(float(metrics["total_pnl_usd"]))
        rolling_win_rates.append(float(metrics["win_rate"]))
        rolling_avg_pnls.append(float(metrics["avg_pnl_per_trade"]))

    latest_total = rolling_totals[-1]
    latest_win_rate = rolling_win_rates[-1]
    latest_avg_pnl = rolling_avg_pnls[-1]
    baseline_win_rate = _mean(rolling_win_rates[:-1]) if len(rolling_win_rates) > 1 else rolling_win_rates[-1]
    baseline_avg_pnl = _mean(rolling_avg_pnls[:-1]) if len(rolling_avg_pnls) > 1 else rolling_avg_pnls[-1]

    drift_hits = 0
    if latest_total < 0:
        drift_hits += 1
    if latest_win_rate < (baseline_win_rate * 0.75):
        drift_hits += 1
    if latest_avg_pnl < min(0.0, baseline_avg_pnl * 0.5):
        drift_hits += 1

    drift_score = round(drift_hits / 3.0, 4)
    drift_warning = drift_hits >= 2
    if drift_warning:
        drift_message = (
            f"Rolling drift warning: latest window total_pnl=${latest_total:,.2f}, "
            f"win_rate={latest_win_rate * 100:.2f}%, avg_pnl=${latest_avg_pnl:,.2f}."
        )
    else:
        drift_message = "Rolling drift monitor is within tolerance."

    return monitor_rows, drift_score, drift_warning, drift_message


def _max_drawdown_from_pnl(pnl_series: List[float]) -> float:
    equity = 0.0
    peak = 0.0
    max_drawdown = 0.0
    for pnl in pnl_series:
        equity += pnl
        peak = max(peak, equity)
        drawdown = peak - equity
        if drawdown > max_drawdown:
            max_drawdown = drawdown
    return max_drawdown


def _simulate_for_volume_threshold(
    bars_by_symbol: Dict[str, List[Dict[str, Any]]],
    min_volume_gate: int,
    base_position_usd: float,
    fold_id: Optional[int] = None,
) -> Dict[str, Any]:
    trades = 0
    wins = 0
    total_pnl = 0.0
    pnl_series: List[float] = []
    ret_series: List[float] = []
    trade_rows: List[Dict[str, Any]] = []

    for symbol, bars in bars_by_symbol.items():
        closes = [float(bar.get("c", 0.0)) for bar in bars]

        for idx in range(20, len(bars) - 1):
            signal = build_stock_signal(symbol, bars, idx=idx)
            if signal is None:
                continue

            close = closes[idx]
            next_close = closes[idx + 1]
            avg_volume_10d = float(signal.raw_data.get("average_volume_10d", 0.0))

            if avg_volume_10d < float(min_volume_gate):
                continue

            decision = evaluate_stock_signal(signal, base_position_usd=base_position_usd)
            if isinstance(decision, str):
                continue

            allocated = float(decision.get("allocated_capital", 0.0))
            if allocated <= 0:
                continue

            ret = (next_close - close) / close if close else 0.0
            pnl = allocated * ret
            trades += 1
            total_pnl += pnl
            pnl_series.append(pnl)
            ret_series.append(ret)
            if pnl > 0:
                wins += 1

            row = {
                "symbol": symbol,
                "date": str(bars[idx].get("t", "")),
                "entry": round(close, 6),
                "next_close": round(next_close, 6),
                "ret": round(ret, 8),
                "allocated_capital": round(allocated, 2),
                "pnl_usd": round(pnl, 6),
                "min_volume_gate": int(min_volume_gate),
                "avg_volume_10d": round(avg_volume_10d, 2),
                "votes": ",".join(str(v) for v in decision.get("votes", [])),
                "consensus_score": int(decision.get("consensus_score", 0)),
                "size_multiplier": round(float(decision.get("size_multiplier", 1.0)), 4),
                "strategy_pack": str(decision.get("strategy_pack", "")),
                "regime_label": str(signal.raw_data.get("regime_label", "")),
                "short_volatility_10d": round(float(signal.raw_data.get("short_volatility_10d", 0.0)), 8),
                "long_volatility_20d": round(float(signal.raw_data.get("long_volatility_20d", 0.0)), 8),
                "volatility_ratio": round(float(signal.raw_data.get("volatility_ratio", 0.0)), 6),
                "trend_strength": round(float(signal.raw_data.get("trend_strength", 0.0)), 6),
                "zscore_20d": round(float(signal.raw_data.get("zscore_20d", 0.0)), 6),
                "action": decision.get("action", ""),
            }
            if fold_id is not None:
                row["fold_id"] = int(fold_id)
            trade_rows.append(row)

    sharpe = 0.0
    rs = _std(ret_series)
    if rs > 0:
        sharpe = (_mean(ret_series) / rs) * (252 ** 0.5)

    return {
        "trades": int(trades),
        "wins": int(wins),
        "total_pnl_usd": float(total_pnl),
        "max_drawdown_usd": float(_max_drawdown_from_pnl(pnl_series)),
        "sharpe_ratio": float(sharpe),
        "max_loss_trade_usd": float(min(pnl_series) if pnl_series else 0.0),
        "trade_rows": trade_rows,
    }


def _clip_bars_by_date(
    bars_by_symbol: Dict[str, List[Dict[str, Any]]],
    start_date: dt.date,
    end_date: dt.date,
) -> Dict[str, List[Dict[str, Any]]]:
    clipped: Dict[str, List[Dict[str, Any]]] = {}
    for symbol, bars in bars_by_symbol.items():
        kept = []
        for bar in bars:
            raw_t = str(bar.get("t", ""))
            if len(raw_t) < 10:
                continue
            try:
                d = dt.date.fromisoformat(raw_t[:10])
            except ValueError:
                continue
            if start_date <= d <= end_date:
                kept.append(bar)
        if kept:
            clipped[symbol] = kept
    return clipped


def _compute_sensitivity(
    bars_by_symbol: Dict[str, List[Dict[str, Any]]],
    base_position_usd: float,
) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for gate in CANDIDATE_VOLUME_GATES:
        run = _simulate_for_volume_threshold(bars_by_symbol, gate, base_position_usd)
        trades = int(run["trades"])
        wins = int(run["wins"])
        win_rate = (wins / trades) if trades else 0.0
        avg_pnl = (run["total_pnl_usd"] / trades) if trades else 0.0
        out.append(
            {
                "min_volume_gate": int(gate),
                "trades": trades,
                "win_rate": round(win_rate, 4),
                "total_pnl_usd": round(float(run["total_pnl_usd"]), 2),
                "avg_pnl_per_trade": round(avg_pnl, 2),
            }
        )
    return out


def _best_gate_from_sensitivity(sensitivity: List[Dict[str, Any]]) -> int:
    best = max(
        sensitivity,
        key=lambda row: row["total_pnl_usd"] if row["trades"] > 0 else float("-inf"),
    )
    return int(best["min_volume_gate"])


def _mode_int(values: List[int], fallback: int) -> int:
    if not values:
        return int(fallback)
    counts: Dict[int, int] = {}
    for v in values:
        counts[v] = counts.get(v, 0) + 1
    return max(counts.items(), key=lambda item: item[1])[0]


def _aggregate_trade_metrics(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    pnls = [float(r.get("pnl_usd", 0.0)) for r in rows]
    rets = [float(r.get("ret", 0.0)) for r in rows]
    trades = len(rows)
    wins = sum(1 for pnl in pnls if pnl > 0)
    total = sum(pnls)
    win_rate = (wins / trades) if trades else 0.0
    avg_pnl = (total / trades) if trades else 0.0
    sharpe = 0.0
    rs = _std(rets)
    if rs > 0:
        sharpe = (_mean(rets) / rs) * (252 ** 0.5)
    return {
        "trades": int(trades),
        "win_rate": float(win_rate),
        "total_pnl_usd": float(total),
        "avg_pnl_per_trade": float(avg_pnl),
        "max_drawdown_usd": float(_max_drawdown_from_pnl(pnls)),
        "sharpe_ratio": float(sharpe),
        "max_loss_trade_usd": float(min(pnls) if pnls else 0.0),
    }


def _run_walk_forward(
    bars_by_symbol: Dict[str, List[Dict[str, Any]]],
    start_day: dt.date,
    end_day: dt.date,
    base_position_usd: float,
    train_years: int,
    test_months: int,
) -> Dict[str, Any]:
    train_days = max(365, int(train_years) * 365)
    test_days = max(30, int(test_months) * 30)

    cursor = start_day
    fold_id = 1
    folds: List[Dict[str, Any]] = []
    chosen_gates: List[int] = []
    all_rows: List[Dict[str, Any]] = []

    while True:
        train_start = cursor
        train_end = train_start + dt.timedelta(days=train_days - 1)
        test_start = train_end + dt.timedelta(days=1)
        test_end = min(end_day, test_start + dt.timedelta(days=test_days - 1))

        if train_end >= end_day or test_start > end_day:
            break

        train_bars = _clip_bars_by_date(bars_by_symbol, train_start, train_end)
        test_bars = _clip_bars_by_date(bars_by_symbol, test_start, test_end)
        if not train_bars or not test_bars:
            cursor = cursor + dt.timedelta(days=test_days)
            fold_id += 1
            continue

        train_sens = _compute_sensitivity(train_bars, base_position_usd)
        gate = _best_gate_from_sensitivity(train_sens)
        fold_run = _simulate_for_volume_threshold(test_bars, gate, base_position_usd, fold_id=fold_id)

        trades = int(fold_run["trades"])
        wins = int(fold_run["wins"])
        win_rate = (wins / trades) if trades else 0.0

        all_rows.extend(fold_run["trade_rows"])
        chosen_gates.append(gate)
        folds.append(
            {
                "fold_id": int(fold_id),
                "train_start": train_start.isoformat(),
                "train_end": train_end.isoformat(),
                "test_start": test_start.isoformat(),
                "test_end": test_end.isoformat(),
                "selected_min_volume_gate": int(gate),
                "trades": trades,
                "win_rate": round(win_rate, 4),
                "total_pnl_usd": round(float(fold_run["total_pnl_usd"]), 2),
            }
        )

        cursor = cursor + dt.timedelta(days=test_days)
        fold_id += 1

    metrics = _aggregate_trade_metrics(all_rows)
    return {
        "metrics": metrics,
        "best_gate": _mode_int(chosen_gates, CANDIDATE_VOLUME_GATES[0]),
        "trade_rows": all_rows,
        "folds": folds,
    }


def run_five_year_backtest(
    symbols: Iterable[str],
    env_path: Optional[Path | str] = None,
    end_date: Optional[dt.date] = None,
    base_position_usd: float = 1000.0,
    walk_forward: bool = False,
    walk_forward_train_years: int = 3,
    walk_forward_test_months: int = 6,
    degradation_threshold: float = 0.35,
) -> BacktestResult:
    values = load_env_file(env_path)
    api_key = values.get("ALPACA_API_KEY", "").strip()
    api_secret = values.get("ALPACA_API_SECRET", "").strip()
    if not api_key or not api_secret:
        raise ValueError("Missing ALPACA_API_KEY or ALPACA_API_SECRET in .env")

    end_day = end_date or dt.date.today()
    start_day = end_day - dt.timedelta(days=365 * 5)

    bars = fetch_alpaca_bars(
        symbols=symbols,
        start_date=start_day,
        end_date=end_day,
        api_key=api_key,
        api_secret=api_secret,
    )

    sensitivity = _compute_sensitivity(bars, base_position_usd)
    best_gate = _best_gate_from_sensitivity(sensitivity)
    base_run = _simulate_for_volume_threshold(bars, best_gate, base_position_usd)
    drift_monitor, drift_score, drift_warning, drift_message = _build_drift_monitor(base_run["trade_rows"])
    in_sample_trades = int(base_run["trades"])
    in_sample_win_rate = (int(base_run["wins"]) / in_sample_trades) if in_sample_trades else 0.0
    in_sample_avg_pnl = (float(base_run["total_pnl_usd"]) / in_sample_trades) if in_sample_trades else 0.0

    per_symbol_gateway: List[Dict[str, Any]] = []
    for symbol in sorted(bars.keys()):
        symbol_sens = _compute_sensitivity({symbol: bars[symbol]}, base_position_usd)
        best_gate = _best_gate_from_sensitivity(symbol_sens)
        best_row = next(row for row in symbol_sens if int(row["min_volume_gate"]) == best_gate)
        per_symbol_gateway.append(
            {
                "symbol": symbol,
                "min_volume_gate": int(best_row["min_volume_gate"]),
                "trades": int(best_row["trades"]),
                "win_rate": float(best_row["win_rate"]),
                "total_pnl_usd": float(best_row["total_pnl_usd"]),
            }
        )

    if walk_forward:
        wf = _run_walk_forward(
            bars_by_symbol=bars,
            start_day=start_day,
            end_day=end_day,
            base_position_usd=base_position_usd,
            train_years=walk_forward_train_years,
            test_months=walk_forward_test_months,
        )
        m = wf["metrics"]
        in_sample_total = float(base_run["total_pnl_usd"])
        oos_total = float(m["total_pnl_usd"])
        ratio = (oos_total / in_sample_total) if in_sample_total else 0.0
        warning = False
        warning_message = "Walk-forward performance is within allowed degradation threshold."
        if in_sample_total > 0:
            minimum_allowed = in_sample_total * (1.0 - float(degradation_threshold))
            warning = oos_total < minimum_allowed
            if warning:
                warning_message = (
                    f"Walk-forward PnL ${oos_total:,.2f} is below threshold vs in-sample ${in_sample_total:,.2f}."
                )

        return BacktestResult(
            symbols=sorted({s.upper() for s in symbols}),
            start_date=start_day.isoformat(),
            end_date=end_day.isoformat(),
            trades=int(m["trades"]),
            win_rate=round(float(m["win_rate"]), 4),
            total_pnl_usd=round(float(m["total_pnl_usd"]), 2),
            avg_pnl_per_trade=round(float(m["avg_pnl_per_trade"]), 2),
            best_gateway_min_volume=int(wf["best_gate"]),
            max_drawdown_usd=round(float(m["max_drawdown_usd"]), 2),
            sharpe_ratio=round(float(m["sharpe_ratio"]), 4),
            max_loss_trade_usd=round(float(m["max_loss_trade_usd"]), 2),
            gateway_sensitivity=sensitivity,
            per_symbol_gateway=per_symbol_gateway,
            trade_rows=wf["trade_rows"],
            walk_forward_enabled=True,
            walk_forward_train_years=int(walk_forward_train_years),
            walk_forward_test_months=int(walk_forward_test_months),
            walk_forward_folds=wf["folds"],
            in_sample_trades=in_sample_trades,
            in_sample_win_rate=round(in_sample_win_rate, 4),
            in_sample_total_pnl_usd=round(in_sample_total, 2),
            in_sample_avg_pnl_per_trade=round(in_sample_avg_pnl, 2),
            oos_vs_insample_pnl_ratio=round(ratio, 4),
            degradation_threshold=float(degradation_threshold),
            degradation_warning=warning,
            degradation_message=warning_message,
            drift_score=drift_score,
            drift_warning=drift_warning,
            drift_message=drift_message,
            drift_monitor=drift_monitor,
        )

    trades = int(base_run["trades"])
    win_rate = (int(base_run["wins"]) / trades) if trades else 0.0
    avg_pnl = (float(base_run["total_pnl_usd"]) / trades) if trades else 0.0

    return BacktestResult(
        symbols=sorted({s.upper() for s in symbols}),
        start_date=start_day.isoformat(),
        end_date=end_day.isoformat(),
        trades=trades,
        win_rate=round(win_rate, 4),
        total_pnl_usd=round(float(base_run["total_pnl_usd"]), 2),
        avg_pnl_per_trade=round(avg_pnl, 2),
        best_gateway_min_volume=int(best_gate),
        max_drawdown_usd=round(float(base_run["max_drawdown_usd"]), 2),
        sharpe_ratio=round(float(base_run["sharpe_ratio"]), 4),
        max_loss_trade_usd=round(float(base_run["max_loss_trade_usd"]), 2),
        gateway_sensitivity=sensitivity,
        per_symbol_gateway=per_symbol_gateway,
        trade_rows=base_run["trade_rows"],
        walk_forward_enabled=False,
        walk_forward_train_years=int(walk_forward_train_years),
        walk_forward_test_months=int(walk_forward_test_months),
        walk_forward_folds=[],
        in_sample_trades=in_sample_trades,
        in_sample_win_rate=round(in_sample_win_rate, 4),
        in_sample_total_pnl_usd=round(float(base_run["total_pnl_usd"]), 2),
        in_sample_avg_pnl_per_trade=round(in_sample_avg_pnl, 2),
        oos_vs_insample_pnl_ratio=1.0,
        degradation_threshold=float(degradation_threshold),
        degradation_warning=False,
        degradation_message="Walk-forward mode disabled; no out-of-sample degradation check.",
        drift_score=drift_score,
        drift_warning=drift_warning,
        drift_message=drift_message,
        drift_monitor=drift_monitor,
    )


def format_backtest_report(result: BacktestResult) -> str:
    lines = [
        "Backtest Summary",
        f"Symbols: {', '.join(result.symbols)}",
        f"Period: {result.start_date} to {result.end_date}",
        f"Trades: {result.trades}",
        f"Win rate: {result.win_rate * 100:.2f}%",
        f"Total PnL: ${result.total_pnl_usd:,.2f}",
        f"Average PnL/trade: ${result.avg_pnl_per_trade:,.2f}",
        f"Best stock gateway volume floor: {result.best_gateway_min_volume:,}",
        f"Max drawdown: ${result.max_drawdown_usd:,.2f}",
        f"Sharpe ratio (daily): {result.sharpe_ratio:.3f}",
        f"Worst trade: ${result.max_loss_trade_usd:,.2f}",
        "",
        f"Walk-forward mode: {'enabled' if result.walk_forward_enabled else 'disabled'}",
    ]
    if result.walk_forward_enabled:
        lines.append(f"Train window: {result.walk_forward_train_years} years")
        lines.append(f"Test window: {result.walk_forward_test_months} months")
        lines.append("")
        lines.append("In-sample vs walk-forward:")
        lines.append(
            f"- In-sample: trades={result.in_sample_trades}, win_rate={result.in_sample_win_rate * 100:.2f}%, "
            f"total_pnl=${result.in_sample_total_pnl_usd:,.2f}, avg_pnl=${result.in_sample_avg_pnl_per_trade:,.2f}"
        )
        lines.append(
            f"- Walk-forward: trades={result.trades}, win_rate={result.win_rate * 100:.2f}%, "
            f"total_pnl=${result.total_pnl_usd:,.2f}, avg_pnl=${result.avg_pnl_per_trade:,.2f}"
        )
        lines.append(
            f"- OOS/IS PnL ratio: {result.oos_vs_insample_pnl_ratio:.3f}"
        )
        lines.append(
            f"- Degradation threshold: {result.degradation_threshold * 100:.1f}%"
        )
        lines.append(
            f"- Degradation warning: {'YES' if result.degradation_warning else 'NO'}"
        )
        lines.append(f"- Note: {result.degradation_message}")
    lines.append(f"Drift score: {result.drift_score:.2f}")
    lines.append(f"Drift warning: {'YES' if result.drift_warning else 'NO'}")
    lines.append(f"Drift note: {result.drift_message}")

    lines.append("")
    lines.append("Gateway sensitivity:")
    for row in result.gateway_sensitivity:
        lines.append(
            "- "
            + f"min_volume={row['min_volume_gate']:,}, trades={row['trades']}, "
            + f"win_rate={row['win_rate'] * 100:.2f}%, total_pnl=${row['total_pnl_usd']:,.2f}"
        )

    lines.append("")
    lines.append("Per-symbol best gateway:")
    for row in result.per_symbol_gateway:
        lines.append(
            "- "
            + f"{row['symbol']}: min_volume={row['min_volume_gate']:,}, trades={row['trades']}, "
            + f"win_rate={row['win_rate'] * 100:.2f}%, total_pnl=${row['total_pnl_usd']:,.2f}"
        )

    if result.walk_forward_folds:
        lines.append("")
        lines.append("Walk-forward folds:")
        for fold in result.walk_forward_folds:
            lines.append(
                "- "
                + f"fold={fold['fold_id']}, gate={fold['selected_min_volume_gate']:,}, "
                + f"test={fold['test_start']}->{fold['test_end']}, trades={fold['trades']}, "
                + f"win_rate={fold['win_rate'] * 100:.2f}%, total_pnl=${fold['total_pnl_usd']:,.2f}"
            )

    return "\n".join(lines)


def export_backtest_csv(result: BacktestResult, output_dir: Path | str) -> Dict[str, str]:
    target = Path(output_dir)
    target.mkdir(parents=True, exist_ok=True)

    summary_path = target / "backtest_summary.csv"
    sensitivity_path = target / "gateway_sensitivity.csv"
    per_symbol_path = target / "per_symbol_gateway.csv"
    folds_path = target / "walk_forward_folds.csv"
    trades_path = target / "trades.csv"
    drift_path = target / "drift_monitor.csv"

    with summary_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "symbols",
                "start_date",
                "end_date",
                "trades",
                "win_rate",
                "total_pnl_usd",
                "avg_pnl_per_trade",
                "best_gateway_min_volume",
                "max_drawdown_usd",
                "sharpe_ratio",
                "max_loss_trade_usd",
                "walk_forward_enabled",
                "walk_forward_train_years",
                "walk_forward_test_months",
                "in_sample_trades",
                "in_sample_win_rate",
                "in_sample_total_pnl_usd",
                "in_sample_avg_pnl_per_trade",
                "oos_vs_insample_pnl_ratio",
                "degradation_threshold",
                "degradation_warning",
                "degradation_message",
                "drift_score",
                "drift_warning",
                "drift_message",
            ],
        )
        writer.writeheader()
        writer.writerow(
            {
                "symbols": ",".join(result.symbols),
                "start_date": result.start_date,
                "end_date": result.end_date,
                "trades": result.trades,
                "win_rate": result.win_rate,
                "total_pnl_usd": result.total_pnl_usd,
                "avg_pnl_per_trade": result.avg_pnl_per_trade,
                "best_gateway_min_volume": result.best_gateway_min_volume,
                "max_drawdown_usd": result.max_drawdown_usd,
                "sharpe_ratio": result.sharpe_ratio,
                "max_loss_trade_usd": result.max_loss_trade_usd,
                "walk_forward_enabled": result.walk_forward_enabled,
                "walk_forward_train_years": result.walk_forward_train_years,
                "walk_forward_test_months": result.walk_forward_test_months,
                "in_sample_trades": result.in_sample_trades,
                "in_sample_win_rate": result.in_sample_win_rate,
                "in_sample_total_pnl_usd": result.in_sample_total_pnl_usd,
                "in_sample_avg_pnl_per_trade": result.in_sample_avg_pnl_per_trade,
                "oos_vs_insample_pnl_ratio": result.oos_vs_insample_pnl_ratio,
                "degradation_threshold": result.degradation_threshold,
                "degradation_warning": result.degradation_warning,
                "degradation_message": result.degradation_message,
                "drift_score": result.drift_score,
                "drift_warning": result.drift_warning,
                "drift_message": result.drift_message,
            }
        )

    with sensitivity_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "min_volume_gate",
                "trades",
                "win_rate",
                "total_pnl_usd",
                "avg_pnl_per_trade",
            ],
        )
        writer.writeheader()
        writer.writerows(result.gateway_sensitivity)

    with per_symbol_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["symbol", "min_volume_gate", "trades", "win_rate", "total_pnl_usd"],
        )
        writer.writeheader()
        writer.writerows(result.per_symbol_gateway)

    with folds_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "fold_id",
                "train_start",
                "train_end",
                "test_start",
                "test_end",
                "selected_min_volume_gate",
                "trades",
                "win_rate",
                "total_pnl_usd",
            ],
        )
        writer.writeheader()
        writer.writerows(result.walk_forward_folds)

    with drift_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "window_end_trade",
                "end_date",
                "trades_in_window",
                "window_total_pnl_usd",
                "window_win_rate",
                "window_avg_pnl_per_trade",
                "window_max_drawdown_usd",
            ],
        )
        writer.writeheader()
        writer.writerows(result.drift_monitor)

    with trades_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "fold_id",
                "symbol",
                "date",
                "entry",
                "next_close",
                "ret",
                "allocated_capital",
                "pnl_usd",
                "min_volume_gate",
                "avg_volume_10d",
                "votes",
                "consensus_score",
                "size_multiplier",
                "strategy_pack",
                "regime_label",
                "short_volatility_10d",
                "long_volatility_20d",
                "volatility_ratio",
                "trend_strength",
                "zscore_20d",
                "action",
            ],
        )
        writer.writeheader()
        for row in result.trade_rows:
            writer.writerow({
                "fold_id": row.get("fold_id", ""),
                "symbol": row.get("symbol", ""),
                "date": row.get("date", ""),
                "entry": row.get("entry", ""),
                "next_close": row.get("next_close", ""),
                "ret": row.get("ret", ""),
                "allocated_capital": row.get("allocated_capital", ""),
                "pnl_usd": row.get("pnl_usd", ""),
                "min_volume_gate": row.get("min_volume_gate", ""),
                "avg_volume_10d": row.get("avg_volume_10d", ""),
                "votes": row.get("votes", ""),
                "consensus_score": row.get("consensus_score", ""),
                "size_multiplier": row.get("size_multiplier", ""),
                "strategy_pack": row.get("strategy_pack", ""),
                "regime_label": row.get("regime_label", ""),
                "short_volatility_10d": row.get("short_volatility_10d", ""),
                "long_volatility_20d": row.get("long_volatility_20d", ""),
                "volatility_ratio": row.get("volatility_ratio", ""),
                "trend_strength": row.get("trend_strength", ""),
                "zscore_20d": row.get("zscore_20d", ""),
                "action": row.get("action", ""),
            })

    return {
        "summary": str(summary_path),
        "gateway_sensitivity": str(sensitivity_path),
        "per_symbol_gateway": str(per_symbol_path),
        "walk_forward_folds": str(folds_path),
        "drift_monitor": str(drift_path),
        "trades": str(trades_path),
    }
