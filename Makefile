.PHONY: up down logs ps init db-shell etl test

up:
	docker compose up -d

down:
	docker compose down

logs:
	docker compose logs -f

ps:
	docker compose ps

init:
	docker compose exec api python scripts/init_db.py

bootstrap-metabase:
	python scripts/setup_metabase.py

metabase-embed:
	python scripts/setup_metabase_embed.py

db-shell:
	docker compose exec db psql -U bi_admin -d bi_dwh

etl:
	docker compose exec api python -m etl.runners.sync --sources 1c,amocrm,gsheets

test:
	cd api && python -m pytest ../tests -v
