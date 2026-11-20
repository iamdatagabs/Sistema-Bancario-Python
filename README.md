# Nexus Banking — Banking & Market Intelligence

Releitura full-stack do desafio original **Sistema Bancário em Python (DIO)**. A aplicação combina operações bancárias demonstrativas, API REST, persistência e integração com cotações do mercado financeiro brasileiro.

> Projeto educacional. Não é banco ou corretora, não movimenta dinheiro real e não oferece recomendação de investimento.

## Funcionalidades

- Dashboard responsivo com saldo, entradas, saídas, histórico e gráfico.
- Depósitos e saques com validação no backend e valores monetários em centavos.
- API REST FastAPI + SQLite.
- Cotações de ativos brasileiros pela brapi.\n- Câmbio de BRL, USD, EUR, JPY e GBP por taxas de referência do Frankfurter.\n- Indicador mensal de inflação (IPCA/SGS) e radar de notícias de economia/política.\n- Cache de dados macroeconômicos e notícias por 12 horas.
- Server-Sent Events (SSE), reconexão automática, cache do último snapshot e keep-alive.
- Testes automatizados com pytest e pipeline GitHub Actions.

## Arquitetura

```text
brapi ── polling periódico ──> FastAPI / MarketBroadcaster
                                      │
                               SSE / EventSource
                                      │
                                GitHub Pages
```

SSE transporta os dados do servidor ao navegador. A cotação de origem depende da frequência, latência e limites do provedor: atualização quase em tempo real não significa feed tick-by-tick. O polling da brapi é de 30 minutos. O endpoint `/api/dashboard` agrega taxas de referência do Frankfurter, IPCA mensal do BCB/SGS e notícias via GDELT, mantendo o resultado em cache por 12 horas.

## Stack

| Camada | Tecnologia |
|---|---|
| Frontend | HTML, CSS, JavaScript |
| Gráficos | Chart.js |
| Backend | Python 3.12, FastAPI, Pydantic |
| Streaming | Server-Sent Events |
| Persistência | SQLite |
| Mercado | brapi |
| Frontend hosting | GitHub Pages |
| Backend hosting | Render |
| Qualidade | pytest, GitHub Actions |

## Executar localmente

Requer Python 3.11+.

```bash
cd backend
python -m venv .venv
# Windows PowerShell: .venv\\Scripts\\Activate.ps1
# macOS/Linux: source .venv/bin/activate
pip install -r requirements-dev.txt
uvicorn main:app --reload
```

Em outro terminal, sirva a raiz do projeto com Live Server ou outro servidor estático. O `config.js` já usa `http://localhost:8000` automaticamente quando acessado em localhost.

- API: http://localhost:8000
- Swagger: http://localhost:8000/docs
- Health: http://localhost:8000/health
- SSE: http://localhost:8000/api/market/stream

## Testes

```bash
cd backend
pip install -r requirements-dev.txt
pytest -q
```

Os testes cobrem inicialização de conta, depósitos, saques, saldo insuficiente, tipos inválidos, conta inexistente, validação de tickers e broadcast SSE. O workflow em `.github/workflows/ci.yml` executa os testes em pushes e pull requests para `main`.

## Configuração da brapi

O backend lê `BRAPI_TOKEN` por variável de ambiente. Se seu plano da brapi exigir token, configure-o no Render. **Nunca coloque tokens no frontend ou no repositório.**

`MARKET_POLL_SECONDS` define o intervalo de consulta (padrão 15 segundos). Uma consulta alimenta todos os clientes conectados à mesma instância.

## Deploy

### Backend — Render

O `render.yaml` descreve o serviço FastAPI, health check e disco persistente para o SQLite. Crie o serviço a partir do Blueprint e configure:

- `BRAPI_TOKEN`: token privado da brapi, se necessário.
- `FRONTEND_ORIGINS`: origem exata do GitHub Pages, por exemplo `https://iamdatagabs.github.io`.
- `MARKET_POLL_SECONDS`: intervalo desejado, respeitando limites do provedor.

O disco persistente configurado no Blueprint pode exigir plano pago do Render. Sem disco persistente, SQLite em filesystem efêmero perde os dados quando a instância reinicia.

### Frontend — GitHub Pages

1. Publique a branch `main` em **Settings → Pages → Deploy from a branch → /(root)**.
2. Edite `config.js` e defina `window.NEXUS_API_URL` com a URL HTTPS do backend no Render.
3. Configure `FRONTEND_ORIGINS` no Render com a origem do GitHub Pages.
4. Aguarde a publicação e teste a API e o dashboard.

## Endpoints

| Método | Rota | Descrição |
|---|---|---|
| GET | `/health` | Health check |
| GET | `/api/accounts/{id}` | Saldo e extrato |
| POST | `/api/transactions` | Depósito ou saque |
| GET | `/api/market/quotes` | Snapshot de cotações |
| GET | `/api/market/stream` | Stream SSE |\n| GET | `/api/dashboard` | Câmbio, IPCA e notícias (cache 12h) |

Exemplo de transação:

```json
{"account_id":"demo","type":"deposit","amount":250.00,"description":"Aporte demonstrativo"}
```

## Limitações e evolução

- O broadcaster/cache SSE é local à instância. Para escalar horizontalmente, usar Redis Pub/Sub.
- SQLite é adequado ao protótipo; PostgreSQL + Alembic é o próximo passo para maior concorrência.
- O sistema ainda não implementa autenticação, autorização por usuário, transferências ou dinheiro real.
- Próximos incrementos: JWT, PostgreSQL, carteira de investimentos, séries históricas, observabilidade, rate limiting e auditoria.

## Licença

Consulte e preserve a licença aplicável ao código original antes de redistribuir.

### Cotações e limites da brapi

O backend consulta os seis ativos individualmente e mantém um snapshot em memória compartilhado pelo SSE e pelo endpoint `/api/market/quotes`. O intervalo mínimo está configurado em 30 minutos para respeitar o plano gratuito da brapi (1 ticker por chamada, até 15.000 requisições/mês e atualização aproximada de 30 minutos). Com seis ativos, a estimativa é de cerca de 8.640 chamadas/mês em operação contínua. Clientes SSE e chamadas ao endpoint de leitura reutilizam o cache e não geram novas consultas à brapi.