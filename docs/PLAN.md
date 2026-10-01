# Evalgate · plan de fases

> **Solo lectura para el agente.** Cambios de plan: propuesta `cambiar-plan` en `docs/PARA-SAMUEL.md`.
>
> Fases `F0..F10`. Equivalen a los hitos `H0..H9` de la hoja de reglas de investigación; se renumeran
> a "fase" por coherencia con `bloqueante_desde_fase` de `GOALS.yaml` y con `make done MILESTONE=N`.
> **NÚCLEO** = lo que hace el proyecto enseñable y defendible; sus metas bloquean.
> **AMPLIACIÓN** = lo que lo hace completo; sus metas nunca bloquean el núcleo y no empezarlas no es un fallo.
>
> Regla de cierre (CONSTITUCION §4.2 caso A): al terminar una fase, `make done MILESTONE=N`, presentar los
> números medidos y **parar**. La fase siguiente no se abre sin el visto bueno de Samuel.

---

## 1. Tabla de fases

| # | Nombre | Tipo | Carril | Entregable concreto | Criterio de salida (comando) | Tests exigidos | Metas que activa | Est. agente | Horas humanas irreducibles |
|---|---|---|---|---|---|---|---|---|---|
| **F0** | Contratos y esqueleto | NÚCLEO | **A · bloquea todo** | Layout de CONSTITUCION §7.5 con `src/evalgate/`; `pyproject.toml` con `requires-python="==3.12.*"`, `[tool.gate]` literal de `RULES.md` §4 y **cero dependencias**; `uv.lock`; `otel-semconv.lock`; `docs/spec/openai-openapi-<ver>.json` (snapshot descargado); `docs/spec/pricing-table.schema.json` derivado del contrato; `evals/report-hash-exclusions.yaml`; `docs/bench/protocol.md`; `Makefile` con los targets de CONSTITUCION §7.4; `PARA-SAMUEL.md` respondido en lo urgente | `make lint && make typecheck && pytest tests/contract -q` (valida que los 4 esquemas cargan y son JSON Schema 2020-12 válidos, y que `docs/CONTRACTS/**` es copia literal de `_comun/`, con 0 tests de negocio aún) | Nivel 0 + validación de esquemas | — | 10-14 h | **1,5-2 h** (D-01, D-02, D-03 y D-06 del global; Q-001, Q-002 y Q-003) |
| **F1** | Proxy tonto | NÚCLEO | A · secuencial | `/v1/chat/completions` no-streaming, passthrough byte a byte; `proxy/translate.py`; `examples/rag-app` mínimo; CLI `evalgate serve` | `make test-fast && make test-e2e -k adoption && make done MILESTONE=1` | Nivel 0, 1 (dominio de traducción), 3 (contrato OpenAPI), 5 (humo de adopción), holdout | G-OPENAI-CONTRACT, G-ADOPTION, G-FUNC-COV, G-LINE-COV | 8-12 h | 0,5 h |
| **F2** | **Streaming correcto** | NÚCLEO | A · secuencial | `proxy/streaming.py`: reenvío chunk a chunk + acumulador en paralelo, cierre de span en `finally`, detección de desconexión, contabilidad ante corte; corpus `tests/fixtures/sse/` con **los 12 casos límite** enumerados en §3 | `pytest tests/property/test_stream_accounting.py -q && make done MILESTONE=2` | Nivel 1 **TDD estricto** + Hypothesis (genera secuencias de chunks y un índice de corte) + nivel 3 (esquema SSE) | G-TOKENS-EXACT, G-TOKENS-STREAM, G-DISCONNECT | 20-30 h | 0,5 h |
| **F3** | Telemetría, almacén y degradación | NÚCLEO | A · secuencial | `telemetry/semconv/` generado desde `otel-semconv.lock`; exportador con cola **acotada y no bloqueante**; migraciones propias de ClickHouse (`create_schema:false`); contador `app.spans.dropped`; `make bench` con su protocolo | `make test-int -k "trace_lossless or degradation" && make bench PROFILE=proxy && make bench PROFILE=stream && make done MILESTONE=3` | Nivel 2 (testcontainers ClickHouse, **tumbando el contenedor a mitad del test**), nivel 3 (atributos OTel) | G-OTEL-CONTRACT, G-TRACE-0, G-TRACE-DEGRADE, G-LAT-PROXY, G-LAT-TTFT | 20-28 h | 0,5 h (D-03 y Q-005: ventana de máquina para los benchmarks) |
| **F4** | Precios versionados y contabilidad | NÚCLEO | **B · arranca tras F0** | `pricing/<YYYY-MM-DD>.yaml` con el formato del contrato; `pricing/TABLES.lock`; resolución por fecha; caché de prompt con precios propios de escritura y lectura; cambio de tarifa a mitad de periodo; conversión `fx` con fecha; `scripts/reconcile_invoice.py` | `make eval SUITE=pricing-repro && mutmut run --paths-to-mutate src/evalgate/pricing && python scripts/check_reconciliation.py && make done MILESTONE=4` | Nivel 1 **TDD estricto** + Hypothesis (coste nunca negativo, monotonía en tokens, aditividad del lote) | G-PRICE-REPRO, G-COST-RECONCILE, G-MUTATION | 14-20 h | **1-2 h** + 3-5 días de calendario de tráfico real (D-04 y D-05) |
| **F5** | Motor de evals, jueces y caché | NÚCLEO | **B · tras F4** | `evals/metrics/` (cada métrica, función pura); `evals/judges/` con caché por clave compuesta; `evals/runner.py`; golden set de 200 casos + subsuite de calibración de 60; `prompts/` con frontmatter de CONSTITUCION §7.6 | `make eval && make eval && evalgate cache stats && make done MILESTONE=5` | Nivel 1 TDD en `metrics/` y en la clave de caché. Los jueces **se miden, no se testean** | G-CACHE-HIT, G-CACHE-INVAL | 24-32 h | 0,5 h (Q-002 y Q-003 respondidas antes de empezar) |
| **F6** | La puerta | NÚCLEO | **C · arranca tras F0** | `stats/paired_bootstrap.py`, `stats/holm.py`, `gate/decision.py`, `evalgate eval compare`, tabla de salida y código de salida 0/1 | `make eval-compare-twice && make done MILESTONE=6` | Nivel 1 **TDD estricto, el más estricto del repo** + Hypothesis (antisimetría, `compare(a,a)` no bloquea) + validación contra resultados analíticos conocidos | G-DETERMINISM | 18-26 h | 0,5 h |
| **F7** | **Meta-evaluación** | NÚCLEO | Confluencia · exige F5 y F6 | `evalgate meta run-matrix / fp / mde / sensitivity / kappa`; `evals/reports/fp-matrix.parquet`; `evals/reports/meta-eval.json`; sección de números del README | `evalgate meta report --check && make done MILESTONE=7` | **Nivel 4 completo.** Aquí el proyecto entrega su tesis | G-GATE-FP, G-GATE-MDE, G-GATE-POWER, G-JUDGE-KAPPA | 20-28 h | **6-9 h** de etiquetado (Q-004) + 1 noche de máquina libre (Q-005) |
| **F8** | Deriva y panel | **AMPLIACIÓN** | **D · arranca tras F3** | `drift/detectors/` con calibración propia; dashboards generados con Grafana Foundation SDK (Python) → JSON en `dashboards/`, aprovisionados por fichero en `compose.yaml` | `evalgate drift calibrate && make report && make done MILESTONE=8` | Nivel 1 TDD en los detectores (son estadística pura) + nivel 5 humo del panel | G-DRIFT-FP, G-DRIFT-POWER | 14-20 h | 0,5 h |
| **F9** | E2E, autopuerta y publicación | NÚCLEO | A · último | `make test-e2e` completo; `EVALGATE_SELF_GATE=on` (retirada de la escotilla de arranque; **es la fase desde la que `scripts/rules/self_gate.py` marca rojo si sigue en `off`**, R16); `.github/workflows/gate.yml` **escrito y no activado**; README con los números medidos y el párrafo de posicionamiento frente a Langfuse; ADRs cerrados; vídeo de 60 s | `make done MILESTONE=9` | Nivel 5 completo + reserva (`tests/holdout/`) | G-GATE-BLOCK-EVIDENCE | 12-18 h | **2-3 h** (vídeo y capturas: D-08; licencia y visibilidad: D-07; git: Q-006) |
| **F10** | Exportación y contraste | **AMPLIACIÓN** | libre, tras F7 | `evalgate export parquet` (volcado de la tabla de spans a Parquet con esquema documentado); suite de contraste nocturno con DeepEval | `evalgate export parquet --check && make eval-refresh SUITE=deepeval-contrast` | Nivel 3 (esquema del Parquet) + nivel 4 nocturno | G-DEEPEVAL-CORR | 8-12 h | 0,5 h (autorizar `uv add deepeval`: Q-007) |
| **F11** | Adopción real en citebound-01 | **AMPLIACIÓN** | **E · tras F9** | evalgate delante del tráfico LLM de citebound-01 cambiando solo su variable de base URL; `evalgate eval compare` sobre informes de citebound; bloqueo real ante una regresión inyectada, documentado en JOURNAL | `make done MILESTONE=11` | Nivel 5 (e2e sobre citebound) + nivel 3 (`eval-report.schema.json`) | Ninguna nueva: G-ADOPTION y G-GATE-BLOCK-EVIDENCE se reutilizan sobre citebound sin bloquear | 8-14 h | 0,5-1 h (autorizar tocar citebound-01) |

---

## 2. Paralelismo: qué es real y qué no

**Carriles:**

- **A · estrictamente secuencial:** F0 → F1 → F2 → F3 → F9. Cada una necesita el binario de la anterior.
- **B:** F4 → F5. Arranca en cuanto F0 congela `docs/spec/pricing-table.schema.json` y está copiado
  `docs/CONTRACTS/eval-report.schema.json`.
- **C:** F6. Arranca en cuanto F0 congela el esquema del informe. **Es la razón de ser de F0:** congelar el
  esquema desbloquea la puerta sin esperar al motor de evals que la alimentará.
- **D:** F8. Arranca tras F3. Es ampliación: saltarla no impide F9.
- **Confluencias:** F7 exige B y C cerrados. F9 exige todo el núcleo. F10 exige F7.

**Regla operativa de paralelismo, sin git — no negociable:** dos agentes escribiendo a la vez en el mismo
directorio se pisan `STATE.md` y el hash de debounce del gate B. El paralelismo real exige **copias físicas
del directorio** (`evalgate-02.laneB/`) que Samuel fusiona a mano al cerrar el carril, o **sesiones
secuenciales alternando de carril**. Un solo agente escritor por directorio, siempre.

**Consecuencia honesta:** con un solo agente y un solo directorio, el paralelismo de la tabla es solo
*libertad de orden*, no reducción de horas. Las horas totales no bajan; lo que baja es el riesgo de quedarse
bloqueado esperando a una fase larga.

---

## 3. Los 12 casos límite de SSE que F2 debe cubrir

Fijados aquí para que el criterio de salida de F2 sea verificable y no negociable. Un fichero en
`tests/fixtures/sse/` por caso, y `scripts/rules/sse_corpus_coverage.py` falla si falta uno o si hay un
fixture sin test que lo consuma:

corte de cliente · corte de proveedor · chunk malformado · timeout a mitad · chunk final de `usage` ausente ·
`[DONE]` sin `usage` · unicode partido entre chunks · keep-alive vacío · error a mitad del stream ·
doble `[DONE]` · chunk con `finish_reason` inesperado · stream de longitud 0.

---

## 4. ADRs obligatorios, por fase

| Fase | ADR |
|---|---|
| F0 | LiteLLM como librería y no como proxy · Evalgate frente a Bifrost (Python frente a Go) · Evalgate frente a Langfuse v4 · modelo de datos OTel interno propio con capa de traducción · Python 3.12 porque MWAA no ofrece más |
| F2 | Contabilidad de tokens ante desconexión del cliente |
| F3 | ClickHouse como almacén y política de degradación ante su caída |
| F4 | Tablas de precios inmutables y fechadas |
| F5 | Diseño de la clave de caché de jueces · corpus sintético autoverificable y su procedencia |
| F6 | Bootstrap pareado y corrección por comparaciones múltiples (**Holm-Bonferroni**, el defecto del contrato: controla la tasa de error por familia y es uniformemente más potente que Bonferroni. Motivo desarrollado en `RULES.md` §3.8) |
| F7 | Matriz de falsos positivos precomputada, y por qué el experimento en vivo es inviable |
| F9 | Endpoint Bedrock de **entrada** retirado del alcance · exportador Iceberg degradado a Parquet plano |

---

## 5. Presupuesto honesto

| Bloque | Horas de agente | Horas humanas irreducibles |
|---|---|---|
| Núcleo (F0-F7, F9) | **136-188 h** | **13-19 h** + 3-5 días de calendario (tráfico de facturación) + 1 noche de máquina para `run-matrix` |
| Ampliación (F8, F10) | 22-32 h | 1 h |
| **Total** | **158-220 h** | **14-20 h** |

**El timebox del mapa de conjunto (3-4 semanas) está infravalorado entre 3 y 4 veces.** A 10-15 h por semana,
el núcleo son **10-14 semanas**; con las ampliaciones, 12-16. Este número está escrito antes de empezar
justamente para que no se descubra en la semana 5. Si las horas semanales reales de Samuel (**D-01** del
global, que además reparte entre los cinco proyectos) son menores, la respuesta correcta es recortar alcance
por fases completas, no comprimir estimaciones.

Las horas humanas **no bajan con un agente más rápido**. Las dos grandes son el etiquetado de 100 casos para
la kappa del juez (6-9 h, F7) y la conciliación contra factura real (1-2 h de trabajo más 3-5 días de espera
de calendario, F4). Ambas se piden en la **hora 1**, no cuando bloquean.

### Punto de parada digno

**Cerrar F0-F7 ya hace el proyecto enseñable y defendible.** Ahí están los cuatro diferenciadores que ninguna
plataforma da llave en mano, y los tres con número medido:

1. Contabilidad de tokens correcta ante desconexión del cliente en streaming (F2, G-DISCONNECT).
2. Tablas de precios inmutables y fechadas que hacen reproducible un informe de coste de hace tres meses
   (F4, G-PRICE-REPRO).
3. Meta-evaluación: kappa del juez, tasa de falsos positivos y efecto mínimo detectable, los tres medidos
   (F7, G-JUDGE-KAPPA, G-GATE-FP, G-GATE-MDE, G-GATE-POWER).
4. Política declarada de degradación cuando el almacén de trazas cae (F3, G-TRACE-DEGRADE).

**F9 lo hace publicable** (e2e, autopuerta, README con los números, evidencia del bloqueo). Es barata
—12-18 h— y sin ella el trabajo existe pero no se ve; si hay que elegir, F9 antes que F8.

**F8 y F10 son prescindibles sin coste narrativo.** Un panel de Grafana no es un argumento: cualquiera lo
tiene. La deriva es interesante pero es un quinto diferenciador cuando ya hay cuatro.

Si el tiempo se agota antes de F7, el recorte correcto **no** es hacer F7 a medias: es cerrar F0-F6 y publicar
el repo diciendo con todas las letras que la meta-evaluación está pendiente. Publicar "faithfulness 0,91" sin
la kappa del juez que lo produjo es exactamente lo que este proyecto denuncia.
