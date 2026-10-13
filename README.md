# Evalgate · puerta de calidad LLM

> **Un evaluador no evaluado es un adorno.** Evalgate es una puerta de calidad para aplicaciones LLM que
> publica sus propias tasas de error: la concordancia de su juez con un humano, su tasa de falsos positivos y
> el efecto mínimo que es capaz de detectar, los tres medidos.

**Estado:** F0 a F6 cerradas con el gate en verde. **F7, la meta-evaluación, está medida y publicada con
el gate en rojo:** de sus cuatro metas, tres no alcanzan su umbral (la concordancia del juez, la tasa de
falsos positivos y el efecto mínimo detectable) y una sí (la potencia). Los números, sus umbrales y las dos
medidas completas están en [La puerta, medida](#la-puerta-medida-meta-evaluación); no se ha bajado ningún
umbral. F9 (e2e, autopuerta y publicación) está en curso sobre esa base. Este README solo
afirma lo que está medido: lo que no tiene fila en [Números medidos](#números-medidos) no se da por hecho.

## Qué es y qué no es

- **Un proxy** compatible con `/v1/chat/completions` de OpenAI, que se adopta cambiando una variable de
  entorno (`OPENAI_BASE_URL`), sin tocar código. Habla con cualquier runtime compatible con OpenAI; hoy,
  Ollama en local (`docs/adr/002-litellm-nunca-como-proxy.md`).
- **Un motor de evaluación y una puerta** que compara dos informes con bootstrap pareado y corrección de
  Holm, y devuelve 0 o 1 para CI. El propio repositorio pasa por ella en cada cambio
  (`evalgate eval self-gate`).
- **No** es una plataforma de observabilidad con interfaz (`docs/adr/004-evalgate-frente-a-langfuse.md`) ni
  compite en latencia con pasarelas en Go (`docs/adr/003-evalgate-frente-a-bifrost.md`).

## Cómo encaja

![Diagrama animado de Evalgate: la app, el proxy y el proveedor; contabilidad de tokens, telemetría, precios, evaluación emparejada y la puerta](docs/animacion/evalgate-flujo.gif)

Nueve escenas en bucle, cada una marcada como hecha, en curso o pendiente. Las cifras que aparecen dentro
(tokens, tarifas, coste) son valores de ejemplo para ilustrar el flujo, no mediciones: las mediciones están
en [Números medidos](#números-medidos). El código de la animación está en `docs/animacion/`; se abre
sirviendo esa carpeta (`python -m http.server -d docs/animacion`) y carga React desde un CDN.

El mismo flujo, en estático:

```
  tu app ──► evalgate (proxy) ──► proveedor compatible con OpenAI (hoy: Ollama)
                  │
                  ├─► registro de uso: tokens y coste, también si el cliente corta   [F2, cerrada]
                  ├─► traza OTel ──► cola acotada ──► ClickHouse                     [F3, cerrada] 
                  │
  informe A ─┐
             ├─► evalgate eval compare ──► exit 0 | 1 para CI                        [F5-F6, cerradas]  
  informe B ─┘
```

Tres piezas que comparten almacén y se usan por separado: el proxy registra, el motor de evaluación mide
y la puerta decide. La puerta es la única con opinión, y por eso es la que tiene que demostrar cuánto se
equivoca.

## Qué mide

**De tu aplicación**, por caso y sobre un conjunto de casos fijo (`src/evalgate/evals/metrics/`):

| Métrica | Qué cuenta | ¿Bloquea? |
|---|---|---|
| `answer_correct` | La respuesta contiene la referencia, por palabras enteras, y ninguna de las respuestas excluidas | sí |
| `context_recall` | Parte de los documentos relevantes que el sistema recuperó (recall@k) | sí |
| `abstencion_incorrecta` | El sistema dijo "no consta" cuando la respuesta sí estaba | sí |
| `faithfulness` | Un juez LLM, distinto del modelo que genera, dice que la respuesta se apoya en el contexto | no: retirada, su juez no concuerda lo bastante con la etiqueta humana |
| `juez_ilegible` | El veredicto del juez no se pudo leer | no: solo informa |

Ninguna métrica llama a un modelo: el juicio se obtiene aparte, se graba y se reutiliza.

**De cada llamada**, en el proxy: tokens de entrada y de salida (también si el cliente corta el flujo),
coste con una tabla de precios fechada, latencia y una traza OpenTelemetry.

**De la propia puerta**, que es la tesis del proyecto: cuánto concuerda su juez con una persona, cuántas
veces bloquea un sistema que no ha cambiado, qué caída mínima distingue del ruido y cuántas veces bloquea una
caída real. Están en [La puerta, medida](#la-puerta-medida-meta-evaluación), con tres de las cuatro por
debajo de su umbral.

## Instalación

Requisitos: Python 3.12 y [`uv`](https://docs.astral.sh/uv/). No está publicado en PyPI: se instala desde
el repositorio.

```bash
git clone https://github.com/samuvm/evalgate.git
cd evalgate
uv sync --locked            # dependencias fijadas con hash
uv run evalgate --help
```

Para el proxy hace falta además un servidor compatible con la API de OpenAI al que reenviar. Todo lo medido
aquí es contra [Ollama](https://ollama.com) en local (`localhost:11434`); contra un proveedor de pago no
está probado.

## Usarlo en tu sistema

Las tres piezas se usan por separado.

### 1. El proxy delante de tu aplicación

```bash
uv run evalgate serve --port 8080 --upstream http://localhost:11434/v1
```

En tu aplicación solo cambia una variable de entorno; el código no se toca:

```bash
OPENAI_BASE_URL=http://127.0.0.1:8080/v1 python tu_app.py
```

El proxy sirve `POST /v1/chat/completions`, con y sin streaming, y cuenta cada llamada. Con
`--clickhouse <DSN>` guarda además las trazas (`uv run evalgate migrate` crea el esquema); sin él, sigue
funcionando. Si el almacén se cae, la petición no se entera.

### 2. La puerta en tu CI

La puerta compara dos informes de evaluación, el de tu rama principal y el de tu cambio, y devuelve un código
de salida:

```bash
uv run evalgate eval compare base.json head.json --gate gate.yaml --goals comparacion.yaml --out resultado.json
# 0 = puede entrar · 1 = bloqueado · 2 = los informes no se pueden comparar
```

Qué tienes que darle:

- **Dos informes** con el formato de `docs/CONTRACTS/eval-report.schema.json`. Cada métrica apunta con
  `raw_path` a un fichero con su valor por caso (`[{"case_id": "...", "value": 1.0}, ...]`). Los dos
  informes tienen que traer los mismos casos: la comparación es pareada y, si no coinciden, se niega.
- **`gate.yaml`**: qué métricas bloquean y en qué sentido.
  ```yaml
  metrics:
    - { id: answer_correct, blocking: true }
    - { id: tasa_de_error, blocking: true, higher_is_better: false }
    - { id: longitud, blocking: false }
  ```
- **`--goals`**: un YAML con el bloque `comparacion` (réplicas, semilla, nivel de confianza, corrección). El
  de este repositorio está en `docs/GOALS.yaml` y es el valor por defecto.

Para verlo bloquear sin escribir nada, con los informes de ejemplo del repositorio:

```bash
uv run evalgate eval compare evals/suites/compare-fixture/base.json \
  evals/suites/compare-fixture/head-regresion.json \
  --gate evals/suites/compare-fixture/gate.yaml --out /tmp/resultado.json
```

**Lo que hay que saber antes de fiarse de ella:** medida a temperatura 0,7 y comparando una ejecución contra
otra, esta puerta bloquea de más y no distingue caídas pequeñas. Los números exactos están en
[La puerta, medida](#la-puerta-medida-meta-evaluación). Con salidas deterministas o grabadas ese ruido no
existe.

### 3. El motor de evaluación

`evalgate eval run --suite <nombre>` puntúa una suite y escribe el informe que la puerta consume. Hoy las
métricas son las de un sistema RAG y la suite tiene la forma de `evals/suites/rag-app/` (casos, salidas
grabadas del sistema, veredictos grabados del juez). Para otro tipo de sistema, lo directo es generar tú
los informes en el formato del contrato y usar solo la puerta.

### Probar el ejemplo incluido

```bash
make up                                   # proxy en http://127.0.0.1:8080/v1; Ollama en el host
python examples/rag-app/generate_corpus.py
OPENAI_BASE_URL=http://127.0.0.1:8080/v1 python examples/rag-app/rag_app.py --limit 3
make down
make eval                                 # la suite de ejemplo desde lo grabado: no llama a ningún modelo
uv run evalgate eval self-gate            # este repositorio pasando por su propia puerta
```

`examples/rag-app` es un cliente de verdad: no importa nada de `src/evalgate/` y solo usa la biblioteca
estándar. Que la adopción cueste una variable de entorno es una meta medida (`G-ADOPTION`: cero líneas de
diferencia entre la salida con proxy y sin él), no una frase del README.

## Frente a Langfuse y otras plataformas

Evalgate no es una plataforma de observabilidad: no tiene interfaz, ni anotación, ni usuarios. Hace una cosa
que esas plataformas no dan hecha: una puerta de CI que publica sus propias tasas de error, y la contabilidad
de tokens y coste que la alimenta. Si ya usas una plataforma, la puerta se puede usar sola, con informes
generados desde donde quieras. El razonamiento está en `docs/adr/004-evalgate-frente-a-langfuse.md`.

## Reglas de diseño

Son reglas de `docs/RULES.md`, cada una con un comprobador en `scripts/rules/` o un test que corre en el
gate:

- **Ninguna traza puede tumbar ni ralentizar una petición.** El proxy no importa exportadores ni espera a
  un export: cola acotada que, al llenarse, descarta y lo cuenta (R1, `no_blocking_export.py`).
- **La contabilidad se cierra siempre.** El registro de uso se emite en `finally` y sobrevive a la
  cancelación: cliente cortado = tokens pagados = tokens contados (R2, `finally_on_generators.py`,
  `docs/adr/010-contabilidad-ante-desconexion.md`). Dirigido por un corpus de transcripts SSE con los casos
  límite, en `tests/fixtures/sse/`.
- **Ningún nombre `gen_ai.*` escrito a mano.** El modelo de datos interno es propio; los nombres externos se
  generan desde la versión fijada en `otel-semconv.lock` (R5, `no_genai_literals.py`,
  `docs/adr/005-modelo-otel-interno-con-traduccion.md`).
- **El ejemplo es un cliente**: `examples/rag-app` no importa nada del paquete (R13, `example_is_client.py`).

Las siguientes se escribieron antes que el código, para que el código no pudiera negociarlas:

- **Ningún precio vive en el código** y una tabla de precios publicada es inmutable: corregir un precio es
  publicar una tabla nueva con fecha posterior (R3, R4).
- **La puerta no contiene un solo umbral literal**: todo parámetro de decisión llega de `docs/GOALS.yaml` (R7).
- **El bootstrap es pareado o falla**, y con varias métricas bloqueantes la corrección es Holm: informes con
  conjuntos de casos distintos lanzan excepción, nunca degradan en silencio (R8).
- **Ninguna métrica llama a un LLM** y **el juez nunca es el modelo que genera** (R11, R12).

## Números medidos

Generados por `make report` desde `evals/reports/`. Ninguno se escribe a mano (regla R17).
Hardware de referencia: MacBook Pro M4 Max, 36 GB de memoria unificada.

<!-- evalgate:numbers:start -->
| Fase | Meta | Valor | Cerrada | Artefacto |
|---|---|---|---|---|
| F1 | `G-ADOPTION` | lineas_de_diff=0, n_lineas=8 | 2026-09-12 | `evals/reports/gate-F1.json` |
| F1 | `G-FUNC-COV` | 0 | 2026-09-12 | `evals/reports/gate-F1.json` |
| F1 | `G-LINE-COV` | 100,00 | 2026-09-12 | `evals/reports/gate-F1.json` |
| F1 | `G-OPENAI-CONTRACT` | ratio=1,00, n=5 | 2026-09-12 | `evals/reports/gate-F1.json` |
| F2 | `G-ADOPTION` | lineas_de_diff=0, n_lineas=8 | 2026-09-20 | `evals/reports/gate-F2.json` |
| F2 | `G-DISCONNECT` | ratio=1, n=222 | 2026-09-20 | `evals/reports/gate-F2.json` |
| F2 | `G-FUNC-COV` | 0 | 2026-09-20 | `evals/reports/gate-F2.json` |
| F2 | `G-LINE-COV` | 98,70 | 2026-09-20 | `evals/reports/gate-F2.json` |
| F2 | `G-OPENAI-CONTRACT` | ratio=1,00, n=7 | 2026-09-20 | `evals/reports/gate-F2.json` |
| F2 | `G-TOKENS-EXACT` | ratio=1, n=5 | 2026-09-20 | `evals/reports/gate-F2.json` |
| F2 | `G-TOKENS-STREAM` | delta_con_usage=0 | 2026-09-20 | `evals/reports/gate-F2.json` |
| F3 | `G-ADOPTION` | lineas_de_diff=0, n_lineas=8 | 2026-10-06 | `evals/reports/gate-F3.json` |
| F3 | `G-DISCONNECT` | ratio=1, n=198 | 2026-10-06 | `evals/reports/gate-F3.json` |
| F3 | `G-FUNC-COV` | 0 | 2026-10-06 | `evals/reports/gate-F3.json` |
| F3 | `G-LAT-PROXY` | 5,29 | 2026-10-06 | `evals/reports/gate-F3.json` |
| F3 | `G-LAT-TTFT` | 3,51 | 2026-10-06 | `evals/reports/gate-F3.json` |
| F3 | `G-LINE-COV` | 99,34 | 2026-10-06 | `evals/reports/gate-F3.json` |
| F3 | `G-OPENAI-CONTRACT` | ratio=1,00, n=7 | 2026-10-06 | `evals/reports/gate-F3.json` |
| F3 | `G-OTEL-CONTRACT` | ratio=1, n=25 | 2026-10-06 | `evals/reports/gate-F3.json` |
| F3 | `G-TOKENS-EXACT` | ratio=1, n=5 | 2026-10-06 | `evals/reports/gate-F3.json` |
| F3 | `G-TOKENS-STREAM` | delta_con_usage=0 | 2026-10-06 | `evals/reports/gate-F3.json` |
| F3 | `G-TRACE-0` | perdidos=0, rps=50, servidas=6000 | 2026-10-06 | `evals/reports/gate-F3.json` |
| F3 | `G-TRACE-DEGRADE` | -0,08 | 2026-10-06 | `evals/reports/gate-F3.json` |
| F4 | `G-ADOPTION` | lineas_de_diff=0, n_lineas=8 | 2026-10-08 | `evals/reports/gate-F4.json` |
| F4 | `G-DISCONNECT` | ratio=1, n=209 | 2026-10-08 | `evals/reports/gate-F4.json` |
| F4 | `G-FUNC-COV` | 0 | 2026-10-08 | `evals/reports/gate-F4.json` |
| F4 | `G-LAT-PROXY` | 5,46 | 2026-10-08 | `evals/reports/gate-F4.json` |
| F4 | `G-LAT-TTFT` | 3,45 | 2026-10-08 | `evals/reports/gate-F4.json` |
| F4 | `G-LINE-COV` | 99,35 | 2026-10-08 | `evals/reports/gate-F4.json` |
| F4 | `G-MUTATION` | 88,58 | 2026-10-08 | `evals/reports/gate-F4.json` |
| F4 | `G-OPENAI-CONTRACT` | ratio=1,00, n=7 | 2026-10-08 | `evals/reports/gate-F4.json` |
| F4 | `G-OTEL-CONTRACT` | ratio=1, n=25 | 2026-10-08 | `evals/reports/gate-F4.json` |
| F4 | `G-PRICE-REPRO` | 0,00 | 2026-10-08 | `evals/reports/gate-F4.json` |
| F4 | `G-TOKENS-EXACT` | ratio=1, n=5 | 2026-10-08 | `evals/reports/gate-F4.json` |
| F4 | `G-TOKENS-STREAM` | delta_con_usage=0 | 2026-10-08 | `evals/reports/gate-F4.json` |
| F4 | `G-TRACE-0` | perdidos=0, rps=50, servidas=6000 | 2026-10-08 | `evals/reports/gate-F4.json` |
| F4 | `G-TRACE-DEGRADE` | -0,17 | 2026-10-08 | `evals/reports/gate-F4.json` |
| F5 | `G-ADOPTION` | lineas_de_diff=0, n_lineas=8 | 2026-10-08 | `evals/reports/gate-F5.json` |
| F5 | `G-CACHE-HIT` | 0,00 | 2026-10-08 | `evals/reports/gate-F5.json` |
| F5 | `G-CACHE-INVAL` | ratio=1, n=63 | 2026-10-08 | `evals/reports/gate-F5.json` |
| F5 | `G-DISCONNECT` | ratio=1, n=212 | 2026-10-08 | `evals/reports/gate-F5.json` |
| F5 | `G-FUNC-COV` | 0 | 2026-10-08 | `evals/reports/gate-F5.json` |
| F5 | `G-LAT-PROXY` | 6,63 | 2026-10-08 | `evals/reports/gate-F5.json` |
| F5 | `G-LAT-TTFT` | 3,96 | 2026-10-08 | `evals/reports/gate-F5.json` |
| F5 | `G-LINE-COV` | 99,35 | 2026-10-08 | `evals/reports/gate-F5.json` |
| F5 | `G-MUTATION` | 88,58 | 2026-10-08 | `evals/reports/gate-F5.json` |
| F5 | `G-OPENAI-CONTRACT` | ratio=1,00, n=7 | 2026-10-08 | `evals/reports/gate-F5.json` |
| F5 | `G-OTEL-CONTRACT` | ratio=1, n=25 | 2026-10-08 | `evals/reports/gate-F5.json` |
| F5 | `G-PRICE-REPRO` | 0,00 | 2026-10-08 | `evals/reports/gate-F5.json` |
| F5 | `G-TOKENS-EXACT` | ratio=1, n=5 | 2026-10-08 | `evals/reports/gate-F5.json` |
| F5 | `G-TOKENS-STREAM` | delta_con_usage=0 | 2026-10-08 | `evals/reports/gate-F5.json` |
| F5 | `G-TRACE-0` | perdidos=0, rps=50, servidas=6000 | 2026-10-08 | `evals/reports/gate-F5.json` |
| F5 | `G-TRACE-DEGRADE` | -0,20 | 2026-10-08 | `evals/reports/gate-F5.json` |
| F6 | `G-ADOPTION` | lineas_de_diff=0, n_lineas=8 | 2026-10-08 | `evals/reports/gate-F6.json` |
| F6 | `G-CACHE-HIT` | 0,00 | 2026-10-08 | `evals/reports/gate-F6.json` |
| F6 | `G-CACHE-INVAL` | ratio=1, n=63 | 2026-10-08 | `evals/reports/gate-F6.json` |
| F6 | `G-DETERMINISM` | ratio=1, n=3 | 2026-10-08 | `evals/reports/gate-F6.json` |
| F6 | `G-DISCONNECT` | ratio=1, n=217 | 2026-10-08 | `evals/reports/gate-F6.json` |
| F6 | `G-FUNC-COV` | 0 | 2026-10-08 | `evals/reports/gate-F6.json` |
| F6 | `G-LAT-PROXY` | 6,97 | 2026-10-08 | `evals/reports/gate-F6.json` |
| F6 | `G-LAT-TTFT` | 3,80 | 2026-10-08 | `evals/reports/gate-F6.json` |
| F6 | `G-LINE-COV` | 99,35 | 2026-10-08 | `evals/reports/gate-F6.json` |
| F6 | `G-MUTATION` | 88,58 | 2026-10-08 | `evals/reports/gate-F6.json` |
| F6 | `G-OPENAI-CONTRACT` | ratio=1,00, n=7 | 2026-10-08 | `evals/reports/gate-F6.json` |
| F6 | `G-OTEL-CONTRACT` | ratio=1, n=25 | 2026-10-08 | `evals/reports/gate-F6.json` |
| F6 | `G-PRICE-REPRO` | 0,00 | 2026-10-08 | `evals/reports/gate-F6.json` |
| F6 | `G-TOKENS-EXACT` | ratio=1, n=5 | 2026-10-08 | `evals/reports/gate-F6.json` |
| F6 | `G-TOKENS-STREAM` | delta_con_usage=0 | 2026-10-08 | `evals/reports/gate-F6.json` |
| F6 | `G-TRACE-0` | perdidos=0, rps=50, servidas=6000 | 2026-10-08 | `evals/reports/gate-F6.json` |
| F6 | `G-TRACE-DEGRADE` | 0,08 | 2026-10-08 | `evals/reports/gate-F6.json` |
<!-- evalgate:numbers:end -->

Qué significa cada meta, su umbral y el comando que la mide: `docs/GOALS.yaml`.

### La puerta, medida (meta-evaluación)

Un evaluador no evaluado es un adorno, así que estos son los números de la propia puerta, salgan como
salgan. Generados por `make report` desde `evals/reports/meta-eval.json`; `evalgate meta report --check` los
vuelve a calcular desde las 150 etiquetas humanas y desde la matriz de 250 ejecuciones, sin llamar a ningún
modelo.

La matriz se midió dos veces. La primera, con los 60 casos de calibración y el juez en vivo, dio un efecto
mínimo de 15 puntos. La segunda repite el mismo plan sobre los 200 casos y sin juez (su métrica ya no
bloquea: kappa bajo el umbral). Antes de ejecutarla quedó escrito que sus tres números sustituirían a los de
la primera salieran como salieran; son los de la tabla. La primera queda debajo, sin tocar.

<!-- evalgate:meta:start -->
| Meta | Medido | Umbral | ¿Cumple? | Detalle |
|---|---|---|---|---|
| `G-JUDGE-KAPPA` | 0,47 | >= 0,60 | **no** | IC95 [0,27, 0,65] · 150 etiquetas humanas · acuerdo bruto 0,86 |
| `G-GATE-FP` | 0,102 | <= 0,05 | **no** | Wilson 95 % [0,044, 0,218] · 5 bloqueos en 49 decisiones contra `base-00` |
| `G-GATE-MDE` | 10,50 | <= 8,00 | **no** | puntos porcentuales, en `answer_correct` · 200 casos · 2450 pares de 50 ejecuciones |
| `G-GATE-POWER` | 1,00 | >= 0,90 | sí | mínimo sobre las degradaciones de tamaño ≥ 15,75 pp · mínimo sobre las 4: 0,02 |

Métricas que bloquean: `answer_correct`, `context_recall`, `abstencion_incorrecta`. Ruido: sistema bajo prueba con RAG_TEMPERATURE=0.7 y semilla distinta por ejecución (RAG_SEED = 1000 + nº de ejecución); sin juez: sus métricas no se miden.

| Degradación | Potencia | Bloqueos | Tamaño medido | ¿Se le exige? |
|---|---|---|---|---|
| `contexto-50` | 1,00 | 50/50 | 36,3 pp en `abstencion_incorrecta` | sí |
| `docs-aleatorios-20` | 1,00 | 50/50 | 23,6 pp en `abstencion_incorrecta` | sí |
| `modelo-pequeno` | 0,02 | 1/50 | 0,8 pp en `answer_correct` | no: por debajo del tamaño exigido |
| `temperatura-1.2` | 0,28 | 14/50 | 4,8 pp en `answer_correct` | no: por debajo del tamaño exigido |

**Medida anterior, publicada tal cual** · 60 casos · `evals/reports/meta-eval-60.json`

| Meta | Medido | Umbral | ¿Cumple? | Detalle |
|---|---|---|---|---|
| `G-GATE-FP` | 0,122 | <= 0,05 | **no** | Wilson 95 % [0,057, 0,242] · 6 bloqueos en 49 decisiones contra `base-00` |
| `G-GATE-MDE` | 15,00 | <= 8,00 | **no** | puntos porcentuales, en `answer_correct` · 60 casos · 2450 pares de 50 ejecuciones |
| `G-GATE-POWER` | 1,00 | >= 0,90 | sí | mínimo sobre las degradaciones de tamaño ≥ 22,50 pp · mínimo sobre las 4: 0,00 |

Métricas que bloquean: `answer_correct`, `context_recall`, `abstencion_incorrecta`. Ruido: sistema bajo prueba con RAG_TEMPERATURE=0.7 y semilla distinta por ejecución (RAG_SEED = 1000 + nº de ejecución); juez llamado en vivo en cada caso, sin caché.

| Degradación | Potencia | Bloqueos | Tamaño medido | ¿Se le exige? |
|---|---|---|---|---|
| `contexto-50` | 1,00 | 50/50 | 31,4 pp en `abstencion_incorrecta` | sí |
| `docs-aleatorios-20` | 1,00 | 50/50 | 24,9 pp en `abstencion_incorrecta` | sí |
| `modelo-pequeno` | 0,00 | 0/50 | 3,7 pp en `answer_correct` | no: por debajo del tamaño exigido |
| `temperatura-1.2` | 0,20 | 10/50 | 4,0 pp en `answer_correct` | no: por debajo del tamaño exigido |
<!-- evalgate:meta:end -->

## Mapa del repositorio

| Ruta | Qué hay |
|---|---|
| `src/evalgate/proxy/` | Proxy: `streaming.py` (contabilidad del flujo, determinista dado un transcript), `translate.py`, `app.py` (montaje) |
| `src/evalgate/pricing/` | Modelo y búsqueda de tablas de precios fechadas |
| `src/evalgate/telemetry/` | Modelo interno de la llamada, traducción a OTel, cola acotada, filas y migraciones de ClickHouse; `semconv/` es generado |
| `src/evalgate/cli/` | CLI `evalgate` (`serve`, `migrate`, `eval`, `cache`, `meta`) |
| `src/evalgate/evals/`, `gate/`, `stats/` | Métricas, jueces con caché, la decisión de la puerta y la estadística (bootstrap pareado, Holm, Wilson) |
| `examples/rag-app/` | Aplicación RAG mínima que hace de cliente, demo y e2e |
| `tests/` | `unit`, `property` (Hypothesis), `contract`, `integration` (ClickHouse con testcontainers), `e2e`, y `fixtures/` con el corpus SSE y respuestas grabadas |
| `evals/reports/` | Informes de los que sale cada número de este README |
| `scripts/` | El gate (`done.py`), los comprobadores de reglas (`rules/`), el bench y el generador de semconv |
| `docs/` | Metas, reglas, contratos y ADR |

## Desarrollo

```bash
make help          # todos los targets
make lint          # ruff check + ruff format --check
make typecheck     # mypy --strict sobre las rutas testeables
make test-fast     # unitarios + propiedad (perfil dev) + contrato
make test-int      # integración contra ClickHouse; necesita Docker
make test-e2e      # e2e contra el proxy y Ollama
```

Los targets de fases futuras fallan diciendo en qué fase llegan: un target que "pasa" sin hacer nada sería
un gate falso.

`make gate-fast`, `make gate-full` y `make done` son el gate con el que se cierra cada fase. Leen estado
local de trabajo que no se publica (ver abajo), así que fuera de la máquina de desarrollo no son
reproducibles tal cual; los tests y los comprobadores de `scripts/rules/` sí lo son.

## Procedencia de los datos

El corpus de `examples/rag-app` es **sintético por construcción**: fichas de productos ficticios generadas
con semilla fija, con la respuesta correcta conocida desde su generación. No mide calidad de dominio: mide si
la puerta detecta degradaciones. Coste real incurrido: 0 € (solo modelos locales); el coste que se publique
será siempre "coste declarado" con una tabla de precios pública y fechada.

## Cómo se ha construido

`docs/GOALS.yaml` (metas con umbral y comando), `docs/RULES.md` (reglas R1-R20), `docs/adr/` (decisiones)
y `CHANGELOG.md`.

La suite reservada (`tests/holdout/`) no está en este repositorio, a propósito: es privada para que el código
no se pueda ajustar contra ella.
