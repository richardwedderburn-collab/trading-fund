import datetime as dt
from pathlib import Path

from trading_fund.backtest import (
    export_backtest_csv,
    format_backtest_report,
    run_five_year_backtest,
)


def _make_bars(days=45, start_price=100.0, daily_step=0.4, volume=800_000):
    bars = []
    now = dt.datetime(2025, 1, 1, 0, 0, 0)
    for idx in range(days):
        close = start_price + (daily_step * idx)
        bars.append(
            {
                "t": (now + dt.timedelta(days=idx)).isoformat() + "Z",
                "c": close,
                "v": volume,
            }
        )
    return bars


def test_run_five_year_backtest_produces_gateway_analysis(monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("ALPACA_API_KEY=test\nALPACA_API_SECRET=secret\n", encoding="utf-8")

    def fake_fetch(**kwargs):
        assert kwargs["api_key"] == "test"
        assert kwargs["api_secret"] == "secret"
        return {
            "AAPL": _make_bars(),
            "MSFT": _make_bars(start_price=120.0, daily_step=0.3),
        }

    monkeypatch.setattr("trading_fund.backtest.fetch_alpaca_bars", fake_fetch)

    result = run_five_year_backtest(
        symbols=["AAPL", "MSFT"],
        env_path=env_file,
        end_date=dt.date(2025, 12, 31),
        base_position_usd=1000.0,
    )

    assert result.trades > 0
    assert result.best_gateway_min_volume in {250000, 500000, 750000, 1000000}
    assert len(result.gateway_sensitivity) == 4
    assert any(item["trades"] > 0 for item in result.gateway_sensitivity)
    assert result.max_drawdown_usd >= 0
    assert isinstance(result.sharpe_ratio, float)
    assert isinstance(result.max_loss_trade_usd, float)
    assert len(result.per_symbol_gateway) == 2
    assert all(item["symbol"] in {"AAPL", "MSFT"} for item in result.per_symbol_gateway)
    assert len(result.trade_rows) > 0
    assert isinstance(result.drift_score, float)
    assert isinstance(result.drift_warning, bool)
    assert isinstance(result.drift_monitor, list)
    assert result.walk_forward_enabled is False
    assert result.in_sample_trades == result.trades
    assert result.oos_vs_insample_pnl_ratio == 1.0


def test_export_backtest_csv_writes_expected_files(monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("ALPACA_API_KEY=test\nALPACA_API_SECRET=secret\n", encoding="utf-8")

    def fake_fetch(**kwargs):
        return {
            "AAPL": _make_bars(),
        }

    monkeypatch.setattr("trading_fund.backtest.fetch_alpaca_bars", fake_fetch)

    result = run_five_year_backtest(
        symbols=["AAPL"],
        env_path=env_file,
        end_date=dt.date(2025, 12, 31),
        base_position_usd=1000.0,
    )

    export_dir = tmp_path / "exports"
    files = export_backtest_csv(result, export_dir)

    assert Path(files["summary"]).exists()
    assert Path(files["gateway_sensitivity"]).exists()
    assert Path(files["per_symbol_gateway"]).exists()
    assert Path(files["walk_forward_folds"]).exists()
    assert Path(files["drift_monitor"]).exists()
    assert Path(files["trades"]).exists()


def test_walk_forward_mode_produces_folds(monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("ALPACA_API_KEY=test\nALPACA_API_SECRET=secret\n", encoding="utf-8")

    def fake_fetch(**kwargs):
        return {
            "AAPL": _make_bars(days=1200, start_price=100.0, daily_step=0.1),
            "MSFT": _make_bars(days=1200, start_price=200.0, daily_step=0.08),
        }

    monkeypatch.setattr("trading_fund.backtest.fetch_alpaca_bars", fake_fetch)

    result = run_five_year_backtest(
        symbols=["AAPL", "MSFT"],
        env_path=env_file,
        end_date=dt.date(2025, 12, 31),
        base_position_usd=1000.0,
        walk_forward=True,
        walk_forward_train_years=1,
        walk_forward_test_months=3,
    )

    assert result.walk_forward_enabled is True
    assert result.walk_forward_train_years == 1
    assert result.walk_forward_test_months == 3
    assert len(result.walk_forward_folds) > 0
    assert result.in_sample_trades >= result.trades
    assert isinstance(result.degradation_warning, bool)
    assert isinstance(result.degradation_message, str)
    assert isinstance(result.drift_message, str)


def test_format_backtest_report_contains_key_metrics():
    class StubResult:
        symbols = ["AAPL"]
        start_date = "2020-01-01"
        end_date = "2025-01-01"
        trades = 10
        win_rate = 0.6
        total_pnl_usd = 1234.5
        avg_pnl_per_trade = 123.45
        best_gateway_min_volume = 500000
        max_drawdown_usd = 456.78
        sharpe_ratio = 1.234
        max_loss_trade_usd = -98.7
        gateway_sensitivity = [
            {
                "min_volume_gate": 500000,
                "trades": 10,
                "win_rate": 0.6,
                "total_pnl_usd": 1234.5,
            }
        ]
        per_symbol_gateway = [
            {
                "symbol": "AAPL",
                "min_volume_gate": 500000,
                "trades": 10,
                "win_rate": 0.6,
                "total_pnl_usd": 1234.5,
            }
        ]
        trade_rows = []
        walk_forward_enabled = False
        walk_forward_train_years = 3
        walk_forward_test_months = 6
        walk_forward_folds = []
        in_sample_trades = 10
        in_sample_win_rate = 0.6
        in_sample_total_pnl_usd = 1234.5
        in_sample_avg_pnl_per_trade = 123.45
        oos_vs_insample_pnl_ratio = 1.0
        degradation_threshold = 0.35
        degradation_warning = False
        degradation_message = "ok"
        drift_score = 0.0
        drift_warning = False
        drift_message = "ok"
        drift_monitor = []

    output = format_backtest_report(StubResult())

    assert "Backtest Summary" in output
    assert "Best stock gateway volume floor" in output
    assert "min_volume=500,000" in output
    assert "Max drawdown" in output
    assert "Per-symbol best gateway" in output
    assert "Walk-forward mode" in output
    assert "Drift score" in output