# Contratos

Estos ficheros son las **interfaces estables** de evalgate: lo que un sistema que se ponga delante o
detrás de la puerta necesita para hablar con ella sin leer su código. Cada uno fija algo que, sin
contrato, cada consumidor acabaría interpretando a su manera.

## La regla

**Se fijan por sha256. Nunca se editan en el día a día.**

El sha256 de cada fichero está en `docs/spec/contracts.sha256` y lo comprueba
`tests/contract/test_contracts_are_verbatim_copies.py` (R20). Cambiar un contrato es un evento consciente:
se edita, se sube su versión, se regenera el pin y se anota en `CHANGELOG.md`.

Un consumidor externo copia el contrato que necesita; no importa un paquete. Duplicar unos
ficheros es barato. Un paquete común del que dependan varios repositorios es caro: rompe la
independencia y obliga a publicarlo.

## Qué hay aquí

| Contrato | Por qué existe |
|---|---|
| `goals.schema.json` | Forma canónica de `docs/GOALS.yaml`. Sin él, cada meta inventa su convención: `clase` significaba dos cosas incompatibles, la cobertura iba unas veces en ratio y otras en porcentaje, y algunos umbrales estaban en prosa. Un umbral en prosa no lo puede leer ningún script, y entonces la meta no bloquea nada |
| `retrieval-metrics.md` | Una sola definición de recall, precisión de cita y abstención, el esquema del golden set, el bootstrap pareado y la corrección por comparaciones múltiples. Sin ella, dos evaluaciones medirían "recall" de dos formas y sus números no se podrían poner en la misma tabla |
| `otel-genai.md` | Versión pineada y lista de atributos OpenTelemetry GenAI. Nada del namespace `gen_ai.*` es estable en 2026: sin versión fijada y capa de traducción, la integración se rompe sola |
| `eval-report.schema.json` | Formato del informe de evaluación. La puerta no puede comparar dos informes que no comparten esquema |
| `pricing-table.md` | Tabla de precios con fecha de vigencia. Sin ella, un informe de coste histórico no es reproducible |

### La distinción que evita el error más fácil

`docs/CONTRACTS/` son **contratos fijados**. Los contratos propios del proyecto —el snapshot de
la OpenAPI de OpenAI, el esquema JSON de la tabla de precios— viven en `docs/spec/`, y ahí sí se
escribe con normalidad. Confundirlos hace inejecutable cualquier fase cuyo entregable sea un
esquema propio.

Donde el repo se aparta de la letra de un contrato, el desvío está declarado en ADR-006.

## Interfaces que NO están aquí, y por qué

- **API compatible con OpenAI.** No necesita fichero: el contrato es la especificación pública de
  OpenAI, y los tests validan contra un snapshot descargado (`docs/spec/openai-openapi-2.3.0.json`),
  no contra una interpretación propia.
- **Iceberg / Parquet sobre S3.** Degradado a `evalgate export parquet` (Parquet plano, ampliación;
  ADR-020). No es Iceberg y no se presenta como tal.
