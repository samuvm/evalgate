# ADR-010 · Contabilidad de tokens cuando el cliente se desconecta a mitad del stream

**Fecha:** 2026-09-12
**Fase:** F2 (ADR obligatorio de `PLAN.md` §4)
**Estado:** aceptado

---

## Contexto

Un cliente que cierra la pestaña a mitad de respuesta deja una pregunta que el protocolo no responde:
**¿cuántos tokens se han pagado?** El proveedor ya los generó y ya los factura; el cliente no los ha visto.
Si la contabilidad se cierra solo en el camino feliz, ese gasto desaparece de los informes y la puerta de
coste mide una factura que no existe. Es el error nº 1 que la investigación previa señalaba en los proxies
de LLM, y el diferenciador que este proyecto declara (R2, `G-DISCONNECT` con `propuesta_admisible: false`).

Tres cosas que no se pueden decidir "por sentido común" y que se midieron o se probaron:

1. En un generador asíncrono, la desconexión llega como `GeneratorExit` (el consumidor cierra) o como
   `asyncio.CancelledError` (se cancela su tarea). Las dos se lanzan **dentro** del generador, en el `yield`.
2. Entre "el proveedor emitió un chunk" y "el cliente lo recibió" hay un chunk de diferencia: el que está en
   vuelo cuando se corta. Está pagado.
3. `qwen3.5:4b-mlx` (Ollama 0.33.3, medido el 2026-09-12) emite el razonamiento en `delta.reasoning` con
   `delta.content` **vacío** y lo factura en `usage.completion_tokens`. Estimar sobre el texto de la
   respuesta da **100 % de error**; sobre texto + razonamiento, 35-57 % según el estimador (JOURNAL).

## Opciones consideradas

| Opción | A favor | En contra | Coste estimado |
|---|---|---|---|
| **A · `finally` en el generador + estimación sobre lo ya emitido** | El registro sale pase lo que pase, con lo que realmente se emitió; no necesita nada del proveedor | Sin el bloque `usage` el número es una estimación, y hay que decirlo | 3 h |
| **B · Registrar solo cuando llega el chunk `usage`** | Siempre exacto | Un corte de cliente no llega nunca al chunk final: justo el caso que se quiere medir queda a cero | 1 h |
| **C · Preguntar el coste al proveedor después** | Exacto y sin heurística | No existe en la API de streaming; y con Ollama no hay factura que consultar | — |

## Decisión

**A**, con cuatro reglas que fijan los tests, no la intuición:

- Todo generador de `proxy/streaming.py` emite el registro en un `finally`, y ningún `except` se traga
  `CancelledError` ni `GeneratorExit` sin relanzarlos. Lo verifica `scripts/rules/finally_on_generators.py`
  por AST, no la buena voluntad.
- **El chunk en vuelo cuenta.** El corte en `k = 0` pide igualmente una trama al proveedor y la contabiliza:
  el cliente no la vio, pero está pagada. Hypothesis corta en **cada** k y lo comprueba (`G-DISCONNECT
  ratio=1, n=8812` con perfil `nightly`).
- **El origen viaja con el número.** `Usage.source` vale `provider` cuando llegó el bloque `usage` y
  `estimated` cuando hubo que contar. Un informe que publique una estimación con la misma cara que un dato
  exacto miente sin decir una sola cosa falsa.
- **Se cuenta el razonamiento.** `UsageRecord.reasoning` guarda `delta.reasoning` **aparte** del texto de la
  respuesta —mezclarlos metería el cuaderno de notas del modelo en la respuesta— y la estimación suma los
  dos recuentos. Sin esto, un stream de razonamiento cortado registra 0 tokens de algo ya facturado.

## Consecuencias

- **Lo que gana:** no hay camino por el que un token emitido no quede registrado, y el informe distingue lo
  medido de lo estimado.
- **Lo que cuesta:** la exactitud de la estimación depende del tokenizador, que este módulo **no trae**: se
  inyecta. Cuánto vale ese número y contra qué se compara es `PARA-SAMUEL.md` P-005, PENDIENTE.
- **Hueco conocido, escrito para que no sorprenda:** solo se lee `delta.reasoning`. Otros proveedores
  (DeepSeek, vLLM) usan `reasoning_content`; cuando uno de ellos entre como proveedor de salida, entra con
  su fixture y su test, no con un `or` escrito a ciegas hoy.

## Revisión

Si algún día el proveedor manda `usage` en cada chunk (incremental), la estimación sobra y `source` valdría
siempre `provider`: se revisa entonces.
