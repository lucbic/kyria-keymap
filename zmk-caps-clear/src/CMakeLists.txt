# Copyright (c) 2026 The ZMK Contributors
# SPDX-License-Identifier: MIT

# behavior_queue, key_press and hid_indicators are only compiled on the central,
# so this file must not be built for a peripheral.
if (((NOT CONFIG_ZMK_SPLIT) OR CONFIG_ZMK_SPLIT_ROLE_CENTRAL) AND CONFIG_ZMK_BEHAVIOR_CAPS_CLEAR)
  target_sources(app PRIVATE behavior_caps_clear.c)
endif()
