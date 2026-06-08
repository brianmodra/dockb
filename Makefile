include .env
export

all: sort check_static_typing detect_cycles lint test

sort:
	isort src/dockb tests/dockb

check_static_typing:
	mypy src --check-untyped-defs

lint:
	pylint src && pylint --rcfile=tests/pylintrc tests
	black src tests
	ruff check --fix src tests

detect_cycles:
	cd src/dockb; pycycle --here

test:
	cd tests; pytest

run:
	cd src; ../.venv/bin/python3 -m main

migrate:
	neo4j-migrations --database=$(NEO4J_DATABASE) migrate

.PHONY: all check_static_typing lint detect_cycles sort run test migrate
