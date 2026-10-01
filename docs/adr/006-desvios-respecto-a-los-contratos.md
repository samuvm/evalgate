# ADR-006 · Desvíos declarados respecto a los contratos fijados en `docs/CONTRACTS/`

**Fecha:** 2026-09-10 (ampliado el 2026-10-06 con el desvío de `gen_ai.response.model`)
**Fase:** F0
**Estado:** **aceptado**

---

## Contexto

`docs/CONTRACTS/` está fijado por sha256 (R20, `docs/spec/contracts.sha256`): un contrato no se edita para
acomodar una necesidad local, se versiona. Pero en tres puntos la letra del contrato no se puede cumplir tal
cual, por un motivo técnico verificable, y quien lea solo el contrato no verá dónde se aparta el repo.

## Opciones consideradas

| Opción | A favor | En contra | Coste estimado |
|---|---|---|---|
| **A · Editar el contrato en el repo para que diga lo que hace el código** | Una sola fuente de verdad | El contrato deja de coincidir con su versión publicada, y el pin pierde su sentido | 0,5 h |
| **B · Registrar cada desvío aquí, con su motivo y el test que lo fija** | El contrato sigue íntegro; el desvío es visible y auditable | Dos sitios que leer hasta que el contrato suba de versión | 0,5 h |

## Decisión

Se elige **B**. Cada desvío es consciente y lleva su motivo:

| Desvío | Contrato | Motivo | Dónde vive |
|---|---|---|---|
| Pin OTel `open-telemetry/semantic-conventions@v1.41.1` en lugar de `semantic-conventions-genai@v1.42.0` | `otel-genai.md` §1, §3 | El repo genai no ha publicado ningún tag (verificado el 2026-09-10); las convenciones salieron del repo principal en v1.42.0, no en v1.43.0. v1.41.1 es la última versión publicada con `model/gen-ai/` completo (ADR-005) | `otel-semconv.lock` |
| `gen_ai.response.model` se omite cuando el proveedor no lo declaró (stream de longitud cero, corte antes del primer chunk); nunca se copia de la petición | `otel-genai.md` §4 ("obligatorio" sin condición) | La llamada ya está cobrada y tiene que trazarse; copiar el modelo pedido es una suposición (los proveedores redirigen alias) y un centinela ensucia los agregados. En v1.41.1 el atributo es *Recommended* | `telemetry/translate.py`, `tests/contract/test_otel_attrs.py` |
| Golden set sintético por construcción, `provenance: sintetico_por_construccion`, sin revisión humana caso a caso | `retrieval-metrics.md` §3, regla 3 y valores de `provenance` | El sujeto medido es la puerta, no la calidad de un RAG; la respuesta correcta se conoce porque se genera con el caso (ADR-016) | `scripts/gen_golden.py`, `evals/golden/` |

Los ficheros de `docs/CONTRACTS/` **no se tocan**: siguen coincidiendo con su sha256 fijado (R20, verificado
por `tests/contract/test_contracts_are_verbatim_copies.py`). El desvío vive en los ficheros propios.

## Consecuencias

- **Lo que gana:** el trabajo no se para, y nadie tiene que adivinar dónde se aparta el repo del contrato.
- **Lo que cuesta:** quien lea solo `docs/CONTRACTS/` verá reglas que este repo no cumple al pie de la letra.
- **Qué habría que ver para revertirla:** una versión nueva de los contratos que incorpore los tres puntos.
  Entonces se regenera `docs/spec/contracts.sha256` y este ADR pasa a supersedido.
- **Qué se toca si se revierte:** `docs/CONTRACTS/**` (versión nueva), `docs/spec/contracts.sha256`,
  `CHANGELOG.md`.
