# ADR-NNN · <título en una línea, en indicativo: "ClickHouse como almacén de trazas">

> Copia este fichero a `docs/adr/NNN-titulo-en-kebab.md` con el siguiente número libre.
> Tope orientativo: 40 líneas. Un ADR largo es un ADR que nadie relee.
> **Los ADR no se modifican.** Cambiar de opinión es escribir otro que supersede a este y anotarlo aquí.

**Fecha:** AAAA-MM-DD
**Fase:** F<N>
**Estado:** propuesto | **aceptado** | supersedido por ADR-NNN | rechazado

---

## Contexto

Qué problema real hay delante, y qué fuerzas lo aprietan: restricciones de la máquina, del contrato, del
presupuesto de horas o de una meta de `GOALS.yaml`. Si hay una medida que motiva la decisión, va aquí con su
número, su `n` y la fecha en que se tomó. Sin contexto medible, el ADR es una opinión con
formato.

## Opciones consideradas

Al menos dos reales. Una opción de paja no cuenta: si la alternativa era obviamente mala, no había decisión
que documentar.

| Opción | A favor | En contra | Coste estimado |
|---|---|---|---|
| **A ·** | | | |
| **B ·** | | | |
| **C ·** | | | |

## Decisión

Se elige **X**. En una o dos frases, el motivo que decanta —no el resumen de la tabla—.
Si la decisión descarta algo que un revisor esperaría ver, dilo explícitamente: *"se descartó Y aunque es la
opción de manual, porque Z"*. Esa frase es la que se lee en una entrevista.

## Consecuencias

- **Lo que gana:** …
- **Lo que cuesta:** … (horas, dependencia nueva, superficie de fallo, cosa que ya no se podrá hacer)
- **Qué habría que ver para revertirla:** el disparador concreto, no "si va mal".
- **Qué se toca si se revierte:** ficheros o módulos afectados.

---

# ADR pendientes de escribir en este proyecto

Salidos de la investigación previa. Todos están escritos; la última columna dice dónde. Una decisión no obvia
fuera de esta lista lleva igualmente su ADR.

| Fase | ADR | Por qué no es obvio | Escrito en |
|---|---|---|---|
| F0 | **LiteLLM como librería, no como proxy** | Hay que listar **exactamente** qué funciones de `litellm` se usan. Si el proxy fuera de LiteLLM, el mérito del proyecto desaparece; y el ataque de cadena de suministro de marzo de 2026 obliga a minimizar la superficie confiada | ADR-002 |
| F0 | **Evalgate frente a Bifrost (Python frente a Go)** | Bifrost tiene 11 µs de sobrecarga a 5.000 rps. Competir en latencia con un runtime Python es perder: hay que escribir por qué la latencia no es el argumento y qué sí lo es | ADR-003 |
| F0 | **Evalgate frente a Langfuse v4** | ClickHouse compró Langfuse en enero de 2026 y v4 trae *experiment gates* en CI. Sin este ADR el repositorio se lee como "reescribí Langfuse". Debe nombrar el 20 % que ninguna plataforma da llave en mano | ADR-004 |
| F0 | **Modelo de datos OTel interno propio con capa de traducción** | Nada de `gen_ai.*` es estable. Adoptar un estándar no es atarse a él mientras es inestable; la diferencia es todo el ADR | ADR-005 |
| F0 | **Python 3.12 porque MWAA no ofrece más** | El motivo correcto, no "porque lo pide la oferta". Existen 3.13 y 3.14 | ADR-001 |
| F2 | **Contabilidad de tokens ante desconexión del cliente** | El caso que casi nadie implementa y medio mérito del proxy. Debe explicar el `finally`, la supervivencia a `CancelledError` y por qué el tokenizador local es la referencia cuando falta el chunk de `usage` | ADR-010 |
| F3 | **ClickHouse como almacén y política de degradación** | Las trazas son carga analítica, no OLTP: es una decisión que hay que saber defender. Y la política de degradación (`app.spans.dropped` como métrica de primera clase, cola acotada, la petición nunca espera) es el cuarto diferenciador | ADR-012 |
| F4 | **Tablas de precios inmutables y fechadas** | Es el argumento comercial: un informe de coste de hace tres meses sigue siendo reproducible. Debe explicar por qué corregir un precio es crear un fichero nuevo y nunca editar el pasado | ADR-013 |
| F5 | **Diseño de la clave de caché de jueces** | Seis componentes, y el fallo típico es invalidar de más o de menos. Debe justificar cada componente | ADR-015 |
| F5 | **Corpus sintético autoverificable y su procedencia** | Debe declarar `provenance` y por qué no invalida la tesis | ADR-016 |
| F6 | **Bootstrap pareado y corrección por comparaciones múltiples** | La elección cambia por completo la sensibilidad y la tasa de falsos positivos. Debe incluir el efecto mínimo detectable con el `n` real y por qué Holm y no Bonferroni | ADR-014 |
| F7 | **Matriz de falsos positivos precomputada** | El ADR más valioso del proyecto: el experimento en vivo son 10.000 generaciones y es inejecutable. Debe explicar por qué el efecto mínimo detectable es empírico y no teórico | ADR-018 |
| F9 | **Endpoint Bedrock de entrada retirado del alcance** | Un recorte deliberado con su motivo cuantificado (20-40 h, SigV4 y framing binario) vale más que un alcance inflado | ADR-019 |
| F9 | **Exportador Iceberg degradado a Parquet plano** | Un exportador Iceberg sin S3 ni un lector real sería un hito no presupuestado. Documentar el recorte es más honesto que fingirlo | ADR-020 |
