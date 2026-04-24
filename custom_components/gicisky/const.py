"""Constants for the Gicisky Bluetooth integration."""

from __future__ import annotations

DOMAIN = "gicisky"
LOCK = "lock"

# Options
CONF_RETRY_COUNT = "retry_count"
CONF_WRITE_DELAY_MS = "write_delay_ms"
CONF_PREVENT_DUPLICATE_SEND = "prevent_duplicate_send"
CONF_DEBOUNCE_MS = "debounce_ms"

# Defaults
DEFAULT_RETRY_COUNT = 3
DEFAULT_WRITE_DELAY_MS = 0
DEFAULT_PREVENT_DUPLICATE_SEND = False
DEFAULT_DEBOUNCE_MS = 0

# Runtime state keys
WRITE_LOCK = "write_lock"


