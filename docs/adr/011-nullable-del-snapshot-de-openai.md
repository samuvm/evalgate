# ADR-011 · El validador de contrato honra `nullable: true` del snapshot de OpenAI

**Fecha:** 2026-09-12
**Fase:** F2
**Estado:** aceptado (decisión reversible del constructor, CONSTITUCION §4.2 caso H)

---

## Contexto

`G-OPENAI-CONTRACT` exige que **toda** respuesta del proxy valide contra
`docs/spec/openai-openapi-2.3.0.json`, y su nota dice literalmente "cuerpo JSON **y tramas SSE**". Al
validar las tramas por primera vez (F2), **ninguna** pasaba:

    ['choices', 0, 'finish_reason'] -> None is not of type 'string'

No es el proveedor: es el documento. El snapshot se declara `openapi: 3.1.0` y usa **111 veces** la palabra
`nullable: true`, que es de OpenAPI **3.0**. En 3.1 la nulabilidad se expresa con unión de tipos
(`"type": ["string", "null"]`) y **ningún validador de JSON Schema respeta `nullable`**, porque no es una
palabra de JSON Schema. Leído al pie de la letra, el snapshot rechaza el `"finish_reason": null` que el
propio OpenAI manda en todas las tramas de streaming menos la última.

Medido sobre transcripciones reales de Ollama 0.33.3 (`tests/fixtures/sse/13-reasoning-tokens.sse`):
32 de 34 tramas inválidas leyendo el snapshot tal cual; **0 de 34** honrando `nullable`.

## Opciones consideradas

| Opción | A favor | En contra | Coste |
|---|---|---|---|
| **A · El validador traduce `nullable: true` a unión con `null`** | Valida lo que el documento *quiere decir*; el snapshot no se toca y su sha sigue siendo el descargado | Una traducción que hay que explicar y probar | 1 h |
| **B · Editar el snapshot** | Validación directa | Deja de ser un snapshot: su `.lock` y su procedencia (commit `b5362da0…`) dejarían de significar nada, y la próxima descarga lo revierte en silencio | 0,5 h y una mentira |
| **C · Sacar las tramas SSE de `G-OPENAI-CONTRACT`** | Sin trabajo | La meta dice "y tramas SSE"; recortar el alcance de una meta para no medir lo incómodo es lo contrario de este repo | 0 h |

## Decisión

**A**. `tests/contract/_proxy.py::honour_nullable` recorre los `components` antes de validar y, donde el
documento dice `nullable: true`, **ensancha el `type`** y, si lo hay, el `enum`. Nada más. Solo puede
aceptar lo que el proveedor ya declaró nulable; no relaja ni un campo que el proveedor no marcara.

El motivo está escrito **como test**, no como comentario:
`test_the_pinned_snapshot_contradicts_itself_and_this_is_where_it_is_written` comprueba las dos mitades —que
el snapshot leído literalmente rechaza una trama real, y que honrando `nullable` la acepta—, así que el día
que OpenAI publique un 3.1 de verdad el test fallará y alguien vendrá a leer esto.

## Consecuencias

- **Lo que gana:** `G-OPENAI-CONTRACT` se puede medir sobre tramas SSE sin bajar el umbral ni recortar el
  alcance, y el snapshot sigue siendo byte a byte el que se descargó.
- **Lo que cuesta:** una capa de traducción entre el contrato publicado y el validador. Está en el código de
  test, no en `src/`: el proxy no depende de ella.
- **Lo que NO cambia:** las tres tramas del corpus que siguen sin validar —`usage: null`, cuerpo de error a
  mitad de stream y `finish_reason` inventado— son fixtures **deliberadamente no conformes**. Que sigan
  fallando es lo correcto: miden que el proxy sobrevive a un proveedor que incumple, no que el proveedor
  cumpla.

## Revisión

Si un día el snapshot usa uniones de tipo de 3.1, `honour_nullable` se vuelve identidad y su test lo dirá.
