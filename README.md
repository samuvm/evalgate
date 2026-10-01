# Evalgate · puerta de calidad LLM

> **Un evaluador no evaluado es un adorno.** Evalgate es una puerta de calidad para aplicaciones LLM que
> publica sus propias tasas de error: la concordancia de su juez con un humano, su tasa de falsos positivos y
> el efecto mínimo que es capaz de detectar, los tres medidos.

**Estado:** en construcción, F2 de 10 cerrada y F3 (telemetría, almacén y degradación) en curso
(`docs/PLAN.md`). El núcleo (F0-F7 y F9) todavía no está completo, y este README solo afirma lo que ya está
medido: lo que no tiene fila en la tabla de [Números medidos](#números-medidos) no se da por hecho.

## Qué es y qué no es

- **Un proxy** compatible con `/v1/chat/completions` de OpenAI, que se adopta cambiando una variable de
  entorno (`OPENAI_BASE_URL`), sin tocar código. Habla con cualquier runtime compatible con OpenAI; hoy,
  Ollama en local (`docs/adr/002-litellm-nunca-como-proxy.md`).
- **Un motor de evaluación y una puerta** que compara dos informes con bootstrap pareado y corrección de
  Holm, y devuelve 0 o 1 para CI (en construcción: F5-F7).
- **No** es una plataforma de observabilidad con interfaz (`docs/adr/004-evalgate-frente-a-langfuse.md`) ni
  compite en latencia con pasarelas en Go (`docs/adr/003-evalgate-frente-a-bifrost.md`).

## Cómo encaja

```
  tu app ──► evalgate (proxy) ──► proveedor compatible con OpenAI (hoy: Ollama)
                  │
                  ├─► registro de uso: tokens y coste, también si el cliente corta   [F2, cerrada]
                  ├─► traza OTel ──► cola acotada ──► ClickHouse                     [F3, en curso]
                  │
  informe A ─┐
             ├─► evalgate eval compare ──► exit 0 | 1 para CI                        [F5-F7, pendiente]
  informe B ─┘
```

Tres piezas que comparten almacén y se usan por separado: el proxy registra, el motor de evaluación mide
y la puerta decide. La puerta es la única con opinión, y por eso es la que tiene que demostrar cuánto se
equivoca.

## Probarlo

Requisitos: Python 3.12, [`uv`](https://docs.astral.sh/uv/) y [Ollama](https://ollama.com) escuchando en
el host (`localhost:11434`) con un modelo descargado (`RAG_MODEL`, por defecto `qwen3.5:9b-mlx`).

```bash
uv sync
make up                                   # proxy en http://127.0.0.1:8080/v1, Ollama en el host
python examples/rag-app/generate_corpus.py
OPENAI_BASE_URL=http://127.0.0.1:8080/v1 python examples/rag-app/rag_app.py --limit 3
make down
```

`examples/rag-app` es un cliente de verdad: no importa nada de `src/evalgate/` y solo usa la biblioteca
estándar. Que la adopción cueste una variable de entorno es una meta medida (`G-ADOPTION`: cero líneas de
diferencia entre la salida con proxy y sin él), no una frase del README.

## Reglas de diseño

Son reglas de `docs/RULES.md`. Las cuatro primeras ya tienen código y un comprobador en `scripts/rules/`
que corre en el gate:

- **Ninguna traza puede tumbar ni ralentizar una petición.** El proxy no importa exportadores ni espera a
  un export: cola acotada que, al llenarse, descarta y lo cuenta (R1, `no_blocking_export.py`).
- **La contabilidad se cierra siempre.** El registro de uso se emite en `finally` y sobrevive a la
  cancelación: cliente cortado = tokens pagados = tokens contados (R2, `finally_on_generators.py`,
  `docs/adr/010-contabilidad-ante-desconexion.md`). Dirigido por un corpus de transcripts SSE con los casos
  límite, en `tests/fixtures/sse/`.
- **Ningún nombre `gen_ai.*` escrito a mano.** El modelo de datos interno es propio; los nombres externos se
  generan desde la versión fijada en `otel-semconv.lock` (R5, `no_genai_literals.py`,
  `docs/adr/005-modelo-otel-interno-con-traduccion.md`).
- **El ejemplo es un cliente**: `examples/rag-app` no importa nada del paquete (R13, `example_is_client.py`).

Las siguientes obligan a fases que todavía no están cerradas; están escritas antes que el código para que
el código no pueda negociarlas:

- **Ningún precio vive en el código** y una tabla de precios publicada es inmutable: corregir un precio es
  publicar una tabla nueva con fecha posterior (R3, R4).
- **La puerta no contiene un solo umbral literal**: todo parámetro de decisión llega de `docs/GOALS.yaml` (R7).
- **El bootstrap es pareado o falla**, y con varias métricas bloqueantes la corrección es Holm: informes con
  conjuntos de casos distintos lanzan excepción, nunca degradan en silencio (R8).
- **Ninguna métrica llama a un LLM** y **el juez nunca es el modelo que genera** (R11, R12).

## Números medidos

Generados por `make report` desde `evals/reports/`. Ninguno se escribe a mano (regla R17).
Hardware de referencia: MacBook Pro M4 Max, 36 GB de memoria unificada (`docs/STACK.md` §0).

<!-- evalgate:numbers:start -->
| Fase | Meta | Valor | Cerrada | Artefacto |
|---|---|---|---|---|
| F1 | `G-ADOPTION` | lineas_de_diff=0, n_lineas=8 | 2026-09-12 | `evals/reports/gate-F1.json` |
| F1 | `G-FUNC-COV` | 0 | 2026-09-12 | `evals/reports/gate-F1.json` |
| F1 | `G-LINE-COV` | 100,00 | 2026-09-12 | `evals/reports/gate-F1.json` |
| F1 | `G-OPENAI-CONTRACT` | ratio=1,00, n=5 | 2026-09-12 | `evals/reports/gate-F1.json` |
| F2 | `G-ADOPTION` | lineas_de_diff=0, n_lineas=8 | 2026-09-20 | `evals/reports/gate-F2.json` |
| F2 | `G-DISCONNECT` | ratio=1, n=222 | 2026-09-20 | `evals/reports/gate-F2.json` |
| F2 | `G-FUNC-COV` | 0 | 2026-09-20 | `evals/reports/gate-F2.json` |
| F2 | `G-LINE-COV` | 98,70 | 2026-09-20 | `evals/reports/gate-F2.json` |
| F2 | `G-OPENAI-CONTRACT` | ratio=1,00, n=7 | 2026-09-20 | `evals/reports/gate-F2.json` |
| F2 | `G-TOKENS-EXACT` | ratio=1, n=5 | 2026-09-20 | `evals/reports/gate-F2.json` |
| F2 | `G-TOKENS-STREAM` | delta_con_usage=0 | 2026-09-20 | `evals/reports/gate-F2.json` |
<!-- evalgate:numbers:end -->

Qué significa cada meta, su umbral y el comando que la mide: `docs/GOALS.yaml`.

## Mapa del repositorio

| Ruta | Qué hay |
|---|---|
| `src/evalgate/proxy/` | Proxy: `streaming.py` (contabilidad del flujo, determinista dado un transcript), `translate.py`, `app.py` (montaje) |
| `src/evalgate/pricing/` | Modelo y búsqueda de tablas de precios fechadas (las tablas llegan en F4) |
| `src/evalgate/telemetry/` | Modelo interno de la llamada, traducción a OTel, cola acotada, filas y migraciones de ClickHouse; `semconv/` es generado |
| `src/evalgate/cli/` | CLI `evalgate` (`serve`, `migrate`) |
| `examples/rag-app/` | Aplicación RAG mínima que hace de cliente, demo y e2e |
| `tests/` | `unit`, `property` (Hypothesis), `contract`, `integration` (ClickHouse con testcontainers), `e2e`, y `fixtures/` con el corpus SSE y respuestas grabadas |
| `evals/reports/` | Informes de los que sale cada número de este README |
| `scripts/` | El gate (`done.py`), los comprobadores de reglas (`rules/`), el bench y el generador de semconv |
| `docs/` | Proyecto, plan, metas, reglas, contratos, ADR y bitácora |

## Desarrollo

```bash
make help          # todos los targets
make lint          # ruff check + ruff format --check
make typecheck     # mypy --strict sobre las rutas testeables
make test-fast     # unitarios + propiedad (perfil dev) + contrato
make test-int      # integración contra ClickHouse; necesita Docker
make test-e2e      # e2e contra el proxy y Ollama
```

Los targets de fases futuras fallan diciendo en qué fase llegan: un target que "pasa" sin hacer nada sería
un gate falso.

`make gate-fast`, `make gate-full` y `make done` son el gate con el que se cierra cada fase. Leen estado
local de trabajo que no se publica (ver abajo), así que fuera de la máquina de desarrollo no son
reproducibles tal cual; los tests y los comprobadores de `scripts/rules/` sí lo son.

## Procedencia de los datos

El corpus de `examples/rag-app` es **sintético por construcción**: fichas de productos ficticios generadas
con semilla fija, con la respuesta correcta conocida desde su generación. No mide calidad de dominio: mide si
la puerta detecta degradaciones. Coste real incurrido: 0 € (solo modelos locales); el coste que se publique
será siempre "coste declarado" con una tabla de precios pública y fechada.

## Cómo se ha construido

`docs/CONSTITUCION.md` (gobierno y gate), `docs/GOALS.yaml` (metas con umbral y comando), `docs/PLAN.md`
(fases), `docs/RULES.md` (reglas R1-R20), `docs/JOURNAL.md` (bitácora con cada número y su comando),
`docs/adr/` (decisiones), `docs/qa/` (hallazgos de la revisión adversaria de cada fase) y `CHANGELOG.md`.

Tres cosas no están en este repositorio, a propósito: el buzón de decisiones entre el agente constructor y
el autor (las referencias `Q-NNN` y `P-NNN` que aparecen en el código y en los documentos apuntan a él), las
instrucciones del agente y el estado local del gate, y la reserva de tests de QA (`tests/holdout/`), que
solo sirve mientras quien escribe el código no la ve.
