# Constitución · gobierno común a los cinco proyectos

> Documento normativo. Se aplica igual a `citebound-01`, `evalgate-02`, `data-warden-03`,
> `indexkeeper-04` y `genai-infra-05`. Cada proyecto añade detalle en su `docs/RULES.md`;
> ninguno puede contradecir esto.
>
> **Se copia, no se enlaza.** Cada proyecto tiene su propia copia en `docs/CONSTITUCION.md`.
> Copiar 300 líneas es barato; crear una dependencia entre los cinco repos rompe la regla
> número uno del mapa de conjunto.

---

## 0. Premisa: tres capas con garantías distintas

| Capa | Mecanismo | ¿Garantiza? |
|---|---|---|
| **Persuasión** | `CLAUDE.md`, `.claude/rules/`, skills | No. Es contexto, no configuración |
| **Ejecución** | `hooks` con `exit 2` / `permissionDecision: deny` | Sí. Corre decida lo que decida el modelo |
| **Permisos** | `permissions.deny` en `settings.json` | Sí, sobre herramientas de fichero y Bash reconocido |

**Consecuencia:** *el gate no vive en el documento de reglas. Vive en hooks y permisos. El
documento explica por qué; el hook lo impone.*

**Primera regla de oro:** el agente nunca puede editar a su propio guardián. Los hooks
bloqueantes, los umbrales y los tests de reserva viven **fuera del directorio del proyecto**,
en `~/.claude/gates/`, y están en `deny`.

**Segunda regla de oro:** *el agente puede cambiar cómo llega al número; nunca puede cambiar
el número.*

**Tercera regla de oro:** *nada que dependa de datos, cuentas, dinero, criterio legal o
decisión de negocio se decide sin Samuel.* No se elige por él, no se asume por él, no se
inventa un sustituto. Se declara en `docs/PARA-SAMUEL.md` con qué es, por qué hace falta, en
qué fase bloquea y qué opciones hay. El agente pregunta cuando toca y sigue con otra tarea
mientras espera.

---

## 1. Anatomía de ficheros de gobierno

### 1.1 El conjunto mínimo suficiente

| # | Fichero | Quién escribe | Tope | Para qué existe |
|---|---|---|---|---|
| 1 | `CLAUDE.md` (raíz) | **Humano** | **≤ 120 líneas, duro** | Lo que el agente necesita en **toda** sesión: comandos, invariantes, punteros. Se recarga tras `/compact` |
| 2 | `docs/PROJECT.md` | **Humano** | libre | La especificación. **Solo lectura para el agente** |
| 3 | `docs/GOALS.yaml` | **Humano** | libre | Metas ejecutables: umbral, comando de medida, artefacto, `bloqueante_desde_fase`. **Solo lectura** |
| 4 | `docs/PLAN.md` | **Humano** | libre | Fases con entregable, comando de salida y timebox. Marca núcleo vs ampliación. **Solo lectura** |
| 5 | `docs/RULES.md` | **Humano** | libre | Invariantes propias del proyecto, dónde TDD es obligatorio y dónde está prohibido. **Solo lectura** |
| 6 | `.claude/state/STATE.md` | **Agente** | **≤ 80 líneas, duro** | Dónde estoy, qué hago, qué está bloqueado. Los campos de verificación los escribe el gate |
| 7 | `docs/JOURNAL.md` | **Agente**, append | libre | Qué se intentó, qué falló, qué número salió. La memoria contra repetir errores |
| 8 | `docs/adr/NNN-titulo.md` | **Agente** | ~40 líneas | Decisiones no obvias: contexto, opciones, elección, consecuencias |
| 9 | `docs/PARA-SAMUEL.md` | **Agente**, append | libre | **Buzón humano único.** Preguntas y propuestas. El canal de parada |
| 10 | `CHANGELOG.md` | **Agente**, al cerrar fase | libre | Una entrada por fase, con los números medidos |
| — | `docs/CONTRACTS/` | **Nadie** | — | **Copias literales de `_comun/CONTRACTS/`.** Inmutables. Un `diff` contra el original es un test |
| — | `docs/spec/` | **Humano** | libre | Contratos **propios** del proyecto (esquemas internos, políticas). Aquí sí se escribe |
| — | `.claude/rules/*.md` | **Agente vía skill** | ≤ 60 líneas c/u | Detalle con `paths:` en frontmatter. Carga diferida |

**Solo dos topes son duros: `CLAUDE.md` y `STATE.md`.** Ambos entran en el contexto en toda
sesión, y ahí cada línea compite con el trabajo. Los demás documentos se leen bajo demanda: un
`GOALS.yaml` de 300 líneas con 25 metas, cada una con su comando exacto, es mejor que uno de 80
con métricas en prosa. La restricción que importa no es la longitud, es que **ninguna meta sea
prosa y ninguna regla sea decorativa**.

**`docs/CONTRACTS/` frente a `docs/spec/`.** Es la distinción que evita el error de tratar como
inmutable algo que el proyecto tiene que escribir. `CONTRACTS/` son copias de `_comun/` y están
en `deny`: cambiarlas es cambiar un contrato compartido, y eso se hace en `_comun/` y se propaga
a mano. `spec/` es donde viven los esquemas propios del proyecto —una política de validación, el
formato de un registro de auditoría— y se escribe con normalidad.

Dos ficheros los escribe **solo el gate**; el agente los lee pero no los edita:
`.claude/state/gate-status.json` y `.claude/state/test-inventory.json`. **Ninguno de los dos
existe hasta el primer `make done`**: toda instrucción que mande leerlos dice "si existe".

### 1.2 Qué se ha descartado y por qué

| Descartado | Motivo |
|---|---|
| `PROGRESS.md` / `TODO.md` | Duplica `STATE.md`. Dos fuentes de verdad sobre el progreso es peor que ninguna |
| `OPEN-QUESTIONS.md` aparte | Dos buzones = uno se ignora. Fusionado en `PARA-SAMUEL.md`: un solo sitio que abrir, una sola convención |
| `decisions.log` | Lo cubren `JOURNAL.md` (cronológico) y `docs/adr/` (razonado) |
| `TESTABLE.md` | La lista de paquetes con TDD obligatorio va en `pyproject.toml [tool.gate]`, porque **la lee un script**, no un humano |
| `README.md` como gobierno | El README es el escaparate, no el contrato. Se escribe al cerrar cada fase y no gobierna nada |

---

## 2. El gate de QA bloqueante

### 2.1 Qué exige exactamente

Decisión de Samuel, literal: **para avanzar de fase o guardar el proyecto hay que pasar todo,
incluida integración.** No hay avance con la suite en rojo, ni parcialmente.

| Capa | Cuándo | ¿Bloquea? | Qué corre | Presupuesto |
|---|---|---|---|---|
| **0 · Inmutabilidad** | siempre | Sí, total | `permissions.deny` | 0 s |
| **A · Feedback** | `PostToolUse` (Edit/Write) | No — informa | Test del módulo tocado | ≤ 5 s |
| **B · Paso** | `PostToolBatch` | **Sí** | `make gate-fast`, con debounce por hash | ≤ 25 s |
| **C · Turno** | `Stop` | **Sí** | `make gate-fast` + contrato | ≤ 3 min |
| **D · Tarea** | `TaskCompleted` | **Sí** | `make gate-fast` | ≤ 25 s |
| **E · Avanzar / guardar** | `make done` | **Sí** | **Todo: estáticos, unitarios, propiedad, contrato, integración, holdout, mutación, metas** | ≤ 20 min |

La capa E es la que responde al encargo. Las A–D existen solo para que el agente no llegue a
la E con cuarenta fallos acumulados; **no la sustituyen ni la relajan**.

**El error técnico que hay que evitar:** `PostToolUse` **no puede bloquear**. La herramienta ya
se ejecutó cuando el hook corre; `exit 2` solo muestra el aviso. Todos los tutoriales que dicen
"pon PostToolUse tras Edit y bloqueas el guardado" describen algo que no ocurre. El bloqueo real
está en `PreToolUse`, `PostToolBatch`, `Stop` y `TaskCompleted`.

### 2.2 El gate no depende de git, y está listo para él

El gate es un **target de Makefile que devuelve 0 o distinto de 0**. Los hooks lo invocan. El
día que hagas `git init`, `pre-commit` invocará el mismo target y no cambiará ni una línea.

Mientras tanto, el punto de retorno que daría git se sustituye por:

- **`.snapshots/<fecha>-fase<N>/`** — copia de `src/`, `tests/`, `docs/`, `pyproject.toml`,
  `uv.lock` y un `MANIFEST.sha256`. La crea `scripts/save.sh` **solo si `make done` pasa**.
  Está en `deny` de edición.
- **`/rewind`** (Esc Esc) para deshacer dentro de la sesión.

Y los criterios de aceptación que exigían historial (el PR bloqueado del 02, la eval revertida
del 01) se cumplen mientras tanto como **evidencia en `JOURNAL.md`**: la tabla antes/después
del cambio revertido, con su snapshot correspondiente. Es la misma evidencia y sigue siendo
demostrable en una entrevista. Cuando entre git, se convierten en lo que decían los documentos.

### 2.3 `settings.json` de referencia

Vive en `~/.claude/settings.json`, **fuera** de los proyectos: por eso el agente no puede
tocarlo. **No está instalado.** Se copia cuando decidas activar el gate, siguiendo el orden
de §9.

```json
{
  "permissions": {
    "deny": [
      "Read(//Users/samuelviciana/Documents/day-300/*/tests/holdout/**)",
      "Edit(//Users/samuelviciana/Documents/day-300/*/tests/holdout/**)",
      "Write(//Users/samuelviciana/Documents/day-300/*/tests/holdout/**)",

      "Edit(//Users/samuelviciana/Documents/day-300/*/docs/PROJECT.md)",
      "Edit(//Users/samuelviciana/Documents/day-300/*/docs/GOALS.yaml)",
      "Edit(//Users/samuelviciana/Documents/day-300/*/docs/PLAN.md)",
      "Edit(//Users/samuelviciana/Documents/day-300/*/docs/RULES.md)",
      "Edit(//Users/samuelviciana/Documents/day-300/*/docs/CONSTITUCION.md)",
      "Edit(//Users/samuelviciana/Documents/day-300/*/docs/STACK.md)",
      "Edit(//Users/samuelviciana/Documents/day-300/*/docs/CONTRACTS/**)",
      "Write(//Users/samuelviciana/Documents/day-300/*/docs/CONTRACTS/**)",

      "Edit(//Users/samuelviciana/Documents/day-300/*/thresholds.lock)",
      "Write(//Users/samuelviciana/Documents/day-300/*/thresholds.lock)",
      "Edit(//Users/samuelviciana/Documents/day-300/*/*.lock)",
      "Edit(//Users/samuelviciana/Documents/day-300/*/.claude/state/*.json)",
      "Edit(//Users/samuelviciana/Documents/day-300/*/.snapshots/**)",

      "Edit(//Users/samuelviciana/Documents/day-300/citebound-01/corpus/raw/**)",
      "Write(//Users/samuelviciana/Documents/day-300/citebound-01/corpus/raw/**)",
      "Edit(//Users/samuelviciana/Documents/day-300/*/evals/golden/**)",
      "Edit(//Users/samuelviciana/Documents/day-300/genai-infra-05/policies/**)",

      "Edit(//Users/samuelviciana/Documents/day-300/_comun/**)",
      "Write(//Users/samuelviciana/Documents/day-300/_comun/**)",
      "Edit(//Users/samuelviciana/.claude/settings.json)",
      "Edit(//Users/samuelviciana/.claude/gates/**)",
      "Read(**/.env)",

      "Bash(pytest * --no-cov *)",
      "Bash(pytest * -k *)",
      "Bash(pytest * -x *)",
      "Bash(pytest * --deselect *)",
      "Bash(rm -rf *)",
      "Bash(git *)"
    ],
    "allow": [
      "Read(//Users/samuelviciana/Documents/day-300/_comun/**)"
    ],
    "ask": [
      "Bash(uv add *)", "Bash(uv remove *)", "Bash(pip install *)",
      "Bash(terraform apply *)", "Bash(terraform destroy *)",
      "Bash(aws *)"
    ],
    "defaultMode": "auto"
  },

  "hooks": {
    "PreToolUse": [
      { "matcher": "Edit|Write",
        "hooks": [
          { "type": "command", "args": [], "command": "\"$HOME\"/.claude/gates/protect-state.sh" },
          { "type": "command", "args": [], "command": "\"$HOME\"/.claude/gates/anti-gaming.sh",
            "if": "Edit(//Users/samuelviciana/Documents/day-300/**/tests/**)" },
          { "type": "command", "args": [], "command": "\"$HOME\"/.claude/gates/tdd-guard.sh",
            "if": "Edit(//Users/samuelviciana/Documents/day-300/**/src/**/*.py)" }
        ] }
    ],
    "PostToolUse": [
      { "matcher": "Edit|Write",
        "hooks": [ { "type": "command", "args": [], "timeout": 90,
                     "command": "\"$HOME\"/.claude/gates/a-feedback.sh" } ] }
    ],
    "PostToolBatch": [
      { "hooks": [ { "type": "command", "args": [], "timeout": 120,
                     "statusMessage": "Gate rapido",
                     "command": "\"$HOME\"/.claude/gates/b-step.sh" } ] }
    ],
    "TaskCompleted": [
      { "hooks": [ { "type": "command", "args": [], "timeout": 120,
                     "command": "\"$HOME\"/.claude/gates/b-step.sh" } ] }
    ],
    "Stop": [
      { "hooks": [ { "type": "command", "args": [], "timeout": 600,
                     "statusMessage": "Gate de cierre de turno",
                     "command": "\"$HOME\"/.claude/gates/c-turn.sh" } ] }
    ],
    "SessionStart": [
      { "matcher": "startup|resume|compact|clear",
        "hooks": [ { "type": "command", "args": [],
                     "command": "\"$HOME\"/.claude/gates/inject-state.sh" } ] }
    ]
  }
}
```

Tres notas sobre esa lista de permisos:

- **`Bash(git *)` está en `deny` a propósito, y es temporal.** Git va a existir; lo inicias tú en
  cada carpeta cuando decidas. Hasta entonces, el agente no debe crear un repositorio a medias
  ni commitear por su cuenta. El día que hagas `git init`, quitas esa línea y añades el gate a
  `pre-commit`: el target de Makefile ya está listo y no cambia nada más.
- **`terraform apply`, `terraform destroy` y `aws` están en `ask`, no en `deny`.** El proyecto 05
  necesita desplegar de verdad; lo que no puede es hacerlo sin que te enteres, porque cuesta
  dinero.
- **Las reglas de `Read`/`Edit` cubren las herramientas de fichero y el Bash que Claude Code
  reconoce.** No cubren un subproceso arbitrario. Ver el límite honesto de §2.5.

Detalles que ahorran horas de depuración:

- `args: []` fuerza la forma exec (sin shell), y evita que el perfil de zsh ensucie el stdout
  JSON del hook.
- `if:` usa sintaxis de reglas de permiso y **solo funciona en eventos de herramienta**. En
  `Stop` impide que el hook corra.
- Si varios hooks corren sobre el mismo evento, **el deny gana**.
- `Stop` se ignora tras **8 bloqueos consecutivos**. El script debe leer `stop_hook_active` y
  salir con 0 si es `true`. Si el agente no arregla la suite en ocho intentos, lo que quieres
  es que pare y avise, no que siga.

### 2.4 Cómo se evita que el gate estorbe

Un gate lento se acaba desactivando, y entonces no hay gate. Cuatro medidas obligatorias:

1. **Debounce por hash.** `b-step.sh` calcula el sha de `(ruta, mtime)` de `src/**` y `tests/**`.
   Si no cambió desde la última ejecución verde, sale con 0 en unos 50 ms.
2. **Presupuesto duro por capa.** Si `gate-fast` supera 25 s es un bug del proyecto: se
   paraleliza con `pytest -n auto`, se mueven tests a `integration/`, o se recorta el perfil de
   Hypothesis. **El gate no se relaja; el test se arregla.**
3. **Perfiles de Hypothesis por contexto.** `dev` = 25 ejemplos, `gate` = 100, `nightly` = 1000.
   Sin esto la suite rápida es intermitente y nadie se fía de ella.
4. **La capa B no se activa hasta que `make test-fast` baje de 20 s.** Antes de eso estorba más
   de lo que aporta.

### 2.5 Anti-gaming: seis mecanismos, ninguno opcional

Un agente con un gate que le bloquea y permiso para editar sus reglas tiene el incentivo
perfecto para editar el gate. Es el fallo de gobierno más previsible que existe.

| # | Riesgo | Contramedida | Dónde vive |
|---|---|---|---|
| 1 | Borrar o debilitar tests | **Inventario firmado.** `test-inventory.json` = `{fichero: {n_tests, n_asserts, sha}}`. `PreToolUse` sobre `tests/**` deniega si baja `n_tests` o `n_asserts` sin propuesta aprobada | `anti-gaming.sh` |
| 2 | Bajar un umbral | **`thresholds.lock`** = sha256 de `GOALS.yaml`. `make done` compara; si difiere, rojo sin excepción. Y `GOALS.yaml` está en `deny` | Gate E |
| 3 | Esquivar la suite | Prohibido `skip`, `xfail`, `--no-cov`, `-k`, `--deselect`, `-x`. Grep en gate C + `deny` sobre el comando | Gate C + permisos |
| 4 | Tests escritos para pasar | **`tests/holdout/` ilegible**: `deny` de Read, Edit y Write. Los escribe el subagente `qa-adversario`, que a su vez **no lee `tests/unit/`**. Solo corren en `make done` | Permisos + subagente |
| 5 | Tests que no prueban nada | **Mutación al cerrar fase**: `mutmut` sobre los paquetes `testable`, ≥ 70 % de mutantes muertos. Es lo único que distingue cobertura de verificación | Meta en `GOALS.yaml` |
| 6 | Alucinación de APIs | Script AST que extrae cada `from X import Y` de `src/` y verifica que resuelve en el venv real. Más dependencias con `==` exacto | Gate C |

**Límite honesto que conviene conocer:** las reglas `Read`/`Edit` cubren las herramientas de
fichero y los comandos Bash que Claude Code reconoce (`cat`, `sed`, `head`). **No cubren un
subproceso arbitrario**: un script Python que abra `tests/holdout/` se salta el deny. Aquí no
hay adversario real —es tu propio proyecto— así que el deny basta y evita el 99 % de los
atajos accidentales. Si algún día quieres cumplimiento a nivel de sistema operativo, eso es
`sandbox`, no permisos.

### 2.6 "Un test unitario por cada función", hecho ejecutable

Tu encargo dice "cada función". Tus documentos dicen "sin objetivo global de cobertura, TDD
solo donde aplica, perseguir el 100 % en adaptadores es ruido". **La contradicción se resuelve
con una definición ejecutable, no con un porcentaje.**

```toml
# pyproject.toml
[tool.gate]
testable          = ["src/citebound/domain", "src/citebound/retrieval"]
tdd_obligatorio   = ["src/citebound/domain", "src/citebound/retrieval"]
excluido          = ["src/citebound/agent", "src/citebound/api", "prompts"]
cobertura_linea_min = 85
mutantes_muertos_min = 70
```

Regla: **toda función pública (sin `_` inicial) de un paquete listado en `testable` tiene al
menos un test unitario que la ejerce directamente.** No se mide por convención de nombres —eso
se falsea trivialmente— sino con:

```
pytest tests/unit --cov --cov-context=test --cov-report=json:/tmp/cov.json
python scripts/check_function_coverage.py     # exit 1 si alguna función pública no tiene contexto de test
```

`--cov-context=test` registra **qué test** cubrió cada línea. El script recorre el AST de los
paquetes `testable` y exige ≥ 1 contexto por función pública. Eso es literalmente un test por
función donde tiene sentido, es automático, y evita el desastre de exigir tests unitarios sobre
prompts y grafos de agente, donde se mide en vez de testear.

---

## 3. La regla de autoescritura

Tres zonas físicas. Sin zona gris.

### Zona verde — el agente escribe libremente

| Fichero | Restricción mecánica |
|---|---|
| `.claude/state/STATE.md` | Esquema validado por hook, ≤ 80 líneas. Los campos `gate_verde_en` y `ultima_verificacion` **los escribe solo el gate**; si el agente los toca, `PreToolUse` deniega |
| `docs/JOURNAL.md` | Solo append: el hook rechaza si el contenido nuevo no empieza exactamente por el viejo |
| `docs/adr/NNN-*.md` | Solo ficheros nuevos. Modificar un ADR existente exige crear otro que lo supersede |
| `CHANGELOG.md` | Append, solo al cerrar fase |
| Código, tests, prompts | Sujeto al gate y al anti-gaming |

### Zona ámbar — el agente propone, tú dispones

Un único canal: **`docs/PARA-SAMUEL.md`**, append-only, formato fijo.

```markdown
## PROPUESTA P-007 · 2026-08-14 · fase 2
Tipo: bajar-umbral | cambiar-meta | cambiar-spec | cambiar-plan | necesito-recurso
Afecta a: docs/GOALS.yaml :: G-RECALL-5 (0.90)
Qué pido: bajar a 0.85
Por qué: 12 h de trabajo, 4 configuraciones de troceado medidas (tabla en JOURNAL 2026-08-13).
         El techo con el corpus actual es 0.87 ± 0.02. Ver ADR-006.
Qué he descartado: reranker mayor (+800 ms p95, rompe G-LATENCIA), chunking semántico (coste).
Alternativa si dices que no: ampliar corpus con RD 818/2009 (estimado 6 h).
Estado: PENDIENTE
```

Reglas duras de esta zona:

- El agente **para** tras escribir la propuesta. No sigue asumiendo que sí.
- Una propuesta de bajar umbral **solo es admisible con ≥ 2 intentos medidos y registrados en
  `JOURNAL.md`**. El gate lo verifica: si aparece una propuesta `bajar-umbral` sin entradas de
  bitácora entre el inicio de la fase y hoy, marca rojo.
- Aprobar es: **tú** editas `GOALS.yaml`, pones `Estado: APROBADA` y regeneras `thresholds.lock`.
  Solo tú puedes regenerar el lock.

### Cuando el cambio lo pides tú

No todo lo de esta zona pesa igual, y tratarlo igual convierte el gobierno en burocracia. Hay
dos casos y se distinguen por una pregunta: **¿el cambio afecta a lo que el proyecto promete, o
solo a cómo lo consigue?**

| Pides… | Qué hace el agente |
|---|---|
| **Subir una versión, cambiar una librería, actualizar el stack** | **Lo hace.** Es tu decisión y no toca ninguna promesa. Antes de aplicarlo te dice en dos líneas qué se rompe y si hay que propagarlo a otros proyectos; luego lo aplica y lo anota en `JOURNAL.md`, con ADR si la decisión no era obvia |
| **Bajar un umbral, quitar una meta, recortar el alcance** | **Escribe la propuesta y para.** Aquí la fricción es deliberada: es la única defensa contra que los objetivos se erosionen fase a fase sin que nadie lo note. Aunque el cambio nazca de ti, quieres ver escrito qué se pierde antes de confirmarlo |

En el primer caso el agente **no se escuda en el `deny` para no hacerte caso**. Si `docs/STACK.md`
está protegido y tú pides el cambio, la respuesta correcta es: hacer el trabajo, dejar el fichero
listo, y decirte la línea exacta que tienes que aplicar tú si el `deny` se lo impide. Nunca
"no puedo".

**La trampa del stack: está copiado en los cinco proyectos.** Cambiarlo en uno los desincroniza,
y el gate lo detecta como copia divergente. Así que cuando pidas actualizar algo, el agente te
dice también si es local a ese proyecto o transversal. Si es transversal, se cambia en `_comun/`
y se propaga a mano a los cinco — que es un evento consciente, no un efecto secundario.

Y una excepción que no se negocia: los umbrales marcados `propuesta_admisible: false` en
`GOALS.yaml` —alucinación de artículo, evasión del validador SQL, fuga de columnas sensibles,
secretos en el repo— **no admiten ni siquiera la propuesta**. Cero es cero: ahí no hay umbral
estadístico que negociar.

### Zona roja — nunca, bajo ninguna circunstancia

`docs/PROJECT.md`, `docs/GOALS.yaml`, `docs/PLAN.md`, `docs/RULES.md`, `docs/CONSTITUCION.md`,
`thresholds.lock`, `tests/holdout/**`, `.claude/state/*.json`, `.snapshots/**`,
`~/.claude/settings.json`, `~/.claude/gates/**`, y todo `_comun/`.

Todos en `permissions.deny`. La prohibición se repite además en `CLAUDE.md` como redundancia
pedagógica: un agente que sabe que algo está prohibido no gasta turnos intentándolo.

### El caso `.claude/rules/` — autoescritura genuina, controlada

Es el único sitio donde el agente **mejora su propio documento de reglas**, y es deliberado:
ahí se acumula el aprendizaje operativo real (rarezas de librerías, patrones que fallaron,
convenciones que emergieron).

1. Solo vía la skill `/mejorar-reglas`, con `disable-model-invocation: true`: **nunca se invoca
   sola**, siempre la pides tú.
2. Toda regla nueva lleva `<!-- origen: JOURNAL 2026-08-12, fallo repetido 3 veces -->`. Una
   regla sin evidencia de fricción real no entra.
3. Una regla nunca puede contradecir `CLAUDE.md`, `GOALS.yaml`, `RULES.md` ni esta constitución.
4. Tope de 60 líneas por fichero. Al superarlo se parte o se poda.
5. **No se activa hasta la semana 3 o 4 de trabajo real.** Dejar que el agente escriba reglas
   antes de que existan problemas produce reglas genéricas e inútiles.

---

## 4. Ciclo de trabajo del agente

### 4.1 El bucle, por unidad de trabajo

```
0. ARRANQUE
   Leer STATE.md + gate-status.json + fase activa. Reportar en 5 líneas. Esperar.

1. ELEGIR
   Tarea activa de STATE.md. Si no hay, la primera bloqueada que ya sea desbloqueable.
   Si ninguna lo es → PARAR (§4.2, caso C).

2. ENCUADRAR
   ¿La tarea toca un paquete de [tool.gate].tdd_obligatorio?  SÍ → 3.  NO → 5.

3. ROJO   (turno propio, no se mezcla con el 4)
   Escribir SOLO el test. Ejecutarlo. Verificar que falla POR LA ASERCIÓN,
   no por ImportError / ModuleNotFoundError / SyntaxError.
   Poner `fase_tdd: rojo` en STATE.md. PARAR el turno.

4. VERDE
   Implementar lo mínimo que pone el test en verde. `fase_tdd: verde`.

5. IMPLEMENTAR / REFACTORIZAR
   Con la suite en verde. `fase_tdd: refactor`.

6. GATE
   Rojo → diagnosticar la causa REAL. Prohibido tocar el test para que pase.
   Tres rojos consecutivos por la misma causa → PARAR (§4.2, caso D).

7. REGISTRAR
   Actualizar STATE.md. Anotar en JOURNAL.md qué se aprendió, con el número si hubo medida.
   Decisión no obvia → ADR.

8. CERRAR
   Al terminar la fase: `make done MILESTONE=N`. Si pasa, presentar los números a Samuel
   y PARAR. No se abre la fase siguiente sin su visto bueno.
```

**La separación temporal entre los pasos 3 y 4 es el mecanismo, no el orden de las líneas en el
fichero.** Un agente que escribe test e implementación en el mismo turno escribe el test contra
la implementación que ya tiene en la cabeza, y se pierde todo el valor. Por eso el paso 3
termina en PARAR, y lo impone `tdd-guard.sh`, que además distingue "rojo por aserción" de "rojo
por ImportError", que no es rojo sino ruido.

### 4.2 Cuándo el agente debe parar y preguntar

Lista cerrada. Fuera de estos casos, sigue solo.

| Caso | Disparador | Qué hace |
|---|---|---|
| **A · Fin de fase** | `make done MILESTONE=N` en verde | Presenta los números medidos y para. **No abre la fase siguiente sin aprobación** |
| **B · Spec inviable** | Algo de `PROJECT.md` no se puede construir como está escrito | Propuesta `cambiar-spec`. **Nunca** reescribir la spec |
| **C · Recurso externo** | Hace falta cuenta, clave, gasto, dataset, corpus, decisión legal o de negocio, u horas humanas | Pregunta en `PARA-SAMUEL.md`. Para y sigue con otra tarea si la hay |
| **D · Meta inalcanzable** | Tras ≥ 2 intentos medidos y registrados, la meta no se alcanza | Propuesta `bajar-umbral` con evidencia. Para |
| **E · Bucle** | 3 fallos del gate seguidos por la misma causa raíz | Escribe el diagnóstico y para. **No sigue intentando** |
| **F · Dependencia nueva** | Necesita una librería que no está en `pyproject.toml` | `uv add` está en `ask`: pide permiso y justifica en el mismo turno |
| **G · Ambigüedad de contrato** | Un contrato de `_comun/CONTRACTS/` no cubre el caso | Pregunta. **Nunca improvisar un contrato compartido**: rompe otros proyectos |
| **H · Ambigüedad ordinaria** | Detalle de implementación no especificado | **NO parar.** Decidir, ejecutar y anotar en `JOURNAL.md` como decisión reversible. Si es no obvia, ADR |

El caso H es el más importante de los ocho: sin él, un agente prudente pregunta cada veinte
minutos y la autonomía desaparece. **La regla es: pregunta lo que no puedes revertir; decide
lo que sí.**

---

## 5. Definition of Done

Un solo comando, idéntico en los cinco:

```
make done MILESTONE=2       # exit 0 o exit 1. Es la única definición de "hecho"
```

Verifica en este orden, parando en el primer fallo:

| # | Condición | Comprobación |
|---|---|---|
| 1 | Estáticos limpios | `ruff check` + `ruff format --check` + `mypy --strict` sobre `testable` + `bandit` + `detect-secrets` |
| 2 | Suite completa verde | `pytest tests/unit tests/property tests/contract tests/integration` |
| 3 | Reserva verde | `pytest tests/holdout` |
| 4 | Cobertura por función | `check_function_coverage.py`: cero funciones públicas sin test en paquetes `testable` |
| 5 | Cobertura de línea | ≥ `cobertura_linea_min` en paquetes `testable` |
| 6 | Mutación | `mutmut` ≥ `mutantes_muertos_min` |
| 7 | Metas activas | Toda meta con `bloqueante_desde_fase <= MILESTONE` pasa su umbral |
| 8 | Umbrales intactos | `sha256(GOALS.yaml) == thresholds.lock` |
| 9 | Inventario de tests | `n_tests` y `n_asserts` ≥ los del último snapshot verde |
| 10 | Deuda bajo tope | `TODO\|FIXME\|XXX\|NotImplementedError` en `src/` ≤ 10; cero `skip`/`xfail` sin ticket en STATE.md |
| 11 | Documentación | La fase tiene entrada en `CHANGELOG.md`; todo ADR referenciado existe |
| 12 | Sin secretos | `detect-secrets scan --baseline` sin hallazgos nuevos |

`make done` escribe el resultado en `.claude/state/gate-status.json` —que el agente no puede
editar— y solo entonces habilita cerrar la fase.

---

## 6. Niveles de test y qué exige cada gate

| Nivel | Qué es | A (feedback) | B (paso) | C (turno) | **E · `make done`** |
|---|---|:--:|:--:|:--:|:--:|
| **0 · Estáticos** | ruff, mypy --strict, bandit, detect-secrets | fichero | sí | sí | sí |
| **1 · Unitarios** | deterministas, sin red ni contenedores | módulo | sí | sí | sí |
| **1b · Propiedad** | Hypothesis: invariantes | no | perfil `dev` | perfil `gate` | perfil `nightly` |
| **2 · Integración** | testcontainers: Postgres, ClickHouse, DuckDB | no | no | no | **sí** |
| **3 · Contrato** | OpenAPI snapshot, esquema SSE, JSON Schema, atributos OTel | no | sí | sí | sí |
| **4 · Evaluación** | mediciones, no tests. Distribuciones y estadística | no | no | no | sí, desde `bloqueante_desde_fase` |
| **5 · Adversarial y e2e** | inyección de prompt, evasión SQL, humo `compose up` | no | no | no | sí |
| **H · Reserva** | escritos por `qa-adversario`, ilegibles para el constructor | no | no | no | **sí** |

Lo que esto fija:

- **El nivel 3 entra en el gate rápido.** Un snapshot de esquema tarda milisegundos y es donde
  más barato sale detectar una rotura de contrato entre proyectos.
- **El nivel 2 nunca entra en el gate rápido, pero es obligatorio para avanzar.** Levantar
  testcontainers cuesta entre 10 y 40 s, y en macOS es el punto de fricción número uno (Ryuk,
  `DOCKER_HOST`, sockets). Corre en `make done`, que es donde Samuel pidió que fuera exigible.
- **El nivel 4 no es un test.** Un test es binario y determinista; una evaluación produce una
  distribución y se compara estadísticamente. Confundirlos produce o tests inestables que se
  acaban desactivando, o la ilusión de calidad. Las evals bloquean vía `GOALS.yaml`, con umbral
  absoluto **y** con intervalo de confianza bootstrap **pareado** sobre los mismos casos.
- **Las evals no corren en el gate de turno.** Con LLM local, 200 casos son minutos u horas.

---

## 7. Convenciones compartidas

### 7.1 Nombres canónicos — congelados

Hoy cada proyecto tiene dos nombres y solo coinciden dos de cinco. Se cierra ahora, porque
renombrar después toca cada import, cada Makefile y cada README.

| Directorio | Paquete Python | CLI | Nombre público |
|---|---|---|---|
| `citebound-01` | `citebound` | `citebound` | Citebound · tutor de normativa |
| `evalgate-02` | `evalgate` | `evalgate` | Evalgate · puerta de calidad LLM |
| `data-warden-03` | `datawarden` | `warden` | Data Warden · agente NL→SQL |
| `indexkeeper-04` | `indexkeeper` | `indexkeeper` | Indexkeeper · ingesta RAG |
| `genai-infra-05` | `genai_infra` | — (Terraform) | GenAI Infra · módulos serverless |

`tutor-normativa`, `llm-gate` y `rag-ingest` quedan como subtítulo descriptivo, no como
identificador.

### 7.2 Dependencias: `uv`

- `pyproject.toml` con **versiones exactas (`==`)**, nunca `^` ni `~`. Es lo que hace que el
  repo siga compilando dentro de seis meses y lo que impide que el agente alucine APIs de una
  minor futura.
- `uv.lock` siempre presente.
- `requires-python = "==3.12.*"`.
- Imágenes Docker **por digest**, no por tag.
- `uv add` y `uv remove` en `ask`: el agente no amplía la superficie de dependencias solo.

**Alcance exacto de la regla `==`, porque `STACK.md` usa rangos y no es una contradicción:**

| Qué | Cómo se fija | Por qué |
|---|---|---|
| Dependencias Python en `pyproject.toml` | `==X.Y.Z` **siempre** | Es donde vive el riesgo de que una minor rompa la API |
| Imágenes de contenedor | **digest** `@sha256:...` | Un tag es mutable; un digest no |
| Binarios externos (Terraform, DuckDB CLI) | versión exacta, verificada por el `Makefile` | El agente no los instala; falla si la versión no coincide |
| Restricciones de provider de Terraform | `~> X.Y.Z` en HCL | Es la sintaxis del lenguaje, no una preferencia. Se declara como desvío |
| Rangos que aparecen en `STACK.md` | **son la investigación, no el pin** | `STACK.md` dice de qué línea coger; el pin exacto vive en `pyproject.toml` y en `uv.lock` |

Esa última fila es la que resuelve la aparente contradicción: `STACK.md` responde a "qué línea
es la correcta hoy y por qué"; `pyproject.toml` responde a "qué versión exacta compila este
repo". Cuando el agente fije una dependencia, **traduce el rango de `STACK.md` a un `==`
concreto y anota la versión elegida en el `JOURNAL.md`**. Si el rango es ambiguo para su caso,
es el caso G de §4.2: decide, ejecuta y anota.

### 7.3 Python 3.12, con el motivo correcto

No "porque lo pide la oferta". **Porque MWAA solo ofrece Python 3.12**, y por uniformidad con
las wheels de torch/MPS. Existen 3.13 y 3.14. Ese razonamiento va en un ADR de los cinco: uno
dice "3.12 porque MWAA no ofrece más" y es ingeniería; el otro dice "porque lo pide la oferta"
y es transcripción.

### 7.4 Makefile canónico

```makefile
up           # levanta el entorno local. Verifica que Ollama responde en el host
down         # lo tumba, sin volúmenes huérfanos
warm         # descarga modelos y precalienta cachés. NUNCA dentro de `up`: rompe el cronómetro
lint         # ruff check + ruff format --check
typecheck    # mypy --strict sobre [tool.gate].testable
test-fast    # nivel 1 + 1b(dev) + 3. Presupuesto: < 20 s
test         # todo salvo evals y holdout
test-int     # nivel 2, testcontainers
eval         # nivel 4 desde caché grabada. Determinista y gratis
eval-refresh # nivel 4 recalculando. Exige clave o modelo. Nunca en el gate
bench        # protocolo de medida de latencia (calentamiento + N + descarte de la primera)
gate-fast    # lint + typecheck + test-fast + anti-gaming
gate-full    # gate-fast + test + contrato + metas + thresholds.lock + secretos
done         # la DoD completa del §5. MILESTONE=N
report       # regenera las tablas de números del README desde evals/reports/
clean
```

Que `gate-fast` y `gate-full` sean targets y no scripts sueltos es lo que hace el gate portable
a git el día que quieras, sin tocar nada.

### 7.5 Layout

```
<proyecto>/
├── CLAUDE.md
├── Makefile · pyproject.toml · uv.lock · compose.yaml
├── src/<paquete>/
│   ├── domain/        # puro, sin I/O. TDD obligatorio
│   ├── <capas propias>
│   └── providers/     # adaptadores. Patrón Provider: Local | Cloud | Recorded
├── prompts/           # .md con frontmatter. NUNCA inline en el código
├── evals/{golden,suites,reports}/
├── tests/{unit,property,integration,contract,adversarial,holdout}/
├── docs/
│   ├── PROJECT.md · GOALS.yaml · PLAN.md · RULES.md · CONSTITUCION.md   (humano)
│   ├── JOURNAL.md · PARA-SAMUEL.md · adr/                                (agente)
│   └── STACK.md · CONTRACTS/                                             (copiados de _comun/)
├── scripts/{save.sh,check_function_coverage.py,time-cold-start.sh}
├── .claude/{settings.json,rules/,agents/,skills/,state/}
└── .snapshots/
```

### 7.6 Prompts

Frontmatter obligatorio. Sin esto no se puede correlacionar un cambio de métrica con un cambio
de prompt, que es medio argumento del proyecto 02.

```markdown
---
id: answer_with_citation
version: 4
modelo_destino: qwen3.5:9b-mlx
temperatura: 0.0
cambios: "v4: se exige el apartado, no solo el artículo"
---
Eres un asistente de normativa de circulación...
```

El informe de cada eval registra `{prompt_id, version, sha256}`. El gate rechaza un prompt sin
frontmatter.

### 7.7 Idioma

**Código, identificadores, docstrings, logs y mensajes de error: inglés.**
**Documentos, ADR, JOURNAL, CHANGELOG, README y comentarios de negocio: español.**
Es la combinación que no cierra puertas y a la vez suena natural en el mercado objetivo.

### 7.8 Qué pasa el día que publiques un repo suelto

`_comun/` es **andamiaje de tu proceso, no parte del entregable**. Cuando alguien clone
`citebound-01` de tu GitHub no tendrá esa carpeta, y no le hará falta: todo lo que necesita ya
está copiado dentro del repo.

| Fichero | ¿Va al repo público? | Por qué |
|---|---|---|
| `docs/CONSTITUCION.md` | **Sí** | Cuenta cómo se construyó. De lo más interesante que un revisor puede leer |
| `docs/STACK.md` | **Sí** | Las versiones exactas son parte de la reproducibilidad |
| `docs/CONTRACTS/` | **Sí** | Sin ellos el repo no se entiende |
| `PROJECT.md`, `GOALS.yaml`, `PLAN.md`, `RULES.md` | **Sí** | Son la especificación y los números prometidos |
| `JOURNAL.md`, `adr/`, `CHANGELOG.md` | **Sí** | La evidencia de que hubo criterio y no improvisación |
| `docs/PARA-SAMUEL.md` | **decisión tuya** | Enseña cómo se gestionó el proyecto, y también lo que faltaba |
| `_comun/PARA-SAMUEL-GLOBAL.md` | **No** | Privado: tus horas, tu presupuesto, tu calendario. No pertenece a ningún repo |
| `.claude/state/`, `.snapshots/` | **No** | Estado local de trabajo. Al `.gitignore` |

Esa es exactamente la razón de que la constitución se copie a los cinco y el buzón global no.

### 7.9 Núcleo mínimo y ampliación

Cada `PLAN.md` marca cada fase como **núcleo** o **ampliación**:

- **Núcleo** — lo que hace el proyecto enseñable y defendible. Si solo haces esto, el proyecto
  vale. Sus metas son bloqueantes.
- **Ampliación** — lo que lo hace completo. Se aborda si hay tiempo. **Sus metas nunca bloquean
  el núcleo**, y no empezarlas no es un fallo.

Cada `PLAN.md` declara además sus **horas humanas irreducibles**: el trabajo que ningún agente
puede hacer por ti. Ese número decide si una fase es realista, y va escrito antes de empezar.

---

## 8. Lo que Samuel debe aportar

Ningún agente puede resolver nada de esto. Hay dos niveles y **no se mezclan**:

**Transversal → `/Users/samuelviciana/Documents/day-300/_comun/PARA-SAMUEL-GLOBAL.md`.** Diez
decisiones que afectan a más de un proyecto: horas por semana y su reparto, nombres canónicos, qué
cabe a la vez en la máquina, la cuenta AWS con **un solo límite de gasto**, la clave de API, la
política de honestidad, la visibilidad de los repos, los vídeos, cuándo se instalan los hooks, y
cómo se despliega cada proyecto.

**Ese fichero vive FUERA de tu directorio de trabajo, un nivel por encima.** Si trabajas en
`citebound-01/`, la ruta relativa `_comun/…` no existe: hay que usar la absoluta de arriba. Y
**no se copia al proyecto**, a diferencia de esta constitución: si hubiera cinco copias, Samuel
respondería en una y cuatro agentes leerían las otras. Se lee siempre desde el original.

Preguntadas por separado, estas nueve se convierten en treinta y tantas preguntas repartidas por
cinco buzones, con el riesgo de que se respondan distinto en cada uno. La de la máquina es la
peor: cada proyecto conoce su propio consumo y ninguno tiene la vista de los 36 GB completos, que
es lo único que permite decidir.

**Regla para el agente:** antes de escribir una pregunta en tu `PARA-SAMUEL.md`, comprueba si ya
está en el global. Si lo está, **no la repitas**: remite a `D-NN` y sigue. Si tu proyecto tiene
un matiz propio sobre una decisión global (un presupuesto concreto, una fecha), escríbelo como
matiz de esa `D-NN`, no como pregunta nueva.

**Específico → `docs/PARA-SAMUEL.md` de cada proyecto**, pre-poblado desde el primer día, con la
fase exacta en que bloquea: el corpus legal del 01, el dataset del 03, el destino de las alertas
del 04. Eso sí es de cada uno y ahí es donde se pregunta.

---

## 9. Orden de activación del gobierno

Levantarlo todo de golpe es el error clásico. Cada paso da valor solo y es reversible.

| # | Paso | Cuándo |
|---|---|---|
| 1 | Leer `PROJECT.md`, `GOALS.yaml`, `PLAN.md` y responder lo urgente de `PARA-SAMUEL.md` | Antes de la primera línea de código |
| 2 | `make gate-fast` y `gate-full` ejecutados **a mano** | Días 1-2. Comprobar que las metas son medibles antes de hacerlas bloqueantes |
| 3 | Hook `Stop` (capa C), solo lint y suite | Día 3. Convivir con él una semana |
| 4 | `permissions.deny` completo (zona roja) | Semana 1 |
| 5 | Hook `SessionStart` de reinyección de estado | Semana 1. Sin esto el agente pierde el hilo tras `/compact` |
| 6 | Hook `PostToolBatch` (capa B) | **Solo cuando `make test-fast` baje de 20 s** |
| 7 | `tests/holdout/` + subagente `qa-adversario` + deny de lectura | Al cerrar la primera fase |
| 8 | `tdd-guard.sh`, acotado a `tdd_obligatorio` | Después del 7 |
| 9 | Skill `/mejorar-reglas` | Semana 3-4, con fricción real acumulada |
| 10 | `git init` y migración del gate a `pre-commit` | Cuando tú decidas |

---

## 10. La medida de éxito

No es que el agente vaya rápido. Es que puedas irte tres horas y al volver encontrarte:

- `STATE.md` coherente con lo que hay en disco,
- el gate en verde, o parado con un diagnóstico escrito,
- `PARA-SAMUEL.md` con una pregunta bien formulada si algo no cuadraba,
- **cero tests borrados y cero umbrales tocados.**

Si algo de eso falla, la contramedida que falta está en §2.5. Y si el agente encontró la forma
de saltarse el gate, la respuesta correcta no es añadir una regla al `CLAUDE.md`: es añadir un
hook.
