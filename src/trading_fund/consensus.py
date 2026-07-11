from __future__ import annotations

import dataclasses
import math
from typing import Any, Dict, List


@dataclasses.dataclass
class TradeSignal:
    asset: str
    market_type: str  # 'crypto', 'stock', 'polymarket'
    direction: str  # 'LONG', 'SHORT'
    raw_data: Dict[str, Any]


class ConsensusEngine:
    def __init__(
        self,
        *agents,
        full_position_threshold: int | None = None,
        half_position_threshold: int | None = None,
    ):
        if len(agents) == 1 and isinstance(agents[0], (list, tuple)):
            self.agents = list(agents[0])
        else:
            self.agents = list(agents)

        if not self.agents:
            raise ValueError("ConsensusEngine requires at least one agent")

        default_full = max(2, int(math.ceil(len(self.agents) * 0.6)))
        self.full_position_threshold = int(full_position_threshold or default_full)
        self.half_position_threshold = int(
            half_position_threshold if half_position_threshold is not None else max(1, self.full_position_threshold - 1)
        )

    def _collect_votes(self, signal: TradeSignal) -> List[int]:
        return [int(bool(agent.vote(signal))) for agent in self.agents]

    def _collect_size_multiplier(self, signal: TradeSignal) -> float:
        multipliers: List[float] = []
        for agent in self.agents:
            if hasattr(agent, "position_size_multiplier"):
                raw_value = agent.position_size_multiplier(signal)
                try:
                    multiplier = float(raw_value)
                except (TypeError, ValueError):
                    multiplier = 1.0
                multipliers.append(max(0.0, min(1.0, multiplier)))
        return min(multipliers) if multipliers else 1.0

    def evaluate_gates(self, signal: TradeSignal) -> bool:
        """
        Decision Gate: Hard-coded technical filters that a signal must pass
        BEFORE burning LLM tokens or spinning up heavy agent processing.
        """
        data = signal.raw_data

        if signal.market_type == "crypto":
            is_low_liq = data.get("pool_tvl", 0) < 100_000
            is_smart_wallet = data.get("wallet_rank", 101) <= 100
            is_fresh = data.get("wallet_age_days", 99) < 7
            return is_low_liq and is_smart_wallet and is_fresh

        if signal.market_type == "polymarket":
            tx_count = data.get(
                "ledger_tx_count",
                data.get("blockchain_tx_count", data.get("onchain_tx_count", 0)),
            )
            volume_usd = data.get(
                "ledger_volume_usd",
                data.get("blockchain_volume_usd", data.get("onchain_volume_usd", 0)),
            )
            unique_wallets = data.get(
                "ledger_unique_wallets",
                data.get("blockchain_unique_wallets", data.get("onchain_unique_wallets", 0)),
            )

            return (
                int(tx_count or 0) >= 100
                and float(volume_usd or 0) >= 50_000
                and int(unique_wallets or 0) >= 20
            )

        if signal.market_type == "stock":
            return data.get("average_volume_10d", 0) > 500_000

        return False

    def process_trade(self, signal: TradeSignal, base_position_usd: float):
        if not self.evaluate_gates(signal):
            return "REJECTED_BY_GATES"

        votes = self._collect_votes(signal)
        consensus_score = sum(votes)
        size_multiplier = self._collect_size_multiplier(signal)

        if consensus_score >= self.full_position_threshold:
            final_position = base_position_usd * size_multiplier
            action = "EXECUTE_FULL"
        elif consensus_score >= self.half_position_threshold:
            final_position = base_position_usd * 0.5 * size_multiplier
            action = "EXECUTE_HALF"
        else:
            final_position = 0.0
            action = "ABORT_NO_CONSENSUS"

        return {
            "action": action,
            "allocated_capital": final_position,
            "votes": votes,
            "consensus_score": consensus_score,
            "size_multiplier": size_multiplier,
        }
