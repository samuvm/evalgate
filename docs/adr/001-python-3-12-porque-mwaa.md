# ADR-001 · Python 3.12 porque MWAA no ofrece más

**Fecha:** 2026-09-10
**Fase:** F0
**Estado:** **aceptado**

---

## Contexto

Existen Python 3.13 y 3.14 (en esta máquina hay 3.13.11 y 3.14.6). Evalgate no despliega en MWAA, pero
está pensado para ponerse delante de pipelines que sí corren en Airflow gestionado de AWS, y comparte con
ellos ruedas de torch/MPS y contratos: un intérprete distinto aquí rompería la uniformidad que permite mover
código y contratos entre repositorios sin sorpresas. Se fija `requires-python = "==3.12.*"`.

## Opciones consideradas

| Opción | A favor | En contra | Coste estimado |
|---|---|---|---|
| **A · 3.12 en todos los repositorios** | Uniforme; MWAA solo ofrece 3.12; ruedas maduras | Se renuncia a mejoras de 3.13/3.14 | 0 h |
| **B · 3.14 solo en evalgate** | Intérprete más rápido para el proxy | Diverge de la matriz de versiones común | 1-2 h + riesgo de ruedas |
| **C · 3.13** | Término medio | Mismos contras que B, con menos ganancia | 1 h |

## Decisión

Se elige **A**. El motivo no es "lo pide la oferta": es que MWAA no ofrece más que 3.12, y un ecosistema de
cinco repositorios con un solo intérprete es más barato de mantener que uno donde cada repo elige.
El intérprete concreto es **CPython 3.12.12 gestionado por uv** (`.python-version`), no el 3.12.4 de Anaconda
del sistema: es la build estándar y la que puede reproducir un desconocido que clone el repo.

## Consecuencias

- **Lo que gana:** una sola matriz de versiones válida para todos los repositorios que la comparten.
- **Lo que cuesta:** la sobrecarga del proxy (`G-LAT-PROXY`, `G-LAT-TTFT`) se mide en 3.12; si hubiera
  margen con 3.14, no se aprovecha.
- **Qué habría que ver para revertirla:** que MWAA ofrezca 3.13 o superior, o que `G-LAT-PROXY` falle por
  el intérprete con el protocolo de `docs/bench/protocol.md` cumplido.
- **Qué se toca si se revierte:** `pyproject.toml`, `.python-version`, `uv.lock`, `[tool.mypy]` y
  `[tool.ruff]`.
