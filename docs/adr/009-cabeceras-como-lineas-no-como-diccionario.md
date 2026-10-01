# ADR-009 · El proxy trata las cabeceras como líneas ordenadas, no como un diccionario

**Fecha:** 2026-09-12
**Fase:** F1 (cierre)
**Estado:** aceptado (decisión reversible del constructor, CONSTITUCION §4.2 caso H)

---

## Contexto

La reserva de F1 falló en 12 casos. `docs/qa/hallazgos-F1.md` los reduce a cuatro causas raíz, y dos de
ellas (H-04 y H-06) son la misma elección de tipo: `forward_request_headers` y `forward_response_headers`
recibían un `Mapping[str, str]` y devolvían un `dict[str, str]`. **Un `dict` no puede representar un campo
que aparece dos veces**, y las dos librerías lo pierden de forma distinta, comprobado en el venv:

- `starlette.datastructures.Headers.items()` **sí** repite el par, y el `dict` por comprensión se queda con
  el último: `X-Trace: alpha` seguido de `X-Trace: beta` llega al proveedor como `beta` a secas.
- `httpx.Headers.items()` **funde** los repetidos con `", "`. Dos `Set-Cookie` del balanceador salen como una
  sola línea, y la cookie queda corrupta: la fecha de `expires` ya lleva una coma, así que el cliente no
  puede volver a separarlas (RFC 6265 §3 lo prohíbe explícitamente para este campo).

RFC 9110 §5.3 dice que varias líneas de un campo equivalen a su lista y que el orden forma parte del
significado. El tipo de datos tenía que ser el de la especificación, no el más cómodo.

## Opciones consideradas

| Opción | A favor | En contra | Coste estimado |
|---|---|---|---|
| **A · Pares explícitos: `Iterable[tuple[str, str]] -> list[tuple[str, str]]`** | Es el modelo del RFC; la función pura deja de depender del multidict de cada librería; el acoplamiento (`.items()` de starlette, `.multi_items()` de httpx) queda a la vista en `app.py` | Cambia la firma de dos funciones públicas y obliga a montar la respuesta con `raw_headers` | 2 h |
| **B · Seguir con `Mapping` y tratar `Set-Cookie` como caso especial** | Cambio mínimo | Es la lista negra que qa avisó de no escribir: arregla los nombres de estos 12 casos y vuelve a fallar con el siguiente campo repetido | 0,5 h |
| **C · Pasar `httpx.Headers` de punta a punta** | Sin tipo propio | Mete la librería de salida en el núcleo determinista y en la firma; un cambio de cliente HTTP se propagaría a `translate.py` | 1 h |

## Decisión

Se elige **A**. `translate.py` filtra **líneas**: conserva las repeticiones y su orden, y descarta lo que no
sale de este salto. La lista hop-by-hop deja de ser fija: es la lista del RFC **∪** los tokens que nombra la
cabecera `Connection` del propio mensaje, insensible a mayúsculas (§7.6.1, H-03 y H-05). En la respuesta se
descarta además lo que escribe la capa que sirve (`date`, `server`, ya estaba `content-length`), porque
uvicorn genera los suyos y reenviar los del proveedor da dos líneas de cada uno (H-01), y
`x-evalgate-normalized`, que es la declaración de evalgate de que ha tocado el cuerpo: si la reenviara, el
proveedor podría firmar en nombre de evalgate una normalización que no ha ocurrido (H-07…H-12, ADR-007).

`app.py` monta la respuesta sin `headers=` —que vuelve a ser un mapa y fundiría las repeticiones— y añade
las líneas a `raw_headers` en orden, con `latin-1`, la codificación de la capa ASGI.

## Consecuencias

- **Lo que gana:** el passthrough deja de mentir en campos repetidos; la regla es general, no una lista de
  los nombres que salieron en la reserva de esta fase.
- **Lo que cuesta:** quien llame a estas funciones tiene que elegir el iterador correcto de su multidict.
  Está comentado en las dos llamadas de `app.py`; con `.items()` de httpx, H-06 volvería en silencio.
- Para F2 (streaming), la respuesta de SSE se montará por el mismo camino: `raw_headers` y pares.

## Revisión

Si el proxy pasa a emitir cabeceras propias en cantidad (F3, trazas), conviene un tipo `HeaderLines` con su
test de propiedad en vez de `list[tuple[str, str]]` suelto.
