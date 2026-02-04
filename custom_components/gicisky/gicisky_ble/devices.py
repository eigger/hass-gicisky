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
    manufacturer: str = "Gicisky"
    max_voltage: float = 2.9
    min_voltage: float = 2.2

DEVICE_TYPES: dict[int, DeviceEntry] = {
    0xA0: DeviceEntry(
        name="TFT 21",
        model="TFT 2.1\" BW",
        width=250,
        height=132,
        red=False,
        tft=True,
        rotation=90,
        mirror_x=True
    ),
    0x0B: DeviceEntry(
        name="EPD 21",
        model="EPD 2.1\" BWR",
        width=250,
        height=128,
        rotation=270,
        mirror_x=True
    ),
    0x33: DeviceEntry(
        name="EPD 29",
        model="EPD 2.9\" BWR",
        width=296,
        height=128,
        rotation=90,
        max_voltage=3.0
    ),
    0x4B: DeviceEntry(
        name="EPD 42",
        model="EPD 4.2\" BWR",
        width=400,
        height=300,
        max_voltage=3.0
    ),
    0x2B: DeviceEntry(
        name="EPD 75",
        model="EPD 7.5\" BWR",
        width=800,
        height=480,
        mirror_y=True,
        compression=True,
        max_voltage=3.0
    ),
    0x8B: DeviceEntry(
        name="EPD 102",
        model="EPD 10.2\" BWR",
        width=800,
        height=480,
        mirror_y=True,
        compression=True,
        max_voltage=3.0
    ),
}
# 비트7	비트6	비트5	비트4	비트3	비트2	비트1	비트0
# 픽셀3	픽셀2	픽셀1	메뉴2	메뉴1	색상2	색상1	이미지 유형

# 픽셀
# 1	000	212x104	
# 2	001	128x296	
# 3	010	400x300	
# 4	011	640x384	
# 5	100	유지	
# 6	101	유지	
# 7	110	유지	
# 8	111	유지

# 메뉴
# 1	00	TFT (폴리프 파이낸스	
# 2	01	미국 환경보호청(EPA)	
# 3	10	미국 증권 시세 표시기	
# 4	11	유지

# 색상
# 1	00	흑인과 백인	
# 2	01	블랙, 화이트, 레드	
# 3	10	블랙, 화이트, 옐로우	
# 4	11	유지

# 이미지
# 1	0	듀얼 미러링	
# 2	1	단일 미러

# 0	0	0	0	1	0	0	0	8	0x08	EPA_LCD_212x104_BW
# 0	0	0	0	1	0	1	1	11	0x0B	EPA_LCD_212x104_BWR
# 0	0	1	0	1	0	0	0	40	0x28	EPA_LCD_128x296_BW
# 0	0	1	0	1	0	1	1	43	0x2B	EPA_LCD_128x296_BWR
# 0	0	1	1	0	0	1	1	51	0x33	EPA_LCD_128x296_1_BWR
# 0	1	0	0	1	0	0	0	72	0x48	EPA_LCD_400x300_BW
# 0	1	0	0	1	0	1	1	75	0x4B	EPA_LCD_400x300_BWR
# 0	1	0	0	0	0	0	0	64	0x40	TFT_LCD_400x300_BW
# 0	1	0	0	0	0	1	0	66	0x42	TFT_LCD_400x300_BWR
# 0	1	1	0	1	0	0	0	104	0x68	EPA_LCD_640x384_BW
# 0	1	1	0	1	0	1	0	106	0x6A	EPA_LCD_640x384_BWR
# 0	0	0	0	0	0	0	0	0	0x00	EPA_LCD_212x104_BW
# 0	0	0	0	0	0	1	0	2	0x02	EPA_LCD_212x104_BWR
# 0	0	1	0	0	0	0	0	32	0x20	EPA_LCD_128x296_BW
# 0	0	1	0	0	0	1	0	34	0x22	EPA_LCD_128x296_BWR
# 0	0	1	0	0	0	1	0	34	0x22	EPA_LCD_128x296_BWR_1
# 0	1	0	0	0	0	0	0	64	0x40	EPA_LCD_400x300_BW
# 0	1	0	0	0	0	1	0	66	0x42	EPA_LCD_400x300_BWR
# 0	1	0	0	0	0	0	0	64	0x40	TFT_LCD_400x300_BW
# 0	1	0	0	0	0	1	0	66	0x42	TFT_LCD_400x300_BWR
# 0	1	1	0	0	0	0	0	96	0x60	EPA_LCD_640x384_BW
# 0	1	1	0	0	0	1	0	98	0x62	EPA_LCD_640x384_BWR
#A0 = 101 00 00 0
#0B = 000 01 01 1
#33 = 001 10 01 1
#4B = 010 01 01 1
#2B = 001 01 01 1