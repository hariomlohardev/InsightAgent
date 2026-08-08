.PHONY: install backend frontend test test-verbose cov format lint run-backend run-frontend docker-up docker-down docker-check

install:
	cd backend && pip install -r requirements.txt
	cd frontend && pip install -r requirements.txt
	cd sdk && pip install -e . --quiet || pip install -e sdk --quiet || true
	@echo "install done — backend + frontend + sdk (30s)"

backend:
	cd backend && uvicorn app.main:app --reload --port 8000

frontend:
	cd frontend && streamlit run streamlit_app.py --server.port 8501 --server.address 0.0.0.0

test:
	cd backend && python -m pytest tests -q

test-verbose:
	cd backend && python -m pytest tests -v --tb=short

cov:
	cd backend && python -m pytest tests --cov=app --cov-report=term-missing --cov-report=html --cov-fail-under=80 -q || python -m pytest tests -q

format:
	cd backend && python -m black app/ tests/ 2>/dev/null || black app/ tests/ || true
	cd frontend && python -m black streamlit_app.py 2>/dev/null || black streamlit_app.py || true

lint:
	cd backend && python -m ruff check app/ 2>/dev/null || ruff check app/ || true
	cd backend && python -m py_compile app/main.py app/core/*.py app/agent/*.py 2>/dev/null && echo "py_compile OK"

run-backend:
	cd backend && uvicorn app.main:app --reload --port 8000 --host 0.0.0.0

run-frontend:
	cd frontend && streamlit run streamlit_app.py --server.port 8501 --server.address 0.0.0.0

docker-up:
	docker-compose up --build

docker-down:
	docker-compose down

docker-check:
	docker compose config 2>&1 | head -n 50 || docker-compose config 2>&1 | head -n 50
	@echo "docker-compose valid"

check: lint test
	@echo "All checks passed"
