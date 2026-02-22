import dataclasses


@dataclasses.dataclass
class DeviceEntry:
    name: str
    model: str
    width: int
    height: int
    red: bool = True
    tft: bool = False
    mirror_x: bool = False
    mirror_y: bool = False
    rotation: int = 0
    compression: bool = False
    compression2: bool = False  # True: 2-bit BWR packing + compress (e.g. EPD 10.2")
    invert_luminance: bool = False
    manufacturer: str = "Gicisky"
    max_voltage: float = 2.9
    min_voltage: float = 2.2
    four_color: bool = False

# ===========================================================================================
#     ID = ((data[4] << 8) | data[0]) & 0x3FFF
#     ID | Hex    | Inch   | Model Name
# -------|--------|--------|--------------------------
#    686 | 0x02AE | 1.5"   | EPA_LCD_200x200_BWRY
#      8 | 0x0008 | 2.1"   | EPA_LCD_212x104_BW
#     11 | 0x000B | 2.1"   | EPA_LCD_212x104_BWR
#    160 | 0x00A0 | 2.1"   | EPA_LCD_250x132_BWR
#    192 | 0x00C0 | 2.1"   | TFT_LCD_196x96_BWR
#    264 | 0x0108 | 2.1"   | EPA_LCD_250x122_BW
#    267 | 0x010B | 2.1"   | EPA_LCD_250x122_BWR
#    270 | 0x010E | 2.1"   | EPA_LCD_250x122_BWRY
#     40 | 0x0028 | 2.9"   | EPA_LCD_296x128_BW
#     43 | 0x002B | 2.9"   | EPA_LCD_296x128_BWR
#     46 | 0x002E | 2.9"   | EPA_LCD_296x128_BWRY
#     48 | 0x0030 | 2.9"   | EPA_LCD_296x128_BW_1
#     51 | 0x0033 | 2.9"   | EPA_LCD_296x128_1_BWR
#    384 | 0x0180 | 2.9"   | TFT_LCD_168x384_BW
#    386 | 0x0182 | 2.9"   | TFT_LCD_168x384_BWR
#    480 | 0x01E0 | 2.9"   | TFT_LCD_384x168_BW
#    482 | 0x01E2 | 2.9"   | TFT_LCD_384x168_BWR
#    718 | 0x02CE | 2.9"   | EPA_LCD_296x152_BWRY
#    328 | 0x0148 | 3.7"   | EPA_LCD_280x480_BW
#     64 | 0x0040 | 4.2"   | TFT_LCD_400x300_BW
#     66 | 0x0042 | 4.2"   | TFT_LCD_400x300_BWR
#     72 | 0x0048 | 4.2"   | EPA_LCD_400x300_BW
#     75 | 0x004B | 4.2"   | EPA_LCD_400x300_BWR
#     78 | 0x004E | 4.2"   | EPA_LCD_400x300_BWRY
#    552 | 0x0228 | 3.7"   | EPA_LCD_240x416_BW
#    555 | 0x022B | 3.7"   | EPA_LCD_240x416_BWR
#    558 | 0x022E | 3.7"   | EPA_LCD_240x416_BWRY
#   4514 | 0x11A2 | 4.2"   | TFT_LCD_210x480_Color
#   4610 | 0x1202 | 4.2"   | TFT_LCD_480x210_Color
#    104 | 0x0068 | 5.8"   | EPA_LCD_640x384_BW
#    106 | 0x006A | 5.8"   | EPA_LCD_640x384_BWR
#    122 | 0x007A | 5.8"   | EPA_LCD_640x384_BWR_ZP
#    224 | 0x00E0 | 5.8"   | TFT_LCD_640x360_BW
#    654 | 0x028E | 5.8"   | EPA_LCD_528x768_BWRY
#   4684 | 0x124C | 5.8"   | EPA_LCD_400x600_Color
#   4556 | 0x11CC | 7.3"   | EPA_LCD_1024x576_Color
#    296 | 0x0128 | 7.5"   | EPA_LCD_800x480_BW
#    299 | 0x012B | 7.5"   | EPA_LCD_800x480_BWR
#    302 | 0x012E | 7.5"   | EPA_LCD_800x480_BWRY
#    310 | 0x0136 | 7.5"   | EPA_LCD_800x480_BWRY_1
#    315 | 0x013B | 7.5"   | EPA_LCD_800x480_BWR_ZP
#    318 | 0x013E | 7.5"   | EPA_LCD_800x480_BWRY_ZP
#   4408 | 0x1138 | 7.5"   | EPA_LCD_800x480_BWRGBYO_ZP
#   4412 | 0x113C | 7.5"   | EPA_LCD_800x480_BWRGBY_ZP
#   2667 | 0x0A6B | 9.7"   | EPA_LCD_792x272_BWR
#   2670 | 0x0A6E | 9.7"   | EPA_LCD_792x272_BWRY
#   2699 | 0x0A8B | 9.7"   | EPA_LCD_272x792_BWR
#   2702 | 0x0A8E | 9.7"   | EPA_LCD_272x792_BWRY
#    136 | 0x0088 | 10.2"  | EPA_LCD_960x640_BW
#    139 | 0x008B | 10.2"  | EPA_LCD_960x640_BWR
#    142 | 0x008E | 10.2"  | EPA_LCD_960x640_BWRY
#    155 | 0x009B | 10.2"  | EPA_LCD_960x640_BWR_ZP
#   2635 | 0x0A4B | 10.2"  | EPA_LCD_960x680_BWR
#    379 | 0x017B | 11.6"  | EPA_LCD_1360X480_BWR
#   4716 | 0x126C | 13.3"  | EPA_LCD_1600x1200_BWR
# ===========================================================================================

DEVICE_TYPES: dict[int, DeviceEntry] = {
    0x00A0: DeviceEntry(
        name="TFT 21",
        model="TFT 2.1\" BW",
        width=250,
        height=132,
        red=False,
        tft=True,
        rotation=90,
        mirror_x=True
    ),
    0x000B: DeviceEntry(
        name="EPD 21",
        model="EPD 2.1\" BWR",
        width=212,
        height=104,
        rotation=270,
        mirror_x=True
    ),
    0x010B: DeviceEntry(
        name="EPD 21",
        model="EPD 2.1\" BWR",
        width=250,
        height=128,
        rotation=270,
        mirror_x=True
    ),
    0x0033: DeviceEntry(
        name="EPD 29",
        model="EPD 2.9\" BWR",
        width=296,
        height=128,
        rotation=90,
        max_voltage=3.0
    ),
    0x002E: DeviceEntry(
        name="EPD 29",
        model="EPD 2.9\" BWRY",
        width=296,
        height=128,
        rotation=90,
        max_voltage=3.0,
        four_color=True,
    ),
    0x022B: DeviceEntry(
        name="EPD 37",
        model="EPD 3.7\" BWR",
        width=240,
        height=416,
        mirror_y=True,
        max_voltage=3.0
    ),
    0x004E: DeviceEntry(
        name="EPD 42",
        model="EPD 4.2\" BWRY",
        width=400,
        height=300,
        max_voltage=3.0,
        four_color=True,
    ),
    0x004B: DeviceEntry(
        name="EPD 42",
        model="EPD 4.2\" BWR",
        width=400,
        height=300,
        max_voltage=3.0
    ),
    0x012B: DeviceEntry(
        name="EPD 75",
        model="EPD 7.5\" BWR",
        width=800,
        height=480,
        mirror_y=True,
        #compression=True,
        invert_luminance=True,
        compression2=True,
        max_voltage=3.0
    ),
    0x008B: DeviceEntry(
        name="EPD 102",
        model="EPD 10.2\" BWR",
        width=960,
        height=640,
        compression2=True,
        max_voltage=3.2
    ),
}

#2.1 0x0B 0x1D 0x81 0x01 0x41
#2.9 0x33 0x1D 0x81 0x01 0x40
#3.7 0x2B 0x1E 0x81 0x01 0x02
#4.2 0x4B 0x1E 0x81 0x01 0x40
#7.5 0x2B 0x1E 0x01 0x01 0x01
#10.2 0x8B 0x1F 0x01 0x01 0x00