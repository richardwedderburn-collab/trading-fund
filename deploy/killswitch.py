import os
import sys


def enforce_killswitch(drawdown_pct: float, threshold_pct: float) -> bool:
    if drawdown_pct >= threshold_pct:
        os.environ["TRADING_KILLSWITCH_ACTIVE"] = "true"
        print("Killswitch activated")
        return True
    return False


if __name__ == "__main__":
    threshold = float(os.environ.get("KILLSWITCH_THRESHOLD_PCT", "10"))
    drawdown = float(sys.argv[1]) if len(sys.argv) > 1 else 0.0
    enforce_killswitch(drawdown, threshold)
