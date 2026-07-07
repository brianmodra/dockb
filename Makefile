include .env
export

all: sort check_static_typing detect_cycles lint test

sort:
	ruff check --fix --select I src tests

check_static_typing:
	mypy src --check-untyped-defs

lint:
	pylint src && pylint --rcfile=tests/pylintrc tests
	black src tests
	ruff check --fix src tests

detect_cycles:
	cd src/dockb; pycycle --here

test:
	pytest --ignore=tests/integration

test_integration:
	pytest tests/integration -v -s

run:
	@bash scripts/run.sh

migrate:
	neo4j-migrations --database=$(NEO4J_DATABASE) migrate

.PHONY: all check_static_typing lint detect_cycles sort run test test_integration migrate
