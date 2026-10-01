# Respuestas grabadas · procedencia

No son inventadas ni retocadas: son la respuesta **tal cual** de un proveedor real, guardada byte a byte.
Un conjunto de medida con casos escritos a mano mide lo que su autor imaginó; estos miden lo que pasa.

| Fichero | Modelo | Petición | `max_tokens` | `finish_reason` | `usage` |
|---|---|---|---|---|---|
| `qwen-corto.json` | `qwen3.5:4b-mlx` | "Responde solo con la palabra: hola" | 900 | `stop` | 19 / 191 |
| `qwen-razonando.json` | `qwen3.5:4b-mlx` | "¿Cuanto es 17 x 23? Piensa antes de responder." | 300 | `length` | 28 / 300 |
| `qwen-unicode.json` | `qwen3.5:4b-mlx` | "Escribe exactamente: el niño pagó 3 € 🙂" | 900 | `stop` | 22 / 296 |

- **Cuándo:** 2026-09-12. **Con qué:** Ollama 0.33.3 en el host (`STACK.md` §0), `temperature: 0`,
  `POST /v1/chat/completions` sin streaming, sin pasar por el proxy.
- **Por qué estas tres:** una que termina con respuesta corta, una que se queda sin tokens **mientras
  razona** (`finish_reason: length`, `content` vacío) y una con unicode fuera del plano básico.
- **Lo que enseñan, y por lo que están aquí:** las tres traen `message.reasoning` con cientos de caracteres
  y `message.content` vacío o mínimo, y las tres facturan ese razonamiento en `usage.completion_tokens`.
  Es el hallazgo del 2026-09-12 (JOURNAL) y la razón de ADR-010.
- **Ninguna valida contra el esquema pineado sin normalizar:** les faltan `logprobs` y `refusal`, que es
  exactamente lo que P-004 (a) y ADR-007 resolvieron en F1.
- **Regenerarlas cambia los números.** No se regeneran para "arreglar" un test: si el modelo cambia, se
  graban de nuevo a propósito y se actualiza esta tabla.
