# Contrato · métricas de retrieval y esquema del golden set

> Afecta a **01 (citebound)**, **02 (evalgate)** y **04 (indexkeeper)**.
> Se copia a los tres. No se importa.
>
> Existe porque hoy el 01 y el 04 miden "recall" con definiciones distintas, y sus README
> no serían comparables. Y porque la métrica insignia del 01 —precisión de cita— no está
> definida lo bastante para implementarla: dos agentes producirían dos números distintos,
> ambos llamados 0,85.
>
> **Versión del contrato: 1**

---

## 1. La regla que lo gobierna: nunca se evalúa contra `chunk_id`

El documento del 01 mide `context recall @5` sobre chunks recuperados. **Eso invalida el
golden set cada vez que cambia la estrategia de troceado**, que es exactamente lo que pasa en
su fase de retrieval y en toda la comparativa de troceado del 04. El trabajo de anotar 150-200
casos se destruiría solo, a mitad del proyecto.

**Toda evaluación de retrieval y de cita se ancla en `legal_ref`** — el identificador legal
estable definido en `chunks-ddl.sql` (`norma#artNN.apartado`). El recall se calcula mapeando
`chunk → legal_ref` y comparando conjuntos de referencias legales, no de chunks.

Consecuencia práctica: puedes cambiar el chunker, el modelo de embeddings o el reranker, y el
golden set sigue siendo válido. Es lo que permite que el 04 compare estrategias de troceado
usando el golden set del 01.

---

## 2. Definiciones únicas

Sea, para una pregunta `q`:

- `R(q)` = conjunto de `legal_ref` **relevantes** según el golden set.
- `P_k(q)` = conjunto de `legal_ref` distintos presentes en los `k` chunks recuperados.

### recall@k

```
recall@k(q) = |R(q) ∩ P_k(q)| / |R(q)|
```

Se reporta la **media sobre las preguntas con `R(q)` no vacío**. Las preguntas sin respuesta en
el corpus (casos negativos) **quedan fuera del denominador de recall** — se usan solo para
medir abstención.

Nota: `|P_k(q)|` puede ser menor que `k`, porque varios chunks pueden apuntar al mismo
artículo. Es correcto y deliberado: lo que importa es si la referencia está, no cuántas veces.

### Precisión de cita

El documento dice "¿el artículo citado es el del golden set? Exacto, sí/no". Eso no resuelve
cuatro casos que aparecen constantemente. Se cierra así:

| Caso | Regla |
|---|---|
| La respuesta cita varias referencias | **Todas** las citadas deben pertenecer a `R(q)`. Una cita correcta más una inventada cuenta como fallo |
| Granularidad de apartado | Si el golden set especifica apartado, la cita **debe** incluirlo. `21` cuando lo correcto es `21.1` es fallo. Si el golden set no especifica apartado, citar uno es correcto siempre que el artículo coincida |
| Respuesta apoyada en dos artículos | `R(q)` los contiene ambos; se exige citar **al menos uno** y **ninguno fuera de `R(q)`** |
| Abstenciones | **Fuera del denominador** de precisión de cita. Se miden aparte |

```
precision_cita = casos_con_todas_las_citas_en_R / casos_respondidos_no_abstenidos
```

### Alucinación de artículo — tolerancia cero

```
alucinacion = casos_donde_alguna_cita_no_existe_en_el_corpus / casos_respondidos
```

"No existe" significa: `legal_ref` que no está en la tabla `chunk` para el `index_version`
activo. Es una comprobación de pertenencia a un conjunto, determinista y barata. **Objetivo
0,00 y sin intervalo de confianza: aquí no hay umbral estadístico.**

### Abstención

```
abstencion_total     = casos_abstenidos / total
abstencion_incorrecta = casos_abstenidos_con_R(q)_no_vacio / casos_con_R(q)_no_vacio
```

**Esto exige casos negativos en el golden set.** Sin preguntas cuya respuesta no está en el
corpus, la abstención incorrecta no se puede calcular y la métrica es decorativa. Ver §3.

---

## 3. Esquema del golden set

Un fichero JSONL. Una línea, un caso. Validado por Pydantic antes de cualquier eval.

```json
{
  "id": "gs-0042",
  "version": 1,
  "pregunta": "¿Se puede adelantar en un cambio de rasante sin visibilidad?",
  "respuesta_referencia": "No. Está expresamente prohibido adelantar en cambios de rasante de visibilidad reducida.",
  "refs": ["RD-1428/2003#art34.1"],
  "materia": "adelantamiento",
  "dificultad": "media",
  "tipo": "positivo",
  "provenance": "llm_generado_revisado_humano",
  "revisado_por": "samuel",
  "revisado_en": "2026-08-20",
  "notas": ""
}
```

| Campo | Obligatorio | Notas |
|---|---|---|
| `id` | sí | Estable. Nunca se reutiliza tras borrar |
| `version` | sí | Sube al editar el caso. Los informes registran qué versión midieron |
| `pregunta` | sí | |
| `respuesta_referencia` | solo si `tipo="positivo"` | |
| `refs` | sí | Lista de `legal_ref`. **Vacía si y solo si `tipo="negativo"`** |
| `materia` | sí | Permite estratificar y filtrar |
| `dificultad` | sí | `facil` / `media` / `dificil` |
| `tipo` | sí | `positivo` (hay respuesta) / `negativo` (no está en el corpus) |
| `provenance` | sí | `humano` / `llm_generado_revisado_humano` / `llm_generado` |
| `revisado_por`, `revisado_en` | sí si hay revisión | |

### Tres reglas duras

1. **Mínimo un 15 % de casos `negativo`.** Sin ellos no hay métrica de abstención incorrecta.
2. **`provenance` se declara en el README.** Los documentos ya dicen que esconder que los datos
   de alumnos son sintéticos "se nota y resta credibilidad". Aplica igual aquí.
3. **Ningún caso entra en el golden set sin revisión humana.** Generación asistida por LLM sí;
   aprobación automática no. Es el único punto del proyecto donde el criterio de dominio de
   Samuel es insustituible.

### Sobre el tamaño: 150 es el suelo, no 200

El tamaño del golden set no es una preferencia, lo fija la estadística de la puerta (§4). Con
bootstrap **pareado** sobre proporciones de p≈0,85:

| n | Efecto mínimo detectable (IC 95 %) |
|---|---|
| 60 | ±9,0 pp |
| 100 | ±7,0 pp |
| **150** | **±5,7 pp** |
| 200 | ±4,9 pp |

Con menos de 150 casos no puedes distinguir una regresión real de ruido, y la puerta del 02 no
significa nada. **Se arranca en 150 y se crece.** El README publica el efecto mínimo detectable
con el `n` real, no solo el número de casos.

Coste humano honesto: anotar a mano son 6-12 min por caso, entre 20 y 40 h para 200. Con
generación asistida más revisión de 1,5-3 min por caso, baja a 8-14 h. **No baja a cero.**

---

## 4. Comparación estadística: bootstrap pareado

El documento del 01 dice "bootstrap sobre los 200 casos" sin decir si es pareado. La elección
cambia por completo la sensibilidad y la tasa de falsos positivos, y dos agentes construirían
dos puertas incomparables.

**Decisión: bootstrap pareado sobre los mismos casos.** Se remuestrean los casos, no las
ejecuciones: para cada réplica se toma la diferencia `métrica_head - métrica_base` **sobre el
mismo subconjunto de casos**. La varianza cae mucho respecto al no pareado y detectas cambios
mucho menores con el mismo `n`.

- 10.000 réplicas, semilla fijada y registrada en el informe.
- La puerta bloquea si: **la métrica cae bajo su umbral absoluto**, **o** el IC 95 % de la
  diferencia pareada queda enteramente por debajo de cero.

### Corrección por comparaciones múltiples

Obligatoria cuando se vigilan más de tres métricas **bloqueantes** a la vez. **Por defecto,
Holm-Bonferroni.**

El motivo importa y conviene saber decirlo: Holm controla la **tasa de error por familia**
—la probabilidad de bloquear al menos una vez sin causa— y eso es exactamente lo que arruina
una puerta de calidad. Un falso bloqueo cuesta una tarde y, sobre todo, erosiona la confianza:
la puerta que bloquea sin motivo se acaba desactivando, que es el riesgo número uno declarado
del proyecto 02. Holm es además uniformemente más potente que Bonferroni y no exige supuestos
adicionales, así que no hay razón para preferir Bonferroni.

Benjamini-Hochberg controla la **tasa de falsos descubrimientos** y es la elección correcta
cuando se exploran muchas métricas informativas y un falso positivo aislado no bloquea nada
—por ejemplo, un panel de diagnóstico o el desglose por materia—. Se admite ahí, no en la
puerta.

Valores admitidos en el informe: `holm` (por defecto), `benjamini-hochberg`, `bonferroni`,
o `null` si se vigilan tres métricas o menos.

---

## 5. Conjunto de consultas para comparar troceado (04)

El 04 compara estrategias de troceado y necesita medir recall. **Usa este mismo formato y esta
misma definición de recall@k**, sobre el subconjunto `tipo="positivo"`. Esa es toda la razón de
que este contrato exista: si el 04 inventa su propia definición, sus números y los del 01 no se
pueden poner en la misma tabla, y la comparativa de estrategias pierde su sentido.

El 04 **no anota su propio golden set**. Consume el del 01 cuando existe, y mientras no exista
usa un conjunto reducido propio marcado explícitamente como provisional en su README.
