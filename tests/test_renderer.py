from unittest.mock import MagicMock
import pytest
from custom_components.gicisky.renderer import render_image

def test_render_image():
    # Arrange
    device = MagicMock()
    device.width = 296
    device.height = 128
    device.four_color = True

    service = MagicMock()
    service.data = {
        "payload": [
            {"type": "rectangle", "x_start": 0, "y_start": 0, "x_end": 100, "y_end": 50, "fill": "red"}
        ],
        "rotate": 0,
        "background": "white"
    }

    hass = MagicMock()
    # Mock hass.config.path to return a temporary/mock path
    hass.config.path = MagicMock(return_value="/tmp/mock_fonts")

    # Act
    image = render_image("dummy_entity", device, service, hass)

    # Assert
    assert image is not None
    assert image.size == (296, 128)
