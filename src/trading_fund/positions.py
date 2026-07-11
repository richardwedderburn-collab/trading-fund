from __future__ import annotations

from typing import Any, Dict, List


def build_position_cards(positions: List[Dict[str, Any]], market_prices: Dict[str, float]) -> List[Dict[str, Any]]:
    cards: List[Dict[str, Any]] = []
    for position in positions:
        symbol = position.get("symbol") or position.get("symbol")
        entry_price = float(position.get("entry_price", 0.0))
        qty = float(position.get("qty", 0))
        market_price = float(market_prices.get(symbol, entry_price))
        pnl = (market_price - entry_price) * qty
        cards.append(
            {
                "symbol": symbol,
                "side": position.get("side", "LONG"),
                "qty": qty,
                "entry_price": entry_price,
                "market_price": market_price,
                "pnl": pnl,
            }
        )
    return cards
