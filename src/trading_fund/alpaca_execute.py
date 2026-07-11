from __future__ import annotations

import json
import datetime as dt
import math
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional
from urllib import parse, request

from trading_fund.backtest import build_stock_signal, evaluate_stock_signal, build_strategy_engines
from trading_fund.config import load_env_file
from trading_fund.consensus import TradeSignal


ALPACA_DATA_BARS = "https://data.alpaca.markets/v2/stocks/bars"

SECTOR_MAP: Dict[str, str] = {
    "AAPL": "Technology",
    "MSFT": "Technology",
    "NVDA": "Technology",
    "AMD": "Technology",
    "GOOGL": "Communication Services",
    "META": "Communication Services",
    "AMZN": "Consumer Discretionary",
    "TSLA": "Consumer Discretionary",
    "SPY": "Diversified",
    "QQQ": "Diversified",
}

FACTOR_MAP: Dict[str, str] = {
    "AAPL": "Quality Growth",
    "MSFT": "Quality Growth",
    "NVDA": "High Momentum",
    "AMD": "High Momentum",
    "TSLA": "High Beta",
    "AMZN": "Quality Growth",
    "META": "Quality Growth",
    "GOOGL": "Quality Growth",
    "SPY": "Broad Market",
    "QQQ": "Growth Beta",
}


@dataclass
class OrderPlan:
    symbol: str
    votes: List[int]
    action: str
    notional_usd: float
    close: float
    size_multiplier: float = 1.0


def _request_json(method: str, url: str, headers: Dict[str, str], payload: Optional[Dict[str, Any]] = None) -> Any:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = request.Request(url=url, data=data, method=method.upper(), headers=headers)
    with request.urlopen(req, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def _api_headers(api_key: str, api_secret: str) -> Dict[str, str]:
    return {
        "APCA-API-KEY-ID": api_key,
        "APCA-API-SECRET-KEY": api_secret,
        "Content-Type": "application/json",
    }


def _mean(values: List[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


def _std(values: List[float]) -> float:
    if len(values) < 2:
        return 0.0
    avg = _mean(values)
    variance = sum((value - avg) ** 2 for value in values) / (len(values) - 1)
    return variance ** 0.5


def _return_series(bars: List[Dict[str, Any]], lookback: int = 20) -> List[float]:
    closes = [float(item.get("c", 0.0)) for item in bars][-1 * (lookback + 1) :]
    returns: List[float] = []
    for prev, current in zip(closes, closes[1:]):
        if abs(prev) <= 1e-12:
            continue
        returns.append((current - prev) / prev)
    return returns


def _correlation(a: List[float], b: List[float]) -> float:
    size = min(len(a), len(b))
    if size < 2:
        return 0.0
    x = a[-size:]
    y = b[-size:]
    std_x = _std(x)
    std_y = _std(y)
    if std_x <= 1e-12 or std_y <= 1e-12:
        return 0.0
    mean_x = _mean(x)
    mean_y = _mean(y)
    covariance = sum((vx - mean_x) * (vy - mean_y) for vx, vy in zip(x, y)) / (size - 1)
    return covariance / (std_x * std_y)


def _max_peer_correlation(
    symbol: str,
    peer_symbols: Iterable[str],
    bars_by_symbol: Dict[str, List[Dict[str, Any]]],
    lookback: int = 20,
) -> tuple[float, str]:
    symbol_returns = _return_series(bars_by_symbol.get(symbol, []), lookback=lookback)
    max_corr = 0.0
    max_symbol = ""
    for peer in peer_symbols:
        peer_returns = _return_series(bars_by_symbol.get(peer, []), lookback=lookback)
        corr = abs(_correlation(symbol_returns, peer_returns))
        if corr > max_corr:
            max_corr = corr
            max_symbol = peer
    return max_corr, max_symbol


def _fetch_symbol_bars(symbols: Iterable[str], api_key: str, api_secret: str) -> Dict[str, List[Dict[str, Any]]]:
    tickers = sorted({s.strip().upper() for s in symbols if s.strip()})
    if not tickers:
        return {}
    end_day = dt.date.today()
    start_day = end_day - dt.timedelta(days=120)
    bars: Dict[str, List[Dict[str, Any]]] = {}

    for ticker in tickers:
        params = {
            "symbols": ticker,
            "timeframe": "1Day",
            "start": start_day.isoformat() + "T00:00:00Z",
            "end": end_day.isoformat() + "T23:59:59Z",
            "limit": "30",
            "adjustment": "raw",
            "feed": "iex",
        }
        url = ALPACA_DATA_BARS + "?" + parse.urlencode(params)
        try:
            payload = _request_json("GET", url, _api_headers(api_key, api_secret))
            series = (payload.get("bars") or {}).get(ticker, [])
            bars[ticker] = sorted(series, key=lambda bar: bar.get("t", ""))
        except Exception:
            bars[ticker] = []

    return bars


def _build_signal(symbol: str, bars: List[Dict[str, Any]]) -> Optional[TradeSignal]:
    return build_stock_signal(symbol, bars)


def _fetch_account(base_url: str, api_key: str, api_secret: str) -> Dict[str, Any]:
    url = f"{base_url.rstrip('/')}/v2/account"
    return _request_json("GET", url, _api_headers(api_key, api_secret))


def _fetch_positions(base_url: str, api_key: str, api_secret: str) -> List[Dict[str, Any]]:
    url = f"{base_url.rstrip('/')}/v2/positions"
    try:
        return _request_json("GET", url, _api_headers(api_key, api_secret))
    except Exception:
        return []


def _fetch_open_orders(base_url: str, api_key: str, api_secret: str) -> List[Dict[str, Any]]:
    url = f"{base_url.rstrip('/')}/v2/orders?status=open&direction=desc&limit=500"
    try:
        return _request_json("GET", url, _api_headers(api_key, api_secret))
    except Exception:
        return []


def _has_open_trailing_stop(open_orders: List[Dict[str, Any]], symbol: str, side: str) -> bool:
    symbol_upper = symbol.upper()
    for order in open_orders:
        if str(order.get("symbol", "")).upper() != symbol_upper:
            continue
        if str(order.get("side", "")).lower() != side.lower():
            continue
        if str(order.get("type", "")).lower() == "trailing_stop":
            return True
    return False


def _trail_percent_value(trailing_stop_pct: float) -> str:
    return str(round(float(trailing_stop_pct) * 100.0, 4))


def _is_fractional_qty(qty: float) -> bool:
    return abs(qty - round(qty)) > 1e-6


def _place_trailing_stop(
    orders_url: str,
    headers: Dict[str, str],
    symbol: str,
    side: str,
    qty: float,
    trailing_stop_pct: float,
) -> Dict[str, Any]:
    normalized_qty = round(max(0.0, qty), 6)
    payload = {
        "symbol": symbol,
        "side": side,
        "type": "trailing_stop",
        "qty": str(normalized_qty),
        "time_in_force": "day" if _is_fractional_qty(normalized_qty) else "gtc",
        "trail_percent": _trail_percent_value(trailing_stop_pct),
    }
    return _request_json("POST", orders_url, headers, payload)


def _place_trailing_stop_with_fallback(
    orders_url: str,
    headers: Dict[str, str],
    symbol: str,
    side: str,
    qty: float,
    trailing_stop_pct: float,
) -> Dict[str, Any]:
    normalized_qty = round(max(0.0, qty), 6)
    try:
        result = _place_trailing_stop(
            orders_url=orders_url,
            headers=headers,
            symbol=symbol,
            side=side,
            qty=normalized_qty,
            trailing_stop_pct=trailing_stop_pct,
        )
        return {"result": result, "qty_used": normalized_qty, "fallback_used": False}
    except Exception as exc:
        # Some brokers reject trailing stops on fractional quantities. Retry with whole shares.
        if _is_fractional_qty(normalized_qty) and normalized_qty >= 1.0:
            fallback_qty = float(math.floor(normalized_qty))
            if fallback_qty > 0.0:
                try:
                    result = _place_trailing_stop(
                        orders_url=orders_url,
                        headers=headers,
                        symbol=symbol,
                        side=side,
                        qty=fallback_qty,
                        trailing_stop_pct=trailing_stop_pct,
                    )
                    return {"result": result, "qty_used": fallback_qty, "fallback_used": True}
                except Exception as fallback_exc:
                    raise RuntimeError(
                        f"{exc}; fallback_qty={fallback_qty} failed: {fallback_exc}"
                    ) from fallback_exc
        raise


def _place_market_cleanup_order(
    orders_url: str,
    headers: Dict[str, str],
    symbol: str,
    side: str,
    qty: float,
) -> Dict[str, Any]:
    payload = {
        "symbol": symbol,
        "side": side,
        "type": "market",
        "qty": str(round(max(0.0, qty), 6)),
        "time_in_force": "day",
    }
    return _request_json("POST", orders_url, headers, payload)


def _build_order_candidates(
    symbols: Iterable[str],
    bars_by_symbol: Dict[str, List[Dict[str, Any]]],
    held_symbols: set[str],
    per_position_budget: float,
) -> List[OrderPlan]:
    scored: List[tuple[int, float, OrderPlan]] = []

    for symbol in symbols:
        ticker = symbol.strip().upper()
        if not ticker or ticker in held_symbols:
            continue
        signal = _build_signal(ticker, bars_by_symbol.get(ticker, []))
        if signal is None:
            continue
        decision = evaluate_stock_signal(signal, base_position_usd=per_position_budget)
        if isinstance(decision, str):
            continue
        notional = float(decision.get("allocated_capital", 0.0))
        if notional <= 0:
            continue
        votes = [int(v) for v in decision.get("votes", [])]
        vote_score = sum(votes)
        momentum = float(signal.raw_data.get("close", 0.0)) - float(signal.raw_data.get("sma20", 0.0))
        plan = OrderPlan(
            symbol=ticker,
            votes=votes,
            action=str(decision.get("action", "")),
            notional_usd=round(notional, 2),
            close=float(signal.raw_data.get("close", 0.0)),
            size_multiplier=float(decision.get("size_multiplier", 1.0)),
        )
        scored.append((vote_score, momentum, plan))

    scored.sort(key=lambda row: (row[0], row[1]), reverse=True)
    return [row[2] for row in scored]


def _classify_sector(symbol: str) -> str:
    return SECTOR_MAP.get(symbol.upper(), "Other")


def _classify_factor(symbol: str) -> str:
    return FACTOR_MAP.get(symbol.upper(), "Core")


def _build_strategy_pack_comparison(signal: TradeSignal, base_position_usd: float) -> Dict[str, Any]:
    packs: Dict[str, Dict[str, Any]] = {}
    for pack_name, engine in build_strategy_engines():
        decision = engine.process_trade(signal, base_position_usd=base_position_usd)
        if isinstance(decision, str):
            packs[pack_name] = {
                "rejected": True,
                "reason": decision,
                "allocated_capital": 0.0,
                "consensus_score": 0,
                "size_multiplier": 0.0,
                "votes": [],
                "action": "hold",
            }
            continue
        packs[pack_name] = {
            "rejected": False,
            "allocated_capital": round(float(decision.get("allocated_capital", 0.0)), 2),
            "consensus_score": int(decision.get("consensus_score", 0)),
            "size_multiplier": round(float(decision.get("size_multiplier", 0.0)), 4),
            "votes": [int(v) for v in decision.get("votes", [])],
            "action": str(decision.get("action", "hold")),
        }

    trend_alloc = float(packs.get("trend_following", {}).get("allocated_capital", 0.0))
    mean_alloc = float(packs.get("mean_reversion", {}).get("allocated_capital", 0.0))
    if trend_alloc >= mean_alloc:
        recommended_pack = "trend_following"
        rationale = "Higher allocated capital under trend-following pack."
    else:
        recommended_pack = "mean_reversion"
        rationale = "Higher allocated capital under mean-reversion pack."

    return {
        "symbol": signal.asset,
        "regime_label": str(signal.raw_data.get("regime_label", "")),
        "trend_strength": round(float(signal.raw_data.get("trend_strength", 0.0)), 6),
        "volatility_ratio": round(float(signal.raw_data.get("volatility_ratio", 0.0)), 6),
        "trend_following": packs.get("trend_following", {}),
        "mean_reversion": packs.get("mean_reversion", {}),
        "recommended_pack": recommended_pack,
        "rationale": rationale,
    }


def execute_alpaca_strategy(
    symbols: Iterable[str],
    env_path: Optional[str] = None,
    max_new_positions: int = 0,
    max_risk_pct: float = 0.05,
    trailing_stop_pct: float = 0.03,
    apply_trailing_to_existing: bool = True,
    enable_dust_cleanup: bool = True,
    dust_cleanup_min_qty: float = 0.0001,
    correlation_soft_limit: float = 0.75,
    correlation_hard_limit: float = 0.9,
    exposure_soft_multiplier: float = 0.5,
    sector_soft_limit: float = 1.0,
    factor_soft_limit: float = 1.0,
    group_soft_multiplier: float = 0.65,
    execute_rebalance_sells: bool = False,
    execute_orders: bool = False,
) -> Dict[str, Any]:
    values = load_env_file(env_path)
    api_key = values.get("ALPACA_API_KEY", "").strip()
    api_secret = values.get("ALPACA_API_SECRET", "").strip()
    if not api_key or not api_secret:
        raise ValueError("Missing ALPACA_API_KEY or ALPACA_API_SECRET in .env")

    base_url = values.get("ALPACA_API_BASE_URL", "https://paper-api.alpaca.markets").strip()
    account = _fetch_account(base_url, api_key, api_secret)
    positions = _fetch_positions(base_url, api_key, api_secret)
    open_orders = _fetch_open_orders(base_url, api_key, api_secret)
    held_symbols = {str(item.get("symbol", "")).upper() for item in positions}
    correlation_soft_limit = max(0.0, min(float(correlation_soft_limit), 0.999))
    correlation_hard_limit = max(correlation_soft_limit + 0.01, min(float(correlation_hard_limit), 0.9999))
    exposure_soft_multiplier = max(0.1, min(float(exposure_soft_multiplier), 1.0))
    sector_soft_limit = max(0.0, min(float(sector_soft_limit), 1.0))
    factor_soft_limit = max(0.0, min(float(factor_soft_limit), 1.0))
    group_soft_multiplier = max(0.1, min(float(group_soft_multiplier), 1.0))

    equity = float(account.get("equity", 0.0) or 0.0)
    risk_budget = round(max(0.0, equity * float(max_risk_pct)), 2)
    requested_slots = max(0, int(max_new_positions))
    auto_slots = 0
    if requested_slots > 0:
        slots = requested_slots
    else:
        candidate_pool = [s.strip().upper() for s in symbols if s and s.strip() and s.strip().upper() not in held_symbols]
        auto_slots = max(1, len(candidate_pool))
        slots = auto_slots
    per_position_budget = (risk_budget / slots) if slots > 0 else 0.0

    universe_symbols = sorted({s.strip().upper() for s in symbols if str(s).strip()} | held_symbols)
    bars = _fetch_symbol_bars(universe_symbols, api_key, api_secret)
    candidates = _build_order_candidates(symbols, bars, held_symbols, per_position_budget)

    pack_comparison: List[Dict[str, Any]] = []
    for symbol in sorted({s.strip().upper() for s in symbols if s and s.strip()}):
        signal = _build_signal(symbol, bars.get(symbol, []))
        if signal is None:
            continue
        pack_comparison.append(_build_strategy_pack_comparison(signal, base_position_usd=per_position_budget))

    base_sector_notional: Dict[str, float] = {}
    base_factor_notional: Dict[str, float] = {}
    for position in positions:
        symbol = str(position.get("symbol", "")).upper()
        qty = float(position.get("qty", 0.0) or 0.0)
        market_value = abs(float(position.get("market_value", 0.0) or 0.0))
        if market_value <= 0.0:
            symbol_bars = bars.get(symbol, [])
            last_bar = symbol_bars[-1] if symbol_bars else {}
            close = float((last_bar or {}).get("c", 0.0) or 0.0)
            market_value = abs(qty) * close
        if not symbol or market_value <= 0.0:
            continue
        sector = _classify_sector(symbol)
        factor = _classify_factor(symbol)
        base_sector_notional[sector] = base_sector_notional.get(sector, 0.0) + market_value
        base_factor_notional[factor] = base_factor_notional.get(factor, 0.0) + market_value

    selected_sector_notional = dict(base_sector_notional)
    selected_factor_notional = dict(base_factor_notional)

    selected: List[OrderPlan] = []
    spent = 0.0
    exposure_skips: List[Dict[str, Any]] = []
    exposure_adjustments: List[Dict[str, Any]] = []
    group_exposure_adjustments: List[Dict[str, Any]] = []
    for plan in candidates:
        if len(selected) >= slots:
            break
        remaining = risk_budget - spent
        if remaining <= 1.0:
            break

        peer_symbols = held_symbols | {item.symbol for item in selected}
        max_corr, peer_symbol = _max_peer_correlation(plan.symbol, peer_symbols, bars)
        if peer_symbol and max_corr >= correlation_hard_limit:
            exposure_skips.append(
                {
                    "symbol": plan.symbol,
                    "peer_symbol": peer_symbol,
                    "correlation": round(max_corr, 4),
                    "reason": "correlation_exceeds_hard_limit",
                }
            )
            continue

        exposure_multiplier = exposure_soft_multiplier if peer_symbol and max_corr >= correlation_soft_limit else 1.0
        if exposure_multiplier < 1.0:
            exposure_adjustments.append(
                {
                    "symbol": plan.symbol,
                    "peer_symbol": peer_symbol,
                    "correlation": round(max_corr, 4),
                    "size_multiplier": exposure_multiplier,
                }
            )

        sector = _classify_sector(plan.symbol)
        factor = _classify_factor(plan.symbol)
        projected_notional = plan.notional_usd
        projected_sector_ratio = (selected_sector_notional.get(sector, 0.0) + projected_notional) / max(risk_budget, 1.0)
        projected_factor_ratio = (selected_factor_notional.get(factor, 0.0) + projected_notional) / max(risk_budget, 1.0)
        group_multiplier = 1.0
        if projected_sector_ratio > sector_soft_limit:
            group_multiplier = min(group_multiplier, group_soft_multiplier)
            group_exposure_adjustments.append(
                {
                    "symbol": plan.symbol,
                    "group_type": "sector",
                    "group_name": sector,
                    "projected_ratio": round(projected_sector_ratio, 4),
                    "limit": round(sector_soft_limit, 4),
                    "size_multiplier": group_soft_multiplier,
                }
            )
        if projected_factor_ratio > factor_soft_limit:
            group_multiplier = min(group_multiplier, group_soft_multiplier)
            group_exposure_adjustments.append(
                {
                    "symbol": plan.symbol,
                    "group_type": "factor",
                    "group_name": factor,
                    "projected_ratio": round(projected_factor_ratio, 4),
                    "limit": round(factor_soft_limit, 4),
                    "size_multiplier": group_soft_multiplier,
                }
            )

        exposure_multiplier = min(exposure_multiplier, group_multiplier)

        capped_notional = min(plan.notional_usd * exposure_multiplier, remaining)
        if capped_notional < 1.0:
            continue
        selected.append(
            OrderPlan(
                symbol=plan.symbol,
                votes=plan.votes,
                action=plan.action,
                notional_usd=round(capped_notional, 2),
                close=plan.close,
                size_multiplier=plan.size_multiplier * exposure_multiplier,
            )
        )
        spent += capped_notional
        selected_sector_notional[sector] = selected_sector_notional.get(sector, 0.0) + capped_notional
        selected_factor_notional[factor] = selected_factor_notional.get(factor, 0.0) + capped_notional

    sector_exposure_snapshot = [
        {
            "group": group,
            "notional_usd": round(value, 2),
            "risk_budget_ratio": round(value / max(risk_budget, 1.0), 4),
        }
        for group, value in sorted(selected_sector_notional.items(), key=lambda item: item[1], reverse=True)
    ]
    factor_exposure_snapshot = [
        {
            "group": group,
            "notional_usd": round(value, 2),
            "risk_budget_ratio": round(value / max(risk_budget, 1.0), 4),
        }
        for group, value in sorted(selected_factor_notional.items(), key=lambda item: item[1], reverse=True)
    ]

    rebalance_sell_plan: List[Dict[str, Any]] = []
    eval_position_budget = per_position_budget if per_position_budget > 0 else max(100.0, risk_budget * 0.2)
    for position in positions:
        symbol = str(position.get("symbol", "")).upper()
        qty = float(position.get("qty", 0.0) or 0.0)
        if not symbol or abs(qty) <= 0.0:
            continue
        signal = _build_signal(symbol, bars.get(symbol, []))
        if signal is None:
            continue

        decision = evaluate_stock_signal(signal, base_position_usd=eval_position_budget)
        trend_strength = float(signal.raw_data.get("trend_strength", 0.0))
        regime_label = str(signal.raw_data.get("regime_label", ""))
        weak_trend_exit = trend_strength < -0.01 and regime_label in {"mean_revert", "shock"}
        should_exit = (
            isinstance(decision, str)
            or float(decision.get("allocated_capital", 0.0)) <= 0.0
            or weak_trend_exit
        )
        if not should_exit:
            continue

        side = "sell" if qty > 0 else "buy"
        rebalance_sell_plan.append(
            {
                "symbol": symbol,
                "qty": round(abs(qty), 6),
                "side": side,
                "reason": "strategy_exit_signal",
                "regime_label": str(signal.raw_data.get("regime_label", "")),
                "trend_strength": round(float(signal.raw_data.get("trend_strength", 0.0)), 6),
                "volatility_ratio": round(float(signal.raw_data.get("volatility_ratio", 0.0)), 6),
            }
        )

    existing_trailing_stop_plan: List[Dict[str, Any]] = []
    for position in positions:
        symbol = str(position.get("symbol", "")).upper()
        qty = float(position.get("qty", 0.0) or 0.0)
        if not symbol or abs(qty) <= 0.0:
            continue
        stop_side = "sell" if qty > 0 else "buy"
        existing_trailing_stop_plan.append(
            {
                "symbol": symbol,
                "qty": round(abs(qty), 6),
                "side": stop_side,
                "already_open": _has_open_trailing_stop(open_orders, symbol, stop_side),
            }
        )

    placed_orders: List[Dict[str, Any]] = []
    placed_trailing_stops: List[Dict[str, Any]] = []
    dust_cleanup_orders: List[Dict[str, Any]] = []
    placed_rebalance_sells: List[Dict[str, Any]] = []
    if execute_orders:
        orders_url = f"{base_url.rstrip('/')}/v2/orders"
        headers = _api_headers(api_key, api_secret)

        if execute_rebalance_sells:
            for plan in rebalance_sell_plan:
                try:
                    placed = _place_market_cleanup_order(
                        orders_url=orders_url,
                        headers=headers,
                        symbol=str(plan["symbol"]),
                        side=str(plan["side"]),
                        qty=float(plan["qty"]),
                    )
                    placed_rebalance_sells.append(
                        {
                            "symbol": plan["symbol"],
                            "qty": plan["qty"],
                            "side": plan["side"],
                            "status": placed.get("status", "submitted"),
                            "id": placed.get("id", ""),
                        }
                    )
                except Exception as exc:
                    placed_rebalance_sells.append(
                        {
                            "symbol": plan["symbol"],
                            "qty": plan["qty"],
                            "side": plan["side"],
                            "status": "rejected",
                            "error": str(exc),
                        }
                    )

        if float(trailing_stop_pct) > 0.0 and apply_trailing_to_existing:
            for plan in existing_trailing_stop_plan:
                if plan["already_open"]:
                    continue
                try:
                    placed = _place_trailing_stop_with_fallback(
                        orders_url=orders_url,
                        headers=headers,
                        symbol=str(plan["symbol"]),
                        side=str(plan["side"]),
                        qty=float(plan["qty"]),
                        trailing_stop_pct=trailing_stop_pct,
                    )
                    result = placed["result"]
                    placed_trailing_stops.append(
                        {
                            "symbol": plan["symbol"],
                            "qty": placed["qty_used"],
                            "side": plan["side"],
                            "scope": "existing",
                            "fallback_used": bool(placed["fallback_used"]),
                            "status": result.get("status", "submitted"),
                            "id": result.get("id", ""),
                        }
                    )
                    residual_qty = round(max(0.0, float(plan["qty"]) - float(placed["qty_used"])), 6)
                    if enable_dust_cleanup and residual_qty >= float(dust_cleanup_min_qty):
                        try:
                            cleanup = _place_market_cleanup_order(
                                orders_url=orders_url,
                                headers=headers,
                                symbol=str(plan["symbol"]),
                                side=str(plan["side"]),
                                qty=residual_qty,
                            )
                            dust_cleanup_orders.append(
                                {
                                    "symbol": plan["symbol"],
                                    "qty": residual_qty,
                                    "side": plan["side"],
                                    "scope": "existing",
                                    "status": cleanup.get("status", "submitted"),
                                    "id": cleanup.get("id", ""),
                                }
                            )
                        except Exception as exc:
                            dust_cleanup_orders.append(
                                {
                                    "symbol": plan["symbol"],
                                    "qty": residual_qty,
                                    "side": plan["side"],
                                    "scope": "existing",
                                    "status": "rejected",
                                    "error": str(exc),
                                }
                            )
                except Exception as exc:
                    placed_trailing_stops.append(
                        {
                            "symbol": plan["symbol"],
                            "qty": plan["qty"],
                            "side": plan["side"],
                            "scope": "existing",
                            "status": "rejected",
                            "error": str(exc),
                        }
                    )

        for plan in selected:
            payload: Dict[str, Any] = {
                "symbol": plan.symbol,
                "side": "buy",
                "type": "market",
                "time_in_force": "day",
                "notional": str(round(plan.notional_usd, 2)),
            }

            result = _request_json("POST", orders_url, headers, payload)
            placed_orders.append(
                {
                    "symbol": plan.symbol,
                    "notional_usd": plan.notional_usd,
                    "status": result.get("status", "submitted"),
                    "id": result.get("id", ""),
                }
            )

            if float(trailing_stop_pct) > 0.0:
                estimated_qty = max(0.0, plan.notional_usd / max(plan.close, 0.01))
                if estimated_qty > 0.0:
                    try:
                        placed = _place_trailing_stop_with_fallback(
                            orders_url=orders_url,
                            headers=headers,
                            symbol=plan.symbol,
                            side="sell",
                            qty=estimated_qty,
                            trailing_stop_pct=trailing_stop_pct,
                        )
                        trailing = placed["result"]
                        placed_trailing_stops.append(
                            {
                                "symbol": plan.symbol,
                                "qty": placed["qty_used"],
                                "side": "sell",
                                "scope": "new",
                                "fallback_used": bool(placed["fallback_used"]),
                                "status": trailing.get("status", "submitted"),
                                "id": trailing.get("id", ""),
                            }
                        )
                        residual_qty = round(max(0.0, estimated_qty - float(placed["qty_used"])), 6)
                        if enable_dust_cleanup and residual_qty >= float(dust_cleanup_min_qty):
                            try:
                                cleanup = _place_market_cleanup_order(
                                    orders_url=orders_url,
                                    headers=headers,
                                    symbol=plan.symbol,
                                    side="sell",
                                    qty=residual_qty,
                                )
                                dust_cleanup_orders.append(
                                    {
                                        "symbol": plan.symbol,
                                        "qty": residual_qty,
                                        "side": "sell",
                                        "scope": "new",
                                        "status": cleanup.get("status", "submitted"),
                                        "id": cleanup.get("id", ""),
                                    }
                                )
                            except Exception as exc:
                                dust_cleanup_orders.append(
                                    {
                                        "symbol": plan.symbol,
                                        "qty": residual_qty,
                                        "side": "sell",
                                        "scope": "new",
                                        "status": "rejected",
                                        "error": str(exc),
                                    }
                                )
                    except Exception as exc:
                        placed_trailing_stops.append(
                            {
                                "symbol": plan.symbol,
                                "qty": round(estimated_qty, 6),
                                "side": "sell",
                                "scope": "new",
                                "status": "rejected",
                                "error": str(exc),
                            }
                        )

    return {
        "base_url": base_url,
        "mode": "execute" if execute_orders else "dry_run",
        "equity": equity,
        "max_risk_pct": float(max_risk_pct),
        "trailing_stop_pct": float(trailing_stop_pct),
        "apply_trailing_to_existing": bool(apply_trailing_to_existing),
        "enable_dust_cleanup": bool(enable_dust_cleanup),
        "dust_cleanup_min_qty": float(dust_cleanup_min_qty),
        "correlation_soft_limit": correlation_soft_limit,
        "correlation_hard_limit": correlation_hard_limit,
        "exposure_soft_multiplier": exposure_soft_multiplier,
        "sector_soft_limit": sector_soft_limit,
        "factor_soft_limit": factor_soft_limit,
        "group_soft_multiplier": group_soft_multiplier,
        "execute_rebalance_sells": bool(execute_rebalance_sells),
        "risk_budget_usd": risk_budget,
        "max_new_positions": requested_slots,
        "auto_slots": auto_slots,
        "effective_new_position_slots": slots,
        "existing_positions": sorted(held_symbols),
        "rebalance_sell_plan": rebalance_sell_plan,
        "existing_trailing_stop_plan": existing_trailing_stop_plan,
        "candidate_count": len(candidates),
        "selected_orders": [
            {
                "symbol": plan.symbol,
                "votes": plan.votes,
                "action": plan.action,
                "notional_usd": plan.notional_usd,
                "close": plan.close,
                "size_multiplier": round(plan.size_multiplier, 4),
            }
            for plan in selected
        ],
        "exposure_adjustments": exposure_adjustments,
        "group_exposure_adjustments": group_exposure_adjustments,
        "sector_exposure_snapshot": sector_exposure_snapshot,
        "factor_exposure_snapshot": factor_exposure_snapshot,
        "per_symbol_pack_comparison": pack_comparison,
        "skipped_by_exposure": exposure_skips,
        "placed_orders": placed_orders,
        "placed_rebalance_sells": placed_rebalance_sells,
        "placed_trailing_stops": placed_trailing_stops,
        "dust_cleanup_orders": dust_cleanup_orders,
        "spent_usd": round(spent, 2),
        "remaining_budget_usd": round(risk_budget - spent, 2),
    }