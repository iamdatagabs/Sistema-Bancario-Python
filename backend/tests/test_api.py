import asyncio

import pytest
from fastapi.testclient import TestClient

import main


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DB_PATH", tmp_path / "test.sqlite3")

    async def idle_market_loop():
        await asyncio.sleep(3600)

    monkeypatch.setattr(main.market, "run", idle_market_loop)
    main.market.latest = None
    main.market.last_error = None
    main.market.subscribers.clear()

    with TestClient(main.app) as test_client:
        yield test_client

    main.market.subscribers.clear()


def test_health_endpoint(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_demo_account_is_initialized(client):
    response = client.get("/api/accounts/demo")
    assert response.status_code == 200
    payload = response.json()
    assert payload["balance"] == 12500.0
    assert payload["transaction_count"] == 1


def test_deposit_updates_balance_and_statement(client):
    response = client.post("/api/transactions", json={
        "account_id": "demo",
        "type": "deposit",
        "amount": 250.50,
        "description": "Teste de depósito",
    })
    assert response.status_code == 201
    assert response.json()["balance"] == 12750.5

    account = client.get("/api/accounts/demo").json()
    assert account["balance"] == 12750.5
    assert account["total_deposits"] == 12750.5
    assert account["transactions"][0]["description"] == "Teste de depósito"


def test_withdraw_updates_balance(client):
    response = client.post("/api/transactions", json={
        "account_id": "demo",
        "type": "withdraw",
        "amount": 500,
    })
    assert response.status_code == 201
    assert response.json()["balance"] == 12000.0


def test_withdraw_rejects_insufficient_funds(client):
    response = client.post("/api/transactions", json={
        "account_id": "demo",
        "type": "withdraw",
        "amount": 20000,
    })
    assert response.status_code == 400
    assert "Saldo insuficiente" in response.json()["detail"]
    assert client.get("/api/accounts/demo").json()["balance"] == 12500.0


def test_invalid_transaction_type_is_rejected(client):
    response = client.post("/api/transactions", json={
        "account_id": "demo",
        "type": "transfer",
        "amount": 10,
    })
    assert response.status_code == 422


def test_unknown_account_returns_404(client):
    response = client.get("/api/accounts/missing")
    assert response.status_code == 404


def test_market_quotes_endpoint_returns_cached_provider_data(client):
    main.market.latest = {
        "provider": "brapi",
        "requested_at": "2026-01-01T00:00:00+00:00",
        "results": [
            {"symbol": "PETR4", "price": 10, "change_percent": 1.5},
            {"symbol": "VALE3", "price": 20, "change_percent": -0.5},
        ],
    }

    response = client.get("/api/market/quotes?tickers=PETR4,VALE3")
    assert response.status_code == 200
    assert [item["symbol"] for item in response.json()["results"]] == ["PETR4", "VALE3"]


def test_market_quotes_returns_503_before_first_snapshot(client):
    response = client.get("/api/market/quotes")
    assert response.status_code == 503
def test_market_quotes_rejects_invalid_symbols(client):
    response = client.get("/api/market/quotes?tickers=PETR4,%3Cscript%3E")
    assert response.status_code == 400


def test_market_broadcaster_delivers_latest_event():
    async def exercise():
        broadcaster = main.MarketBroadcaster()
        queue = await broadcaster.subscribe()
        payload = {"results": [{"symbol": "PETR4", "price": 35.0}]}

        broadcaster.publish("market", payload)

        message = await queue.get()
        assert message == {"event": "market", "data": payload}
        broadcaster.unsubscribe(queue)
        assert queue not in broadcaster.subscribers

    asyncio.run(exercise())
