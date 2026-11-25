# Nexus Banking — Banking & Market Intelligence

Releitura full-stack do desafio original **Sistema Bancário em Python (DIO)**. O projeto reúne operações bancárias demonstrativas, API REST, persistência local, streaming de cotações e um painel de inteligência de mercado com indicadores econômicos, câmbio e notícias.

> **Projeto educacional.** Não é uma instituição financeira ou corretora, não movimenta dinheiro real e não oferece recomendações de investimento.

**Portfólio:** https://iamdatagabs.github.io/iamdatagabs/portfolio/\n\n## Aplicação publicada

- **Dashboard:** https://iamdatagabs.github.io/Sistema-Bancario-Python/
- **Repositório:** https://github.com/iamdatagabs/Sistema-Bancario-Python
- **API (Render):** https://nexus-banking-api-wip3.onrender.com
- **Documentação interativa:** https://nexus-banking-api-wip3.onrender.com/docs

O frontend é hospedado no GitHub Pages e consome a API hospedada no Render. A disponibilidade dos dados externos depende do backend e dos respectivos provedores.

## Funcionalidades

### Banking
- Dashboard responsivo com saldo, entradas, saídas, histórico e gráfico.
- Depósitos e saques demonstrativos.
- Validação das operações no backend e representação monetária em centavos.
- Persistência de dados com SQLite.

### Market & Intelligence
- Cotações de seis ativos brasileiros: PETR4, VALE3, ITUB4, BBDC4, BBAS3 e WEGE3.
- Atualização das cotações por polling no backend e distribuição aos navegadores via Server-Sent Events (SSE).
- Reconexão automática, snapshot em cache e keep-alive do stream.
- Painel de câmbio com BRL, USD, EUR, JPY e GBP, exibindo valores de referência em reais.
- Indicador mensal de inflação (IPCA), consultado na série 433 do Sistema Gerenciador de Séries Temporais (SGS) do Banco Central.
- Radar com notícias recentes de economia e política brasileira.
- Cache de 12 horas para o conjunto de dados de câmbio, IPCA e notícias.

## Arquitetura

```text
                         ┌─────────────────────────┐
                         │      GitHub Pages       │
                         │ HTML · CSS · JavaScript │
                         └────────────┬────────────┘
                                      │ HTTPS / REST
                                      │ EventSource (SSE)
                         ┌────────────▼────────────┐
                         │       FastAPI           │
                         │       Render            │
                         ├─────────────────────────┤
                         │ Banking API · SQLite   │
                         │ Market Broadcaster      │
                         │ Dashboard Intelligence  │
                         └──────┬──────────┬───────┘
                                │          │
                    ┌───────────┘          └───────────────┐
                    ▼                                      ▼
             ┌────────────┐                     ┌──────────────────┐
             │   brapi    │                     │ Dados externos   │
             │ Cotações   │                     │ Frankfurter      │
             └────────────┘                     │ Banco Central    │
                                                │ GDELT            │
                                                └──────────────────┘
```

O backend centraliza as consultas de mercado para os clientes conectados à mesma instância. O SSE distribui o snapshot ao navegador; não se trata de um feed tick-by-tick. O intervalo de polling da brapi deve respeitar os limites do plano contratado. A inteligência de câmbio, inflação e notícias é agregada por `GET /api/dashboard` e armazenada em cache por 12 horas.

## Stack

| Camada | Tecnologia |
|---|---|
| Frontend | HTML, CSS, JavaScript |
| Gráficos | Chart.js |
| Backend | Python, FastAPI, Pydantic |
| Streaming | Server-Sent Events (SSE) |
| Persistência | SQLite |
| Cotações | brapi |
| Câmbio | Frankfurter |
| Indicador econômico | Banco Central do Brasil — SGS |
| Notícias | GDELT |
| Frontend hosting | GitHub Pages |
| Backend hosting | Render |
| Testes e CI | pytest, GitHub Actions |

## Executar localmente

Requer Python 3.11 ou superior.

1. Clone o repositório e entre na pasta do backend:

```bash
git clone https://github.com/iamdatagabs/Sistema-Bancario-Python.git
cd Sistema-Bancario-Python/backend
```

2. Crie e ative um ambiente virtual:

```bash
python -m venv .venv

# Windows PowerShell
.venv\Scripts\Activate.ps1

# macOS / Linux
source .venv/bin/activate
```

3. Instale as dependências e inicie a API:

```bash
pip install -r requirements-dev.txt
uvicorn main:app --reload
```

4. Em outro terminal, na raiz do repositório, sirva os arquivos estáticos com Live Server ou outro servidor HTTP local.

Endereços locais:

- API: http://localhost:8000
- Swagger: http://localhost:8000/docs
- Health check: http://localhost:8000/health
- Stream SSE: http://localhost:8000/api/market/stream

O `config.js` seleciona a URL local da API quando o frontend é aberto em localhost.

## Testes

Na pasta `backend`:

```bash
pip install -r requirements-dev.txt
pytest -q
```

A suíte automatizada cobre operações bancárias, validações, consulta de ativos, streaming SSE e cache do painel de inteligência. O workflow em `.github/workflows/ci.yml` executa os testes em pushes e pull requests para a branch principal.

## Configuração

O backend utiliza variáveis de ambiente para parâmetros de execução:

| Variável | Finalidade |
|---|---|
| `BRAPI_TOKEN` | Token privado da brapi, quando exigido pelo plano |
| `FRONTEND_ORIGINS` | Origens autorizadas pelo CORS, incluindo a origem do GitHub Pages |
| `MARKET_POLL_SECONDS` | Intervalo, em segundos, entre consultas de cotações |

Nunca inclua tokens ou credenciais no frontend, no README ou no controle de versão. Cadastre segredos diretamente nas variáveis de ambiente do serviço de backend.

A frequência de consulta à brapi deve observar os limites do provedor. Para a implantação com plano gratuito, o intervalo foi configurado em **1.800 segundos (30 minutos)**. O cache do painel de câmbio, IPCA e notícias tem validade de **12 horas**.

## Deploy

### Backend — Render

O serviço FastAPI é hospedado no Render. Configure as variáveis de ambiente indicadas acima e defina o health check como `/health`. A URL pública da API utilizada pelo frontend é:

`https://nexus-banking-api-wip3.onrender.com`

O projeto utiliza SQLite. Se o serviço estiver em filesystem efêmero, os dados locais podem ser perdidos em reinicializações ou novos deploys; armazenamento persistente depende da configuração e do plano do serviço.

### Frontend — GitHub Pages

O frontend está publicado em:

https://iamdatagabs.github.io/Sistema-Bancario-Python/

A publicação é automatizada pelo GitHub Actions. Para uma nova instalação, habilite GitHub Pages nas configurações do repositório e configure a URL pública da API em `config.js`. No Render, autorize a origem do GitHub Pages em `FRONTEND_ORIGINS`.

## Endpoints da API

| Método | Rota | Descrição |
|---|---|---|
| GET | `/health` | Health check |
| GET | `/api/accounts/{id}` | Saldo e extrato da conta |
| POST | `/api/transactions` | Depósito ou saque |
| GET | `/api/market/quotes` | Snapshot de cotações |
| GET | `/api/market/stream` | Stream de cotações via SSE |
| GET | `/api/dashboard` | Câmbio, IPCA e notícias (cache de 12 horas) |

Exemplo de transação demonstrativa:

```json
{
  "account_id": "demo",
  "type": "deposit",
  "amount": 250.00,
  "description": "Aporte demonstrativo"
}
```

## Limitações e próximos passos

- O broadcaster e o cache SSE são locais à instância; escalabilidade horizontal exigiria um mecanismo compartilhado, como Redis Pub/Sub.
- SQLite atende ao protótipo; PostgreSQL e migrações com Alembic são caminhos para maior concorrência e evolução do esquema.
- O projeto não implementa autenticação, autorização por usuário, transferências entre contas ou movimentação de dinheiro real.
- Cotações e indicadores dependem da disponibilidade, atualização e limites das APIs externas.
- O cache em memória é reiniciado quando o processo do backend reinicia ou recebe um novo deploy.

Possíveis evoluções incluem autenticação JWT, PostgreSQL, carteira de investimentos, séries históricas, observabilidade, rate limiting e trilha de auditoria.

## Fontes de dados

- [brapi](https://brapi.dev/) — cotações de ativos brasileiros.
- [Frankfurter](https://www.frankfurter.dev/) — taxas de câmbio de referência.
- [Banco Central do Brasil — SGS](https://www3.bcb.gov.br/sgspub/) — série mensal do IPCA.
- [GDELT](https://www.gdeltproject.org/) — monitoramento de notícias.

## Licença

Consulte e preserve a licença aplicável ao código original antes de redistribuir o projeto.
