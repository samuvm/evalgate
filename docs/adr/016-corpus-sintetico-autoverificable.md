# ADR-016 · Corpus sintético autoverificable: de dónde sale el golden set y qué no mide

**Fecha:** 2026-10-07
**Fase:** F5
**Estado:** aceptado

---

## Contexto

La suite necesita 200 casos con respuesta conocida. El contrato `retrieval-metrics.md` §3 dice que ningún
caso entra en un golden set sin revisión humana; revisar 200 casos son 8-14 h humanas sobre un corpus que no
mediría nada de dominio. Se decidió un corpus sintético para este proyecto: la regla del contrato tiene
sentido para los golden sets que miden calidad de dominio, no para uno cuyo sujeto es la puerta. El desvío
está declarado en ADR-006.

Lo que este proyecto mide no es si un RAG responde bien. Es si **la puerta** distingue una degradación real
del ruido. Para eso hace falta saber la respuesta correcta sin discusión, no que el dominio sea interesante.

## Opciones consideradas

| Opción | A favor | En contra | Coste |
|---|---|---|---|
| **A · Sintético por construcción** | La respuesta se conoce porque se genera con la ficha; determinista; gratis; reproducible por cualquiera | No mide calidad de dominio; hay que declararlo | 0 h humanas |
| **B · Generado por LLM y revisado a mano** | Cumple el contrato tal cual | 8-14 h humanas sobre fichas de productos inventados | 8-14 h |
| **C · Un dataset público de preguntas y respuestas** | Nadie puede decir que es de juguete | Licencias, respuestas discutibles, y el sistema bajo prueba es una app de ejemplo de 100 líneas | 4-6 h + riesgo |

## Decisión

Se elige **A**, con la procedencia declarada en cada caso (`provenance: sintetico_por_construccion`) y en
el README. 120 fichas de productos que no existen y 200 preguntas sobre un campo de una ficha; el 15 % son
negativas (el producto no está y la respuesta correcta es `NO_CONSTA`), el suelo del contrato. Todo sale de
`scripts/gen_golden.py` con semilla fija.

Dos cosas que se aprendieron al medir, y que ya están en el corpus:

1. **La referencia es el dato, no su presentación.** Con `"433 €"` como referencia, la primera tanda real
   puntuó 0,39 a un sistema que respondía `433` a "¿cuál es el precio en euros…?". Acertaba; la medida
   estaba mal. La referencia es ahora `"433"` y la métrica sigue comparando palabras enteras.
2. **El corpus es fácil, y eso tiene una consecuencia.** La línea base saca 1,00 en todo. Una caída se ve
   igual de bien desde 1,00, pero una línea base sin varianza no dice nada sobre falsos positivos: a
   temperatura 0 y con caché, dos ejecuciones son idénticas. De dónde sale el ruido de la matriz de falsos
   positivos es una decisión de F7 que hay que tomar a sabiendas, no un detalle.

Lo que este corpus **no** permite afirmar: nada sobre la calidad de ningún RAG real. Cuando evalgate se
aplique a citebound-01 (F11), el golden set será el de citebound, con revisión humana y bajo el contrato
tal cual.

## Consecuencias

- **Lo que gana:** `make eval` reproducible por un desconocido, sin horas humanas, y respuestas correctas
  indiscutibles para medir la puerta.
- **Lo que cuesta:** un corpus de juguete, dicho con esas palabras. Y una dependencia de calendario: la
  kappa del juez (F7) sí necesita etiquetas humanas, 100 casos etiquetados a mano, que no se sintetizan.
- **Qué habría que ver para revertirla:** que F7 no pueda construir una fuente de ruido defendible sobre
  este corpus. Entonces, preguntas más difíciles (comparar dos fichas, agregar) antes que más casos.
- **Qué se toca si se revierte:** `scripts/gen_golden.py` y `evals/golden/`. Cambiar el golden invalida las
  salidas grabadas, no los veredictos de casos que no cambien.
