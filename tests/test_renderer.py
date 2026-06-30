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


def test_render_image_dither():
    # Arrange
    device = MagicMock()
    device.width = 10
    device.height = 10
    device.four_color = False
    device.red = False  # black/white only

    hass = MagicMock()
    hass.config.path = MagicMock(return_value="/tmp/mock_fonts")

    # 1. Render without dither (flat)
    service_no_dither = MagicMock()
    service_no_dither.data = {
        "payload": [
            {"type": "rectangle", "x_start": 0, "y_start": 0, "x_end": 10, "y_end": 10, "fill": "#b0b0b0", "outline": "#b0b0b0"}
        ],
        "dither": False,
        "background": "white"
    }
    img_no_dither = render_image("dummy_entity", device, service_no_dither, hass)

    # 2. Render with dither
    service_dither = MagicMock()
    service_dither.data = {
        "payload": [
            {"type": "rectangle", "x_start": 0, "y_start": 0, "x_end": 10, "y_end": 10, "fill": "#b0b0b0", "outline": "#b0b0b0"}
        ],
        "dither": True,
        "background": "white"
    }
    img_dither = render_image("dummy_entity", device, service_dither, hass)

    # Assert
    w, h = img_no_dither.size
    pixels_no_dither = [img_no_dither.getpixel((x, y)) for y in range(h) for x in range(w)]
    unique_no_dither = set(pixels_no_dither)
    assert len(unique_no_dither) == 1

    pixels_dither = [img_dither.getpixel((x, y)) for y in range(h) for x in range(w)]
    unique_dither = set(pixels_dither)
    assert (0, 0, 0) in unique_dither
    assert (255, 255, 255) in unique_dither


def test_render_image_dither_pink_gray():
    # Arrange for a 3-color device (black, white, red)
    device_bwr = MagicMock()
    device_bwr.width = 10
    device_bwr.height = 10
    device_bwr.four_color = False
    device_bwr.red = True

    hass = MagicMock()
    hass.config.path = MagicMock(return_value="/tmp/mock_fonts")

    # 1. Render pink (#FFC0CB) without dither
    service_pink_no_dither = MagicMock()
    service_pink_no_dither.data = {
        "payload": [
            {"type": "rectangle", "x_start": 0, "y_start": 0, "x_end": 10, "y_end": 10, "fill": "#FFC0CB", "outline": "#FFC0CB"}
        ],
        "dither": False,
        "background": "white"
    }
    img_pink_no_dither = render_image("dummy_entity", device_bwr, service_pink_no_dither, hass)

    # 2. Render pink (#FFC0CB) with dither
    service_pink_dither = MagicMock()
    service_pink_dither.data = {
        "payload": [
            {"type": "rectangle", "x_start": 0, "y_start": 0, "x_end": 10, "y_end": 10, "fill": "#FFC0CB", "outline": "#FFC0CB"}
        ],
        "dither": True,
        "background": "white"
    }
    img_pink_dither = render_image("dummy_entity", device_bwr, service_pink_dither, hass)

    # Without dither, pink snaps to white (255, 255, 255) because it's closer to white than red (255, 0, 0)
    w_bwr, h_bwr = img_pink_no_dither.size
    pixels_pink_no_dither = [img_pink_no_dither.getpixel((x, y)) for y in range(h_bwr) for x in range(w_bwr)]
    unique_pink_no_dither = set(pixels_pink_no_dither)
    assert len(unique_pink_no_dither) == 1
    assert (255, 255, 255) in unique_pink_no_dither

    # With dither, pink maps to a mixture of red (255, 0, 0) and white (255, 255, 255)
    pixels_pink_dither = [img_pink_dither.getpixel((x, y)) for y in range(h_bwr) for x in range(w_bwr)]
    unique_pink_dither = set(pixels_pink_dither)
    assert (255, 255, 255) in unique_pink_dither
    assert (255, 0, 0) in unique_pink_dither


