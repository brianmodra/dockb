all: sort check_static_typing detect_cycles lint

sort:
	isort src/dockb

check_static_typing:
	mypy src --check-untyped-defs

lint:
	pylint src

detect_cycles:
	cd src/dockb; pycycle --here

run:
	cd src; ../.venv/bin/python3 -m main

.PHONY: all check_static_typing lint detect_cycles sort run
