# Nexus Banking — Banking & Market Intelligence

Releitura full-stack do desafio original **Sistema Bancário em Python (DIO)**. O projeto evolui depósito, saque e extrato para uma aplicação web com API REST, persistência e integração com cotações do mercado financeiro brasileiro.

> Projeto educacional e demonstrativo. Não é banco ou corretora, não movimenta dinheiro real e não oferece recomendação de investimento.

## Funcionalidades

- Dashboard bancário com saldo, entradas, saídas e histórico.
- Depósitos e saques com validação no backend.
- API REST com FastAPI e persistência SQLite.
- Cotações de ativos brasileiros pela brapi.
- Streaming de cotações via **Server-Sent Events (SSE)**.
- Uma consulta periódica do backend ao provedor alimenta todos os clientes conectados nesta instância.
- Reconexão automática do EventSource, eventos de erro e keep-alive.
- Frontend estático compatível com GitHub Pages.

## Arquitetura

```text
brapi ──polling (15s)──> FastAPI / MarketBroadcaster
                              │
                       SSE / EventSource
                              │
                         GitHub Pages
```

SSE é adequado para fluxo unidirecional servidor → navegador. Operações bancárias continuam usando HTTP REST. A atualização visual pode ser quase em tempo real, mas a cotação de origem depende da frequência, latência e limites da brapi. Não é feed tick-by-tick.

## Stack

| Camada | Tecnologia |
|---|---|
| Frontend | HTML, CSS, JavaScript |
| Gráficos | Chart.js |
| Backend | Python, FastAPI, Pydantic |
| Streaming | Server-Sent Events (SSE) |
| Persistência | SQLite |
| Mercado | brapi |
| Frontend hosting | GitHub Pages |
| Backend hosting | Render |

## Executar localmente

Requer Python 3.11+.

```bash
cd backend
python -m venv .venv
# Windows PowerShell: .venv\\Scripts\\Activate.ps1
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload
```

API: http://localhost:8000  
Documentação: http://localhost:8000/docs  
Health check: http://localhost:8000/health  
Stream SSE: http://localhost:8000/api/market/stream

Abra a raiz do projeto com Live Server ou outro servidor estático. Para apontar o frontend a outro backend, defina antes de carregar `app.js`:

```html
<script>window.NEXUS_API_URL = "https://sua-api.onrender.com";</script>
<script src="app.js"></script>
```

## Integração brapi

O backend lê `BRAPI_TOKEN` da variável de ambiente. Configure-a no ambiente de deploy se seu plano exigir token. Nunca exponha a credencial no JavaScript ou no GitHub Pages.

`MARKET_POLL_SECONDS` controla a periodicidade de consulta do backend (mínimo de 10 segundos; padrão 15). Todos os navegadores recebem o último snapshot pelo SSE. Keep-alive é enviado a cada 20 segundos sem atualização.

## Deploy

### Backend — Render

O `render.yaml` configura o serviço, health check e disco persistente para SQLite. Crie um Web Service conectado ao repositório e configure `BRAPI_TOKEN`, se necessário. Após deploy, valide `/health` e `/api/market/stream`.

Para este projeto educacional, o broadcaster mantém cache e conexões na memória de uma instância. Não habilite múltiplas instâncias sem mover o cache/pub-sub para Redis ou outro broker compartilhado. Para concorrência maior, migre SQLite para PostgreSQL.

### Frontend — GitHub Pages

1. Abra **Settings → Pages** no repositório.
2. Selecione **Deploy from a branch**, branch `main`, pasta `/ (root)`.
3. Defina `window.NEXUS_API_URL` no HTML com a URL HTTPS do backend publicado.
4. Configure `FRONTEND_ORIGINS` no backend com a origem do GitHub Pages para restringir CORS.
5. Publique e teste o dashboard.

## Endpoints

| Método | Rota | Finalidade |
|---|---|---|
| GET | `/health` | Saúde da API |
| GET | `/api/accounts/{id}` | Saldo e extrato |
| POST | `/api/transactions` | Depósito/saque |
| GET | `/api/market/quotes` | Snapshot de cotações |
| GET | `/api/market/stream` | Stream SSE |

Exemplo de transação:

```json
{"account_id":"demo","type":"deposit","amount":250.00,"description":"Aporte demonstrativo"}
```

## Próximas evoluções

- Testes automatizados (pytest + TestClient) e CI.
- Autenticação JWT e autorização por conta.
- PostgreSQL + Alembic.
- Transferências entre contas e limites.
- Carteira de investimentos e séries históricas.
- Redis Pub/Sub para múltiplas instâncias.
- Observabilidade, rate limiting e auditoria.

## Licença

Verifique e preserve a licença aplicável ao código original antes de redistribuir.
