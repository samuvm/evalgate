#!/usr/bin/env bash
# Stop hook · capa C (CONSTITUCION §2.1): `make gate-fast` al cerrar cada turno en los proyectos de day-300
# que definan ese target. exit 2 = el turno no se cierra y Claude recibe el motivo por stderr.
#
# Excepción deliberada, que la constitución no resuelve: en el paso ROJO del TDD (§4.1 paso 3) el test
# falla por diseño y el turno DEBE cerrarse. Si STATE.md dice `fase_tdd: rojo`, solo se exigen lint y
# typecheck. El agujero (dejar `rojo` puesto) lo cierra `make done`, que no mira fase_tdd.
set -uo pipefail

input="$(cat)"
field() { printf '%s' "$input" | /usr/bin/python3 -c "import json,sys; print(json.load(sys.stdin).get('$1', ''))" 2>/dev/null; }

# Tras 8 bloqueos seguidos Claude Code ignora el hook; aun así, si ya estamos continuando por un Stop
# anterior, se deja parar: si el agente no arregla la suite, lo que se quiere es que pare y avise (§2.3).
[ "$(field stop_hook_active)" = "True" ] && exit 0

dir="${CLAUDE_PROJECT_DIR:-$(field cwd)}"
case "$dir" in /Users/samuelviciana/Documents/day-300/*) ;; *) exit 0 ;; esac
[ -f "$dir/Makefile" ] && grep -q '^gate-fast:' "$dir/Makefile" || exit 0

targets="gate-fast"
if grep -qE '^fase_tdd:[[:space:]]*rojo' "$dir/.claude/state/STATE.md" 2>/dev/null; then
  targets="lint typecheck"
fi

if ! out="$(make -C "$dir" --no-print-directory $targets 2>&1)"; then
  printf 'Gate de cierre de turno en rojo (make %s). Diagnostica la causa real; no toques el test:\n%s\n' \
    "$targets" "$(printf '%s' "$out" | tail -40)" >&2
  exit 2
fi
exit 0
