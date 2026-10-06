# Changelog

Formato: [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/).
Versionado: [SemVer](https://semver.org/lang/es/).

> **Se escribe una entrada por fase cerrada, y solo cuando `make done MILESTONE=N` pasa en verde.**
> Cada entrada lleva **los números medidos**, no las intenciones: la meta, su valor, su `n` y el artefacto
> de `evals/reports/` de donde sale. Un cambio sin número no es una entrada de changelog.
>
> Reglas: append; nada se reescribe. Cambiar un contrato de `docs/CONTRACTS/` es un evento consciente y
> **siempre** lleva su entrada aquí, con la versión del contrato. Los ADR se referencian por número.

---

## [No publicado]

### Añadido
- Metas medibles en `docs/GOALS.yaml`, reglas R1–R20 en `docs/RULES.md`, ADR en `docs/adr/` (con
  `000-plantilla.md`) y estado del gate en `.gate/STATE.md`.
- Contratos que aplican a este proyecto, en `docs/CONTRACTS/`: `eval-report.schema.json`, `otel-genai.md`,
  `pricing-table.md`, `retrieval-metrics.md`, más `goals.schema.json` y `README.md`.
- `R19` (check cruzado `[tool.gate]` ↔ `GOALS.yaml`) y `R20` (`docs/CONTRACTS/` fijado por sha256,
  `docs/spec/` para lo propio), con su §7 en `docs/RULES.md`.

### Contratos
- `retrieval-metrics.md` (§4: Holm por defecto, con el motivo), `eval-report.schema.json` (admite `holm`) y
  el nuevo `goals.schema.json`.
- `docs/GOALS.yaml` reescrito a la forma canónica del contrato: `version`/`proyecto`/`metas`, umbral
  estructurado `{operador, valor, unidad}`, `tipo`/`requiere`/`propuesta_admisible` en lugar de `clase`,
  y `comparacion.correccion_multiple: holm`. Sin cambio de número en ninguna meta salvo dos cambios de
  **unidad** declarados: `G-LINE-COV` 0.90 → 90 (porcentaje) y `G-MUTATION` 0.75 → 75 (porcentaje), que
  es la escala en que ya estaban `[tool.gate]`, `coverage.py` y `mutmut`; y `G-GATE-MDE` 0.08 → 8 pp,
  que es la escala del campo `mde_pp` que la meta lee.

### Pendiente
- F0. Nada medido todavía: ninguna meta de `docs/GOALS.yaml` tiene número.

## [0.4.0] · F3 · telemetría, almacén y degradación · 2026-10-06

### Añadido
- `telemetry/model.py`: `LlmCall`, el modelo interno de una llamada. Nombres propios, ni uno `gen_ai.*`, y
  ningún campo que pueda llevar el texto de un prompt o de una respuesta (R6 por construcción).
- `telemetry/translate.py`: el único módulo que conoce los nombres externos, y los toma de
  `telemetry/semconv/`, generado desde el commit de `otel-semconv.lock` (v1.41.1).
- `telemetry/processor.py`: cola acotada propia. La petición solo hace `put_nowait`; cada span acaba
  exportado o descartado **y contado** en `app.spans.dropped`. No hay una tercera salida.
- `telemetry/rows.py`, `migrations.py`, `exporters/clickhouse.py`, `pipeline.py`: escritura directa en
  ClickHouse sobre la tabla `otel_traces` del Collector, con migraciones propias numeradas e inmutables
  (sha256 en `schema_migrations`), conexión perezosa y rehecha tras cada fallo.
- `proxy/streaming.py`: el registro dice qué modelo respondió y cuándo llegó el primer chunk con texto
  (reloj inyectado). `proxy/translate.py`: `request_facts` y `llm_call`, puras. `proxy/app.py`: sumidero
  `on_call`, llamado y nunca esperado.
- CLI: `evalgate serve --clickhouse` y `evalgate migrate`.
- Nivel 2, el primero del repo: `tests/integration/` con ClickHouse 26.4 real fijado por digest.
- `scripts/bench.py` y `bench_stub.py`: el protocolo de `docs/bench/protocol.md`, con tres procesos y las
  trazas activas contra ClickHouse real.
- Reglas mecánicas nuevas, probadas en negativo: `rules/no_genai_literals.py` (R5),
  `rules/no_blocking_export.py` (R1) y `gen_semconv.py --check`.

### Corregido
- 8 tests del corpus SSE comparaban el registro entero y exigían sin decirlo `model=None`. Se amplió su
  registro esperado con el modelo que declara cada fixture; ninguna aserción quitada.

### Números medidos
| Meta | Umbral | Medido | n | Artefacto |
|---|---|---|---|---|
| G-OTEL-CONTRACT | == 1,0 | **1,0** | 25 spans en el comando de la meta; 1000 en la suite (perfil nightly) | `.gate/gate-status.json` |
| G-TRACE-0 | == 0 perdidos | **0** | 6000 peticiones, 50 rps durante 120 s, contadas como filas en ClickHouse | `.gate/gate-status.json` |
| G-TRACE-DEGRADE | Δp95 <= 5 ms y 100 % servidas | **−0,084 ms**, 2000/2000 servidas, 1000 exportados + 1000 descartados y contados | 1000 + 1000 peticiones, `docker kill` en la 50 de la segunda fase | `evals/reports/degradation-2026-10-06.json` |
| G-LAT-PROXY | p95 <= 30 ms | **5,29 ms** (p50 4,04 · p99 6,66) | 500 + 50 de calentamiento por brazo | `evals/reports/bench-proxy-2026-10-06.json` |
| G-LAT-TTFT | p95 <= 15 ms | **3,51 ms** (p50 2,84 · p99 3,67) | 500 + 50 de calentamiento por brazo | `evals/reports/bench-stream-2026-10-06.json` |

Latencias medidas con las trazas ACTIVAS contra ClickHouse real, con la máquina sin otra carga
(`exclusive_window: true`), Apple M4 Max, macOS 27.0.1. Los tres últimos números son de la tanda que ejecuta
el propio `make done MILESTONE=3`.
También: G-LINE-COV 99,34 %, G-FUNC-COV 0, suite reservada 349/349, suite 256 passed (perfil nightly).

### Decisiones
- ADR-012 · ClickHouse como almacén, escrito desde el proxy con cola acotada propia. Se descartó el
  Collector: con él en medio, el proxy recibe SUCCESS con ClickHouse caído y el contador no mide.
- `gen_ai.response.model` se omite solo cuando el proveedor nunca lo dijo; nunca se copia del modelo pedido.
- `otel-semconv.lock` declara las tres rutas (`gen-ai`, `error`, `server`) del mismo commit.

### Contratos
- Sin cambios en `docs/CONTRACTS/`. Desvío declarado respecto a otel-genai §4: `gen_ai.response.model` es
  "obligatorio cuando el proveedor lo declara".

## [0.3.0] · F2 · streaming correcto · 2026-09-20

### Añadido
- `proxy/streaming.py`: reenvío chunk a chunk con acumulador en paralelo. Enmarca sobre **bytes** (busca
  `\n\n` en un búfer) y decodifica después, que es lo que permite reensamblar un carácter partido entre dos
  chunks de red. `relay` cierra la contabilidad en un `finally` y sobrevive a `CancelledError` (R2).
- Corpus `tests/fixtures/sse/`: los 12 casos límite declarados en `CASES.yaml` más `13-reasoning-tokens.sse`,
  transcripción real de Ollama sin editar, con su procedencia en `CASES.yaml`. Los 12 son un **suelo, no un
  techo**: los extras se admiten con motivo y procedencia, y se les exige lo mismo que a los 12.
- Montaje en `proxy/app.py`: `StreamingResponse` con las cabeceras por pares, sumidero `on_usage` que se
  **llama y nunca se espera** y no puede tumbar la petición (R1), y `translate.record_of_completion` para
  el camino no-streaming, que devuelve `None` cuando el cuerpo no es una respuesta de chat.
- `AccountedStream`: la respuesta en flujo cierra su cuerpo **dentro de la llamada ASGI**, en un `finally`.
- Cuatro reglas mecánicas nuevas o ampliadas en el gate, las cuatro probadas en negativo antes de darlas
  por buenas: `rules/finally_on_generators.py` (R2 por AST en el módulo),
  `rules/sse_corpus_coverage.py` (los 12 casos, letra a letra contra `CASES.yaml`, y ningún fixture
  huérfano), `rules/stream_closed_in_request.py` (R2 en el montaje) y las tramas SSE dentro de
  `G-OPENAI-CONTRACT`.

### Corregido
- **Tokens de razonamiento contabilizados como cero.** `qwen3.5` manda el texto en `delta.reasoning` con
  `delta.content` **vacío** y lo factura igual en `usage.completion_tokens`: un acumulador que solo mire
  `content` registra 0 tokens de algo ya pagado. Se cuenta aparte y los dos recuentos se **suman**, no se
  concatenan los textos (concatenar pegaría la última palabra de uno con la primera del otro).
- **Con el cliente cortado, el registro salía fuera de la petición** (el único defecto de F2 que encontró
  la suite reservada). `StreamingResponse` recorre el cuerpo con `async for`, y `async for` no cierra lo
  que recorre: al colgar el cliente, starlette cancelaba la tarea con el generador suspendido en su `yield`
  y el `finally` de `relay` —correcto— corría cuando el recolector quisiera. El contenido del registro
  siempre fue bueno; lo que fallaba era **cuándo**.
- **El snapshot de OpenAI rechazaba lo que manda OpenAI** (ADR-011): se declara `openapi: 3.1.0` y usa
  111 veces `nullable: true`, que es palabra de 3.0 y ningún validador de JSON Schema respeta. Medido:
  32 de 34 tramas reales inválidas leyendo el snapshot tal cual, **0 de 34** honrando `nullable`.

### Cambiado
- `G-TOKENS-STREAM`: la exactitud se exige donde es verificable, contra el bloque `usage` del proveedor.
  **`delta_estimado` deja de publicarse**; medía el estimador contra el mismo tokenizador que usa el proxy,
  daba 0 por construcción y se leía como exactitud de facturación. Sin `usage`, el registro viaja declarado
  como `estimated`.
- Se retiran los dos tests de F1 que daban por bueno el `501` a `stream: true`. No se borran: se
  sustituyen por el comportamiento que F2 entrega.

### Números medidos
| Meta | Umbral | Medido | n | Artefacto |
|---|---|---|---|---|
| G-DISCONNECT | == 1,0 | **1,0** | 222 cortes (215 en el relevo + 7 en el montaje) | `.gate/gate-status.json` |
| G-TOKENS-EXACT | == 1,0 | **1,0** | 5 respuestas grabadas (3 reales de Ollama) | `.gate/gate-status.json` |
| G-TOKENS-STREAM | delta con `usage` == 0 | **0** | perfil nightly | `.gate/gate-status.json` |
| G-OPENAI-CONTRACT | >= 1,0 | **1,0** | 7 | `.gate/gate-status.json` |
| G-ADOPTION | == 0 líneas | **0** | 8 líneas | `.gate/gate-status.json` |
| G-LINE-COV | >= 90 % | **98,7 %** | — | `.gate/gate-status.json` |
| G-FUNC-COV | == 0 | **0** | — | `.gate/gate-status.json` |
| G-MUTATION (informativa hasta F4) | >= 75 % | **88,96 %** | 145 / 163 | `evals/reports/mutation-F2.json` |
| Suite completa (perfil nightly) | — | **176 passed** | — | `.gate/gate-status.json` |
| Suite reservada `tests/holdout/` (privada) | 0 fallos | **349 passed** | 349 | `.gate/gate-status.json` |

Los 15 mutantes supervivientes se analizaron uno a uno: son equivalentes (`_done = False` → `None`,
`find` → `rfind` con un lector orientado a líneas, ramas que acaban las dos en `continue`) o solo
alcanzables con tramas de varios `data:`, que el estándar manda concatenar y ningún proveedor del alcance
parte. **No se escriben tests para matarlos:** un test cuyo único fin es subir el porcentaje es el adorno
que este repo dice no publicar.

El mismo día del cierre se amplió `G-DISCONNECT` al montaje: su comando incluye ahora
`tests/contract/test_stream_disconnect_accounting.py` y sus cortes **entran en el número**, que por eso
pasa de 209 a 222. Cambiar solo el comando no bastaba: medido, el comando ampliado seguía imprimiendo
`n=208` —idéntico al fichero de propiedad a solas— porque un test que solo pasa no aporta casos al
contador. La fase se volvió a cerrar con la meta ya redefinida, y este número es el de esa ejecución.

### Decisiones
- ADR-010 · Contabilidad ante desconexión del cliente. Hueco escrito a propósito: solo se lee
  `delta.reasoning`; DeepSeek y vLLM usan `reasoning_content` y entrarán con su fixture, no con un `or`
  escrito hoy a ciegas sobre un proveedor que este proyecto no usa.
- ADR-011 · `nullable` del snapshot de OpenAI, traducido a unión con `null` y al `enum`. El snapshot sigue
  byte a byte el descargado y el motivo está escrito **como test**, no como comentario.

### Contratos
- Sin cambios en `docs/CONTRACTS/`. `docs/spec/openai-openapi-2.3.0.json` sigue pineado y sin editar: la
  traducción de `nullable` vive en el validador (ADR-011), no en el fichero.

## [0.2.0] · F1 · proxy tonto · 2026-09-12

### Añadido
- Proxy `/v1/chat/completions` no-streaming en passthrough: `proxy/app.py` (FastAPI, I/O y montaje),
  `proxy/translate.py` (puro: URL de salida, cabeceras, detección de `stream`, normalización) y CLI
  `evalgate serve`. `stream: true` responde 501 a propósito hasta F2.
- `examples/rag-app`: cliente de demostración con corpus sintético, sin un solo import de `src/evalgate/`
  (R13, verificado por AST en `scripts/rules/example_is_client.py`). La adopción cuesta `OPENAI_BASE_URL`.
- Normalización mínima declarada (ADR-007): se añaden con `null` los campos que el esquema de OpenAI exige
  y Ollama omite (`choices[].logprobs`, `choices[].message.refusal`), y solo entonces la respuesta lleva
  `x-evalgate-normalized`. Con el cuerpo ya conforme, los bytes salen intactos.
- Suite reservada `tests/holdout/` (privada, no se publica, para que no se pueda ajustar contra ella):
  318 tests.
- `make mutation` operativo sobre una copia sin la suite reservada (ADR-008); es el comando de `G-MUTATION`.

### Corregido
- **Los 12 fallos de la suite reservada, reducidos a 4 causas raíz**, reproducidos antes de tocar el código
  con 22 casos propios en `tests/unit/proxy/test_translate.py` y
  `tests/contract/test_proxy_header_fidelity.py`:
  - Las cabeceras se copiaban a un `dict`: la petición perdía el primer valor de un campo repetido y la
    respuesta fundía dos `Set-Cookie` en una línea, corrompiendo la cookie. Ahora son líneas ordenadas, no
    un diccionario (**ADR-009**).
  - La lista hop-by-hop era fija: ignoraba los campos que nombra `Connection` en cada mensaje, en los dos
    sentidos (RFC 9110 §7.6.1).
  - `x-evalgate-normalized` del proveedor se reenviaba: podía firmar en nombre de evalgate una
    normalización que no había ocurrido, en las seis combinaciones 200/400/500 × on/off.
  - La query string del cliente no llegaba al proveedor y el `Date`/`Server` del proveedor se reenviaban,
    así que uvicorn añadía los suyos y salían dos líneas de cada uno.

### Números medidos
| Meta | Umbral | Medido | n | Artefacto |
|---|---|---|---|---|
| G-OPENAI-CONTRACT | >= 1.0 ratio | 1.0 | 5 respuestas validadas | `.gate/gate-status.json` |
| G-ADOPTION | == 0 líneas de diff | 0 | 8 preguntas de `examples/rag-app` | `.gate/gate-status.json` |
| G-LINE-COV | >= 90 % | 100,0 % | paquetes `[tool.gate].testable` | `/tmp/cov.json#$.totals.percent_covered` |
| G-FUNC-COV | == 0 | 0 funciones públicas sin test | — | `.gate/gate-status.json` |
| G-MUTATION (informativa, bloquea desde F4) | >= 75 % | 89,66 % (26 muertos / 29) | 29 mutantes | `evals/reports/mutation-F1.json#$.killed_pct` |

| Qué | Valor | n | Artefacto |
|---|---|---|---|
| Suite completa (unit + property + contract), perfil `nightly` | 101 / 101 en 3,16 s | 101 | `.gate/gate-status.json` |
| **Suite reservada `tests/holdout/`** | **318 / 318** en 3,03 s (antes: 12 fallos) | 318 | `.gate/gate-status.json` |
| Inventario de tests | 11 ficheros, 62 tests, regresiones = 0 | — | `.gate/test-inventory.json` |
| Deuda en `src/` | 0 (`TODO`/`FIXME`/`XXX`), 0 escapes en tests | — | `.gate/gate-status.json` |

### Decisiones
- ADR-007 · normalización mínima declarada con cabecera · ADR-008 · mutación en copia sin la suite
  reservada · **ADR-009 · cabeceras como líneas ordenadas, no como diccionario**.

### Contratos
- Sin cambios en `docs/CONTRACTS/`. `docs/spec/openai-openapi-2.3.0.json` sigue pineado, sin desvíos nuevos
  respecto a ADR-006.

## [0.1.0] · F0 · contratos y esqueleto · 2026-09-10

### Añadido
- Esqueleto del repositorio con `src/evalgate/`; `pyproject.toml` con `requires-python = "==3.12.*"`,
  `[tool.gate]` literal de RULES §4.1 y 14 dependencias, todas `==` (R18); `uv.lock`; CPython 3.12.12
  gestionado por uv.
- Contratos propios en `docs/spec/`: `pricing-table.schema.json`, `openai-openapi-2.3.0.json` (snapshot
  descargado, commit `b5362da0…`) con su `.lock`, y el manifiesto sha256 de `docs/CONTRACTS/` (R20).
- `otel-semconv.lock` → `open-telemetry/semantic-conventions@v1.41.1` (ADR-005).
- `evals/report-hash-exclusions.yaml`, `docs/bench/protocol.md`, `Makefile`.
- Scripts del gate: `done.py` (definición de hecho), `check_function_coverage.py`, `check_gate_config.py`
  (R19), `rules/self_gate.py` (R16), `rules/pins.py` (R18), `test_inventory.py`, `debt.py`, `save.sh`.
- Primer código de dominio: `pricing.lookup.price_at` (TDD: rojo por aserción → verde).

### Números medidos
| Qué | Valor | n | Artefacto |
|---|---|---|---|
| Tests en verde (unit + contract) | 31 / 31 | 31 | `.gate/gate-status.json` |
| Duración de `make gate-fast` | 0,73 s (presupuesto < 20 s) | 1 ejecución, 2026-09-10 | `make gate-fast` |
| G-LINE-COV (informativa, bloquea desde F1) | 93,94 % | 1 módulo | `/tmp/cov.json#$.totals.percent_covered` |
| G-FUNC-COV (informativa, bloquea desde F1) | 1 función sin test de propiedad (`price_at`) | 1 | `.gate/gate-status.json` |

### Decisiones
- ADR-001 Python 3.12 · ADR-002 LiteLLM nunca como proxy · ADR-003 frente a Bifrost · ADR-004 frente a
  Langfuse v4 · ADR-005 modelo OTel interno y pin v1.41.1 · ADR-006 desvíos declarados respecto a
  los contratos.

### Contratos
- Sin cambios en `docs/CONTRACTS/`. Desvíos locales documentados en ADR-006 (pin OTel, Ollama 0.33.3).

<!--
Plantilla de una entrada de fase cerrada:

## [0.3.0] · F3 · telemetría, almacén y degradación · AAAA-MM-DD

### Añadido
- ...

### Números medidos
| Meta | Umbral | Medido | n | Artefacto |
|---|---|---|---|---|
| G-LAT-PROXY | <= 30 ms | 9,6 ms (p95) | 500 | evals/reports/bench-proxy-AAAA-MM-DD.json |
| G-TRACE-0 | == 0 | 0 spans perdidos | 50 rps / 120 s | .gate/gate-status.json |

### Decisiones
- ADR-007 · ClickHouse como almacén y política de degradación.

### Contratos
- Sin cambios. `otel-semconv.lock` en v1.42.0.
-->
