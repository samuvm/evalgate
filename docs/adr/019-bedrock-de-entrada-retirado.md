# ADR-019 · Endpoint de entrada compatible con Bedrock: retirado del alcance

**Fecha:** 2026-10-13
**Fase:** F9 (la decisión es de F0, RULES §3.3 y §6; este ADR la deja cerrada)
**Estado:** aceptado.

---

## Contexto

El planteamiento inicial pedía dos endpoints de entrada: uno compatible con el protocolo de OpenAI y otro con el de
Bedrock. El de OpenAI existe y es por donde entra toda la adopción (`G-ADOPTION`: cero líneas de diff con
solo cambiar `OPENAI_BASE_URL`).

Servir Bedrock de entrada no es añadir una ruta. Un cliente de Bedrock firma cada petición con SigV4 y
espera el flujo en `application/vnd.amazon.eventstream`, un formato binario con sus propios CRC.

## Opciones consideradas

| Opción | A favor | En contra |
|---|---|---|
| **A · Retirarlo; Bedrock solo como proveedor de salida** | El proyecto conserva lo que lo distingue (contabilidad, precios, puerta medida) | El README no puede decir "compatible con Bedrock" de entrada |
| **B · Implementarlo** | Cumple el planteamiento inicial | 20-40 h estimadas en RULES §6, sin valor narrativo frente al endpoint de OpenAI; verificar SigV4 es código de seguridad que habría que testear como tal; sin cuenta AWS no se puede probar contra el servicio real |
| **C · Un endpoint que acepte la forma pero no la firma** | Barato | Es decir "compatible" de algo que no lo es |

## Decisión

Se elige **A**. Evalgate no sirve ningún endpoint de entrada con el protocolo de Bedrock. Bedrock queda
como destino de salida posible a través de los adaptadores de LiteLLM usado como librería (ADR-002).

## Consecuencias

- El README dice "endpoint compatible con OpenAI" y no menciona Bedrock como entrada.
- **Tampoco la salida a Bedrock está probada:** el proyecto no usa cuenta AWS y solo usa modelos locales.
  Todo lo medido en este repo es contra Ollama. El README no afirma que Bedrock funcione.
- Una aplicación que hable el protocolo de Bedrock no puede adoptar evalgate cambiando una variable.
- Reabrirlo es un cambio de alcance, con su propio ADR.
