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
    total_deposits = sum(float(t.get("amount_usd", 0.0)) for t in transfers if t.get("direction") == "deposit")
    total_withdrawals = sum(float(t.get("amount_usd", 0.0)) for t in transfers if t.get("direction") == "withdrawal")
    return {
        "transfer_count": len(transfers),
        "total_deposits_usd": round(total_deposits, 2),
        "total_withdrawals_usd": round(total_withdrawals, 2),
        "net_contributed_usd": round(total_deposits - total_withdrawals, 2),
    }


def add_transfer(
    path: Path,
    amount_usd: float,
    direction: str = "deposit",
    source: str = "crypto_com_app",
    note: str = "",
) -> Dict[str, Any]:
    direction = direction if direction in VALID_DIRECTIONS else "deposit"
    source = source if source in VALID_SOURCES else "other"
    amount = max(0.0, float(amount_usd or 0))

    transfers = load_transfers(path)
    entry = {
        "id": len(transfers) + 1,
        "amount_usd": amount,
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
