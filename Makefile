.PHONY: up down logs shell test reset config lint
up:
	docker compose up --build -d device
down:
	docker compose down
logs:
	docker compose logs -f device
shell:
	docker compose exec device bash
test:
	./scripts/smoke-test.sh
reset:
	docker compose down -v --remove-orphans
config:
	docker compose config
lint:
	uv run ruff check .
	uv run ruff format --check .
