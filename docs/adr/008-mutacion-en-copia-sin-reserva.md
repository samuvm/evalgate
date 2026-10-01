# ADR-008 · `make mutation` corre mutmut en una copia del proyecto que no contiene la suite reservada

**Fecha:** 2026-09-11
**Fase:** F1 (preparación de F4)
**Estado:** aceptado (decisión reversible)

---

## Contexto

`G-MUTATION` (>= 75 %, bloquea desde F4) se mide con `make mutation` y `mutmut==3.7.0`: en la línea 3.x no
existen `run --paths-to-mutate` ni `results --json`, así que el comando tiene que ser un target propio.
Dos hechos de mutmut 3.7.0, leídos en su código (`mutmut/configuration.py`, `mutmut/__main__.py`):

1. `also_copy` lleva **siempre** `tests/`: al ejecutarse copia el directorio de tests entero a `mutants/`.
   En la raíz del proyecto eso deja `tests/holdout/` en `mutants/tests/holdout/`: una segunda copia de la
   suite reservada (privada, no se publica, para que no se pueda ajustar el código contra ella), fuera de la
   ruta que la protege.
2. A `mutants/` solo se copian las rutas de `source_paths`. Con las cinco rutas de `tdd_obligatorio` como
   `source_paths`, `mutants/src/evalgate/` queda sin `__init__.py`: Python lo trata como porción de paquete
   de espacio de nombres, encuentra antes el paquete original (instalado en editable) y los tests ejercitan
   el código **sin mutar**. mutmut responde "no test case for any mutant".

Pasó de verdad el 2026-09-11: una ejecución de depuración lanzada por error en la raíz creó `mutants/` con la
copia de la suite reservada. Se borró en el acto sin leer nada de ella.

## Opciones consideradas

| Opción | A favor | En contra | Coste estimado |
|---|---|---|---|
| **A · Copia temporal sin `tests/holdout/` y mutmut dentro, con el intérprete del proyecto** | La suite reservada no existe donde corre mutmut; nada nuevo en la raíz | Copiar el proyecto cuesta ~1 s | 1 h |
| **B · mutmut en la raíz y proteger también `mutants/**`** | Sin copia | La suite reservada seguiría copiada en disco, y la protección pasaría a depender de una ruta más | 0,5 h |
| **C · Parchear `also_copy` de mutmut** | Directo | Parche a una dependencia fijada; se pierde en cada actualización | 1 h y deuda |

## Decisión

Se elige **A**. `scripts/mutation.py` copia el proyecto a un directorio temporal excluyendo `tests/holdout/`
(y aborta si aun así apareciera), ejecuta `python -m mutmut run` con `cwd` en esa copia y escribe
`evals/reports/mutation-F<N>.json` con `killed_pct = 100 · killed / (total − skipped)`: supervivientes, sin
test, timeout y sospechosos cuentan en contra. El informe lista cada mutante no muerto con su diff.
En `[tool.mutmut]`: `source_paths = ["src/"]` y las cinco rutas de `tdd_obligatorio` en `only_mutate`; matan
mutantes solo `tests/unit`, `tests/property` y `tests/contract` (la suite reservada nunca participa en esta
medida).

## Consecuencias

- **Lo que gana:** la mutación no puede filtrar la suite reservada; el número mide el código mutado de verdad.
- **Lo que cuesta:** una copia del proyecto por ejecución; `also_copy` debe listar lo que leen los tests de
  contrato (`docs/`, `evals/`, `otel-semconv.lock`). Un test nuevo que lea otro fichero de la raíz obliga a
  añadirlo ahí.
- **Regla operativa:** nunca `mutmut` a mano en la raíz. Solo `make mutation`.

## Revisión

Si mutmut deja de copiar `tests/` por defecto, la copia sobra.
