# ADR-012 · ClickHouse como almacén de trazas, escrito desde el proxy, con cola acotada propia

**Fecha:** 2026-09-29
**Fase:** F3 (ADR obligatorio de `PLAN.md` §4)
**Estado:** aceptado

---

## Contexto

Las trazas son carga **analítica**: agregados por modelo, por día o por prompt sobre millones de filas que
no se actualizan nunca. Eso es trabajo para un almacén columnar, no para uno OLTP (PROJECT §1, STACK §3), y
ClickHouse es además el backend del que hay esquema público (`otel_traces` del `clickhouseexporter`).

La decisión que no es obvia es **por dónde llegan las trazas**, y la forzó una medida del contrato: el
contrato otel-genai §4 y `G-TRACE-DEGRADE` exigen que `app.spans.dropped` cuente **todo** lo que no llega al
almacén, porque "un descarte silencioso es peor que un descarte medido". Dos hallazgos del 2026-09-29
(JOURNAL):

1. El `BatchSpanProcessor` del SDK (1.44.0) **ignora el resultado de `export()`**: un lote rechazado con
   ClickHouse caído desaparece sin contarse.
2. Con el Collector en medio, el proxy recibe SUCCESS en cuanto el Collector acepta el lote, esté ClickHouse
   vivo o no. El descarte ocurre en otro proceso y `app.spans.dropped` dice 0 justo cuando importa.

## Opciones consideradas

| Opción | A favor | En contra | Coste |
|---|---|---|---|
| **A · SDK → OTLP → Collector (`clickhouseexporter`) → ClickHouse** | La receta de STACK §6; cualquier backend | El proxy no ve la caída del almacén: el contador no mide. Un contenedor más (RAM, D-03) | 0 h de código; métrica inservible |
| **B · SDK con `BatchSpanProcessor` + exportador propio a ClickHouse** | Menos código propio | Punto 1: el procesador del SDK pierde los rechazos sin contarlos | 2 h |
| **C · Cola acotada propia + exportador directo a ClickHouse (`clickhouse-connect`), mismo esquema `otel_traces`** | El contador cuenta los dos descartes (cola llena y almacén caído); la petición solo hace `put_nowait` | Código propio que mantener (~150 líneas, 100 % cubiertas); se aparta de STACK §6 | 6-8 h |

## Decisión

Se elige **C**. Lo que decanta es que el contador tiene que medir el caso para el que existe. Se descartó
el Collector, aunque es la opción de manual, porque le esconde al proxy la única señal que la meta pide
medir. Para que la decisión se pueda revertir barato, la tabla es **la del `clickhouseexporter`**: mismas
columnas y misma codificación de atributos (JSON para las listas, booleanos en minúscula). Una consulta
escrita contra trazas del Collector funciona sin cambios contra las nuestras.

Política de degradación, la que miden los tests de nivel 2:
- La ruta de la petición solo crea el span y hace `put_nowait`. Nunca espera (R1, regla por AST).
- Cola de 4096 spans (unos 80 s de ClickHouse caído a 50 rps). Lotes de 512 o de 1 s.
- Cada span acaba **exportado** (el almacén respondió SUCCESS) o **descartado y contado** (no cupo en la
  cola, el almacén falló o el procesador ya estaba cerrado). No hay una tercera salida.
- La conexión es perezosa y se rehace tras cada fallo: ClickHouse caído no impide que el proxy arranque, y
  si ClickHouse se reinicia, se vuelve a escribir en el siguiente lote.
- Esquema con migraciones propias numeradas (`create_schema: false`) e inmutables una vez aplicadas, con su
  sha256 en `schema_migrations`, como las tablas de precios (R4).

Medido (nivel 2, ClickHouse 26.4 por digest): **G-TRACE-0 = 0 perdidos**, 6000 servidas a 50 rps durante
120 s. **G-TRACE-DEGRADE: Δp95 = −0,03 ms** con el contenedor matado a mitad del tráfico, 2000/2000
servidas, 1000 exportadas (= 1000 filas) + 1000 descartadas y contadas.

## Consecuencias

- **Lo que gana:** `app.spans.dropped` es verdad también con ClickHouse caído, y el diferenciador nº 4
  tiene número.
- **Lo que cuesta:** una cola propia que mantener. La métrica se publica por la API de métricas de OTel:
  sin un `MeterProvider` configurado no sale del proceso, y el panel llega en F8.
- **Qué habría que ver para revertirla:** que el SDK cuente los rechazos de `export()`, o necesitar varios
  backends a la vez. Entonces A o B con esta misma tabla.
- **Qué se toca si se revierte:** `telemetry/processor.py`, `telemetry/exporters/`, `telemetry/pipeline.py`
  y `cli/main.py`. Ni el esquema ni `proxy/`.
