# ADR-017 · Golden set v2: el mismo método sintético, con preguntas que se pueden fallar

**Fecha:** 2026-10-10
**Fase:** entre F6 y F7
**Estado:** aceptado. Amplía ADR-016, que sigue vigente para el v1.

---

## Contexto

Sobre el golden v1 no se puede medir lo que F7 tiene que medir (medido el 2026-10-07): la línea base saca
1,000 en todo, el juez dijo NO_FIEL en 6 de 497 veredictos y dos de las cuatro degradaciones canónicas no
cambian ni una respuesta. Sin casos de las dos clases no hay kappa; sin varianza no hay falsos positivos que
contar; sin degradaciones que degraden no hay potencia.

## Opciones consideradas

| Opción | A favor | En contra |
|---|---|---|
| **A · Un v2 más difícil, mismo método** | Deja sitio para medir sin tocar las degradaciones ni el juez; sigue siendo reproducible y sin horas humanas | Es diseñar un banco de pruebas, y eso se puede hacer con trampa |
| **B · Retocar las degradaciones** hasta que degraden | Rápido | RULES §5 las declara fijadas; elegir la degradación por el resultado es lo que este repo denuncia. No arregla la kappa |
| **C · Publicar "no medible"** | Honesto | F7 es la tesis del proyecto |

## Decisión

Se elige **A** (2026-10-07). El v2 son 160 fichas en 40 familias de cuatro "hermanos" con el mismo
nombre y otro número, y 200 casos de cinco clases: búsqueda simple (60), comparación entre dos productos
(50), filtro por categoría, país y año (50), negativo cuyo hermano sí existe (25) y negativo simple (15).
El 20 % son negativos. El v1 no se toca: respalda los números de F5.

**Lo que se fijó antes de medir, y lo que se cambió después.** La mezcla se escribió antes de ejecutar nada.
Tras la primera medición se cambió **una cosa, y solo de redacción**: las 50 preguntas de filtro decían
"¿cuál es el más caro?" y el sistema, que tiene orden de responder "solo con el dato pedido", contestó el
**precio del producto correcto** en 32 de 50. Puntuaba 10 de 50. La pregunta era ambigua y contarlo como
error medía la redacción. Ahora dicen "¿cómo se llama el más caro?" y puntúa 49 de 50. La línea base pasó de
0,705 a 0,900. Las comparaciones, donde los fallos son reales (respuesta equivocada, o nombrar las dos
opciones), no se tocaron: 31 de 50.

Para las comparaciones, la métrica `answer_correct` acepta `excluye`: una respuesta que nombra las dos
opciones contiene la correcta y no ha respondido nada.

Medido el 2026-10-10 (qwen3.5:9b-mlx; juez gemma4:12b-mlx; 200 casos), **sin retocar ninguna degradación**:

| Variante | answer_correct | faithfulness | Puerta |
|---|---|---|---|
| base | 0,900 | 0,905 | — |
| (a) contexto al 50 % | 0,635 | 0,645 | bloquea |
| (b) modelo pequeño | 0,855 | 0,885 | **pasa** (−4,5 pp, IC95 [−10,0, +0,5]) |
| (c) 20 % de documentos aleatorios | 0,705 | 0,905 | bloquea |
| (d) temperatura 1,2 | 0,755 | 0,765 | bloquea |

El juez dijo NO_FIEL en 171 de 652 veredictos (26 %). Ya hay dos clases.

## Consecuencias

- **Lo que gana:** F7 tiene de qué medir. Y un dato que ya vale por sí solo: una caída real de 4,5 puntos
  **no** se detecta con 200 casos. Es el efecto mínimo detectable asomando antes de medirlo.
- **Lo que cuesta:** un banco diseñado por quien construye la puerta. La defensa es la que hay: la mezcla
  fijada antes de medir, el único cambio posterior explicado con sus dos números, y las degradaciones tal
  cual las fija RULES.
- **Lo que no arregla:** la línea base sigue siendo determinista (temperatura 0, caché). De dónde sale el
  ruido de la matriz de falsos positivos es decisión de F7.
- **Qué habría que ver para revertirla:** que la kappa del juez salga baja por culpa de preguntas mal
  planteadas y no del juez. Las etiquetas humanas lo dirán.
- **Qué se toca si se revierte:** `scripts/gen_golden_v2.py`, `evals/golden/rag-app-v2/` y la suite
  `rag-app-v2`. Nada del v1.
