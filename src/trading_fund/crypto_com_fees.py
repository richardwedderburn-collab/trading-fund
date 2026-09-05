from __future__ import annotations

from typing import Dict, List, Optional, TypedDict


class FeeTier(TypedDict):
    level: int
    min_30d_volume_usd: float
    maker_fee: float
    taker_fee: float
    maker_fee_with_cro: float
    taker_fee_with_cro: float


# Crypto.com Exchange spot VIP fee schedule (maker/taker rates as decimal
# fractions, e.g. 0.0025 == 0.250%). "With CRO balance" columns reflect the
# zero maker fee and 12% taker fee discount tiers.
VIP_FEE_TIERS: List[FeeTier] = [
    {
        "level": 1,
        "min_30d_volume_usd": 0,
        "maker_fee": 0.0025,
        "taker_fee": 0.0050,
        "maker_fee_with_cro": 0.0000,
        "taker_fee_with_cro": 0.0044,
    },
    {
        "level": 2,
        "min_30d_volume_usd": 10_000,
        "maker_fee": 0.0020,
        "taker_fee": 0.0040,
        "maker_fee_with_cro": 0.0000,
        "taker_fee_with_cro": 0.00352,
    },
    {
        "level": 3,
        "min_30d_volume_usd": 50_000,
        "maker_fee": 0.0015,
        "taker_fee": 0.0025,
        "maker_fee_with_cro": 0.0000,
        "taker_fee_with_cro": 0.0022,
    },
    {
        "level": 4,
        "min_30d_volume_usd": 250_000,
        "maker_fee": 0.0010,
        "taker_fee": 0.0020,
        "maker_fee_with_cro": 0.0000,
        "taker_fee_with_cro": 0.00176,
    },
    {
        "level": 5,
        "min_30d_volume_usd": 500_000,
        "maker_fee": 0.0008,
        "taker_fee": 0.0018,
        "maker_fee_with_cro": 0.0000,
        "taker_fee_with_cro": 0.001584,
    },
]


def resolve_fee_tier(volume_30d_usd: float) -> FeeTier:
    volume = max(float(volume_30d_usd or 0), 0.0)

    applicable = VIP_FEE_TIERS[0]
    for tier in VIP_FEE_TIERS:
        if volume >= tier["min_30d_volume_usd"]:
            applicable = tier
        else:
            break

    return applicable


def estimate_trade_fee(
    notional_usd: float,
    volume_30d_usd: float,
    is_maker: bool = True,
    use_cro_balance: bool = False,
) -> float:
    tier = resolve_fee_tier(volume_30d_usd)

    if use_cro_balance:
        rate = tier["maker_fee_with_cro"] if is_maker else tier["taker_fee_with_cro"]
    else:
        rate = tier["maker_fee"] if is_maker else tier["taker_fee"]

    return max(float(notional_usd or 0), 0.0) * rate


def fee_schedule_snapshot(volume_30d_usd: Optional[float] = None) -> Dict[str, object]:
    snapshot: Dict[str, object] = {"tiers": VIP_FEE_TIERS}

    if volume_30d_usd is not None:
        snapshot["resolved_tier"] = resolve_fee_tier(volume_30d_usd)
        snapshot["volume_30d_usd"] = max(float(volume_30d_usd or 0), 0.0)

    return snapshot
