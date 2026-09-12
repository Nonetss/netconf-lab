.PHONY: up down logs shell client test reset config
up:
	docker compose up --build -d
down:
	docker compose down
logs:
	docker compose logs -f device
shell:
	docker compose exec device bash
client:
	docker compose exec client python examples/get_all.py
test:
	./scripts/smoke-test.sh
reset:
	docker compose down -v --remove-orphans
config:
	docker compose config
