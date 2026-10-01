# ADR-005 · Modelo de datos interno propio y traducción a OTel GenAI pineado en v1.41.1

**Fecha:** 2026-09-10
**Fase:** F0
**Estado:** **aceptado**

---

## Contexto

Ningún atributo `gen_ai.*` es estable: todo el namespace está en *Development* y ya ha roto dos veces
(`gen_ai.system` → `gen_ai.provider.name`; `prompt_tokens`/`completion_tokens` →
`input_tokens`/`output_tokens`; `docs/CONTRACTS/otel-genai.md` §1). Además, el pin que fija el contrato
(`semantic-conventions-genai@v1.42.0`) **no existe**: ese repo no ha publicado ningún tag (verificado con la
API de GitHub el 2026-09-10; JOURNAL de ese día). Samuel eligió en Q-008 (a)
`open-telemetry/semantic-conventions@v1.41.1` (`ead83b9b0fa36540c1642fce46e874f002ac23f1`), la última versión
publicada con `model/gen-ai/` completo, que contiene los 9 atributos y las 2 métricas obligatorias del §4.

## Opciones consideradas

| Opción | A favor | En contra | Coste estimado |
|---|---|---|---|
| **A · Usar los nombres `gen_ai.*` como modelo interno** | Menos código | Cada ruptura de la spec es una migración de ClickHouse y una reescritura de paneles | 0 h hoy, deuda después |
| **B · Modelo interno propio (`LlmCall`) + traductor generado desde `otel-semconv.lock`** | Una ruptura de la spec cambia un fichero; R5 se verifica con un grep | Una capa más | 3-5 h en F3 |
| **C · Instrumentación de terceros (OpenInference)** | Llave en mano | Convenciones propias, no `gen_ai.*`: contradice la tesis (RULES §3.12) | — |

## Decisión

Se elige **B**. Adoptar un estándar no obliga a atarse a él mientras es inestable: el dominio habla
`LlmCall` y solo `src/evalgate/telemetry/semconv/`, generado desde el lock, conoce los nombres `gen_ai.*`
(R5). Lo propio va en `app.*` (`app.cost.eur`, `app.stream.client_disconnected`, `app.spans.dropped`…).
Toda consulta analítica hace `coalesce()` de ambas generaciones de nombres.

## Consecuencias

- **Lo que gana:** subir de v1.41.1 a la primera release de `semantic-conventions-genai` será regenerar el
  traductor y revisar sus tests de contrato, no migrar datos.
- **Lo que cuesta:** un generador de código en F3 y un desvío documentado del contrato compartido, que
  Samuel corregirá en `_comun/` (Q-008).
- **Qué habría que ver para revertirla:** que `gen_ai.*` se declare estable.
- **Qué se toca si se revierte:** `otel-semconv.lock`, `telemetry/semconv/`, migraciones de ClickHouse.
