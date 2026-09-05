from __future__ import annotations

import json
import base64
import csv
import io
import hashlib
import hmac
import os
import sqlite3
import sys
import tempfile
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parent
SRC_ROOT = ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from trading_fund.config import get_connection_status, resolve_llm_provider, load_env_file
from trading_fund.backtest import export_backtest_csv, run_five_year_backtest
from trading_fund.ledger import fetch_polymarket_ledger_snapshot
from trading_fund.positions import build_position_cards
from trading_fund.alpaca_execute import execute_alpaca_strategy
from trading_fund.autotrade_manager import load_state as load_autotrade_state, update_settings as update_autotrade_settings, run_cycle as run_autotrade_cycle, maybe_run_due as maybe_run_autotrade_due
from trading_fund.crypto_com_fees import fee_schedule_snapshot
from trading_fund.capital_ledger import add_transfer, transfers_snapshot

WEB_ROOT = ROOT / "web"
IP_MONITOR_STATE_PATH = ROOT / ".ip_monitor_state.json"
BACKTEST_OUTPUT_DIR = ROOT / "outputs" / "backtest"
AUTOTRADE_STATE_PATH = ROOT / ".autotrade_state.json"
CAPITAL_LEDGER_PATH = ROOT / ".capital_ledger.json"
AUTOTRADE_AUDIT_PATH = ROOT / "outputs" / "autotrade_audit.jsonl"
DEFAULT_STRATEGY_SYMBOLS = ["AAPL", "MSFT", "NVDA", "TSLA", "AMD", "AMZN", "META", "GOOGL"]
BACKTEST_DATASET_FILES = {
    "summary": "backtest_summary.csv",
    "drift_monitor": "drift_monitor.csv",
    "gateway_sensitivity": "gateway_sensitivity.csv",
    "per_symbol_gateway": "per_symbol_gateway.csv",
    "walk_forward_folds": "walk_forward_folds.csv",
    "trades": "trades.csv",
}


def _alpaca_base_url(values: dict[str, str]) -> str:
    return values.get("ALPACA_API_BASE_URL", "https://paper-api.alpaca.markets").strip()


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_bool(value: str, default: bool = False) -> bool:
    text = str(value or "").strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return bool(default)


def _parse_int(value: str, default: int) -> int:
    try:
        return int(str(value or "").strip())
    except Exception:
        return int(default)


def _parse_csv(value: str) -> list[str]:
    return [item.strip() for item in str(value or "").split(",") if item.strip()]


def _autotrade_security_config(values: dict[str, str]) -> dict[str, object]:
    return {
        "multi_operator": _parse_bool(values.get("AUTOTRADE_MULTI_OPERATOR", "false"), default=False),
        "cooldown_seconds": max(0, _parse_int(values.get("AUTOTRADE_LIVE_COOLDOWN_SECONDS", "90"), 90)),
        "allowed_live_roles": [role.lower() for role in _parse_csv(values.get("AUTOTRADE_LIVE_APPROVER_ROLES", "owner,admin"))],
    }


def _extract_operator_identity(handler: BaseHTTPRequestHandler, params: dict[str, list[str]]) -> dict[str, str]:
    name = params.get("operator_name", [""])[0].strip()
    role = params.get("operator_role", [""])[0].strip().lower()
    if not name:
        name = str(handler.headers.get("X-Operator-Name", "") or "").strip()
    if not role:
        role = str(handler.headers.get("X-Operator-Role", "") or "").strip().lower()
    if not name:
        name = "unknown"
    if not role:
        role = "unknown"
    return {"name": name, "role": role}


def _can_execute_live(values: dict[str, str], operator_role: str) -> tuple[bool, str]:
    security = _autotrade_security_config(values)
    if not bool(security.get("multi_operator", False)):
        return True, "single_operator_mode"
    allowed_roles = list(security.get("allowed_live_roles", []))
    if operator_role.lower() in allowed_roles:
        return True, "approved"
    return False, "live_approval_required"


def _live_cooldown_state(state: dict[str, object], cooldown_seconds: int) -> dict[str, object]:
    if cooldown_seconds <= 0:
        return {"cooldown_active": False, "remaining_seconds": 0}

    if str(state.get("last_mode", "")) != "execute":
        return {"cooldown_active": False, "remaining_seconds": 0}

    last_run_at_raw = str(state.get("last_run_at", "") or "")
    if not last_run_at_raw:
        return {"cooldown_active": False, "remaining_seconds": 0}

    try:
        last_run_at = datetime.fromisoformat(last_run_at_raw.replace("Z", "+00:00"))
    except Exception:
        return {"cooldown_active": False, "remaining_seconds": 0}

    elapsed = max(0.0, (datetime.now(timezone.utc) - last_run_at).total_seconds())
    remaining = max(0, int(cooldown_seconds - elapsed))
    return {"cooldown_active": remaining > 0, "remaining_seconds": remaining}


def _append_autotrade_audit(event: dict[str, object]) -> None:
    AUTOTRADE_AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(event)
    payload.setdefault("timestamp", _utc_now_iso())
    with AUTOTRADE_AUDIT_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload) + "\n")


def _read_autotrade_audit(limit: int = 100) -> list[dict[str, object]]:
    if not AUTOTRADE_AUDIT_PATH.exists():
        return []
    rows: list[dict[str, object]] = []
    with AUTOTRADE_AUDIT_PATH.open("r", encoding="utf-8") as handle:
        for line in handle:
            text = line.strip()
            if not text:
                continue
            try:
                rows.append(json.loads(text))
            except Exception:
                continue
    if limit <= 0:
        return rows[::-1]
    return rows[-limit:][::-1]


def _fetch_public_ip(url: str) -> str:
    import urllib.request

    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=8) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return str(payload.get("ip", "")).strip()


def _load_ip_monitor_state() -> dict[str, object]:
    if not IP_MONITOR_STATE_PATH.exists():
        return {}
    try:
        return json.loads(IP_MONITOR_STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_ip_monitor_state(state: dict[str, object]) -> None:
    IP_MONITOR_STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")


def _build_whitelist_entries(ipv4: str, ipv6: str) -> list[str]:
    entries = []
    if ipv4:
        entries.append(f"{ipv4}/32")
    if ipv6:
        entries.append(f"{ipv6}/128")
    return entries


def _capture_egress_ips() -> dict[str, str]:
    ipv4 = ""
    ipv6 = ""
    try:
        ipv4 = _fetch_public_ip("https://api.ipify.org?format=json")
    except Exception:
        ipv4 = ""

    try:
        ipv6 = _fetch_public_ip("https://api64.ipify.org?format=json")
    except Exception:
        ipv6 = ""

    return {"ipv4": ipv4, "ipv6": ipv6}


def _refresh_ip_monitor_snapshot() -> dict[str, object]:
    current_ips = _capture_egress_ips()
    previous_state = _load_ip_monitor_state()
    previous_ipv4 = str(previous_state.get("ipv4", "") or "")
    previous_ipv6 = str(previous_state.get("ipv6", "") or "")
    ipv4_changed = bool(previous_ipv4 and current_ips["ipv4"] and previous_ipv4 != current_ips["ipv4"])
    ipv6_changed = bool(previous_ipv6 and current_ips["ipv6"] and previous_ipv6 != current_ips["ipv6"])

    state_payload = {
        "ipv4": current_ips["ipv4"],
        "ipv6": current_ips["ipv6"],
        "updated_at": _utc_now_iso(),
    }
    _save_ip_monitor_state(state_payload)

    warning = ""
    if ipv4_changed or ipv6_changed:
        warning = "Public egress IP changed. Update Crypto.com Exchange IP whitelist before running bot actions."

    return {
        "ok": bool(current_ips["ipv4"] or current_ips["ipv6"]),
        "checked_at": state_payload["updated_at"],
        "current": current_ips,
        "previous": {"ipv4": previous_ipv4, "ipv6": previous_ipv6},
        "changed": {"ipv4": ipv4_changed, "ipv6": ipv6_changed},
        "whitelist_entries": _build_whitelist_entries(current_ips["ipv4"], current_ips["ipv6"]),
        "warning": warning,
    }


def _log_ip_monitor_startup(snapshot: dict[str, object]) -> None:
    current = snapshot.get("current", {})
    whitelist_entries = snapshot.get("whitelist_entries", [])
    print(f"Egress IPv4: {current.get('ipv4', '') or 'unavailable'}")
    print(f"Egress IPv6: {current.get('ipv6', '') or 'unavailable'}")
    if whitelist_entries:
        print("Crypto.com whitelist entries: " + ", ".join(whitelist_entries))
    warning = str(snapshot.get("warning", "") or "")
    if warning:
        print("WARNING: " + warning)


def _dataset_path(dataset: str) -> Path:
    filename = BACKTEST_DATASET_FILES.get(dataset, "")
    if not filename:
        raise ValueError("unknown_dataset")
    return BACKTEST_OUTPUT_DIR / filename


def _read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return [dict(row) for row in reader]


def _backtest_datasets_snapshot() -> dict[str, object]:
    datasets: list[dict[str, object]] = []
    for dataset, filename in BACKTEST_DATASET_FILES.items():
        path = BACKTEST_OUTPUT_DIR / filename
        exists = path.exists()
        rows = _read_csv_rows(path) if exists else []
        stat = path.stat() if exists else None
        datasets.append(
            {
                "dataset": dataset,
                "filename": filename,
                "path": str(path),
                "exists": exists,
                "rows": len(rows),
                "columns": list(rows[0].keys()) if rows else [],
                "updated_at": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat().replace("+00:00", "Z") if stat else "",
                "size_bytes": int(stat.st_size) if stat else 0,
            }
        )
    return {
        "ok": True,
        "base_dir": str(BACKTEST_OUTPUT_DIR),
        "datasets": datasets,
        "generated_at": _utc_now_iso(),
    }


def _build_sql_table_name(dataset: str) -> str:
    return "bt_" + "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in dataset)


def _rows_to_sql_script(dataset: str, rows: list[dict[str, str]]) -> str:
    table = _build_sql_table_name(dataset)
    columns = list(rows[0].keys()) if rows else ["id"]
    create_cols = ", ".join(f'"{col}" TEXT' for col in columns)
    lines = [
        f"DROP TABLE IF EXISTS \"{table}\";",
        f"CREATE TABLE \"{table}\" ({create_cols});",
    ]

    for row in rows:
        values = []
        for col in columns:
            raw = str(row.get(col, "") or "")
            escaped = raw.replace("'", "''")
            values.append(f"'{escaped}'")
        lines.append(f"INSERT INTO \"{table}\" ({', '.join(f'\"{c}\"' for c in columns)}) VALUES ({', '.join(values)});")

    return "\n".join(lines) + "\n"


def _rows_to_sqlite_bytes(dataset: str, rows: list[dict[str, str]]) -> bytes:
    table = _build_sql_table_name(dataset)
    columns = list(rows[0].keys()) if rows else ["id"]
    temp_fd, temp_path = tempfile.mkstemp(suffix=".sqlite3")
    os.close(temp_fd)

    try:
        conn = sqlite3.connect(temp_path)
        cur = conn.cursor()
        create_cols = ", ".join(f'"{col}" TEXT' for col in columns)
        cur.execute(f'CREATE TABLE "{table}" ({create_cols})')
        if rows:
            placeholders = ", ".join("?" for _ in columns)
            insert_sql = f'INSERT INTO "{table}" ({", ".join(f"\"{c}\"" for c in columns)}) VALUES ({placeholders})'
            cur.executemany(insert_sql, [[str(row.get(col, "") or "") for col in columns] for row in rows])
        conn.commit()
        conn.close()
        with open(temp_path, "rb") as handle:
            return handle.read()
    finally:
        try:
            os.remove(temp_path)
        except OSError:
            pass


def _rows_to_xlsx_bytes(dataset: str, rows: list[dict[str, str]]) -> bytes:
    from openpyxl import Workbook

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = _build_sql_table_name(dataset)[:31]

    columns = list(rows[0].keys()) if rows else ["id"]
    sheet.append(columns)
    for row in rows:
        sheet.append([str(row.get(col, "") or "") for col in columns])

    output = io.BytesIO()
    workbook.save(output)
    output.seek(0)
    return output.read()


def _serialize_dataset(dataset: str, fmt: str) -> tuple[bytes, str, str]:
    path = _dataset_path(dataset)
    if not path.exists():
        raise FileNotFoundError("dataset_not_found")

    rows = _read_csv_rows(path)

    if fmt == "csv":
        return path.read_bytes(), "text/csv; charset=utf-8", f"{dataset}.csv"

    if fmt == "json":
        payload = {
            "dataset": dataset,
            "rows": rows,
            "row_count": len(rows),
            "generated_at": _utc_now_iso(),
        }
        return json.dumps(payload, indent=2).encode("utf-8"), "application/json; charset=utf-8", f"{dataset}.json"

    if fmt == "sql":
        script = _rows_to_sql_script(dataset, rows)
        return script.encode("utf-8"), "application/sql; charset=utf-8", f"{dataset}.sql"

    if fmt == "sqlite":
        data = _rows_to_sqlite_bytes(dataset, rows)
        return data, "application/x-sqlite3", f"{dataset}.sqlite3"

    if fmt == "xlsx":
        data = _rows_to_xlsx_bytes(dataset, rows)
        return data, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", f"{dataset}.xlsx"

    raise ValueError("unsupported_format")


def _alpaca_headers(values: dict[str, str]) -> dict[str, str]:
    return {
        "APCA-API-KEY-ID": values.get("ALPACA_API_KEY", ""),
        "APCA-API-SECRET-KEY": values.get("ALPACA_API_SECRET", ""),
    }


def _fetch_alpaca_json(url: str, headers: dict[str, str]):
    import urllib.request

    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def _crypto_com_base_url(values: dict[str, str]) -> str:
    return values.get("CRYPTO_COM_API_BASE_URL", "https://api.crypto.com").strip().rstrip("/")


def _crypto_com_sign_payload(
    method: str,
    req_id: int,
    api_key: str,
    api_secret: str,
    params: dict[str, object],
    nonce: int,
) -> str:
    def encode(value: object) -> str:
        if isinstance(value, dict):
            parts = []
            for key in sorted(value.keys()):
                parts.append(f"{key}{encode(value[key])}")
            return "".join(parts)
        if isinstance(value, list):
            return "".join(encode(item) for item in value)
        if value is None:
            return "null"
        return str(value)

    param_string = "".join(f"{key}{encode(params[key])}" for key in sorted(params.keys()))
    payload = f"{method}{req_id}{api_key}{param_string}{nonce}"
    return hmac.new(api_secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()


def _fetch_crypto_com_balances(values: dict[str, str]) -> dict[str, object]:
    private_call = _crypto_com_private_call(values, "private/get-account-summary", {})
    if not private_call.get("ok"):
        return {
            "ok": False,
            "reason": private_call.get("reason", "request_failed"),
            "message": private_call.get("message", "Unable to query Crypto.com account summary."),
            "endpoint": private_call.get("endpoint", ""),
            "attempts": private_call.get("attempts", []),
        }

    response_payload = private_call.get("response", {})
    endpoint = private_call.get("endpoint", "")
    attempts = private_call.get("attempts", [])

    accounts = response_payload.get("result", {}).get("accounts", [])
    balances = []
    for account in accounts:
        currency = str(account.get("currency", "")).upper()
        balance = float(account.get("balance", 0) or 0)
        available = float(account.get("available", 0) or 0)
        if balance <= 0:
            continue
        balances.append(
            {
                "currency": currency,
                "balance": balance,
                "available": available,
            }
        )

    balances.sort(key=lambda item: item["balance"], reverse=True)
    return {
        "ok": True,
        "reason": "ready",
        "balances": balances,
        "raw_account_count": len(accounts),
        "endpoint": endpoint,
        "attempts": attempts,
    }


def _crypto_com_private_call(values: dict[str, str], method: str, params: dict[str, object]) -> dict[str, object]:
    import urllib.error
    import urllib.request

    api_key = values.get("CRYPTO_COM_API_KEY", "")
    api_secret = values.get("CRYPTO_COM_API_SECRET", "")
    if not api_key or not api_secret:
        return {"ok": False, "reason": "missing_keys", "message": "Missing Crypto.com API credentials."}

    base_url = _crypto_com_base_url(values)
    endpoints = [
        f"{base_url}/v2/private/get-account-summary",
        f"{base_url}/exchange/v1/private/get-account-summary",
    ]
    req_id = 1
    nonce = int(time.time() * 1000)
    sig = _crypto_com_sign_payload(method, req_id, api_key, api_secret, params, nonce)

    payload = {
        "id": req_id,
        "method": method,
        "api_key": api_key,
        "params": params,
        "nonce": nonce,
        "sig": sig,
    }

    response_payload = None
    last_error = ""
    endpoint = endpoints[0]
    attempts = []
    for endpoint in endpoints:
        req = urllib.request.Request(
            endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=15) as response:
                response_payload = json.loads(response.read().decode("utf-8"))
                attempts.append(
                    {
                        "endpoint": endpoint,
                        "http_status": int(getattr(response, "status", 200)),
                        "api_code": response_payload.get("code"),
                        "api_message": response_payload.get("message", ""),
                    }
                )
            last_error = None
            break
        except urllib.error.HTTPError as exc:
            body_text = exc.read().decode("utf-8", errors="replace")
            api_code = None
            api_message = ""
            try:
                parsed = json.loads(body_text)
                api_code = parsed.get("code")
                api_message = parsed.get("message", "")
            except Exception:
                parsed = None

            attempts.append(
                {
                    "endpoint": endpoint,
                    "http_status": int(exc.code),
                    "api_code": api_code,
                    "api_message": api_message,
                    "raw_body": body_text[:400],
                }
            )
            last_error = api_message or str(exc)
        except Exception as exc:
            last_error = str(exc)
            attempts.append(
                {
                    "endpoint": endpoint,
                    "http_status": None,
                    "api_code": None,
                    "api_message": str(exc),
                }
            )

    if response_payload is None:
        return {
            "ok": False,
            "reason": "request_failed",
            "message": last_error or "Unable to reach Crypto.com API.",
            "endpoint": endpoint,
            "attempts": attempts,
        }

    if response_payload.get("code") != 0:
        return {
            "ok": False,
            "reason": "api_error",
            "message": response_payload.get("message", "Crypto.com API returned an error."),
            "code": response_payload.get("code"),
            "endpoint": endpoint,
            "attempts": attempts,
        }

    return {
        "ok": True,
        "reason": "ready",
        "endpoint": endpoint,
        "attempts": attempts,
        "response": response_payload,
    }


def _fetch_crypto_com_public_price(base_url: str, instrument_name: str) -> float:
    import urllib.request

    endpoint = f"{base_url}/v2/public/get-ticker?instrument_name={instrument_name}"
    req = urllib.request.Request(endpoint)
    with urllib.request.urlopen(req, timeout=10) as response:
        payload = json.loads(response.read().decode("utf-8"))

    data = payload.get("result", {}).get("data", [])
    if not data:
        raise ValueError("ticker_not_found")
    row = data[0] or {}

    # Prefer last traded price, then ask price, then mark-like fallback fields.
    for key in ("a", "k", "b"):
        try:
            price = float(row.get(key, 0) or 0)
            if price > 0:
                return price
        except Exception:
            continue
    raise ValueError("price_unavailable")


def _fetch_crypto_com_quotes(values: dict[str, str], symbols: list[str]) -> dict[str, object]:
    base_url = _crypto_com_base_url(values)
    quote_map: dict[str, float] = {}
    errors: list[dict[str, str]] = []

    stable_assets = {"USD", "USDT", "USDC"}
    for raw_symbol in symbols:
        symbol = str(raw_symbol or "").upper().strip()
        if not symbol:
            continue
        if symbol in stable_assets:
            quote_map[symbol] = 1.0
            continue

        candidates = [f"{symbol}_USDT", f"{symbol}_USD", f"{symbol}_USDC"]
        resolved = False
        for instrument in candidates:
            try:
                quote_map[symbol] = _fetch_crypto_com_public_price(base_url, instrument)
                resolved = True
                break
            except Exception:
                continue

        if not resolved:
            errors.append({"symbol": symbol, "reason": "quote_unavailable"})

    return {
        "ok": True,
        "quotes": quote_map,
        "errors": errors,
    }


def _crypto_com_diagnostics(values: dict[str, str]) -> dict[str, object]:
    api_key = values.get("CRYPTO_COM_API_KEY", "")
    api_secret = values.get("CRYPTO_COM_API_SECRET", "")
    base_url = _crypto_com_base_url(values)

    diagnostics: dict[str, object] = {
        "ok": False,
        "base_url": base_url,
        "api_key_present": bool(api_key),
        "api_secret_present": bool(api_secret),
        "api_key_prefix": api_key[:4] if api_key else "",
        "api_key_length": len(api_key),
        "api_secret_length": len(api_secret),
        "api_secret_base64_valid": False,
        "server_time_ms": int(time.time() * 1000),
        "hints": [],
    }

    hints: list[str] = []
    if not api_key or not api_secret:
        if not api_key:
            hints.append("CRYPTO_COM_API_KEY is missing.")
        if not api_secret:
            hints.append("CRYPTO_COM_API_SECRET is missing.")
        diagnostics["hints"] = hints
        return diagnostics

    try:
        base64.b64decode(api_secret, validate=True)
        diagnostics["api_secret_base64_valid"] = True
    except Exception:
        hints.append("CRYPTO_COM_API_SECRET is not valid base64 text. Verify exact value from Crypto.com Exchange API settings.")

    private_probe = _crypto_com_private_call(values, "private/get-account-summary", {})
    diagnostics["private_probe"] = {
        "ok": private_probe.get("ok", False),
        "reason": private_probe.get("reason", ""),
        "message": private_probe.get("message", ""),
        "endpoint": private_probe.get("endpoint", ""),
        "attempts": private_probe.get("attempts", []),
    }

    if private_probe.get("ok"):
        diagnostics["ok"] = True
        hints.append("Private API auth succeeded. Balances can be fetched.")
    else:
        message = str(private_probe.get("message", "")).lower()
        attempts = private_probe.get("attempts", [])
        saw_401 = any(attempt.get("http_status") == 401 for attempt in attempts if isinstance(attempt, dict))
        if saw_401 or "unauthorized" in message:
            hints.append("Crypto.com rejected authentication (401). Check API key and secret pair, Exchange permissions, and IP whitelist rules.")
        if "nonce" in message:
            hints.append("Nonce/time issue detected. Ensure local system clock is accurate and synchronized.")
        if not hints:
            hints.append("Private API call failed. Inspect private_probe.attempts for endpoint-specific details.")

    diagnostics["hints"] = hints
    return {
        **diagnostics,
    }


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)

        if parsed.path == "/api/connection":
            params = parse_qs(parsed.query)
            connection_type = params.get("type", [""])[0]
            status = get_connection_status(connection_type, ROOT / ".env")
            body = json.dumps(status).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if parsed.path == "/api/llm":
            status = resolve_llm_provider(ROOT / ".env")
            body = json.dumps(status).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if parsed.path == "/api/crypto/balances":
            values = load_env_file(ROOT / ".env")
            status = _fetch_crypto_com_balances(values)
            body = json.dumps(status).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if parsed.path == "/api/crypto/quotes":
            values = load_env_file(ROOT / ".env")
            params = parse_qs(parsed.query)
            symbols_raw = params.get("symbols", [""])[0]
            symbols = [item.strip().upper() for item in symbols_raw.split(",") if item.strip()]
            status = _fetch_crypto_com_quotes(values, symbols)
            body = json.dumps(status).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if parsed.path == "/api/crypto/fees":
            params = parse_qs(parsed.query)
            volume_raw = params.get("volume_30d_usd", [""])[0]
            volume = None
            if volume_raw:
                try:
                    volume = float(volume_raw)
                except ValueError:
                    volume = None
            status = fee_schedule_snapshot(volume)
            body = json.dumps(status).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if parsed.path == "/api/capital/transfers":
            status = transfers_snapshot(CAPITAL_LEDGER_PATH)
            body = json.dumps({"ok": True, **status}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if parsed.path == "/api/capital/transfers/add":
            params = parse_qs(parsed.query)
            amount_raw = params.get("amount", [""])[0]
            try:
                amount = float(amount_raw)
            except ValueError:
                body = json.dumps({"ok": False, "reason": "invalid_amount"}).encode("utf-8")
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

            currency = params.get("currency", ["USD"])[0]
            direction = params.get("direction", ["deposit"])[0]
            source = params.get("source", ["crypto_com_app"])[0]
            note = params.get("note", [""])[0]

            result = add_transfer(
                CAPITAL_LEDGER_PATH,
                amount=amount,
                currency=currency,
                direction=direction,
                source=source,
                note=note,
            )
            body = json.dumps({"ok": True, **result}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if parsed.path == "/api/crypto/diagnostics":
            values = load_env_file(ROOT / ".env")
            status = _crypto_com_diagnostics(values)
            body = json.dumps(status).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if parsed.path == "/api/network/egress-ip":
            status = _refresh_ip_monitor_snapshot()
            body = json.dumps(status).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if parsed.path == "/api/backtest/datasets":
            body = json.dumps(_backtest_datasets_snapshot()).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if parsed.path == "/api/backtest/regenerate":
            params = parse_qs(parsed.query)
            symbols_raw = params.get("symbols", ["AAPL,MSFT,NVDA,TSLA"])[0]
            symbols = [item.strip().upper() for item in symbols_raw.split(",") if item.strip()]
            try:
                result = run_five_year_backtest(
                    symbols=symbols,
                    env_path=ROOT / ".env",
                    walk_forward=True,
                    walk_forward_train_years=1,
                    walk_forward_test_months=3,
                )
                files = export_backtest_csv(result, BACKTEST_OUTPUT_DIR)
                body = json.dumps({"ok": True, "files": files, "summary": _backtest_datasets_snapshot()}).encode("utf-8")
                self.send_response(200)
            except Exception as exc:
                body = json.dumps({"ok": False, "reason": "regeneration_failed", "message": str(exc)}).encode("utf-8")
                self.send_response(400)

            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if parsed.path == "/api/backtest/preview":
            params = parse_qs(parsed.query)
            dataset = params.get("dataset", [""])[0]
            limit_raw = params.get("limit", ["50"])[0]
            try:
                limit = max(1, min(500, int(limit_raw)))
            except ValueError:
                limit = 50

            try:
                path = _dataset_path(dataset)
                rows = _read_csv_rows(path)
                body = json.dumps(
                    {
                        "ok": True,
                        "dataset": dataset,
                        "row_count": len(rows),
                        "columns": list(rows[0].keys()) if rows else [],
                        "rows": rows[:limit],
                        "updated_at": datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat().replace("+00:00", "Z") if path.exists() else "",
                    }
                ).encode("utf-8")
                self.send_response(200)
            except Exception as exc:
                body = json.dumps({"ok": False, "reason": "preview_failed", "message": str(exc)}).encode("utf-8")
                self.send_response(400)

            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if parsed.path == "/api/backtest/export":
            params = parse_qs(parsed.query)
            dataset = params.get("dataset", [""])[0]
            fmt = params.get("format", ["csv"])[0].lower()

            try:
                payload, content_type, filename = _serialize_dataset(dataset, fmt)
                self.send_response(200)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
            except FileNotFoundError:
                body = json.dumps({"ok": False, "reason": "dataset_not_found"}).encode("utf-8")
                self.send_response(404)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except ValueError as exc:
                body = json.dumps({"ok": False, "reason": str(exc)}).encode("utf-8")
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            return

        if parsed.path == "/api/strategy/execution-preview":
            params = parse_qs(parsed.query)
            symbols_raw = params.get("symbols", [","])[0]
            max_new_positions_raw = params.get("max_new_positions", ["0"])[0]
            max_risk_pct_raw = params.get("max_risk_pct", ["0.05"])[0]
            corr_soft_raw = params.get("corr_soft_limit", ["0.75"])[0]
            corr_hard_raw = params.get("corr_hard_limit", ["0.9"])[0]
            exposure_mult_raw = params.get("exposure_soft_multiplier", ["0.5"])[0]
            sector_soft_raw = params.get("sector_soft_limit", ["1.0"])[0]
            factor_soft_raw = params.get("factor_soft_limit", ["1.0"])[0]
            group_soft_mult_raw = params.get("group_soft_multiplier", ["0.65"])[0]

            symbols = [item.strip().upper() for item in symbols_raw.split(",") if item.strip()]
            if not symbols:
                symbols = list(DEFAULT_STRATEGY_SYMBOLS)

            try:
                preview = execute_alpaca_strategy(
                    symbols=symbols,
                    env_path=ROOT / ".env",
                    max_new_positions=max(0, int(max_new_positions_raw)),
                    max_risk_pct=max(0.0, float(max_risk_pct_raw)),
                    correlation_soft_limit=float(corr_soft_raw),
                    correlation_hard_limit=float(corr_hard_raw),
                    exposure_soft_multiplier=float(exposure_mult_raw),
                    sector_soft_limit=float(sector_soft_raw),
                    factor_soft_limit=float(factor_soft_raw),
                    group_soft_multiplier=float(group_soft_mult_raw),
                    execute_orders=False,
                )
                body = json.dumps({"ok": True, **preview}).encode("utf-8")
                self.send_response(200)
            except Exception as exc:
                body = json.dumps({"ok": False, "reason": "execution_preview_failed", "message": str(exc)}).encode("utf-8")
                self.send_response(400)

            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if parsed.path == "/api/autotrade/status":
            values = load_env_file(ROOT / ".env")
            due_result = maybe_run_autotrade_due(AUTOTRADE_STATE_PATH, ROOT / ".env")
            state = load_autotrade_state(AUTOTRADE_STATE_PATH)
            security = _autotrade_security_config(values)
            cooldown = _live_cooldown_state(state, int(security.get("cooldown_seconds", 90)))
            body = json.dumps(
                {
                    "ok": True,
                    "state": state,
                    "due_result": due_result,
                    "alpaca_base_url": values.get("ALPACA_API_BASE_URL", "https://paper-api.alpaca.markets"),
                    "security": {
                        **security,
                        **cooldown,
                    },
                }
            ).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if parsed.path == "/api/autotrade/toggle":
            params = parse_qs(parsed.query)
            enabled_raw = params.get("enabled", [""])[0]
            enabled = _parse_bool(enabled_raw, default=False)
            state = update_autotrade_settings(AUTOTRADE_STATE_PATH, {"enabled": enabled})
            body = json.dumps({"ok": True, "state": state}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if parsed.path == "/api/autotrade/config":
            params = parse_qs(parsed.query)
            updates = {}
            if "mode" in params:
                updates["mode"] = params.get("mode", ["dry_run"])[0]
            if "interval_seconds" in params:
                updates["interval_seconds"] = int(params.get("interval_seconds", ["300"])[0])
            if "symbols" in params:
                updates["symbols"] = params.get("symbols", [""])[0]
            if "max_risk_pct" in params:
                updates["max_risk_pct"] = float(params.get("max_risk_pct", ["0.05"])[0])
            if "max_new_positions" in params:
                updates["max_new_positions"] = int(params.get("max_new_positions", ["0"])[0])
            if "corr_soft_limit" in params:
                updates["corr_soft_limit"] = float(params.get("corr_soft_limit", ["0.75"])[0])
            if "corr_hard_limit" in params:
                updates["corr_hard_limit"] = float(params.get("corr_hard_limit", ["0.9"])[0])
            if "exposure_soft_multiplier" in params:
                updates["exposure_soft_multiplier"] = float(params.get("exposure_soft_multiplier", ["0.5"])[0])

            state = update_autotrade_settings(AUTOTRADE_STATE_PATH, updates)
            body = json.dumps({"ok": True, "state": state}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if parsed.path == "/api/autotrade/run-once":
            values = load_env_file(ROOT / ".env")
            params = parse_qs(parsed.query)
            operator = _extract_operator_identity(self, params)
            execute = _parse_bool(params.get("execute", ["false"])[0], default=False)

            if execute:
                current_state = load_autotrade_state(AUTOTRADE_STATE_PATH)
                security = _autotrade_security_config(values)
                cooldown = _live_cooldown_state(current_state, int(security.get("cooldown_seconds", 90)))
                if bool(cooldown.get("cooldown_active", False)):
                    payload = {
                        "ok": False,
                        "reason": "live_cooldown_active",
                        "remaining_seconds": int(cooldown.get("remaining_seconds", 0)),
                        "state": current_state,
                    }
                    _append_autotrade_audit(
                        {
                            "event": "manual_run_once_rejected",
                            "execute": True,
                            "reason": "live_cooldown_active",
                            "operator": operator,
                            "remaining_seconds": int(cooldown.get("remaining_seconds", 0)),
                        }
                    )
                    body = json.dumps(payload).encode("utf-8")
                    self.send_response(429)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return

                approved, approval_reason = _can_execute_live(values, operator.get("role", "unknown"))
                if not approved:
                    payload = {
                        "ok": False,
                        "reason": "live_approval_required",
                        "required_roles": _autotrade_security_config(values).get("allowed_live_roles", []),
                    }
                    _append_autotrade_audit(
                        {
                            "event": "manual_run_once_rejected",
                            "execute": True,
                            "reason": "live_approval_required",
                            "operator": operator,
                        }
                    )
                    body = json.dumps(payload).encode("utf-8")
                    self.send_response(403)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return

            result = run_autotrade_cycle(
                state_path=AUTOTRADE_STATE_PATH,
                env_path=ROOT / ".env",
                reason="manual_run_once",
                force_execute=execute,
            )
            _append_autotrade_audit(
                {
                    "event": "manual_run_once",
                    "execute": execute,
                    "operator": operator,
                    "ok": bool(result.get("ok", False)),
                    "last_error": str(result.get("state", {}).get("last_error", "") or ""),
                    "selected_orders": int(result.get("state", {}).get("last_result", {}).get("selected_orders", 0) or 0),
                }
            )
            body = json.dumps(result).encode("utf-8")
            self.send_response(200 if result.get("ok") else 400)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if parsed.path == "/api/autotrade/audit":
            params = parse_qs(parsed.query)
            limit = max(1, min(1000, _parse_int(params.get("limit", ["100"])[0], 100)))
            rows = _read_autotrade_audit(limit=limit)
            body = json.dumps({"ok": True, "events": rows, "count": len(rows)}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if parsed.path == "/api/polymarket-ledger":
            values = load_env_file(ROOT / ".env")
            try:
                status = fetch_polymarket_ledger_snapshot(values)
            except Exception as exc:
                status = {"ok": False, "reason": "rpc_error", "details": str(exc)}
            body = json.dumps(status).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if parsed.path == "/api/positions":
            values = load_env_file(ROOT / ".env")
            headers = _alpaca_headers(values)
            base_url = _alpaca_base_url(values)

            try:
                positions_payload = _fetch_alpaca_json(
                    f"{base_url.rstrip('/')}/v2/positions", headers
                )
            except Exception:
                positions_payload = []

            cards = []
            for position in positions_payload:
                symbol = position.get("symbol", "")
                qty = float(position.get("qty", 0))
                entry_price = float(position.get("avg_entry_price", 0))
                market_price = float(position.get("current_price", entry_price))
                cards.append(
                    {
                        "symbol": symbol,
                        "side": position.get("side", "LONG"),
                        "qty": qty,
                        "entry_price": entry_price,
                        "market_price": market_price,
                        "pnl": (market_price - entry_price) * qty,
                    }
                )

            body = json.dumps(cards).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if parsed.path.rstrip("/") == "/api/account":
            values = load_env_file(ROOT / ".env")
            headers = _alpaca_headers(values)
            base_url = _alpaca_base_url(values)
            is_paper = "paper" in base_url.lower()

            try:
                account = _fetch_alpaca_json(f"{base_url.rstrip('/')}/v2/account", headers)
                payload = {
                    "ok": True,
                    "equity": float(account.get("equity", 0) or 0),
                    "buying_power": float(account.get("buying_power", 0) or 0),
                    "cash": float(account.get("cash", 0) or 0),
                    "account_number": account.get("account_number", ""),
                    "status": account.get("status", ""),
                    "trading_blocked": bool(account.get("trading_blocked", False)),
                    "base_url": base_url,
                    "environment": "paper" if is_paper else "live",
                    "environment_label": "Paper account" if is_paper else "Live account",
                }
            except Exception as exc:
                payload = {
                    "ok": False,
                    "reason": "request_failed",
                    "message": str(exc),
                    "base_url": base_url,
                    "environment": "paper" if is_paper else "live",
                    "environment_label": "Paper account" if is_paper else "Live account",
                }

            body = json.dumps(payload).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        file_path = (WEB_ROOT / parsed.path.lstrip("/")).resolve()
        if file_path.exists() and file_path.is_file() and WEB_ROOT in file_path.parents:
            content = file_path.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", self._content_type(file_path))
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
            return

        self.send_error(404, "File not found")

    def _content_type(self, path: Path) -> str:
        if path.suffix == ".css":
            return "text/css; charset=utf-8"
        if path.suffix == ".js":
            return "text/javascript; charset=utf-8"
        return "text/html; charset=utf-8"

    def log_message(self, format: str, *args):
        return


if __name__ == "__main__":
    startup_snapshot = _refresh_ip_monitor_snapshot()
    _log_ip_monitor_startup(startup_snapshot)
    server = ThreadingHTTPServer(("127.0.0.1", 8000), Handler)
    print("Serving at http://127.0.0.1:8000")
    server.serve_forever()
