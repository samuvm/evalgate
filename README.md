# Evalgate · puerta de calidad LLM

> **Un evaluador no evaluado es un adorno.** Evalgate es una puerta de calidad para aplicaciones LLM que
> publica sus propias tasas de error: la concordancia de su juez con un humano, su tasa de falsos positivos y
> el efecto mínimo que es capaz de detectar, los tres medidos.

**Estado:** en construcción, F6 de 10 cerrada (proxy, telemetría, precios, evals y la puerta); F7, la meta-evaluación, pendiente
. El núcleo (F0-F7 y F9) todavía no está completo, y este README solo afirma lo que ya está
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

![Diagrama animado de Evalgate: la app, el proxy y el proveedor; contabilidad de tokens, telemetría, precios, evaluación emparejada y la puerta](docs/animacion/evalgate-flujo.gif)

Nueve escenas en bucle, cada una marcada como hecha, en curso o pendiente. Las cifras que aparecen dentro
(tokens, tarifas, coste) son valores de ejemplo para ilustrar el flujo, no mediciones: las mediciones están
en [Números medidos](#números-medidos). El código de la animación está en `docs/animacion/`; se abre
sirviendo esa carpeta (`python -m http.server -d docs/animacion`) y carga React desde un CDN.

El mismo flujo, en estático:

```
  tu app ──► evalgate (proxy) ──► proveedor compatible con OpenAI (hoy: Ollama)
                  │
                  ├─► registro de uso: tokens y coste, también si el cliente corta   [F2, cerrada]
                  ├─► traza OTel ──► cola acotada ──► ClickHouse                     [F3, cerrada] 
                  │
  informe A ─┐
             ├─► evalgate eval compare ──► exit 0 | 1 para CI                        [F5-F6, cerradas]  
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
Hardware de referencia: MacBook Pro M4 Max, 36 GB de memoria unificada.

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
| F3 | `G-ADOPTION` | lineas_de_diff=0, n_lineas=8 | 2026-10-06 | `evals/reports/gate-F3.json` |
| F3 | `G-DISCONNECT` | ratio=1, n=198 | 2026-10-06 | `evals/reports/gate-F3.json` |
| F3 | `G-FUNC-COV` | 0 | 2026-10-06 | `evals/reports/gate-F3.json` |
| F3 | `G-LAT-PROXY` | 5,29 | 2026-10-06 | `evals/reports/gate-F3.json` |
| F3 | `G-LAT-TTFT` | 3,51 | 2026-10-06 | `evals/reports/gate-F3.json` |
| F3 | `G-LINE-COV` | 99,34 | 2026-10-06 | `evals/reports/gate-F3.json` |
| F3 | `G-OPENAI-CONTRACT` | ratio=1,00, n=7 | 2026-10-06 | `evals/reports/gate-F3.json` |
| F3 | `G-OTEL-CONTRACT` | ratio=1, n=25 | 2026-10-06 | `evals/reports/gate-F3.json` |
| F3 | `G-TOKENS-EXACT` | ratio=1, n=5 | 2026-10-06 | `evals/reports/gate-F3.json` |
| F3 | `G-TOKENS-STREAM` | delta_con_usage=0 | 2026-10-06 | `evals/reports/gate-F3.json` |
| F3 | `G-TRACE-0` | perdidos=0, rps=50, servidas=6000 | 2026-10-06 | `evals/reports/gate-F3.json` |
| F3 | `G-TRACE-DEGRADE` | -0,08 | 2026-10-06 | `evals/reports/gate-F3.json` |
| F4 | `G-ADOPTION` | lineas_de_diff=0, n_lineas=8 | 2026-10-08 | `evals/reports/gate-F4.json` |
| F4 | `G-DISCONNECT` | ratio=1, n=209 | 2026-10-08 | `evals/reports/gate-F4.json` |
| F4 | `G-FUNC-COV` | 0 | 2026-10-08 | `evals/reports/gate-F4.json` |
| F4 | `G-LAT-PROXY` | 5,46 | 2026-10-08 | `evals/reports/gate-F4.json` |
| F4 | `G-LAT-TTFT` | 3,45 | 2026-10-08 | `evals/reports/gate-F4.json` |
| F4 | `G-LINE-COV` | 99,35 | 2026-10-08 | `evals/reports/gate-F4.json` |
| F4 | `G-MUTATION` | 88,58 | 2026-10-08 | `evals/reports/gate-F4.json` |
| F4 | `G-OPENAI-CONTRACT` | ratio=1,00, n=7 | 2026-10-08 | `evals/reports/gate-F4.json` |
| F4 | `G-OTEL-CONTRACT` | ratio=1, n=25 | 2026-10-08 | `evals/reports/gate-F4.json` |
| F4 | `G-PRICE-REPRO` | 0,00 | 2026-10-08 | `evals/reports/gate-F4.json` |
| F4 | `G-TOKENS-EXACT` | ratio=1, n=5 | 2026-10-08 | `evals/reports/gate-F4.json` |
| F4 | `G-TOKENS-STREAM` | delta_con_usage=0 | 2026-10-08 | `evals/reports/gate-F4.json` |
| F4 | `G-TRACE-0` | perdidos=0, rps=50, servidas=6000 | 2026-10-08 | `evals/reports/gate-F4.json` |
| F4 | `G-TRACE-DEGRADE` | -0,17 | 2026-10-08 | `evals/reports/gate-F4.json` |
| F5 | `G-ADOPTION` | lineas_de_diff=0, n_lineas=8 | 2026-10-08 | `evals/reports/gate-F5.json` |
| F5 | `G-CACHE-HIT` | 0,00 | 2026-10-08 | `evals/reports/gate-F5.json` |
| F5 | `G-CACHE-INVAL` | ratio=1, n=63 | 2026-10-08 | `evals/reports/gate-F5.json` |
| F5 | `G-DISCONNECT` | ratio=1, n=212 | 2026-10-08 | `evals/reports/gate-F5.json` |
| F5 | `G-FUNC-COV` | 0 | 2026-10-08 | `evals/reports/gate-F5.json` |
| F5 | `G-LAT-PROXY` | 6,63 | 2026-10-08 | `evals/reports/gate-F5.json` |
| F5 | `G-LAT-TTFT` | 3,96 | 2026-10-08 | `evals/reports/gate-F5.json` |
| F5 | `G-LINE-COV` | 99,35 | 2026-10-08 | `evals/reports/gate-F5.json` |
| F5 | `G-MUTATION` | 88,58 | 2026-10-08 | `evals/reports/gate-F5.json` |
| F5 | `G-OPENAI-CONTRACT` | ratio=1,00, n=7 | 2026-10-08 | `evals/reports/gate-F5.json` |
| F5 | `G-OTEL-CONTRACT` | ratio=1, n=25 | 2026-10-08 | `evals/reports/gate-F5.json` |
| F5 | `G-PRICE-REPRO` | 0,00 | 2026-10-08 | `evals/reports/gate-F5.json` |
| F5 | `G-TOKENS-EXACT` | ratio=1, n=5 | 2026-10-08 | `evals/reports/gate-F5.json` |
| F5 | `G-TOKENS-STREAM` | delta_con_usage=0 | 2026-10-08 | `evals/reports/gate-F5.json` |
| F5 | `G-TRACE-0` | perdidos=0, rps=50, servidas=6000 | 2026-10-08 | `evals/reports/gate-F5.json` |
| F5 | `G-TRACE-DEGRADE` | -0,20 | 2026-10-08 | `evals/reports/gate-F5.json` |
| F6 | `G-ADOPTION` | lineas_de_diff=0, n_lineas=8 | 2026-10-08 | `evals/reports/gate-F6.json` |
| F6 | `G-CACHE-HIT` | 0,00 | 2026-10-08 | `evals/reports/gate-F6.json` |
| F6 | `G-CACHE-INVAL` | ratio=1, n=63 | 2026-10-08 | `evals/reports/gate-F6.json` |
| F6 | `G-DETERMINISM` | ratio=1, n=3 | 2026-10-08 | `evals/reports/gate-F6.json` |
| F6 | `G-DISCONNECT` | ratio=1, n=217 | 2026-10-08 | `evals/reports/gate-F6.json` |
| F6 | `G-FUNC-COV` | 0 | 2026-10-08 | `evals/reports/gate-F6.json` |
| F6 | `G-LAT-PROXY` | 6,97 | 2026-10-08 | `evals/reports/gate-F6.json` |
| F6 | `G-LAT-TTFT` | 3,80 | 2026-10-08 | `evals/reports/gate-F6.json` |
| F6 | `G-LINE-COV` | 99,35 | 2026-10-08 | `evals/reports/gate-F6.json` |
| F6 | `G-MUTATION` | 88,58 | 2026-10-08 | `evals/reports/gate-F6.json` |
| F6 | `G-OPENAI-CONTRACT` | ratio=1,00, n=7 | 2026-10-08 | `evals/reports/gate-F6.json` |
| F6 | `G-OTEL-CONTRACT` | ratio=1, n=25 | 2026-10-08 | `evals/reports/gate-F6.json` |
| F6 | `G-PRICE-REPRO` | 0,00 | 2026-10-08 | `evals/reports/gate-F6.json` |
| F6 | `G-TOKENS-EXACT` | ratio=1, n=5 | 2026-10-08 | `evals/reports/gate-F6.json` |
| F6 | `G-TOKENS-STREAM` | delta_con_usage=0 | 2026-10-08 | `evals/reports/gate-F6.json` |
| F6 | `G-TRACE-0` | perdidos=0, rps=50, servidas=6000 | 2026-10-08 | `evals/reports/gate-F6.json` |
| F6 | `G-TRACE-DEGRADE` | 0,08 | 2026-10-08 | `evals/reports/gate-F6.json` |
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
| `docs/` | Metas, reglas, contratos y ADR |

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

`docs/GOALS.yaml` (metas con umbral y comando), `docs/RULES.md` (reglas R1-R20), `docs/adr/` (decisiones)
y `CHANGELOG.md`.

La suite reservada (`tests/holdout/`) no está en este repositorio, a propósito: es privada para que el código
no se pueda ajustar contra ella.
