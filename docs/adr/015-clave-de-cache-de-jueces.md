# ADR-015 · Clave de caché de las llamadas a modelo: todo lo que puede cambiar la respuesta, y nada más

**Fecha:** 2026-10-07
**Fase:** F5
**Estado:** aceptado

---

## Contexto

Cada veredicto del juez es una llamada a un modelo de 12 B de parámetros. Sin caché, `make eval` no puede
correr en el gate: tarda minutos, depende de que Ollama esté vivo y no da el mismo informe dos veces. Con
caché, el riesgo se invierte, y es peor porque no se ve: una clave a la que le falta un componente **sirve el
veredicto de un prompt viejo** y la métrica conserva su valor aunque el juez haya cambiado.

Medido el 2026-10-07: la ejecución en frío de la suite `rag-app` cuesta **107.120 tokens** (200 veredictos);
la segunda, **0**. `G-CACHE-INVAL` = 1,0 sobre 2.013 comprobaciones (perfil nightly).

## Opciones consideradas

| Decisión | Elegida | Descartada, y por qué |
|---|---|---|
| **Componentes** | Los seis de R10 (id del juez, modelo, parámetros de muestreo, versión del prompt, sha256 del prompt, sha256 del texto evaluado) **más el rol** (`judge` / `generator`) | Solo "prompt + texto": cambiar de modelo o de temperatura serviría veredictos de otro juez. Sin rol: un generador y un juez con el mismo prompt compartirían entrada |
| **Cómo se combinan** | sha256 del **JSON canónico** (claves ordenadas, cada valor en su campo) | Concatenar: `("ab","c")` y `("a","bc")` dan la misma cadena. Es el bug clásico y tiene su test |
| **Qué es "el prompt"** | El sha256 del **fichero entero**, frontmatter incluido | Solo el cuerpo: la temperatura vive en el frontmatter, y dos jueces que solo difieren en ella son dos jueces |
| **Parámetros de muestreo** | Todos los que se envían, sin importar el orden; `0` y `0.0` son el mismo | Una lista cerrada de parámetros "que importan": `reasoning_effort` no estaba en ninguna lista y cambia la respuesta entera (ver abajo) |
| **Almacén** | Un JSONL en el repositorio, una entrada por línea, en orden de llamada | DuckDB o SQLite: binarios que no se revisan en un diff, y `uv add duckdb` no estaba autorizado en el turno. 200 entradas caben de sobra en texto |
| **Un fallo de caché en `make eval`** | **Error** que dice `make eval-refresh` | Llamar al modelo: convertiría un gate determinista en uno que depende de si Ollama está encendido |
| **Dos respuestas para una clave** | **Error**; una entrada no se pisa | Quedarse con la última: a temperatura 0 la misma llamada da la misma respuesta, y si no la da, eso es justo lo que hay que ver |

## Decisión

Se eligen las siete de la columna central. El criterio es uno: **la clave incluye todo lo que puede cambiar
la respuesta, y lo que no la cambia no entra** (ni el orden en que se escriben los parámetros, ni si un cero
lleva decimales).

El caso que justifica "todos los parámetros que se envían": `gemma4:12b-mlx` razona por defecto y, con
`max_tokens: 8`, gasta los ocho en razonar y devuelve el veredicto vacío. Con `reasoning_effort: none`
responde `FIEL` en dos tokens. Ese parámetro es parte de la llamada y por tanto de la clave.

El coste se cuenta en **tokens**, no en euros: con modelos locales todo euro es cero y una razón de ceros
no dice nada. Los tokens son lo que facturaría un proveedor de pago y lo que la ejecución se ahorró.

## Consecuencias

- **Lo que gana:** `make eval` es gratis, determinista y corre en el gate. Subir la versión del prompt de un
  juez invalida el 100 % de sus entradas y el 0 % de las de los demás (test de extremo a extremo).
- **Lo que cuesta:** cambiar una coma del prompt del juez son otras 200 llamadas. Es correcto que lo sea.
- **Qué habría que ver para revertirla:** que la caché pase de miles de entradas y el JSONL pese en los
  diffs. Entonces, DuckDB con este mismo esquema de clave.
- **Qué se toca si se revierte:** `evals/cache/store.py`. La clave (`key.py`) no.
