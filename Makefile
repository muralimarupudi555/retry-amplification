# `make verify` is the gate: it must pass on a clean clone with no network.
# `make bench` is the slow part, because a benchmark that runs on every commit stops
# being run at all.

PYTHON := python3
DSN ?= postgresql://postgres:postgres@127.0.0.1:5433/postgres
export RETRY_AMPLIFICATION_DSN = $(DSN)

.PHONY: help install db-up db-down lint test verify bench diagram tables cli clean

help:
	@echo "make install   install the package and its development dependencies"
	@echo "make db-up     start the PostgreSQL this repository measures against"
	@echo "make verify    lint, tests, law check, number check - the gate"
	@echo "make bench     run the four experiments, minutes not seconds"
	@echo "make db-down   stop the database"

install:
	$(PYTHON) -m pip install -e ".[dev]"

db-up:
	docker compose up -d --wait

db-down:
	docker compose down -v

lint:
	$(PYTHON) -m ruff check .

test:
	$(PYTHON) -m pytest

diagram:
	$(PYTHON) tools/render_diagram.py

tables:
	$(PYTHON) tools/render_tables.py

# A transcript carries measured timings, so regenerating it dirties the tree. It
# belongs with the measurements rather than in the gate: a `make verify` that leaves
# uncommitted changes behind is one people stop reading the output of.
cli:
	$(PYTHON) tools/capture_cli.py

verify: lint test diagram tables
	$(PYTHON) tools/check_laws.py
	$(PYTHON) tools/collect_metrics.py
	$(PYTHON) tools/check_numbers.py

bench: cli
	$(PYTHON) experiments/e1_one_number_two_bills.py
	$(PYTHON) experiments/e2_the_cap_is_a_trade.py
	$(PYTHON) experiments/e3_what_the_ledger_costs.py
	$(PYTHON) experiments/e4_backoff_does_not_help.py

clean:
	rm -rf .pytest_cache .ruff_cache **/__pycache__ *.egg-info
