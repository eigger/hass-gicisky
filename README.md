# hass-gicisky
[![HACS](https://img.shields.io/badge/HACS-Custom-41BDF5.svg?logo=home-assistant)](https://hacs.xyz/)
[![GitHub Release](https://img.shields.io/github/release/eigger/hass-gicisky.svg)](https://github.com/eigger/hass-gicisky/releases)
[![License](https://img.shields.io/github/license/eigger/hass-gicisky)](https://github.com/eigger/hass-gicisky/blob/main/LICENSE)
![integration usage](https://img.shields.io/badge/dynamic/json?color=41BDF5&logo=home-assistant&label=integration%20usage&suffix=%20installs&cacheSeconds=15600&url=https://analytics.home-assistant.io/custom_integrations.json&query=%24.gicisky.total)

Gicisky BLE Label Home Assistant Integration

## Gallery

| Size | Example |
|------|---------|
| 2.1" (250×128) | <img src="https://raw.githubusercontent.com/eigger/hass-gicisky/master/docs/images/21_1.png" alt="2.1 inch" width="200" /> |
| 2.9" (296×128) | <img src="https://raw.githubusercontent.com/eigger/hass-gicisky/master/docs/images/29_1.png" alt="2.9 inch" width="200" /> |
| 10.2" (960×640) | <img src="https://raw.githubusercontent.com/eigger/hass-gicisky/master/docs/images/102_1.jpg" alt="10.2 inch" width="200" /> |

## What is an electronic label?

An **electronic label** (electronic shelf label, ESL) is a small **e-paper** display that keeps showing content **without continuous power**. This integration targets labels manufactured by **Gicisky**.

They work well for information that should stay visible, changes infrequently, and lives where mains power is impractical — not only retail price tags.

## Feedback & Support

- Found a bug? [Open an issue](https://github.com/eigger/hass-gicisky/issues)
- Questions or ideas? [Join the discussion](https://github.com/eigger/hass-gicisky/discussions)

## Related

- [Stash](https://github.com/eigger/stash) — self-hosted home inventory manager. Track and restock items with barcode scanning, and print labels to Gicisky devices via Home Assistant.

---

## Supported Models

| Type | Size | Resolution | Colors |
|------|------|------------|--------|
| TFT | 2.1" | 250 × 132 | BW |
| EPD | 2.1" | 250 × 128 | BWR |
| EPD | 2.9" | 296 × 128 | BW |
| EPD | 2.9" | 296 × 128 | BWR |
| EPD | 2.9" | 296 × 128 | BWRY |
| EPD | 3.7" | 240 × 416 | BWR |
| EPD | 4.2" | 400 × 300 | BWR |
| EPD | 7.5" | 800 × 480 | BWR |
| EPD | 10.2" | 960 × 640 | BWR |

## Where to Buy

Availability varies by country. Official Gicisky listings on AliExpress:

- [Gicisky store (item 1)](https://ko.aliexpress.com/item/1005002399342939.html)
- [Gicisky store (item 2)](https://ko.aliexpress.com/item/1005002398744297.html)

## Installation

1. Install with HACS (custom repository required), or copy this repo into `custom_components/gicisky`.
2. Restart Home Assistant.
3. Add the integration via **Settings** → **Integrations** → **Gicisky** and select your device.

## Important Notice

Use a **Bluetooth proxy** instead of a built-in adapter when possible — especially with multiple BLE devices nearby.

> [!TIP]
> Hardware recommendations: [Great ESP32 Board for an ESPHome Bluetooth Proxy](https://community.home-assistant.io/t/great-esp32-board-for-an-esphome-bluetooth-proxy/916767/31)

Keep the proxy scan interval at its default. **`bluetooth_proxy` must have `active: true`.**

```yaml
esp32_ble_tracker:
  scan_parameters:
    active: true

bluetooth_proxy:
  active: true
```

## Options

Configure via **Settings** → **Devices & Services** → **Gicisky** → **Configure**:

| Option | Default | Range | Description |
|--------|---------|-------|-------------|
| **Retry Count** | 3 | 1–10 | Retries when a BLE write fails |
| **Write Delay (ms)** | 0 | 0–1000 | Pause between BLE write packets |
| **Prevent Duplicate Send** | false | on/off | Skip sending when image data is unchanged |
| **Debounce Delay (ms)** | 0 | 0–120000 | Wait before writing; new requests cancel pending ones (`0` = immediate) |

> [!TIP]
> Unstable writes: try **Write Delay** 50–100 ms. Frequent automations: enable **Prevent Duplicate Send** and/or **Debounce Delay** to save battery and reduce BLE traffic.

---

## Payload & rendering (`imagespec`)

From version 5.0.0, labels are rendered with **[imagespec](https://github.com/eigger/imagespec)** — a declarative YAML/JSON list of drawing elements packed and sent to the e-paper panel.

**Documentation (maintained in imagespec, not duplicated here):**

| Topic | Link |
|-------|------|
| Element examples with preview images | [imagespec/docs/elements.md](https://github.com/eigger/imagespec/blob/main/docs/elements.md) |
| All element fields & defaults | [imagespec README — Element Reference](https://github.com/eigger/imagespec#elements-reference) |
| Layout, palette, LLM authoring guide | [imagespec/docs/authoring.md](https://github.com/eigger/imagespec/blob/main/docs/authoring.md) |

**Gicisky-specific behaviour:**

- **Resolution:** `width` and `height` come from the **device profile**, not the service call.
- **Palette:** auto-selected per tag — BW, BWR (`black`/`white`/`red`), or BWRY (+ `yellow`). Off-palette colors are quantized to the nearest supported color.
- **Rotation:** `rotate: 90/180/270` uses **canvas mode** — the fixed panel rotates; output size stays the device resolution.
- **Default font:** `NotoSansKR-Regular.ttf` in `custom_components/gicisky/fonts/`. Custom fonts also work from `www/fonts/`.
- **`plot` element:** reads history from Home Assistant **Recorder**.
- **`dlimg`:** local file paths under `/config/...` are allowed (HTTP/HTTPS and data URIs too).
- **`dither`:** halftone for photos/charts on limited-color panels — see [imagespec dithering docs](https://github.com/eigger/imagespec#dithering).
- **Layout:** prefer `row` / `column` / `stack` over hand-placed coordinates.
- **Image entities:** each tag exposes **Last Updated Content** (last image sent) and **Preview Content** (`dry_run` renders).

---

## Services

### `gicisky.write`

Renders the payload and sends it to the tag (unless `dry_run: true`).

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `payload` | yes | — | List of [imagespec elements](https://github.com/eigger/imagespec/blob/main/docs/elements.md) |
| `rotate` | no | `0` | `0`, `90`, `180`, or `270` |
| `background` | no | `white` | `white`, `black`, `red`, or `yellow` |
| `dither` | no | `false` | Floyd–Steinberg halftone for the whole image |
| `dry_run` | no | `false` | Render only; updates **Preview Content** image entity without BLE send |

Basic example:

```yaml
action: gicisky.write
target:
  device_id: <your device>
data:
  payload:
    - type: text
      value: Hello World!
      x: 10
      y: 10
      size: 40
```

Rotation and background:

```yaml
action: gicisky.write
target:
  device_id: <your device>
data:
  rotate: 90
  background: black
  payload:
    - type: text
      value: Rotated!
      x: 10
      y: 10
      size: 30
      color: white
```

Preview without sending (`dry_run` updates the tag's **Preview Content** image entity):

```yaml
action: gicisky.write
target:
  device_id: <your device>
data:
  dry_run: true
  payload:
    - type: text
      value: Preview Test
      x: 10
      y: 10
      size: 30
```

Use the **[Gicisky Payload Editor](https://eigger.github.io/Gicisky_Payload_Editor.html)** to design layouts in the browser and paste the generated YAML.

Combined dashboard-style example:

```yaml
action: gicisky.write
target:
  device_id: <your device>
data:
  background: white
  payload:
    - type: text
      value: "Home Status"
      x: 10
      y: 5
      size: 24
      font: "fonts/NotoSansKR-Bold.ttf"
    - type: line
      x_start: 0
      x_end: 250
      y_start: 35
      y_end: 35
      fill: black
      width: 1
    - type: icon
      value: thermometer
      x: 10
      y: 45
      size: 24
    - type: text
      value: "{{ states('sensor.temperature') }}°C"
      x: 40
      y: 48
      size: 20
    - type: progress_bar
      x_start: 10
      y_start: 80
      x_end: 240
      y_end: 95
      progress: "{{ states('sensor.humidity') | int }}"
      fill: black
      show_percentage: true
    - type: qrcode
      data: "https://www.home-assistant.io"
      x: 180
      y: 40
      width: 60
      height: 60
```

### `gicisky.write_guarded`

Same rendering as `gicisky.write`, with guards before BLE transmission:

- duplicate image skip (when **Prevent Duplicate Send** is enabled)
- write lock check
- debounce scheduling (**Debounce Delay** option, overridable per call)

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `payload` | yes | — | Same as `gicisky.write` |
| `rotate`, `background`, `dither`, `dry_run` | no | — | Same as `gicisky.write` |
| `debounce_override_ms` | no | option value | Override debounce for this call (`0` = write immediately) |

```yaml
action: gicisky.write_guarded
target:
  device_id: <your device>
data:
  payload:
    - type: text
      value: Guarded Write
      x: 10
      y: 10
      size: 36
```

Immediate write (skip debounce once):

```yaml
action: gicisky.write_guarded
target:
  device_id: <your device>
data:
  debounce_override_ms: 0
  payload:
    - type: text
      value: Immediate
      x: 10
      y: 10
      size: 36
```

| Service | When to use |
|---------|-------------|
| `gicisky.write` | Always send (except explicit `dry_run`) |
| `gicisky.write_guarded` | Automations that fire often; skip duplicates and coalesce rapid updates |

---

## Fonts

The default font is `fonts/NotoSansKR-Regular.ttf`. The integration checks `custom_components/gicisky/fonts/` first, then `config/www/fonts/`.

### Built-in fonts

| Family | Files |
|--------|-------|
| **CookieRun** | `CookieRunRegular.ttf`, `CookieRunBold.ttf`, `CookieRunBlack.ttf` |
| **Gmarket Sans** | `GmarketSansTTFLight.ttf`, `GmarketSansTTFMedium.ttf`, `GmarketSansTTFBold.ttf` |
| **Noto Sans KR** | Thin through Black weights (`NotoSansKR-*.ttf`) |
| **OwnglyphParkDaHyun** | `OwnglyphParkDaHyun.ttf` |

Custom font example:

```yaml
- type: text
  value: "Custom Font"
  x: 10
  y: 10
  size: 30
  font: "MyCustomFont.ttf"
```

Place `MyCustomFont.ttf` in `config/www/fonts/`.

---

## Examples

| Size | Example | Preview | YAML |
|------|---------|---------|------|
| 2.1" (250×128) | Date | ![2.1-date.jpg](https://raw.githubusercontent.com/eigger/hass-gicisky/master/examples/2.1-date.jpg) | [2.1-date.yaml](./examples/2.1-date.yaml) |
| 2.1" (250×128) | Naver Weather | ![2.1-naver-weather.jpg](https://raw.githubusercontent.com/eigger/hass-gicisky/master/examples/2.1-naver-weather.jpg) | [2.1-naver-weather.yaml](./examples/2.1-naver-weather.yaml) |
| 2.1" (250×128) | Waste Collection | ![2.1-waste-collection.png](https://raw.githubusercontent.com/eigger/hass-gicisky/master/examples/2.1-waste-collection.png) | [2.1-waste-collection.yaml](./examples/2.1-waste-collection.yaml) |
| 2.1" (250×128) | Wifi | ![2.1-wifi.jpg](https://raw.githubusercontent.com/eigger/hass-gicisky/master/examples/2.1-wifi.jpg) | [2.1-wifi.yaml](./examples/2.1-wifi.yaml) |
| 2.1" (250×128) | TMap time | ![2.1-tmap-time.jpg](https://raw.githubusercontent.com/eigger/hass-gicisky/master/examples/2.1-tmap-time.jpg) | [2.1-tmap-time.yaml](./examples/2.1-tmap-time.yaml) |
| 2.9" (296×128) | Google Calendar | ![2.9-google-calendar.jpg](https://raw.githubusercontent.com/eigger/hass-gicisky/master/examples/2.9-google-calendar.jpg) | [2.9-google-calendar.yaml](./examples/2.9-google-calendar.yaml) |
| 2.9" (296×128) | Presence Display | ![2.9-presence-display.jpg](https://raw.githubusercontent.com/eigger/hass-gicisky/master/examples/2.9-presence-display.jpg) | [2.9-presence-display.yaml](./examples/2.9-presence-display.yaml) |
| 4.2" (400×300) | Image | ![4.2-image.jpg](https://raw.githubusercontent.com/eigger/hass-gicisky/master/examples/4.2-image.jpg) | [4.2-image.yaml](./examples/4.2-image.yaml) |
| 4.2" (400×300) | 기상청 Weather | ![4.2-kma-weather.png](https://raw.githubusercontent.com/eigger/hass-gicisky/master/examples/4.2-kma-weather.png) | [4.2-kma-weather.yaml](./examples/4.2-kma-weather.yaml) |
| 4.2" (400×300) | Naver Weather | ![4.2-naver-weather.jpg](https://raw.githubusercontent.com/eigger/hass-gicisky/master/examples/4.2-naver-weather.jpg) | [4.2-naver-weather.yaml](./examples/4.2-naver-weather.yaml) |
| 4.2" (400×300) | Date Weather | ![4.2-date-weather.jpg](https://raw.githubusercontent.com/eigger/hass-gicisky/master/examples/4.2-date-weather.jpg) | [4.2-date-weather.yaml](./examples/4.2-date-weather.yaml) |
| 4.2" (400×300) | Weather News | ![4.2-weather-news.png](https://raw.githubusercontent.com/eigger/hass-gicisky/master/examples/4.2-weather-news.png) | [4.2-weather-news.yaml](./examples/4.2-weather-news.yaml) |
| 4.2" (400×300) | 3D Print | ![4.2-3d-print.png](https://raw.githubusercontent.com/eigger/hass-gicisky/master/examples/4.2-3d-print.png) | [4.2-3d-print.yaml](./examples/4.2-3d-print.yaml) |
| 7.5" (800×480) | Google Calendar | ![7.5-google-calendar.jpg](https://raw.githubusercontent.com/eigger/hass-gicisky/master/examples/7.5-google-calendar.jpg) | [7.5-google-calendar.yaml](./examples/7.5-google-calendar.yaml) |
| 7.5" (800×480) | Date Weather | ![7.5-date-weather.png](https://raw.githubusercontent.com/eigger/hass-gicisky/master/examples/7.5-date-weather.png) | [7.5-date-weather.yaml](./examples/7.5-date-weather.yaml) |
| 10.2" (960×640) | Calendar Weather | ![10.2-calendar-weather.png](https://raw.githubusercontent.com/eigger/hass-gicisky/master/examples/10.2-calendar-weather.png) | [10.2-calendar-weather.yaml](./examples/10.2-calendar-weather.yaml) |
| 10.2" (960×640) | Calendar | ![10.2-calendar.png](https://raw.githubusercontent.com/eigger/hass-gicisky/master/examples/10.2-calendar.png) | [10.2-calendar.yaml](./examples/10.2-calendar.yaml) |

---

## Tools

- **[Gicisky Image Edit & Uploader](https://eigger.github.io/Gicisky_Image_Uploader.html)**
- **[Gicisky Payload Editor](https://eigger.github.io/Gicisky_Payload_Editor.html)**

---

## Appendix

### T-Map integration

```yaml
# https://openapi.sk.com/products/detail?linkMenuSeq=46
rest_command:
  request_tmap_routes:
    url: https://apis.openapi.sk.com/tmap/routes?version=1
    method: POST
    headers:
      appKey: !secret tmap_api_key
      accept: "application/json, text/html"
    content_type: "application/json; charset=utf-8"
    payload: >-
      {
        "startX": {{ startX }},
        "startY": {{ startY }},
        "endX": {{ endX }},
        "endY": {{ endY }},
        "searchOption": {{ searchOption }},
        "totalValue": 2,
        "trafficInfo ": "Y",
        "mainRoadInfo": "Y"
      }
```

See [2.1-tmap-time.yaml](./examples/2.1-tmap-time.yaml) for a full label example.

### Google Calendar

Add a remote calendar: **Settings** → **Devices & Services** → **Calendar** → add Google `*.ics` URL.

### Third-party custom components

- [기상청 APIhub (eigger)](https://github.com/eigger/hass-kma)
- [Naver Weather (minumida)](https://github.com/miumida/naver_weather)
- [ha-weathernews (dugurs)](https://github.com/dugurs/ha-weathernews)
- [Waste Collection Schedule (mampfes)](https://github.com/mampfes/hacs_waste_collection_schedule)

---

## References

- [imagespec](https://github.com/eigger/imagespec) — rendering engine
- [ATC GICISKY ESL (atc1441)](https://github.com/atc1441/ATC_GICISKY_ESL)
- [OpenEPaperLink](https://github.com/OpenEPaperLink/Home_Assistant_Integration)
- [bthome](https://github.com/home-assistant/core/tree/dev/homeassistant/components/bthome)
- [bthome-ble](https://github.com/Bluetooth-Devices/bthome-ble)
