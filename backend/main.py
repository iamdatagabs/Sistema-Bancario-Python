import asyncio
import json
import logging
import os
import sqlite3
from contextlib import asynccontextmanager, contextmanager, suppress
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Optional

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = Path(os.getenv("DATABASE_PATH", BASE_DIR / "nexus.db"))
logger = logging.getLogger("nexus.market")

BRAPI_BASE_URL = "https://brapi.dev/api"
BRAPI_TOKEN = os.getenv("BRAPI_TOKEN", "")
FRONTEND_ORIGINS = [origin.strip() for origin in os.getenv("FRONTEND_ORIGINS", "*").split(",")]
DEFAULT_TICKERS = ["PETR4", "VALE3", "ITUB4", "BBDC4", "BBAS3", "WEGE3"]
# Plano gratuito: 1 ticker por chamada, atualização ~30 min. Seis ativos = ~8.640 chamadas/mês.
MARKET_POLL_SECONDS = max(1800, int(os.getenv("MARKET_POLL_SECONDS", "1800")))


def utc_now():
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB_PATH, timeout=15)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def initialize_database():
    with connect() as db:
        db.execute("""CREATE TABLE IF NOT EXISTS accounts (
            id TEXT PRIMARY KEY, holder TEXT NOT NULL, balance_cents INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL)""")
        db.execute("""CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT, account_id TEXT NOT NULL,
            type TEXT NOT NULL CHECK(type IN ('deposit','withdraw')),
            amount_cents INTEGER NOT NULL, description TEXT, created_at TEXT NOT NULL,
            FOREIGN KEY(account_id) REFERENCES accounts(id))""")
        db.execute("INSERT OR IGNORE INTO accounts(id,holder,balance_cents,created_at) VALUES(?,?,?,?)",
                   ("demo", "Conta demonstrativa", 1250000, utc_now()))
        if db.execute("SELECT COUNT(*) FROM transactions WHERE account_id='demo'").fetchone()[0] == 0:
            db.execute("""INSERT INTO transactions(account_id,type,amount_cents,description,created_at)
                          VALUES(?,?,?,?,?)""",
                       ("demo", "deposit", 1250000, "Saldo inicial demonstrativo", utc_now()))


async def fetch_market_quotes(symbols):
    """Consulta cada ativo separadamente, compatível com o plano gratuito da brapi."""
    headers = {"User-Agent": "NexusBanking/1.0"}
    if BRAPI_TOKEN:
        headers["Authorization"] = f"Bearer {BRAPI_TOKEN}"

    quotes = []
    errors = []
    async with httpx.AsyncClient(timeout=12) as client:
        for symbol in symbols:
            try:
                response = await client.get(f"{BRAPI_BASE_URL}/quote/{symbol}", headers=headers)
                response.raise_for_status()
                payload = response.json()
                for result in payload.get("results", []):
                    item = result.get("data") or result
                    price = item.get("regularMarketPrice")
                    change = item.get("regularMarketChangePercent")
                    if price is None or change is None:
                        continue
                    quotes.append({
                        "symbol": item.get("symbol") or symbol,
                        "name": item.get("longName") or item.get("shortName") or symbol,
                        "price": price,
                        "change_percent": change,
                        "market_state": item.get("marketState") or "Cotação disponível",
                        "market_time": item.get("regularMarketTime"),
                    })
            except (httpx.HTTPError, ValueError) as exc:
                errors.append(exc)

    if not quotes and errors:
        raise errors[0]
    return {"provider": "brapi", "requested_at": utc_now(), "results": quotes}

class MarketBroadcaster:
    """Uma consulta ao provedor alimenta todos os clientes SSE desta instância."""
    def __init__(self):
        self.latest = None
        self.last_error = None
        self.subscribers = set()
        self.task = None

    def publish(self, event, payload):
        message = {"event": event, "data": payload}
        for queue in tuple(self.subscribers):
            if queue.full():
                with suppress(asyncio.QueueEmpty):
                    queue.get_nowait()
            with suppress(asyncio.QueueFull):
                queue.put_nowait(message)

    async def run(self):
        while True:
            try:
                self.latest = await fetch_market_quotes(DEFAULT_TICKERS)
                self.last_error = None
                logger.info("Snapshot brapi atualizado: %s/%s ativos.", len(self.latest["results"]), len(DEFAULT_TICKERS))
                self.publish("market", self.latest)
            except Exception as exc:
                self.last_error = str(exc)
                logger.warning("Falha ao atualizar snapshot brapi (%s).", type(exc).__name__)
                self.publish("market_error", {"message": "Provedor de cotações temporariamente indisponível.",
                                              "requested_at": utc_now()})
            await asyncio.sleep(MARKET_POLL_SECONDS)

    async def subscribe(self):
        queue = asyncio.Queue(maxsize=2)
        self.subscribers.add(queue)
        if self.latest:
            queue.put_nowait({"event": "market", "data": self.latest})
        elif self.last_error:
            queue.put_nowait({"event": "market_error", "data": {"message": "Aguardando conexão com o provedor."}})
        return queue

    def unsubscribe(self, queue):
        self.subscribers.discard(queue)


market = MarketBroadcaster()


@asynccontextmanager
async def lifespan(app: FastAPI):
    initialize_database()
    market.task = asyncio.create_task(market.run())
    yield
    if market.task:
        market.task.cancel()
        with suppress(asyncio.CancelledError):
            await market.task


app = FastAPI(title="Nexus Banking API", version="1.1.0",
              description="API bancária educacional com streaming de mercado via Server-Sent Events.",
              lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=FRONTEND_ORIGINS, allow_credentials=False,
                   allow_methods=["*"], allow_headers=["*"])


class TransactionInput(BaseModel):
    account_id: str = "demo"
    type: str
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    description: Optional[str] = Field(default=None, max_length=120)


@app.get("/")
def root():
    return {"name": "Nexus Banking API", "version": app.version, "docs": "/docs",
            "health": "/health", "market_stream": "/api/market/stream"}


@app.get("/health")
def health():
    return {"status": "ok", "timestamp": utc_now(), "market_stream": "enabled"}


@app.get("/api/accounts/{account_id}")
def get_account(account_id: str):
    with connect() as db:
        account = db.execute("SELECT * FROM accounts WHERE id=?", (account_id,)).fetchone()
        if not account:
            raise HTTPException(status_code=404, detail="Conta não encontrada.")
        transactions = db.execute("SELECT * FROM transactions WHERE account_id=? ORDER BY id DESC LIMIT 100",
                                  (account_id,)).fetchall()
        totals = db.execute("""SELECT
            COALESCE(SUM(CASE WHEN type='deposit' THEN amount_cents ELSE 0 END),0) deposits,
            COALESCE(SUM(CASE WHEN type='withdraw' THEN amount_cents ELSE 0 END),0) withdrawals,
            COUNT(*) total FROM transactions WHERE account_id=?""", (account_id,)).fetchone()
    return {
        "id": account["id"], "holder": account["holder"], "balance": account["balance_cents"] / 100,
        "total_deposits": totals["deposits"] / 100, "total_withdrawals": totals["withdrawals"] / 100,
        "transaction_count": totals["total"],
        "transactions": [{"id": t["id"], "type": t["type"], "amount": t["amount_cents"] / 100,
                          "description": t["description"], "created_at": t["created_at"]} for t in transactions]
    }


@app.post("/api/transactions", status_code=201)
def create_transaction(payload: TransactionInput):
    if payload.type not in ("deposit", "withdraw"):
        raise HTTPException(status_code=422, detail="Tipo inválido. Use deposit ou withdraw.")
    try:
        cents = int((payload.amount * 100).quantize(Decimal("1")))
    except (InvalidOperation, ValueError):
        raise HTTPException(status_code=422, detail="Valor monetário inválido.")
    if cents <= 0:
        raise HTTPException(status_code=422, detail="O valor deve ser maior que zero.")
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        account = db.execute("SELECT * FROM accounts WHERE id=?", (payload.account_id,)).fetchone()
        if not account:
            raise HTTPException(status_code=404, detail="Conta não encontrada.")
        if payload.type == "withdraw" and cents > account["balance_cents"]:
            raise HTTPException(status_code=400, detail="Saldo insuficiente para realizar o saque.")
        new_balance = account["balance_cents"] + cents if payload.type == "deposit" else account["balance_cents"] - cents
        db.execute("UPDATE accounts SET balance_cents=? WHERE id=?", (new_balance, payload.account_id))
        cursor = db.execute("""INSERT INTO transactions(account_id,type,amount_cents,description,created_at)
                               VALUES(?,?,?,?,?)""",
                            (payload.account_id, payload.type, cents,
                             payload.description or ("Depósito" if payload.type == "deposit" else "Saque"), utc_now()))
        transaction_id = cursor.lastrowid
    return {"id": transaction_id, "message": "Transação registrada.", "balance": new_balance / 100}


@app.get("/api/market/quotes")
async def market_quotes(tickers: str = ",".join(DEFAULT_TICKERS)):
    """Entrega o último snapshot em cache; nunca consulta a brapi por requisição de cliente."""
    symbols = [symbol.strip().upper() for symbol in tickers.split(",") if symbol.strip()]
    if not symbols or len(symbols) > 20 or any(not symbol.replace(".", "").isalnum() for symbol in symbols):
        raise HTTPException(status_code=400, detail="Informe entre 1 e 20 tickers válidos.")
    if market.latest is None:
        raise HTTPException(status_code=503, detail="Cotações ainda não carregadas. Tente novamente em instantes.")

    by_symbol = {item.get("symbol"): item for item in market.latest.get("results", [])}
    return {
        **market.latest,
        "results": [by_symbol[symbol] for symbol in symbols if symbol in by_symbol],
    }


DASHBOARD_CACHE_SECONDS = 12 * 60 * 60


class IntelligenceCache:
    def __init__(self):
        self.payload = None
        self.expires_at = 0
        self.lock = asyncio.Lock()

    async def get(self):
        if self.payload is not None and asyncio.get_running_loop().time() < self.expires_at:
            return self.payload
        async with self.lock:
            if self.payload is not None and asyncio.get_running_loop().time() < self.expires_at:
                return self.payload
            async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
                fx_task = client.get(
                    "https://api.frankfurter.dev/v1/latest",
                    params={"base": "BRL", "symbols": "USD,EUR,JPY,GBP"},
                )
                ipca_task = client.get(
                    "https://api.bcb.gov.br/dados/serie/bcdata.sgs.433/dados/ultimos/1",
                    params={"formato": "json"},
                )
                news_task = client.get(
                    "https://api.gdeltproject.org/api/v2/doc/doc",
                    params={
                        "query": '(economia OR mercado OR inflação OR juros OR política) sourceCountry:BR sourcelang:por',
                        "mode": "ArtList", "format": "json", "maxrecords": 6,
                        "timespan": "12h", "sort": "DateDesc",
                    },
                )
                results = await asyncio.gather(fx_task, ipca_task, news_task, return_exceptions=True)

            exchange_rates = {"BRL": 1.0}
            exchange_date = None
            if not isinstance(results[0], Exception):
                try:
                    results[0].raise_for_status()
                    fx = results[0].json()
                    exchange_date = fx.get("date")
                    # Frankfurter returns units of foreign currency per BRL; invert for BRL per unit.
                    exchange_rates.update({
                        code: round(1 / float(rate), 6)
                        for code, rate in fx.get("rates", {}).items()
                        if float(rate) > 0
                    })
                except (httpx.HTTPError, ValueError, TypeError, ZeroDivisionError):
                    logger.warning("Não foi possível atualizar as taxas de câmbio.")

            economic_indicator = None
            if not isinstance(results[1], Exception):
                try:
                    results[1].raise_for_status()
                    rows = results[1].json()
                    if rows:
                        economic_indicator = {
                            "name": "IPCA mensal",
                            "period": rows[-1].get("data"),
                            "value": float(rows[-1].get("valor", "nan").replace(",", ".")),
                        }
                except (httpx.HTTPError, ValueError, TypeError):
                    logger.warning("Não foi possível atualizar o IPCA do Banco Central.")

            news = []
            if not isinstance(results[2], Exception):
                try:
                    results[2].raise_for_status()
                    payload = results[2].json()
                    for article in payload.get("articles", [])[:6]:
                        title = article.get("title")
                        url = article.get("url")
                        if title and url and url.startswith("http"):
                            news.append({
                                "title": title,
                                "url": url,
                                "source": article.get("domain") or article.get("source", {}).get("name") or "Notícia",
                                "published_at": article.get("seendate", ""),
                            })
                except (httpx.HTTPError, ValueError, TypeError):
                    logger.warning("Não foi possível atualizar o radar de notícias.")

            self.payload = {
                "updated_at": utc_now(),
                "cache_ttl_hours": 12,
                "exchange_date": exchange_date,
                "exchange_rates": exchange_rates,
                "economic_indicator": economic_indicator,
                "news": news,
            }
            self.expires_at = asyncio.get_running_loop().time() + DASHBOARD_CACHE_SECONDS
            return self.payload


intelligence = IntelligenceCache()


@app.get("/api/dashboard")
async def dashboard_intelligence():
    """Câmbio, IPCA e notícias agregados em cache por 12 horas."""
    return await intelligence.get()

@app.get("/api/market/stream")
async def market_stream(request: Request):
    """Fluxo SSE: event: market\ndata: {...}\n\n. Reconexão gerenciada pelo EventSource."""
    queue = await market.subscribe()

    async def event_generator():
        try:
            yield "retry: 5000\n\n"
            yield f": nexus-stream-connected {utc_now()}\n\n"
            while not await request.is_disconnected():
                try:
                    message = await asyncio.wait_for(queue.get(), timeout=20)
                    data = json.dumps(message["data"], ensure_ascii=False, separators=(",", ":"))
                    yield f"event: {message['event']}\ndata: {data}\n\n"
                except asyncio.TimeoutError:
                    yield f": keep-alive {utc_now()}\n\n"
        finally:
            market.unsubscribe(queue)

    return StreamingResponse(event_generator(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache, no-transform",
                                      "Connection": "keep-alive", "X-Accel-Buffering": "no"})
