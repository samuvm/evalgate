# ADR-003 · Evalgate frente a Bifrost: la latencia no es el argumento

**Fecha:** 2026-09-10
**Fase:** F0
**Estado:** **aceptado**

---

## Contexto

Existen pasarelas de LLM escritas en Go. Según la investigación previa del proyecto
(`docs/adr/000-plantilla.md`, dato **no medido aquí**), Bifrost declara unos 11 µs de sobrecarga a
5.000 rps. Evalgate es Python 3.12 (ADR-001) y sus metas de latencia son `G-LAT-PROXY` (p95 ≤ 30 ms,
no-streaming) y `G-LAT-TTFT` (p95 ≤ 15 ms sobre el tiempo hasta el primer token): tres órdenes de magnitud
por encima. Sin este ADR, el repo se leería como "una pasarela lenta".

## Opciones consideradas

| Opción | A favor | En contra | Coste estimado |
|---|---|---|---|
| **A · Competir en latencia** (reescribir el camino caliente en Go o Rust) | Números de escaparate | Otro lenguaje, otro proyecto; se abandona lo que ninguna pasarela da | +60-100 h |
| **B · Acotar la latencia y competir en lo que se mide** | Coherente con la tesis; las metas de latencia son cotas con protocolo, no una carrera | Hay que explicarlo, y un lector apresurado verá "30 ms" | 0 h |
| **C · Montar Evalgate encima de Bifrost** | Latencia regalada | Streaming y contabilidad ajenos: el mérito desaparece (mismo argumento que ADR-002 A) | 10-20 h |

## Decisión

Se elige **B**. Una pasarela rápida que cuenta mal los tokens de un cliente desconectado, o una puerta que
bloquea por ruido, no se salva por su p95. El argumento de Evalgate son tres números que ninguna pasarela
publica: la contabilidad exacta ante desconexión (`G-DISCONNECT`), la reproducibilidad del coste con tablas
fechadas (`G-PRICE-REPRO`) y la meta-evaluación de la propia puerta (`G-GATE-FP`, `G-GATE-MDE`,
`G-GATE-POWER`, `G-JUDGE-KAPPA`). **Se descartó competir en latencia aunque sea la métrica que primero se
mira, porque en Python se pierde y porque no es lo que el proyecto defiende.**

## Consecuencias

- **Lo que gana:** el esfuerzo va a los diferenciadores; la latencia se acota, se mide con protocolo
  (`docs/bench/protocol.md`) y se publica con su hardware.
- **Lo que cuesta:** el README tiene que decir en la primera pantalla qué es y qué no es Evalgate.
- **Qué habría que ver para revertirla:** que `G-LAT-PROXY` falle con el protocolo cumplido y el perfil
  apunte al intérprete, no al diseño.
- **Qué se toca si se revierte:** `src/evalgate/proxy/` completo y ADR-001.
