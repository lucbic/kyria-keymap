/*
 * Copyright (c) 2026 The ZMK Contributors
 *
 * SPDX-License-Identifier: MIT
 */

#define DT_DRV_COMPAT zmk_behavior_caps_clear

#include <zephyr/device.h>
#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>
#include <zephyr/usb/class/hid.h>

#include <drivers/behavior.h>
#include <dt-bindings/zmk/keys.h>
#include <zmk/behavior.h>
#include <zmk/behavior_queue.h>
#include <zmk/event_manager.h>
#include <zmk/events/keycode_state_changed.h>
#include <zmk/hid.h>
#include <zmk/keymap.h>
#include <zmk/keys.h>

#if IS_ENABLED(CONFIG_ZMK_HID_INDICATORS)
#include <zmk/hid_indicators.h>
#endif // IS_ENABLED(CONFIG_ZMK_HID_INDICATORS)

LOG_MODULE_DECLARE(zmk, CONFIG_ZMK_LOG_LEVEL);

#if DT_HAS_COMPAT_STATUS_OKAY(DT_DRV_COMPAT)

// Behavior parameter: which action this invocation performs.
#define CAPS_MODE_TAP 0  // clear whichever caps state is on, else sticky shift
#define CAPS_MODE_WORD 1 // toggle caps word

// Indices into the DT `bindings` array.
#define BINDING_CAPS 0  // the caps lock key press
#define BINDING_SHIFT 1 // sticky shift
#define BINDING_WORD 2  // caps word
#define BINDING_COUNT 3

struct behavior_caps_clear_config {
    uint32_t tap_ms;
    uint32_t wait_ms;
    const struct zmk_behavior_binding *bindings;
};

// Shadow of caps word's active state.
//
// ZMK keeps that state file-static in behavior_caps_word.c and exposes neither a
// getter nor an event, so we cannot ask it. Instead we mirror it: set the flag when
// we turn caps word on, and clear it on any keycode that ZMK itself would cancel
// caps word for. The rule below is a copy of behavior_caps_word.c:148-154 and is only
// correct because config/west.yml pins an exact ZMK revision.
static bool caps_word_active = false;

static bool is_alpha(uint32_t usage_id) {
    return usage_id >= HID_USAGE_KEY_KEYBOARD_A && usage_id <= HID_USAGE_KEY_KEYBOARD_Z;
}

static bool is_numeric(uint32_t usage_id) {
    return usage_id >= HID_USAGE_KEY_KEYBOARD_1_AND_EXCLAMATION &&
           usage_id <= HID_USAGE_KEY_KEYBOARD_0_AND_RIGHT_PARENTHESIS;
}

// Mirrors caps word's default continue-list: <UNDERSCORE BACKSPACE DELETE>.
// UNDERSCORE is MINUS carrying an implicit left shift, so it needs the same
// modifier test upstream applies rather than a bare keycode comparison.
static bool is_continue(const struct zmk_keycode_state_changed *ev) {
    if (ev->usage_page != HID_USAGE_KEY) {
        return false;
    }

    if (ev->keycode == ZMK_HID_USAGE_ID(BACKSPACE) || ev->keycode == ZMK_HID_USAGE_ID(DELETE)) {
        return true;
    }

    if (ev->keycode == ZMK_HID_USAGE_ID(MINUS)) {
        const uint8_t mods = ev->implicit_modifiers | zmk_hid_get_explicit_mods();
        return (mods & MOD_LSFT) == MOD_LSFT;
    }

    return false;
}

static int caps_clear_keycode_listener(const zmk_event_t *eh) {
    const struct zmk_keycode_state_changed *ev = as_zmk_keycode_state_changed(eh);
    if (ev == NULL || !ev->state || !caps_word_active) {
        return ZMK_EV_EVENT_BUBBLE;
    }

    if (!is_alpha(ev->keycode) && !is_numeric(ev->keycode) &&
        !is_mod(ev->usage_page, ev->keycode) && !is_continue(ev)) {
        LOG_DBG("caps word cancelled by 0x%02X - 0x%02X", ev->usage_page, ev->keycode);
        caps_word_active = false;
    }

    return ZMK_EV_EVENT_BUBBLE;
}

ZMK_LISTENER(behavior_caps_clear, caps_clear_keycode_listener);
ZMK_SUBSCRIPTION(behavior_caps_clear, zmk_keycode_state_changed);

static bool caps_lock_is_on(void) {
#if IS_ENABLED(CONFIG_ZMK_HID_INDICATORS)
    return (zmk_hid_indicators_get_current_profile() & HID_KBD_LED_CAPS_LOCK) != 0;
#else
    // Without host LED feedback the lock state is unknowable. Reporting "off" keeps
    // the tap useful (it still clears caps word and applies sticky shift) instead of
    // toggling a lock we cannot see.
    return false;
#endif // IS_ENABLED(CONFIG_ZMK_HID_INDICATORS)
}

static void tap(const struct zmk_behavior_binding_event *event,
                const struct behavior_caps_clear_config *cfg, int index) {
    zmk_behavior_queue_add(event, cfg->bindings[index], true, cfg->tap_ms);
    zmk_behavior_queue_add(event, cfg->bindings[index], false, cfg->wait_ms);
}

static int on_caps_clear_binding_pressed(struct zmk_behavior_binding *binding,
                                         struct zmk_behavior_binding_event event) {
    const struct device *dev = zmk_behavior_get_binding(binding->behavior_dev);
    const struct behavior_caps_clear_config *cfg = dev->config;

    if (binding->param1 == CAPS_MODE_WORD) {
        // caps word is itself a toggle, so this turns it off again on a second use.
        caps_word_active = !caps_word_active;
        LOG_DBG("caps word -> %s", caps_word_active ? "on" : "off");
        tap(&event, cfg, BINDING_WORD);
        return ZMK_BEHAVIOR_OPAQUE;
    }

    if (caps_lock_is_on()) {
        LOG_DBG("caps lock on, clearing");
        tap(&event, cfg, BINDING_CAPS);
    } else if (caps_word_active) {
        LOG_DBG("caps word on, clearing");
        caps_word_active = false;
        tap(&event, cfg, BINDING_WORD);
    } else {
        LOG_DBG("nothing active, sticky shift");
        tap(&event, cfg, BINDING_SHIFT);
    }

    return ZMK_BEHAVIOR_OPAQUE;
}

static int on_caps_clear_binding_released(struct zmk_behavior_binding *binding,
                                          struct zmk_behavior_binding_event event) {
    return ZMK_BEHAVIOR_OPAQUE;
}

static const struct behavior_driver_api behavior_caps_clear_driver_api = {
    .binding_pressed = on_caps_clear_binding_pressed,
    .binding_released = on_caps_clear_binding_released,
};

#define _EXTRACT_BINDING(idx, node) ZMK_KEYMAP_EXTRACT_BINDING(idx, node)

#define CC_INST(n)                                                                                 \
    BUILD_ASSERT(DT_INST_PROP_LEN(n, bindings) == BINDING_COUNT,                                   \
                 "caps-clear needs exactly three bindings: caps lock, sticky shift, caps word");   \
    static const struct zmk_behavior_binding behavior_caps_clear_bindings_##n[] = {                \
        LISTIFY(DT_INST_PROP_LEN(n, bindings), _EXTRACT_BINDING, (, ), DT_DRV_INST(n))};           \
    static const struct behavior_caps_clear_config behavior_caps_clear_config_##n = {              \
        .tap_ms = DT_INST_PROP(n, tap_ms),                                                         \
        .wait_ms = DT_INST_PROP(n, wait_ms),                                                       \
        .bindings = behavior_caps_clear_bindings_##n,                                              \
    };                                                                                             \
    BEHAVIOR_DT_INST_DEFINE(n, NULL, NULL, NULL, &behavior_caps_clear_config_##n, POST_KERNEL,     \
                            CONFIG_KERNEL_INIT_PRIORITY_DEFAULT,                                   \
                            &behavior_caps_clear_driver_api);

DT_INST_FOREACH_STATUS_OKAY(CC_INST)

#endif // DT_HAS_COMPAT_STATUS_OKAY(DT_DRV_COMPAT)
