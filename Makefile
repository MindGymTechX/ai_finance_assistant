PY ?= python

install:
	$(PY) -m pip install -r requirements.txt

index:
	$(PY) -m scripts.build_index

run:
	streamlit run app.py

test:
	$(PY) -m pytest -q

coverage:
	$(PY) -m pytest --cov=src --cov-config=.coveragerc --cov-report=term-missing

mcp:
	$(PY) -m src.mcp_server

docker:
	docker build -t finai . && docker run --rm -p 8501:8501 --env-file .env -v finai-data:/data finai

clean:
	rm -rf .finai .pytest_cache htmlcov .coverage
