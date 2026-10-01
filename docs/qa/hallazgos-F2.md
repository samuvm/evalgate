# Hallazgos de la reserva · F2

**Autor:** qa-adversario · **Fecha:** 2026-09-20 · **Comando:** `uv run pytest tests/holdout -q`
**Resultado de partida:** 318 tests, 8 fallan, 310 pasan (igual que el paso 3 de `make done MILESTONE=2`).
**Resultado tras actualizar la reserva:** 349 tests, **1 falla**, 348 pasan.

Los 8 fallos de partida eran **uno solo repetido**: la reserva de F1 exigía que una petición con
`stream: true` fuese rechazada sin tocar al proveedor —el `501` que `PLAN.md` fila F1 pedía— y F2 entrega
justo lo contrario. Ninguno era un defecto: era la reserva defendiendo la fase anterior. Esos tests **no se
han borrado, se han dado la vuelta**: ahora exigen que la petición llegue al proveedor byte a byte y que el
flujo vuelva como flujo.

Sobre eso se ha añadido reserva nueva para lo que F2 sí promete —contabilidad ante corte de cliente, el
chunk en vuelo, las tramas contra el snapshot pineado y el razonamiento contado aparte—, **31 tests más**.
De todo ello queda **un fallo**, y es de clase `defecto-F2`.

| Clase | Entradas |
|---|---|
| `defecto-F2` | H-13 |

Resumen de lo que la reserva nueva **sí** encuentra en verde, para que conste que el fallo está acotado:
el flujo se reenvía trama a trama y no al final (comprobado con el proveedor detenido a mitad, contra el
proceso servido real); el registro de uso sale con `provider` cuando llega el bloque `usage` y con
`estimated` cuando no; `usage: null` no se cuenta como cero; el chunk en vuelo **sí** se cuenta en cada
índice de corte; el razonamiento se guarda aparte del texto y los dos recuentos se suman; las 34 tramas de
la transcripción real de Ollama validan contra el snapshot pineado leído como lo lee ADR-011; un sumidero
de uso que revienta no altera ni el estado ni los bytes de la respuesta; y el servidor sobrevive a un
cliente que cierra el socket a mitad de respuesta y sigue atendiendo.

---

## H-13 · Con el cliente cortado, la contabilidad no se cierra dentro de la petición

Clase: defecto-F2

Petición: POST a `/v1/chat/completions` con `stream: true` contra un proveedor que devuelve una
transcripción SSE completa (cinco tramas de contenido, trama de `finish_reason`, trama de `usage` y
`[DONE]`). El cliente se conduce por el borde ASGI para que el índice de corte sea exacto: recibe dos
tramas, informa `http.disconnect` y no deja aterrizar la tercera. Se observa el sumidero de uso
(`on_usage`) **en el instante en que la llamada ASGI de esa petición retorna**, todavía dentro del bucle de
eventos y antes de que nada más finalice generadores pendientes.

Esperado: exactamente un registro de uso, ya emitido cuando la petición termina. `RULES.md` R2 ("la
contabilidad se cierra siempre": toda corrutina generadora de `proxy/streaming.py` emite el registro en un
`finally` y sobrevive a `asyncio.CancelledError`), `docs/adr/010-contabilidad-ante-desconexion.md`
("el registro sale pase lo que pase") y `GOALS.yaml` G-DISCONNECT, que es la única meta del repo con
`propuesta_admisible: false` precisamente porque esos tokens ya están pagados. El propio `JOURNAL` de F2
(2026-09-12) escribe el criterio con todas las letras al justificar el cierre explícito del flujo interior:
*"dejárselo al recolector de basura significaría que el registro de uso sale cuando Python quiera, y no
mientras la petición sigue siendo la petición"*.

Obtenido: **cero registros** cuando la petición termina. El registro aparece más tarde, y solo cuando algo
externo finaliza el generador de respuesta: en la medida hecha aquí no bastó ceder el bucle de eventos
durante 0,1 s ni dejar morir todos los marcos de la prueba —hizo falta una pasada del recolector cíclico
para que saliera—. Es decir: hay un ciclo de referencias, el conteo de referencias no lo libera, y el
momento del registro lo decide el recolector, no la petición. En un proceso servido de larga vida eso
significa que el registro de una desconexión sale en un instante arbitrario posterior, fuera de la petición
que lo generó, y no sale en absoluto si el proceso muere antes de esa pasada.

**El contenido del registro, cuando por fin sale, es correcto**: `end` vale `client_disconnect`, cuenta
`k + 1` tramas para un corte tras `k` entregadas —el chunk en vuelo se contabiliza, que es lo que ADR-010
defiende—, el texto y el razonamiento son los emitidos y el origen es `estimated`. Lo que falla es
**cuándo**, no **cuánto**.

Por qué la meta no lo ve: G-DISCONNECT se mide con Hypothesis sobre el relevo (`tests/property/`), donde
quien corta el generador es el propio test y por tanto el `finally` corre en el acto. El hueco está en el
**montaje**, que es entregable de F2 igual que el módulo: entre el relevo y el cliente hay una capa que
cancela la tarea y deja el generador suspendido en su `yield` sin cerrarlo nunca. El `ratio=1` publicado es
cierto para lo que mide y no cubre la petición real.

Acción: para el constructor.

---

Nota para el constructor, del mismo tenor que la de F1: el arreglo tiene que ser **general**, no el caso
concreto. Que este punto lo vigile una regla mecánica igual que R2 vigila el `finally` por AST, porque un
`finally` que existe pero corre cuando el recolector quiere cumple la letra de R2 y no su invariante. Y el
número de G-DISCONNECT conviene que se mida también donde se sirve la petición, no solo donde vive el
relevo: un evaluador no evaluado es un adorno, y una meta que solo mira el módulo que sí cumple es la misma
figura.

---

Reserva activa: 349 tests, 1 falla, `defecto-F2`
