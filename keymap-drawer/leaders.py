"""Places each combo legend in open space and links it with a single leader line.

keymap-drawer draws a combo as a box plus one line per key it triggers on, which
gets busy fast. annotate.py turns those lines off and marks the trigger keys so
they can be ringed instead; this script then reads the geometry back out of the
rendered SVG, moves each legend to the nearest spot that clears every key and
every other legend, and draws one line from it to the nearest key it belongs to.
The line is only kept if it crosses nothing on the way.

Usage: leaders.py <layer name> <keymap.yaml> <layer.svg>
"""

import math
import re
import sys

import yaml

KEY_CLEARANCE = 14  # px kept between a legend and any key
BOX_CLEARANCE = 12  # px kept between two legends
HULL_MARGIN = 6  # px the outline stands off the keycaps; must exceed half the
                 # gutter between keys so neighbouring rings intersect and merge
HULL_RADIUS = 9  # px corner rounding on that outline
STEP = 10  # px granularity of the outward search
MAX_DISTANCE = 620  # px; give up past this
DIRECTIONS = [(math.sin(a * math.pi / 8), -math.cos(a * math.pi / 8)) for a in range(16)]

CELL = 8  # px, resolution of the grid a turning leader is routed over
ROUTE_MARGIN = 5  # px that routed leader keeps clear of a key
BESIDE_PENALTY = 3.0  # per px a legend sticks out past the side of the board
TURN_PENALTY = 45  # px-equivalent; a straight leader is worth a longer trip

KEY_RE = re.compile(
    r'<g transform="translate\((-?[\d.]+), (-?[\d.]+)\)(?: rotate\((-?[\d.]+)\))?" class="key ([^"]*)">'
    r'\s*<rect[^>]*width="([\d.]+)" height="([\d.]+)"'
)
COMBO_RE = re.compile(
    r'<g class="combo ([^"]*)combopos-(\d+)">\s*'
    r'<rect[^>]*x="(-?[\d.]+)" y="(-?[\d.]+)" width="([\d.]+)" height="([\d.]+)"'
)


class Box:
    """An axis-aligned box. A key also carries its true size and rotation."""

    def __init__(self, cx, cy, w, h, key_w=None, key_h=None, rotation=0.0):
        self.cx, self.cy, self.w, self.h = cx, cy, w, h
        self.key_w, self.key_h, self.rotation = key_w or w, key_h or h, rotation

    def grown(self, pad):
        return Box(self.cx, self.cy, self.w + 2 * pad, self.h + 2 * pad)

    def overlaps(self, other):
        return (abs(self.cx - other.cx) < (self.w + other.w) / 2
                and abs(self.cy - other.cy) < (self.h + other.h) / 2)

    def contains(self, x, y):
        return abs(x - self.cx) <= self.w / 2 and abs(y - self.cy) <= self.h / 2


def parse_keys(svg):
    """Key boxes by position index, widened to the bounding box when rotated."""
    keys = {}
    for cx, cy, rot, classes, w, h in KEY_RE.findall(svg):
        cx, cy, w, h, rot = float(cx), float(cy), float(w), float(h), float(rot or 0)
        cos, sin = abs(math.cos(math.radians(rot))), abs(math.sin(math.radians(rot)))
        position = int(re.search(r"keypos-(\d+)", classes).group(1))
        keys[position] = Box(cx, cy, w * cos + h * sin, w * sin + h * cos, w, h, rot)
    return keys


def rounded_ring(key, margin):
    """The key's outline, pushed out by `margin`, sampled as a closed polygon."""
    half_w, half_h = key.key_w / 2 + margin, key.key_h / 2 + margin
    radius = min(HULL_RADIUS, half_w, half_h)
    angle = math.radians(key.rotation)
    cos, sin = math.cos(angle), math.sin(angle)
    points = []
    for corner_x, corner_y in ((1, 1), (-1, 1), (-1, -1), (1, -1)):  # one arc per corner
        center = (corner_x * (half_w - radius), corner_y * (half_h - radius))
        for step in range(7):
            theta = math.atan2(corner_y, corner_x) - math.pi / 4 + step * math.pi / 12
            local = (center[0] + radius * math.cos(theta), center[1] + radius * math.sin(theta))
            points.append((key.cx + local[0] * cos - local[1] * sin,
                           key.cy + local[0] * sin + local[1] * cos))
    return points


def inside_key(x, y, key, margin):
    angle = math.radians(-key.rotation)
    dx, dy = x - key.cx, y - key.cy
    local_x = dx * math.cos(angle) - dy * math.sin(angle)
    local_y = dx * math.sin(angle) + dy * math.cos(angle)
    return abs(local_x) <= key.key_w / 2 + margin and abs(local_y) <= key.key_h / 2 + margin


def outline(keys):
    """The boundary of the union of a combo's keys.

    A convex hull would cut the corner off any key that sits between two of them
    on another row, covering its legends; tracing each key's own ring and
    dropping the parts that fall inside another key hugs the group instead.
    """
    segments, points = [], []
    for key in keys:
        ring = rounded_ring(key, HULL_MARGIN)
        others = [k for k in keys if k is not key]
        run = []
        for index, point in enumerate(ring + ring[:1]):
            previous = ring[index - 1]
            midpoint = ((point[0] + previous[0]) / 2, (point[1] + previous[1]) / 2)
            visible = index > 0 and not any(inside_key(*midpoint, k, HULL_MARGIN) for k in others)
            if visible:
                run = run + [point] if run else [previous, point]
            elif run:
                segments.append(run)
                run = []
        if run:
            segments.append(run)
        points += [p for segment in segments for p in segment]
    return segments, points


def outline_path(segments):
    return " ".join("M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in segment) for segment in segments)


def parse_combos(svg):
    return {int(index): Box(float(x) + float(w) / 2, float(y) + float(h) / 2, float(w), float(h))
            for _, index, x, y, w, h in COMBO_RE.findall(svg)}


class Router:
    """Finds a leader that turns corners when no straight one exists.

    A legend beside the board can always be reached in a straight line, which is
    why the search used to put them there. Below the board is the better place,
    but getting back up to the keys means threading the gaps between them. Free
    space is gridded once per legend and flooded outward from the keys it points
    at, so any candidate position can then be routed by walking downhill.
    """

    def __init__(self, obstacles, targets, bounds):
        self.left, self.top, right, bottom = bounds
        self.cols = int((right - self.left) / CELL) + 1
        self.rows = int((bottom - self.top) / CELL) + 1
        blocked = bytearray(self.cols * self.rows)
        for box in obstacles:
            for index in self._cells_of(box):
                blocked[index] = 1

        self.distance = [-1] * (self.cols * self.rows)
        frontier = []
        for key in targets:  # the ring the outline draws is where a leader lands
            for index in self._cells_of(key.grown(HULL_MARGIN)):
                if self.distance[index] < 0:
                    self.distance[index], _ = 0, frontier.append(index)
        while frontier:
            frontier = self._expand(frontier, blocked)

    def _cells_of(self, box):
        first_col = max(0, int((box.cx - box.w / 2 - self.left) / CELL))
        last_col = min(self.cols - 1, int((box.cx + box.w / 2 - self.left) / CELL))
        first_row = max(0, int((box.cy - box.h / 2 - self.top) / CELL))
        last_row = min(self.rows - 1, int((box.cy + box.h / 2 - self.top) / CELL))
        return [row * self.cols + col
                for row in range(first_row, last_row + 1)
                for col in range(first_col, last_col + 1)]

    def _expand(self, frontier, blocked):
        following = []
        for index in frontier:
            for neighbour in self._neighbours(index):
                if self.distance[neighbour] < 0 and not blocked[neighbour]:
                    self.distance[neighbour] = self.distance[index] + 1
                    following.append(neighbour)
        return following

    def _neighbours(self, index):
        col, row = index % self.cols, index // self.cols
        if col:
            yield index - 1
        if col < self.cols - 1:
            yield index + 1
        if row:
            yield index - self.cols
        if row < self.rows - 1:
            yield index + self.cols

    def _point(self, index):
        return (self.left + (index % self.cols) * CELL, self.top + (index // self.cols) * CELL)

    def _reachable(self, indices, box):
        return [(self.distance[i], i) for i in indices
                if self.distance[i] >= 0 and not box.contains(*self._point(i))]

    def route(self, box):
        """Corner points from the edge of `box` to the keys, or None."""
        start = self._reachable(self._cells_of(box.grown(CELL)), box)
        if not start:
            return None
        index, points = min(start)[1], []
        while self.distance[index] > 0:
            points.append(self._point(index))
            step = self._reachable(self._neighbours(index), box)
            if not step or min(step)[0] >= self.distance[index]:
                return None
            index = min(step)[1]
        points.append(self._point(index))
        return points


def square_off(box, point):
    """Where a leader leaves `box` heading for `point`, kept axis-aligned."""
    if abs(point[0] - box.cx) <= box.w / 2:
        return (point[0], box.cy + (box.h / 2 if point[1] > box.cy else -box.h / 2))
    return (box.cx + (box.w / 2 if point[0] > box.cx else -box.w / 2), point[1])


def simplify(points):
    """Drop points that fall on the straight line between their neighbours."""
    kept = points[:1]
    for previous, point, following in zip(points, points[1:], points[2:]):
        if (previous[0] == point[0] == following[0]) or (previous[1] == point[1] == following[1]):
            continue
        kept.append(point)
    return kept + points[-1:]


def polyline(points):
    return "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in points)


def crosses(x1, y1, x2, y2, obstacles):
    """Sample the segment densely enough that no key-sized obstacle slips through."""
    steps = max(int(math.hypot(x2 - x1, y2 - y1) / 3), 1)
    return any(box.contains(x1 + (x2 - x1) * i / steps, y1 + (y2 - y1) * i / steps)
               for i in range(steps + 1) for box in obstacles)


def edge_point(box, toward_x, toward_y):
    """Where the segment to (toward_x, toward_y) leaves the box."""
    dx, dy = toward_x - box.cx, toward_y - box.cy
    if not dx and not dy:
        return box.cx, box.cy
    scale = min(box.w / 2 / abs(dx) if dx else math.inf, box.h / 2 / abs(dy) if dy else math.inf)
    return box.cx + dx * scale, box.cy + dy * scale


def place(combo_box, trigger_keys, all_keys, placed, span):
    """Nearest position clear of every key and legend, and a leader that reaches it.

    The search runs outward from each trigger key rather than from the middle of
    the group: a group sitting inside a hand has no straight line out of its own
    centre, but there is almost always one off the edge of one of its keys.

    Distance alone would park a legend beside the board, where a straight line
    out of the hand always exists. Sticking out past the side is charged for, so
    the space under the board wins even though reaching it needs a turn.
    """
    center_x = sum(k.cx for k in trigger_keys) / len(trigger_keys)
    center_y = sum(k.cy for k in trigger_keys) / len(trigger_keys)
    obstacles = [k.grown(2) for k in all_keys if k not in trigger_keys]
    router = None

    best = None
    for distance in range(STEP, MAX_DISTANCE, STEP):
        for anchor in trigger_keys:
            for dx, dy in DIRECTIONS:
                candidate = Box(anchor.cx + dx * distance, anchor.cy + dy * distance, combo_box.w, combo_box.h)
                if any(candidate.grown(KEY_CLEARANCE).overlaps(k) for k in all_keys):
                    continue
                if any(candidate.grown(BOX_CLEARANCE).overlaps(p) for p in placed):
                    continue
                overhang = (max(0.0, span[0] - candidate.cx + candidate.w / 2)
                            + max(0.0, candidate.cx + candidate.w / 2 - span[1]))
                cost = math.hypot(candidate.cx - center_x, candidate.cy - center_y) \
                    + BESIDE_PENALTY * overhang
                if best and cost >= best[0]:
                    continue

                start = edge_point(candidate, anchor.cx, anchor.cy)
                # stop at the outline, which hugs the anchor key
                end = edge_point(anchor.grown(HULL_MARGIN), candidate.cx, candidate.cy)
                if not crosses(*start, *end, obstacles + placed):
                    best = (cost, candidate, [start, end])
                    continue

                if router is None:
                    router = Router([o.grown(ROUTE_MARGIN - 2) for o in obstacles]
                                    + [p.grown(BOX_CLEARANCE) for p in placed],
                                    trigger_keys, grid_bounds(all_keys))
                path = router.route(candidate)
                if path and cost + TURN_PENALTY < (best[0] if best else math.inf):
                    path = [square_off(candidate, path[0])] + path
                    best = (cost + TURN_PENALTY, candidate, simplify(path))
        # a whole ring further out cannot beat a placement already this close
        if best and best[0] <= distance:
            break
    return best[1:] if best else (None, None)


def grid_bounds(keys):
    """Board bounds with room around them for a legend and its route."""
    left = min(k.cx - k.w / 2 for k in keys) - 460
    right = max(k.cx + k.w / 2 for k in keys) + 460
    top = min(k.cy - k.h / 2 for k in keys) - 200
    bottom = max(k.cy + k.h / 2 for k in keys) + 520
    return left, top, right, bottom


GLYPH_DEF_RE = re.compile(r'<svg id="([^"]+)">\s*<svg([^>]*)>(.*?)</svg>\s*</svg>', re.S)
USE_RE = re.compile(r'<use\s+([^>]*?)/?>')
ATTR_RE = re.compile(r'([\w:-]+)="([^"]*)"')


def inline_glyphs(svg):
    """Paste each icon's paths where it is used, instead of referencing them.

    keymap-drawer emits icons as a nested `<svg>` in `<defs>` plus a `<use>`
    per site. Only full renderers resolve that: rsvg, Quick Look and GitHub's
    sanitiser all drop it, and every icon on the board disappears. Inlining the
    paths at each site makes the diagrams render the same everywhere.
    """
    icons = {}
    for name, attributes, body in GLYPH_DEF_RE.findall(svg):
        keep = {k: v for k, v in ATTR_RE.findall(attributes)
                if k in ("fill", "stroke", "stroke-width", "stroke-linecap", "stroke-linejoin")}
        icons[name] = (" ".join(f'{k}="{v}"' for k, v in keep.items()), body.strip())

    def paste(use):
        attributes = dict(ATTR_RE.findall(use.group(1)))
        icon = icons.get(attributes.get("href", "").lstrip("#"))
        if not icon:
            return use.group(0)
        style, body = icon
        # the icons are drawn on a 24-unit grid; `width` is the size asked for
        scale = float(attributes.get("width", 24)) / 24
        return (f'<g transform="translate({attributes.get("x", 0)}, {attributes.get("y", 0)}) '
                f'scale({scale:.4g})" class="{attributes.get("class", "")}" {style}>{body}</g>')

    svg = USE_RE.sub(paste, svg)
    return re.sub(r"<defs>.*?</defs>", "<defs/>", svg, flags=re.S)  # nothing refers to them now


MARKS = {"tap": "○", "hold": "◉"}  # geometric shapes, not emoji: every renderer has them


def note_card(box, title, rows):
    """Re-draw a note card's insides: a title, marked rows, and a key to the marks.

    keymap-drawer only knows tap/shifted/hold legends, so annotate.py packs the
    rows into the hold slot and the whole group body is replaced here.
    """
    left, right = box.cx - box.w / 2, box.cx + box.w / 2
    top = box.cy - box.h / 2
    parsed = [row.split("\t") for row in rows]
    footer = top + box.h - 22

    out = [f'<rect rx="6" ry="6" x="{left:.0f}" y="{top:.0f}" '
           f'width="{box.w:.0f}" height="{box.h:.0f}" class="combo"/>',
           f'<text x="{box.cx:.0f}" y="{top + 24:.0f}" class="note-title">{title}</text>']
    for index, (kind, label, chord) in enumerate(parsed):
        y = top + 52 + 20 * index
        out.append(f'<text x="{left + 16:.0f}" y="{y:.0f}" class="note-mark {kind}">{MARKS[kind]}</text>')
        out.append(f'<text x="{left + 34:.0f}" y="{y:.0f}" class="note-label">{label}</text>')
        out.append(f'<text x="{right - 16:.0f}" y="{y:.0f}" class="note-chord">{chord}</text>')

    out.append(f'<path d="M{left + 16:.0f},{footer - 17:.0f} L{right - 16:.0f},{footer - 17:.0f}" class="note-rule"/>')
    key = "   ".join(f"{MARKS[kind]} {word}" for kind, word in (("tap", "tap"), ("hold", "hold")))
    out.append(f'<text x="{box.cx:.0f}" y="{footer:.0f}" class="note-key">{key}</text>')
    return "\n".join(out)


def upright_marks(svg):
    """Counter-rotate single-glyph legends on rotated keys.

    The thumb fan is rotated up to 45 degrees and glyphs rotate with it, which
    turns ✕ into +, ▽ into ▷, and tips ⌫ on its side. Words and icons keep the
    key's angle; a lone glyph reads better upright.
    """
    def fix(group):
        rotation = float(group.group(1))
        return group.group(0).replace(
            group.group(2),
            re.sub(r'<text x="0" y="(-?[\d.]+)" (class="key[^"]*tap")>(.)</text>',
                   lambda t: f'<text x="0" y="{t.group(1)}" {t.group(2)} '
                             f'transform="rotate({-rotation:g}, 0, {float(t.group(1)) - 5:g})">{t.group(3)}</text>',
                   group.group(2)))
    return re.sub(r'<g transform="[^"]*rotate\((-?[\d.]+)\)" class="key [^"]*">(.*?)</g>',
                  fix, svg, flags=re.S)


def main(layer, yaml_path, svg_path):
    svg = inline_glyphs(upright_marks(open(svg_path).read()))
    km = yaml.safe_load(open(yaml_path))
    combos = [c for c in km.get("combos", []) if not c.get("l") or layer in c["l"]]

    keys, boxes = parse_keys(svg), parse_combos(svg)
    placed, moves, overlay, hull_points, rewrites = [], {}, [], [], {}
    span = (min(k.cx - k.w / 2 for k in keys.values()), max(k.cx + k.w / 2 for k in keys.values()))
    bottom = max(k.cy + k.h / 2 for k in keys.values())

    # knob and pad cards first: they hang off one thing at the edge of the board
    # and have the fewest places to go, so no combo legend should box them in
    priority = {"knob": 0, "pad": 1, "note": 2}
    for index in sorted(boxes, key=lambda i: priority.get(combos[i].get("type"), 3)):
        combo, box = combos[index], boxes[index]
        positions = list(dict.fromkeys(combo["p"]))  # a knob legend repeats its one position
        trigger_keys = [keys[p] for p in positions if p in keys]
        card = combo.get("type")  # "knob" / "pad" cards point at one round thing
        if card in (None, "note"):  # which needs no outline; key groups do
            segments, points = outline(trigger_keys)
            hull_points += points
            klass = "combo-outline note" if card == "note" else "combo-outline"
            overlay.append(f'<path d="{outline_path(segments)}" class="{klass}"/>')
        if card == "note":
            rewrites[index] = note_card(box, combo["k"]["t"], combo["k"]["h"].split(" ‖ "))
            # a note is a reference, not a callout: it sits in the corner under
            # the board, and the ring round its keys is the only tie it needs
            target = Box(span[1] - box.w / 2, bottom + 28 + box.h / 2, box.w, box.h)
            placed.append(target)
            moves[index] = (target.cx - box.cx, target.cy - box.cy)
            continue

        target, path = place(box, trigger_keys, list(keys.values()), placed, span)
        if target is None:
            print(f"  {svg_path}: no clear spot for combo {index}, left in place", file=sys.stderr)
            placed.append(box)
            continue
        placed.append(target)
        moves[index] = (target.cx - box.cx, target.cy - box.cy)
        leader_class = f"combo-leader {card}" if card else "combo-leader"
        overlay.append(f'<path d="{polyline(path)}" class="{leader_class}"/>')

    for index, body in rewrites.items():
        svg = re.sub(rf'(<g class="combo [^"]*combopos-{index}">\n).*?(</g>)',
                     lambda m: m.group(1) + body + "\n" + m.group(2), svg, flags=re.S)

    for index, (dx, dy) in moves.items():  # the class carries the combo type, so match it loosely
        svg = re.sub(rf'<g class="(combo [^"]*combopos-{index})">',
                     rf'<g class="\1" transform="translate({dx:.1f},{dy:.1f})">', svg)

    # outlines and leaders go in before the boxes, so the boxes paint over them
    svg = svg.replace('<g class="combo ', "\n".join(overlay) + '\n<g class="combo ', 1)
    open(svg_path, "w").write(resize(svg, keys, placed, hull_points))


def resize(svg, keys, boxes, hull_points):
    """Grow the canvas so relocated legends and outlines stay inside it."""
    all_boxes = list(keys.values()) + boxes
    min_x = min([b.cx - b.w / 2 for b in all_boxes] + [p[0] for p in hull_points])
    max_x = max([b.cx + b.w / 2 for b in all_boxes] + [p[0] for p in hull_points])
    min_y = min([b.cy - b.h / 2 for b in all_boxes] + [p[1] for p in hull_points])
    max_y = max([b.cy + b.h / 2 for b in all_boxes] + [p[1] for p in hull_points])

    pad_x, label_h, pad_y = 20, 44, 20
    inner = re.search(r'<g transform="translate\(0, [\d.]+\)">', svg)
    svg = svg[: inner.start()] + f'<g transform="translate({-min_x:.1f}, {label_h - min_y:.1f})">' + svg[inner.end():]
    width, height = max_x - min_x + 2 * pad_x, max_y - min_y + label_h + pad_y
    return re.sub(r'^<svg width="[\d.]+" height="[\d.]+" viewBox="[^"]*"',
                  f'<svg width="{width:.0f}" height="{height:.0f}" viewBox="0 0 {width:.0f} {height:.0f}"',
                  svg, count=1)


if __name__ == "__main__":
    main(*sys.argv[1:])
