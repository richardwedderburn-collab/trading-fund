from trading_fund.capital_ledger import add_transfer, load_transfers, summarize, transfers_snapshot


def test_load_transfers_missing_file_returns_empty(tmp_path):
    assert load_transfers(tmp_path / "missing.json") == []


def test_add_transfer_persists_and_returns_summary(tmp_path):
    path = tmp_path / "ledger.json"

    result = add_transfer(path, amount=3500, currency="USD", direction="deposit", source="crypto_com_app", note="app transfer")

    assert result["transfer"]["amount"] == 3500.0
    assert result["transfer"]["currency"] == "USD"
    assert result["transfer"]["direction"] == "deposit"
    assert result["transfer"]["source"] == "crypto_com_app"
    assert result["summary"]["by_currency"]["USD"]["total_deposits"] == 3500.0
    assert result["summary"]["by_currency"]["USD"]["net_contributed"] == 3500.0
    assert load_transfers(path) == result["transfers"]


def test_add_transfer_accumulates_multiple_entries_same_currency(tmp_path):
    path = tmp_path / "ledger.json"

    add_transfer(path, amount=1000, currency="USD", direction="deposit", source="crypto_com_app")
    result = add_transfer(path, amount=200, currency="USD", direction="withdrawal", source="crypto_com_exchange")

    assert result["summary"]["transfer_count"] == 2
    assert result["summary"]["by_currency"]["USD"]["total_deposits"] == 1000.0
    assert result["summary"]["by_currency"]["USD"]["total_withdrawals"] == 200.0
    assert result["summary"]["by_currency"]["USD"]["net_contributed"] == 800.0


def test_add_transfer_keeps_currencies_separate(tmp_path):
    path = tmp_path / "ledger.json"

    add_transfer(path, amount=100, currency="USD", direction="deposit")
    result = add_transfer(path, amount=316.91, currency="EUR", direction="deposit", source="crypto_com_app")

    assert result["summary"]["transfer_count"] == 2
    assert result["summary"]["by_currency"]["USD"]["net_contributed"] == 100.0
    assert result["summary"]["by_currency"]["EUR"]["net_contributed"] == 316.91


def test_add_transfer_rejects_negative_amount(tmp_path):
    path = tmp_path / "ledger.json"

    result = add_transfer(path, amount=-50, direction="deposit")

    assert result["transfer"]["amount"] == 0.0


def test_add_transfer_defaults_invalid_direction_and_source(tmp_path):
    path = tmp_path / "ledger.json"

    result = add_transfer(path, amount=100, direction="bogus", source="bogus")

    assert result["transfer"]["direction"] == "deposit"
    assert result["transfer"]["source"] == "other"


def test_summarize_empty_transfers():
    summary = summarize([])
    assert summary == {
        "transfer_count": 0,
        "by_currency": {},
    }


def test_transfers_snapshot_reads_existing_ledger(tmp_path):
    path = tmp_path / "ledger.json"
    add_transfer(path, amount=500, currency="EUR", direction="deposit")

    snapshot = transfers_snapshot(path)

    assert snapshot["summary"]["transfer_count"] == 1
    assert snapshot["summary"]["by_currency"]["EUR"]["total_deposits"] == 500.0
    assert len(snapshot["transfers"]) == 1
