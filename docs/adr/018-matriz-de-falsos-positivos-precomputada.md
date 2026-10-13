# ADR-018 · Matriz de falsos positivos precomputada, y por qué el experimento en vivo es inviable

**Fecha:** 2026-10-13
**Fase:** F7
**Estado:** aceptado. Desarrolla RULES §5; las desviaciones respecto de su letra están en "Consecuencias".

---

## Contexto

F7 tiene que decir tres cosas de la propia puerta: cuántas veces bloquea un sistema que no ha cambiado
(`G-GATE-FP`), qué tamaño de caída es capaz de ver (`G-GATE-MDE`) y cuántas veces bloquea una caída real
(`G-GATE-POWER`). Las tres piden muchas ejecuciones del sistema con ruido: 49 decisiones como mínimo para
los falsos positivos y 50 por cada una de las cuatro degradaciones canónicas.

Medido en la máquina de referencia: una ejecución de 60 casos con el juez en vivo tarda unos 2,2 minutos;
una de 200 casos sin juez, unos 2,4. Las 250 ejecuciones son entre 6 y 10 horas de modelos.

## Opciones consideradas

| Opción | A favor | En contra |
|---|---|---|
| **A · Matriz grabada una vez, metas recalculadas offline** | El gate no llama a ningún modelo; los números se pueden volver a calcular y auditar caso a caso | La matriz envejece: si cambia el sistema o la suite hay que volver a grabarla |
| **B · Experimento en vivo en el gate** | Siempre al día | 6-10 h por `make done`; no determinista: dos ejecuciones del gate darían dos tasas; un fallo de Ollama a mitad tumba el cierre |
| **C · Simular el ruido** (remuestrear respuestas grabadas) | Segundos | El ruido que importa es el del modelo, y es justo lo que una simulación tendría que suponer |

## Decisión

Se elige **A**. `evalgate meta run-matrix` ejecuta el plan (`evals/suites/<suite>/matrix.yaml`) y guarda una
ejecución por fichero; es reanudable y una ejecución cortada se descarta entera. De los crudos sale
`evals/reports/fp-matrix.parquet` con `(run_id, case_id, metrica, valor)` y, en su metadato, el plan y su
sha256, la fuente de ruido, la semilla y el sha256 de cada ejecución. `meta fp | mde | sensitivity` leen solo
ese fichero y deciden con la puerta real (`gate.compare`), no con una copia.

- **Ruido declarado:** sistema a temperatura 0,7 y una semilla por ejecución (1000 + nº de ejecución).
- **Línea base fija:** `base-00`. Las otras 49 ejecuciones sin cambios dan las 49 decisiones de H0.
- **MDE leído, no estimado:** percentil 95 por rango más cercano de la caída entre todos los pares
  ordenados de ejecuciones de H0, en la peor métrica bloqueante.
- **Degradaciones ejecutadas de verdad,** 50 veces cada una, no inyectadas sobre las respuestas base.
- **Potencia** sobre las degradaciones de tamaño medido ≥ 1,5 × MDE; el mínimo sobre las cuatro se publica
  también.

## Consecuencias

- El gate comprueba la meta-evaluación sin modelos: `evalgate meta report --check` recalcula el documento
  publicado desde las etiquetas y la matriz y falla si difiere.
- **Desviación de RULES §5.2:** el recálculo tarda unos 25 s con 200 casos, no "menos de un segundo": son
  10.000 réplicas de bootstrap por decisión y 249 decisiones.
- **Desviación de RULES §5.1:** hay dos matrices, no una. La primera (60 casos, con juez) dio un MDE de
  15 pp; la segunda (200 casos, sin juez) se declaró antes de ejecutarla con el compromiso de que
  sustituiría a la primera en las tres metas a la vez. Las dos están publicadas.
- El juez no entra en la medida oficial: `faithfulness` dejó de bloquear al salir su kappa en 0,47.
- **Lo que la matriz enseñó:** con 200 casos, 5 de 49 decisiones bloquean un sistema sin cambios (0,102) y
  el MDE es 10,5 pp; las dos metas quedan en rojo y así se publican. El ruido entre ejecuciones iguales
  baja menos de lo que bajaría si cada caso variara por su cuenta; la interpretación, no demostrada, es que
  parte del ruido es de la ejecución entera (con ciertas semillas el modelo se abstiene de más en bloque) y
  no baja añadiendo casos.
- Una matriz solo vale para el sistema, la suite y el modelo con que se grabó. Cambiar cualquiera de los
  tres obliga a grabarla de nuevo; el metadato dice con cuáles se hizo.
