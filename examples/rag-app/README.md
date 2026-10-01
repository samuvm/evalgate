# examples/rag-app

Aplicación RAG mínima que sirve de demo y de e2e. **Es un cliente**: no importa nada de `src/evalgate/`
(RULES R13, verificado por `scripts/rules/example_is_client.py`). Solo usa la biblioteca estándar.

## Datos

`data/` se genera con `python generate_corpus.py` (semilla fija `20260910`): 40 fichas de productos
**ficticios** y 20 preguntas, un 20 % de ellas negativas (el producto no existe y la respuesta correcta es
`NO_CONSTA`). La respuesta correcta se conoce por construcción: `provenance: sintetico_por_construccion`
(PARA-SAMUEL Q-002 (a)). Este corpus no mide calidad de dominio; mide si la puerta detecta degradaciones.

## Adopción: una variable de entorno

```bash
python generate_corpus.py
OPENAI_BASE_URL=http://localhost:11434/v1 python rag_app.py --limit 3   # directo a Ollama
evalgate serve --port 8080 &                                             # proxy delante de Ollama
OPENAI_BASE_URL=http://localhost:8080/v1  python rag_app.py --limit 3   # a través de evalgate
```

`G-ADOPTION` mide las líneas de diferencia entre ambas salidas: tienen que ser cero
(`make test-e2e -k adoption`, `tests/e2e/test_adoption.py`).

Variables: `OPENAI_BASE_URL` (por defecto Ollama en el host), `RAG_MODEL` (por defecto `qwen3.5:9b-mlx`),
`OPENAI_API_KEY` (Ollama no la usa).
