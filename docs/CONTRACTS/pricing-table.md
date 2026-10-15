# Contrato · tabla de precios con fecha de vigencia

> La construye evalgate y la necesita cualquier métrica de coste o de ahorro en euros. Se copia;
> no se importa.
>
> Sin ella, un ahorro "medido en euros" no se puede calcular de forma reproducible.
>
> **Versión del contrato: 1**

---

## 1. Por qué la fecha de vigencia no es un detalle

Los proveedores cambian precios. **Un informe de coste de hace tres meses debe seguir siendo
reproducible con los precios de entonces.** Si la tabla no tiene vigencia, cada recálculo da un
número distinto y ningún informe histórico vale nada.

Es un detalle pequeño y es exactamente de las cosas que distinguen a alguien que ha operado
esto de verdad de alguien que lo ha leído.

---

## 2. Formato

`pricing/YYYY-MM-DD.yaml`. Un fichero por fecha de vigencia, **nunca se edita uno pasado**.

```yaml
effective_from: 2026-08-01
source: https://aws.amazon.com/bedrock/pricing/   # URL consultada
retrieved_at: 2026-08-08
currency: USD
fx:
  USD_EUR: 0.92          # tipo usado, con su fecha. Sin esto los euros no son reproducibles
  fx_date: 2026-08-08

models:
  - id: anthropic.claude-haiku-4-5
    provider: aws.bedrock
    region: eu-west-1
    input_per_1k: 0.0008
    output_per_1k: 0.004
    cache_write_per_1k: 0.001
    cache_read_per_1k: 0.00008

  - id: qwen3.5:9b-mlx
    provider: ollama
    region: local
    input_per_1k: 0.0
    output_per_1k: 0.0
    note: "Coste real incurrido = 0. Ver §4."
```

Resolución: para un uso con fecha `t`, se aplica el fichero con el `effective_from` **más
reciente que sea ≤ t**. Nunca el actual.

---

## 3. Reglas de cálculo

Casos que un test de tabla debe cubrir, con el resultado calculado a mano:

1. Modelos con precio distinto de entrada y de salida.
2. **Cambio de tarifa a mitad de periodo**: un informe mensual que cruza una frontera de
   vigencia usa cada tramo con su tabla.
3. **Caché de prompt con descuento**: escritura y lectura tienen precios propios.
4. **Cliente que se desconecta a mitad del stream**: esos tokens ya se han pagado y **se
   contabilizan igual**. Es el caso que casi nadie implementa y medio mérito del proxy.
5. Redondeo: se acumula en la unidad más pequeña y se redondea solo al presentar.

Propiedades verificables con Hypothesis: el coste nunca es negativo; añadir tokens nunca reduce
el coste; el coste de un lote es la suma de sus partes.

---

## 4. Las dos métricas de coste que hay que separar

Una meta como "ahorro incremental ≥ 90 % medido en euros" **vale 0 € con Ollama local**, y no se
puede medir con un stack local por defecto.

Se resuelve publicando **dos columnas, siempre**:

| Columna | Qué es |
|---|---|
| **Coste declarado** | Tokens reales × tabla de precios de un proveedor de pago, con fecha. Es lo que costaría en producción. Automatizable, determinista, comparable |
| **Coste real incurrido** | Lo que se ha gastado de verdad. En local, 0 € |

Publicar solo la primera es engañoso. Publicar solo la segunda hace la métrica inútil. Las dos
juntas son honestas y siguen contando la historia: *"procesar 1.000 documentos costaría 4,20 €
en Bedrock; el incremental lo baja a 0,31 €. En local no me costó nada, pero el ahorro es real
y así lo he medido."*

El **tiempo de reloj** se publica siempre junto al coste. Es la métrica que no depende de
ninguna tabla de precios.

---

## 5. La validación del 1 % contra factura real: reformulada

Pedir "error ≤ 1 % contra la factura real del proveedor" como criterio de aceptación de una fase
**es inviable dentro del timebox**: exige cuenta de pago,
treinta días naturales de tráfico y volumen suficiente para que el redondeo no domine — con
menos de 20-50 € de gasto, el error de cuantización supera por sí solo el 1 %. Solo la espera
de calendario ya excede la fase entera.

Se parte en dos métricas, y ambas son honestas:

1. **Automatizable y bloqueante:** error ≤ 0,5 % contra el bloque `usage` que devuelve el propio
   proveedor, multiplicado por la tabla de precios vigente. Determinista, corre en cada
   ejecución, no cuesta nada.
2. **Evidencia puntual, no bloqueante:** una conciliación manual contra una factura real de 3-5
   días con 5-10 € de gasto, publicada **con su delta honesto**, sea cual sea. Requiere una
   cuenta de pago y un gasto autorizado, declarados como recurso externo de la meta.

La primera es la que corre siempre. La segunda es la que se enseña.
