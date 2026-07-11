from __future__ import annotations

import json
from typing import Any, Dict, Iterable, Optional
from urllib import request


TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"


def _rpc_call(rpc_url: str, method: str, params: list[Any], timeout: int = 10) -> Any:
    payload = json.dumps(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": method,
            "params": params,
        }
    ).encode("utf-8")
    req = request.Request(
        rpc_url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with request.urlopen(req, timeout=timeout) as response:
        body = json.loads(response.read().decode("utf-8"))
    if "error" in body:
        raise ValueError(str(body["error"]))
    return body.get("result")


def _topic_to_address(topic_hex: str) -> str:
    value = str(topic_hex or "").lower().replace("0x", "")
    if len(value) < 40:
        return ZERO_ADDRESS
    return "0x" + value[-40:]


def _iter_wallets(log: Dict[str, Any]) -> Iterable[str]:
    topics = log.get("topics") or []
    if len(topics) < 3:
        return []
    return (_topic_to_address(topics[1]), _topic_to_address(topics[2]))


def fetch_erc20_transfer_metrics(
    rpc_url: str,
    token_contract: str,
    from_block: int,
    to_block: Optional[int] = None,
    token_decimals: int = 6,
    token_price_usd: float = 1.0,
) -> Dict[str, Any]:
    """
    Pull ERC-20 Transfer logs from an EVM RPC endpoint and aggregate metrics.
    """
    if to_block is None:
        latest_hex = _rpc_call(rpc_url, "eth_blockNumber", [])
        to_block = int(str(latest_hex), 16)

    logs = _rpc_call(
        rpc_url,
        "eth_getLogs",
        [
            {
                "address": token_contract,
                "fromBlock": hex(max(0, int(from_block))),
                "toBlock": hex(max(0, int(to_block))),
                "topics": [TRANSFER_TOPIC],
            }
        ],
    ) or []

    tx_count = len(logs)
    wallets: set[str] = set()
    raw_volume = 0

    for log in logs:
        for wallet in _iter_wallets(log):
            if wallet != ZERO_ADDRESS:
                wallets.add(wallet)
        try:
            raw_volume += int(str(log.get("data") or "0x0"), 16)
        except ValueError:
            continue

    denominator = 10 ** max(0, int(token_decimals))
    volume_token = raw_volume / denominator
    volume_usd = volume_token * float(token_price_usd)

    return {
        "ledger_tx_count": tx_count,
        "ledger_unique_wallets": len(wallets),
        "ledger_volume_usd": volume_usd,
        "from_block": int(from_block),
        "to_block": int(to_block),
    }


def fetch_polymarket_ledger_snapshot(env_values: Dict[str, str]) -> Dict[str, Any]:
    """
    Build polymarket-ready ledger metrics from RPC configuration.
    """
    rpc_url = env_values.get("POLYMARKET_RPC_URL", "").strip()
    token_contract = env_values.get("POLYMARKET_TOKEN_CONTRACT", "").strip()
    if not rpc_url or not token_contract:
        return {
            "ok": False,
            "reason": "missing_config",
            "required": ["POLYMARKET_RPC_URL", "POLYMARKET_TOKEN_CONTRACT"],
        }

    from_block = int(env_values.get("POLYMARKET_FROM_BLOCK", "0") or 0)
    to_block_raw = env_values.get("POLYMARKET_TO_BLOCK", "").strip()
    to_block = int(to_block_raw) if to_block_raw else None
    token_decimals = int(env_values.get("POLYMARKET_TOKEN_DECIMALS", "6") or 6)
    token_price_usd = float(env_values.get("POLYMARKET_TOKEN_PRICE_USD", "1.0") or 1.0)

    metrics = fetch_erc20_transfer_metrics(
        rpc_url=rpc_url,
        token_contract=token_contract,
        from_block=from_block,
        to_block=to_block,
        token_decimals=token_decimals,
        token_price_usd=token_price_usd,
    )
    metrics["ok"] = True
    return metrics