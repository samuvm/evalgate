# ADR-002 · LiteLLM nunca como proxy; como librería, solo si hace falta un proveedor no compatible

**Fecha:** 2026-09-10
**Fase:** F0
**Estado:** **aceptado**

---

## Contexto

El planteamiento inicial admitía "FastAPI **o** LiteLLM como base". Se decidió el 2026-09-10 que el
servidor proxy es propio y que LiteLLM entra, como mucho, como librería de adaptadores de salida. Dos hechos
aprietan la decisión: (1) LiteLLM sufrió un ataque de cadena de suministro confirmado en marzo de 2026
(versiones 1.82.7 y 1.82.8 en PyPI, robo de credenciales); (2) el proyecto usa solo modelos locales, sin
clave de API de pago: hoy todo el tráfico de salida va a Ollama, que expone `/v1/chat/completions`.

## Opciones consideradas

| Opción | A favor | En contra | Coste estimado |
|---|---|---|---|
| **A · Proxy de LiteLLM** | Casi nada que escribir | El repo pasa a ser configuración: desaparecen streaming y contabilidad ante desconexión, que son el mérito; su telemetría colisiona con la nuestra | −8-12 h |
| **B · LiteLLM como librería desde ya** | Muchos proveedores gratis | Superficie de dependencias grande y con historial de compromiso, para usar hoy un solo proveedor | 2-4 h |
| **C · `OpenAICompatProvider` propio sobre `httpx`; LiteLLM solo cuando haga falta un proveedor no compatible** | Superficie mínima; cubre Ollama, llama.cpp, vLLM y LM Studio con un adaptador | Si llega un proveedor de pago no compatible, hay que añadir la dependencia entonces | 3-5 h |

## Decisión

Se elige **C**, y **A queda descartada sin excepción**. Con un único proveedor de salida compatible con
OpenAI, importar LiteLLM sería ampliar la superficie confiada (con el precedente de marzo de 2026) sin usar
ninguna de sus funciones. El día que se active un proveedor que no hable el protocolo de OpenAI (por
ejemplo, Bedrock), un ADR nuevo supersede a este y lista **exactamente** qué funciones de `litellm` se
usan, con `==` y hash (R18).

## Consecuencias

- **Lo que gana:** cero dependencias de LiteLLM hoy; el proxy, el streaming y la contabilidad son propios y
  enseñables.
- **Lo que cuesta:** el README dirá "habla con cualquier runtime compatible con OpenAI", no "con cualquier
  proveedor".
- **Qué habría que ver para revertirla:** que se active un proveedor de pago no compatible con OpenAI.
- **Qué se toca si se revierte:** `src/evalgate/providers/`, `pyproject.toml` (`litellm` con `==` y hash),
  y un ADR nuevo con la lista de funciones.
