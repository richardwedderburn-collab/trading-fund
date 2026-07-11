from pathlib import Path

from trading_fund.positions import build_position_cards


def test_build_position_cards_uses_live_price_data():
    positions = [
        {"symbol": "AAPL", "side": "LONG", "qty": 10, "entry_price": 100.0},
    ]

    cards = build_position_cards(positions, {"AAPL": 102.5})

    assert cards[0]["market_price"] == 102.5
    assert cards[0]["pnl"] == 25.0
