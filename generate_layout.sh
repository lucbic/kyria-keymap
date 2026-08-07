#!/bin/bash
# Renders one SVG per layer (plus a combos diagram) into ./layouts/ with keymap-drawer.
# Install: pipx install keymap-drawer
set -euo pipefail

KEYMAP=./config/kyria_rev3.keymap
CONFIG=./keymap-drawer/config.yaml
LAYOUT=./keymap-drawer/kyria_rev3_layout.json
OUT=./layouts
YAML=$OUT/keymap.yaml

command -v keymap >/dev/null || { echo "keymap-drawer not found: pipx install keymap-drawer"; exit 1; }

mkdir -p "$OUT"
keymap -c "$CONFIG" parse -z "$KEYMAP" >"$YAML"

# Adds the encoders and labels combos with their layer -- see annotate.py.
python3 ./keymap-drawer/annotate.py "$YAML" "$KEYMAP" "$CONFIG"

for layer in Base Symbols Numbers Navigation Function Mouse; do
    svg="$OUT/$(echo "$layer" | tr '[:upper:]' '[:lower:]').svg"
    keymap -c "$CONFIG" draw "$YAML" -j "$LAYOUT" -s "$layer" >"$svg"
    python3 ./keymap-drawer/leaders.py "$layer" "$YAML" "$svg"
done

echo "wrote $OUT/{base,symbols,numbers,navigation,function,mouse}.svg"
