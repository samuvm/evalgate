#!/usr/bin/env bash
# Instala el gobierno mínimo de D-09 (CONSTITUCION §9, pasos 3, 4 y 7). LO EJECUTA SAMUEL, no el agente:
# el agente nunca escribe en su propio guardián. Idempotente; hace copia de seguridad de settings.json.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
gates="$HOME/.claude/gates"
settings="$HOME/.claude/settings.json"

mkdir -p "$gates"
install -m 0755 "$here/c-turn.sh" "$gates/c-turn.sh"
install -m 0644 "$here/builder.settings.json" "$gates/builder.settings.json"
install -m 0644 "$here/qa.settings.json" "$gates/qa.settings.json"

backup="$settings.bak-$(date +%Y%m%d-%H%M%S)"
cp "$settings" "$backup"
/usr/bin/python3 - "$settings" "$here/user-settings.snippet.json" <<'PY'
import json, sys
settings_path, snippet_path = sys.argv[1], sys.argv[2]
settings = json.load(open(settings_path))
snippet = json.load(open(snippet_path))
perms = settings.setdefault("permissions", {})
for key in ("deny", "ask"):
    current = perms.setdefault(key, [])
    current += [rule for rule in snippet["permissions"][key] if rule not in current]
stop = settings.setdefault("hooks", {}).setdefault("Stop", [])
command = snippet["hooks"]["Stop"][0]["hooks"][0]["command"]
if not any(h.get("command") == command for group in stop for h in group.get("hooks", [])):
    stop += snippet["hooks"]["Stop"]
json.dump(settings, open(settings_path, "w"), indent=2, ensure_ascii=False)
print(f"settings.json actualizado: {len(perms['deny'])} deny, {len(perms['ask'])} ask, hook Stop presente")
PY
echo "copia de seguridad: $backup"
echo "Siguiente paso: abrir las sesiones con los alias del README (perfil constructor y perfil qa)."
