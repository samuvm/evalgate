# ADR-020 · Exportador Iceberg degradado a Parquet plano

**Fecha:** 2026-10-13
**Fase:** F9 (la decisión es de F0, RULES §3.15 y §6; el exportador en sí es F10, ampliación)
**Estado:** aceptado.

---

## Contexto

El diseño inicial preveía exportar las trazas como "Iceberg/Parquet sobre S3", para que un consumidor
analítico externo las leyera. Para evalgate eso significaría escribir sus spans como tabla Iceberg en S3.

No hay cuenta AWS, el almacén de este proyecto es ClickHouse (ADR-012) y Athena no lee Iceberg v3, así que el formato de tabla tendría que elegirse pensando en un consumidor que
todavía no existe.

## Opciones consideradas

| Opción | A favor | En contra |
|---|---|---|
| **A · Parquet plano con esquema documentado** (`evalgate export parquet`) | Lo lee DuckDB, pandas, Athena y cualquier catálogo; se puede testear el esquema en local | No es una tabla: sin snapshots, sin evolución de esquema, sin catálogo |
| **B · Escribir Iceberg** | Cumple el contrato tal como se nombró | Catálogo, metadatos y commits atómicos sobre S3 sin S3 donde probarlos; sería un exportador sin un solo lector real |
| **C · No exportar** | Cero trabajo | Ningún consumidor externo puede leer las trazas sin hablar con ClickHouse |

## Decisión

Se elige **A**, y se deja en **F10 (ampliación)**: no es núcleo y no bloquea la publicación. El volcado es
la tabla de spans a ficheros Parquet con el esquema escrito en `docs/spec/`.

## Consecuencias

- **No es Iceberg y el README no lo llamará así.** Quien quiera una tabla Iceberg la registra sobre esos
  ficheros con su propio catálogo.
- **A día de hoy el exportador no existe:** F10 no está comenzada. `pyarrow` ya es dependencia (lo trajo
  la matriz de F7), así que F10 no añade ninguna para esto.
- La promesa inicial de "Iceberg sobre S3" queda incumplida en su nombre, y así se dice.
