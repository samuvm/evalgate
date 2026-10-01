# Evalgate · reglas específicas del proyecto

> **Solo lectura para el agente.** No repite nada de `docs/CONSTITUCION.md`: la complementa.
> Donde esta hoja y `docs/PROJECT.md` difieran, gana esta hoja y el motivo está escrito.
> Donde esta hoja y `docs/CONTRACTS/**` difieran, **gana el contrato**: es compartido con otros
> proyectos y no se improvisa (CONSTITUCION §4.2 caso G).

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
| **R16** | **La puerta se autoexcluye hasta F9.** `EVALGATE_SELF_GATE=off` es válido mientras la fase activa sea < 9; **en F9 su retirada es entregable del plan**, y a partir de ahí volver a ponerlo en `off` exige una propuesta en `PARA-SAMUEL.md` | `scripts/rules/self_gate.py` lee la fase activa de `STATE.md` y falla si está en `off` con fase >= 9 sin propuesta | F0 |
| **R17** | **Todo número del README sale de un fichero de `evals/reports/`.** Ninguno se escribe a mano | `make report` regenera las tablas; `scripts/rules/readme_numbers.py` falla si el README difiere de lo regenerado | F1 |
| **R18** | **Toda dependencia con `==` y hash.** `uv --require-hashes`, `pip-audit` en el gate de turno, imágenes Docker por digest. El rango de `STACK.md` es la investigación, no el pin: el agente lo traduce a un `==` concreto y anota la versión elegida en `JOURNAL.md` (CONSTITUCION §7.2) | `scripts/rules/pins.py` + `pip-audit` en `gate-full` | F0 |
| **R19** | **`[tool.gate].cobertura_linea_min` y `.mutantes_muertos_min` coinciden con `G-LINE-COV` y `G-MUTATION`, en la misma unidad** (`porcentaje`: 90 y 75) | `scripts/check_gate_config.py`, en `gate-fast`. Ver §4.1 | F1 |
| **R20** | **`docs/CONTRACTS/` son copias literales de `_comun/CONTRACTS/`** y no se escriben nunca. Lo propio del proyecto vive en `docs/spec/`, que sí se escribe. Ver §7 | `pytest tests/contract/test_contracts_are_verbatim_copies.py` (sha256 fichero a fichero contra `_comun/`) | F0 |

**Por qué R16 existe, y por qué el número es 9:** el repo se usa a sí mismo como puerta de calidad, y eso es un
bucle. Una puerta rota bloquea el trabajo sobre la puerta. La escotilla es explícita, está acotada y su
retirada es un **entregable de F9** (`PLAN.md` §1, fila F9: `EVALGATE_SELF_GATE=on`). Por eso la verificación
falla desde la fase 9 y no antes: marcar rojo en F7 y F8 sería exigir algo que el propio plan todavía no ha
pedido, y el resultado previsible es que alguien desactive el script en lugar de arreglar nada.

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

**Dónde TDD es obligatorio:** los cinco paquetes de `[tool.gate].tdd_obligatorio`. El ciclo rojo→verde con
**parada de turno entre medias** (CONSTITUCION §4.1) es el mecanismo, no el orden de las líneas del fichero.

**Dónde TDD está prohibido:** `evals/judges/` (llamadas), `prompts/`, `dashboards/` y `examples/`. Forzar TDD
sobre un prompt es teatro: produce un test que solo dice que el fichero no ha cambiado, se rompe cada vez que
se mejora el prompt, y se acaba borrando. Lo que se hace con un prompt es versionarlo (frontmatter de
CONSTITUCION §7.6), registrarlo en el informe (R14) y medir su efecto.

---

## 3. Errores típicos de este dominio, y por qué el agente los evitará

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
15. **Inventar un exportador Iceberg.** El mapa de conjunto declara un contrato "Iceberg/Parquet sobre S3"
    que este proyecto no implementa en ninguna parte. Degradado a `evalgate export parquet` (Parquet plano,
    F10, ampliación). No se mete un hito no presupuestado por leer el mapa.

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

**Extensión propia sobre la constitución:** `testable` y `tdd_obligatorio` aceptan **rutas de fichero**, no
solo paquetes. Motivo: `proxy/` en conjunto no es testeable unitariamente (es I/O asíncrono y estado de
conexión), pero `proxy/streaming.py` **sí lo es** dado un transcript grabado, y es el fichero más importante
del repositorio. Excluirlo por vivir en un paquete "de adaptador" sería exactamente el error que este
proyecto denuncia. `scripts/check_function_coverage.py` debe soportar ambas formas.

**Aviso de gobierno (R19), y la unidad de los dos números.** `pyproject.toml` **no** está en
`permissions.deny`: un agente bloqueado podría bajar `cobertura_linea_min` o `mutantes_muertos_min` sin tocar
`GOALS.yaml`. Por eso están duplicados en `docs/GOALS.yaml` (`G-LINE-COV`, `G-MUTATION`), que sí está
protegido por `thresholds.lock`, y `scripts/check_gate_config.py` falla si difieren. **Manda el número de
`GOALS.yaml`.** Los cuatro números están en **porcentaje** (90 y 75), nunca en ratio: `coverage.py` escribe
`totals.percent_covered` en escala 0-100 y `mutmut` reporta muertos sobre total en la misma escala, así que la
comparación es literal y no lleva conversión. Escribir 0.90 aquí y 90 allí es el fallo que hace que un check
cruzado marque rojo sin motivo —o, peor, verde sin motivo—; por eso `GOALS.yaml` declara `unidad` en cada
umbral (contrato `goals.schema.json`).

### 4.2 Qué significa exactamente

1. **Toda función pública** (sin `_` inicial) de un paquete o fichero de `testable` tiene **≥ 1 contexto de
   test** (`pytest --cov-context=test`). Estándar de la constitución §2.6.
2. **Toda función pública de `pricing/` y `stats/` necesita además ≥ 1 test de propiedad**, no solo de
   ejemplo. Motivo: son los dos sitios donde el test por ejemplo es demostradamente insuficiente —un cálculo
   de coste con tres casos de ejemplo pasa y sigue siendo incorrecto en el cambio de tarifa; un intervalo
   bootstrap con un caso pasa y tiene el sesgo invertido—. Verificación: segunda pasada de
   `check_function_coverage.py` sobre `tests/property/`, cruzando por nombre de función referenciada.
3. **`proxy/streaming.py` no se mide por función sino por corpus.** Su criterio es: **cada fichero de
   `tests/fixtures/sse/` tiene un test que lo consume**, y el conjunto cubre los 12 casos límite de
   `PLAN.md` §3. Verificación: `scripts/rules/sse_corpus_coverage.py` falla si hay un fixture sin test o un
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

## 6. Correcciones explícitas a `docs/PROJECT.md` y a la hoja de investigación

Se listan porque un agente que lea `PROJECT.md` sin esto construirá lo que ya no aplica.

| Fuente | Qué decía | Qué aplica ahora, y por qué |
|---|---|---|
| PROJECT.md §3 | `src/llm_gate/`, repositorio `llm-gate` | `src/evalgate/`, directorio `evalgate-02`, CLI `evalgate`. Nombres canónicos congelados en CONSTITUCION §7.1 |
| PROJECT.md §1 | "endpoint compatible con el protocolo de Bedrock" (de entrada) | **Retirado.** SigV4 + `application/vnd.amazon.eventstream`: 20-40 h sin retorno. Bedrock solo de salida |
| PROJECT.md §1 | "FastAPI **o** LiteLLM como base" | **El servidor proxy es propio.** LiteLLM entra solo como librería de adaptadores de salida, con las funciones concretas listadas en su ADR |
| PROJECT.md §1 | "Métricas: Ragas + DeepEval + propias" | **Métricas propias, funciones puras.** DeepEval solo como contraste nocturno (F10). Ragas fuera: congelado desde feb-2026 |
| PROJECT.md §2 | "error ≤ 1 % contra la factura real del proveedor" | Partido en `G-PRICE-REPRO` (aritmética, determinista, bloqueante) y `G-COST-RECONCILE` (conciliación humana, artefacto fresco bloqueante, delta publicado sea cual sea) |
| PROJECT.md §2 | "falsos positivos ≤ 5 % en 20 ejecuciones" | n ≥ 49 con fuente de ruido declarada, más `G-GATE-MDE` y `G-GATE-POWER`, que no existían |
| PROJECT.md §2 | "ahorro por caché de jueces ≥ 70 %" | `G-CACHE-HIT` (coste marginal ≤ 5 %) y `G-CACHE-INVAL` |
| PROJECT.md §4 | "mypy --strict en **todo** `src/`" | Sobre `[tool.gate].testable`, como en los otros cuatro proyectos (CONSTITUCION §7.4). Extender a `providers/` y `cli/` es ruido con adaptadores de terceros sin tipos |
| PROJECT.md §4 | Trunk-based, Conventional Commits, `release-please`, PRs, GitHub Actions | **No hay git todavía.** `make gate-full` es la CI. `.github/workflows/gate.yml` se escribe en F9 **sin activar**, como prueba de que la portabilidad es de una línea |
| PROJECT.md §5 | Criterio 4: "PR público donde la puerta bloqueó" | `G-GATE-BLOCK-EVIDENCE`: entrada en `JOURNAL.md` con tabla antes/después + snapshot. Misma evidencia, demostrable en entrevista, y convertible a PR cuando llegue git |
| Hoja de investigación §H | Escribir `docs/CONTRACTS/eval-report.schema.json` con `required: [schema_version, suite_id, cases[].case_id, ...]` y una lista `no_deterministicos` dentro del informe | **Corregido: el contrato ya existe en `_comun/` y se copia, no se escribe.** Sus campos obligatorios son `contract_version, run_id, project, suite, created_at, environment, dataset, metrics`. No hay `cases[]`: el detalle caso a caso va en `metrics[].raw_path`. Y la lista de campos no deterministas **no cabe** dentro del informe (`additionalProperties: false` en la raíz): vive en `evals/report-hash-exclusions.yaml` |
| Hoja de investigación §D/E | `pricing/tables/<proveedor>-<fecha>.yaml` con `valid_from`/`valid_to` y `cached_input_per_1k` | **Corregido: gana el contrato `pricing-table.md`.** Ruta `pricing/<YYYY-MM-DD>.yaml`; sin `valid_to` (se resuelve por el `effective_from` más reciente ≤ t); `cache_write_per_1k` y `cache_read_per_1k` separados; `fx.USD_EUR` con `fx_date` obligatorio |
| Hoja de investigación §E R1 | Contador `spans_dropped_total` | El **nombre externo** de la métrica es `app.spans.dropped` (contrato `otel-genai.md` §4). El nombre interno es libre |
| Mapa de conjunto | Contrato "Iceberg/Parquet sobre S3 · 04, 02 → 03" | Degradado a `evalgate export parquet` (Parquet plano, F10, ampliación). No es Iceberg y el README no lo llamará así |

---

## 7. Dónde vive cada contrato: `docs/CONTRACTS/` frente a `docs/spec/`

La distinción es de la constitución (§1.1) y aquí importa más que en los otros cuatro proyectos, porque este
consume **cinco** contratos compartidos y además escribe los suyos. Confundirlos es editar un contrato de
otros, o tratar como inmutable algo que hay que escribir.

| Ruta | Qué es | Quién escribe |
|---|---|---|
| `docs/CONTRACTS/` | **Copias literales** de `_comun/CONTRACTS/`: `eval-report.schema.json`, `otel-genai.md`, `pricing-table.md`, `retrieval-metrics.md`, `goals.schema.json`, `README.md` | **Nadie.** En `deny`. Se cambian en `_comun/` y se propagan a mano, con entrada en `CHANGELOG.md` (R20) |
| `docs/spec/` | Contratos **propios** de este proyecto: `openai-openapi-<ver>.json` (snapshot **descargado** de la OpenAPI publicada) y `pricing-table.schema.json` (esquema de `pricing/<YYYY-MM-DD>.yaml`, derivado de `docs/CONTRACTS/pricing-table.md` §2) | El agente, en F0. Aquí **sí** se escribe |
| `otel-semconv.lock`, `pricing/TABLES.lock`, `thresholds.lock` | Anclas de versión y de integridad | `otel-semconv.lock` en F0; los dos `.lock` de umbrales y precios los regenera **solo Samuel** |
| `evals/report-hash-exclusions.yaml` | Campos no deterministas excluidos del sha256 del informe | El agente. No cabe dentro del informe: el esquema tiene `additionalProperties: false` en la raíz |

`chunks-ddl.sql` **no** se copia: es el contrato 01 ↔ 04 y no aplica aquí (`_comun/CONTRACTS/README.md`).
No existe un directorio `contracts/` en la raíz: era un tercer sitio confundible con `docs/CONTRACTS/` y su
contenido vive ahora en `docs/spec/`.
