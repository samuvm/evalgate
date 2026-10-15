# Hoja de ruta

El proyecto avanza por fases. Una fase se cierra solo cuando `make done MILESTONE=N` sale en verde: el
gate lee de `docs/GOALS.yaml` qué metas bloquean desde esa fase y las mide. Las fases de **ampliación**
nunca bloquean el núcleo.

| Fase | Nombre | Tipo | Entregable | Metas que activa | Estado |
|---|---|---|---|---|---|
| F0 | Contratos y esqueleto | núcleo | Contratos y esquemas, `pyproject.toml` y `uv.lock` fijados, protocolo de benchmark, `Makefile` con los targets del gate | — | cerrada |
| F1 | Proxy transparente | núcleo | `/v1/chat/completions` sin streaming, byte a byte; `examples/rag-app`; `evalgate serve` | G-OPENAI-CONTRACT, G-ADOPTION, G-FUNC-COV, G-LINE-COV | cerrada |
| F2 | Streaming correcto | núcleo | Reenvío chunk a chunk con acumulador en paralelo, contabilidad ante corte; corpus SSE de 12 casos límite (`tests/fixtures/sse/CASES.yaml`) | G-TOKENS-EXACT, G-TOKENS-STREAM, G-DISCONNECT | cerrada |
| F3 | Telemetría, almacén y degradación | núcleo | Convenciones OTel generadas desde `otel-semconv.lock`; exportador con cola acotada y no bloqueante; migraciones de ClickHouse; `make bench` | G-OTEL-CONTRACT, G-TRACE-0, G-TRACE-DEGRADE, G-LAT-PROXY, G-LAT-TTFT | cerrada |
| F4 | Precios versionados | núcleo | `pricing/<YYYY-MM-DD>.yaml` sellados en `TABLES.lock`, resolución por fecha, caché de prompt con precios propios, tipo de cambio fechado | G-PRICE-REPRO, G-COST-RECONCILE, G-MUTATION | cerrada |
| F5 | Motor de evaluación, jueces y caché | núcleo | Métricas puras, jueces con caché por clave compuesta, golden set de 200 casos, prompts versionados | G-CACHE-HIT, G-CACHE-INVAL | cerrada |
| F6 | La puerta | núcleo | Bootstrap pareado, Holm, `evalgate eval compare` con salida 0/1/2 | G-DETERMINISM | cerrada |
| F7 | Meta-evaluación | núcleo | `evalgate meta run-matrix / fp / mde / sensitivity / kappa`; la puerta medida contra sí misma | G-GATE-FP, G-GATE-MDE, G-GATE-POWER, G-JUDGE-KAPPA | medida y publicada en rojo (tres de cuatro metas bajo umbral) |
| F8 | Deriva y panel | ampliación | Detectores de deriva calibrados; dashboards de Grafana generados | G-DRIFT-FP, G-DRIFT-POWER | sin empezar |
| F9 | E2E, autopuerta y publicación | núcleo | `make test-e2e` completo; el repo pasa por su propia puerta (`EVALGATE_SELF_GATE=on`, R16); flujo de CI escrito; ADR cerrados | G-GATE-BLOCK-EVIDENCE | entregables hechos; `make done` en rojo por las metas de F7 |
| F10 | Exportación y contraste | ampliación | `evalgate export parquet`; contraste nocturno con DeepEval | G-DEEPEVAL-CORR | sin empezar |

F7 no se cerró bajando umbrales: los números reales se publican con su intervalo
([`docs/NUMEROS.md`](NUMEROS.md)) y las metas que fallan siguen fallando en el gate.
