from trading_fund.capital_ledger import add_transfer, load_transfers, summarize, transfers_snapshot


def test_load_transfers_missing_file_returns_empty(tmp_path):
    assert load_transfers(tmp_path / "missing.json") == []


def test_add_transfer_persists_and_returns_summary(tmp_path):
    path = tmp_path / "ledger.json"

    result = add_transfer(path, amount_usd=3500, direction="deposit", source="crypto_com_app", note="app transfer")

    assert result["transfer"]["amount_usd"] == 3500.0
    assert result["transfer"]["direction"] == "deposit"
    assert result["transfer"]["source"] == "crypto_com_app"
    assert result["summary"]["total_deposits_usd"] == 3500.0
    assert result["summary"]["net_contributed_usd"] == 3500.0
    assert load_transfers(path) == result["transfers"]


def test_add_transfer_accumulates_multiple_entries(tmp_path):
    path = tmp_path / "ledger.json"

    add_transfer(path, amount_usd=1000, direction="deposit", source="crypto_com_app")
    result = add_transfer(path, amount_usd=200, direction="withdrawal", source="crypto_com_exchange")

    assert result["summary"]["transfer_count"] == 2
    assert result["summary"]["total_deposits_usd"] == 1000.0
    assert result["summary"]["total_withdrawals_usd"] == 200.0
    assert result["summary"]["net_contributed_usd"] == 800.0


def test_add_transfer_rejects_negative_amount(tmp_path):
    path = tmp_path / "ledger.json"

    result = add_transfer(path, amount_usd=-50, direction="deposit")

    assert result["transfer"]["amount_usd"] == 0.0


def test_add_transfer_defaults_invalid_direction_and_source(tmp_path):
    path = tmp_path / "ledger.json"

    result = add_transfer(path, amount_usd=100, direction="bogus", source="bogus")

    assert result["transfer"]["direction"] == "deposit"
    assert result["transfer"]["source"] == "other"


def test_summarize_empty_transfers():
    summary = summarize([])
    assert summary == {
        "transfer_count": 0,
        "total_deposits_usd": 0.0,
        "total_withdrawals_usd": 0.0,
        "net_contributed_usd": 0.0,
    }


def test_transfers_snapshot_reads_existing_ledger(tmp_path):
    path = tmp_path / "ledger.json"
    add_transfer(path, amount_usd=500, direction="deposit")

    snapshot = transfers_snapshot(path)

    assert snapshot["summary"]["transfer_count"] == 1
    assert len(snapshot["transfers"]) == 1
