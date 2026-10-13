# Números medidos

Generado por `make report` desde `evals/reports/`. No se edita a mano (regla R17).
Hardware de referencia: MacBook Pro M4 Max, 36 GB de memoria unificada.

## La puerta, medida (meta-evaluación)

`evalgate meta report --check` vuelve a calcular la medida oficial desde las etiquetas humanas
y la matriz de ejecuciones, sin llamar a ningún modelo. La matriz se midió dos veces; antes de
ejecutar la segunda quedó escrito que sus tres números sustituirían a los de la primera,
salieran como salieran.

| Meta | Medido | Umbral | ¿Cumple? | Detalle |
|---|---|---|---|---|
| `G-JUDGE-KAPPA` | 0,47 | >= 0,60 | **no** | IC95 [0,27, 0,65] · 150 etiquetas humanas · acuerdo bruto 0,86 |
| `G-GATE-FP` | 0,102 | <= 0,05 | **no** | Wilson 95 % [0,044, 0,218] · 5 bloqueos en 49 decisiones contra `base-00` |
| `G-GATE-MDE` | 10,50 | <= 8,00 | **no** | puntos porcentuales, en `answer_correct` · 200 casos · 2450 pares de 50 ejecuciones |
| `G-GATE-POWER` | 1,00 | >= 0,90 | sí | mínimo sobre las degradaciones de tamaño ≥ 15,75 pp · mínimo sobre las 4: 0,02 |

Métricas que bloquean: `answer_correct`, `context_recall`, `abstencion_incorrecta`. Ruido: sistema bajo prueba con RAG_TEMPERATURE=0.7 y semilla distinta por ejecución (RAG_SEED = 1000 + nº de ejecución); sin juez: sus métricas no se miden.

| Degradación | Potencia | Bloqueos | Tamaño medido | ¿Se le exige? |
|---|---|---|---|---|
| `contexto-50` | 1,00 | 50/50 | 36,3 pp en `abstencion_incorrecta` | sí |
| `docs-aleatorios-20` | 1,00 | 50/50 | 23,6 pp en `abstencion_incorrecta` | sí |
| `modelo-pequeno` | 0,02 | 1/50 | 0,8 pp en `answer_correct` | no: por debajo del tamaño exigido |
| `temperatura-1.2` | 0,28 | 14/50 | 4,8 pp en `answer_correct` | no: por debajo del tamaño exigido |

**Medida anterior, publicada tal cual** · 60 casos · `evals/reports/meta-eval-60.json`

| Meta | Medido | Umbral | ¿Cumple? | Detalle |
|---|---|---|---|---|
| `G-GATE-FP` | 0,122 | <= 0,05 | **no** | Wilson 95 % [0,057, 0,242] · 6 bloqueos en 49 decisiones contra `base-00` |
| `G-GATE-MDE` | 15,00 | <= 8,00 | **no** | puntos porcentuales, en `answer_correct` · 60 casos · 2450 pares de 50 ejecuciones |
| `G-GATE-POWER` | 1,00 | >= 0,90 | sí | mínimo sobre las degradaciones de tamaño ≥ 22,50 pp · mínimo sobre las 4: 0,00 |

Métricas que bloquean: `answer_correct`, `context_recall`, `abstencion_incorrecta`. Ruido: sistema bajo prueba con RAG_TEMPERATURE=0.7 y semilla distinta por ejecución (RAG_SEED = 1000 + nº de ejecución); juez llamado en vivo en cada caso, sin caché.

| Degradación | Potencia | Bloqueos | Tamaño medido | ¿Se le exige? |
|---|---|---|---|---|
| `contexto-50` | 1,00 | 50/50 | 31,4 pp en `abstencion_incorrecta` | sí |
| `docs-aleatorios-20` | 1,00 | 50/50 | 24,9 pp en `abstencion_incorrecta` | sí |
| `modelo-pequeno` | 0,00 | 0/50 | 3,7 pp en `answer_correct` | no: por debajo del tamaño exigido |
| `temperatura-1.2` | 0,20 | 10/50 | 4,0 pp en `answer_correct` | no: por debajo del tamaño exigido |

## Cada meta en cada fase cerrada

| Fase | Meta | Valor | Cerrada | Artefacto |
|---|---|---|---|---|
| F1 | `G-ADOPTION` | lineas_de_diff=0, n_lineas=8 | 2026-09-12 | `evals/reports/gate-F1.json` |
| F1 | `G-FUNC-COV` | 0 | 2026-09-12 | `evals/reports/gate-F1.json` |
| F1 | `G-LINE-COV` | 100,00 | 2026-09-12 | `evals/reports/gate-F1.json` |
| F1 | `G-OPENAI-CONTRACT` | ratio=1,00, n=5 | 2026-09-12 | `evals/reports/gate-F1.json` |
| F2 | `G-ADOPTION` | lineas_de_diff=0, n_lineas=8 | 2026-09-20 | `evals/reports/gate-F2.json` |
| F2 | `G-DISCONNECT` | ratio=1, n=222 | 2026-09-20 | `evals/reports/gate-F2.json` |
| F2 | `G-FUNC-COV` | 0 | 2026-09-20 | `evals/reports/gate-F2.json` |
| F2 | `G-LINE-COV` | 98,70 | 2026-09-20 | `evals/reports/gate-F2.json` |
| F2 | `G-OPENAI-CONTRACT` | ratio=1,00, n=7 | 2026-09-20 | `evals/reports/gate-F2.json` |
| F2 | `G-TOKENS-EXACT` | ratio=1, n=5 | 2026-09-20 | `evals/reports/gate-F2.json` |
| F2 | `G-TOKENS-STREAM` | delta_con_usage=0 | 2026-09-20 | `evals/reports/gate-F2.json` |
| F3 | `G-ADOPTION` | lineas_de_diff=0, n_lineas=8 | 2026-10-06 | `evals/reports/gate-F3.json` |
| F3 | `G-DISCONNECT` | ratio=1, n=198 | 2026-10-06 | `evals/reports/gate-F3.json` |
| F3 | `G-FUNC-COV` | 0 | 2026-10-06 | `evals/reports/gate-F3.json` |
| F3 | `G-LAT-PROXY` | 5,29 | 2026-10-06 | `evals/reports/gate-F3.json` |
| F3 | `G-LAT-TTFT` | 3,51 | 2026-10-06 | `evals/reports/gate-F3.json` |
| F3 | `G-LINE-COV` | 99,34 | 2026-10-06 | `evals/reports/gate-F3.json` |
| F3 | `G-OPENAI-CONTRACT` | ratio=1,00, n=7 | 2026-10-06 | `evals/reports/gate-F3.json` |
| F3 | `G-OTEL-CONTRACT` | ratio=1, n=25 | 2026-10-06 | `evals/reports/gate-F3.json` |
| F3 | `G-TOKENS-EXACT` | ratio=1, n=5 | 2026-10-06 | `evals/reports/gate-F3.json` |
| F3 | `G-TOKENS-STREAM` | delta_con_usage=0 | 2026-10-06 | `evals/reports/gate-F3.json` |
| F3 | `G-TRACE-0` | perdidos=0, rps=50, servidas=6000 | 2026-10-06 | `evals/reports/gate-F3.json` |
| F3 | `G-TRACE-DEGRADE` | -0,08 | 2026-10-06 | `evals/reports/gate-F3.json` |
| F4 | `G-ADOPTION` | lineas_de_diff=0, n_lineas=8 | 2026-10-08 | `evals/reports/gate-F4.json` |
| F4 | `G-DISCONNECT` | ratio=1, n=209 | 2026-10-08 | `evals/reports/gate-F4.json` |
| F4 | `G-FUNC-COV` | 0 | 2026-10-08 | `evals/reports/gate-F4.json` |
| F4 | `G-LAT-PROXY` | 5,46 | 2026-10-08 | `evals/reports/gate-F4.json` |
| F4 | `G-LAT-TTFT` | 3,45 | 2026-10-08 | `evals/reports/gate-F4.json` |
| F4 | `G-LINE-COV` | 99,35 | 2026-10-08 | `evals/reports/gate-F4.json` |
| F4 | `G-MUTATION` | 88,58 | 2026-10-08 | `evals/reports/gate-F4.json` |
| F4 | `G-OPENAI-CONTRACT` | ratio=1,00, n=7 | 2026-10-08 | `evals/reports/gate-F4.json` |
| F4 | `G-OTEL-CONTRACT` | ratio=1, n=25 | 2026-10-08 | `evals/reports/gate-F4.json` |
| F4 | `G-PRICE-REPRO` | 0,00 | 2026-10-08 | `evals/reports/gate-F4.json` |
| F4 | `G-TOKENS-EXACT` | ratio=1, n=5 | 2026-10-08 | `evals/reports/gate-F4.json` |
| F4 | `G-TOKENS-STREAM` | delta_con_usage=0 | 2026-10-08 | `evals/reports/gate-F4.json` |
| F4 | `G-TRACE-0` | perdidos=0, rps=50, servidas=6000 | 2026-10-08 | `evals/reports/gate-F4.json` |
| F4 | `G-TRACE-DEGRADE` | -0,17 | 2026-10-08 | `evals/reports/gate-F4.json` |
| F5 | `G-ADOPTION` | lineas_de_diff=0, n_lineas=8 | 2026-10-08 | `evals/reports/gate-F5.json` |
| F5 | `G-CACHE-HIT` | 0,00 | 2026-10-08 | `evals/reports/gate-F5.json` |
| F5 | `G-CACHE-INVAL` | ratio=1, n=63 | 2026-10-08 | `evals/reports/gate-F5.json` |
| F5 | `G-DISCONNECT` | ratio=1, n=212 | 2026-10-08 | `evals/reports/gate-F5.json` |
| F5 | `G-FUNC-COV` | 0 | 2026-10-08 | `evals/reports/gate-F5.json` |
| F5 | `G-LAT-PROXY` | 6,63 | 2026-10-08 | `evals/reports/gate-F5.json` |
| F5 | `G-LAT-TTFT` | 3,96 | 2026-10-08 | `evals/reports/gate-F5.json` |
| F5 | `G-LINE-COV` | 99,35 | 2026-10-08 | `evals/reports/gate-F5.json` |
| F5 | `G-MUTATION` | 88,58 | 2026-10-08 | `evals/reports/gate-F5.json` |
| F5 | `G-OPENAI-CONTRACT` | ratio=1,00, n=7 | 2026-10-08 | `evals/reports/gate-F5.json` |
| F5 | `G-OTEL-CONTRACT` | ratio=1, n=25 | 2026-10-08 | `evals/reports/gate-F5.json` |
| F5 | `G-PRICE-REPRO` | 0,00 | 2026-10-08 | `evals/reports/gate-F5.json` |
| F5 | `G-TOKENS-EXACT` | ratio=1, n=5 | 2026-10-08 | `evals/reports/gate-F5.json` |
| F5 | `G-TOKENS-STREAM` | delta_con_usage=0 | 2026-10-08 | `evals/reports/gate-F5.json` |
| F5 | `G-TRACE-0` | perdidos=0, rps=50, servidas=6000 | 2026-10-08 | `evals/reports/gate-F5.json` |
| F5 | `G-TRACE-DEGRADE` | -0,20 | 2026-10-08 | `evals/reports/gate-F5.json` |
| F6 | `G-ADOPTION` | lineas_de_diff=0, n_lineas=8 | 2026-10-08 | `evals/reports/gate-F6.json` |
| F6 | `G-CACHE-HIT` | 0,00 | 2026-10-08 | `evals/reports/gate-F6.json` |
| F6 | `G-CACHE-INVAL` | ratio=1, n=63 | 2026-10-08 | `evals/reports/gate-F6.json` |
| F6 | `G-DETERMINISM` | ratio=1, n=3 | 2026-10-08 | `evals/reports/gate-F6.json` |
| F6 | `G-DISCONNECT` | ratio=1, n=217 | 2026-10-08 | `evals/reports/gate-F6.json` |
| F6 | `G-FUNC-COV` | 0 | 2026-10-08 | `evals/reports/gate-F6.json` |
| F6 | `G-LAT-PROXY` | 6,97 | 2026-10-08 | `evals/reports/gate-F6.json` |
| F6 | `G-LAT-TTFT` | 3,80 | 2026-10-08 | `evals/reports/gate-F6.json` |
| F6 | `G-LINE-COV` | 99,35 | 2026-10-08 | `evals/reports/gate-F6.json` |
| F6 | `G-MUTATION` | 88,58 | 2026-10-08 | `evals/reports/gate-F6.json` |
| F6 | `G-OPENAI-CONTRACT` | ratio=1,00, n=7 | 2026-10-08 | `evals/reports/gate-F6.json` |
| F6 | `G-OTEL-CONTRACT` | ratio=1, n=25 | 2026-10-08 | `evals/reports/gate-F6.json` |
| F6 | `G-PRICE-REPRO` | 0,00 | 2026-10-08 | `evals/reports/gate-F6.json` |
| F6 | `G-TOKENS-EXACT` | ratio=1, n=5 | 2026-10-08 | `evals/reports/gate-F6.json` |
| F6 | `G-TOKENS-STREAM` | delta_con_usage=0 | 2026-10-08 | `evals/reports/gate-F6.json` |
| F6 | `G-TRACE-0` | perdidos=0, rps=50, servidas=6000 | 2026-10-08 | `evals/reports/gate-F6.json` |
| F6 | `G-TRACE-DEGRADE` | 0,08 | 2026-10-08 | `evals/reports/gate-F6.json` |
