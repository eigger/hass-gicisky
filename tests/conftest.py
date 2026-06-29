import sys
from unittest.mock import MagicMock

# Base class mock supporting subscripting (e.g., BaseClass[T])
class MockBase:
    def __init__(self, *args, **kwargs):
        pass
    def __class_getitem__(cls, item):
        return cls

# ── Mock Home Assistant Modules ────────────────────────────────────────────────

# Mock homeassistant.exceptions
class MockHomeAssistantError(Exception):
    """Mock HomeAssistantError."""
    pass

ha_exceptions = MagicMock()
ha_exceptions.HomeAssistantError = MockHomeAssistantError
sys.modules["homeassistant.exceptions"] = ha_exceptions

# Mock other homeassistant submodules
sys.modules["homeassistant.components.recorder.history"] = MagicMock()
sys.modules["homeassistant.components.bluetooth"] = MagicMock()

# Setup bluetooth passive update processor mocks
ha_bt_processor = MagicMock()
ha_bt_processor.PassiveBluetoothProcessorCoordinator = MockBase
ha_bt_processor.PassiveBluetoothDataProcessor = MockBase
sys.modules["homeassistant.components.bluetooth.passive_update_processor"] = ha_bt_processor

sys.modules["homeassistant.config_entries"] = MagicMock()
sys.modules["homeassistant.const"] = MagicMock()
sys.modules["homeassistant.core"] = MagicMock()
sys.modules["homeassistant.helpers"] = MagicMock()
sys.modules["homeassistant.helpers.device_registry"] = MagicMock()
sys.modules["homeassistant.helpers.update_coordinator"] = MagicMock()
sys.modules["homeassistant.helpers.debounce"] = MagicMock()
sys.modules["homeassistant.util"] = MagicMock()
sys.modules["homeassistant.util.dt"] = MagicMock()

# ── Mock External Modules ─────────────────────────────────────────────────────

# Mock sensor_state_data
sys.modules["sensor_state_data"] = MagicMock()

# Mock bluetooth_sensor_state_data
sys.modules["bluetooth_sensor_state_data"] = MagicMock()

# Mock home_assistant_bluetooth
sys.modules["home_assistant_bluetooth"] = MagicMock()

# Mock bleak
sys.modules["bleak"] = MagicMock()
sys.modules["bleak.backends.device"] = MagicMock()
sys.modules["bleak_retry_connector"] = MagicMock()
