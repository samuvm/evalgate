# ADR-008 · `make mutation` corre mutmut en una copia del proyecto que no contiene la reserva

**Fecha:** 2026-09-11
**Fase:** F1 (preparación de F4)
**Estado:** aceptado (decisión reversible del constructor, CONSTITUCION §4.2 caso H; ejecuta P-003, aprobada)

---

## Contexto

P-003 fija `make mutation` como comando de `G-MUTATION` (>= 75 %, bloquea desde F4) con `mutmut==3.7.0`.
Dos hechos de mutmut 3.7.0, leídos en su código (`mutmut/configuration.py`, `mutmut/__main__.py`):

1. `also_copy` lleva **siempre** `tests/`: al ejecutarse copia el directorio de tests entero a `mutants/`.
   En la raíz del proyecto eso deja `tests/holdout/` en `mutants/tests/holdout/`, y el `deny` del
   constructor (`day-300/*/tests/holdout/**`) **no cubre esa ruta**. La reserva dejaría de ser ilegible.
2. A `mutants/` solo se copian las rutas de `source_paths`. Con las cinco rutas de P-003 como
   `source_paths`, `mutants/src/evalgate/` queda sin `__init__.py`: Python lo trata como porción de paquete
   de espacio de nombres, encuentra antes el paquete original (instalado en editable) y los tests ejercitan
   el código **sin mutar**. mutmut responde "no test case for any mutant".

Pasó de verdad el 2026-09-11: una ejecución de depuración lanzada por error en la raíz creó `mutants/` con la
copia de la reserva. Se borró en el acto sin leer nada de ella (JOURNAL 2026-09-11).

## Opciones consideradas

| Opción | A favor | En contra | Coste estimado |
|---|---|---|---|
| **A · Copia temporal sin `tests/holdout/` y mutmut dentro, con el intérprete del proyecto** | La reserva no existe donde corre mutmut; nada nuevo en la raíz | Copiar el proyecto cuesta ~1 s | 1 h |
| **B · mutmut en la raíz y ampliar el `deny` a `mutants/**`** | Sin copia | Toca `~/.claude/gates/` (solo Samuel); la reserva seguiría copiada en disco | 0,5 h + Samuel |
| **C · Parchear `also_copy` de mutmut** | Directo | Parche a una dependencia fijada; se pierde en cada actualización | 1 h y deuda |

## Decisión

Se elige **A**. `scripts/mutation.py` copia el proyecto a un directorio temporal excluyendo `tests/holdout/`
(y aborta si aun así apareciera), ejecuta `python -m mutmut run` con `cwd` en esa copia y escribe
`evals/reports/mutation-F<N>.json` con `killed_pct = 100 · killed / (total − skipped)`: supervivientes, sin
test, timeout y sospechosos cuentan en contra. El informe lista cada mutante no muerto con su diff.
En `[tool.mutmut]`: `source_paths = ["src/"]` y las cinco rutas de P-003 en `only_mutate`; matan mutantes solo
`tests/unit`, `tests/property` y `tests/contract` (la reserva nunca participa en una medida del constructor).

## Consecuencias

- **Lo que gana:** la mutación no puede filtrar la reserva; el número mide el código mutado de verdad.
- **Lo que cuesta:** una copia del proyecto por ejecución; `also_copy` debe listar lo que leen los tests de
  contrato (`docs/`, `evals/`, `otel-semconv.lock`). Un test nuevo que lea otro fichero de la raíz obliga a
  añadirlo ahí.
- **Regla operativa:** nunca `mutmut` a mano en la raíz. Solo `make mutation`.

## Revisión

Si mutmut deja de copiar `tests/` por defecto, o si Samuel amplía el `deny` a `mutants/**`, la copia sobra.
