from trading_fund.crypto_com_fees import (
    estimate_trade_fee,
    fee_schedule_snapshot,
    resolve_fee_tier,
)


def test_resolve_fee_tier_level_1_below_threshold():
    tier = resolve_fee_tier(5_000)
    assert tier["level"] == 1
    assert tier["maker_fee"] == 0.0025
    assert tier["taker_fee"] == 0.0050


def test_resolve_fee_tier_exact_threshold_upgrades_level():
    tier = resolve_fee_tier(50_000)
    assert tier["level"] == 3


def test_resolve_fee_tier_top_level_for_large_volume():
    tier = resolve_fee_tier(10_000_000)
    assert tier["level"] == 5
    assert tier["maker_fee"] == 0.0008
    assert tier["taker_fee"] == 0.0018


def test_resolve_fee_tier_negative_volume_clamped_to_level_1():
    tier = resolve_fee_tier(-100)
    assert tier["level"] == 1


def test_estimate_trade_fee_maker_without_cro():
    fee = estimate_trade_fee(10_000, volume_30d_usd=0, is_maker=True, use_cro_balance=False)
    assert fee == 25.0


def test_estimate_trade_fee_taker_with_cro_balance():
    fee = estimate_trade_fee(10_000, volume_30d_usd=0, is_maker=False, use_cro_balance=True)
    assert round(fee, 2) == 44.0


def test_estimate_trade_fee_maker_with_cro_balance_is_zero():
    fee = estimate_trade_fee(10_000, volume_30d_usd=250_000, is_maker=True, use_cro_balance=True)
    assert fee == 0.0


def test_fee_schedule_snapshot_includes_all_tiers():
    snapshot = fee_schedule_snapshot()
    assert len(snapshot["tiers"]) == 5
    assert "resolved_tier" not in snapshot


def test_fee_schedule_snapshot_resolves_tier_when_volume_given():
    snapshot = fee_schedule_snapshot(50_000)
    assert snapshot["resolved_tier"]["level"] == 3
    assert snapshot["volume_30d_usd"] == 50_000
