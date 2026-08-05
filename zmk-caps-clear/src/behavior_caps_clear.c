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

#if IS_ENABLED(CONFIG_ZMK_HID_INDICATORS)
#include <zmk/hid_indicators.h>
#endif // IS_ENABLED(CONFIG_ZMK_HID_INDICATORS)

LOG_MODULE_DECLARE(zmk, CONFIG_ZMK_LOG_LEVEL);

#if DT_HAS_COMPAT_STATUS_OKAY(DT_DRV_COMPAT)

#define KEY_PRESS DEVICE_DT_NAME(DT_INST(0, zmk_behavior_key_press))

struct behavior_caps_clear_config {
    uint32_t tap_ms;
    uint32_t wait_ms;
};

static bool caps_lock_is_on(void) {
#if IS_ENABLED(CONFIG_ZMK_HID_INDICATORS)
    return (zmk_hid_indicators_get_current_profile() & HID_KBD_LED_CAPS_LOCK) != 0;
#else
    // Without host LED feedback the lock state is unknowable, so emit an even number of
    // taps: the lock is left as it was, and caps-word is still broken by the keycode.
    return false;
#endif // IS_ENABLED(CONFIG_ZMK_HID_INDICATORS)
}

static int on_caps_clear_binding_pressed(struct zmk_behavior_binding *binding,
                                         struct zmk_behavior_binding_event event) {
    const struct device *dev = zmk_behavior_get_binding(binding->behavior_dev);
    const struct behavior_caps_clear_config *cfg = dev->config;

    const bool locked = caps_lock_is_on();
    const int taps = locked ? 1 : 2;

    LOG_DBG("caps lock %s, sending %d CAPS tap(s)", locked ? "on" : "off", taps);

    const struct zmk_behavior_binding caps = {
        .behavior_dev = KEY_PRESS,
        .param1 = CAPS,
        .param2 = 0,
    };

    for (int i = 0; i < taps; i++) {
        zmk_behavior_queue_add(&event, caps, true, cfg->tap_ms);
        zmk_behavior_queue_add(&event, caps, false, cfg->wait_ms);
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

#define CC_INST(n)                                                                                 \
    static const struct behavior_caps_clear_config behavior_caps_clear_config_##n = {              \
        .tap_ms = DT_INST_PROP(n, tap_ms),                                                         \
        .wait_ms = DT_INST_PROP(n, wait_ms),                                                       \
    };                                                                                             \
    BEHAVIOR_DT_INST_DEFINE(n, NULL, NULL, NULL, &behavior_caps_clear_config_##n, POST_KERNEL,     \
                            CONFIG_KERNEL_INIT_PRIORITY_DEFAULT,                                   \
                            &behavior_caps_clear_driver_api);

DT_INST_FOREACH_STATUS_OKAY(CC_INST)

#endif // DT_HAS_COMPAT_STATUS_OKAY(DT_DRV_COMPAT)
