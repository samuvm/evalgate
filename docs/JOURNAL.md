# Bitácora · Evalgate

**Qué es.** La memoria del proyecto contra repetir errores. Es lo que hace que un intento fallido de hace
tres semanas valga algo en vez de repetirse.

**Formato.** **Append-only**: una entrada por sesión, al final del fichero, nunca se edita ni se reordena lo
anterior. El hook rechaza una escritura cuyo contenido nuevo no empiece exactamente por el viejo.

**Qué lleva cada entrada**, en este orden y sin adornos:

- Cabecera `## AAAA-MM-DD · fase N · <titular de una línea>`.
- **Qué se intentó** — la tarea, no la intención.
- **Qué falló** — con el error literal si lo hubo. Un fallo sin su mensaje no sirve de nada dentro de un mes.
- **Qué número salió** — si hubo medida. **Toda medida va con su `n`, su comando y su artefacto.** Un número
  sin el comando que lo produjo no es reproducible y no cuenta.
- **Qué se decidió** — y si es una decisión no obvia, el ADR que la recoge.
- **Qué queda abierto** — lo que va a `STATE.md` o a `PARA-SAMUEL.md`.

**Reglas duras.** Toda propuesta `bajar-umbral` exige **≥ 2 intentos medidos y registrados aquí** entre el
inicio de la fase y hoy; el gate lo verifica y marca rojo si no los encuentra. Las tablas antes/después de
una regresión revertida viven aquí: son la evidencia que sustituye al PR bloqueado mientras no haya git
(`CONSTITUCION.md` §2.2, meta `G-GATE-BLOCK-EVIDENCE`).

---

## 2026-08-08 · fase 0 · ENTRADA DE EJEMPLO — no es trabajo real, se conserva como modelo de formato

> Marcada como ejemplo. Bórrala o déjala; lo que importa es que las entradas reales tengan esta forma.

**Qué se intentó.** Fijar el protocolo de medida de la sobrecarga del proxy antes de escribir el proxy, para
que `G-LAT-PROXY` fuera medible desde el primer día. Se preparó un stub local que responde con un retardo
fijo de 50 ms en loopback y se midió la sobrecarga de un passthrough vacío.

**Qué falló.** Dos cosas, en este orden:

1. La primera tanda dio p95 = 41 ms, muy por encima del umbral de 30 ms. Causa real: se estaban midiendo las
   primeras 500 peticiones sin descartar el calentamiento; el intérprete y el pool de conexiones de `httpx`
   dominaban la cola de la distribución. No era el proxy.
2. Al corregirlo apareció un segundo problema. Error literal:
   `httpx.PoolTimeout: timed out while waiting for a connection from the pool`, con `max_connections=10` por
   defecto y 500 peticiones en vuelo. Medía el límite del cliente de prueba, no el del proxy.

**Qué número salió.**

| Configuración | n | p50 | p95 | p99 |
|---|---|---|---|---|
| Sin descarte de calentamiento, pool 10 | 500 | 3,1 ms | 41,0 ms | 88,4 ms |
| 50 de calentamiento descartadas, pool 100 | 500 | 2,8 ms | **9,6 ms** | 14,2 ms |

Comando: `make bench PROFILE=proxy`. Artefacto: `evals/reports/bench-proxy-2026-08-08.json`.
Hardware: MacBook Pro M4 Max, 36 GB unificada, macOS 26.5, sin otros contenedores corriendo.

**Qué se decidió.** El protocolo queda cerrado en `docs/bench/protocol.md`: 50 peticiones de calentamiento
descartadas, n = 500 medidas, prompt fijo de 512 tokens, stub local en loopback con retardo fijo de 50 ms,
`max_connections` del cliente de prueba a 100, hardware declarado en el informe. Se anota como ADR-005
porque el protocolo determina si la meta se cumple o no, y publicar el p95 sin él sería publicar una
anécdota. **No se toca el umbral de 30 ms**: el problema era el protocolo, no la meta.

**Qué queda abierto.** Confirmar con Samuel la exclusividad de la máquina durante los benchmarks de F3
(Q-005 en `PARA-SAMUEL.md`, `Estado: PENDIENTE`). Mientras tanto, todo informe de `bench` registra qué más
estaba corriendo.

---

## 2026-08-08 · fase 0 · resincronización con la capa común y corrección de incoherencias internas

**Qué se intentó.** Alinear el gobierno del proyecto con la nueva versión de `_comun/` (constitución §1.1,
§2.3, §7.2 y §8 reescritos; `PARA-SAMUEL-GLOBAL.md` nuevo; `goals.schema.json` nuevo; `retrieval-metrics.md`
§4 y `eval-report.schema.json` ampliados) y cerrar las incoherencias que salieron en la revisión cruzada de
los cinco proyectos.

**Qué falló.** Cinco contradicciones reales, todas de gobierno y ninguna de código:

1. `EVALGATE_SELF_GATE`: `RULES.md` R16 hacía fallar la verificación desde la fase 7, pero `PLAN.md` pone su
   retirada como entregable de F9. El script habría marcado rojo en F7 y F8 exigiendo algo que el plan aún no
   pedía — y el desenlace previsible de eso es que alguien desactive el script.
2. `G-LINE-COV` estaba en ratio (`>= 0.90`) y `[tool.gate].cobertura_linea_min` en porcentaje (`90`), sin
   nada que los comparase. Lo mismo entre `G-MUTATION` (`>= 0.75`) y `mutantes_muertos_min` (`75`).
3. `G-GATE-MDE` tenía umbral `<= 0.08` leyendo el campo `$.mde_pp.point`, que se mide en puntos porcentuales:
   la meta habría pasado siempre.
4. `GOALS.yaml` usaba umbrales en prosa (`"== 1.0"`) y campos `campo`/`publica_ademas` que el contrato común
   no admite (`additionalProperties: false` por meta).
5. Referencias cruzadas rotas a `PARA-SAMUEL.md`: `PLAN.md` citaba `Q-001` para la clave de API y `Q-009`
   para las horas semanales, que eran otras preguntas.

**Qué número salió.** No hay medida: es trabajo de documentos. Lo verificable: `CLAUDE.md` 92 líneas y
`STATE.md` 80, ambos bajo el tope duro; `docs/GOALS.yaml` valida contra `docs/CONTRACTS/goals.schema.json`
(26 metas, las 3 de ampliación con `bloqueante_desde_fase: null`); `docs/CONSTITUCION.md`, `docs/STACK.md` y los
seis ficheros de `docs/CONTRACTS/` son idénticos byte a byte a `_comun/`.

**Qué se decidió.**

- **R16 se ancla en la fase 9**, la que el plan declara. Un solo número en los tres sitios.
- **Cobertura y mutación se expresan en porcentaje** en los dos ficheros, porque es la escala en la que ya
  escriben `coverage.py` (`totals.percent_covered`, 0-100) y `mutmut`. Nace **R19**: `check_gate_config.py`
  compara los dos pares de números en `gate-fast` y manda el de `GOALS.yaml`, porque `pyproject.toml` no
  está en `deny`.
- **Holm-Bonferroni se queda** —es el valor por defecto documentado del contrato— y ahora el motivo está
  escrito donde se lee (RULES §3.8 y `comparacion` de `GOALS.yaml`): controla la tasa de error **por
  familia**, que es el riesgo que mata una puerta de calidad, y es uniformemente más potente que Bonferroni.
  El informe emite literalmente `"holm"` y R8 lo verifica.
- **Los contratos propios se mudan a `docs/spec/`** (`openai-openapi-<ver>.json` y
  `pricing-table.schema.json`). Desaparece el directorio `contracts/` de la raíz: era un tercer sitio
  confundible con `docs/CONTRACTS/`, que ahora es solo copias literales e inmutables (**R20**).
- **Las nueve decisiones transversales dejan de preguntarse aquí.** `PARA-SAMUEL.md` pasa de 17 preguntas a
  7 propias, renumeradas Q-001..Q-007, más una sección que remite a D-01..D-09 con el matiz de este proyecto
  en cada una. No es una decisión reversible a la ligera: si se vuelven a duplicar, se responderán distinto
  en cada buzón.

**Qué queda abierto.** Todo lo de `bloqueado_por` en `STATE.md`. Lo urgente por latencia de calendario sigue
siendo D-05 (clave de API y 5-10 € de tráfico durante 3-5 días) y, por volumen de horas tuyas, Q-004.

---

## 2026-09-10 · fase 0 · arranque: entorno verificado, respuestas de Samuel, esqueleto y primer rojo

**Qué se intentó.** Pasos 1-4 del `primer_paso` de `STATE.md`, tras transcribir las respuestas de Samuel
del chat: acepta todas las recomendaciones (Q-001 a/b/c sí, Q-002 (a), Q-003 (a), Q-007 (a), D-03 (a)),
**solo modelos locales** (D-05, sin clave ni gasto) y trabajar **solo dentro de este repo** por ahora (las
decisiones globales se registran en local; `_comun/` no se toca). Pide además aplicar evalgate a
citebound-01 como último paso (propuesta P-002).

**Entorno, salida literal** (paso 1):

```
$ python --version            -> Python 3.12.4        (/opt/anaconda3; el venv NO lo usa, ver decisiones)
$ uv --version                -> uv 0.9.27 (b5797b2ab 2026-01-26)
$ ollama --version            -> ollama version is 0.33.3
$ ollama list                 -> qwen3-embedding:0.6b 639 MB · qwen3.5:4b-mlx 4.0 GB · qwen3.5:9b-mlx 8.9 GB
                                 gemma4:26b-mlx 17 GB · qwen3.5:9b 6.6 GB · gemma4:12b-mlx 7.7 GB
                                 gemma4:12b 7.6 GB · bge-m3:latest 1.2 GB · gemma4:31b-cloud - · gemma3:12b 8.1 GB
$ docker info (ServerVersion, MemTotal, NCPU) -> 29.7.2 mem=11210366976 cpus=6
$ docker ps                   -> ai-gateway · eade-postgres · eade-renderer · eade-minio (ajenos a los cinco)
$ df -h .                     -> /dev/disk3s5 926Gi 717Gi 179Gi 80%
$ sysctl -n hw.memsize        -> 38654705664   (Apple M4 Max · macOS 26.6.2, no 26.5 como STACK.md §0)
```

**Qué falló.** Nada de código. Tres discrepancias con los documentos:

1. **El pin OTel del contrato no existe.** `otel-genai.md` §3 fija `semantic-conventions-genai@v1.42.0`. La
   API de GitHub devuelve `404` para `refs/tags/v1.42.0` y el repo no tiene ningún tag ni release
   (`model/manifest.yaml`: `schema_url: .../gen-ai-dev/1.42.0-dev`). En el repo principal, `model/gen-ai/`
   solo contiene `deprecated/` desde v1.42.0 (no desde v1.43.0, como dice el contrato); la última versión
   con las convenciones es `v1.41.1` (`ead83b9b0fa36540c1642fce46e874f002ac23f1`), con los 9 atributos y
   las 2 métricas obligatorias del contrato §4. Es contrato compartido, caso G: **Q-008**, sin
   `otel-semconv.lock` hasta la respuesta.
2. **Ollama 0.33.3** instalado frente a 0.32.6 de `STACK.md` §2. Transversal; muerde en `make up` (F1).
3. **macOS 26.6.2** frente a 26.5 de `hardware_referencia`. Se declara el real en cada informe de bench.

**Qué número salió.** Sin medida. Lo verificable:
- Primer rojo, por aserción y no por import: `uv run --with pytest==9.1.1 pytest tests/unit/pricing -q` ->
  `AssertionError: assert None == Decimal('0.0010')`, `1 failed in 0.01s`.
- `docs/spec/pricing-table.schema.json` es JSON Schema 2020-12 válido (`Draft202012Validator.check_schema`,
  `jsonschema==4.25.1` efímero) y el ejemplo de `pricing-table.md` §2 valida contra él.
- `docs/spec/openai-openapi-2.3.0.json`: commit `b5362da020b772e9f6feffe8f4e94b5e6c07de3f` de
  `openai/openai-openapi`, sha256 `58164f5f…f9ba`, OpenAPI 3.1.0. Procedencia en `docs/spec/openai-openapi.lock`.

**Qué se decidió** (caso H, reversibles):
- **Python del venv: CPython 3.12.12 gestionado por uv** (`uv python install 3.12.12`, `.python-version`),
  no el 3.12.4 de Anaconda: build estándar y reproducible por un desconocido.
- **Backend de construcción `uv_build==0.9.27`**, igual a la versión de uv. `dependencies = []`: la regla de
  "cero dependencias" de la hora 1 se cumple; el backend no es dependencia de ejecución.
- **`effective_from` se interpreta como 00:00:00 UTC de ese día**, y `price_at` recibe un `datetime` con
  zona. Lo fija el primer test.
- **`evals/report-hash-exclusions.yaml`** excluye `$.created_at` y `$.environment.timing`. `run_id` no se
  excluye: se generará de forma determinista.
- **Pytest en la hora 1 con `uv run --with`**, no con `uv add`, respetando `prohibido_en_la_primera_hora`
  aunque Q-007 ya esté autorizada. Las dependencias de desarrollo entran en el paso siguiente.
- Corregida en `PARA-SAMUEL.md` una ruta duplicada al buzón global (`day-300//Users/...`).

**Qué queda abierto.** Q-008 (pin OTel), P-001 (`G-COST-RECONCILE` con solo local), P-002 (fase F11 en
citebound-01), acotar `retrieval-metrics.md` en `_comun/` antes de F5 (Q-002 a), D-01 y D-09. Siguiente
turno: VERDE de `price_at`.

---

## 2026-09-10 · fase 0 · verde de price_at, pin OTel y horas

**Qué se intentó.** Turno siguiente al rojo: implementación mínima de `price_at` y aplicación de las
respuestas de Samuel del chat (Q-008 (a); D-01 = al menos 20 h por semana para evalgate).

**Qué falló.** Nada.

**Qué número salió.** `uv run --with pytest==9.1.1 pytest tests/unit/pricing -q` -> `1 passed in 0.00s`.

**Qué se decidió.** `otel-semconv.lock` apunta a `open-telemetry/semantic-conventions@v1.41.1`
(`ead83b9b…23f1`), `path: model/gen-ai`, con el desvío del contrato escrito en la cabecera del propio lock.
`price_at` resuelve la tabla con el `effective_from` más reciente ≤ `at` (00:00 UTC) y devuelve `None` si no
hay tabla vigente, si el modelo no está en ella o si el componente no tiene precio. Los tres casos de `None`
y los componentes distintos de `INPUT` aún no tienen test: los pedirá la mutación y se escriben en rojo.

**Qué queda abierto.** P-001, P-002, acotar `retrieval-metrics.md` (antes de F5), D-09 (antes de cerrar F1).

---

## 2026-09-10 · fase 0 · infraestructura de F0 completa; `make done MILESTONE=0` rojo solo por thresholds.lock

**Qué se intentó.** Primera vuelta de `/loop` en modo autónomo: el resto de F0. Respuestas de Samuel
aplicadas antes: Ollama 0.33.3 aceptado, D-09 sí, Q-005 (a), P-001 y P-002 aprobadas (GOALS.yaml ya
editado por él para P-001), sin autorización permanente de apertura de fases. `caffeinate -i -w <pid de
claude>` en marcha: el Mac no se duerme mientras viva la sesión.

**Qué falló.**
1. **El comando de `G-MUTATION` no existe en mutmut 3.** `uv run mutmut run --help` solo ofrece
   `--max-children`; `uv run mutmut results --help` solo `--all`. Ni `--paths-to-mutate` ni `--json`.
   Propuesta **P-003** (solo el campo `comando`; umbral intacto). No bloquea hasta F4.
2. `scripts/done.py`: `NotImplementedError: Non-relative patterns are unsupported` al resolver el artefacto
   absoluto `/tmp/cov.json` con `Path.glob`. Corregido con `glob.glob`.
3. `detect-secrets` marcaba 12 "secretos" dentro del propio `.secrets.baseline` (sus hashes). Excluido el
   fichero del escaneo. Los 12 hallazgos de `docs/spec/openai-openapi-2.3.0.json` son ids de ejemplo
   (`chatcmpl-…`), revisados a mano: van a la línea base.
4. **Hueco de diseño en D-09**, consultado en la documentación de Claude Code: las listas `deny` de todos los
   niveles se suman y existe `claude --settings <fichero>`; no está documentado que un subagente pueda
   saltarse el `deny` del padre. Con el `deny` de escritura de `tests/holdout/` en el `settings.json`
   global, `qa-adversario` tampoco podría escribir. Resuelto en `scripts/gates-install/` con dos perfiles de
   sesión (constructor y qa). Y un choque con la constitución: el hook `Stop` bloquearía el paso ROJO del
   TDD. `c-turn.sh` solo exige lint y typecheck mientras `fase_tdd: rojo`; `make done` cierra el agujero.

**Qué número salió.** `make done MILESTONE=0`:
`[ok] 1 estáticos y reglas · 7 comprobaciones` · `[ok] 2 suite completa · perfil nightly · 31 passed in 0.12s`
· `[ok] 3 reserva · no existe aún` · `[info] 4 cobertura por función · 1` (bloquea desde F1) ·
`[ok] 5 cobertura de línea · 93.94 % (>= 90)` · `[ok] 6 mutación · no activa hasta F4` ·
`[ok] 7 metas activas · 0` · `[ROJO] 8 umbrales intactos · falta thresholds.lock`. Pasos 9-12 ejecutados
aparte: inventario ok, `deuda_src=0 escapes_tests=0`, documentación ok, `0 hallazgos nuevos`.
`make gate-fast`: 0,73 s de reloj (presupuesto < 20 s).

**Qué se decidió.** Versiones fijadas desde PyPI el 2026-09-10 (R18, rango de `STACK.md` → `==`): ejecución
`pydantic==2.13.4` (la de `STACK.md`, no la 2.13.5), `pyyaml==6.0.3`; desarrollo `ruff==0.16.6`,
`mypy==2.3.1`, `pytest==9.1.1`, `pytest-cov==7.1.0`, `pytest-xdist==3.8.0`, `pytest-socket==0.8.1`,
`hypothesis==6.168.0`, `mutmut==3.7.0`, `bandit==1.9.4`, `detect-secrets==1.5.0`, `pip-audit==2.10.1`,
`jsonschema==4.26.0`. `types-pyyaml` **no** se instala: está fuera de la lista de Q-007, y hoy no hace falta
porque mypy solo corre sobre `testable`, que no importa `yaml`. `done.py` decide qué bloquea leyendo
`bloqueante_desde_fase` de `GOALS.yaml` (R7). Los targets de fases futuras fallan diciendo en qué fase
llegan, en vez de pasar vacíos. ADR-001 a ADR-006.

**Qué queda abierto.** `thresholds.lock` (Samuel) para cerrar F0; pegar la fila F11 en `PLAN.md` (P-002);
P-003; instalar D-09 antes de cerrar F1; test de propiedad de `price_at` al abrir F1.

---

## 2026-09-10 · fase 0 · F0 CERRADA: `make done MILESTONE=0` en verde

**Qué se intentó.** Cerrar F0 cuando Samuel creó `thresholds.lock` (tras aprobar P-003 y cambiar el comando
de `G-MUTATION` a `make mutation` en `GOALS.yaml`).

**Qué falló.** Nada.

**Qué número salió.** `make done MILESTONE=0` → `done F0: VERDE`, 12/12 pasos (el 4, cobertura por función,
informativo: 1 función sin test de propiedad, bloquea desde F1). Suite: 31 passed, perfil nightly. Cobertura
de línea 93,94 %. `sha256(GOALS.yaml) = 9b84147509c2…` = lock. Artefactos: `.claude/state/gate-status.json`
(2026-09-10T12:52:22+00:00) y snapshot `.snapshots/2026-09-10-fase0`.

**Qué se decidió.** Parar (CONSTITUCION §4.2 caso A): F1 no se abre sin el visto bueno de Samuel. Se detiene
el bucle `/loop` y el `caffeinate` asociado; se reactivan cuando Samuel diga "abre F1".

**Qué queda abierto.** Visto bueno para F1; fila F11 en `PLAN.md`; D-09 antes de cerrar F1.

---

## 2026-09-10 · fase 1 · F1 abierta; Ollama no cumple el esquema de OpenAI; rojo de price_at

**Qué se intentó.** Samuel abrió F1 ("abre F1 y continúa con lo que puedas"). Bucle `/loop` y `caffeinate`
reanudados. Antes de escribir el proxy, comprobar si una respuesta real de Ollama valida contra la OpenAPI
pineada, porque `G-OPENAI-CONTRACT` (== 1.0, sin propuesta admisible) y "passthrough byte a byte" dependen
de ello. Después, rojo del test de propiedad de `price_at` (G-FUNC-COV bloquea desde F1).

**Qué falló.**
1. **La respuesta de Ollama no valida.** `curl localhost:11434/v1/chat/completions` con `qwen3.5:4b-mlx`,
   `temperature 0`, `max_tokens 40`, `seed 7` → HTTP 200 en 1,62 s; validada contra
   `#/components/schemas/CreateChatCompletionResponse`: 2 errores, `['choices', 0] 'logprobs' is a required
   property` y `['choices', 0, 'message'] 'refusal' is a required property`. Es caso B → **P-004**.
2. `qwen3.5` razona por defecto: con `max_tokens 40` devolvió `content: ""` y 40 tokens en `reasoning`.
   `"think": false` no funciona en el endpoint OpenAI de Ollama; `"reasoning_effort": "none"` sí
   (`content: '¡Hola! ¿En qué puedo ayudarte hoy?'`, 10 tokens de salida). La app de ejemplo lo enviará.

**Qué número salió.** Rojo: `uv run pytest tests/unit/pricing tests/property/pricing -q` → `2 failed, 11
passed`. Falla `test_price_at_rejects_duplicate_effective_from` (no lanza) y
`test_price_at_rejects_naive_datetime` (`TypeError: can't compare offset-naive and offset-aware datetimes`
en vez de `ValueError`): rojo por comportamiento, no por importación. Los 4 tests de propiedad (orden
indiferente, una tabla futura nunca aplica, sale la última vigente, precio nunca negativo) pasan ya: describen
comportamiento existente, no lo conducen.

**Qué se decidió.** Mientras Samuel responde P-004, el mecanismo de su opción (a) se construye como función
pura configurable en `proxy/translate.py`; el valor por defecto se fija con la respuesta.

**Qué queda abierto.** VERDE de `price_at` (siguiente turno); P-004 antes de cerrar F1; fila F11 mal pegada.

---

## 2026-09-10 · fase 1 · proxy tonto, app de ejemplo y adopción medida; F1 lista salvo reserva y P-004

**Qué se intentó.** Verde de `price_at` y el resto de F1: `proxy/translate.py`, `proxy/app.py`
(`/v1/chat/completions` no-streaming), `evalgate serve`, `examples/rag-app` con corpus sintético, e2e de
adopción, R13 y R17.

**Qué falló.**
1. Mi fixture "conforme" no validaba: `['system_fingerprint']: None is not of type 'string'`. En la
   OpenAPI 2.3.0 ese campo, si aparece, es cadena. Se corrigió el fixture, no el test.
2. Recuperación léxica de la app: 16 fichas empataban a 3 coincidencias con la pregunta `q-0000` por los
   **nombres de campo** (`garantia_meses` → `garantia`, `meses`) y la palabra `de`; el desempate por id
   devolvía `ficha-0000..0002`. Se puntúa solo sobre valores y sin palabras vacías: recall@1 16/16.
3. `ruff`: 9 avisos (S603/S310 del e2e, S311 del generador, líneas largas). Ignorados por fichero con
   motivo en `pyproject.toml` los tres primeros tipos; el resto, corregidos.
4. Aviso de terceros: `StarletteDeprecationWarning: Using httpx with starlette.testclient is deprecated;
   install httpx2 instead` (starlette 1.6.0). `httpx==0.28.1` es de diciembre de 2024. Riesgo de
   dependencias anotado; no se actúa en F1.

**Qué número salió.**
- Verde: `pytest tests/unit/pricing tests/property/pricing -q` → `13 passed`; perfil nightly (1.000
  ejemplos por propiedad) → `4 passed in 2.86s`.
- `G-ADOPTION`: `make test-e2e -k adoption` → `G-ADOPTION lineas_de_diff=0 n_lineas=8` con el proveedor
  simulado; y con `EVALGATE_E2E_UPSTREAM=http://localhost:11434/v1` (Ollama 0.33.3, `qwen3.5:4b-mlx`, 8
  preguntas) también `lineas_de_diff=0`, 2,37 s.
- En seco (funciones de `scripts/done.py`, sin escribir estado): `G-FUNC-COV = 0`, `G-LINE-COV = 100.0 %`,
  `G-OPENAI-CONTRACT ratio 1.0, n=5`, `G-ADOPTION lineas_de_diff=0`.
- `make gate-fast`: 49 tests, 1,33 s.

**Qué se decidió** (caso H, reversibles).
- **Nota sobre el comando de `G-ADOPTION`:** `make test-e2e -k adoption` no es `pytest -k` (prohibido): es
  `make -k` (seguir tras error) con dos objetivos, `test-e2e` y `adoption`. Se define el target `adoption`.
- e2e con proveedor **simulado determinista** por defecto (respuesta derivada del sha256 de los bytes
  exactos de la petición: si el proxy alterase un byte, el diff lo contaría) y opción de Ollama real.
- `respx` no se instala: `httpx.MockTransport` basta para inyectar el proveedor en los tests de contrato.
- `evalgate serve` responde 501 a peticiones `stream: true` hasta F2, con cuerpo `ErrorResponse` válido.
- `make up` / `make down` en F1 levantan el proxy en local (Ollama en el host); ClickHouse llega en F3.
- `done.py` escribe `evals/reports/gate-F<N>.json` al cerrar una fase y regenera el README (R17).

**Qué queda abierto.** P-004; D-09 y sesión qa para `tests/holdout/`; entrada F1 del CHANGELOG al cerrar.

---

## 2026-09-11 · fase 1 · reserva instalada y en rojo (12 de 318); `make mutation` operativo

**Qué se intentó.** Cerrar F1 tras la instalación de D-09 por Samuel. Verificar antes el `deny` sin leer
nada; después `make done MILESTONE=1`. Mientras la reserva esté bloqueada, la tarea desbloqueable: `make
mutation` (P-003).

**Qué falló.**
1. **Reserva roja.** `make done MILESTONE=1` → paso 3: `12 failed, 306 passed, 2 warnings in 3.41s`. No hay
   canal definido para saber qué falla sin leer los tests: **Q-009**. Se para ahí la tarea (caso C).
2. **mutmut 3.7.0 copia `tests/` entero a `mutants/`**, reserva incluida, en una ruta que el `deny` no cubre
   (ADR-008). Y con las rutas de P-003 como `source_paths` los tests importaban el código **sin mutar**
   ("no test case for any mutant"): `mutants/src/evalgate/` quedaba sin `__init__.py`.
3. **Incidente, error mío:** un `mutmut run` de depuración cuyo `cd` a una copia no llegó a ejecutarse corrió
   en la raíz y creó `mutants/` (16:10:58) con la copia de `tests/holdout/`. Ese run solo recogió
   unit/property/contract y no mostró nada de la reserva; `mutants/` se borró en el acto, sin listar ni leer
   su `tests/holdout/`. Desde ahí, todo comando con efectos pasa `cwd` explícito.

**Qué número salió.**
- `deny`: `Read tests/holdout/__no_existe__.py` → "denied by your permission settings" (no "no existe").
  `~/.claude/gates/{builder,qa}.settings.json` y `c-turn.sh` idénticos byte a byte a `scripts/gates-install/`.
- `make done MILESTONE=1`: paso 1 ok (9 comprobaciones), paso 2 ok (`81 passed`, perfil nightly, 3,67 s),
  paso 3 ROJO. 12,1 s en total.
- `make mutation`: **G-MUTATION killed_pct = 89,66 %** (26 muertos / 29, 0 sin test, 0 timeout), 2,7 s;
  artefacto `evals/reports/mutation-F1.json`. Solo `pricing/` existe de las cinco rutas. Supervivientes, los
  3 en `price_at`: `or`→`and` en la comprobación de zona horaria (haría falta un `tzinfo` con
  `utcoffset() is None`) y los textos de los dos `ValueError` (ningún test mira el mensaje). Informativo:
  bloquea desde F4.
- `make gate-fast` verde: 49 tests.

**Qué se decidió** (caso H, reversibles).
- ADR-008: mutmut en una copia temporal sin la reserva; `source_paths = ["src/"]` + `only_mutate` con las
  cinco rutas de P-003; matan mutantes solo unit, property y contract; `killed_pct = killed / (total −
  skipped)`, conservador.
- No se amplían los tests de `price_at` para matar los 3 supervivientes ahora: 89,66 > 75 y la meta no
  bloquea hasta F4. Se retoma al abrir F4.

**Qué queda abierto.** Q-009 (Samuel + sesión qa); fichero suelto `thresho` en la raíz (copia idéntica de
`thresholds.lock`, creado 15:41, no es del agente; no afecta al gate).

---

## 2026-09-12 · fase 1 · Q-009 respondida (a); los 12 hallazgos de la reserva, reproducidos en ROJO

**Qué se intentó.** Cerrar F1 por el canal que abrió Q-009: qa traduce la reserva a hallazgos legibles, el
constructor los reproduce con **sus propios** tests y arregla la causa, sin leer `tests/holdout/**`.

**Qué pasó.** `docs/qa/hallazgos-F1.md` (qa, 2026-09-11) clasifica los 12 fallos como `defecto-F1` —ninguno
fuera de fase, ninguno con Ollama o red de por medio, ninguno mal planteado— y los reduce a **4 causas raíz**:

1. Las cabeceras se copian a un `dict`. En la petición, `starlette.Headers.items()` sí repite pares y el
   `dict` se queda con **el último** (H-04); en la respuesta, `httpx.Headers.items()` **funde** los repetidos
   con `", "` (H-06), que es justo lo que `Set-Cookie` no admite porque `expires` ya lleva una coma.
   Comprobado en el venv: `[('set-cookie','a=1; expires=Mon, 01 Jan…, b=2')]` frente a `multi_items()`.
2. La lista hop-by-hop es fija e ignora los campos que nombra `Connection` (H-03 y H-05, RFC 9110 §7.6.1).
3. `x-evalgate-normalized` del upstream se reenvía: el proveedor puede firmar en nombre de evalgate una
   normalización que no ha ocurrido, en las 6 combinaciones de 200/400/500 × on/off (H-07…H-12, ADR-007).
4. Lo que no es cabecera ni cuerpo se pierde o se duplica: la query string no llega al upstream (H-02) y el
   `Date`/`Server` del proveedor se reenvían, así que uvicorn añade los suyos y salen dos de cada (H-01).

**Qué número salió.** Paso ROJO (CONSTITUCION §4.1 nº 3): `make test-fast` → **22 failed, 79 passed** en
0,49 s. 12 casos en `tests/contract/test_proxy_header_fidelity.py`, **uno por hallazgo y los 12 por
aserción**; 10 en `tests/unit/proxy/test_translate.py`, por `AttributeError: 'list' object has no attribute
'items'`. Esa excepción **no es ruido de TDD**: es la causa raíz 1 en su forma más pura —las funciones recibían
un `Mapping`, y un `Mapping` no puede representar un campo repetido—, y por eso la firma pasa a pares
explícitos. La prueba de comportamiento de cada hallazgo es igualmente la de contrato, que sí falla por
aserción. `translate.py` no está en `tdd_obligatorio` (RULES §2), así que el rojo separado es disciplina
elegida, no obligación.

**Qué se decidió** (caso H, reversibles; se implementan en el turno VERDE).
- `forward_request_headers` y `forward_response_headers` pasan de `Mapping[str, str] -> dict` a
  `Iterable[tuple[str, str]] -> list[tuple[str, str]]`. Es la única forma de que una función pura represente
  un campo repetido, y deja la elección del multidict en `app.py` (`.items()` de starlette,
  `.multi_items()` de httpx), que es donde vive el acoplamiento a la librería.
- El arreglo se escribe como **regla general, no como lista de nombres**: hop-by-hop = lista fija ∪ tokens de
  `Connection` (insensible a mayúsculas), y la respuesta descarta además lo que regenera la capa que sirve
  (`date`, `server`, ya estaba `content-length`) y `x-evalgate-normalized`. Es el aviso explícito de qa: una
  lista negra con los nombres de estos 12 casos volvería a fallar en la reserva de la fase siguiente.
- H-01 se fija por su causa en contrato (esos dos campos no salen del proxy): la duplicación solo se observa
  con proceso servido, y `tests/e2e` no entra en el paso 2 de `make done`.
- `tests/contract/_proxy.py`: el `Upstream` de pruebas acepta ya una lista de pares, o no puede simular dos
  `Set-Cookie`.

**Qué queda abierto.** El turno VERDE (`translate.py` + `app.py`, que tendrá que montar la `Response` con
`raw_headers` para no fundir las repetidas), `make done MILESTONE=1` y la entrada `[0.2.0]` del CHANGELOG.
Q-009 queda RESPONDIDA en `PARA-SAMUEL.md`. Sigue abierto el fichero suelto `thresho` de la raíz.

---

## 2026-09-12 · fase 1 · F1 CERRADA: `make done MILESTONE=1` en verde, reserva 318/318

**Qué se intentó.** El paso VERDE de los 22 tests rojos del turno anterior y el cierre de F1.

**Qué pasó.** Cuatro cambios, uno por causa raíz, escritos como regla general y no como lista de nombres:

1. `translate.py` filtra **líneas** (`Iterable[tuple[str, str]] -> list[tuple[str, str]]`), no un `dict`. Un
   `dict` no puede representar un campo repetido; ADR-009 tiene el porqué y las tres opciones.
2. Hop-by-hop = lista fija ∪ tokens de la cabecera `Connection` del propio mensaje, insensible a mayúsculas.
3. `_RESPONSE_DROPPED` incorpora `date`, `server` (los escribe uvicorn) y `x-evalgate-normalized` (es la
   declaración de evalgate, no del proveedor).
4. `app.py`: reenvía `request.url.query` cruda; pasa `request.headers.items()` (starlette repite) y
   `upstream.headers.multi_items()` (httpx **funde** con `.items()`); y monta la respuesta con
   `raw_headers` en vez de `headers=`, que es un mapa y volvería a fundir las repeticiones.

Al relanzar el gate aparecieron dos rojos más, los dos previstos en `STATE.md` salvo el segundo:

- Paso 11, CHANGELOG sin entrada de F1 → escrita `[0.2.0]` con los números medidos.
- Paso 12, `detect-secrets`: 5 "hallazgos nuevos" en `.claude/state/test-inventory.json`. **No son
  secretos:** son los sha256 que el propio gate escribe en el paso 9, y cambian con cada test legítimo. Se
  excluyó ese fichero del escaneo en `SECRETS_EXCLUDED`, por el mismo motivo por el que ya estaba excluido
  `.secrets.baseline`, y **no** regenerando el baseline: refrescar el baseline cada vez que cambia un test
  es justo el hábito que un día esconde un secreto de verdad. Los ficheros que el inventario indexa se
  siguen escaneando enteros, así que el paso 12 no pierde alcance. Queda dicho aquí porque es una edición
  del guardián: `scripts/done.py`. El número (cero hallazgos nuevos) no se ha tocado.

**Qué número salió.** `make done MILESTONE=1` **VERDE** a las 00:05:37 UTC, 12 pasos:

| Paso | Número |
|---|---|
| 2 · suite completa (perfil `nightly`) | 101 passed, 3,23 s |
| 3 · **reserva** | **318 passed** (antes 12 failed / 306 passed) |
| 4 · cobertura por función | 0 funciones públicas sin test |
| 5 · cobertura de línea | 100,0 % (umbral ≥ 90) |
| 7 · metas activas | G-OPENAI-CONTRACT ratio 1,0 (n=5) · G-ADOPTION 0 líneas de diff (n=8) |
| 9 · inventario | 11 ficheros, 62 tests, regresiones 0 |
| 12 · sin secretos | 0 hallazgos nuevos |

`make mutation` relanzado: **killed_pct = 89,66 %** (26/29), idéntico al del 2026-09-11 porque `only_mutate`
son las cinco rutas de P-003 y `translate.py` no es una de ellas. Snapshot `.snapshots/2026-09-12-fase1`.
`make report` regeneró la tabla del README (R17: ningún número a mano).

**Qué se decidió.**
- ADR-009 (cabeceras como líneas). El resto, en la tabla de arriba.
- **Autorización de Samuel (chat del 2026-09-12):** *"Autorizo abrir la fase siguiente cuando make done pase
  en verde, salvo F7 y F9"*. Registrada en `PARA-SAMUEL.md`. Deroga la parada por defecto de §4.2 caso A; F7
  y F9 siguen parando, porque dependen de Q-004, D-06, D-07 y D-08.
- El H-01 se fija por su causa en contrato (`date`/`server` no salen del proxy) y no con un test de proceso
  servido: `tests/e2e` no entra en el paso 2 de `make done`. La prueba de que basta es la reserva en verde.

**Qué queda abierto.** F2 (streaming) abierta con la autorización permanente. Sigue suelto el fichero
`thresho` de la raíz (copia idéntica de `thresholds.lock`, no es del agente).

---

## 2026-09-12 · fase 2 · F2 abierta: corpus SSE de 12 casos y el rojo dirigido por corpus

**Qué se intentó.** Abrir F2 con la autorización permanente de Samuel y dar el paso ROJO: el corpus de
`tests/fixtures/sse/` y un test por fichero, antes de escribir una línea de contabilidad.

**Qué pasó.** Los 12 casos límite de `PLAN.md` §3, uno por fichero, con la decisión de qué significa cada
uno escrita en el propio fixture. Dos que la lista no distingue y aquí sí, porque el bug es distinto:

- **05 · chunk final de `usage` ausente:** llega `[DONE]` y no existe bloque `usage` en ninguna trama.
- **06 · `[DONE]` sin `usage`:** la trama final existe y trae `"usage": null`. Un `.get("usage", {})` con
  `or 0` detrás lo contaría como **cero tokens pagados**, que es peor que no contarlo: es contar mal.

Otras tres decisiones del corpus (caso H, reversibles): **01** es un transcript completo y quien corta es el
consumidor (el corte de cliente no está en los bytes, está en cómo se consumen); **07** se alimenta **byte a
byte**, así que "ñ", "€" y el emoji se parten por dentro y obligan a enmarcar sobre bytes y decodificar
después, no al revés; **08** lleva `: ping` y una trama `data:` vacía, que no son texto pero tampoco
malformadas, y llegan al cliente porque son lo que mantiene la conexión viva.

La forma del registro la fija el test, no el código: `UsageRecord(usage, text, chunks, finish_reason, end,
malformed)` con `Usage(input_tokens, output_tokens, source)` y `source ∈ {provider, estimated}`. Publicar una
estimación con la misma cara que un número exacto es justo lo que este repo dice que no se hace, así que el
origen viaja con el número. `end ∈ {done, upstream_eof, client_disconnect, timeout, error}`.

**El tokenizador no vive en el módulo:** `StreamAccountant` lo recibe inyectado. `streaming.py` es puro y
determinista dado un transcript (RULES §2); meterle un tokenizador lo ataría a una dependencia y a un
proveedor. Los tests inyectan un contador de palabras determinista.

**Qué número salió.** `pytest tests/unit/proxy/test_streaming.py` → **11 failed, 14 passed**, y los 11
fallos son `AssertionError`, ninguno de import. Comprobado el primer intento: sin `streaming.py` el fallo era
`ModuleNotFoundError`, que es ruido y no rojo; se añadió el **esqueleto** —firmas, tipos y el `finally` de
R2, `feed` sin leer nada y `result` devolviendo el registro neutro— igual que se hizo con `price_at` en F0.
El caso 12 (stream de longitud 0) pasa ya contra el esqueleto porque el registro neutro es exactamente el
esperado: se deja dicho aquí para que no parezca un test que se coló en verde.

**Qué se decidió.**
- El corte de cliente se prueba con `aclose()` sobre el generador (`GeneratorExit`). La cancelación de tarea
  (`CancelledError`) que exige R2 se prueba con Hypothesis en el paso 3, cortando en cada índice k.
- Sin `pytest-asyncio` ni `anyio` como plugin: los tests son síncronos y mueven el generador con
  `asyncio.run`. No se añade dependencia para esto (`uv add` está en `ask` y no hace falta).

**Qué queda abierto.** El VERDE. Y una pregunta que hay que hacer antes del test de propiedad: **con qué
tokenizador se mide** `G-TOKENS-STREAM` (≤ 2 % contra "el recuento del tokenizador") cuando el proveedor no
manda `usage`. Si la respuesta es `tiktoken`, es un `uv add` y por tanto CONSTITUCION §4.2 caso F.

---

## 2026-09-12 · fase 2 · VERDE del relay y las dos reglas que lo vigilan

**Qué se intentó.** El paso VERDE de los 11 rojos del corpus y las dos verificaciones mecánicas que `RULES`
exige desde F2, que hasta hoy eran prosa.

**Qué pasó.** `StreamAccountant` enmarca sobre **bytes** (busca `\n\n` en un búfer) y decodifica **después**:
es lo que hace que el fixture 07, alimentado byte a byte, reensamble "El año cuesta 42 € 🙂" en vez de
romperse. Decodificar cada chunk de red por separado es el bug que ese fixture existe para cazar.

Reglas de contabilidad, todas exigidas por un fixture: `usage` solo se cree si trae `prompt_tokens` y
`completion_tokens` **enteros** (un `usage: null` no es cero); un `data:` vacío o un `: ping` no son texto ni
tramas malformadas; una trama con `error` no cuenta como chunk y marca el final; `finish_reason` se guarda
tal cual, esté o no en el enum de OpenAI. En `relay`, el final del **transcript** (`done`, `error`) manda
sobre el final del **transporte** (`upstream_eof`, `client_disconnect`, `timeout`): cómo se cerró el socket
dice menos que lo que el proveedor llegó a decir.

**Qué número salió.**
- `pytest tests/unit/proxy/test_streaming.py` → **25 passed** (venía de 11 failed).
- `make test-fast` → **126 passed** en 0,33 s. `make gate-fast` verde; inventario 12 ficheros, 76 tests.
- `make lint`, `make typecheck` (mypy --strict sobre 5 ficheros) verdes.

**Qué se decidió** (caso H).
- **`scripts/rules/sse_corpus_coverage.py`**: lee los 12 casos de `PLAN.md` §3 —que es de solo lectura, así
  que la lista no la puede tocar el agente—, los compara **letra a letra** con `tests/fixtures/sse/CASES.yaml`
  y exige que cada fixture aparezca en algún test fuera de `tests/holdout/`. Un manifiesto aparte (y no
  metadatos dentro del `.sse`) porque el fixture 12 tiene que poder ser un fichero de 0 bytes.
- **`scripts/rules/finally_on_generators.py`** (R2, AST): todo generador asíncrono de `streaming.py` llama
  en su `finally` a un callback que recibe por parámetro —llamarlo en el camino feliz no vale, el camino
  feliz es justo el que no falla— y ningún `except` que capture `CancelledError`, `GeneratorExit` o
  `BaseException` se los traga sin volver a lanzarlos.
- **Las dos se probaron en negativo antes de darlas por buenas**, que es la diferencia entre una regla y un
  adorno: quitando `09-error-midstream.sse` → `CORPUS SSE FALLA · … ese fichero no existe`, exit 1; metiendo
  un fixture huérfano → falla; y borrando el `raise` del `except` de `relay` → `R2 FALLA · relay:158 captura
  ['CancelledError', 'GeneratorExit'] y no vuelve a lanzarla`, exit 1. Después se restauró todo.
- Ambas entran en `make gate-fast` (con las otras cuatro de `scripts/rules/`) y en el paso 1 de `make done`.

**Qué queda abierto.** El test de propiedad. Y la pregunta que **todavía no se hace**: con qué tokenizador se
mide el ≤ 2 % de `G-TOKENS-STREAM` cuando el proveedor no manda `usage`. Se hará con el número delante —
midiendo primero el error de un estimador trivial contra el `usage` real de los transcripts—, porque
preguntar antes de medir es pedirle a Samuel que decida a ciegas, y porque §4.2 caso D exige ≥ 2 intentos
medidos antes de tocar un umbral.

---

## 2026-09-12 · fase 2 · el test de propiedad, y dos hallazgos medidos contra Ollama real

**Qué se intentó.** Los dos números de F2 con Hypothesis, y —antes de preguntarle nada a Samuel— medir
cuánto se equivoca un estimador de tokens contra el `usage` real de un proveedor.

**Qué pasó · el test de propiedad.** `tests/property/test_stream_accounting.py` genera el transcript y
**recorre todos los índices de corte de cada ejemplo**, no uno sorteado: G-DISCONNECT dice "en CADA índice
k" y un corte al azar por ejemplo no es eso. Dos detalles que decidí aquí (caso H):

- `k = 0` **también pide una trama al proveedor**. Es la verdad del dominio: el chunk que ya venía en vuelo
  lo produjo el proveedor y está pagado, lo viera el cliente o no. Esa asimetría es el proyecto entero.
- Los umbrales se leen de `GOALS.yaml`, no hay literales en el test. Y el `usage` que genera Hypothesis es
  `palabras(texto) + 3` **a propósito**: si coincidiera con el estimador, el test no probaría que cuando
  llega el bloque `usage` se registra ese y no la estimación.
- El número agregado sale por `pytest_terminal_summary` (`tests/property/conftest.py`), porque `GOALS.yaml`
  declara el comando con `-q` y sin `-s`, y un `print` dentro de un test que pasa no se ve.

**Qué número salió.** `HYPOTHESIS_PROFILE=nightly` → `G-DISCONNECT ratio=1 n=8812` y
`G-TOKENS-STREAM delta_con_usage=0 delta_estimado=0`, en 5,98 s. Perfil `dev`: n=183, 0,18 s.
`make test-fast` 129 passed; `make gate-fast` verde.

**Qué pasó · la medida contra Ollama (es el hallazgo del día).** Comando: script en el scratchpad contra
`http://localhost:11434/v1/chat/completions`, Ollama 0.33.3, `qwen3.5:4b-mlx`, `temperature 0`,
`stream_options.include_usage`, 4 prompts. **Intento 1**, estimando sobre `delta.content`:

    solo content:  palabras 100,0 %  ·  caracteres/4 100,0 %  ·  caracteres/3,6 100,0 %

El 100 % no era un fallo del estimador: `content` llegaba **vacío** con `usage.completion_tokens = 600`.
`qwen3.5` es un modelo de razonamiento y manda el texto en **`delta.reasoning`** (no `reasoning_content`),
con `content` vacío hasta que termina de pensar. **Intento 2**, sumando el razonamiento:

    content+reasoning:  palabras 57,2 %  ·  caracteres/4 41,7 %  ·  caracteres/3,6 35,2 %

Los dos intentos medidos que exige CONSTITUCION §4.2 caso D antes de tocar una meta. Consecuencias:

1. **Bug, y se arregla sin preguntar:** el acumulador solo mira `delta.content`, así que un stream de
   razonamiento cortado registra **0 tokens de algo ya facturado**. Rojo escrito y por aserción:
   `assert 0 == 12` en `test_13_a_reasoning_stream_cut_before_usage_still_counts_what_was_thought`.
   Fixture `13-reasoning-tokens.sse`: **transcripción real de Ollama**, 35 tramas, bytes sin editar,
   procedencia en `CASES.yaml`.
2. **Propuesta P-005**, que sí es de Samuel: ninguna heurística se acerca al 2 % de `G-TOKENS-STREAM`, y la
   meta leída al pie de la letra compara contra el mismo tokenizador que usa el proxy, así que da 0 por
   construcción. No pido bajar el umbral: pido fijar contra qué se mide.
3. **Para F4, anotado hoy:** Ollama manda `usage.prompt_tokens_details.cached_tokens` (17 de 18 en una
   repetición). Hay fuente local y gratis para la caché de prompt, que era justo lo que D-05 dejaba sin
   medir. Se retoma al abrir F4.

**Qué se decidió** (caso H). `tests/fixtures/sse/CASES.yaml` gana una sección `extra:` y
`sse_corpus_coverage.py` la acepta: los 12 casos de `PLAN.md` §3 son un **suelo, no un techo** —RULES §4.2
dice "el conjunto cubre los 12", no "consta de 12"—, porque los proveedores reales hacen cosas que esa lista
no enumera y `PLAN.md` es de solo lectura. A cada extra se le exige lo mismo que a los 12 (que algún test lo
consuma) más el motivo y la procedencia por escrito. Comprobado: el fixture 13 sin test → la regla falla.

**Qué queda abierto.** El VERDE del razonamiento. P-005 PENDIENTE, que **no bloquea F2**: la fase puede
cerrar en verde con cualquiera de las tres opciones; lo que decide es si el número publicado significa lo
que parece.

---

## 2026-09-12 · fase 2 · VERDE del razonamiento y ADR-010

**Qué se intentó.** Poner en verde los dos rojos del razonamiento y escribir el ADR que `PLAN.md` §4 exige
para F2.

**Qué pasó.** `UsageRecord` gana `reasoning: str = ""` —con valor por defecto, así que los 26 tests que ya
pasaban no se tocan— y el acumulador guarda `delta.reasoning` **aparte** del texto de la respuesta. La
estimación **suma los dos recuentos en vez de concatenar los textos**: son dos flujos de tokens distintos y
concatenarlos pegaría la última palabra de uno con la primera del otro, que es un token de más por corte.
Mezclarlos en `text` habría metido el cuaderno de notas del modelo dentro de la respuesta.

**Qué número salió.** `pytest tests/unit/proxy/test_streaming.py` → **28 passed** (venía de 2 failed).
`make test-fast` → **132 passed** en 0,52 s. `make gate-fast` verde. Inventario: 13 ficheros, 81 tests.

**Qué se decidió.** ADR-010 (contabilidad ante desconexión), con las cuatro reglas que ya imponen los tests:
`finally` en todo generador, **el chunk en vuelo cuenta** (el corte en k=0 pide igualmente una trama y la
contabiliza), el origen (`provider`/`estimated`) viaja con el número, y el razonamiento se cuenta aparte.
Y un hueco escrito a propósito en el ADR para que no sorprenda a nadie: **solo se lee `delta.reasoning`**.
DeepSeek y vLLM usan `reasoning_content`; cuando uno de ellos entre como proveedor de salida entrará con su
fixture y su test, no con un `or` escrito hoy a ciegas sobre un proveedor que este proyecto no usa.

**Qué queda abierto.** Enganchar el streaming en `proxy/app.py`, que hoy responde 501. Y un agujero que he
encontrado revisando las metas activas: **`G-TOKENS-EXACT` bloquea desde F2 y su comando apunta a
`tests/contract/test_token_reconcile.py`, que no existe**. Sin él, `make done MILESTONE=2` fallará en el
paso 7; está anotado como punto 2 de `STATE.md`.

---

## 2026-09-12 · fase 2 · el proxy ya hace streaming de verdad; la reserva defiende la fase anterior

**Qué se intentó.** Montar el streaming en `proxy/app.py`, cerrar los dos agujeros de metas que quedaban
(`G-TOKENS-EXACT` sin test, `G-OPENAI-CONTRACT` sin tramas SSE) y cerrar F2.

**Qué pasó.**
- `app.py` abre el upstream con `stream=True`, envuelve `aiter_bytes()` en `relay` y devuelve un
  `StreamingResponse` con las cabeceras por pares. El generador cierra el interior con `await
  stream.aclose()` **explícitamente**: dejárselo al recolector de basura significaría que el registro de uso
  sale cuando Python quiera, y no mientras la petición sigue siendo la petición (R2).
- El sumidero de uso es `ProxySettings.on_usage`, se **llama y nunca se espera**, y va envuelto para que no
  pueda tumbar la petición (R1). Hay test: un sumidero que lanza `RuntimeError` no cambia ni el estado ni el
  cuerpo de la respuesta.
- `translate.record_of_completion` hace lo mismo para no-streaming, y devuelve `None` cuando el cuerpo no es
  una respuesta de chat: inventar un cero no es "no contabilizar", es contabilizar mal.
- Se retiran los dos tests de F1 que daban por bueno el `501` (`PLAN.md` fila F1). No se borran: se
  sustituyen por el comportamiento de F2.

**Hallazgo de contrato (ADR-011).** Al validar tramas SSE por primera vez, **ninguna** pasaba:
`['choices', 0, 'finish_reason'] -> None is not of type 'string'`. No es el proveedor: el snapshot pineado
se declara `openapi: 3.1.0` y usa **111 veces** `nullable: true`, que es palabra de OpenAPI 3.0 y **ningún
validador de JSON Schema respeta**. Leído al pie de la letra, el contrato de OpenAI rechaza lo que manda el
propio OpenAI. Medido sobre la transcripción real: **32 de 34 tramas inválidas** leyendo el snapshot tal
cual, **0 de 34** honrando `nullable`. El validador de contrato traduce ahora `nullable` a unión con `null`
(y al `enum`, que era la segunda mitad del problema), el snapshot sigue byte a byte el descargado, y el
motivo está escrito **como test**, no como comentario.

**Qué número salió.**
- `make gate-fast` verde. Suite completa con perfil nightly: **149 passed**. Inventario: 14 ficheros, 91
  tests (ahora 96).
- `G-TOKENS-EXACT ratio=1 n=5` sobre respuestas **grabadas**: las 2 sintéticas de F1 y 3 reales de Ollama
  (`tests/fixtures/openai/recorded/`, con su procedencia y su tabla).
- `G-OPENAI-CONTRACT`: 34 de 34 tramas SSE reales validan contra el esquema pineado.
- `G-MUTATION` = **85,28 %** → **88,96 %** tras cerrar huecos (145/163). Umbral 75, informativa hasta F4.
- **`make done MILESTONE=2`: ROJO en el paso 3, reserva `8 failed, 310 passed`.**

**Qué se decidió** (caso H). Los mutantes supervivientes se **analizaron uno a uno** antes de escribir nada:
cinco eran huecos de test reales y se cerraron con casos que prueban algo —dos tramas en un mismo chunk de
red, una trama con `event:`/`id:`/comentario antes del `data:`, varias tramas malformadas seguidas, un
bloque `usage` a medio escribir, y un `choices` con un elemento que no es objeto—. Los 12 que quedan son
**equivalentes** (`_done = False` → `None`, `find` → `rfind` con un lector orientado a líneas, dos ramas que
acaban las dos en `continue`) o solo alcanzables con tramas de varios `data:`, que el estándar SSE manda
concatenar y ningún proveedor del alcance usa. **No se escriben tests para matarlos:** un test cuyo único
propósito es subir el porcentaje de mutación es exactamente el adorno que este repo dice no publicar. Queda
anotado como hueco conocido: el lector trata cada línea `data:` como una carga independiente en vez de
concatenarlas; si algún día entra un proveedor que las parta, entra con su fixture.

**Qué queda abierto.** **Q-010**: la reserva se escribió para F1, donde el `501` a `stream: true` era el
comportamiento correcto y estaba en el plan. F2 entrega lo contrario. Los 8 fallos son, casi con seguridad,
la reserva defendiendo lo que esta fase viene a sustituir — pero **no puedo comprobarlo sin leerla**, así que
va por el mismo canal que Q-009: una sesión `claude-qa` que la actualice y escriba `hallazgos-F2.md`.
El resto de F2 está terminado.

---

## 2026-09-20 · F2 · H-13: la contabilidad cerraba fuera de la petición (paso ROJO)

**Qué se intentó.** qa entregó `docs/qa/hallazgos-F2.md`: los 8 fallos de la reserva eran **uno solo
repetido** —la reserva de F1 defendiendo el `501` a `stream: true` que F2 retira—, ninguno un defecto. Tras
darle la vuelta a la reserva y añadir 31 tests nuevos, queda **349 tests, 1 falla**, clase `defecto-F2`:
**H-13**. Este turno escribe solo su test, según el ciclo (CONSTITUCION §4.1 paso 3).

**Qué falló, y dónde estaba el hueco.** Con el cliente cortado a mitad de respuesta, el registro de uso
**no sale dentro de la petición**. `relay` tiene su `finally` y R2 se cumple al pie de la letra, pero entre
el relevo y el cliente está `StreamingResponse`: cuando llega `http.disconnect`, su grupo de tareas cancela
la tarea de respuesta mientras el generador está suspendido en su `yield`, y un `async for` no cierra el
generador al salir. Nadie lo cierra. El `finally` corre cuando el recolector quiere, que en un proceso
servido de larga vida es un instante arbitrario posterior — y nunca, si el proceso muere antes.

**Por qué la meta no lo veía, con el número delante.** `G-DISCONNECT` se mide sobre `relay`, donde es el
propio test quien cierra el generador y el `finally` corre en el acto. La misma ejecución que deja la
petición servida sin registro publica **`G-DISCONNECT ratio=1 n=861`** (perfil dev). El 1 es cierto para lo
que mide y no cubre el montaje, que es entregable de F2 igual que el módulo.

**El arnés, que es la mitad del trabajo.** Primer intento: **22 passed**, verde y falso. `asyncio.run`
cierra el bucle al terminar y `loop.shutdown_asyncgens()` finaliza todo generador pendiente, así que el
registro "aparecía" — fuera de la petición, que es justo lo que se quiere prohibir. Un `TestClient` tampoco
vale: lee el cuerpo entero antes de devolver. El test se conduce por el **borde ASGI** (`await app(scope,
receive, send)`, `http.disconnect` emitido tras k tramas) y lee el sumidero **dentro de `serve()`, antes de
que el bucle se cierre**. `Served` guarda las dos lecturas —`at_return` y `eventually`— porque son dos
afirmaciones distintas: **cuándo** sale el registro y **qué** dice.

**Qué número salió.** `tests/contract/test_stream_disconnect_accounting.py`: **7 failed, 15 passed**, rojo
por la aserción en los 7 índices de corte (`0 == 1` registros al retornar la llamada ASGI). Los 15 verdes
son el contenido del registro (`end=client_disconnect`, texto y razonamiento completos, `estimated`, nunca
menos tokens de los entregados), la no duplicación y el control sin corte. Suite completa: **7 failed, 169
passed**; `make lint` verde. Falla el **cuándo**, no el **cuánto**, exactamente como qa lo acotó.

**Qué queda abierto.** El arreglo tiene que ser **general** y llevar regla mecánica propia, como pide qa:
un `finally` que existe pero corre cuando el recolector quiere cumple la letra de R2 y pierde su
invariante, y `finally_on_generators.py` no puede verlo porque solo mira `streaming.py`. Va en el turno
VERDE. **P-006** (ampliar el `comando` de `G-DISCONNECT` al montaje) queda PENDIENTE y **no bloquea F2**.

---

## 2026-09-20 · F2 · VERDE de H-13: el cierre lo aprieta el montaje, y una regla nueva lo vigila

**Qué se intentó.** El paso VERDE del turno anterior: que el registro de uso salga **dentro** de la
petición cuando el cliente cuelga, de forma general y no para el caso del test, más la regla mecánica que
qa pidió en `hallazgos-F2.md`.

**Qué pasó.** El arreglo es una subclase, `AccountedStream`, y son seis líneas: `StreamingResponse` recorre
el cuerpo con `async for`, y `async for` **no cierra lo que recorre**. Su `__call__` envuelve ahora la
llamada ASGI entera en un `try/finally` y cierra el generador en el `finally`. Es el único sitio que cubre
las tres salidas que tiene starlette 1.6.0 —el cuerpo se agotó; el cliente colgó y el grupo de tareas
canceló la tarea con el generador suspendido en su `yield`; o la ruta de `spec_version >= 2.4` lanzó
`ClientDisconnect`—, y por eso no se puso el cierre en `stream_response` ni en el generador: ahí solo se
cubre una.

Lo que estaba mal **no era `relay`**. Su `finally` era correcto y R2 se cumplía al pie de la letra. Lo que
faltaba era alguien que apretara el gatillo mientras la petición seguía siendo la petición. Esa es la
diferencia entre cumplir la letra de una regla y conservar su invariante, y es exactamente lo que qa
escribió: *un `finally` que existe pero corre cuando el recolector quiere*.

**Qué número salió.**
- `tests/contract/test_stream_disconnect_accounting.py`: **22 passed** (venía de 7 failed, 15 passed).
- `make done MILESTONE=2`: pasos 1-10 **VERDES**. Suite completa con perfil nightly **176 passed**;
  **reserva 349 passed** (venía de 8 failed, 310 passed en F1 y de 1 failed, 348 passed tras qa).
- `G-DISCONNECT ratio=1 n=210`, `G-TOKENS-EXACT ratio=1 n=5`, `G-OPENAI-CONTRACT ratio=1 n=7`,
  `G-ADOPTION lineas_de_diff=0`, `G-LINE-COV 98,7 %`, `G-FUNC-COV 0`. Inventario: 15 ficheros, 100 tests.

**Qué se decidió** (caso H). **`scripts/rules/stream_closed_in_request.py`**, y no mira `finally`: mira
**quién aprieta el gatillo**. Dos comprobaciones sobre el AST de `src/evalgate/proxy/`: (1) nadie monta un
`StreamingResponse` pelado —construirlo *es* el defecto, porque hereda el `async for` que no cierra—, y
(2) toda subclase suya cierra su cuerpo con `aclose()` en un `finally` de `__call__`. `R2` por AST no podía
ver esto: `finally_on_generators.py` solo mira `streaming.py`, que es justo el fichero que sí cumplía.

**Probada en negativo antes de darla por buena**, como las otras seis: quitando el `finally` de
`AccountedStream` → `R2 (montaje) FALLA · app.py:88 AccountedStream hereda de StreamingResponse y no
cierra su cuerpo…`, exit 1; volviendo a `StreamingResponse(forwarded(), …)` en `streamed` →
`R2 (montaje) FALLA · app.py:152 monta un StreamingResponse pelado…`, exit 1. Después se restauró
`app.py` byte a byte y se comprobó con `diff`. La regla entra en `make gate-fast` y en el paso 1 de
`make done`, que pasa de 11 a **12 comprobaciones**.

**Qué queda abierto.** P-005 está APROBADA (opción a) y su trabajo —publicar la cobertura de `usage` como
número propio y sacar la estimación de la meta de exactitud— **no está hecho**: hoy el artefacto sigue
publicando `delta_estimado=0`, que es lo que la propuesta dice que no significa lo que parece. Va en el
turno siguiente, antes de abrir F3. **P-006 sigue PENDIENTE** y no bloquea: el defecto está arreglado y
vigilado con o sin ella; lo que decide es si el número publicado de G-DISCONNECT cubre el montaje además
del módulo.

---

## 2026-09-20 · F2 CERRADA: `make done MILESTONE=2` en verde, y el número de P-005 que NO se publica

**Qué se intentó.** Aplicar P-005 (a), que Samuel aprobó hoy, y cerrar la fase.

**Qué pasó · la mitad que sí se puede cumplir.** `G-TOKENS-STREAM` deja de comparar la estimación contra el
tokenizador que el propio test inyecta. Con `usage` del proveedor, el umbral es 0 y se cumple. Sin `usage`,
lo que se exige es que el registro lo **declare** (`source: estimated`) y que el reensamblado no haya
perdido texto. **`delta_estimado=0` ha dejado de publicarse**, y esa es la línea que importa: era el número
que sonaba a exactitud de facturación midiendo reensamblado. El umbral no se tocó; `thresholds.lock` sigue
cuadrando con `GOALS.yaml`.

**Qué pasó · la mitad que no, con la medida delante.** P-005 (a) pide además publicar "qué porcentaje de
streams trajo `usage`". Antes de escribirlo lo medí, y por eso no está: sobre el test de propiedad da
**0,453 por transcript completo** (n=1000) y **0,101 por índice de corte** (n=8951). El primero es
literalmente el `st.booleans()` con que Hypothesis decide si el transcript lleva `usage`; el segundo, su
reparto de cortes. Los dos describen **el test**, no a los proveedores, y `make report` los habría puesto
en el README al lado de `G-TOKENS-STREAM`, donde cualquiera los leería como "solo 1 de cada 10 streams
trae usage". Ese número necesita streams grabados de verdad y llega con el tráfico real de F4 (D-05).
Escrito como matiz de P-005 en `PARA-SAMUEL.md` y anotado en `bloqueado_por`. Se revirtió también el
`share()` que había añadido al `Meter`: infraestructura que no se usa es deuda.

**Qué número salió.** `make done MILESTONE=2` → **VERDE, 12 de 12 pasos**.

| Paso | Número |
|---|---|
| 1 · estáticos y reglas | 12 comprobaciones (eran 11: entra `stream_closed_in_request.py`) |
| 2 · suite completa | 176 passed, perfil nightly |
| 3 · **reserva** | **349 passed** |
| 4-5 · cobertura | G-FUNC-COV 0 · G-LINE-COV 98,7 % (umbral 90) |
| 7 · metas activas | G-DISCONNECT ratio=1 n=209 · G-TOKENS-EXACT ratio=1 n=5 · G-TOKENS-STREAM delta_con_usage=0 · G-OPENAI-CONTRACT ratio=1 n=7 · G-ADOPTION 0 líneas |
| 9-10 | 15 ficheros, 100 tests, regresiones=0 · deuda 0 |

`G-MUTATION` 88,96 % (145/163) sin cambio: `app.py` no está en el alcance de mutación (es montaje, R2 del
mapa). Snapshot `.snapshots/2026-09-20-fase2`. CHANGELOG `[0.3.0]`. README regenerado con `make report`:
ahora publica `delta_con_usage=0` y ya no `delta_estimado=0`.

**Qué se decidió.** Abrir **F3** por la autorización permanente de Samuel (2026-09-12) y **parar antes de
su primer paso**: F3 necesita `opentelemetry-sdk`, `opentelemetry-exporter-otlp`, `clickhouse-connect` y
`testcontainers`. Q-007 (a) las autorizó en bloque, pero `uv add` está en `ask` y `CLAUDE.md` exige permiso
explícito **en el mismo turno**. Pedido; sin respuesta no se instala nada.

**Qué queda abierto.** El `uv add` de F3 (bloquea ya). P-006 PENDIENTE, que no bloquea. La `cobertura_usage`
de P-005, que espera tráfico real. Q-005 (a): la ventana de exclusividad se pide al llegar a `make bench`.

---

## 2026-09-20 · F3 abierta · P-006 aplicada de verdad, y `telemetry/semconv/` generado

**Qué se intentó.** Aplicar P-006, instalar las dependencias que Samuel autorizó y entregar el primer
artefacto de F3: `telemetry/semconv/` generado desde el commit pineado.

**Qué pasó · P-006 no se cumplía sola.** Samuel cambió el `comando` de `G-DISCONNECT` para incluir el
fichero de contrato del montaje. Lo ejecuté antes de darlo por hecho: **`n=208`, exactamente lo que
imprime el fichero de propiedad a solas**. Los 22 tests de contrato hacían que el comando *pasara*, pero
`ratio`/`n` salen del `Meter` y un fichero que solo pasa **no aporta un caso al número**: la meta habría
seguido publicando la capa que ya funcionaba, que es justo lo que la propuesta venía a arreglar. Metré el
predicado de la meta en el borde ASGI —hay registro cuando la petición retorna **Y** nunca cuenta menos
tokens de los emitidos— y el número pasó a **222** (215 en el relevo + 7 en el montaje). Se volvió a cerrar
F2 con la meta ya redefinida; README y CHANGELOG cuadrados con el artefacto.

**Qué pasó · las dependencias.** `opentelemetry-sdk==1.44.0`, `opentelemetry-exporter-otlp==1.44.0`,
`clickhouse-connect==1.8.0` en tiempo de ejecución y `testcontainers==4.15.0` en el grupo `dev`. Versiones
resueltas con `uv pip compile` **antes** de tocar `pyproject.toml`, para que entraran con `==` y no con el
`>=` que `uv add` escribe por defecto (R18). `pip-audit`: **sin vulnerabilidades conocidas**. R18 pasa de
19 a 23 dependencias.

**Qué pasó · el generador, y el agujero del contrato que apareció al usarlo.** `scripts/gen_semconv.py`
tiene tres modos y la separación es el diseño: `--fetch` descarga el tarball del commit del lock y
**vendoriza** el modelo en `docs/spec/otel-semconv/` con su manifiesto de hashes —único paso con red—; sin
flags, renderiza el paquete desde ese snapshot, offline y determinista; `--check` vuelve a renderizar y
compara. Sin el snapshot vendorizado, el test de contrato tendría que salir a la red y R15 lo prohíbe.

Y al escribirlo apareció esto: el contrato §4 declara **once** atributos obligatorios en el span, y dos de
ellos —`error.type` y `server.address`— **no están en `model/gen-ai/`**, que es la ruta que pinea el lock.
La elección era escribirlos a mano —rompiendo R5 y el "no se escribe a mano" del mapa en el primer fichero
de la fase— o vendorizar `model/error/` y `model/server/` **del mismo commit**. Hice lo segundo, está
declarado en la cabecera del manifiesto, y **no desancla nada**: mismo sha, diez ficheros fijados por hash
uno a uno. La línea `path:` del lock es de Samuel, así que va como **P-007**.

**Qué número salió.**
- `tests/contract/test_semconv_generated.py`: **6 passed**, de 4 failed / 2 passed. El rojo fue por
  **aserción**, no por `ModuleNotFoundError`: se puso antes el esqueleto, como con `price_at` en F0.
- `make gate-fast` verde: **182 passed**, 16 ficheros, 106 tests, deuda 0.
- `mypy --strict` sobre 6 ficheros, incluido el paquete generado: sin incidencias.

**Qué se decidió** (caso H). Dos reglas nuevas, **las dos probadas en negativo y restauradas después**:
- **`scripts/rules/no_genai_literals.py`** da cuerpo a R5, que hasta hoy era prosa en `CLAUDE.md`. Mira el
  **AST y no el texto**: un `gen_ai.` en un comentario es prosa y puede explicar precisamente esta regla; lo
  que se prohíbe es el literal que se ejecuta. Los tests quedan fuera a propósito: un test de contrato que
  importara el nombre del módulo que valida no comprobaría nada. Negativo: literal en `translate.py` →
  `R5 FALLA · …:161`, exit 1.
- **`gen_semconv.py --check`** en el gate. Negativo: una constante añadida a mano al fichero generado →
  `SEMCONV FALLA · … no es lo que el generador produce`, exit 1.
- El paquete generado lleva `S105` ignorado en `pyproject.toml`, acotado a esa ruta y con el motivo
  escrito: `TOKEN_USAGE = "gen_ai.client.token.usage"` no es una credencial, los nombres los pone
  OpenTelemetry, y un fichero que no se edita a mano no puede llevar un `noqa`.

**Qué queda abierto.** El exportador con cola acotada y `app.spans.dropped` (R1: `proxy/` no importa
`telemetry/exporters/` ni hace `await` sobre un export). Las migraciones de ClickHouse con
`create_schema:false`. El nivel 2 tumbando el contenedor a mitad del test. Y antes de `make bench`, pedir a
Samuel la ventana de exclusividad de Q-005 (a) y parar. P-007 PENDIENTE, no bloquea.

---

## 2026-09-29 · F3 pasos 1 y 2: `LlmCall`, traductor, cola acotada y R1 mecánica. Parada en ROJO de streaming

**Contexto.** Samuel aprobó P-007 (a) y editó él la línea `path:` del lock; respondió Q-004 (b) —dos tandas
de 50, la primera al abrir F5—. Antes de tocar nada, `make gate-fast` verde (182 passed): nueve días sin
cambios desde el 20-09.

**Qué se intentó · paso 1.** El modelo interno y su traducción, en `telemetry/model.py` y
`telemetry/translate.py`. `LlmCall` usa nombres propios y **no tiene ningún campo que pueda llevar el texto
de un prompt o de una respuesta**: lo que el modelo no puede contener, ningún exportador lo puede filtrar
(R6 por construcción; el test del canario llega con el montaje). El traductor coge los nombres de
`telemetry/semconv/` y nunca los escribe (R5 sigue en verde, ahora sobre 13 módulos).

**Qué número salió · paso 1.** `tests/contract/test_otel_attrs.py` (el comando de G-OTEL-CONTRACT) emite
spans **de verdad**, a través del SDK hasta un exportador en memoria, y los contrasta con los nombres del
contrato **escritos a mano en el test**, no importados. Rojo primero por aserción (0 spans emitidos), después
verde: **G-OTEL-CONTRACT ratio=1 n=25** en perfil dev y **n=1000** en nightly. Mide cuatro cosas: los ocho
atributos "sí" siempre presentes, los "si aplica" solo cuando la llamada los tiene, tipos correctos, y que no
salga ningún nombre que el registro pineado no declare ni ningún `app.*` fuera de los del contrato.
Cobertura de línea global 98,7 → **99,1 %**; los tres ficheros de telemetría al 100 %.

**Qué se decidió (caso H).**
- `app.usage.source` como extensión propia (namespace `app.*`, que el contrato reserva para lo nuestro): P-005
  (a) exige que un recuento estimado viaje declarado, y un span es un registro.
- El campo se llama `usage_source` y no `token_source`: ruff (S106) confundía "token" con una credencial, y
  renombrar era mejor que un `noqa`.
- `temperature=0.0` y un coste de 0 € son valores, no ausencias: el traductor compara con `is not None`, y
  hay un test que lo fija. Son justo los casos más comunes aquí (ejecuciones deterministas, modelos locales).
- Los tres ficheros nuevos entran en `[tool.gate].testable` de `pyproject.toml`. Eso endurece el gate y se
  aparta del "literal" de RULES §4.1, así que va como **P-008** (no bloquea).

**Qué pasó · paso 2, y el hallazgo.** La cola de R1 iba a ser el `BatchSpanProcessor` del SDK, que ya tiene
cola acotada. Leyendo su código (`opentelemetry/sdk/_shared_internal`, SDK 1.44.0): **ignora el valor de
retorno de `exporter.export()`**. Un almacén que contesta `FAILURE` pierde el lote sin que nadie lo cuente,
y `app.spans.dropped` diría 0 con ClickHouse caído, que es justo el caso para el que existe el contador. Así
que `telemetry/processor.py` es propio: `on_end` hace `put_nowait` o cuenta, y nada más, porque corre en la
ruta de la petición. Un span acaba **exportado** (el almacén dijo SUCCESS) o **descartado** (no cupo, el
almacén lo rechazó o el procesador ya estaba cerrado). No hay una tercera salida. Lotes y no inserciones
sueltas, porque el almacén es ClickHouse (una parte por inserción).

**Qué número salió · paso 2.** 8 tests unitarios. En rojo primero los 7 iniciales, todos por aserción. El
central: con el almacén colgado dentro de `export`, 10 spans nuevos se reparten en **4 encolados y 6
descartados**, y `on_end` vuelve en **< 0,5 s** en total (esperar al almacén habrían sido 5 s). Estable en 5 de
5 repeticiones. Un primer diseño tardaba 4,5 s porque `force_flush` esperaba al intervalo del lote; ahora
fuerza el envío y el fichero corre en 0,8 s, dentro del presupuesto de `test-fast`.

**R1 mecánica.** `scripts/rules/no_blocking_export.py` (AST sobre `proxy/`) prohíbe importar exportadores (los
nuestros y los del SDK) y hacer `await` sobre `export()`/`force_flush()`. **Probada en negativo** dos veces
sobre `app.py` (un import y un `await sink.export([])`: exit 1 las dos) y restaurada byte a byte con `diff`.
Entra en `gate-fast` y en el paso 1 de `make done`, que pasa de 12 a **13 comprobaciones**.

**Qué queda abierto · y dónde paro.** Para montar `LlmCall` en el proxy faltan dos datos que solo están
dentro del stream: **qué modelo respondió** (`response.model`, obligatorio en el contrato) y **cuándo llegó el
primer chunk con contenido** (TTFT, con reloj inyectado para no romper la pureza del módulo). Los dos van en
`proxy/streaming.py`, que es TDD obligatorio, así que este turno termina **en ROJO**: 16 tests fallando por
aserción (13 de modelo, uno por fixture del corpus más el no-streaming; 2 de TTFT; y el `test_01` ampliado con
el modelo, que suma un assert y no quita ninguno). Esqueleto puesto (campos a `None`, `clock` aceptado sin
usar), como con `price_at` en F0.
Después: verde → montaje en `app.py` → exportador a ClickHouse. Queda por decidir si va **directo** con
`clickhouse-connect` (autorizado en Q-007) o por el Collector con `clickhouseexporter` (STACK §6). Tras leer el
SDK me inclino por el directo: con el Collector en medio, el proxy recibe SUCCESS aunque ClickHouse esté caído y
`app.spans.dropped` volvería a no medir nada. Lo cerrará el ADR obligatorio de F3, con el esquema de
`otel_traces` del exportador del Collector para que cambiar de camino sea configuración.

---

## 2026-09-29 (tarde) · F3 pasos 2b, 3 y 4: verde de streaming, montaje, ClickHouse y nivel 2. Parada ante el bench

**Verde de streaming.** `UsageRecord` gana `model` (el primero que dice el stream) y `first_content_ns` (el
reloj inyectado, en el primer chunk con `content` **o** `reasoning` no vacío; un pensamiento es un token
generado y cobrado). Al ponerlo en verde, **8 tests antiguos (02-09) se pusieron rojos**: comparaban el registro
entero con `==` y exigían sin decirlo `model=None`, lo contrario de lo que el rojo de esta mañana pedía para
cada fichero del corpus. Se amplió su registro esperado con `model="qwen3.5:4b-mlx"`, que es lo que dice cada
fixture. Ninguna aserción quitada ni relajada; el inventario sube. **Reserva 349/349**, mirada solo en su línea
de resumen.

**Montaje.** `proxy/translate.py` gana `request_facts` (modelo, temperatura y límite de la petición, sin un solo
mensaje: R6) y `llm_call`, puras. `app.py` llama a un sumidero `on_call` que nunca espera. El test de contrato
`tests/contract/test_no_prompt_leak.py` (el que RULES R6 nombra) monta la tubería real, con un canario en la
pregunta y en la respuesta, en streaming y sin él. **Probado en negativo**: con una fuga simulada en
`request_facts` lo caza en el nombre del span y en `gen_ai.request.model`; `translate.py` se restauró byte a byte.

**Caso G · Q-011.** El contrato exige `gen_ai.response.model` siempre, pero un stream de longitud cero o un corte
antes del primer chunk nunca dicen quién respondió, y el prompt ya está cobrado. Preguntado a Samuel. Mientras,
la opción (a) provisional: se omite solo en ese caso y no se inventa. Es reversible y el test la documenta.

**Almacén (ADR-012).** Directo a ClickHouse con `clickhouse-connect`, en la tabla `otel_traces` del Collector.
El motivo: con el Collector en medio, el proxy recibe SUCCESS con ClickHouse caído. Migraciones propias
numeradas e inmutables (sha256 en `schema_migrations`, misma regla que R4). Conexión perezosa y rehecha tras
cada fallo: un ClickHouse caído al arrancar no impide arrancar al proxy (hallado al escribir el CLI:
`get_client` consulta al servidor al crearse). `evalgate migrate` y `evalgate serve --clickhouse` son nuevos.

**Qué número salió · nivel 2, primer contenedor del repo** (ClickHouse 26.4 fijado por digest `c7796a13…`).
- Ida y vuelta: timestamp y duración **exactos al nanosegundo**; atributos con la codificación del Collector.
- **G-TRACE-0 = 0 perdidos**: 6000 servidas a 50 rps durante 120 s, contadas como filas en ClickHouse. `dropped=0`.
- **G-TRACE-DEGRADE: Δp95 = −0,03 ms** (p95 0,563 → 0,534 ms). `docker kill` en la petición 50 de la segunda
  fase, con tráfico. 2000/2000 servidas; 1000 exportadas (= 1000 filas antes de matar) + 1000 descartadas y
  contadas: `exported + dropped == emitidos`. Informe en `evals/reports/degradation-2026-09-29.json`.
  **Matiz honesto:** se midió con 4 contenedores de otros proyectos encendidos. No es un benchmark (ese es
  G-LAT-*), pero queda dicho.

**Dos veces me paró el gate, y las dos tenía razón.** R5 cazó un `gen_ai.provider.name` que había puesto en el
texto de ayuda del CLI. G-FUNC-COV contó como funciones sin test los cuatro métodos del `Protocol`
`StoreClient`, que son solo firmas: el tipo se movió a `telemetry/exporters/`, que es I/O, en vez de relajar el
script.

**Bench.** `scripts/bench.py` + `bench_stub.py`, pegados al protocolo: tres procesos (stub en loopback, el
`evalgate serve --clickhouse` real y el cliente), trazas **activas** contra ClickHouse real, brazos
intercalados, 50 + 500. Probado solo en modo humo (5 peticiones, escrito en el scratchpad; el script se niega
a escribir un humo en `evals/`). **No se ha medido nada publicable**: falta la ventana de Q-005 (a).
