.PHONY: install dev backend desktop test lint docker-up docker-down package

install:
	npm install
	python -m venv .venv
	@if exist apps\backend\requirements.lock ( \
		.venv\Scripts\pip install -r apps\backend\requirements.lock \
	) else ( \
		.venv\Scripts\pip install -r apps\backend\requirements.txt \
	)

dev:
	npm run backend:dev

backend:
	.venv/Scripts/uvicorn app.main:app --reload --app-dir apps/backend --host 0.0.0.0 --port 8000

desktop:
	npm run dev --workspace @interview/desktop

test:
	.venv/Scripts/pytest apps/backend/tests
	npm test

lint:
	.venv/Scripts/ruff check apps/backend
	npm run lint

docker-up:
	docker compose up --build

docker-down:
	docker compose down

package:
	npm run desktop:package
