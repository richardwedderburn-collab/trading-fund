import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from trading_fund.consensus import ConsensusEngine, TradeSignal


class DummyAgent:
    def __init__(self, vote_value):
        self.vote_value = vote_value

    def vote(self, signal):
        return self.vote_value


def test_crypto_signal_passes_gates_and_executes_full_position():
    signal = TradeSignal(
        asset="PEPE",
        market_type="crypto",
        direction="LONG",
        raw_data={
            "pool_tvl": 50_000,
            "wallet_rank": 10,
            "wallet_age_days": 3,
        },
    )
    engine = ConsensusEngine(DummyAgent(1), DummyAgent(1), DummyAgent(1))

    result = engine.process_trade(signal, base_position_usd=1000.0)

    assert result["action"] == "EXECUTE_FULL"
    assert result["allocated_capital"] == 1000.0
    assert result["votes"] == [1, 1, 1]


def test_single_agreement_results_in_half_position():
    signal = TradeSignal(
        asset="BTC",
        market_type="crypto",
        direction="LONG",
        raw_data={
            "pool_tvl": 50_000,
            "wallet_rank": 10,
            "wallet_age_days": 3,
        },
    )
    engine = ConsensusEngine(DummyAgent(1), DummyAgent(0), DummyAgent(0))

    result = engine.process_trade(signal, base_position_usd=1000.0)

    assert result["action"] == "EXECUTE_HALF"
    assert result["allocated_capital"] == 500.0


def test_no_consensus_aborts_trade():
    signal = TradeSignal(
        asset="AAPL",
        market_type="stock",
        direction="LONG",
        raw_data={
            "average_volume_10d": 600_000,
        },
    )
    engine = ConsensusEngine(DummyAgent(0), DummyAgent(0), DummyAgent(0))

    result = engine.process_trade(signal, base_position_usd=1000.0)

    assert result["action"] == "ABORT_NO_CONSENSUS"
    assert result["allocated_capital"] == 0.0


def test_rejects_signal_when_entry_gates_fail():
    signal = TradeSignal(
        asset="ETH",
        market_type="crypto",
        direction="LONG",
        raw_data={
            "pool_tvl": 200_000,
            "wallet_rank": 200,
            "wallet_age_days": 10,
        },
    )
    engine = ConsensusEngine(DummyAgent(1), DummyAgent(1), DummyAgent(1))

    result = engine.process_trade(signal, base_position_usd=1000.0)

    assert result == "REJECTED_BY_GATES"


@pytest.mark.parametrize(
    ("raw_data", "expected"),
    [
        ({"pool_tvl": 50_000, "wallet_rank": 10, "wallet_age_days": 3}, True),
        ({"pool_tvl": 100_000, "wallet_rank": 10, "wallet_age_days": 3}, False),
        ({"pool_tvl": 50_000, "wallet_rank": 101, "wallet_age_days": 3}, False),
        ({"pool_tvl": 50_000, "wallet_rank": 10, "wallet_age_days": 7}, False),
    ],
)
def test_crypto_gates_require_all_subcriteria(raw_data, expected):
    signal = TradeSignal(
        asset="PEPE",
        market_type="crypto",
        direction="LONG",
        raw_data=raw_data,
    )
    engine = ConsensusEngine(DummyAgent(1), DummyAgent(1), DummyAgent(1))

    assert engine.evaluate_gates(signal) is expected


def test_stock_gate_requires_volume_above_threshold():
    signal = TradeSignal(
        asset="AAPL",
        market_type="stock",
        direction="LONG",
        raw_data={"average_volume_10d": 500_000},
    )
    engine = ConsensusEngine(DummyAgent(1), DummyAgent(1), DummyAgent(1))

    assert engine.evaluate_gates(signal) is False


def test_polymarket_gate_requires_strong_blockchain_ledger_activity():
    signal = TradeSignal(
        asset="YES",
        market_type="polymarket",
        direction="LONG",
        raw_data={
            "ledger_tx_count": 250,
            "ledger_volume_usd": 75_000,
            "ledger_unique_wallets": 80,
        },
    )
    engine = ConsensusEngine(DummyAgent(1), DummyAgent(1), DummyAgent(1))

    assert engine.evaluate_gates(signal) is True


def test_polymarket_gate_rejects_weak_blockchain_ledger_activity():
    signal = TradeSignal(
        asset="YES",
        market_type="polymarket",
        direction="LONG",
        raw_data={
            "ledger_tx_count": 10,
            "ledger_volume_usd": 5_000,
            "ledger_unique_wallets": 3,
        },
    )
    engine = ConsensusEngine(DummyAgent(1), DummyAgent(1), DummyAgent(1))

    assert engine.evaluate_gates(signal) is False


def test_polymarket_gate_requires_ledger_data():
    signal = TradeSignal(
        asset="YES",
        market_type="polymarket",
        direction="LONG",
        raw_data={"volume_24h": 100_000, "spread": 0.01},
    )
    engine = ConsensusEngine(DummyAgent(1), DummyAgent(1), DummyAgent(1))

    assert engine.evaluate_gates(signal) is False


def test_unknown_market_type_is_rejected_by_default():
    signal = TradeSignal(
        asset="XYZ",
        market_type="unknown",
        direction="LONG",
        raw_data={},
    )
    engine = ConsensusEngine(DummyAgent(1), DummyAgent(1), DummyAgent(1))

    assert engine.evaluate_gates(signal) is False


def test_strict_thresholds_allow_half_position_before_full_consensus():
    signal = TradeSignal(
        asset="BTC",
        market_type="crypto",
        direction="LONG",
        raw_data={
            "pool_tvl": 50_000,
            "wallet_rank": 10,
            "wallet_age_days": 3,
        },
    )
    engine = ConsensusEngine(
        DummyAgent(1),
        DummyAgent(1),
        DummyAgent(0),
        full_position_threshold=3,
        half_position_threshold=2,
    )

    result = engine.process_trade(signal, base_position_usd=1000.0)

    assert result["action"] == "EXECUTE_HALF"
    assert result["allocated_capital"] == 500.0
