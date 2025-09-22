# Repository Guidelines

## Project Structure & Module Organization
- `config/` holds the Kyria Rev3 keymap (`kyria_rev3.keymap`), device-tree overlays, per-half configs, and the `west.yml` manifest that pins firmware modules.
- ZMK sources and addons live under `zmk/`, `zmk-helpers/`, `cirque-input-module/`, and `zmk-dongle-display/`; treat these as west-managed dependencies and avoid manual edits.
- Build artifacts land in `build_left/`, `build_right/`, and final UF2s in `output/`; remove or regenerate these rather than committing.
- `layouts/` stores rendered layer diagrams from `generate_layout.sh`; `boards/` and `modules/` mirror upstream Zephyr structure when adding custom shields or modules.

## Build, Test, and Development Commands
- `./build.sh` provisions the Python venv, updates west, and produces left/right UF2 firmware in `output/` for quick iteration.
- `./build_debug.sh` adds prerequisite checks, USB logging snippets, and verbose diagnostics—use when investigating build or runtime issues.
- `west update` (run inside the repo root) syncs the Zephyr and module revisions defined in `config/west.yml` after dependency changes.
- `./generate_layout.sh` calls `zmk-viewer` to refresh the layer PNGs under `layouts/` after keymap edits.

## Coding Style & Naming Conventions
- Follow ZMK device-tree conventions: 4-space indentation, lowercase node labels (`hm_l`), uppercase macros/constants (`HM_TAPPING_TERM`).
- Group related `#define` macros and maintain alignment to keep key position arrays scannable.
- Shell scripts use bash with `set -e`/`set -ex`; keep functions idempotent and prefer POSIX-safe patterns.

## Testing Guidelines
- Primary verification is a clean `./build.sh`; ensure both halves complete and UF2 sizes look consistent via `ls -lh output/`.
- For deeper checks, run `./build_debug.sh` to surface toolchain issues and confirm logging snippets compile.
- Flash each half with the generated UF2 files and exercise layer combos, trackpad behavior, and RGB modes before merging substantial changes.

## Commit & Pull Request Guidelines
- Match existing history: concise imperatives with optional scopes, e.g. `feat(trackpad): tune glidepoint gain` or `fix: adjust homerow timing`.
- Limit commits to a focused change; mention affected layers or modules in the body when context helps reviewers.
- PRs should describe the motivation, list user-facing effects, note any required hardware validation, and attach updated layout PNGs or console logs when relevant.
