# Bloqueos de la puerta

Evidencia de `G-GATE-BLOCK-EVIDENCE`: regresiones reales que la puerta bloqueó, con la tabla antes/después,
la decisión y el punto al que se volvió. `scripts/check_block_evidence.py` cuenta las entradas cuyo título
dice `BLOQUEO DE LA PUERTA` y que traen la tabla, la línea `Decisión de la puerta: BLOCK` y un snapshot que
existe. Los snapshots (`.snapshots/`) son locales: en un clon, la comprobación cuenta 0.

## 2026-10-13 · BLOQUEO DE LA PUERTA · regresión inyectada en el propio repo y revertida

La puerta que juzga es la del propio repositorio (`evalgate eval self-gate`, R16), sobre el commit `577e1c7`.

**Regresión inyectada.** Las salidas grabadas del sistema base de `rag-app-v2`
(`evals/suites/rag-app-v2/sut/base.jsonl`) se sustituyeron por las de la degradación `contexto-50`: el
mismo sistema respondiendo con la mitad del contexto recuperado. Es un cambio real, grabado con sus 200
veredictos, no un número editado.

**Comando.** `evalgate eval self-gate --suite rag-app-v2` → exit 1. n = 200 casos (160 en las métricas que
excluyen negativos). Bootstrap pareado, 10.000 réplicas, semilla 42, sin corrección (tres bloqueantes).

| Métrica | Antes | Después | Delta | IC95 del delta | Veredicto |
|---|---|---|---|---|---|
| `answer_correct` | 0,900 | 0,635 | −0,265 | [−0,330, −0,205] | BLOQUEA |
| `context_recall` | 1,000 | 1,000 | 0,000 | [0,000, 0,000] | ok |
| `abstencion_incorrecta` | 0,000 | 0,381 | +0,381 | [+0,306, +0,456] | BLOQUEA |
| `faithfulness` (solo informa) | 0,905 | 0,645 | −0,260 | [−0,330, −0,190] | solo informa |

Decisión de la puerta: **BLOCK**
Snapshot: `.snapshots/2026-10-08-fase6`

"Antes" es el informe publicado, `evals/reports/rag-app-v2.json`. El snapshot es el último verde (F6); el
estado exacto de "antes" es el commit `577e1c7`, que es adonde se volvió.

**`make gate-fast`** también dio rojo, y antes de llegar a R16: `make test-fast` falló en el test de la kappa
("t1-06 ya no es lo que se etiquetó: las salidas grabadas del sistema han cambiado"). Dos defensas distintas
vieron el mismo cambio; la que da la tabla de arriba es la puerta.

**Revertido** con `git checkout -- evals/suites/rag-app-v2/sut/base.jsonl`; después, `self-gate` → PASS.
