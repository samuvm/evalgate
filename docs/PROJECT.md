# Proyecto 02 · `llm-gate`

> Pasarela que se sitúa delante de cualquier API de LLM: registra trazas, tokens y coste; ejecuta suites de evaluación contra un conjunto de casos con respuesta conocida; y bloquea el merge cuando la calidad cae más de lo que explica el ruido.

**Independiente:** sí. Se prueba contra una aplicación de ejemplo incluida en el propio repo. No necesita a ningún otro proyecto para demostrar su valor.

---

## 1. De qué va técnicamente

Tres subsistemas que comparten almacén pero se pueden usar por separado:

**A · El proxy.** Expone un endpoint compatible con el protocolo de OpenAI y otro con el de Bedrock. Reenvía la petición al proveedor real y, por el camino, emite un span de OpenTelemetry con modelo, tokens de entrada y salida, latencia hasta el primer token, latencia total, coste calculado y hash del prompt. La adopción cuesta cambiar una variable de entorno: cero código.

**B · El motor de evaluación.** Lee un conjunto de casos versionados, ejecuta el sistema bajo prueba, aplica métricas y produce un informe comparable entre ejecuciones.

**C · La puerta de calidad.** Un comando que compara el informe de la rama contra el de la línea base y devuelve código de salida distinto de cero si hay regresión estadísticamente significativa. Eso es lo que ejecuta CI.

### Por qué el streaming complica todo

El punto técnicamente interesante: en modo streaming no puedes esperar la respuesta completa para medirla, porque bloquearías al usuario. El proxy tiene que **reenviar los chunks según llegan y acumular en paralelo**, cerrando el span cuando termina el flujo. Hay que manejar además el caso de cliente que se desconecta a mitad: esos tokens ya se han pagado y deben contabilizarse igual. Resolver esto bien es la mitad del mérito del proyecto.

### Arquitectura

```
   tu app  ──►  llm-gate (proxy)  ──►  Bedrock / OpenAI / Ollama
                     │
                     ├─► span OTel ──► ClickHouse ──► panel (Grafana)
                     │                     │
                     │                     └──► alertas: coste, p95, tasa de error
                     │
   golden set ──► motor de evals ──► informe JSON ──► puerta ──► CI (exit 0/1)
   (JSONL)              │
                        └─► jueces LLM (cacheados por hash)
                        └─► detector de deriva (embeddings de entradas vs. base)
```

### Stack

| Componente | Elección | Por qué |
|---|---|---|
| Proxy | Python 3.12 + FastAPI, o **LiteLLM** como base | LiteLLM ya resuelve la traducción entre proveedores; construir eso desde cero no aporta nada |
| Trazas | OpenTelemetry + convenciones semánticas de GenAI | Estándar abierto. Cualquier backend lo consume |
| Almacén | ClickHouse (o DuckDB en modo ligero) | Las trazas son carga analítica: columnar, no OLTP. Es una decisión que hay que saber defender |
| Métricas | Ragas + DeepEval + métricas propias | |
| Panel | Grafana con dashboards como código | |
| Estadística | `scipy` + bootstrap propio | Para los intervalos de confianza |
| CI | GitHub Actions | |

---

## 2. Objetivos

### Funcionales

- Proxy transparente compatible con `/v1/chat/completions`, con y sin streaming.
- `llm-gate eval run --suite X` → informe JSON reproducible.
- `llm-gate eval compare --base main --head HEAD` → tabla + código de salida.
- Panel con coste por día/modelo/servicio, p95 de latencia, tasa de error, tokens.
- Detección de deriva de distribución de las entradas.
- Presupuesto configurable con alerta al superar la proyección.

### De calidad

| Métrica | Objetivo | Nota |
|---|---|---|
| Sobrecarga de latencia del proxy | p95 ≤ 30 ms sobre la llamada directa | Medido, no estimado |
| Exactitud del cálculo de coste | error ≤ 1 % contra la factura real del proveedor | Se valida con una factura real de un mes |
| Pérdida de trazas | 0 % en operación normal, degradación elegante si el almacén cae | Nunca tumbar la app por un fallo de observabilidad |
| Falsos positivos de la puerta | ≤ 5 % en 20 ejecuciones consecutivas sin cambios | Es *el* riesgo del proyecto |
| Ahorro por caché de jueces | ≥ 70 % en ejecuciones repetidas | |

**El requisito no negociable:** si ClickHouse no responde, el proxy sigue sirviendo peticiones y descarta trazas. Una capa de observabilidad que puede tirar la aplicación es peor que no tenerla.

### Fuera de alcance

Interfaz web de anotación, gestión de usuarios, entrenamiento de modelos, comparación automática entre proveedores.

---

## 3. Estructura del repositorio

```
llm-gate/
├── src/llm_gate/
│   ├── proxy/          # rutas, traducción de protocolos, streaming
│   ├── telemetry/      # spans, atributos, exportadores
│   ├── pricing/        # tablas de precios versionadas por fecha
│   ├── evals/
│   │   ├── metrics/    # cada métrica, aislada y testeable
│   │   ├── judges/     # jueces LLM + caché
│   │   └── runner.py
│   ├── gate/           # comparación estadística y decisión
│   └── drift/
├── examples/rag-app/   # app de ejemplo instrumentada, sirve de demo y de e2e
├── golden/             # casos en JSONL, versionados
├── dashboards/         # JSON de Grafana, como código
├── tests/
└── docs/adr/
```

**Las tablas de precios llevan fecha de vigencia.** Los proveedores cambian precios; un informe de coste de hace tres meses debe seguir siendo reproducible con los precios de entonces. Este detalle, pequeño, es de las cosas que distinguen a alguien que ha operado esto de verdad.

---

## 4. Metodología de desarrollo

### Enfoque general

**Hito 0 — el proxy más tonto posible (2 días).** Reenvía y devuelve, sin streaming, sin métricas. Con un test que compruebe que la respuesta es byte a byte idéntica a la llamada directa.

**Hito 1 — streaming correcto.** Aquí está la dificultad real. Se ataca con tests antes que con código, porque los casos límite son enumerables: cliente que corta, proveedor que corta, chunk malformado, timeout a mitad.

**Hito 2 — telemetría y coste.** Con la validación contra una factura real como criterio de aceptación.

**Hito 3 — motor de evals.** Cada métrica es un módulo puro y aislado que recibe estructuras de datos y devuelve un número.

**Hito 4 — la puerta.** El componente que decide. Se construye al final porque necesita datos históricos para calibrarse.

**Hito 5 — deriva y panel.**

### Pirámide de tests

**Nivel 0 · Estáticos.** `ruff`, `mypy --strict` en todo `src/` (aquí sí en todo: es una librería, la API pública importa), `bandit`, `detect-secrets`.

**Nivel 1 · Unitarios.** El corazón de este proyecto es determinista, así que la cobertura aquí puede y debe ser alta (≥ 90 % en `pricing/`, `metrics/`, `gate/`).

Lo que se prueba de verdad:
- **Cálculo de coste:** tabla de casos con precios conocidos, incluidos cambios de tarifa a mitad de periodo, caché de prompt con descuento, modelos con precio distinto de entrada y salida.
- **Ensamblado de chunks de streaming:** dada una secuencia grabada de eventos SSE, ¿el texto reconstruido y el conteo de tokens son correctos? Incluye secuencias truncadas.
- **Cada métrica por separado:** con entradas fabricadas donde el resultado esperado se calcula a mano.
- **La lógica de la puerta:** dados dos informes sintéticos, ¿decide bien? Este es el módulo que se escribe **con TDD estricto**, porque es donde un error tiene consecuencias reales (bloquear cambios buenos o dejar pasar malos).
- **Propiedades con Hypothesis:** el coste nunca es negativo; añadir tokens nunca reduce el coste; la comparación es antisimétrica.

**Nivel 2 · Integración.** `testcontainers` con ClickHouse.
- Escritura y consulta de spans reales.
- Comportamiento cuando el almacén está caído: la petición debe completarse igual. Se prueba **tumbando el contenedor a mitad del test**.
- Contrapresión: con el almacén lento, la cola se llena y descarta sin bloquear.

**El proveedor de LLM se dobla con `respx`** para las respuestas HTTP y con transcripciones grabadas para el streaming.

**Nivel 3 · Contrato.**
- Compatibilidad con el esquema de OpenAI: se valida contra su especificación OpenAPI publicada, no contra la interpretación propia.
- Los atributos de los spans cumplen las convenciones semánticas de GenAI de OpenTelemetry. Inventarse nombres de atributo aquí es el error que hace inútil la integración con cualquier herramienta.
- El formato del informe de evaluación tiene esquema versionado.

**Nivel 4 · Meta-evaluación.** Este es el nivel propio de este proyecto y no existe en los demás: **hay que evaluar el evaluador.**

- **Calibración de los jueces:** un subconjunto de 50 casos etiquetados a mano. Se mide la concordancia del juez LLM con la etiqueta humana (Cohen's kappa). Si el juez no correlaciona con el criterio humano, la métrica no vale nada por muy bonito que sea el número.
- **Tasa de falsos positivos de la puerta:** se ejecuta la misma suite 20 veces sin cambiar nada. Cuántas veces bloquea. Ese número va en el README.
- **Sensibilidad:** se introduce una degradación conocida (por ejemplo, se recorta el contexto a la mitad) y se comprueba que la puerta la detecta. Una puerta que nunca bloquea es tan inútil como una que bloquea siempre.

**Nivel 5 · E2E.** Con `examples/rag-app`: levantar todo, generar tráfico, comprobar que las trazas llegan, ejecutar evals, provocar una regresión y ver la puerta bloquear.

### QA y flujo de trabajo

- Trunk-based, ramas cortas, Conventional Commits, `release-please` para versionado semántico.
- **El propio repo se usa a sí mismo:** los PRs de `llm-gate` pasan por la puerta de `llm-gate`. Es la mejor demostración posible y sale gratis.
- **Un PR de demostración deliberadamente roto**, mantenido abierto en el repo, con el comentario automático de bloqueo visible. Lo primero que enseñas en una entrevista.
- Pipeline rápido < 3 min. El lento (integración + meta-evaluación) por la noche.
- ADRs obligatorios en: elección de almacén, diseño de la caché de jueces, criterio estadístico de la puerta, política de degradación ante fallo.

---

## 5. Criterios de aceptación

1. Una app existente se instrumenta cambiando una variable de entorno, sin tocar código.
2. El panel muestra coste y latencia reales tras dos minutos de tráfico.
3. `eval compare` produce la misma decisión ejecutado dos veces sobre los mismos datos.
4. Existe un PR público donde la puerta bloqueó, con su tabla.
5. El README declara la tasa de falsos positivos medida, no estimada.

## 6. Riesgos conocidos

| Riesgo | Mitigación |
|---|---|
| La puerta bloquea por ruido y acaba desactivada | Es el riesgo principal. Se mide explícitamente y el umbral se calibra con datos, no a ojo |
| El coste de los jueces se dispara | Caché por hash desde el primer día, no como optimización posterior. Modelo barato para juez |
| Proyecto poco vistoso | La demo del PR bloqueado y un vídeo de 60 s en el README |
| Reinventar LiteLLM | Se usa como base y se documenta en un ADR qué se añade encima |
