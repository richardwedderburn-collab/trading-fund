from trading_fund.alpaca_execute import execute_alpaca_strategy


def test_execute_alpaca_strategy_respects_position_and_risk_caps(monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("ALPACA_API_KEY=test\nALPACA_API_SECRET=secret\n", encoding="utf-8")

    def fake_request(method, url, headers, payload=None):
        if url.endswith("/v2/account"):
            return {"equity": "100000"}
        if url.endswith("/v2/positions"):
            return [{"symbol": "AAPL"}]
        if "data.alpaca.markets" in url:
            bars = {}
            for symbol in ["AAPL", "MSFT", "NVDA", "TSLA", "AMD", "AMZN"]:
                series = []
                for i in range(30):
                    series.append({"t": f"2026-01-{i+1:02d}T00:00:00Z", "c": 100 + i, "v": 1_000_000})
                bars[symbol] = series
            return {"bars": bars}
        if url.endswith("/v2/orders"):
            return {"id": "order-1", "status": "accepted"}
        raise AssertionError(url)

    monkeypatch.setattr("trading_fund.alpaca_execute._request_json", fake_request)

    result = execute_alpaca_strategy(
        symbols=["AAPL", "MSFT", "NVDA", "TSLA", "AMD", "AMZN"],
        env_path=env_file,
        max_new_positions=5,
        max_risk_pct=0.05,
        execute_orders=False,
    )

    assert result["risk_budget_usd"] == 5000.0
    assert len(result["selected_orders"]) <= 5
    assert result["spent_usd"] <= 5000.0
    assert all(order["symbol"] != "AAPL" for order in result["selected_orders"])


def test_execute_mode_places_orders(monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("ALPACA_API_KEY=test\nALPACA_API_SECRET=secret\n", encoding="utf-8")

    order_calls = []

    def fake_request(method, url, headers, payload=None):
        if url.endswith("/v2/account"):
            return {"equity": "100000"}
        if url.endswith("/v2/positions"):
            return []
        if "data.alpaca.markets" in url:
            bars = {}
            for symbol in ["MSFT", "NVDA"]:
                series = []
                for i in range(30):
                    series.append({"t": f"2026-01-{i+1:02d}T00:00:00Z", "c": 100 + i, "v": 1_000_000})
                bars[symbol] = series
            return {"bars": bars}
        if url.endswith("/v2/orders"):
            order_calls.append(payload)
            return {"id": f"order-{len(order_calls)}", "status": "accepted"}
        raise AssertionError(url)

    monkeypatch.setattr("trading_fund.alpaca_execute._request_json", fake_request)

    result = execute_alpaca_strategy(
        symbols=["MSFT", "NVDA"],
        env_path=env_file,
        max_new_positions=5,
        max_risk_pct=0.05,
        execute_orders=True,
    )

    assert len(result["placed_orders"]) == len(result["selected_orders"])
    assert len(order_calls) == len(result["placed_orders"]) + len(result["placed_trailing_stops"])


def test_execute_mode_adds_trailing_stop_for_new_positions(monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("ALPACA_API_KEY=test\nALPACA_API_SECRET=secret\n", encoding="utf-8")

    buy_calls = []
    trailing_calls = []

    def fake_request(method, url, headers, payload=None):
        if url.endswith("/v2/account"):
            return {"equity": "100000"}
        if url.endswith("/v2/positions"):
            return []
        if "/v2/orders?status=open" in url:
            return []
        if "data.alpaca.markets" in url:
            bars = {}
            for symbol in ["MSFT"]:
                series = []
                for i in range(30):
                    series.append({"t": f"2026-01-{i+1:02d}T00:00:00Z", "c": 100 + i, "v": 1_000_000})
                bars[symbol] = series
            return {"bars": bars}
        if url.endswith("/v2/orders"):
            if payload.get("type") == "trailing_stop":
                trailing_calls.append(payload)
                return {"id": "trail-1", "status": "accepted"}
            buy_calls.append(payload)
            return {"id": "order-1", "status": "accepted"}
        raise AssertionError(url)

    monkeypatch.setattr("trading_fund.alpaca_execute._request_json", fake_request)

    result = execute_alpaca_strategy(
        symbols=["MSFT"],
        env_path=env_file,
        max_new_positions=1,
        max_risk_pct=0.05,
        trailing_stop_pct=0.03,
        execute_orders=True,
    )

    assert len(buy_calls) == 1
    assert len(trailing_calls) == 1
    payload = trailing_calls[0]
    assert payload.get("side") == "sell"
    assert payload.get("type") == "trailing_stop"
    assert payload.get("trail_percent") == "3.0"
    assert result["trailing_stop_pct"] == 0.03
    assert len(result["placed_trailing_stops"]) == 1


def test_execute_mode_applies_trailing_stop_to_existing_positions(monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("ALPACA_API_KEY=test\nALPACA_API_SECRET=secret\n", encoding="utf-8")

    trailing_calls = []

    def fake_request(method, url, headers, payload=None):
        if url.endswith("/v2/account"):
            return {"equity": "100000"}
        if url.endswith("/v2/positions"):
            return [{"symbol": "AAPL", "qty": "10"}]
        if "/v2/orders?status=open" in url:
            return []
        if "data.alpaca.markets" in url:
            return {"bars": {}}
        if url.endswith("/v2/orders"):
            trailing_calls.append(payload)
            return {"id": "trail-1", "status": "accepted"}
        raise AssertionError(url)

    monkeypatch.setattr("trading_fund.alpaca_execute._request_json", fake_request)

    result = execute_alpaca_strategy(
        symbols=[],
        env_path=env_file,
        max_new_positions=1,
        max_risk_pct=0.05,
        trailing_stop_pct=0.03,
        execute_orders=True,
    )

    assert len(trailing_calls) == 1
    payload = trailing_calls[0]
    assert payload.get("symbol") == "AAPL"
    assert payload.get("side") == "sell"
    assert payload.get("type") == "trailing_stop"
    assert len(result["existing_trailing_stop_plan"]) == 1


def test_execute_mode_skips_existing_symbol_with_open_trailing_stop(monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("ALPACA_API_KEY=test\nALPACA_API_SECRET=secret\n", encoding="utf-8")

    order_calls = []

    def fake_request(method, url, headers, payload=None):
        if url.endswith("/v2/account"):
            return {"equity": "100000"}
        if url.endswith("/v2/positions"):
            return [{"symbol": "AAPL", "qty": "10"}]
        if "/v2/orders?status=open" in url:
            return [{"symbol": "AAPL", "side": "sell", "type": "trailing_stop"}]
        if "data.alpaca.markets" in url:
            return {"bars": {}}
        if url.endswith("/v2/orders"):
            order_calls.append(payload)
            return {"id": "should-not-happen", "status": "accepted"}
        raise AssertionError(url)

    monkeypatch.setattr("trading_fund.alpaca_execute._request_json", fake_request)

    result = execute_alpaca_strategy(
        symbols=[],
        env_path=env_file,
        max_new_positions=1,
        max_risk_pct=0.05,
        trailing_stop_pct=0.03,
        execute_orders=True,
    )

    assert len(order_calls) == 0
    assert result["existing_trailing_stop_plan"][0]["already_open"] is True


def test_execute_mode_cleans_up_residual_dust_after_fallback(monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("ALPACA_API_KEY=test\nALPACA_API_SECRET=secret\n", encoding="utf-8")

    trailing_calls = []
    cleanup_calls = []

    def fake_request(method, url, headers, payload=None):
        if url.endswith("/v2/account"):
            return {"equity": "100000"}
        if url.endswith("/v2/positions"):
            return [{"symbol": "AMD", "qty": "1.806437"}]
        if "/v2/orders?status=open" in url:
            return []
        if "data.alpaca.markets" in url:
            return {"bars": {}}
        if url.endswith("/v2/orders"):
            if payload.get("type") == "trailing_stop":
                trailing_calls.append(payload)
                qty = float(payload.get("qty", "0"))
                if abs(qty - 1.806437) < 1e-6:
                    raise Exception("HTTP Error 422: Unprocessable Entity")
                return {"id": "trail-fallback", "status": "accepted"}
            cleanup_calls.append(payload)
            return {"id": "cleanup-1", "status": "accepted"}
        raise AssertionError(url)

    monkeypatch.setattr("trading_fund.alpaca_execute._request_json", fake_request)

    result = execute_alpaca_strategy(
        symbols=[],
        env_path=env_file,
        max_new_positions=0,
        trailing_stop_pct=0.03,
        enable_dust_cleanup=True,
        dust_cleanup_min_qty=0.0001,
        execute_orders=True,
    )

    assert len(trailing_calls) == 2
    assert trailing_calls[1].get("qty") == "1.0"
    assert len(cleanup_calls) == 1
    assert cleanup_calls[0].get("type") == "market"
    assert cleanup_calls[0].get("qty") == "0.806437"
    assert len(result["dust_cleanup_orders"]) == 1


def test_execute_strategy_skips_highly_correlated_candidate_when_limit_exceeded(monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("ALPACA_API_KEY=test\nALPACA_API_SECRET=secret\n", encoding="utf-8")

    def fake_request(method, url, headers, payload=None):
        if url.endswith("/v2/account"):
            return {"equity": "100000"}
        if url.endswith("/v2/positions"):
            return [{"symbol": "AAPL"}]
        if "/v2/orders?status=open" in url:
            return []
        if "data.alpaca.markets" in url:
            bars = {}
            for symbol in ["AAPL", "MSFT", "NVDA"]:
                series = []
                for i in range(30):
                    series.append({"t": f"2026-01-{i+1:02d}T00:00:00Z", "c": 100 + i, "v": 1_000_000})
                bars[symbol] = series
            return {"bars": bars}
        raise AssertionError(url)

    monkeypatch.setattr("trading_fund.alpaca_execute._request_json", fake_request)

    result = execute_alpaca_strategy(
        symbols=["AAPL", "MSFT", "NVDA"],
        env_path=env_file,
        max_new_positions=5,
        max_risk_pct=0.05,
        correlation_soft_limit=0.75,
        correlation_hard_limit=0.9,
        execute_orders=False,
    )

    assert len(result["skipped_by_exposure"]) >= 1
    assert all(item["reason"] == "correlation_exceeds_hard_limit" for item in result["skipped_by_exposure"])


def test_auto_slots_mode_uses_candidate_pool_when_max_new_positions_zero(monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("ALPACA_API_KEY=test\nALPACA_API_SECRET=secret\n", encoding="utf-8")

    def fake_request(method, url, headers, payload=None):
        if url.endswith("/v2/account"):
            return {"equity": "100000"}
        if url.endswith("/v2/positions"):
            return []
        if "/v2/orders?status=open" in url:
            return []
        if "data.alpaca.markets" in url:
            bars = {}
            for symbol in ["MSFT", "NVDA", "TSLA"]:
                series = []
                for i in range(30):
                    series.append({"t": f"2026-01-{i+1:02d}T00:00:00Z", "c": 100 + i, "v": 1_000_000})
                bars[symbol] = series
            return {"bars": bars}
        raise AssertionError(url)

    monkeypatch.setattr("trading_fund.alpaca_execute._request_json", fake_request)

    result = execute_alpaca_strategy(
        symbols=["MSFT", "NVDA", "TSLA"],
        env_path=env_file,
        max_new_positions=0,
        max_risk_pct=0.05,
        execute_orders=False,
    )

    assert result["max_new_positions"] == 0
    assert result["auto_slots"] == 3
    assert result["effective_new_position_slots"] == 3


def test_rebalance_sell_plan_generated_for_weak_existing_position(monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("ALPACA_API_KEY=test\nALPACA_API_SECRET=secret\n", encoding="utf-8")

    def fake_request(method, url, headers, payload=None):
        if url.endswith("/v2/account"):
            return {"equity": "100000"}
        if url.endswith("/v2/positions"):
            return [{"symbol": "AAPL", "qty": "5"}]
        if "/v2/orders?status=open" in url:
            return []
        if "data.alpaca.markets" in url:
            # Flat/down bars produce weak signal and should trigger strategy exit planning.
            bars = {
                "AAPL": [{"t": f"2026-01-{i+1:02d}T00:00:00Z", "c": 100 - (i * 0.2), "v": 1_000_000} for i in range(30)]
            }
            return {"bars": bars}
        raise AssertionError(url)

    monkeypatch.setattr("trading_fund.alpaca_execute._request_json", fake_request)

    result = execute_alpaca_strategy(
        symbols=["AAPL"],
        env_path=env_file,
        max_new_positions=0,
        max_risk_pct=0.05,
        execute_orders=False,
    )

    assert len(result["rebalance_sell_plan"]) >= 1
    assert result["rebalance_sell_plan"][0]["symbol"] == "AAPL"
    assert result["rebalance_sell_plan"][0]["side"] == "sell"
