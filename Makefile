# Atalhos de conveniência. Rode `make` ou `make help` para ver os alvos.
# Pré-requisitos: Docker (alvos db-*) e o venv ativado (alvos install/ingest/eda).

# Janela de competências da ingestão (sobrescreva: make ingest INICIO=2025-01 FIM=2025-06)
INICIO ?= 2024-01
FIM    ?= 2025-12

# Banco usado pelos alvos de aplicação (ingest/reingest/eda). O default é o
# Postgres local do compose, e é EXPORTADO na execução — assim estes alvos
# ignoram um eventual .env de produção e nunca tocam o Supabase por engano.
# Para mirar outro banco: make ingest DB_URL=postgresql+psycopg2://usuario:senha@host:5432/db
DB_URL ?= postgresql+psycopg2://postgres:postgres@localhost:5432/pix_med

.DEFAULT_GOAL := help

.PHONY: help install db-up db-down db-reset db-logs ingest reingest eda

help: ## Lista os alvos disponíveis
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

install: ## Instala as dependências Python (use dentro do venv)
	pip install -r requirements.txt

db-up: ## Sobe o Postgres local (docker compose up -d)
	docker compose up -d

db-down: ## Para o Postgres local, mantendo os dados
	docker compose down

db-reset: ## Reset total: para o banco e APAGA o volume de dados
	docker compose down -v

db-logs: ## Acompanha os logs do contêiner do banco
	docker compose logs -f db

ingest: ## Roda o pipeline ETL no banco local (use INICIO=/FIM=/DB_URL=)
	DATABASE_URL="$(DB_URL)" python run.py --inicio $(INICIO) --fim $(FIM)

reingest: ## Reaplica o schema (apaga dados!) e roda o ETL no banco local
	DATABASE_URL="$(DB_URL)" python run.py --recriar-schema --inicio $(INICIO) --fim $(FIM)

eda: ## Gera as figuras da análise exploratória (lê do banco local)
	DATABASE_URL="$(DB_URL)" python -m src.eda
