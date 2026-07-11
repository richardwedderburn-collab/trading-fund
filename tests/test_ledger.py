from trading_fund.ledger import fetch_erc20_transfer_metrics, fetch_polymarket_ledger_snapshot


def test_fetch_erc20_transfer_metrics_aggregates_logs(monkeypatch):
    calls = []

    def fake_rpc_call(rpc_url, method, params, timeout=10):
        calls.append((rpc_url, method, params))
        if method == "eth_blockNumber":
            return "0x64"
        if method == "eth_getLogs":
            return [
                {
                    "topics": [
                        "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef",
                        "0x0000000000000000000000001111111111111111111111111111111111111111",
                        "0x0000000000000000000000002222222222222222222222222222222222222222",
                    ],
                    "data": hex(2_000_000),
                },
                {
                    "topics": [
                        "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef",
                        "0x0000000000000000000000001111111111111111111111111111111111111111",
                        "0x0000000000000000000000003333333333333333333333333333333333333333",
                    ],
                    "data": hex(1_000_000),
                },
            ]
        raise AssertionError(f"unexpected method {method}")

    monkeypatch.setattr("trading_fund.ledger._rpc_call", fake_rpc_call)

    metrics = fetch_erc20_transfer_metrics(
        rpc_url="https://rpc.example",
        token_contract="0xabc",
        from_block=10,
        to_block=None,
        token_decimals=6,
        token_price_usd=1.0,
    )

    assert metrics["ledger_tx_count"] == 2
    assert metrics["ledger_unique_wallets"] == 3
    assert metrics["ledger_volume_usd"] == 3.0
    assert metrics["from_block"] == 10
    assert metrics["to_block"] == 100
    assert calls[0][1] == "eth_blockNumber"
    assert calls[1][1] == "eth_getLogs"


def test_fetch_polymarket_ledger_snapshot_requires_config():
    snapshot = fetch_polymarket_ledger_snapshot({})

    assert snapshot["ok"] is False
    assert snapshot["reason"] == "missing_config"


def test_fetch_polymarket_ledger_snapshot_uses_helper(monkeypatch):
    def fake_fetch(**kwargs):
        assert kwargs["rpc_url"] == "https://rpc.example"
        assert kwargs["token_contract"] == "0xabc"
        assert kwargs["from_block"] == 120
        assert kwargs["to_block"] == 150
        assert kwargs["token_decimals"] == 6
        assert kwargs["token_price_usd"] == 0.5
        return {
            "ledger_tx_count": 101,
            "ledger_unique_wallets": 45,
            "ledger_volume_usd": 1234.5,
            "from_block": 120,
            "to_block": 150,
        }

    monkeypatch.setattr("trading_fund.ledger.fetch_erc20_transfer_metrics", fake_fetch)

    snapshot = fetch_polymarket_ledger_snapshot(
        {
            "POLYMARKET_RPC_URL": "https://rpc.example",
            "POLYMARKET_TOKEN_CONTRACT": "0xabc",
            "POLYMARKET_FROM_BLOCK": "120",
            "POLYMARKET_TO_BLOCK": "150",
            "POLYMARKET_TOKEN_DECIMALS": "6",
            "POLYMARKET_TOKEN_PRICE_USD": "0.5",
        }
    )

    assert snapshot["ok"] is True
    assert snapshot["ledger_tx_count"] == 101
    assert snapshot["ledger_unique_wallets"] == 45
