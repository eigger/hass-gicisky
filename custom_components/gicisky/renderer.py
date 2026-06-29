import logging
import os

from homeassistant.exceptions import HomeAssistantError
from homeassistant.components.recorder.history import get_significant_states

from imagespec import render, RenderContext, RenderError

_LOGGER = logging.getLogger(__name__)


def _make_context(hass, *, default_font, palette):
    def font_resolver(name):
        base_name = os.path.basename(name)
        
        # 1. Check local gicisky components fonts directory
        local_font_dir = os.path.join(os.path.dirname(__file__), "fonts")
        local_path = os.path.join(local_font_dir, base_name)
        if os.path.exists(local_path):
            return local_path

        # 2. Check Home Assistant www/fonts
        www_fonts_dir = hass.config.path("www/fonts")
        www_path = os.path.join(www_fonts_dir, base_name)
        if os.path.exists(www_path):
            return www_path

        return None

    def history_provider(entity_ids, start, end):
        return get_significant_states(
            hass,
            start_time=start,
            entity_ids=list(entity_ids),
            significant_changes_only=False,
            minimal_response=True,
            no_attributes=False,
        )

    # Use custom_components/gicisky/fonts/ as the default icons source directory
    # so that it finds materialdesignicons-webfont.ttf and its metadata
    icons_dir = os.path.join(os.path.dirname(__file__), "fonts")

    return RenderContext(
        font_resolver=font_resolver,
        history_provider=history_provider,
        default_font=default_font,
        palette=palette,
        icons_dir=icons_dir,
        allow_local_images=True  # Gicisky originally allowed local paths for dlimg
    )


def render_image(entity_id, device, service, hass):
    # Explicitly specify the colors supported by each device palette
    if getattr(device, "four_color", False):
        palette = ["black", "white", "red", "yellow"]
    elif getattr(device, "red", True):
        palette = ["black", "white", "red"]
    else:
        palette = ["black", "white"]

    try:
        return render(
            payload=service.data.get("payload", ""),
            width=device.width,
            height=device.height,
            rotate=int(service.data.get("rotate", 0)),
            rotate_mode="canvas",  # ESL panel: fixed resolution, background rotates
            background=service.data.get("background", "white"),
            context=_make_context(hass, default_font="NotoSansKR-Regular.ttf", palette=palette),
        )
    except RenderError as err:
        raise HomeAssistantError(str(err)) from err
