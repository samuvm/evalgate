# Makefile canónico (CONSTITUCION §7.4). El gate es un target que devuelve 0 o distinto de 0: el día que
# llegue git, pre-commit invoca estos mismos targets sin cambiar una línea.
#
# Los targets de fases futuras FALLAN diciendo en qué fase llegan: un target que "pasa" sin hacer nada es
# un gate falso.

SHELL := /bin/bash
.DEFAULT_GOAL := help
MILESTONE ?=
PROFILE ?= proxy
PROXY_PORT ?= 8080
export EVALGATE_SELF_GATE ?= off

RUN := uv run --locked
PYTEST := $(RUN) pytest -p no:cacheprovider
FAST_DIRS := tests/unit tests/property tests/contract
TESTABLE = $(shell $(RUN) python scripts/testable_paths.py)

define not_yet
	@echo "make $@: llega en $(1) (docs/PLAN.md). Aún no existe." >&2; exit 1
endef

.PHONY: help up down warm lint typecheck test-fast test test-int test-e2e adoption eval eval-refresh \
        eval-compare-twice bench mutation trace_lossless degradation gate-fast gate-full done report clean

help:
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | sed 's/:.*## /\t/' | column -t -s $$'\t'

up: ## levanta el proxy (Ollama en el HOST, nunca en compose). ClickHouse llega en F3
	@curl -sf -m 3 http://localhost:11434/api/version >/dev/null \
		|| { echo "Ollama no responde en localhost:11434 (va en el host, STACK §0)" >&2; exit 1; }
	@mkdir -p .run
	@if [ -f .run/proxy.pid ] && kill -0 $$(cat .run/proxy.pid) 2>/dev/null; then \
		echo "proxy ya en marcha (pid $$(cat .run/proxy.pid))"; \
	else \
		nohup $(RUN) evalgate serve --port $(PROXY_PORT) > .run/proxy.log 2>&1 & echo $$! > .run/proxy.pid; \
		for i in $$(seq 50); do curl -sf -m 1 http://127.0.0.1:$(PROXY_PORT)/healthz >/dev/null && break; sleep 0.2; done; \
		curl -sf -m 1 http://127.0.0.1:$(PROXY_PORT)/healthz >/dev/null \
			|| { echo "el proxy no arrancó: ver .run/proxy.log" >&2; exit 1; }; \
		echo "proxy en http://127.0.0.1:$(PROXY_PORT)/v1 (pid $$(cat .run/proxy.pid))"; \
	fi
down: ## para el proxy
	@if [ -f .run/proxy.pid ]; then kill $$(cat .run/proxy.pid) 2>/dev/null || true; rm -f .run/proxy.pid; fi
	@echo "proxy parado"
warm: ## descarga modelos y precalienta cachés; nunca dentro de up
	$(call not_yet,F5)

lint: ## ruff check + ruff format --check
	$(RUN) ruff check .
	$(RUN) ruff format --check .

typecheck: ## mypy --strict sobre [tool.gate].testable
	$(RUN) mypy $(TESTABLE)

test-fast: ## nivel 1 + 1b(dev) + 3. Presupuesto < 20 s
	HYPOTHESIS_PROFILE=dev $(PYTEST) $(FAST_DIRS) -q

test: ## todo salvo evals y holdout
	HYPOTHESIS_PROFILE=gate $(PYTEST) $(FAST_DIRS) tests/integration tests/adversarial -q

test-int: ## nivel 2, testcontainers ClickHouse. Necesita Docker vivo; nunca en gate-fast (RULES §3.10)
	$(PYTEST) tests/integration -q
trace_lossless: ## G-TRACE-0: `make test-int -k trace_lossless` (make -k sigue tras fallo; es un target)
	$(PYTEST) tests/integration/test_trace_lossless.py -q
degradation: ## G-TRACE-DEGRADE: `make test-int -k degradation`. Tumba ClickHouse a mitad del test
	$(PYTEST) tests/integration/test_degradation.py -q
test-e2e: ## nivel 5. `make test-e2e -k adoption` = G-ADOPTION (make -k sigue tras fallo; adoption es un target)
	$(PYTEST) tests/e2e -q
adoption: ## G-ADOPTION: líneas de diff de examples/rag-app con y sin proxy. Tiene que dar 0
	$(PYTEST) tests/e2e/test_adoption.py -q -s
eval: ## nivel 4 desde caché grabada
	$(call not_yet,F4 (pricing-repro) y F5 (suite))
eval-refresh: ## nivel 4 recalculando; nunca en el gate
	$(call not_yet,F5)
eval-compare-twice: ## G-DETERMINISM
	$(call not_yet,F6)
bench: ## protocolo de docs/bench/protocol.md. PROFILE=proxy|stream. Pedir antes la ventana (Q-005 (a))
	@test -n "$(PROFILE)" || { echo "uso: make bench PROFILE=proxy|stream" >&2; exit 2; }
	$(RUN) python scripts/bench.py --profile $(PROFILE)
mutation: ## G-MUTATION (PARA-SAMUEL P-003): mutmut en una copia sin tests/holdout/
	$(RUN) python scripts/mutation.py $(if $(MILESTONE),--milestone $(MILESTONE))

gate-fast: ## lint + typecheck + test-fast + reglas + anti-gaming
	$(MAKE) --no-print-directory lint typecheck test-fast
	$(RUN) python scripts/check_gate_config.py
	$(RUN) python scripts/rules/self_gate.py
	$(RUN) python scripts/rules/pins.py
	$(RUN) python scripts/rules/example_is_client.py
	$(RUN) python scripts/rules/readme_numbers.py
	$(RUN) python scripts/rules/finally_on_generators.py
	$(RUN) python scripts/rules/stream_closed_in_request.py
	$(RUN) python scripts/rules/no_genai_literals.py
	$(RUN) python scripts/rules/no_blocking_export.py
	$(RUN) python scripts/gen_semconv.py --check
	$(RUN) python scripts/rules/sse_corpus_coverage.py
	$(RUN) python scripts/debt.py
	$(RUN) python scripts/test_inventory.py --against .claude/state/test-inventory.json

gate-full: ## gate-fast + test + contrato + metas + thresholds.lock + secretos
	$(MAKE) --no-print-directory gate-fast
	$(RUN) python scripts/done.py --mode full --milestone $$(grep -E '^fase_activa:' .claude/state/STATE.md | awk '{print $$2}')

done: ## la única definición de "hecho". make done MILESTONE=N
	@test -n "$(MILESTONE)" || { echo "uso: make done MILESTONE=N" >&2; exit 2; }
	$(RUN) python scripts/done.py --mode done --milestone $(MILESTONE)

report: ## regenera las tablas del README desde evals/reports/ (R17)
	$(RUN) python scripts/report.py

clean: ## borra cachés y artefactos regenerables
	rm -rf .pytest_cache .mypy_cache .ruff_cache .coverage htmlcov mutants
	find . -name __pycache__ -type d -not -path './.venv/*' -prune -exec rm -rf {} +
