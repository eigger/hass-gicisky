# hass-gicisky
Gicisky BLE Label Home Assistant Integration

## 💬 Feedback & Support

🐞 Found a bug? Let us know via an [Issue](https://github.com/eigger/hass-gicisky/issues).  
💡 Have a question or suggestion? Join the [Discussion](https://github.com/eigger/hass-gicisky/discussions)!


## Supported Models
- TFT 2.1" BW (250x132)
- EPD 2.1" BWR (250x128)
- EPD 2.9" BWR (296x128)
- EPD 4.2" BWR (400x300)
- EPD 7.5" BWR (800x480)

## Installation
1. Install this integration with HACS (adding repository required), or copy the contents of this
repository into the `custom_components/gicisky` directory.
2. Restart Home Assistant.

## ⚠️ Important Notice
- It is **strongly recommended to use a Bluetooth proxy instead of a built-in Bluetooth adapter**.  
  Bluetooth proxies generally offer more stable connections and better range, especially in environments with multiple BLE devices.
- When using a Bluetooth proxy, it is strongly recommended to **keep the scan interval at its default value**.  
  Changing these values may cause issues with Bluetooth data transmission.
- **bluetooth_proxy:** must always have **active: true**.
  
  Example (recommended configuration with default values):

  ```yaml
  esp32_ble_tracker:
    scan_parameters:
      active: true
  
  bluetooth_proxy:
    active: true


## Examples
| Size | Example | Preview | Yaml |
|------|---------|---------|------|
| 2.1" (250x128) | Date | ![2.1-date.jpg](./examples/2.1-date.jpg) | [2.1" Date](./examples/2.1-date.yaml) |
| 2.1" (250x128) | Naver Weather | ![2.1-naver-weather.jpg](./examples/2.1-naver-weather.jpg) | [2.1" Naver Weather](./examples/2.1-naver-weather.yaml) |
 2.1" (250x128) | Waste Collection | ![2.1-waste-collection.png](./examples/2.1-waste-collection.png) | [2.1" Waste Collection](./examples/2.1-waste-collection.yaml) |
| 2.1" (250x128) | Wifi | ![2.1-wifi.jpg](./examples/2.1-wifi.jpg) | [2.1" Wifi](./examples/2.1-wifi.yaml) |
| 2.1" (250x128) | TMap time | ![2.1-tmap-time.jpg](./examples/2.1-tmap-time.jpg) | [2.1" TMap time](./examples/2.1-tmap-time.yaml) |
| 2.9" (296x128) | Google Calendar | ![2.9-google-calendar.jpg](./examples/2.9-google-calendar.jpg) | [2.9" Google Calendar](./examples/2.9-google-calendar.yaml) |
| 2.9" (296x128) | Presence Display | ![2.9-presence-display.jpg](./examples/2.9-presence-display.jpg) | [2.9" Presence Display](./examples/2.9-presence-display.yaml) |
| 4.2" (400x300) | Image | ![4.2-image.jpg](./examples/4.2-image.jpg) | [4.2" Image](./examples/4.2-image.yaml) |
| 4.2" (400x300) | Naver Weather | ![4.2-naver-weather.jpg](./examples/4.2-naver-weather.jpg) | [4.2" Naver Weather](./examples/4.2-naver-weather.yaml) |
| 4.2" (400x300) | Date Weather | ![4.2-date-weather.jpg](./examples/4.2-date-weather.jpg) | [4.2" Date Weather](./examples/4.2-date-weather.yaml) |
| 7.5" (800x480) | Google Calendar | ![7.5-google-calendar.jpg](./examples/7.5-google-calendar.jpg) | [7.5" Google Calendar](./examples/7.5-google-calendar.yaml) |
| 7.5" (800x480) | Date Weather | ![7.5-date-weather.jpg](./examples/7.5-date-weather.jpg) | [7.5" Date Weather](./examples/7.5-date-weather.yaml) |
```yaml
action: gicisky.write
data:
  rotate: 0 or 90 or 180 or 270
  background: white or black or red
  payload:
    - type: text
      value: Hello World!
      x: 10
      y: 10
      size: 40
    - type: barcode
      data: "12345"
      code: "code128"
      x: 10
      y: 10
    - type: icon
      value: account-cowboy-hat
      x: 6
      y: 12
      size: 12
    - type: dlimg
      url: "https://image url.png" or "/config/www/images/image.png"
      x: 10
      y: 10
      xsize: 12
      ysize: 12
    - type: qrcode
      data: "qr data"
      x: 140
      y: 50
      boxsize: 2
      border: 2
target:
  device_id: <your device>
```
## Internal Font List
  - fonts/CookieRunBlack.ttf
  - fonts/CookieRunBold.ttf
  - fonts/CookieRunRegular.ttf
  - fonts/GmarketSansTTFBold.ttf
  - fonts/GmarketSansTTFLight.ttf
  - fonts/GmarketSansTTFMedium.ttf
  - fonts/NotoSansKR-Black.ttf
  - fonts/NotoSansKR-Bold.ttf
  - fonts/NotoSansKR-ExtraBold.ttf
  - fonts/NotoSansKR-ExtraLight.ttf
  - fonts/NotoSansKR-Light.ttf
  - fonts/NotoSansKR-Medium.ttf
  - fonts/NotoSansKR-Regular.ttf
  - fonts/NotoSansKR-SemiBold.ttf
  - fonts/NotoSansKR-Thin.ttf
  - fonts/OwnglyphParkDaHyun.ttf

## [Gicisky Image Edit & Uploader](https://eigger.github.io/Gicisky_Image_Uploader.html)

## T-Map
```
#https://openapi.sk.com/products/detail?linkMenuSeq=46
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
        "mainRoadInfo": "Y",
      }
```

## Google Calendar
```
Remote Calendar -> Add google *.ics
```

## Third-Party Custom Components
- [Naver Weather (minumida)](https://github.com/miumida/naver_weather.git)
- [Waste Collection Schedule (mampfes)](https://github.com/mampfes/hacs_waste_collection_schedule.git)
  
## References
- [ATC GICISKY ESL (atc1441)](https://github.com/atc1441/ATC_GICISKY_ESL.git)
- [OpenEPaperLink](https://github.com/OpenEPaperLink/Home_Assistant_Integration.git)
- [bthome](https://github.com/home-assistant/core/tree/dev/homeassistant/components/bthome)
- [bthome-ble](https://github.com/Bluetooth-Devices/bthome-ble.git)
