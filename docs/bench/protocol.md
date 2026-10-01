# Protocolo de medida de latencia · `make bench PROFILE=proxy|stream`

> Existe antes que el proxy para que `G-LAT-PROXY` y `G-LAT-TTFT` sean medibles desde el primer día. Un p95
> sin este protocolo es una anécdota (RULES §3.5). Cambiar el protocolo es cambiar la meta: se hace con ADR.

## Qué se mide

| Perfil | Meta | Número publicado |
|---|---|---|
| `proxy` | `G-LAT-PROXY` (p95 ≤ 30 ms) | `overhead_ms.pXX = pXX(latencia vía proxy) − pXX(latencia directa)`, para p50, p95 y p99 |
| `stream` | `G-LAT-TTFT` (p95 ≤ 15 ms) | `ttft_overhead_ms.pXX = pXX(TTFT vía proxy) − pXX(TTFT directo)`, ídem |

Se publica la **diferencia de percentiles**, que es lo que dice la meta ("p95 sobre la llamada directa").
La distribución de diferencias pareadas petición a petición se guarda también, como diagnóstico.

## Condiciones fijas

1. **Contra un stub local determinista en loopback, nunca contra un proveedor real**, que mediría la varianza
   de la red y no el proxy (RULES §3.5).
   - `proxy`: el stub responde tras un retardo fijo de **50 ms** con un cuerpo `chat.completion` válido
     contra `docs/spec/openai-openapi-2.3.0.json`.
   - `stream`: primer chunk SSE a los **50 ms**, después un chunk cada **10 ms**, 64 chunks y el `usage` final.
2. **Prompt fijo de 512 tokens**, el mismo en todas las peticiones.
3. **50 peticiones de calentamiento descartadas + n = 500 medidas** por brazo (directo y vía proxy).
4. **Brazos intercalados** (directo, proxy, directo, proxy…) y concurrencia 1, para que la deriva térmica o
   de carga afecte a los dos por igual.
5. Cliente de prueba `httpx` con `max_connections = 100` y conexiones reutilizadas en ambos brazos: así se
   mide el proxy y no el pool del cliente.
6. Reloj: `time.perf_counter_ns()`. TTFT = desde el envío hasta el primer byte del primer chunk con contenido.
7. **Ventana de exclusividad** (PARA-SAMUEL Q-005 (a)): sin contenedores ajenos ni otros proyectos en marcha.
   El informe registra igualmente `docker ps` y `ollama ps` del momento; si no están vacíos, el número se
   publica marcado.

## Informe

`evals/reports/bench-<perfil>-<AAAA-MM-DD>.json` con, como mínimo: `overhead_ms` o `ttft_overhead_ms`
(`p50`, `p95`, `p99`), `n`, `n_warmup`, `hardware` (modelo, memoria, núcleos, versión de macOS **leída de la
máquina**, no copiada de `STACK.md`), `python`, `concurrent_processes` (salida de `docker ps` y `ollama ps`)
y `protocol_sha256` (sha256 de este fichero). Sin `protocol_sha256`, un informe no es comparable con otro.

## Qué no se hace

- No se descarta ningún outlier fuera del calentamiento fijo.
- No se repite una tanda "porque salió mal". Si hay que repetir, se registran las dos en `JOURNAL.md`.
- No se toca el umbral cuando falla: primero se revisa el protocolo; y si el protocolo se cumplió, se
  diagnostica el proxy (ver la entrada de ejemplo de `JOURNAL.md`).
