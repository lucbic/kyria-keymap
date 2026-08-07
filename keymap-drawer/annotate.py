"""Post-processes the parsed keymap YAML before drawing.

Two things keymap-drawer leaves on the table:

  * `sensor-bindings` are not parsed, so the rotary encoders are read out of the
    keymap here and placed on the key positions they occupy, clockwise legend
    above the knob and counter-clockwise below.

  * A combo is drawn as a box with one line per key it triggers on. Instead, the
    keys themselves are marked so they can be ringed, the box is relabelled with
    what the combo *does* (from its node name in the keymap) over the keystroke
    it sends, and the lines are turned off -- leaders.py draws a single one.
"""

import re
import sys
from pathlib import Path

import yaml

# The encoders replace these two switch positions: the outermost thumb key of
# each half. They are unbound on every layer for that reason.
ENCODER_POSITIONS = [40, 49]

# What each knob is for, by layer and side. The directions come from the keymap;
# only the intent has to be written down.
KNOB_INTENTS = {
    ("Base", 0): "Switch desktop",
    ("Base", 1): "Scroll",
    ("Symbols", 1): "Volume",
    ("Numbers", 1): "Brightness",
    ("Navigation", 0): "Scroll ×5",
    ("Function", 0): "Word jump",
    ("Mouse", 0): "Scroll ↕",
    ("Mouse", 1): "Scroll ↔",
}

# Chords whose keystroke does not say what it is for. Keyed on the legend as
# drawn, so one entry covers every layer the chord appears on.
MEANINGS = {
    "⌘X": "cut", "⌘C": "copy", "⌘V": "paste", "⌘Z": "undo", "⌘⇧Z": "redo",
    "⌘⇧3": "screenshot", "⌘⇧4": "snip", "⌘⇥": "app switch", "⌘␣": "search",
    "⌃\\": "left bar", "⌃⇧\\": "right bar",
    "⌃1": "desktop 1", "⌃2": "desktop 2", "⌃3": "desktop 3", "⌃4": "desktop 4",
    "⌃⌥←": "desktop ←", "⌃⌥→": "desktop →",
    "⌥←": "word ←", "⌥→": "word →",
    "⌥⇧←": "sel word", "⌥⇧→": "sel word",
    "⌥⌫": "del word", "⌥⌦": "del word",
    "⌘⇧D": "duplicate", "⌘/": "comment", "⌘]": "indent", "⌘[": "dedent",
    "F19": "sleep",
}

MOD_GLYPHS = {"LC": "⌃", "RC": "⌃", "LS": "⇧", "RS": "⇧", "LA": "⌥", "RA": "⌥", "LG": "⌘", "RG": "⌘"}

# A knob legend reads "↺ x ↻ y", and keymap-drawer can only take a glyph as a
# whole legend, so keycodes drawn as icons turn into a sign here instead. The
# card's title already says which quantity is going up or down.
GLYPH_WORDS = {
    "$$tabler:volume$$": "+",
    "$$tabler:volume-2$$": "−",
    "$$tabler:sun-high$$": "+",
    "$$tabler:sun-low$$": "−",
}

# The trackpad is not a key, so it gets a position of its own at the end of the
# physical layout and a card saying what mode the active layer puts it in.
TRACKPAD_POSITION = 50

# A group of keys that share a scheme reads better with the scheme stated once
# beside them than repeated on every key. leaders.py rings the keys and draws
# the card; the keys themselves are then free to carry only what they do.
ROW_SEPARATOR = " ‖ "  # packs the rows into one legend for leaders.py to unpack

NOTES = [
    {
        "layer": "Navigation",
        "positions": [2, 3, 4, 26, 28],  # snap / maximize / snap, and the panes
        "title": "Window management",
        # (how the key is pressed, what it does, what the Mac receives)
        "rows": [
            ("tap", "Snap half", "⌥⌘ ← →"),
            ("tap", "Maximize", "⌥⌘ ↑"),
            ("tap", "New pane", "⌃⌘ ← →"),
            ("hold", "Send to other display", "⌥⌃⌘ ← →"),
        ],
    },
]


def plain(label):
    if label in GLYPH_WORDS:
        return GLYPH_WORDS[label]
    return label.split(":")[-1].strip("$").replace("-", " ") if label.startswith("$$") else label


def fmt_keycode(code, keycode_map):
    if mod := re.fullmatch(r"([LR][CSAG])\((.+)\)", code):
        return MOD_GLYPHS[mod.group(1)] + fmt_keycode(mod.group(2), keycode_map)
    return keycode_map.get(code, code.replace("_", " "))


def fmt_binding(binding, keycode_map):
    parts = binding.split()
    return fmt_keycode(parts[1], keycode_map) if len(parts) > 1 else ""


def encoder_labels(sensor_binding, keymap_src, keycode_map):
    """Return (clockwise, counter-clockwise) labels for one sensor binding."""
    parts = sensor_binding.split()
    if parts[0] == "&inc_dec_kp":
        return fmt_keycode(parts[1], keycode_map), fmt_keycode(parts[2], keycode_map)

    # Any other sensor behavior: resolve the two bindings it rotates between.
    behavior = re.search(rf"{parts[0][1:]}:\s*\w+\s*{{(.*?)}};", keymap_src, re.S)
    if behavior and (binds := re.search(r"bindings\s*=\s*(.*?);", behavior.group(1), re.S)):
        pair = re.findall(r"<([^>]*)>", binds.group(1))
        if len(pair) == 2:
            return tuple(fmt_binding(b, keycode_map) for b in pair)
    return "", ""


# Combo legends wrap to at most two lines, so node names that humanize into
# three or more words need a shorter form. The keystroke below them disambiguates.
COMBO_LABELS = {
    "FocusNextPane": "Next pane",
    "FocusPreviousPane": "Prev pane",
    "CommentSelectedLines": "Comment lines",
    "DelPrevWord": "Delete back",
    "DelNextWord": "Delete forward",
}


def combo_names(keymap_src):
    """Combo node names, in the order keymap-drawer parses them."""
    combos = re.search(r"combos\s*{(.*?)\n    };", keymap_src, re.S)
    if not combos:
        return []
    return re.findall(r"(\w+)\s*{\s*bindings", combos.group(1))


def humanize(name):
    if name in COMBO_LABELS:
        return COMBO_LABELS[name]
    words = re.findall(r"[A-Z]+(?![a-z])|[A-Z][a-z]*|\d+", name) or [name]
    return " ".join([words[0]] + [w.lower() for w in words[1:]])


def trackpad_modes(dtsi_src, layer_names):
    """Layer name -> (mode, detail), read off the Cirque input listener."""
    listener = re.search(r"glidepoint_listener\s*{(.*)}", dtsi_src, re.S)
    if not listener:
        return {}
    body = listener.group(1)
    base = re.search(r"input-processors\s*=\s*<&zip_xy_scaler (\d+) (\d+)>", body)
    default = ("Pointer", f"{base.group(1)}:{base.group(2)}") if base else ("Pointer", "")
    modes = dict.fromkeys(layer_names, default)

    for name, node in re.findall(r"(\w+)\s*{\s*(layers\s*=.*?)};", body, re.S):
        layers = re.search(r"layers\s*=\s*<([\d ]+)>", node)
        processors = re.search(r"input-processors\s*=\s*(.*?);", node, re.S)
        if not layers or not processors:
            continue
        scaler = re.search(r"zip_xy_scaler (\d+) (\d+)", processors.group(1))
        mode = (name.replace("_mode", "").replace("_", " ").capitalize(),
                f"{scaler.group(1)}:{scaler.group(2)}" if scaler else "wheel")
        for index in (int(i) for i in layers.group(1).split()):
            if index < len(layer_names):
                modes[layer_names[index]] = mode
    return modes


def layer_sensors(keymap_src):
    """Map layer label -> list of sensor binding strings, in sensor order."""
    sensors = {}
    for chunk in re.split(r"\n\s*\w+_layer\s*{", keymap_src)[1:]:
        label = re.search(r'label\s*=\s*"([^"]+)"', chunk)
        binds = re.search(r"sensor-bindings\s*=\s*(.*?);", chunk, re.S)
        if label and binds:
            sensors[label.group(1)] = re.findall(r"<([^>]*)>", binds.group(1))
    return sensors


def main(yaml_path, keymap_path, config_path):
    km = yaml.safe_load(open(yaml_path))
    keymap_src = open(keymap_path).read()
    keycode_map = yaml.safe_load(open(config_path))["parse_config"]["zmk_keycode_map"]

    # every hold legend moves to the bottom-right corner, and chords that don't
    # explain themselves get a note in the bottom-left one
    for keys in km["layers"].values():
        for position, key in enumerate(keys):
            if not isinstance(key, dict):
                key = {"t": key}
            # a glyph tucks into the corner; a word like "Navigation" would not fit
            if key.get("h") and len(key["h"]) <= 3:
                key = {**key, "br": key["h"], "h": ""}
            # only when the bottom of the key is free -- a hold legend that had to
            # stay centred already fills it
            if MEANINGS.get(key.get("t")) and not any(key.get(slot) for slot in ("bl", "h")):
                key = {**key, "bl": MEANINGS[key["t"]]}
            keys[position] = key

    # knobs: the face stays clean, a legend box says what turning it does
    sensors = layer_sensors(keymap_src)
    knob_legends = []
    for layer, keys in km["layers"].items():
        bindings = sensors.get(layer, [])
        for index, position in enumerate(ENCODER_POSITIONS):
            keys[position] = {"type": "encoder"}
            if index >= len(bindings):
                continue
            cw, ccw = encoder_labels(bindings[index], keymap_src, keycode_map)
            if not cw and not ccw:
                continue
            knob_legends.append({
                "p": [position, position],  # keymap-drawer wants two positions
                "k": {
                    "t": KNOB_INTENTS.get((layer, index), ""),
                    "s": f"↻ {plain(cw)}",  # clockwise above the intent,
                    "h": f"↺ {plain(ccw)}",  # counter-clockwise below it
                },
                "l": [layer],
                "type": "knob",
                "d": False,
                "w": 132,
                "height": 80,  # four stacked lines
            })

    # the trackpad: one more position on the board, with a card for its mode
    modes = trackpad_modes(open(Path(keymap_path).parent / "shared.dtsi").read(), list(km["layers"]))
    pad_legends = []
    for layer, keys in km["layers"].items():
        keys.insert(TRACKPAD_POSITION, {"type": "trackpad"})
        mode, detail = modes.get(layer, ("", ""))
        pad_legends.append({
            "p": [TRACKPAD_POSITION, TRACKPAD_POSITION],
            "k": {"t": mode, "h": detail},
            "l": [layer],
            "type": "pad",
            "d": False,
        })

    # explanatory cards; leaders.py replaces the contents with the rows it finds
    # in the hold slot, so what is written here is only a placeholder
    note_legends = []
    for note in NOTES:
        if note["layer"] not in km["layers"]:
            continue
        note_legends.append({
            "p": note["positions"],
            "k": {"t": note["title"], "h": ROW_SEPARATOR.join("\t".join(row) for row in note["rows"])},
            "l": [note["layer"]],
            "type": "note",
            "d": False,
            "w": 268,
            "height": 110 + 20 * (len(note["rows"]) - 1),
        })

    base_layer = next(iter(km["layers"]))
    names = combo_names(keymap_src)
    for index, combo in enumerate(km.get("combos", [])):
        keystroke = combo["k"]
        combo["k"] = {
            "t": humanize(names[index]) if index < len(names) else keystroke,
            "h": keystroke if index < len(names) else "",
        }
        combo["d"] = False  # leaders.py draws one line instead of one per key
        # a combo with no layer list is live everywhere; drawing it on all six
        # diagrams is just noise, so it is shown on the base layer only
        if not combo.get("l"):
            combo["l"] = [base_layer]

    km["combos"] = km.get("combos", []) + knob_legends + pad_legends + note_legends

    yaml.safe_dump(km, open(yaml_path, "w"), sort_keys=False, allow_unicode=True, width=200)


if __name__ == "__main__":
    main(*sys.argv[1:])
