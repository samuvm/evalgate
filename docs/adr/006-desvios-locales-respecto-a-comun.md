# ADR-006 · Desvíos locales respecto a `_comun/` mientras se trabaja solo en este repositorio

**Fecha:** 2026-09-10
**Fase:** F0
**Estado:** **aceptado**

---

## Contexto

Samuel ordenó el 2026-09-10 trabajar "únicamente dentro de este repositorio; luego lo adaptaremos al
siguiente". `_comun/` es de solo lectura para el agente. Pero cuatro decisiones de ese día contradicen o
completan documentos compartidos, y alguien que lea `_comun/` no las verá.

## Opciones consideradas

| Opción | A favor | En contra | Coste estimado |
|---|---|---|---|
| **A · Esperar a que Samuel edite `_comun/`** | Una sola fuente de verdad | Bloquea F0 por algo que Samuel pidió aplazar | días |
| **B · Registrar cada desvío aquí y en `PARA-SAMUEL.md`, con su vuelta atrás escrita** | No bloquea; el desvío es visible y auditable | Dos sitios hasta que se propague | 0,5 h |

## Decisión

Se elige **B**. Cada desvío es consciente, lleva su origen y la acción pendiente en `_comun/`:

| Desvío | Documento compartido | Origen | Acción pendiente de Samuel |
|---|---|---|---|
| Pin OTel `semantic-conventions@v1.41.1` | `CONTRACTS/otel-genai.md` §1, §3 | Q-008 (a); ADR-005 | Corregir repo, versión y "eliminadas en v1.43.0" → v1.42.0 |
| Ollama 0.33.3 | `STACK.md` §2 (0.32.6) | Chat 2026-09-10 | Subir la versión en `STACK.md` y propagar a los cinco |
| Decisiones D-01, D-03, D-04, D-05 y D-09 | `PARA-SAMUEL-GLOBAL.md` | Chat 2026-09-10 | Volcarlas al global |
| Golden set sintético del 02 | `CONTRACTS/retrieval-metrics.md` §3 regla 3 | Q-002 (a) | Acotar la regla a 01 y 04 **antes de F5** |

Las copias de `docs/CONTRACTS/`, `docs/CONSTITUCION.md` y `docs/STACK.md` **no se tocan**: siguen siendo
literales (R20, verificado por `tests/contract/test_contracts_are_verbatim_copies.py`). El desvío vive en
los ficheros propios: `otel-semconv.lock`, este ADR y `PARA-SAMUEL.md`.

## Consecuencias

- **Lo que gana:** el trabajo no se para, y nadie tiene que adivinar dónde se aparta el repo del estándar común.
- **Lo que cuesta:** hasta que Samuel propague, otro agente que lea `_comun/` verá decisiones pendientes.
- **Qué habría que ver para revertirla:** que Samuel edite `_comun/`. Entonces se regenera
  `docs/spec/copias-comun.sha256` y este ADR pasa a supersedido.
- **Qué se toca si se revierte:** `docs/CONTRACTS/**` (copia nueva), `docs/spec/copias-comun.sha256`, CHANGELOG.
