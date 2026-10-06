# ADR-013 · Tablas de precios inmutables y fechadas, con coste exacto hasta presentar

**Fecha:** 2026-10-06
**Fase:** F4
**Estado:** aceptado

---

## Contexto

Los proveedores cambian precios. Si el coste se calcula con "la tabla de hoy", un informe de hace tres
meses da un número distinto cada vez que se recalcula y deja de servir como informe. El contrato
`pricing-table.md` fija el formato (`pricing/<AAAA-MM-DD>.yaml`, resolución por el `effective_from` más
reciente ≤ t) y RULES fija dos invariantes: ningún precio en el código (R3) y una tabla publicada no se edita
(R4). Quedaban por decidir cinco cosas que el contrato no cierra y que cambian el número publicado.

## Opciones consideradas

| Decisión | Elegida | Descartada, y por qué |
|---|---|---|
| **Aritmética** | `Decimal` de punta a punta; un único redondeo en `presented` (§3.5) | `float`: 0,1 + 0,2 ≠ 0,3, y "lote = suma de las partes" deja de ser exacta. Redondear por llamada: tres llamadas de 0,004 € suman 0,00 € en vez de 0,01 € |
| **Lectura del YAML** | Cada escalar como texto (`BaseLoader`), directo a `Decimal` | `safe_load`: convierte `0.0008` en float antes de que nadie lo vea. `jsonschema` en ejecución: es dependencia de desarrollo; un test de contrato mantiene de acuerdo al cargador y al esquema |
| **Qué es "publicada"** | Sellada a mano en `TABLES.lock`; el cargador comprueba el sha256 **antes** de leer y rechaza editada, borrada o sin sellar | Confiar en la revisión: el día que alguien "corrige una errata" en una tabla vieja, todos los informes anteriores cambian sin dejar rastro |
| **Lo que no tiene precio** | Modelo o fecha sin tabla → `None`; periodo con una llamada así → error; caché sin precio de caché → error; local a 0 → **0** | Tratar lo desconocido como 0: publica un coste menor que la factura y lo llama exacto. 0 es un precio; `None` es "nadie lo sabe" |
| **Moneda** | La tabla declara moneda y tipo de cambio con fecha; USD sin `fx` se rechaza; EUR no aplica cambio | Un tipo por defecto en el código: es un precio en el código (R3) y hace irreproducibles los euros |

## Decisión

Se eligen las cinco de la columna central. Lo que decanta es una sola idea: **ante un dato que falta, el
paquete se niega; nunca supone.** Un coste es un número que alguien va a comparar con una factura, y un
supuesto silencioso es indistinguible de un dato.

Tres límites conocidos, escritos para que no se descubran tarde:

1. **Clave del modelo.** `price_at` (F0, cubierto por la suite reservada) resuelve por `id` a secas; el esquema
   admite el mismo `id` en dos regiones. Hoy el cargador **rechaza** esa tabla en vez de elegir una región
   en silencio. Cuando haga falta, la clave pasa a `(provider, id, region)` con un ADR que supersede a este.
2. **Tokens de caché del tráfico.** El cálculo los valora; el proxy todavía no los lee del bloque `usage`
   del proveedor (Ollama no los emite). Hasta entonces el coste trazado de un proveedor con caché los
   contaría como entrada normal. No afecta a lo local, que vale 0.
3. **LiteLLM no entra** (ADR-002): con solo modelos locales el único proveedor es compatible con OpenAI y
   no hace falta ningún adaptador. Una dependencia menos, y una con un ataque de cadena de suministro
   reciente.

Corpus de `G-PRICE-REPRO`: 12 informes **sintéticos y declarados**, con tablas propias que copian el ejemplo
del contrato y totales calculados a mano y comprobados con fracciones, sin usar el código medido. Un total
que saliera de `cost_of` daría cero por construcción. Medido: **0 € de diferencia, 12 de 12.**

La primera tabla real (`2026-10-06`) lleva Claude Haiku 4.5 a precio de lista como referencia del "coste
declarado" (contrato §4), los modelos locales a 0 y el cambio del BCE del día. La caché de escritura es la
de 5 minutos: el contrato tiene un solo campo y la de 1 hora no cabe.

## Consecuencias

- **Lo que gana:** un informe de coste antiguo se recalcula al céntimo, y si no se puede, falla diciendo
  por qué.
- **Lo que cuesta:** publicar una tabla exige un paso humano (sellarla). Es deliberado: es el punto donde
  alguien responde de los números.
- **Qué habría que ver para revertirla:** un segundo proveedor con el mismo `id` de modelo en dos regiones
  (límite 1), o precios por tramos de volumen, que este formato no expresa.
- **Qué se toca si se revierte:** `pricing/model.py` (clave), `pricing/loader.py` y el esquema de
  `docs/spec/`. El corpus de `pricing-repro` no se toca nunca: es la prueba de que nada cambió.
