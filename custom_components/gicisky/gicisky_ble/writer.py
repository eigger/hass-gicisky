# gicisky_ble.py

from __future__ import annotations
from enum import Enum
import logging
import struct
import traceback
from typing import Any, Callable, TypeVar
from asyncio import Event, wait_for, sleep
from PIL import Image
from bleak import BleakClient, BleakError
from bleak.backends.device import BLEDevice
from bleak_retry_connector import establish_connection

from .devices import DeviceEntry
from .const import SERVICE_GICISKY

_LOGGER = logging.getLogger(__name__)

# 예외 정의
class BleakCharacteristicMissing(BleakError):
    """Characteristic Missing"""

class BleakServiceMissing(BleakError):
    """Service Missing"""

WrapFuncType = TypeVar("WrapFuncType", bound=Callable[..., Any])

def disconnect_on_missing_services(func: WrapFuncType) -> WrapFuncType:
    """Missing services"""
    async def wrapper(self, *args, **kwargs):
        try:
            return await func(self, *args, **kwargs)
        except (BleakServiceMissing, BleakCharacteristicMissing):
            if self.client.is_connected:
                await self.client.clear_cache()
                await self.client.disconnect()
            raise
    return wrapper  # type: ignore

async def update_image(
    ble_device: BLEDevice,
    device: DeviceEntry,
    image: Image,
    threshold: int,
    red_threshold: int
) -> bool:
    client: BleakClient | None = None
    try:
        client = await establish_connection(BleakClient, ble_device, ble_device.address)
        services = client.services
        char_uuids = [
            c.uuid
            for svc in services if svc.uuid == SERVICE_GICISKY
            for c in svc.characteristics
        ]
        if len(char_uuids) != 3:
            raise BleakServiceMissing(f"UUID Len: {len(char_uuids)}")
        gicisky = GiciskyClient(client, char_uuids, device)
        await gicisky.start_notify()
        await gicisky.write_image(image, threshold, red_threshold)
        await gicisky.stop_notify()
        return True
    except Exception as e:
        _LOGGER.error("Fail image write: %s", e)
        _LOGGER.error(traceback.print_exc())
        return False
    finally:
        if client and client.is_connected:
            await client.disconnect()

class GiciskyClient:
    class Status(Enum):
        START = 0
        SIZE_DATA = 1
        IMAGE = 2
        IMAGE_DATA = 3
        
    def __init__(
        self,
        client: BleakClient,
        uuids: list[str],
        device: DeviceEntry
    ) -> None:
        self.client = client
        self.cmd_uuid, self.img_uuid = uuids[:2]
        self.width = device.width
        self.height = device.height
        self.support_red = device.red
        self.tft = device.tft
        self.rotation = device.rotation
        self.mirror = device.mirror
        self.packet_size = (device.width * device.height) // 8 * (2 if device.red else 1)
        self.event: Event = Event()
        self.command_data: bytes | None = None
        self.image_packets: list[int] = []

    @disconnect_on_missing_services
    async def start_notify(self) -> None:
        await self.client.start_notify(self.cmd_uuid, self._notification_handler)
        await sleep(0.5)

    @disconnect_on_missing_services
    async def stop_notify(self) -> None:
        await self.client.stop_notify(self.cmd_uuid)

    @disconnect_on_missing_services
    async def write(self, uuid: str, data: bytes) -> None:
        _LOGGER.debug("Write UUID=%s data=%s", uuid, len(data))
        chunk = 20 # len(data)
        for i in range(0, len(data), chunk):
            await self.client.write_gatt_char(uuid, data[i : i + chunk])
            await sleep(0.01)

    def _notification_handler(self, _: Any, data: bytearray) -> None:
        if self.command_data == None:
            self.command_data = bytes(data)
            self.event.set()

    async def read(self, timeout: float = 5.0) -> bytes:
        await wait_for(self.event.wait(), timeout)
        data = self.command_data or b""
        _LOGGER.debug("Received: %s", data.hex())
        return data

    async def write_with_response(self, uuid, packet: bytes) -> bytes:
        self.command_data = None
        self.event.clear()
        await self.write(uuid, packet)
        return await self.read()
    
    async def write_start_with_response(self) -> bytes:
        return await self.write_with_response(self.cmd_uuid, self._make_cmd_packet(0x01))

    async def write_size_with_response(self) -> bytes:
        return await self.write_with_response(self.cmd_uuid, self._make_cmd_packet(0x02))

    async def write_start_image_with_response(self) -> bytes:
        return await self.write_with_response(self.cmd_uuid, self._make_cmd_packet(0x03))

    async def write_image_with_response(self, part:int) -> bytes:
        return await self.write_with_response(self.img_uuid, self._make_size_packet(part))
    
    async def write_image(self, image: Image, threshold: int, red_threshold: int) -> None:
        part = 0
        count = 0
        status = self.Status.START
        self.image_packets = self._make_image_packet(image, threshold, red_threshold)
        try:
            while True:
                if status == self.Status.START:
                    data = await self.write_start_with_response()
                    if len(data) < 3 or data[0] != 0x01 or data[1] != 0xF4 or data[2] != 0x00:
                        raise Exception(f"Packet Error: {data}")
                    status = self.Status.SIZE_DATA
                
                elif status == self.Status.SIZE_DATA:  
                    data = await self.write_size_with_response()
                    if len(data) < 1 or data[0] != 0x02:
                        raise Exception(f"Packet Error: {data}")
                    status = self.Status.IMAGE

                elif status == self.Status.IMAGE:  
                    data = await self.write_start_image_with_response()
                    if len(data) < 6 or data[0] != 0x05 or data[1] != 0x00:
                        raise Exception(f"Packet Error: {data}")
                    status = self.Status.IMAGE_DATA

                elif status == self.Status.IMAGE_DATA:  
                    data = await self.write_image_with_response(part)
                    if len(data) < 6 or data[0] != 0x05 or data[1] != 0x00:
                        break
                    part = int.from_bytes(data[2:6], "little")
                    count += 1
                    if part != count:
                        raise Exception(f"Count Error: {part} {count}")
                else:
                    break
        except Exception as e:
            _LOGGER.error("Write Error: %s", e)
        finally:
            _LOGGER.debug("Finish")

    def _overlay_images(
        self,
        base: Image,
        overlay: Image,
        position: tuple[int, int] = (0, 0),
        center: bool = False
    ) -> Image:
        if base.mode != 'RGB':
            base_rgb = base.convert('RGB')
        else:
            base_rgb = base.copy()

        w_base, h_base = base_rgb.size

        ov = overlay.convert('RGB')
        if ov.width > w_base or ov.height > h_base:
            ov = ov.crop((0, 0, w_base, h_base))

        if center:
            x = (w_base - ov.width) // 2
            y = (h_base - ov.height) // 2
            position = (x, y)

        base_rgb.paste(ov, position)
        return base_rgb

    def _make_image_packet(self, image: Image, threshold: int, red_threshold: int) -> list[int]:
        img = Image.new('RGB', (self.width, self.height), color='white')
        img = self._overlay_images(img, image)
        tft = self.tft
        rotation = self.rotation
        width, height = img.size
        if tft:
            img = img.resize((width // 2, height * 2), resample=Image.BICUBIC)

        if rotation != 0:
            img = img.rotate(rotation, expand=True)

        width, height = img.size
        pixels = img.load()

        byte_data = []
        byte_data_red = []
        current_byte = 0
        current_byte_red = 0
        bit_pos = 7

        for y in range(height):
            for x in range(width - 1, -1, -1) if self.mirror else range(width):
                px = (x, y)
                r, g, b = pixels[px]

                luminance = 0.2126 * r + 0.7152 * g + 0.0722 * b
                if luminance > threshold:
                    current_byte |= (1 << bit_pos)
                if (r > red_threshold) and (g < red_threshold):
                    current_byte_red |= (1 << bit_pos)

                bit_pos -= 1
                if bit_pos < 0:
                    byte_data.append(current_byte)
                    byte_data_red.append(current_byte_red)
                    current_byte = 0
                    current_byte_red = 0
                    bit_pos = 7

        if bit_pos != 7:
            byte_data.append(current_byte)
            byte_data_red.append(current_byte_red)

        combined = byte_data + byte_data_red if self.support_red else byte_data
        return list(bytearray(combined))

    def _make_cmd_packet(self, cmd: int) -> bytes:
        if cmd == 0x02:
            packet = bytearray(8)
            packet[0] = cmd
            struct.pack_into("<I", packet, 1, self.packet_size)
            packet[-3:] = b"\x00\x00\x00"
            return bytes(packet)
        return bytes([cmd])

    def _make_size_packet(self, part: int) -> bytes:
        start = part * 240
        chunk = self.image_packets[start : start + min(240, self.packet_size - start)]
        packet = bytearray(4 + len(chunk))
        struct.pack_into("<I", packet, 0, part)
        packet[4:] = bytes(chunk)
        return bytes(packet)
