import http.client
import json
import threading

import server


def _request_json(path: str):
    httpd = server.ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    port = httpd.server_port
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        conn.request("GET", path)
        response = conn.getresponse()
        body = response.read().decode("utf-8")
        conn.close()
        return response.status, json.loads(body)
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=2)


def test_autotrade_status_route_returns_state(monkeypatch):
    monkeypatch.setattr(
        server,
        "load_env_file",
        lambda _: {
            "ALPACA_API_BASE_URL": "https://paper-api.alpaca.markets",
            "AUTOTRADE_MULTI_OPERATOR": "false",
            "AUTOTRADE_LIVE_COOLDOWN_SECONDS": "90",
            "AUTOTRADE_LIVE_APPROVER_ROLES": "owner,admin",
        },
    )
    monkeypatch.setattr(server, "maybe_run_autotrade_due", lambda *_: {"ok": True, "skipped": "disabled", "state": {"enabled": False}})
    monkeypatch.setattr(server, "load_autotrade_state", lambda *_: {"enabled": False, "mode": "dry_run"})

    status, payload = _request_json("/api/autotrade/status")

    assert status == 200
    assert payload["ok"] is True
    assert payload["state"]["mode"] == "dry_run"
    assert payload["due_result"]["skipped"] == "disabled"
    assert payload["security"]["cooldown_seconds"] == 90


def test_autotrade_toggle_route_updates_enabled(monkeypatch):
    monkeypatch.setattr(server, "update_autotrade_settings", lambda *_: {"enabled": True, "mode": "dry_run"})

    status, payload = _request_json("/api/autotrade/toggle?enabled=true")

    assert status == 200
    assert payload["ok"] is True
    assert payload["state"]["enabled"] is True


def test_autotrade_config_route_persists_symbols_and_mode(monkeypatch):
    def _fake_update(_path, updates):
        assert updates["mode"] == "live"
        assert updates["interval_seconds"] == 600
        assert updates["symbols"] == "AAPL,MSFT"
        return {
            "enabled": False,
            "mode": "live",
            "interval_seconds": 600,
            "symbols": ["AAPL", "MSFT"],
        }

    monkeypatch.setattr(server, "update_autotrade_settings", _fake_update)

    status, payload = _request_json("/api/autotrade/config?mode=live&interval_seconds=600&symbols=AAPL,MSFT")

    assert status == 200
    assert payload["ok"] is True
    assert payload["state"]["mode"] == "live"
    assert payload["state"]["interval_seconds"] == 600


def test_autotrade_run_once_route_respects_execute_flag(monkeypatch):
    called = {"force_execute": None}

    def _fake_run_cycle(*, state_path, env_path, reason, force_execute):
        called["force_execute"] = force_execute
        return {"ok": True, "state": {"last_mode": "execute"}}

    monkeypatch.setattr(
        server,
        "load_env_file",
        lambda *_: {
            "AUTOTRADE_MULTI_OPERATOR": "false",
            "AUTOTRADE_LIVE_COOLDOWN_SECONDS": "90",
            "AUTOTRADE_LIVE_APPROVER_ROLES": "owner,admin",
        },
    )
    monkeypatch.setattr(server, "load_autotrade_state", lambda *_: {"last_mode": "dry_run", "last_run_at": ""})
    monkeypatch.setattr(server, "_append_autotrade_audit", lambda *_: None)
    monkeypatch.setattr(server, "run_autotrade_cycle", _fake_run_cycle)

    status, payload = _request_json("/api/autotrade/run-once?execute=true")

    assert status == 200
    assert payload["ok"] is True
    assert payload["state"]["last_mode"] == "execute"
    assert called["force_execute"] is True


def test_autotrade_run_once_rejects_when_live_cooldown_active(monkeypatch):
    monkeypatch.setattr(
        server,
        "load_env_file",
        lambda *_: {
            "AUTOTRADE_MULTI_OPERATOR": "false",
            "AUTOTRADE_LIVE_COOLDOWN_SECONDS": "90",
            "AUTOTRADE_LIVE_APPROVER_ROLES": "owner,admin",
        },
    )
    monkeypatch.setattr(
        server,
        "load_autotrade_state",
        lambda *_: {
            "last_mode": "execute",
            "last_run_at": "2999-01-01T00:00:00Z",
            "last_result": {},
        },
    )
    monkeypatch.setattr(server, "_append_autotrade_audit", lambda *_: None)

    status, payload = _request_json("/api/autotrade/run-once?execute=true")

    assert status == 429
    assert payload["ok"] is False
    assert payload["reason"] == "live_cooldown_active"


def test_autotrade_run_once_rejects_when_role_not_approved(monkeypatch):
    monkeypatch.setattr(
        server,
        "load_env_file",
        lambda *_: {
            "AUTOTRADE_MULTI_OPERATOR": "true",
            "AUTOTRADE_LIVE_COOLDOWN_SECONDS": "0",
            "AUTOTRADE_LIVE_APPROVER_ROLES": "owner,admin",
        },
    )
    monkeypatch.setattr(server, "load_autotrade_state", lambda *_: {"last_mode": "dry_run", "last_run_at": ""})
    monkeypatch.setattr(server, "_append_autotrade_audit", lambda *_: None)

    status, payload = _request_json("/api/autotrade/run-once?execute=true&operator_name=alice&operator_role=trader")

    assert status == 403
    assert payload["ok"] is False
    assert payload["reason"] == "live_approval_required"


def test_autotrade_audit_route_returns_events(monkeypatch):
    monkeypatch.setattr(server, "_read_autotrade_audit", lambda limit=100: [{"event": "manual_run_once", "ok": True}])

    status, payload = _request_json("/api/autotrade/audit?limit=25")

    assert status == 200
    assert payload["ok"] is True
    assert payload["count"] == 1
    assert payload["events"][0]["event"] == "manual_run_once"
