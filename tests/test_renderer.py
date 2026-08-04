from unittest.mock import MagicMock
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


def test_render_image_per_element_dither():
    """Service has no dither; use per-element dither for photos/charts only."""
    device = MagicMock()
    device.width = 10
    device.height = 10
    device.four_color = False
    device.red = False  # black/white only

    hass = MagicMock()
    hass.config.path = MagicMock(return_value="/tmp/mock_fonts")

    service_flat = MagicMock()
    service_flat.data = {
        "payload": [
            {"type": "rectangle", "x_start": 0, "y_start": 0, "x_end": 10, "y_end": 10, "fill": "#b0b0b0", "outline": "#b0b0b0"}
        ],
        "background": "white",
    }
    img_flat = render_image("dummy_entity", device, service_flat, hass)

    service_dither = MagicMock()
    service_dither.data = {
        "payload": [
            {
                "type": "rectangle",
                "x_start": 0,
                "y_start": 0,
                "x_end": 10,
                "y_end": 10,
                "fill": "#b0b0b0",
                "outline": "#b0b0b0",
                "dither": "floyd",
            }
        ],
        "background": "white",
    }
    img_dither = render_image("dummy_entity", device, service_dither, hass)

    w, h = img_flat.size
    unique_flat = {img_flat.getpixel((x, y)) for y in range(h) for x in range(w)}
    assert len(unique_flat) == 1

    unique_dither = {img_dither.getpixel((x, y)) for y in range(h) for x in range(w)}
    assert unique_dither == {(0, 0, 0), (255, 255, 255)}


def test_render_image_per_element_dither_pink_bwr():
    device_bwr = MagicMock()
    device_bwr.width = 10
    device_bwr.height = 10
    device_bwr.four_color = False
    device_bwr.red = True

    hass = MagicMock()
    hass.config.path = MagicMock(return_value="/tmp/mock_fonts")

    service_flat = MagicMock()
    service_flat.data = {
        "payload": [
            {"type": "rectangle", "x_start": 0, "y_start": 0, "x_end": 10, "y_end": 10, "fill": "#FFC0CB", "outline": "#FFC0CB"}
        ],
        "background": "white",
    }
    img_flat = render_image("dummy_entity", device_bwr, service_flat, hass)

    service_dither = MagicMock()
    service_dither.data = {
        "payload": [
            {
                "type": "rectangle",
                "x_start": 0,
                "y_start": 0,
                "x_end": 10,
                "y_end": 10,
                "fill": "#FFC0CB",
                "outline": "#FFC0CB",
                "dither": True,
            }
        ],
        "background": "white",
    }
    img_dither = render_image("dummy_entity", device_bwr, service_dither, hass)

    # Without dither, pink snaps to white
    unique_flat = {img_flat.getpixel((x, y)) for y in range(10) for x in range(10)}
    assert unique_flat == {(255, 255, 255)}

    # With per-element dither, pink becomes a red/white halftone
    unique_dither = {img_dither.getpixel((x, y)) for y in range(10) for x in range(10)}
    assert (255, 255, 255) in unique_dither
    assert (255, 0, 0) in unique_dither
