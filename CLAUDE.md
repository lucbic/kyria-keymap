# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a ZMK (Zephyr Mechanical Keyboard) firmware configuration for a Kyria Rev3 split keyboard with advanced features including:
- Homerow mods with timeless configuration
- Layer-based navigation and symbols
- Cirque Pinnacle trackpad integration
- RGB underglow support
- Rotary encoder support
- Custom behaviors and combos

## Build Commands

### Primary Build Command
```bash
./build.sh
```
This script builds firmware for both keyboard halves (left and right) and outputs UF2 files to the `output/` directory.

### Debug Build Command
```bash
./build_debug.sh
```
Enhanced build script with additional checks, verbose output, and debug features including USB logging.

### Layout Generation
```bash
./generate_layout.sh
```
Generates visual keyboard layout images using zmk-viewer.

### Build System Details
- Uses West build system (Zephyr's meta-tool)
- Targets `nice_nano_v2` controller board
- Builds separate firmware for left and right halves
- Left half: `kyria_rev3_left` + `dongle_display` shields
- Right half: `kyria_rev3_right` shield with Cirque trackpad module
- Output: UF2 files in `output/zmk_left.uf2` and `output/zmk_right.uf2`

## Architecture

### Configuration Structure
- `config/kyria_rev3.keymap` - Main keymap definition with 6 layers
- `config/shared.dtsi` - Shared device tree configuration for trackpad and input processing
- `config/kyria_rev3_left.conf` - Left half configuration (display, RGB, trackpad)
- `config/kyria_rev3_right.conf` - Right half configuration (RGB, trackpad)
- `config/west.yml` - West manifest defining ZMK and module dependencies

### Key Features
- **Homerow Mods**: Balanced hold-tap behaviors with 300ms timing
- **Layer System**: 
  - Layer 0: Base (QWERTY)
  - Layer 1: Symbols
  - Layer 2: Numbers
  - Layer 3: Navigation
  - Layer 4: Special/Function keys
  - Layer 5: Warp (fast mouse movement)
- **Trackpad Integration**: Cirque Pinnacle with layer-dependent behavior modes
- **Custom Behaviors**: Shift hold-tap, encoder mousewheel, custom macros

### Module Dependencies
- `zmk` - Main ZMK firmware (zmkfirmware/zmk)
- `zmk-helpers` - Helper utilities (urob/zmk-helpers)
- `cirque-input-module` - Trackpad support (petejohanson/cirque-input-module)
- `zmk-dongle-display` - Display support (englmaxi/zmk-dongle-display)

### Development Environment
- Requires Python 3.x with virtual environment
- Uses GNU ARM Embedded toolchain via Homebrew
- West build system for Zephyr
- CMake and Ninja for build process

## Key Code Patterns

### Keymap Layer Structure
Layers are defined in `config/kyria_rev3.keymap` with each layer containing:
- `bindings` array defining key behavior per position
- Optional `sensor-bindings` for rotary encoder behavior
- `label` for layer identification

### Homerow Mods Configuration
```c
hm_l: homerow_mods_left {
    compatible = "zmk,behavior-hold-tap";
    tapping-term-ms = <HM_TAPPING_TERM>;
    hold-trigger-key-positions = <KEYS_R KEYS_RT>;
    // ... additional configuration
};
```

### Trackpad Input Processing
Located in `config/shared.dtsi`, defines different input processing modes:
- Base mode: 3x2 scaling
- Scroll mode: Layer 1 - converts XY movement to scroll
- Warp mode: Layer 5 - 2x1 scaling for fast movement
- Precision mode: Layer 2 - 5x4 scaling for fine control

### Build Environment Variables
```bash
ZEPHYR_TOOLCHAIN_VARIANT=gnuarmemb
GNUARMEMB_TOOLCHAIN_PATH=/opt/homebrew
```

## Testing and Debugging

### Build Verification
- UF2 files are generated in `output/` directory
- File sizes should be reasonable (typically 200-400KB)
- Both left and right builds must succeed

### Common Issues
- Missing ARM toolchain: Install with `brew install armmbed/formulae/arm-none-eabi-gcc`
- West initialization: Run `west init -l ./config` if `.west` directory missing
- Module updates: Run `west update` to sync dependencies

### Layout Testing
Use `generate_layout.sh` to create visual representations of keymap layers for validation.

## File Organization

### Config Files
- `config/` - All keyboard configuration
- `output/` - Generated UF2 firmware files
- `build_left/`, `build_right/` - Build artifacts
- `layouts/` - Generated layout images

### Module Structure
- `zmk/` - Main ZMK firmware
- `zmk-helpers/` - Community helper utilities
- `cirque-input-module/` - Trackpad driver
- `zmk-dongle-display/` - Display functionality

The codebase follows ZMK conventions with device tree configuration and Zephyr RTOS patterns.