from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from trading_fund.alpaca_execute import execute_alpaca_strategy

DEFAULT_STATE: Dict[str, Any] = {
    "enabled": False,
    "mode": "dry_run",
    "interval_seconds": 300,
    "symbols": ["AAPL", "MSFT", "NVDA", "TSLA", "AMD", "AMZN", "META", "GOOGL"],
    "max_risk_pct": 0.05,
    "max_new_positions": 0,
    "corr_soft_limit": 0.75,
    "corr_hard_limit": 0.90,
    "exposure_soft_multiplier": 0.5,
    "last_run_at": "",
    "last_reason": "",
    "last_mode": "",
    "last_result": {},
    "last_error": "",
    "run_count": 0,
}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_iso(value: str) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return None


def _normalize_symbols(raw: Any) -> list[str]:
    if isinstance(raw, str):
        source = raw.split(",")
    elif isinstance(raw, list):
        source = raw
    else:
        source = []
    symbols = sorted({str(item).strip().upper() for item in source if str(item).strip()})
    return symbols or list(DEFAULT_STATE["symbols"])


def load_state(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return dict(DEFAULT_STATE)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        state = dict(DEFAULT_STATE)
        state.update(payload)
        state["symbols"] = _normalize_symbols(state.get("symbols", []))
        state["enabled"] = bool(state.get("enabled", False))
        state["mode"] = "live" if str(state.get("mode", "dry_run")).lower() == "live" else "dry_run"
        state["interval_seconds"] = max(30, int(state.get("interval_seconds", 300)))
        return state
    except Exception:
        return dict(DEFAULT_STATE)


def save_state(path: Path, state: Dict[str, Any]) -> None:
    path.write_text(json.dumps(state, indent=2), encoding="utf-8")


def update_settings(path: Path, updates: Dict[str, Any]) -> Dict[str, Any]:
    state = load_state(path)
    for key, value in updates.items():
        if key == "symbols":
            state["symbols"] = _normalize_symbols(value)
        elif key == "mode":
            state["mode"] = "live" if str(value).lower() == "live" else "dry_run"
        elif key == "enabled":
            state["enabled"] = bool(value)
        elif key == "interval_seconds":
            state["interval_seconds"] = max(30, int(value))
        elif key in {"max_risk_pct", "corr_soft_limit", "corr_hard_limit", "exposure_soft_multiplier"}:
            state[key] = float(value)
        elif key == "max_new_positions":
            state[key] = max(0, int(value))
    save_state(path, state)
    return state


def run_cycle(
    state_path: Path,
    env_path: Path,
    reason: str,
    force_execute: Optional[bool] = None,
) -> Dict[str, Any]:
    state = load_state(state_path)

    execute_orders = bool(force_execute) if force_execute is not None else (state["enabled"] and state["mode"] == "live")
    mode = "execute" if execute_orders else "dry_run"

    try:
        result = execute_alpaca_strategy(
            symbols=state["symbols"],
            env_path=env_path,
            max_new_positions=int(state["max_new_positions"]),
            max_risk_pct=float(state["max_risk_pct"]),
            correlation_soft_limit=float(state["corr_soft_limit"]),
            correlation_hard_limit=float(state["corr_hard_limit"]),
            exposure_soft_multiplier=float(state["exposure_soft_multiplier"]),
            execute_orders=execute_orders,
        )
        summary = {
            "mode": mode,
            "candidate_count": int(result.get("candidate_count", 0)),
            "selected_orders": int(len(result.get("selected_orders", []))),
            "spent_usd": float(result.get("spent_usd", 0.0)),
            "remaining_budget_usd": float(result.get("remaining_budget_usd", 0.0)),
            "selected_order_details": [
                {
                    "symbol": str(order.get("symbol", "")),
                    "action": str(order.get("action", "")),
                    "votes": int(order.get("votes", 0) or 0),
                    "notional_usd": float(order.get("notional_usd", 0.0) or 0.0),
                    "close": float(order.get("close", 0.0) or 0.0),
                }
                for order in list(result.get("selected_orders", []))[:20]
                if isinstance(order, dict)
            ],
        }
        state["last_result"] = summary
        state["last_error"] = ""
    except Exception as exc:
        summary = {
            "mode": mode,
            "candidate_count": 0,
            "selected_orders": 0,
            "spent_usd": 0.0,
            "remaining_budget_usd": 0.0,
        }
        state["last_result"] = summary
        state["last_error"] = str(exc)

    state["last_run_at"] = _utc_now_iso()
    state["last_reason"] = reason
    state["last_mode"] = mode
    state["run_count"] = int(state.get("run_count", 0)) + 1
    save_state(state_path, state)

    return {
        "ok": state["last_error"] == "",
        "state": state,
    }


def maybe_run_due(state_path: Path, env_path: Path) -> Dict[str, Any]:
    state = load_state(state_path)
    if not state.get("enabled", False):
        return {"ok": True, "skipped": "disabled", "state": state}

    now = datetime.now(timezone.utc)
    last_run_at = _parse_iso(str(state.get("last_run_at", "")))
    if last_run_at is not None:
        elapsed = (now - last_run_at).total_seconds()
        if elapsed < max(30, int(state.get("interval_seconds", 300))):
            return {"ok": True, "skipped": "not_due", "state": state}

    return run_cycle(state_path=state_path, env_path=env_path, reason="interval")
