# Fraudes PIX — MED (Mecanismo Especial de Devolução)

Pipeline analítico end-to-end sobre as transações PIX contestadas por
suspeita de fraude, a partir dos [dados abertos do Banco Central do
Brasil](https://dadosabertos.bcb.gov.br/dataset/pix) (API Olinda).

## Arquitetura

```
tp-ibd/
├── run.py                # Ponto de entrada do pipeline (CLI)
├── Makefile              # Atalhos (make db-up, make ingest, ...)
├── docker-compose.yml    # Postgres local para desenvolvimento
├── requirements.txt      # Dependências Python
├── sql/
│   └── schema.sql        # DDL PostgreSQL (3FN) + seed de regiões/UFs
├── src/
│   ├── config.py         # Configuração (conexão, API, timeouts)
│   ├── logger.py         # Configuração de logging (arquivo em logs/)
│   ├── extract.py        # Cliente da API Olinda/BCB (OData)
│   ├── transform.py      # Limpeza, tipagem e normalização (wide -> long)
│   ├── ingest.py         # Orquestração ETL + carga via COPY
│   ├── data_accessor.py  # Camada de acesso a dados (padrão DAO)
│   └── eda.py            # Análise exploratória (gera as figuras)
├── queries/              # Consultas analíticas (.sql) usadas na EDA
├── notebooks/
│   ├── INSIGHTS.md       # Relatório com os insights de negócio
│   └── figuras/          # Visualizações geradas pela EDA
└── docs/                 # Relatório técnico (LaTeX/PDF) e diagramas
```

Fontes consumidas (todas com competência mensal):

| Endpoint | Conteúdo | Granularidade |
|---|---|---|
| `EstatisticasFraudesPix` | Contestações, devoluções e bloqueios do MED | Nacional / mês |
| `ChavesPix` | Base de chaves por instituição (ISPB) | Instituição / mês |
| `TransacoesPixPorMunicipio` | Volumetria transacionada | Município / mês |

## Setup

Pré-requisitos: Python 3.10+. Para o banco, escolha **uma** das opções abaixo.

> **Atalho:** com o `venv` ativo e o Docker disponível, o caminho local
> resume-se a `make db-up && make ingest`. Rode `make help` para a lista
> completa de alvos. Os alvos `make ingest`/`reingest`/`eda` apontam para o
> Postgres local por padrão (ignoram um eventual `.env` de produção); para
> mirar outro banco, passe `DB_URL=...`.

### 1. Ambiente Python

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Banco de dados

#### Opção A — Postgres local via Docker (recomendado p/ desenvolvimento)

Não toca no Supabase de produção. O `schema.sql` é aplicado automaticamente
no primeiro boot do contêiner.

```bash
docker compose up -d        # sobe o Postgres em localhost:5432
```

A string de conexão default (`src/config.py`) já casa com este contêiner,
então **o `.env` é opcional** para o fluxo local. Se ainda não existir um
`.env` e quiser torná-lo explícito, `cp .env.example .env` (já vem apontando
para o Postgres local). Não copie por cima de um `.env` de Supabase que você
queira preservar.

Comandos úteis: `docker compose down` (para, mantendo os dados) e
`docker compose down -v` (reset total, apaga o volume).

#### Opção B — Supabase / Postgres existente

```bash
cp .env.example .env
# edite o .env e descomente/preencha a DATABASE_URL do Supabase
```

O schema é aplicado pelo próprio app na primeira ingestão, com
`--recriar-schema` (passo 3) — o pipeline usa SQLAlchemy e entende o prefixo
`postgresql+psycopg2://`. Se preferir aplicar via `psql`, use uma URL **sem**
esse prefixo (que é específico do SQLAlchemy; o `psql` não o reconhece):

```bash
psql "postgresql://USUARIO:SENHA@HOST:5432/postgres" -f sql/schema.sql
```

> **Supabase:** em redes IPv4 (ex.: WSL2), use o host do *Session Pooler*
> (`aws-1-<regiao>.pooler.supabase.com`, usuário `postgres.<ref>`) — o host
> direto `db.<ref>.supabase.co` resolve apenas para IPv6.

### 3. Ingestão (janela de competências configurável)

```bash
python run.py --inicio 2024-01 --fim 2025-12          # ou: make ingest

# Reaplica o schema antes de carregar (apaga dados existentes):
python run.py --recriar-schema --inicio 2024-01 --fim 2025-12   # ou: make reingest
```

A janela default é `2024-01 .. 2025-12`. Com `make`, sobrescreva via
`make ingest INICIO=2025-01 FIM=2025-06`.

A ingestão é **idempotente**: dimensões usam `INSERT ... ON CONFLICT` e os
fatos são recarregados por competência (`DELETE` + `COPY`) dentro de uma
única transação.

## Análise exploratória

```bash
python -m src.eda   # gera notebooks/figuras/*.png   (ou: make eda)
```

Os insights de negócio estão documentados em
[`notebooks/INSIGHTS.md`](notebooks/INSIGHTS.md).
