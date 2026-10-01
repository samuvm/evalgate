# ADR-004 · Evalgate frente a Langfuse v4: no es una plataforma de observabilidad

**Fecha:** 2026-09-10
**Fase:** F0
**Estado:** **aceptado**

---

## Contexto

Según la investigación previa (`docs/adr/000-plantilla.md`, datos **no verificados en este ADR**),
ClickHouse compró Langfuse en enero de 2026 y Langfuse v4 incorpora *experiment gates* en CI. Evalgate
también traza en ClickHouse y también decide en CI. Sin este ADR, el repositorio se lee como "reescribí
Langfuse".

## Opciones consideradas

| Opción | A favor | En contra | Coste estimado |
|---|---|---|---|
| **A · Plataforma completa** (UI, anotación, usuarios) | Comparable función a función | Fuera de alcance (`PROJECT.md` §2); se pierde contra un producto con equipo | +200 h |
| **B · Integrarse en Langfuse** (exportar y usar sus gates) | Menos código | Sus gates no publican su propia tasa de falsos positivos ni su efecto mínimo detectable: la tesis desaparece | 10-20 h |
| **C · Una puerta que publica sus propias tasas de error, más la contabilidad que la alimenta** | Es el 20 % que ninguna plataforma da llave en mano | No hay UI; el panel (F8) es ampliación | Plan actual |

## Decisión

Se elige **C**. Lo que Evalgate añade no es ver trazas: es poder decir **cuánto se equivoca la puerta**.
Publica la tasa de falsos positivos con su intervalo de Wilson y `n ≥ 49` (`G-GATE-FP`), el efecto mínimo
que es capaz de ver (`G-GATE-MDE`), su potencia frente a cuatro degradaciones fijadas (`G-GATE-POWER`) y la
concordancia del juez con un humano (`G-JUDGE-KAPPA`, `n ≥ 100`). Además, bootstrap siempre pareado y
corrección de Holm (R8). **Se descartó integrarse en una plataforma existente aunque sea lo que haría un
equipo con prisa, porque ninguna publica esas tres tasas y sin ellas un gate es un adorno.**

## Consecuencias

- **Lo que gana:** una tesis defendible en una entrevista con números propios.
- **Lo que cuesta:** no hay interfaz de anotación; el etiquetado de Q-004 se hace por consola.
- **Qué habría que ver para revertirla:** que Langfuse u otra plataforma publique FP, MDE y potencia de sus
  gates con protocolo equivalente. Entonces el argumento pasa a ser solo la contabilidad (ADR-003).
- **Qué se toca si se revierte:** `README.md` (posicionamiento) y la prioridad de F7 frente a F8.
