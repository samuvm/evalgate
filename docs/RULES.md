# Evalgate · reglas específicas del proyecto

> Donde esta hoja y `docs/CONTRACTS/**` difieran, **gana el contrato**: está fijado por sha256 y no se
> improvisa. Los desvíos declarados respecto a los contratos están en ADR-006.

---

## 1. Invariantes verificables

Cada una con su verificación mecánica. Las que empiezan por `scripts/rules/` viven ahí y las llama
`make gate-fast`. Una invariante sin comando no es una invariante, es una intención.

| # | Regla | Verificación | Desde |
|---|---|---|---|
| **R1** | **Ninguna traza puede tumbar ni ralentizar una petición.** La ruta de petición nunca espera al exportador. La cola es acotada; al llenarse descarta y suma el contador de spans descartados | `scripts/rules/no_blocking_export.py` (AST: ningún módulo de `proxy/` importa `telemetry/exporters/` ni hace `await` sobre `export()`) + `make test-int -k degradation` | F3 |
| **R2** | **La contabilidad se cierra siempre.** Toda corrutina generadora de `proxy/streaming.py` tiene un bloque `finally` que emite el registro de uso, y sobrevive a `asyncio.CancelledError` | `scripts/rules/finally_on_generators.py` (AST) + Hypothesis inyectando corte en cada índice `k` | F2 |
| **R3** | **Ningún precio vive en el código.** Los precios están en `pricing/<YYYY-MM-DD>.yaml` con el formato del contrato | `scripts/rules/no_price_literals.py` (AST: ningún literal `float`/`Decimal` en `src/evalgate/pricing/*.py` fuera de constantes de test) | F4 |
| **R4** | **Una tabla de precios publicada es inmutable.** Corregir un precio = crear un fichero nuevo con `effective_from` posterior, nunca editar el existente | `scripts/rules/tables_lock.py` compara el sha256 de cada fichero contra `pricing/TABLES.lock` | F4 |
| **R5** | **Ningún nombre `gen_ai.*` aparece literalmente en el código** fuera de la capa de traducción | `grep -rn '"gen_ai\.' src/ --include='*.py' \| grep -v 'telemetry/semconv/'` debe estar vacío | F3 |
| **R6** | **El proxy no persiste contenido de prompts por defecto.** Solo `app.prompt.sha256` y longitud. La captura de contenido es opt-in y pasa por redactor | `pytest tests/contract/test_no_prompt_leak.py`: envía una cadena canario y verifica que no aparece en ningún span exportado | F3 |
| **R7** | **La puerta no contiene un solo umbral literal.** Todo parámetro de decisión llega de `GOALS.yaml` | `scripts/rules/no_magic_thresholds.py` (AST sobre `gate/decision.py`) | F6 |
| **R8** | **El bootstrap es pareado o falla, y la corrección múltiple es Holm.** No existe función de bootstrap no pareado en el repositorio; dos informes con conjuntos de `case_id` distintos **lanzan excepción**, nunca degradan en silencio. Con más de 3 métricas bloqueantes vigiladas, todo informe emitido escribe **literalmente `"holm"`** en `comparison.multiple_comparison_correction` | `pytest tests/unit/stats/test_paired_only.py` + `scripts/rules/no_unpaired_bootstrap.py` + `pytest tests/contract/test_report_schema.py -k multiple_comparison` (valor literal `holm` y coincidencia con `comparacion.correccion_multiple` de `GOALS.yaml`) | F6 |
| **R9** | **La puerta es antisimétrica y `compare(a, a)` no bloquea nunca** | `tests/property/test_gate_algebra.py` (Hypothesis) | F6 |
| **R10** | **La clave de caché de jueces incluye siempre**: id del juez, modelo, parámetros de muestreo, versión del prompt, sha256 del prompt y sha256 del texto evaluado. Cambiar cualquiera cambia la clave; no cambiar nada la conserva | `tests/unit/judges/test_cache_key.py` (property: permutación de cada componente) | F5 |
| **R11** | **Ninguna métrica llama a un LLM.** Todo juicio pasa por `evals/judges/` con caché | `scripts/rules/metrics_are_pure.py` (AST: ningún módulo de `evals/metrics/` importa `httpx`, `litellm`, `providers` ni `judges`; se admite un callable ya cacheado inyectado) | F5 |
| **R12** | **El juez nunca es el mismo modelo que genera.** Un modelo juzgando su propia salida infla `faithfulness` sistemáticamente | Validación de esquema en la configuración de suite + `tests/unit/evals/test_suite_config.py` | F5 |
| **R13** | **`examples/rag-app` no importa nada de `src/evalgate/`.** Es un cliente: la adopción cuesta una variable de entorno, y eso solo es cierto si no hay import | `scripts/rules/example_is_client.py` (AST) + `G-ADOPTION` | F1 |
| **R14** | **Ningún informe se escribe sin `{id, version, sha256}` de cada prompt usado.** Sin eso no se puede correlacionar un cambio de métrica con un cambio de prompt, que es medio proyecto | `required` en `docs/CONTRACTS/eval-report.schema.json` + `pytest tests/contract/test_report_schema.py` | F5 |
| **R15** | **Cero red en `tests/unit` y `tests/property`** | `pytest-socket --disable-socket` activado por `conftest.py` en esos dos directorios | F0 |
| **R16** | **La puerta se autoexcluye hasta F9.** `EVALGATE_SELF_GATE=off` es válido mientras la fase activa sea < 9; **en F9 se retira**, y a partir de ahí `off` no se admite: el repositorio pasa por su propia puerta | `scripts/rules/self_gate.py` lee la fase activa de `.gate/STATE.md`; falla con `off` en fase >= 9, y con `on` ejecuta `evalgate eval self-gate` y falla si la puerta bloquea | F0 |
| **R17** | **Todo número del README sale de un fichero de `evals/reports/`.** Ninguno se escribe a mano | `make report` regenera las tablas; `scripts/rules/readme_numbers.py` falla si el README difiere de lo regenerado | F1 |
| **R18** | **Toda dependencia con `==` y hash.** `uv --require-hashes`, `pip-audit` en el gate, imágenes Docker por digest. Un rango de versiones no es un pin: cada dependencia se fija en un `==` concreto | `scripts/rules/pins.py` + `pip-audit` en `gate-full` | F0 |
| **R19** | **`[tool.gate].cobertura_linea_min` y `.mutantes_muertos_min` coinciden con `G-LINE-COV` y `G-MUTATION`, en la misma unidad** (`porcentaje`: 90 y 75). Un cambio en `pyproject.toml` no puede bajar el umbral sin tocar `GOALS.yaml` | `scripts/check_gate_config.py`, en `gate-fast`. Ver §4.1 | F1 |
| **R20** | **`docs/CONTRACTS/` está fijado por sha256** (`docs/spec/contracts.sha256`). Cambiar un contrato es un evento versionado, con entrada en `CHANGELOG.md`. Lo propio del proyecto vive en `docs/spec/`, que sí se escribe. Ver §7 | `pytest tests/contract/test_contracts_are_verbatim_copies.py` (sha256 fichero a fichero contra `docs/spec/contracts.sha256`) | F0 |

**Por qué R16 existe, y por qué el número es 9:** el repo se usa a sí mismo como puerta de calidad, y eso es un
bucle. Una puerta rota bloquea el trabajo sobre la puerta. La escotilla es explícita, está acotada y su
retirada es un **entregable de F9** (`docs/ROADMAP.md`, fila F9: `EVALGATE_SELF_GATE=on`). Por eso la
verificación falla desde la fase 9 y no antes: marcar rojo en F7 y F8 sería exigir algo que la hoja de ruta
todavía no pedía, y el resultado previsible es que alguien desactive el script en lugar de arreglar nada.

---

## 2. Qué se testea y qué se mide

La distinción no es de estilo. Un test es binario y determinista; una evaluación produce una distribución y
se compara estadísticamente. Confundirlos produce tests intermitentes que se acaban desactivando, o la
ilusión de calidad.

| Módulo | Naturaleza | Régimen |
|---|---|---|
| `pricing/` | Determinista puro | **TDD obligatorio.** Cobertura ≥ 90 %, mutación ≥ 75 %, **propiedades obligatorias** |
| `accounting/` | Determinista puro | **TDD obligatorio.** Ídem |
| `stats/` | Determinista puro | **TDD obligatorio** + validación contra resultados analíticos conocidos + propiedades obligatorias |
| `gate/decision.py` | Determinista puro | **TDD estricto, el más estricto del repo.** Es donde un error bloquea cambios buenos o deja pasar malos |
| `proxy/streaming.py` | Determinista dado un transcript | **TDD obligatorio, dirigido por corpus** (§4.2 punto 3) |
| `proxy/translate.py` | Determinista | Testeable. TDD **no** obligatorio |
| `telemetry/semconv/` | Generado desde el `.lock` | **No se escribe a mano: se genera.** Tests de contrato sobre la traducción |
| `evals/metrics/` | Determinista (funciones puras) | Testeable, cobertura ≥ 90 % |
| `evals/cache/` | Determinista | Testeable + propiedades sobre la clave |
| `drift/detectors/` | Determinista (estadística) | Testeable + calibración propia |
| `proxy/app.py` | I/O y montaje | **Excluido de unitarios.** Se cubre por contrato y e2e |
| `providers/` | Adaptadores | **Excluido de unitarios.** Tests de **contrato** contra el esquema del proveedor |
| `evals/judges/` (llamadas) | **No determinista** | **TDD PROHIBIDO. No se testea: se mide** (kappa, F7). Lo que sí se testea es su caché |
| `prompts/` | Texto | **TDD PROHIBIDO.** Se versionan y se miden. Un test que asserta el string exacto de un prompt es el test frágil que se desactiva en dos semanas |
| `dashboards/` | Generado por el SDK | **TDD PROHIBIDO.** Snapshot del JSON generado, nada más |
| `examples/rag-app` | Demostración | Solo e2e |

**Dónde TDD es obligatorio:** los cinco paquetes de `[tool.gate].tdd_obligatorio`. El ciclo rojo→verde —el
test se ve fallar antes de que exista el código— es el mecanismo, no el orden de las líneas del fichero.

**Dónde TDD está prohibido:** `evals/judges/` (llamadas), `prompts/`, `dashboards/` y `examples/`. Forzar TDD
sobre un prompt es teatro: produce un test que solo dice que el fichero no ha cambiado, se rompe cada vez que
se mejora el prompt, y se acaba borrando. Lo que se hace con un prompt es versionarlo (frontmatter, que
comprueba `scripts/rules/prompts_frontmatter.py`), registrarlo en el informe (R14) y medir su efecto.

---

## 3. Errores típicos de este dominio

Salieron todos en la investigación previa. Están aquí para no repetirlos, no como advertencia genérica.

1. **Asumir que las convenciones `gen_ai.*` son estables.** No lo son: todo el namespace está en estado
   *Development* y se movió a otro repositorio. Ya han ocurrido rupturas (`gen_ai.system` →
   `gen_ai.provider.name`; `prompt_tokens`/`completion_tokens` → `input_tokens`/`output_tokens`). De ahí R5 y
   el modelo interno propio. **Toda consulta analítica sobre trazas históricas hace `coalesce()` de ambas
   generaciones**, o los paneles se vacían al cruzar una frontera de versión.
2. **Usar el proxy de LiteLLM en vez de su librería.** Si el proxy es de LiteLLM, el mérito del proyecto
   —streaming y contabilidad— desaparece y el repositorio es un fichero de configuración. Además LiteLLM
   sufrió un ataque de cadena de suministro confirmado en marzo de 2026 (versiones 1.82.7 y 1.82.8 en PyPI,
   robo de credenciales): de ahí R18. Y su proxy trae telemetría propia que colisionaría con la nuestra.
3. **Servir un endpoint de entrada compatible con Bedrock.** Implica verificar SigV4 y emitir
   `application/vnd.amazon.eventstream` (framing binario, no SSE JSON): 20-40 h no presupuestadas con retorno
   narrativo casi nulo frente al endpoint OpenAI. **Bedrock solo como proveedor de salida.**
4. **Ejecutar el experimento de falsos positivos en vivo.** 50 ejecuciones × 200 casos = 10.000 generaciones
   locales. Es inviable como paso de gate. El diseño correcto está en §5: una matriz precomputada una vez por
   fase, y todas las metas de meta-evaluación recalculadas offline desde ella en menos de un segundo.
5. **Medir la sobrecarga del proxy contra un proveedor real.** Mide la varianza de la red, no el proxy. Stub
   local determinista en loopback, protocolo en `docs/bench/protocol.md`, hardware declarado.
6. **Publicar un punto sin intervalo.** Con n=20 y un bloqueo, el IC95 es aproximadamente [1 %, 24 %]. Toda
   proporción sobre n pequeño va con intervalo de Wilson, no normal.
7. **Bootstrap no pareado.** Sobre proporciones de p≈0,85 con n=200 da semianchura ±4,9 pp; pareado detecta
   cambios mucho menores con el mismo n. R8 lo hace imposible de escribir por accidente.
8. **Olvidar la corrección por comparaciones múltiples.** Con más de 3 métricas bloqueantes vigiladas,
   **Holm-Bonferroni**, que es el valor por defecto del contrato (`docs/CONTRACTS/retrieval-metrics.md` §4).
   Sin ella, la tasa de falsos positivos de la puerta sube sola con cada métrica nueva. **El motivo, que hay
   que saber decir en una entrevista:** Holm controla la **tasa de error por familia** —la probabilidad de
   bloquear al menos una vez sin causa—, que es exactamente lo que arruina una puerta de calidad, porque un
   falso bloqueo cuesta una tarde y erosiona la confianza hasta que alguien desactiva la puerta; y es
   **uniformemente más potente que Bonferroni** sin exigir supuestos adicionales, así que preferir Bonferroni
   no tiene ventaja. Benjamini-Hochberg controla la tasa de **falsos descubrimientos** y es correcto en un
   panel de diagnóstico, donde un falso positivo aislado no bloquea nada: ahí sí, en la puerta no. El informe
   lo escribe literalmente como `holm` (R8), igual que `comparacion.correccion_multiple` de `GOALS.yaml`.
9. **Meter Ollama en `compose.yaml`.** Docker en macOS no pasa la GPU. Ollama va en el host y se accede por
   `host.docker.internal`. Es el error que destruye la latencia y nadie entiende por qué.
10. **Levantar testcontainers en el gate rápido.** Cuestan entre 10 y 40 s y en macOS son el punto de fricción
    número uno (Ryuk, `DOCKER_HOST`, sockets). Nivel 2 solo en `make done`.
11. **Usar Ragas.** Congelado desde febrero de 2026 (último commit en `main`: 24-feb-2026). El riesgo es de
    credibilidad, no técnico. Fuera del gate, sin excepción.
12. **Usar OpenInference.** Usa convenciones propias, no `gen_ai.*`: elegirlo contradice la tesis del
    proyecto. OpenLLMetry o SDK OTel puro.
13. **Basar el panel de coste en el exportador de métricas del collector.** En `clickhouseexporter`, traces y
    logs están en beta y **metrics en alpha**. El coste se deriva de spans. `create_schema: false`: el esquema
    lo gestionamos nosotros con migraciones versionadas.
14. **Que el juez sea el mismo modelo que genera.** Infla `faithfulness` sistemáticamente. R12.
15. **Inventar un exportador Iceberg.** Sin S3 donde probarlo ni un lector real, sería un hito no
    presupuestado. Degradado a `evalgate export parquet` (Parquet plano, F10, ampliación; ADR-020).

---

## 4. "Un test unitario por función", hecho ejecutable aquí

### 4.1 Bloque `[tool.gate]` de `pyproject.toml`, literal

```toml
[tool.gate]
testable = [
  "src/evalgate/pricing",
  "src/evalgate/accounting",
  "src/evalgate/proxy/streaming.py",
  "src/evalgate/proxy/translate.py",
  "src/evalgate/telemetry/semconv",
   "src/evalgate/telemetry/model.py",
  "src/evalgate/telemetry/translate.py",
  "src/evalgate/telemetry/processor.py",
  "src/evalgate/telemetry/rows.py",
  "src/evalgate/telemetry/migrations.py",
  "src/evalgate/telemetry/pipeline.py",
  "src/evalgate/evals/metrics",
  "src/evalgate/evals/cache",
  "src/evalgate/gate",
  "src/evalgate/stats",
  "src/evalgate/drift/detectors",
]
tdd_obligatorio = [
  "src/evalgate/gate",
  "src/evalgate/stats",
  "src/evalgate/pricing",
  "src/evalgate/accounting",
  "src/evalgate/proxy/streaming.py",
]
excluido = [
  "src/evalgate/proxy/app.py",
  "src/evalgate/providers",
  "src/evalgate/evals/judges/client.py",
  "src/evalgate/cli",
  "prompts",
  "dashboards",
  "examples",
]
cobertura_linea_min = 90
mutantes_muertos_min = 75
property_obligatorio = ["src/evalgate/pricing", "src/evalgate/stats"]
```

**Rutas de fichero, no solo paquetes:** `testable` y `tdd_obligatorio` aceptan **rutas de fichero**, no
solo paquetes. Motivo: `proxy/` en conjunto no es testeable unitariamente (es I/O asíncrono y estado de
conexión), pero `proxy/streaming.py` **sí lo es** dado un transcript grabado, y es el fichero más importante
del repositorio. Excluirlo por vivir en un paquete "de adaptador" sería exactamente el error que este
proyecto denuncia. `scripts/check_function_coverage.py` debe soportar ambas formas.

**R19, y la unidad de los dos números.** `pyproject.toml` **no** está sellado: un cambio en
`pyproject.toml` no puede bajar `cobertura_linea_min` o `mutantes_muertos_min` sin tocar `GOALS.yaml`, porque
los dos números están duplicados en `docs/GOALS.yaml` (`G-LINE-COV`, `G-MUTATION`), que sí está sellado por
`thresholds.lock`, y `scripts/check_gate_config.py` falla si difieren. **Manda el número de `GOALS.yaml`.** Los cuatro números están en **porcentaje** (90 y 75), nunca en ratio: `coverage.py` escribe
`totals.percent_covered` en escala 0-100 y `mutmut` reporta muertos sobre total en la misma escala, así que la
comparación es literal y no lleva conversión. Escribir 0.90 aquí y 90 allí es el fallo que hace que un check
cruzado marque rojo sin motivo —o, peor, verde sin motivo—; por eso `GOALS.yaml` declara `unidad` en cada
umbral (contrato `goals.schema.json`).

### 4.2 Qué significa exactamente

1. **Toda función pública** (sin `_` inicial) de un paquete o fichero de `testable` tiene **≥ 1 contexto de
   test** (`pytest --cov-context=test`).
2. **Toda función pública de `pricing/` y `stats/` necesita además ≥ 1 test de propiedad**, no solo de
   ejemplo. Motivo: son los dos sitios donde el test por ejemplo es demostradamente insuficiente —un cálculo
   de coste con tres casos de ejemplo pasa y sigue siendo incorrecto en el cambio de tarifa; un intervalo
   bootstrap con un caso pasa y tiene el sesgo invertido—. Verificación: segunda pasada de
   `check_function_coverage.py` sobre `tests/property/`, cruzando por nombre de función referenciada.
3. **`proxy/streaming.py` no se mide por función sino por corpus.** Su criterio es: **cada fichero de
   `tests/fixtures/sse/` tiene un test que lo consume**, y el conjunto cubre los 12 casos límite de
   `tests/fixtures/sse/CASES.yaml`. Verificación: `scripts/rules/sse_corpus_coverage.py` falla si hay un fixture sin test o un
   caso límite de la lista sin fixture.

---

## 5. La matriz de falsos positivos: el diseño que hace viable F7

Es el ADR más valioso del proyecto y la razón de que la meta-evaluación quepa en el presupuesto.

1. **Una vez por fase**, `evalgate meta run-matrix` ejecuta 50 × 60 = 3.000 generaciones y 3.000 juicios
   (≈ 4-7 h en la máquina de referencia, tarea nocturna) y persiste `evals/reports/fp-matrix.parquet` con
   `(run_id, case_id, metrica, valor)`.
2. A partir de ahí, **todas** las metas de meta-evaluación —falsos positivos, efecto mínimo detectable y
   potencia— se recalculan **offline en menos de un segundo** desde la matriz. Son deterministas, gratis, y
   entran en el gate sin coste.
3. **El efecto mínimo detectable no se estima con teoría:** es el percentil 95 empírico de la distribución de
   deltas pareados bajo H0, leído directamente de la matriz.
4. **Las degradaciones canónicas están fijadas y no son negociables:** (a) contexto recortado al 50 %;
   (b) modelo del sistema bajo prueba sustituido por uno más pequeño; (c) 20 % de los documentos recuperados
   sustituidos por documentos aleatorios; (d) temperatura del sistema bajo prueba a 1,2. La potencia se mide
   inyectándolas sobre la misma matriz.

---

## 6. Decisiones de alcance

Lo que queda dentro y fuera, y por qué. Cada fila es una decisión cerrada; reabrirla es un cambio de alcance
con su ADR.

| Decisión | Dentro / fuera | Por qué |
|---|---|---|
| **Servidor proxy propio** | El servidor es de evalgate. LiteLLM nunca como proxy; como librería, solo si llega un proveedor de salida no compatible con OpenAI (ADR-002) | Con el proxy de LiteLLM, streaming y contabilidad ante desconexión —el mérito del proyecto— serían ajenos, y su telemetría colisionaría con la nuestra |
| **Bedrock de entrada, retirado** | Endpoint de entrada solo compatible con OpenAI. Bedrock, como mucho, de salida (ADR-019) | SigV4 + `application/vnd.amazon.eventstream` (framing binario): 20-40 h sin retorno frente al endpoint OpenAI |
| **Métricas propias** | Funciones puras en `evals/metrics/`. DeepEval solo como contraste nocturno (F10). Ragas fuera | Ragas está congelado desde feb-2026; una métrica pura se testea y no llama a un LLM (R11) |
| **Precio: reproducción y conciliación, separadas** | `G-PRICE-REPRO` (aritmética, determinista, bloqueante) y `G-COST-RECONCILE` (conciliación contra factura, artefacto fresco bloqueante, delta publicado sea cual sea) | "Error ≤ 1 % contra la factura real" en una sola meta exige cuenta de pago y treinta días de tráfico; partida, la parte determinista corre en cada ejecución (`docs/CONTRACTS/pricing-table.md` §5) |
| **Falsos positivos de la puerta con n ≥ 49** | `G-GATE-FP` con n ≥ 49 y fuente de ruido declarada, más `G-GATE-MDE` y `G-GATE-POWER` | Con 20 ejecuciones el intervalo de Wilson de una tasa del 5 % es demasiado ancho para afirmar nada; y una puerta sin potencia medida solo mide la mitad |
| **Caché de jueces medida por dos metas** | `G-CACHE-HIT` (coste marginal ≤ 5 %) y `G-CACHE-INVAL` | Un "ahorro ≥ 70 %" no dice si la caché sirve veredictos viejos; invalidar bien importa tanto como acertar |
| **`mypy --strict` sobre `[tool.gate].testable`** | No sobre todo `src/` | Extenderlo a `providers/` y `cli/` es ruido con adaptadores de terceros sin tipos |
| **`make gate-full` es la CI** | `.github/workflows/gate.yml` escrito y no activado | La portabilidad a CI es de una línea; el gate completo necesita Docker y la suite reservada, que no se publica |
| **Evidencia de bloqueo** | `G-GATE-BLOCK-EVIDENCE`: tabla antes/después de una regresión inyectada, decisión de la puerta y snapshot, verificados por `scripts/check_block_evidence.py` | Misma evidencia que un PR bloqueado, reproducible sin depender de un servicio externo |
| **Iceberg degradado a Parquet plano** | `evalgate export parquet` (F10, ampliación). No es Iceberg y el README no lo llama así (ADR-020) | Sin S3 ni catálogo donde probarlo, sería un exportador sin un solo lector real |

---

## 7. Dónde vive cada contrato: `docs/CONTRACTS/` frente a `docs/spec/`

Este proyecto consume **cinco** contratos fijados y además escribe los suyos. Confundirlos es editar un
contrato fijado sin versionarlo, o tratar como inmutable algo que hay que escribir.

| Ruta | Qué es | Cómo se cambia |
|---|---|---|
| `docs/CONTRACTS/` | Contratos **fijados por sha256** (`docs/spec/contracts.sha256`): `eval-report.schema.json`, `otel-genai.md`, `pricing-table.md`, `retrieval-metrics.md`, `goals.schema.json`, `README.md` | Como evento versionado: sube la versión del contrato, se regenera `docs/spec/contracts.sha256` y se anota en `CHANGELOG.md` (R20) |
| `docs/spec/` | Contratos **propios** de este proyecto: `openai-openapi-<ver>.json` (snapshot **descargado** de la OpenAPI publicada) y `pricing-table.schema.json` (esquema de `pricing/<YYYY-MM-DD>.yaml`, derivado de `docs/CONTRACTS/pricing-table.md` §2) | Se escriben con normalidad |
| `otel-semconv.lock`, `pricing/TABLES.lock`, `thresholds.lock` | Anclas de versión y de integridad | `otel-semconv.lock` se fijó en F0; los dos `.lock` de umbrales y precios se regeneran a mano, como acto de sellado, nunca desde el gate |
| `evals/report-hash-exclusions.yaml` | Campos no deterministas excluidos del sha256 del informe | Configuración del proyecto. No cabe dentro del informe: el esquema tiene `additionalProperties: false` en la raíz |

No existe un directorio `contracts/` en la raíz: era un tercer sitio confundible con `docs/CONTRACTS/` y su
contenido vive ahora en `docs/spec/`.
