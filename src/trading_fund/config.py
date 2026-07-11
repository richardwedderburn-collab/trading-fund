from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, Optional


def load_env_file(env_path: Optional[Path | str] = None) -> Dict[str, str]:
    path = Path(env_path or Path(__file__).resolve().parents[2] / ".env")
    values: Dict[str, str] = {}

    if not path.exists():
        return values

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        lower_line = line.lower()
        if lower_line.startswith("key="):
            values["ALPACA_API_KEY"] = line.split("=", 1)[1].strip()
            continue

        if lower_line.startswith("secret key=") or lower_line.startswith("secret="):
            values["ALPACA_API_SECRET"] = line.split("=", 1)[1].strip()
            continue

        if "=" in line:
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()

    return values


def get_connection_status(connection_type: str, env_path: Optional[Path | str] = None) -> Dict[str, object]:
    values = load_env_file(env_path)

    if connection_type == "wallet":
        required_keys = ["COINBASE_API_KEY", "COINBASE_API_SECRET"]
    elif connection_type == "platform":
        required_keys = ["BINANCE_API_KEY", "BINANCE_API_SECRET"]
    elif connection_type == "alpaca":
        required_keys = ["ALPACA_API_KEY", "ALPACA_API_SECRET"]
    elif connection_type == "crypto":
        required_keys = ["CRYPTO_COM_API_KEY", "CRYPTO_COM_API_SECRET"]
    else:
        return {"ok": False, "reason": "unknown_connection"}

    missing = [key for key in required_keys if not values.get(key)]
    if missing:
        return {
            "ok": False,
            "reason": "missing_keys",
            "missing_keys": missing,
        }

    return {"ok": True, "reason": "ready"}


def resolve_llm_provider(env_path: Optional[Path | str] = None) -> Dict[str, object]:
    values = load_env_file(env_path)
    if values.get("OLLAMA_HOST"):
        return {
            "provider": "ollama",
            "host": values.get("OLLAMA_HOST"),
            "model": values.get("OLLAMA_MODEL") or "llama3",
            "ready": True,
        }

    if values.get("OPENROUTER_API_KEY"):
        return {
            "provider": "openrouter",
            "model": values.get("OPENROUTER_MODEL") or "openai/gpt-4o-mini",
            "ready": True,
        }

    return {"provider": "none", "ready": False, "reason": "missing_keys"}
