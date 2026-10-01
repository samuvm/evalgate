# ADR-007 · Byte a byte si el proveedor cumple el esquema; normalización mínima y declarada si no

**Fecha:** 2026-09-10
**Fase:** F1
**Estado:** **aceptado** (PARA-SAMUEL P-004 (a), aprobada por Samuel el 2026-09-10)

---

## Contexto

`PROJECT.md` §4 pide que la respuesta del proxy sea "byte a byte idéntica a la llamada directa", y
`G-OPENAI-CONTRACT` (== 1.0, sin propuesta admisible) exige que toda respuesta valide contra la OpenAPI
pineada. Con solo modelos locales (D-05) el proveedor es Ollama 0.33.3, cuya respuesta **no valida**: omite
`choices[].logprobs` y `choices[].message.refusal`, obligatorios aunque admitan `null` (medido el
2026-09-10; fixture `tests/fixtures/openai/ollama_chat_completion.json`). Las dos promesas no caben juntas
con este proveedor.

## Opciones consideradas

| Opción | A favor | En contra | Coste estimado |
|---|---|---|---|
| **A · Byte a byte si cumple; añadir solo los campos ausentes con `null` si no, y declararlo** | Las dos promesas se cumplen donde son compatibles; la única excepción es visible | Con Ollama, el cuerpo ya no es idéntico al directo | 1 h |
| **B · Byte a byte siempre** | Transparencia absoluta | `G-OPENAI-CONTRACT` inalcanzable con Ollama; habría que reinterpretar una meta cerrada | 0 h |
| **C · Normalizar siempre** (volver a serializar) | Salida uniforme | Se pierde la prueba más limpia de transparencia (hito 0) | 1 h |

## Decisión

Se elige **A**. `proxy/translate.py::normalize_chat_completion` devuelve **los bytes originales intactos**
si no falta nada; si faltan, añade únicamente esos dos campos con `null` y el proxy responde con la cabecera
`x-evalgate-normalized: choices.logprobs,choices.message.refusal`. Activado por defecto
(`EVALGATE_NORMALIZE=on`, `evalgate serve --no-normalize` para desactivarlo). Solo se normalizan respuestas
200; los errores del proveedor pasan tal cual. **Se descartó "byte a byte siempre" aunque es la lectura
literal del hito 0, porque dejaría el proxy incumpliendo el esquema que dice defender.**

## Consecuencias

- **Lo que gana:** `G-OPENAI-CONTRACT` alcanzable con Ollama; `G-ADOPTION` intacta (la app no ve diferencias:
  0 líneas con Ollama real).
- **Lo que cuesta:** con un proveedor no conforme, el cuerpo cambia (claves añadidas y JSON compacto). Queda
  declarado en cada respuesta.
- **Qué habría que ver para revertirla:** que Ollama emita esos campos (entonces la función ya no toca nada),
  o un cliente que dependa de la ausencia de esos campos.
- **Qué se toca si se revierte:** el valor por defecto de `ProxySettings.normalize` y de `--normalize`.
