import io
import logging
import os
import math
import json

import requests
import qrcode
from io import BytesIO
import base64

import urllib
from PIL import Image, ImageDraw, ImageFont
import barcode
from barcode.writer import ImageWriter
from homeassistant.exceptions import HomeAssistantError
from homeassistant.components.recorder.history import get_significant_states
from homeassistant.util import dt
from datetime import timedelta, datetime

_LOGGER = logging.getLogger(__name__)

white =  (255, 255, 255, 255)
black = (0, 0, 0, 255)
red = (255, 0, 0, 255)
yellow = (255, 255, 0, 255)
queue = []
notsetup = True
running = False

# MDI icon metadata cache (loaded once, shared across all calls)
_mdi_icon_cache = None

def _get_mdi_icon_data():
    global _mdi_icon_cache
    if _mdi_icon_cache is None:
        meta_file = os.path.join(os.path.dirname(__file__), "fonts/materialdesignicons-webfont_meta.json")
        with open(meta_file) as f:
            _mdi_icon_cache = json.load(f)
    return _mdi_icon_cache

# is_decimal
def is_decimal(string):
    if not string:
        return False
    if string.startswith("-"):
        string = string[1:]
    return len(string.split(".")) <= 2 and string.replace(".", "").isdecimal()

# min_max
def min_max(data):
    if not(data):
        raise HomeAssistantError("data error, someting is not in range of the recorder")
    mi, ma = data[0], data[0]
    for d in data[1:]:
        mi = min(mi, d)
        ma = max(ma, d)
    return mi, ma

def get_wrapped_text(text: str, font: ImageFont.ImageFont, line_length: int):
    lines = ['']
    for word in text.split():
        line = f'{lines[-1]} {word}'.strip()
        if font.getlength(line) <= line_length:
            lines[-1] = line
        else:
            lines.append(word)
    return '\n'.join(lines)

# E-ink supported colors: white, black, red, yellow
_SUPPORTED_COLORS = [white, black, red, yellow]

def _nearest_eink_color(r, g, b):
    """Return the nearest supported e-ink color (white/black/red/yellow) by Euclidean distance."""
    best = white
    best_dist = float('inf')
    for c in _SUPPORTED_COLORS:
        dist = (r - c[0]) ** 2 + (g - c[1]) ** 2 + (b - c[2]) ** 2
        if dist < best_dist:
            best_dist = dist
            best = c
    return best

# converts a color name or HEX string to the nearest supported e-ink color
def getIndexColor(color):
    if color is None:
        return None
    color_str = str(color).strip()
    # Named colors
    if color_str in ("black", "b"):
        return black
    elif color_str in ("red", "r"):
        return red
    elif color_str in ("yellow", "y"):
        return yellow
    elif color_str in ("white", "w"):
        return white
    # HEX color: map to nearest supported e-ink color
    elif color_str.startswith("#"):
        try:
            h = color_str.lstrip("#")
            if len(h) >= 6:
                r = int(h[0:2], 16)
                g = int(h[2:4], 16)
                b = int(h[4:6], 16)
                mapped = _nearest_eink_color(r, g, b)
                _LOGGER.debug(f"HEX color {color_str} mapped to nearest e-ink color: {mapped}")
                return mapped
        except ValueError:
            pass
        return white
    else:
        return white

# should_show_element
def should_show_element(element):
    return element['visible'] if 'visible' in element else True

def get_font_file(font_name, hass):
    font_file = os.path.join(os.path.dirname(__file__), font_name)
    _LOGGER.debug(f"Font => font_name: {font_name} first checking for default font_file: {font_file}")
    if not os.path.exists(font_file):
        _LOGGER.debug(f"Font => font_name: {font_name} not found in default package")
        www_fonts_dir = hass.config.path("www/fonts")
        if os.path.exists(www_fonts_dir):
            _LOGGER.debug(f"Found {www_fonts_dir} in Home Assistant")
            font_file = os.path.join(www_fonts_dir, font_name)
            _LOGGER.debug(f"Font => font_name: {font_name} got font_file: {font_file}")
    return font_file

def _draw_dashed_line(draw, x0, y0, x1, y1, dash, fill, width):
    """Draw a dashed/dotted line between two points."""
    dash_on, dash_off = dash[0], dash[1] if len(dash) > 1 else dash[0]
    total_len = math.hypot(x1 - x0, y1 - y0)
    if total_len == 0:
        return
    dx = (x1 - x0) / total_len
    dy = (y1 - y0) / total_len
    pos = 0
    drawing = True
    while pos < total_len:
        seg_len = dash_on if drawing else dash_off
        seg_end = min(pos + seg_len, total_len)
        if drawing:
            sx0 = x0 + dx * pos
            sy0 = y0 + dy * pos
            sx1 = x0 + dx * seg_end
            sy1 = y0 + dy * seg_end
            draw.line([(sx0, sy0), (sx1, sy1)], fill=fill, width=width)
        pos += seg_len
        drawing = not drawing

def _resize_image(imgdl, xsize, ysize, mode):
    """Resize image according to fit mode: stretch, fit, fill, contain."""
    target_ratio = xsize / ysize
    src_w, src_h = imgdl.size
    src_ratio = src_w / src_h if src_h else 1

    if mode == "stretch" or mode is None:
        return imgdl.resize((xsize, ysize), Image.LANCZOS)
    elif mode in ("fit", "contain"):
        # Scale to fit inside target box, preserving aspect ratio; pad with transparency
        if src_ratio > target_ratio:
            new_w = xsize
            new_h = round(xsize / src_ratio)
        else:
            new_h = ysize
            new_w = round(ysize * src_ratio)
        imgdl = imgdl.resize((new_w, new_h), Image.LANCZOS)
        canvas = Image.new("RGBA", (xsize, ysize), (255, 255, 255, 0))
        paste_x = (xsize - new_w) // 2
        paste_y = (ysize - new_h) // 2
        canvas.paste(imgdl.convert("RGBA"), (paste_x, paste_y))
        return canvas
    elif mode == "fill":
        # Scale and crop to fill target box completely
        if src_ratio > target_ratio:
            new_h = ysize
            new_w = round(ysize * src_ratio)
        else:
            new_w = xsize
            new_h = round(xsize / src_ratio)
        imgdl = imgdl.resize((new_w, new_h), Image.LANCZOS)
        left = (new_w - xsize) // 2
        top = (new_h - ysize) // 2
        return imgdl.crop((left, top, left + xsize, top + ysize))
    else:
        return imgdl.resize((xsize, ysize), Image.LANCZOS)

# label image renderer
def render_image(entity_id, device, service, hass):
    payload = service.data.get("payload", "")
    rotate = int(service.data.get("rotate", 0))
    background = getIndexColor(service.data.get("background", "white"))
    canvas_width = device.width
    canvas_height = device.height
    if rotate == 90 or rotate == 270:
        img = Image.new('RGBA', (canvas_height, canvas_width), color=background)
    else:
        img = Image.new('RGBA', (canvas_width, canvas_height), color=background)

    pos_y = 0
    known_types = {
        "line", "rectangle", "rectangle_pattern", "circle", "ellipse",
        "text", "multiline", "icon", "dlimg", "qrcode", "barcode",
        "diagram", "plot", "progress_bar",
        "arc", "gauge", "polygon", "table", "text_box", "datamatrix",
    }

    for element in payload:
        elem_type = element.get("type", "")
        _LOGGER.debug("type: " + elem_type)
        if not should_show_element(element):
            continue

        if elem_type not in known_types:
            _LOGGER.warning(f"Unknown element type '{elem_type}' — skipping.")
            continue

        # ── line ──────────────────────────────────────────────────────────────
        if elem_type == "line":
            check_for_missing_required_arguments(element, ["x_start", "x_end"], "line")
            img_line = ImageDraw.Draw(img)
            if "y_start" not in element:
                y_start = pos_y + element.get("y_padding", 0)
                y_end = y_start
            else:
                y_start = element["y_start"]
                y_end = element["y_end"]

            fill = getIndexColor(element['fill']) if 'fill' in element else black
            width = element.get('width', 1)
            dash = element.get('dash', None)

            if dash:
                _draw_dashed_line(img_line, element['x_start'], y_start, element['x_end'], y_end, dash, fill, width)
            else:
                img_line.line([(element['x_start'], y_start), (element['x_end'], y_end)], fill=fill, width=width)
            pos_y = y_start

        # ── rectangle ─────────────────────────────────────────────────────────
        if elem_type == "rectangle":
            check_for_missing_required_arguments(element, ["x_start", "x_end", "y_start", "y_end"], "rectangle")
            img_rect = ImageDraw.Draw(img)
            rect_fill = getIndexColor(element['fill']) if 'fill' in element else None
            rect_outline = getIndexColor(element['outline']) if 'outline' in element else black
            rect_width = element.get('width', 1)
            radius = element['radius'] if 'radius' in element else 10 if 'corners' in element else 0
            corners = rounded_corners(element['corners']) if 'corners' in element else rounded_corners("all") if 'radius' in element else (False, False, False, False)
            img_rect.rounded_rectangle([(element['x_start'], element['y_start']), (element['x_end'], element['y_end'])],
                               fill=rect_fill, outline=rect_outline, width=rect_width, radius=radius, corners=corners)

        # ── rectangle_pattern ─────────────────────────────────────────────────
        if elem_type == "rectangle_pattern":
            check_for_missing_required_arguments(element, ["x_start", "x_size",
                                                           "y_start", "y_size",
                                                           "x_repeat", "y_repeat",
                                                           "x_offset", "y_offset"], "rectangle_pattern")
            img_rect_pattern = ImageDraw.Draw(img)
            fill = getIndexColor(element['fill']) if 'fill' in element else None
            outline = getIndexColor(element['outline']) if 'outline' in element else black
            width = element.get('width', 1)
            radius = element['radius'] if 'radius' in element else 10 if 'corners' in element else 0
            corners = rounded_corners(element['corners']) if 'corners' in element else rounded_corners("all") if 'radius' in element else (False, False, False, False)
            for x in range(element["x_repeat"]):
                for y in range(element["y_repeat"]):
                    img_rect_pattern.rounded_rectangle([(element['x_start'] + x * (element['x_offset'] + element['x_size']),
                                                 element['y_start'] + y * (element['y_offset'] + element['y_size'])),
                                                (element['x_start'] + x * (element['x_offset'] + element['x_size'])
                                                 + element['x_size'], element['y_start'] + y * (element['y_offset']
                                                 + element['y_size'])+element['y_size'])],
                                               fill=fill, outline=outline, width=width, radius=radius, corners=corners)

        # ── circle ────────────────────────────────────────────────────────────
        if elem_type == "circle":
            check_for_missing_required_arguments(element, ["x", "y", "radius"], "circle")
            img_circle = ImageDraw.Draw(img)
            fill = getIndexColor(element['fill']) if 'fill' in element else None
            outline = getIndexColor(element['outline']) if 'outline' in element else black
            width = element.get('width', 1)
            img_circle.circle((element['x'], element['y']), element['radius'], fill=fill, outline=outline, width=width)

        # ── ellipse ───────────────────────────────────────────────────────────
        if elem_type == "ellipse":
            check_for_missing_required_arguments(element, ["x_start", "x_end", "y_start", "y_end"], "ellipse")
            img_ellipse = ImageDraw.Draw(img)
            fill = getIndexColor(element['fill']) if 'fill' in element else None
            outline = getIndexColor(element['outline']) if 'outline' in element else black
            width = element.get('width', 1)
            img_ellipse.ellipse([(element['x_start'], element['y_start']), (element['x_end'], element['y_end'])],
                                fill=fill, outline=outline, width=width)

        # ── arc ───────────────────────────────────────────────────────────────
        if elem_type == "arc":
            check_for_missing_required_arguments(element, ["x_start", "y_start", "x_end", "y_end", "start_angle", "end_angle"], "arc")
            img_arc = ImageDraw.Draw(img)
            fill = getIndexColor(element.get('fill', None))
            outline = getIndexColor(element.get('outline', 'black'))
            width = element.get('width', 1)
            pie = element.get('pie', False)
            bbox = [(element['x_start'], element['y_start']), (element['x_end'], element['y_end'])]
            if pie:
                img_arc.pieslice(bbox, start=element['start_angle'], end=element['end_angle'],
                                 fill=fill, outline=outline, width=width)
            else:
                img_arc.arc(bbox, start=element['start_angle'], end=element['end_angle'],
                            fill=outline, width=width)

        # ── gauge ─────────────────────────────────────────────────────────────
        if elem_type == "gauge":
            check_for_missing_required_arguments(element, ["x", "y", "radius", "progress"], "gauge")
            img_gauge = ImageDraw.Draw(img)
            cx = element['x']
            cy = element['y']
            radius = element['radius']
            progress = float(element['progress'])
            min_val = element.get('min_value', 0)
            max_val = element.get('max_value', 100)
            bar_width = element.get('width', 8)
            fill_color = getIndexColor(element.get('fill', 'black'))
            bg_color = getIndexColor(element.get('background', 'white'))
            outline_color = getIndexColor(element.get('outline', 'black'))
            show_value = element.get('show_value', False)
            font_name = element.get('font', "fonts/NotoSansKR-Regular.ttf")
            font_size = element.get('size', 16)
            value_color = getIndexColor(element.get('color', 'black'))
            # Gauge spans 210° (from 195° to 225°+210° = 345° ... but common gauge: -210 to 30 i.e. 195..345 + 360 wraps)
            # Use 135° start (bottom-left) to 45° end (bottom-right) = 270° sweep
            start_angle = 135
            end_angle = 405  # = 135 + 270
            ratio = max(0.0, min(1.0, (progress - min_val) / (max_val - min_val) if max_val != min_val else 0))
            progress_end = start_angle + ratio * 270
            bbox = [(cx - radius, cy - radius), (cx + radius, cy + radius)]
            inner_r = radius - bar_width
            # Draw background arc
            img_gauge.arc(bbox, start=start_angle, end=end_angle, fill=bg_color, width=bar_width)
            # Draw progress arc
            if ratio > 0:
                img_gauge.arc(bbox, start=start_angle, end=progress_end, fill=fill_color, width=bar_width)
            # Draw outline circle
            img_gauge.arc([(cx - radius - 1, cy - radius - 1), (cx + radius + 1, cy + radius + 1)],
                          start=start_angle, end=end_angle, fill=outline_color, width=1)
            # Show value text
            if show_value:
                font_file = get_font_file(font_name, hass)
                font = ImageFont.truetype(font_file, font_size)
                d = ImageDraw.Draw(img)
                d.fontmode = "1"
                display_val = f"{int(progress)}" if progress == int(progress) else f"{progress:.1f}"
                d.text((cx, cy), display_val, fill=value_color, font=font, anchor="mm")

        # ── polygon ───────────────────────────────────────────────────────────
        if elem_type == "polygon":
            check_for_missing_required_arguments(element, ["points"], "polygon")
            img_poly = ImageDraw.Draw(img)
            fill = getIndexColor(element.get('fill', None))
            outline = getIndexColor(element.get('outline', 'black'))
            width = element.get('width', 1)
            try:
                pts = []
                for pair in element['points'].split(";"):
                    x_str, y_str = pair.strip().split(",")
                    pts.append((float(x_str), float(y_str)))
                img_poly.polygon(pts, fill=fill, outline=outline, width=width)
            except Exception as e:
                raise HomeAssistantError(f"polygon: invalid points format '{element['points']}' — expected 'x1,y1;x2,y2;...'") from e

        # ── text ──────────────────────────────────────────────────────────────
        if elem_type == "text":
            check_for_missing_required_arguments(element, ["x", "value"], "text")
            d = ImageDraw.Draw(img)
            d.fontmode = "1"
            size = element.get('size', 20)
            font_name = element.get('font', "fonts/NotoSansKR-Regular.ttf")
            font_file = get_font_file(font_name, hass)
            font = ImageFont.truetype(font_file, size)
            if "y" not in element:
                akt_pos_y = pos_y + element.get('y_padding', 10)
            else:
                akt_pos_y = element['y']
            color = element.get('color', "black")
            anchor = element.get('anchor', "lt")
            align = element.get('align', "left")
            spacing = element.get('spacing', 5)
            stroke_width = element.get('stroke_width', 0)
            stroke_fill = element.get('stroke_fill', 'white')
            text_rotation = element.get('rotation', 0)
            bg_color = element.get('background', None)
            bg_padding = element.get('background_padding', 2)

            if "max_width" in element:
                text = get_wrapped_text(str(element['value']), font, line_length=element['max_width'])
                anchor = None
            else:
                text = str(element['value'])

            if text_rotation != 0:
                # Render text on a temporary transparent image, then rotate and composite
                tmp_draw_dummy = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
                tbbox = tmp_draw_dummy.textbbox((0, 0), text, font=font, spacing=spacing, stroke_width=stroke_width)
                tw = tbbox[2] - tbbox[0] + stroke_width * 2
                th = tbbox[3] - tbbox[1] + stroke_width * 2
                tmp = Image.new("RGBA", (tw + 4, th + 4), (255, 255, 255, 0))
                tmp_d = ImageDraw.Draw(tmp)
                tmp_d.fontmode = "1"
                if bg_color is not None:
                    tmp_d.rectangle([(0, 0), (tw + 4, th + 4)], fill=getIndexColor(bg_color))
                tmp_d.text((2, 2), text, fill=getIndexColor(color), font=font, spacing=spacing,
                           stroke_width=stroke_width, stroke_fill=stroke_fill)
                tmp = tmp.rotate(text_rotation, expand=True)
                tmp_canvas = Image.new("RGBA", img.size, (255, 255, 255, 0))
                tmp_canvas.paste(tmp, (element['x'], akt_pos_y))
                img = Image.alpha_composite(img, tmp_canvas)
            else:
                if bg_color is not None:
                    tbbox = d.textbbox((element['x'], akt_pos_y), text, font=font, anchor=anchor,
                                       align=align, spacing=spacing, stroke_width=stroke_width)
                    d.rectangle([
                        (tbbox[0] - bg_padding, tbbox[1] - bg_padding),
                        (tbbox[2] + bg_padding, tbbox[3] + bg_padding)
                    ], fill=getIndexColor(bg_color))
                d.text((element['x'], akt_pos_y), text, fill=getIndexColor(color), font=font,
                       anchor=anchor, align=align, spacing=spacing,
                       stroke_width=stroke_width, stroke_fill=stroke_fill)

            textbbox = ImageDraw.Draw(img).textbbox((element['x'], akt_pos_y), text, font=font,
                                                     anchor=anchor, align=align, spacing=spacing,
                                                     stroke_width=stroke_width)
            pos_y = textbbox[3]

        # ── text_box ──────────────────────────────────────────────────────────
        if elem_type == "text_box":
            check_for_missing_required_arguments(element, ["x", "y", "value"], "text_box")
            d = ImageDraw.Draw(img)
            d.fontmode = "1"
            size = element.get('size', 20)
            font_name = element.get('font', "fonts/NotoSansKR-Regular.ttf")
            font_file = get_font_file(font_name, hass)
            font = ImageFont.truetype(font_file, size)
            text = str(element['value'])
            padding = element.get('padding', 5)
            fill_color = getIndexColor(element.get('fill', 'black'))
            text_color = getIndexColor(element.get('color', 'white'))
            outline_color = getIndexColor(element.get('outline', None))
            outline_width = element.get('width', 1)
            radius = element.get('radius', 5)
            tbbox = d.textbbox((element['x'] + padding, element['y'] + padding), text, font=font)
            box_x0 = element['x']
            box_y0 = element['y']
            box_x1 = tbbox[2] + padding
            box_y1 = tbbox[3] + padding
            d.rounded_rectangle([(box_x0, box_y0), (box_x1, box_y1)],
                                 fill=fill_color, outline=outline_color, width=outline_width, radius=radius)
            d.text((element['x'] + padding, element['y'] + padding), text, fill=text_color, font=font, anchor="lt")

        # ── multiline ─────────────────────────────────────────────────────────
        if elem_type == "multiline":
            check_for_missing_required_arguments(element, ["x", "value", "delimiter"], "multiline")
            d = ImageDraw.Draw(img)
            d.fontmode = "1"
            size = element.get('size', 20)
            font_name = element.get('font', "fonts/NotoSansKR-Regular.ttf")
            font_file = get_font_file(font_name, hass)
            font = ImageFont.truetype(font_file, size)
            color = element.get('color', "black")
            anchor = element.get('anchor', "lm")
            stroke_width = element.get('stroke_width', 0)
            stroke_fill = element.get('stroke_fill', 'white')
            _LOGGER.debug("Got Multiline string: %s with delimiter: %s" % (element['value'], element["delimiter"]))
            lst = element['value'].replace("\n", "").split(element["delimiter"])
            pos = element.get('start_y', pos_y + element.get('y_padding', 10))
            for elem in lst:
                _LOGGER.debug("String: %s" % (elem))
                d.text((element['x'], pos), str(elem), fill=getIndexColor(color), font=font,
                       anchor=anchor, stroke_width=stroke_width, stroke_fill=stroke_fill)
                pos = pos + element['offset_y']
            pos_y = pos

        # ── table ─────────────────────────────────────────────────────────────
        if elem_type == "table":
            check_for_missing_required_arguments(element, ["x", "y", "columns", "rows"], "table")
            d = ImageDraw.Draw(img)
            d.fontmode = "1"
            font_name = element.get('font', "fonts/NotoSansKR-Regular.ttf")
            font_file = get_font_file(font_name, hass)
            font_size = element.get('font_size', 14)
            font = ImageFont.truetype(font_file, font_size)
            table_x = element['x']
            table_y = element['y']
            col_widths = element['columns']
            rows = element['rows']
            row_height = element.get('row_height', font_size + 8)
            padding = element.get('padding', 4)
            header_fill = getIndexColor(element.get('header_fill', 'black'))
            header_color = getIndexColor(element.get('header_color', 'white'))
            cell_color = getIndexColor(element.get('cell_color', 'black'))
            border_color = getIndexColor(element.get('border_color', 'black'))
            border_width = element.get('border_width', 1)
            align = element.get('align', 'left')

            cur_y = table_y
            total_width = sum(col_widths)
            for row_idx, row in enumerate(rows):
                is_header = (row_idx == 0) and element.get('header', True)
                fill_bg = header_fill if is_header else getIndexColor(element.get('cell_fill', None))
                text_color = header_color if is_header else cell_color
                cur_x = table_x
                for col_idx, (cell, col_w) in enumerate(zip(row, col_widths)):
                    # cell background
                    d.rectangle([(cur_x, cur_y), (cur_x + col_w, cur_y + row_height)],
                                 fill=fill_bg, outline=border_color, width=border_width)
                    # cell text
                    if align == 'center':
                        tx = cur_x + col_w // 2
                        ta = "mm"
                        ty = cur_y + row_height // 2
                    elif align == 'right':
                        tx = cur_x + col_w - padding
                        ta = "rm"
                        ty = cur_y + row_height // 2
                    else:
                        tx = cur_x + padding
                        ta = "lm"
                        ty = cur_y + row_height // 2
                    d.text((tx, ty), str(cell), fill=text_color, font=font, anchor=ta)
                    cur_x += col_w
                cur_y += row_height
            pos_y = cur_y

        # ── icon ──────────────────────────────────────────────────────────────
        if elem_type == "icon":
            check_for_missing_required_arguments(element, ["x", "y", "value", "size"], "icon")
            d = ImageDraw.Draw(img)
            d.fontmode = "1"
            font_file = os.path.join(os.path.dirname(__file__), 'fonts/materialdesignicons-webfont.ttf')
            icon_data = _get_mdi_icon_data()
            chr_hex = ""
            value = element['value']
            if value.startswith("mdi:"):
                value = value[4:]
            value = map_weather_icon(value)
            for icon in icon_data:
                if icon['name'] == value:
                    chr_hex = icon['codepoint']
                    break
            if chr_hex == "":
                for icon in icon_data:
                    if value in icon['aliases']:
                        chr_hex = icon['codepoint']
                        break
            if chr_hex == "":
                raise HomeAssistantError("Non valid icon used: " + value)
            stroke_width = element.get('stroke_width', 0)
            stroke_fill = element.get('stroke_fill', 'white')
            font = ImageFont.truetype(font_file, element['size'])
            anchor = element.get('anchor', "la")
            fill = getIndexColor(element['color']) if 'color' in element \
                else getIndexColor(element['fill']) if 'fill' in element else black
            d.text((element['x'], element['y']), chr(int(chr_hex, 16)), fill=fill, font=font,
                   anchor=anchor, stroke_width=stroke_width, stroke_fill=stroke_fill)

        # ── dlimg ─────────────────────────────────────────────────────────────
        if elem_type == "dlimg":
            check_for_missing_required_arguments(element, ["x", "y", "url", "xsize", "ysize"], "dlimg")
            url = element['url']
            pos_x = element['x']
            pos_y = element['y']
            xsize = element['xsize']
            ysize = element['ysize']
            rotate2 = element.get('rotate', 0)
            fit_mode = element.get('mode', 'stretch')
            imgdl = ""
            if "http://" in url or "https://" in url:
                response = requests.get(url)
                imgdl = Image.open(io.BytesIO(response.content))
            elif "data:" in url:
                s = url[5:]
                if not s or ',' not in s:
                    raise HomeAssistantError('invalid data url')
                media_type, _, raw_data = s.partition(',')
                is_base64_encoded = media_type.endswith(';base64')
                if is_base64_encoded:
                    media_type = media_type[:-7]
                    missing_padding = '=' * (-len(raw_data) % 4)
                    if missing_padding:
                        raw_data += missing_padding
                    try:
                        data = base64.b64decode(raw_data)
                    except ValueError as exc:
                        raise HomeAssistantError('invalid base64 in data url') from exc
                else:
                    data = urllib.parse.unquote_to_bytes(raw_data)
                imgdl = Image.open(io.BytesIO(data))
            else:
                imgdl = Image.open(url)

            if rotate2 != 0:
                imgdl = imgdl.rotate(-rotate2, expand=True)
            imgdl = _resize_image(imgdl, xsize, ysize, fit_mode)
            imgdl = imgdl.convert("RGBA")
            temp_image = Image.new("RGBA", img.size)
            temp_image.paste(imgdl, (pos_x, pos_y), imgdl)
            img = Image.alpha_composite(img, temp_image)
            img.convert('RGBA')

        # ── qrcode ────────────────────────────────────────────────────────────
        if elem_type == "qrcode":
            check_for_missing_required_arguments(element, ["x", "y", "data"], "qrcode")
            data = element['data']
            pos_x = element['x']
            pos_y = element['y']
            color = element.get('color', "black")
            bgcolor = element.get('bgcolor', "white")
            border = element.get('border', 1)
            boxsize = element.get('boxsize', 2)
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_H,
                box_size=boxsize,
                border=border,
            )
            qr.add_data(data)
            qr.make(fit=True)
            imgqr = qr.make_image(fill_color=color, back_color=bgcolor)
            imgqr = imgqr.convert("RGBA")
            img.paste(imgqr, (pos_x, pos_y), imgqr)
            img.convert('RGBA')

        # ── barcode ───────────────────────────────────────────────────────────
        if elem_type == "barcode":
            check_for_missing_required_arguments(element, ["x", "y", "data"], "barcode")
            data = element['data']
            pos_x = element['x']
            pos_y = element['y']
            color = element.get('color', "black")
            bgcolor = element.get('bgcolor', "white")
            code = element.get('code', "code128")
            module_width = element.get('module_width', 0.2)
            module_height = element.get('module_height', 7)
            quiet_zone = element.get('quiet_zone', 6.5)
            font_size = element.get('font_size', 5)
            text_distance = element.get('text_distance', 5.0)
            write_text = element.get('write_text', True)
            barcode_format = barcode.get_barcode_class(code)
            options = {
                "module_width": float(module_width),
                "module_height": float(module_height),
                "quiet_zone": float(quiet_zone),
                "font_size": int(font_size),
                "text_distance": float(text_distance),
                "background": bgcolor,
                "foreground": color,
                "write_text": write_text,
            }
            buffer = BytesIO()
            barcode_image = barcode_format(data, writer=ImageWriter())
            barcode_image.write(buffer, options=options)
            buffer.seek(0)
            imagebc = Image.open(buffer)
            imagebc = imagebc.convert("RGBA")
            img.paste(imagebc, (pos_x, pos_y), imagebc)
            img.convert('RGBA')

        # ── datamatrix ────────────────────────────────────────────────────────
        if elem_type == "datamatrix":
            check_for_missing_required_arguments(element, ["x", "y", "data"], "datamatrix")
            try:
                from pystrich.datamatrix import DataMatrixEncoder
            except ImportError:
                raise HomeAssistantError("datamatrix requires 'pyStrich'. Add 'pyStrich' to your requirements.")
            data = str(element['data'])
            pos_x = element['x']
            pos_y = element['y']
            color = element.get('color', "black")
            bgcolor = element.get('bgcolor', "white")
            boxsize = element.get('boxsize', 2)

            encoder = DataMatrixEncoder(data)
            dm_image = Image.open(BytesIO(encoder.get_imagedata(cellsize=boxsize)))

            if color != "black" or bgcolor != "white":
                dm_image = dm_image.convert("RGBA")
                data_pixels = list(dm_image.getdata())
                new_data = []
                target_color = getIndexColor(color)
                target_bg = getIndexColor(bgcolor)
                for item in data_pixels:
                    if item[0] < 128:  # Black / Foreground
                        new_data.append(target_color)
                    else:  # White / Background
                        new_data.append(target_bg)
                dm_image.putdata(new_data)
            else:
                dm_image = dm_image.convert("RGBA")

            img.paste(dm_image, (pos_x, pos_y), dm_image)
            img.convert('RGBA')

        # ── diagram ───────────────────────────────────────────────────────────
        if elem_type == "diagram":
            img_draw = ImageDraw.Draw(img)
            d = ImageDraw.Draw(img)
            d.fontmode = "1"
            font_name = element.get('font', "fonts/NotoSansKR-Regular.ttf")
            pos_x = element['x']
            pos_y = element['y']
            width = element.get('width', canvas_width)
            height = element['height']
            offset_lines = element.get('margin', 20)
            img_draw.line([(pos_x+offset_lines, pos_y+height-offset_lines), (pos_x+width, pos_y+height-offset_lines)], fill=getIndexColor('black'), width=1)
            img_draw.line([(pos_x+offset_lines, pos_y), (pos_x+offset_lines, pos_y+height-offset_lines)], fill=getIndexColor('black'), width=1)
            if "bars" in element:
                bar_margin = element["bars"].get('margin', 10)
                bars = element["bars"]["values"].split(";")
                barcount = len(bars)
                bar_width = math.floor((width - offset_lines - ((barcount + 1) * bar_margin)) / barcount)
                _LOGGER.info("Found %i in bars width: %i" % (barcount, bar_width))
                size = element["bars"].get('legend_size', 10)
                font_file = get_font_file(font_name, hass)
                font = ImageFont.truetype(font_file, size)
                legend_color = element["bars"].get('legend_color', "black")
                max_val = 0
                for bar in bars:
                    name, value = bar.split(",", 1)
                    if int(value) > max_val:
                        max_val = int(value)
                height_factor = (height - offset_lines) / max_val
                bar_pos = 0
                for bar in bars:
                    name, value = bar.split(",", 1)
                    x_pos = ((bar_margin + bar_width) * bar_pos) + offset_lines
                    d.text((x_pos + (bar_width/2), pos_y + height - offset_lines / 2), str(name),
                           fill=getIndexColor(legend_color), font=font, anchor="mm")
                    img_draw.rectangle([(x_pos, pos_y+height-offset_lines-(height_factor*int(value))),
                                        (x_pos+bar_width, pos_y+height-offset_lines)],
                                       fill=getIndexColor(element["bars"]["color"]))
                    bar_pos = bar_pos + 1

        # ── plot ──────────────────────────────────────────────────────────────
        if elem_type == "plot":
            check_for_missing_required_arguments(element, ["data"], "plot")
            img_draw = ImageDraw.Draw(img)
            img_draw.fontmode = "1"
            x_start = element.get("x_start", 0)
            y_start = element.get("y_start", 0)
            x_end = element.get("x_end", canvas_width-1-x_start)
            y_end = element.get("y_end", canvas_height-1-x_start)
            width = x_end - x_start + 1
            height = y_end - y_start + 1
            duration = timedelta(seconds=element.get("duration", 60*60*24))
            end = dt.utcnow()
            start = end - duration
            size = element.get("size", 10)
            font_file = element.get("font", "fonts/NotoSansKR-Regular.ttf")
            abs_font_file = os.path.join(os.path.dirname(__file__), font_file)
            font = ImageFont.truetype(abs_font_file, size)

            ylegend = element.get("ylegend", dict())
            if ylegend is None:
                ylegend_width = 0
                ylegend_pos = None
            else:
                ylegend_width = ylegend.get("width", -1)
                ylegend_color = ylegend.get("color", "black")
                ylegend_pos = ylegend.get("position", "left")
                if ylegend_pos not in ("left", "right", None):
                    ylegend_pos = "left"
                ylegend_font_file = ylegend.get("font", font_file)
                ylegend_size = ylegend.get("size", size)
                if ylegend_font_file != font_file or ylegend_size != size:
                    ylegend_abs_font_file = os.path.join(os.path.dirname(__file__), ylegend_font_file)
                    ylegend_font = ImageFont.truetype(ylegend_abs_font_file, ylegend_size)
                else:
                    ylegend_font = font

            yaxis = element.get("yaxis", dict())
            if yaxis is None:
                yaxis_width = 0
                yaxis_tick_width = 0
            else:
                yaxis_width = yaxis.get("width", 1)
                yaxis_color = yaxis.get("color", "black")
                yaxis_tick_width = yaxis.get("tick_width", 2)
                yaxis_tick_every = float(yaxis.get("tick_every", 1))
                yaxis_grid = yaxis.get("grid", 5)
                yaxis_grid_color = yaxis.get("grid_color", "black")

            # x-axis legend (time labels)
            xlegend = element.get("xlegend", None)
            xlegend_height = 0
            if xlegend is not None:
                xlegend_color = getIndexColor(xlegend.get("color", "black"))
                xlegend_size = xlegend.get("size", size)
                xlegend_font_file = xlegend.get("font", font_file)
                xlegend_abs = os.path.join(os.path.dirname(__file__), xlegend_font_file)
                xlegend_font = ImageFont.truetype(xlegend_abs, xlegend_size)
                xlegend_format = xlegend.get("format", "%H:%M")
                xlegend_ticks = int(xlegend.get("ticks", 3))
                xlegend_height = xlegend_size + 4

            min_v = element.get("low", None)
            max_v = element.get("high", None)
            all_states = get_significant_states(hass, start_time=start,
                                                entity_ids=[plot["entity"] for plot in element["data"]],
                                                significant_changes_only=False,
                                                minimal_response=True, no_attributes=False)

            raw_data = []
            for plot in element["data"]:
                if not (plot["entity"] in all_states):
                    raise HomeAssistantError("no recorded data found for " + plot["entity"])
                states = all_states[plot["entity"]]
                state_obj = states[0]
                states[0] = {"state": state_obj.state, "last_changed": str(state_obj.last_changed)}
                states = [(datetime.fromisoformat(s["last_changed"]), float(s["state"])) for s in states if is_decimal(s["state"])]
                min_v_local, max_v_local = min_max([s[1] for s in states])
                min_v = min(min_v or min_v_local, min_v_local)
                max_v = max(max_v or max_v_local, max_v_local)
                raw_data.append(states)

            max_v = math.ceil(max_v)
            min_v = math.floor(min_v)
            if max_v == min_v:
                min_v -= 1
            spread = max_v - min_v

            if ylegend is not None and ylegend_width == -1:
                ylegend_width = math.ceil(max(
                    img_draw.textlength(str(max_v), font=ylegend_font),
                    img_draw.textlength(str(min_v), font=ylegend_font),
                ))

            diag_x = x_start + (ylegend_width if ylegend is not None and ylegend_pos == "left" else 0)
            diag_y = y_start
            diag_width = width - (ylegend_width if ylegend is not None else 0)
            diag_height = height - xlegend_height

            if element.get("debug", False):
                img_draw.rectangle([(x_start, y_start), (x_end, y_end)], fill=None, outline=getIndexColor("black"), width=1)
                img_draw.rectangle([(diag_x, diag_y), (diag_x + diag_width - 1, diag_y + diag_height - 1)], fill=None, outline=getIndexColor("red"), width=1)

            # y grid
            if yaxis is not None:
                if yaxis_grid is not None:
                    grid_points = []
                    curr = min_v
                    while curr <= max_v:
                        curr_y = round(diag_y + (1 - ((curr - min_v) / spread)) * (diag_height - 1))
                        grid_points.extend((x, curr_y) for x in range(diag_x, diag_x + diag_width, yaxis_grid))
                        curr += yaxis_tick_every
                    img_draw.point(grid_points, fill=getIndexColor(yaxis_grid_color))

            # draw plots
            for plot, data in zip(element["data"], raw_data):
                xy_raw = []
                for time_val, value in data:
                    rel_time = (time_val - start) / duration
                    rel_value = (value - min_v) / spread
                    xy_raw.append((round(diag_x + rel_time * (diag_width - 1)),
                                   round(diag_y + (1 - rel_value) * (diag_height - 1))))
                xy = []
                last_x = None
                ys = []
                for x, y in xy_raw:
                    if x != last_x:
                        if ys:
                            xy.append((last_x, round(sum(ys) / len(ys))))
                            ys = []
                        last_x = x
                    ys.append(y)
                if ys:
                    xy.append((last_x, round(sum(ys) / len(ys))))

                # area fill
                area_fill = plot.get("area_fill", None)
                if area_fill and len(xy) >= 2:
                    baseline_y = diag_y + diag_height - 1
                    poly_pts = [(xy[0][0], baseline_y)] + xy + [(xy[-1][0], baseline_y)]
                    img_draw.polygon(poly_pts, fill=getIndexColor(area_fill))

                img_draw.line(xy, fill=getIndexColor(plot.get("color", "black")),
                              width=plot.get("width", 1), joint=plot.get("joint", None))

            # y legend
            if ylegend is not None:
                if ylegend_pos == "left":
                    img_draw.text((x_start, y_start), str(max_v), fill=getIndexColor(ylegend_color), font=ylegend_font, anchor="lt")
                    img_draw.text((x_start, diag_y + diag_height - 1), str(min_v), fill=getIndexColor(ylegend_color), font=ylegend_font, anchor="ls")
                elif ylegend_pos == "right":
                    img_draw.text((x_end, y_start), str(max_v), fill=getIndexColor(ylegend_color), font=ylegend_font, anchor="rt")
                    img_draw.text((x_end, diag_y + diag_height - 1), str(min_v), fill=getIndexColor(ylegend_color), font=ylegend_font, anchor="rs")

            # y axis
            if yaxis is not None:
                img_draw.rectangle([(diag_x, diag_y), (diag_x + yaxis_width - 1, diag_y + diag_height - 1)],
                                   width=0, fill=getIndexColor(yaxis_color))
                if yaxis_tick_width > 0:
                    curr = min_v
                    while curr <= max_v:
                        curr_y = round(diag_y + (1 - ((curr - min_v) / spread)) * (diag_height - 1))
                        img_draw.rectangle([(diag_x + yaxis_width, curr_y),
                                            (diag_x + yaxis_width + yaxis_tick_width - 1, curr_y)],
                                           width=0, fill=getIndexColor(yaxis_color))
                        curr += yaxis_tick_every

            # x legend (time labels)
            if xlegend is not None:
                label_y = diag_y + diag_height + 2
                for i in range(xlegend_ticks):
                    ratio = i / max(xlegend_ticks - 1, 1)
                    lx = round(diag_x + ratio * (diag_width - 1))
                    time_label = (start + duration * ratio).strftime(xlegend_format)
                    if i == 0:
                        anchor = "lt"
                    elif i == xlegend_ticks - 1:
                        anchor = "rt"
                    else:
                        anchor = "mt"
                    img_draw.text((lx, label_y), time_label, fill=xlegend_color, font=xlegend_font, anchor=anchor)

        # ── progress_bar ──────────────────────────────────────────────────────
        if elem_type == "progress_bar":
            check_for_missing_required_arguments(element, ["x_start", "x_end", "y_start", "y_end", "progress"], "progress_bar")
            img_draw = ImageDraw.Draw(img)
            x_start = element['x_start']
            y_start = element['y_start']
            x_end = element['x_end']
            y_end = element['y_end']
            progress = element['progress']
            direction = element.get('direction', 'right')
            bg_color = getIndexColor(element.get('background', 'white'))
            fill = getIndexColor(element.get('fill', 'red'))
            outline = getIndexColor(element.get('outline', 'black'))
            width = element.get('width', 1)
            show_percentage = element.get('show_percentage', False)
            radius = element.get('radius', 0)

            # background
            img_draw.rounded_rectangle([(x_start, y_start), (x_end, y_end)],
                                       fill=bg_color, outline=outline, width=width, radius=radius)

            if direction in ['right', 'left']:
                progress_width = int((x_end - x_start) * (progress / 100))
            else:
                progress_height = int((y_end - y_start) * (progress / 100))

            if direction == 'right':
                img_draw.rounded_rectangle([(x_start, y_start), (x_start + progress_width, y_end)],
                                           fill=fill, radius=radius)
            elif direction == 'left':
                img_draw.rounded_rectangle([(x_end - progress_width, y_start), (x_end, y_end)],
                                           fill=fill, radius=radius)
            elif direction == 'up':
                img_draw.rounded_rectangle([(x_start, y_end - progress_height), (x_end, y_end)],
                                           fill=fill, radius=radius)
            elif direction == 'down':
                img_draw.rounded_rectangle([(x_start, y_start), (x_end, y_start + progress_height)],
                                           fill=fill, radius=radius)

            img_draw.rounded_rectangle([(x_start, y_start), (x_end, y_end)],
                                       fill=None, outline=outline, width=width, radius=radius)

            if show_percentage:
                font_size = min(y_end - y_start - 4, x_end - x_start - 4, 20)
                pb_font = ImageFont.truetype(os.path.join(os.path.dirname(__file__), 'fonts/NotoSansKR-Regular.ttf'), font_size)
                percentage_text = f"{progress}%"
                text_bbox = img_draw.textbbox((0, 0), percentage_text, font=pb_font)
                text_width = text_bbox[2] - text_bbox[0]
                text_height = text_bbox[3] - text_bbox[1]
                text_x = (x_start + x_end - text_width) / 2
                text_y = (y_start + y_end - text_height) / 2
                text_color = bg_color if progress > 50 else fill
                img_draw.text((text_x, text_y), percentage_text, font=pb_font, fill=text_color, anchor='lt')

    # post processing
    if rotate == 90 or rotate == 180 or rotate == 270:
        img = img.rotate(-rotate, expand=True)
    rgb_image = img.convert('RGB')
    return rgb_image


def check_for_missing_required_arguments(element, required_keys, func_name):
    missing_keys = [key for key in required_keys if key not in element]
    if missing_keys:
        raise HomeAssistantError(f"Missing required argument(s) '{', '.join(missing_keys)}' in '{func_name}'")

def map_weather_icon(icon: str) -> str:
    if icon.startswith("weather-"):
        weather_mapping = {
            "clear-night": "night",
            "partlycloudy": "partly-cloudy",
            "exceptional": "sunny-off"
        }
        clean_icon = icon.removeprefix("weather-")
        mapped = weather_mapping.get(clean_icon, clean_icon)
        return f"weather-{mapped}"
    else:
        return icon

def rounded_corners(corner_string):
    if corner_string == "all":
        return True, True, True, True
    corners = corner_string.split(",")
    corner_map = {
        "top_left": 0,
        "top_right": 1,
        "bottom_right": 2,
        "bottom_left": 3
    }
    result = [False] * 4
    for corner in corners:
        corner = corner.strip()
        if corner in corner_map:
            result[corner_map[corner]] = True
    return tuple(result)