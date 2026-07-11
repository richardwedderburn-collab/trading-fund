from pathlib import Path

from trading_fund.config import (
    get_connection_status,
    load_env_file,
    resolve_llm_provider,
)


def test_load_env_file_reads_values(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("COINBASE_API_KEY=test-key\nBINANCE_API_SECRET=secret\n", encoding="utf-8")

    values = load_env_file(env_file)

    assert values["COINBASE_API_KEY"] == "test-key"
    assert values["BINANCE_API_SECRET"] == "secret"


def test_get_connection_status_reports_missing_keys(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("COINBASE_API_KEY=\n", encoding="utf-8")

    status = get_connection_status("platform", env_file)

    assert status["ok"] is False
    assert status["reason"] == "missing_keys"


def test_resolve_llm_provider_prefers_ollama_when_configured(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("OLLAMA_HOST=http://127.0.0.1:11434\nOLLAMA_MODEL=llama3\n", encoding="utf-8")

    provider = resolve_llm_provider(env_file)

    assert provider["provider"] == "ollama"
    assert provider["model"] == "llama3"


def test_get_connection_status_accepts_alpaca_credentials(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("ALPACA_API_KEY=key\nALPACA_API_SECRET=secret\n", encoding="utf-8")

    status = get_connection_status("alpaca", env_file)

    assert status["ok"] is True
    assert status["reason"] == "ready"


def test_get_connection_status_accepts_crypto_com_credentials(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("CRYPTO_COM_API_KEY=key\nCRYPTO_COM_API_SECRET=secret\n", encoding="utf-8")

    status = get_connection_status("crypto", env_file)

    assert status["ok"] is True
    assert status["reason"] == "ready"


def test_load_env_file_parses_alpaca_pasted_values(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "https://paper-api.alpaca.markets/v2\nkey=PKWGRS5D2EWPXLBF6XWZ5IOKSC\nsecret key=abc123\n",
        encoding="utf-8",
    )

    values = load_env_file(env_file)

    assert values["ALPACA_API_KEY"] == "PKWGRS5D2EWPXLBF6XWZ5IOKSC"
    assert values["ALPACA_API_SECRET"] == "abc123"
