# Instalación del gobierno fuera del proyecto · D-09

> Preparado por el agente al cerrar F0 (2026-09-10) para que **Samuel lo revise y lo instale**. El agente no
> escribe en `~/.claude/`: sería editar a su propio guardián (CONSTITUCION §0, primera regla de oro).
> Tiempo estimado: 20-30 min de revisión + 5 de instalación. Reversible con la copia de seguridad.

## Qué instala

| Paso §9 | Qué | Fichero |
|---|---|---|
| 3 | Hook `Stop` (capa C): `make gate-fast` al cerrar cada turno en los proyectos de `day-300` | `c-turn.sh` |
| 4 | `permissions.deny` de la zona roja y `ask` para `uv add`/`uv remove`/`pip install`, en **todas** tus sesiones | `user-settings.snippet.json` |
| 7 | Reserva (`tests/holdout/`) ilegible para el constructor y escribible solo por la sesión qa | `builder.settings.json`, `qa.settings.json` |

**No instala** la capa B (`PostToolBatch`), que según §9 paso 6 no se activa hasta que `make test-fast` baje
de 20 s. Hoy tarda ~0,7 s, así que puede activarse cuando quieras, pero es otro paso.

## Dos decisiones de diseño que difieren de `CONSTITUCION.md` §2.3, y por qué

1. **La reserva va en un perfil de sesión, no en tu `settings.json` global.** La documentación de Claude Code
   (consultada el 2026-09-10) dice que las listas `deny` de todos los niveles **se suman** y que existe
   `claude --settings <fichero>`. Si el `deny` de escritura sobre `tests/holdout/` estuviera en el global,
   **tampoco podría escribir la sesión qa**, que es quien crea esos tests. No está documentado si un
   subagente puede saltarse el `deny` de su sesión padre, así que `qa-adversario` no será un subagente del
   constructor: será **una sesión aparte, que abres tú**.
2. **`Bash(git *)` no va en el global.** Denegaría git en *todas* tus sesiones, incluida citebound-01, que
   sí usa git. Va solo en los dos perfiles de evalgate.

## Cómo se instala

```bash
cd /Users/samuelviciana/Documents/day-300/evalgate-02
cat scripts/gates-install/*.json scripts/gates-install/c-turn.sh   # revisar primero
bash scripts/gates-install/install.sh
```

Añade estos dos alias a `~/.zshrc`:

```bash
alias claude-evalgate='cd ~/Documents/day-300/evalgate-02 && claude --settings ~/.claude/gates/builder.settings.json'
alias claude-qa='cd ~/Documents/day-300/evalgate-02 && claude --settings ~/.claude/gates/qa.settings.json'
```

- **Constructor:** a partir de ahí, abre siempre evalgate con `claude-evalgate`. **La sesión actual no
  tiene el perfil**: hay que cerrarla y abrir una nueva con el alias.
- **qa-adversario:** al cerrar cada fase, `claude-qa` y pídele: *"Eres qa-adversario. Lee docs/PLAN.md,
  docs/GOALS.yaml, docs/CONTRACTS/ y docs/spec/, y la API pública de src/evalgate/ para la fase N. Escribe
  en tests/holdout/ tests de caja negra que intenten romperla. No leas tests/unit/ ni tests/property/.
  Ejecuta solo `uv run pytest tests/holdout -q` y dime cuántos tests has añadido y cuántos pasan, sin su
  contenido."* Después vuelve a `claude-evalgate`: `make done MILESTONE=N` lo lanza el constructor.
  Si algún test de reserva falla, es un hallazgo: el constructor lo verá como rojo del paso 3 sin ver el test.

## Cómo se revierte

`cp ~/.claude/settings.json.bak-<fecha> ~/.claude/settings.json` y `rm -r ~/.claude/gates`.

## Límite honesto

Los `deny` cubren las herramientas de fichero y los comandos Bash que Claude Code reconoce, no un
subproceso arbitrario (§2.5): `make done` ejecuta la reserva con pytest, y eso es lo que se quiere.
