from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

VALID_DIRECTIONS = {"deposit", "withdrawal"}
VALID_SOURCES = {"crypto_com_app", "crypto_com_exchange", "bank_transfer", "other"}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def load_transfers(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    if not isinstance(payload, list):
        return []
    return [entry for entry in payload if isinstance(entry, dict)]


def save_transfers(path: Path, transfers: List[Dict[str, Any]]) -> None:
    path.write_text(json.dumps(transfers, indent=2), encoding="utf-8")


def summarize(transfers: List[Dict[str, Any]]) -> Dict[str, Any]:
    by_currency: Dict[str, Dict[str, float]] = {}
    for entry in transfers:
        currency = str(entry.get("currency") or "USD").upper()
        bucket = by_currency.setdefault(currency, {"total_deposits": 0.0, "total_withdrawals": 0.0})
        amount = float(entry.get("amount", 0.0))
        if entry.get("direction") == "withdrawal":
            bucket["total_withdrawals"] += amount
        else:
            bucket["total_deposits"] += amount

    for currency, bucket in by_currency.items():
        bucket["total_deposits"] = round(bucket["total_deposits"], 2)
        bucket["total_withdrawals"] = round(bucket["total_withdrawals"], 2)
        bucket["net_contributed"] = round(bucket["total_deposits"] - bucket["total_withdrawals"], 2)

    return {
        "transfer_count": len(transfers),
        "by_currency": by_currency,
    }


def add_transfer(
    path: Path,
    amount: float,
    currency: str = "USD",
    direction: str = "deposit",
    source: str = "crypto_com_app",
    note: str = "",
) -> Dict[str, Any]:
    direction = direction if direction in VALID_DIRECTIONS else "deposit"
    source = source if source in VALID_SOURCES else "other"
    amount = round(max(0.0, float(amount or 0)), 2)
    currency = str(currency or "USD").upper()

    transfers = load_transfers(path)
    entry = {
        "id": len(transfers) + 1,
        "amount": amount,
        "currency": currency,
        "direction": direction,
        "source": source,
        "note": str(note or ""),
        "recorded_at": _utc_now_iso(),
    }
    transfers.append(entry)
    save_transfers(path, transfers)

    return {
        "transfer": entry,
        "transfers": transfers,
        "summary": summarize(transfers),
    }


def transfers_snapshot(path: Path) -> Dict[str, Any]:
    transfers = load_transfers(path)
    return {
        "transfers": transfers,
        "summary": summarize(transfers),
    }
