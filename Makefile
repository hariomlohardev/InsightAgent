.PHONY: install backend frontend test format lint run-backend run-frontend docker-up docker-down

install:
	cd backend && pip install -r requirements.txt
	cd frontend && pip install -r requirements.txt

backend:
	cd backend && uvicorn app.main:app --reload --port 8000

frontend:
	cd frontend && streamlit run streamlit_app.py --server.port 8501

test:
	cd backend && pytest -v --tb=short

format:
	cd backend && python -m pip install black ruff 2>/dev/null; black app/ tests/ || true
	cd frontend && black streamlit_app.py || true

lint:
	cd backend && ruff check app/ || true

docker-up:
	docker-compose up --build

docker-down:
	docker-compose down
