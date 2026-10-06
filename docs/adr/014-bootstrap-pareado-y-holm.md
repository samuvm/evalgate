# ADR-014 · Bootstrap pareado y Holm, decididos sobre una cuenta exacta y sin dependencias

**Fecha:** 2026-10-06
**Fase:** F6
**Estado:** aceptado

---

## Contexto

La puerta tiene que contestar una sola pregunta: *¿esta caída es mayor que el ruido?* El contrato
(`retrieval-metrics.md` §4) fija el método —bootstrap **pareado**, 10.000 réplicas, semilla registrada,
IC 95 %, Holm con más de tres métricas bloqueantes— y deja abiertas cuatro cosas de las que depende qué
cambios se bloquean. Se decidieron escribiendo primero el test.

Medido el 2026-10-06: 10.000 réplicas sobre 200 casos tardan **58 ms** con la librería estándar.
Con 200 casos y una proporción en torno a 0,88, el intervalo pareado de dos ejecuciones independientes mide
unos ±6,5 puntos: es el orden de magnitud del efecto mínimo detectable, que F7 medirá de verdad.

## Opciones consideradas

| Decisión | Elegida | Descartada, y por qué |
|---|---|---|
| **Qué se remuestrea** | Los casos. Cada réplica es la media de `head − base` sobre los mismos casos | Remuestrear cada informe por separado: mezcla la dispersión entre casos en la diferencia. Test: una caída de 0,01 en todos los casos se ve pareada (intervalo de anchura cero) y sin parear queda enterrada |
| **Cómo se decide "IC entero bajo cero"** | Sobre la **cuenta exacta** de réplicas en que el cambio no fue peor (`Fraction`), contra α = (1 − nivel)/2. Los extremos del intervalo son rangos elegidos para que sea la misma afirmación | Comparar flotantes del intervalo: informe y decisión podrían discrepar en el borde, y un p-valor justo en α caería de un lado u otro según la máquina |
| **Corrección múltiple** | Holm sobre p-valores ajustados, y solo sobre la familia de métricas **bloqueantes** | Bonferroni: Holm rechaza todo lo que Bonferroni y más, sin supuestos. Benjamini-Hochberg: controla falsos descubrimientos, no el error por familia; vale para un panel. Incluir las métricas informativas en la familia: añadir un diagnóstico volvería sorda a la puerta |
| **"Cae bajo su umbral absoluto"** | Bajo el umbral **y** peor que la base | Bloquear todo lo que esté bajo el umbral: `compare(a, a)` bloquearía (rompe R9), y también el cambio que arregla la métrica |
| **Dependencias** | Solo librería estándar (`random`, `math.fsum`, `fractions`) | numpy + scipy (`scipy.stats.bootstrap`): dos dependencias que fijar y auditar para ahorrar 58 ms, y `uv add` no estaba autorizado en el turno. Si F7 necesita vectorizar la matriz de 3.000 × 50, se pide entonces |

## Decisión

Se eligen las cinco de la columna central. El hilo común es que **la puerta tiene que poder defenderse línea
a línea**: una decisión reproducible al bit (misma semilla, casos ordenados, `fsum`, fracciones exactas, una
semilla derivada por métrica para que añadir una no mueva el intervalo de otra) y sin un solo número escrito
en `gate/decision.py` (R7, regla por AST que también prohíbe fabricar el número con `float()` o
`Fraction(True)`: la primera versión lo hacía).

Lo que la puerta **no** sabe todavía, y no finge saber: cada cuánto se equivoca. `compare-fixture` es
sintético y solo prueba la mecánica. La tasa de falsos positivos, el efecto mínimo detectable y la potencia
son F7, sobre salidas de modelo reales.

Dos parámetros llegan del contrato y no de `GOALS.yaml`: el 95 % y el "más de tres". Están como constantes con
nombre en `gate/config.py`, el único sitio, y `GOALS.yaml` gana si los declara (`comparacion.nivel_confianza`
y `comparacion.correccion_desde`).

## Consecuencias

- **Lo que gana:** G-DETERMINISM = 1 (3 parejas, dos procesos); mutación 88,58 % con `stats/` y `gate/`
  dentro; antisimetría exacta y `compare(a, a)` que nunca bloquea, como propiedades.
- **Lo que cuesta:** el intervalo percentil no corrige sesgo (no es BCa). Con proporciones lejos de 0 y 1
  y n ≥ 150 la diferencia es pequeña; con n pequeño o tasas cerca de 0 conviene saberlo.
- **Qué habría que ver para revertirla:** que F7 mida una tasa de falsos positivos por encima de su meta
  atribuible al intervalo percentil, o que la matriz de F7 no quepa en tiempo sin vectorizar.
- **Qué se toca si se revierte:** `stats/paired_bootstrap.py`. Ni la decisión ni el informe.
