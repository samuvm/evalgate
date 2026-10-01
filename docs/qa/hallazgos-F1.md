# Hallazgos de la reserva · F1

**Autor:** qa-adversario · **Fecha:** 2026-09-11 · **Comando:** `uv run pytest tests/holdout -q`
**Resultado de partida:** 318 tests, 12 fallan, 306 pasan (igual que `make done MILESTONE=1`).

Los 12 fallos son **defecto-F1**: ninguno depende de Ollama ni de red (el upstream es un transporte simulado
en memoria o un stub HTTP local en 127.0.0.1), ninguno contradice ADR-007 ni un contrato, y todos caen en el
entregable de F1 (`/v1/chat/completions` no-streaming en passthrough y `evalgate serve`). Por eso no he
corregido ni renombrado nada en `tests/holdout/`.

Las 12 entradas salen de **4 causas raíz**, todas en `proxy/translate.py` / `proxy/app.py` / `cli`:

| Causa raíz | Entradas |
|---|---|
| Las cabeceras se copian a un `dict`: los valores repetidos se pierden o se funden en uno | H-04, H-06 |
| La lista hop-by-hop es fija: ignora los campos que nombra la cabecera `Connection` | H-03, H-05 |
| `x-evalgate-normalized` del upstream se reenvía: la declaración de ADR-007 se puede falsificar | H-07 a H-12 |
| Lo que no es cabecera ni cuerpo se pierde o se duplica al montar la respuesta (query, `Date`/`Server`) | H-01, H-02 |

Nota para el constructor: la reserva prueba el comportamiento con nombres y valores concretos, pero el
arreglo tiene que ser el general (la regla de RFC 9110), no el caso concreto. Una lista negra con los nombres
que aparecen aquí seguiría fallando en la reserva de la próxima fase.

---

## H-01 · `evalgate serve` emite `Date` y `Server` dos veces

Clase: defecto-F1
Petición: con `evalgate serve` levantado como proceso real y apuntando a un proveedor stub local que responde
200 con su propio `Date` y `Server`, se envía un POST no-streaming a `/v1/chat/completions` y se cuentan las
líneas de cada cabecera de campo único (`date`, `server`, `content-type`, `content-length`) en la respuesta.
Esperado: como mucho una línea por cada una. RFC 9110 §5.3: un emisor no genera varias líneas de un campo que
no es una lista, y `Date` y `Server` no lo son. PLAN F1 (passthrough, CLI `evalgate serve`) y PROJECT §4 hito 0
(respuesta idéntica a la llamada directa, que trae una sola línea de cada).
Obtenido: dos `date` (la del proveedor y la que añade el servidor HTTP del proxy) y dos `server` (`uvicorn` y
el del proveedor). `content-type` y `content-length` salen una vez, bien. Con el cliente de pruebas en memoria
no se ve, porque ahí no hay servidor HTTP que añada las suyas: solo aparece con el proceso servido.
Acción: para el constructor.

## H-02 · La query string del cliente no llega al proveedor

Clase: defecto-F1
Petición: POST no-streaming a `/v1/chat/completions` con una query string (`api-version=…&trace=on`) y un
cuerpo válido; se mira la URL que recibe el upstream.
Esperado: el upstream recibe la misma query, byte a byte. PLAN F1 ("passthrough byte a byte") y PROJECT §2
("proxy transparente"). La OpenAPI pineada (`docs/spec/openai-openapi-2.3.0.json`) no declara parámetros de
query para POST `/chat/completions`, así que el proxy no tiene base para quitarlos: lo que no entiende lo
reenvía. La llamada directa sí los lleva.
Obtenido: el upstream recibe la ruta correcta con la query vacía. Se descarta en silencio.
Acción: para el constructor.

## H-03 · Las cabeceras que nombra `Connection` en la petición se reenvían

Clase: defecto-F1
Petición: POST no-streaming con `Connection: keep-alive, X-Client-Hop` y una cabecera `X-Client-Hop` con
un valor que solo vale para el siguiente salto.
Esperado: `X-Client-Hop` no llega al upstream. RFC 9110 §7.6.1: además de la lista fija, son hop-by-hop
todos los campos que nombra `Connection`, y un proxy los quita antes de reenviar. El propio
`proxy/translate.py` cita esa sección como su regla.
Obtenido: `Connection` se quita, pero `X-Client-Hop` llega al upstream con su valor.
Acción: para el constructor.

## H-04 · Una cabecera repetida en la petición pierde valores

Clase: defecto-F1
Petición: POST no-streaming con la misma cabecera de extensión enviada dos veces, con dos valores distintos
(`alpha` y luego `beta`).
Esperado: el upstream recibe los dos valores, en orden. RFC 9110 §5.3 (varias líneas del mismo campo equivalen
a su lista, y el orden importa) y PLAN F1 (passthrough).
Obtenido: el upstream solo recibe `beta`. El primer valor se pierde en silencio.
Acción: para el constructor.

## H-05 · Las cabeceras que nombra `Connection` en la respuesta llegan al cliente

Clase: defecto-F1
Petición: POST no-streaming; el upstream responde 200 con un cuerpo conforme, `Connection: X-Upstream-Hop` y
una cabecera `X-Upstream-Hop` con estado interno de su balanceador.
Esperado: `X-Upstream-Hop` no llega al cliente. RFC 9110 §7.6.1, igual que H-03 en el sentido contrario.
Obtenido: `Connection` se quita, pero `X-Upstream-Hop` llega al cliente con su valor.
Acción: para el constructor.

## H-06 · Dos `Set-Cookie` del proveedor se funden en una sola línea

Clase: defecto-F1
Petición: POST no-streaming; el upstream responde 200 con dos líneas `Set-Cookie` distintas (las que pone
Cloudflare delante de OpenAI: una con fecha `expires=` que lleva coma dentro).
Esperado: el cliente recibe dos líneas `Set-Cookie`, idénticas y en el mismo orden. RFC 9110 §5.3 y
RFC 6265 §3: `Set-Cookie` es la excepción conocida que **no** se puede combinar con comas, porque la fecha
de `expires` ya lleva una coma y el resultado no se puede volver a separar.
Obtenido: una sola línea con los dos valores unidos por coma y espacio. El cliente ve una cookie corrupta.
Acción: para el constructor.

## H-07 · El upstream falsifica `x-evalgate-normalized` · 200, normalización activa

Clase: defecto-F1
Petición: POST no-streaming con normalización activada; el upstream responde 200 con un cuerpo **conforme**
(no hay nada que normalizar) y añade él mismo `x-evalgate-normalized: choices.logprobs,choices.message.refusal`.
Esperado: el cuerpo llega byte a byte y la respuesta **no** lleva `x-evalgate-normalized`. ADR-007: esa
cabecera es la declaración del proxy de que ha tocado el cuerpo; aquí no lo ha tocado, así que su presencia
es una declaración falsa en nombre de evalgate. (Cuando el proxy sí normaliza, ya sustituye bien la del
upstream: ese caso de la reserva pasa.)
Obtenido: el cuerpo llega intacto, pero la cabecera falsificada llega al cliente tal cual.
Acción: para el constructor.

## H-08 · El upstream falsifica `x-evalgate-normalized` · 200, normalización desactivada

Clase: defecto-F1
Petición: igual que H-07, con la normalización desactivada (`normalize=False`, el equivalente de
`--no-normalize`).
Esperado: sin `x-evalgate-normalized`. ADR-007: con la normalización apagada el proxy no declara nunca nada.
Obtenido: la cabecera falsificada llega al cliente.
Acción: para el constructor.

## H-09 · El upstream falsifica `x-evalgate-normalized` · 400, normalización activa

Clase: defecto-F1
Petición: igual que H-07, pero el upstream responde 400.
Esperado: el cuerpo del error pasa tal cual y sin `x-evalgate-normalized`. ADR-007: "solo se normalizan
respuestas 200; los errores del proveedor pasan tal cual" se refiere al **cuerpo**, que la reserva comprueba
intacto; un error no se normaliza nunca, así que cualquier declaración de normalización es falsa.
Obtenido: el cuerpo pasa intacto, pero la cabecera falsificada llega al cliente.
Acción: para el constructor.

## H-10 · El upstream falsifica `x-evalgate-normalized` · 400, normalización desactivada

Clase: defecto-F1
Petición: igual que H-09, con la normalización desactivada.
Esperado: sin `x-evalgate-normalized` (ADR-007, como H-08 y H-09).
Obtenido: la cabecera falsificada llega al cliente.
Acción: para el constructor.

## H-11 · El upstream falsifica `x-evalgate-normalized` · 500, normalización activa

Clase: defecto-F1
Petición: igual que H-09, pero el upstream responde 500.
Esperado: cuerpo del error tal cual y sin `x-evalgate-normalized` (ADR-007, como H-09).
Obtenido: la cabecera falsificada llega al cliente.
Acción: para el constructor.

## H-12 · El upstream falsifica `x-evalgate-normalized` · 500, normalización desactivada

Clase: defecto-F1
Petición: igual que H-11, con la normalización desactivada.
Esperado: sin `x-evalgate-normalized` (ADR-007, como H-08 y H-11).
Obtenido: la cabecera falsificada llega al cliente.
Acción: para el constructor.

---

Reserva activa: 318 tests, 12 fallan, todos defecto-F1
