# gicisky_ble.py

from __future__ import annotations
from enum import Enum
import logging
import struct
from typing import Any, Callable, TypeVar
from asyncio import Event, wait_for, sleep
from PIL import Image
from bleak import BleakClient, BleakError
from bleak.backends.device import BLEDevice
from bleak_retry_connector import establish_connection

from .devices import DeviceEntry
from .compression import compress as compress_data

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
            try:
                if self.client.is_connected:
                    await self.client.clear_cache()
                    await self.client.disconnect()
            except Exception:
                pass
            raise
    return wrapper  # type: ignore

async def update_image(
    ble_device: BLEDevice,
    device: DeviceEntry,
    image: Image,
    threshold: int,
    red_threshold: int,
    attempt: int = 1,
    write_delay_ms: int = 0
) -> bool:
    client: BleakClient | None = None
    try:
        client = await establish_connection(BleakClient, ble_device, ble_device.address)
        services = client.services
        char_uuids = [
            c.uuid
            for svc in services if svc.uuid.lower().startswith("0000f")
            for c in svc.characteristics
        ]
        if len(char_uuids) < 2:
            raise BleakServiceMissing(f"UUID Len: {len(char_uuids)}")
        sorted_uuids = sorted(char_uuids, key=lambda x: int(x[4:8], 16))
        gicisky = GiciskyClient(client, sorted_uuids, device, attempt, write_delay_ms)
        await gicisky.start_notify()
        success = await gicisky.write_image(image, threshold, red_threshold)
        try:
            await gicisky.stop_notify()
        except Exception as e:
            _LOGGER.warning(f"{ble_device.address} Already stop notify: {e}")
        return success
    except Exception as e:
        _LOGGER.error(f"Update failed: {e}")
        return False
    finally:
        if client:
            try:
                if client.is_connected:
                    await client.disconnect()
            except Exception as e:
                _LOGGER.warning(f"{ble_device.address} Already disconnected: {e}")

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
        device: DeviceEntry,
        attempt: int = 1,
        write_delay_ms: int = 0
    ) -> None:
        self.client = client
        self.attempt = attempt
        self.write_delay_ms = write_delay_ms
        self.cmd_uuid, self.img_uuid = uuids[:2]
        self.width = device.width
        self.height = device.height
        self.support_red = device.red
        self.tft = device.tft
        self.rotation = device.rotation
        self.mirror_x = device.mirror_x
        self.mirror_y = device.mirror_y
        self.compression = device.compression
        self.compression2 = device.compression2
        self.invert_luminance = device.invert_luminance
        self.four_color = device.four_color
        self.packet_size = 0 #(device.width * device.height) // 8 * (2 if device.red else 1)
        self.event: Event = Event()
        self.command_data: bytes | None = None
        self.image_packets: list[int] = []

    @disconnect_on_missing_services
    async def start_notify(self) -> None:
        await self.client.start_notify(self.cmd_uuid, self._notification_handler)
        await sleep(1.0)

    @disconnect_on_missing_services
    async def stop_notify(self) -> None:
        await self.client.stop_notify(self.cmd_uuid)

    @disconnect_on_missing_services
    async def write(self, uuid: str, data: bytes, response = False) -> None:
        chunk = len(data)
        delay = self.write_delay_ms / 1000.0  # Convert ms to seconds
        delay += (0.05 * (self.attempt - 1))
        _LOGGER.debug("Write UUID=%s data=%s attempt=%s delay=%s", uuid, len(data), self.attempt, delay)
        for i in range(0, len(data), chunk):
            await self.client.write_gatt_char(uuid, data[i : i + chunk], response)
            if delay > 0:
                await sleep(delay)

    def _notification_handler(self, _: Any, data: bytearray) -> None:
        if self.command_data is None:
            self.command_data = bytes(data)
            self.event.set()

    async def read(self, timeout: float = 5.0) -> bytes:
        await wait_for(self.event.wait(), timeout)
        data = self.command_data or b""
        _LOGGER.debug("Received: %s", data.hex())
        return data

    async def write_with_response(self, uuid, packet: bytes) -> bytes:
        # self.command_data = None
        # self.event.clear()
        # await self.write(uuid, packet)
        # return await self.read()
        last_exception = None
        max_retries = 1
        for attempt in range(1, max_retries + 1):
            try:
                self.command_data = None
                self.event.clear()
                await self.write(uuid, packet)
                return await self.read()
            except Exception as e:
                last_exception = e
                if attempt < max_retries:
                    _LOGGER.warning(f"Write retry (attempt {attempt}/{max_retries})")
                    await sleep(0.5)
                    continue
                raise last_exception
    
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
        last_part = -1
        same_part_count = 0
        status = self.Status.START
        self.image_packets = self._make_image_packet(image, threshold, red_threshold)
        self.packet_size = len(self.image_packets)
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
                    new_part = int.from_bytes(data[2:6], "little")
                    
                    # Check for consecutive identical part values
                    if new_part == last_part:
                        same_part_count += 1
                        if same_part_count >= 3:
                            raise Exception(f"Part stalled: part={new_part} repeated 3 times")
                    else:
                        same_part_count = 1
                        last_part = new_part
                    part = new_part
                else:
                    raise Exception(f"Status Error: {status}")
            return True
        except Exception as e:
            _LOGGER.error(f"Write failed: {e}")
            return False
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

        if self.four_color:
            return self._make_four_color_packet(pixels, width, height, threshold, red_threshold)

        if self.compression2:
            return self._compress_byte_data_2(pixels, width, height, threshold, red_threshold)

        byte_data = []
        byte_data_red = []
        current_byte = 0
        current_byte_red = 0
        bit_pos = 7

        for y in range(height - 1, -1, -1) if self.mirror_y else range(height):
            for x in range(width - 1, -1, -1) if self.mirror_x else range(width):
                px = (x, y)
                r, g, b = pixels[px]

                luminance = ((r * 38) + (g * 75) + (b * 15)) >> 7
                if self.invert_luminance:
                    if luminance < threshold:
                        current_byte |= (1 << bit_pos)
                else:
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



        if self.compression:
            return self._compress_byte_data(byte_data, byte_data_red)
        
        combined = byte_data + byte_data_red if self.support_red else byte_data
        return list(bytearray(combined))

    def _make_four_color_packet(self, pixels, width, height, threshold, red_threshold) -> list[int]:
        byte_data = []
        current_byte = 0
        shift_counter = 3
        
        for y in range(height - 1, -1, -1) if self.mirror_y else range(height):
            for x in range(width - 1, -1, -1) if self.mirror_x else range(width):
                r, g, b = pixels[(x, y)]
                
                # Calculate weighted luminance for white detection
                luminance = ((r * 38) + (g * 75) + (b * 15)) >> 7
                
                if self.invert_luminance:
                    is_white = luminance < threshold
                else:
                    is_white = luminance > threshold
                is_red = r > red_threshold
                is_green = g > red_threshold
                is_blue = b > red_threshold
                
                if is_green and is_red and is_blue:
                   is_green = False
                
                if is_red and is_white:
                    is_red = False

                # 00: Black, 01: White, 10: Yellow, 11: Red
                val = 2 if is_green else (3 if is_red else (1 if is_white else 0))

                current_byte |= (val << (shift_counter * 2))
                
                if shift_counter == 0:
                    byte_data.append(current_byte)
                    current_byte = 0
                    shift_counter = 3
                else:
                    shift_counter -= 1
        
        return list(bytearray(byte_data))
    
    def _compress_byte_data(self, byte_data, byte_data_red) -> list[int]:
        byte_per_line = self.height // 8
        buf = [0x00, 0x00, 0x00, 0x00]
        pos = 0
        for _ in range(self.width):
            buf.extend([
                0x75,
                byte_per_line + 7,
                byte_per_line,
                0x00, 0x00, 0x00, 0x00
            ])
            buf.extend(byte_data[pos:pos + byte_per_line])
            pos += byte_per_line

        if byte_data_red is not None:
            pos = 0
            for _ in range(self.width):
                buf.extend([
                    0x75,
                    byte_per_line + 7,
                    byte_per_line,
                    0x00, 0x00, 0x00, 0x00
                ])
                buf.extend(byte_data_red[pos:pos + byte_per_line])
                pos += byte_per_line

        total_len = len(buf)
        buf[0] = total_len & 0xFF
        buf[1] = (total_len >> 8) & 0xFF
        buf[2] = (total_len >> 16) & 0xFF
        buf[3] = (total_len >> 24) & 0xFF

        return list(bytearray(buf))

    def _compress_byte_data_2(self, pixels, width, height, threshold, red_threshold) -> list[int]:
        """1-bit dual plane BWR packing + compress. Used when compression2=True.

        Part1: BW plane (1=white, 0=black), MSB first, row-major
        Part2: Red plane (1=red, 0=not red), MSB first, row-major
        """
        total_pixels = width * height
        plane_bytes = total_pixels // 8
        bw_plane = bytearray(plane_bytes)
        red_plane = bytearray(plane_bytes)
        byte_idx = 0
        bit_pos = 7  # MSB first
        y_range = range(height - 1, -1, -1) if self.mirror_y else range(height)
        x_range = range(width - 1, -1, -1) if self.mirror_x else range(width)
        for y in y_range:
            for x in x_range:
                r, g, b = pixels[x, y]
                luminance = (r * 38 + g * 75 + b * 15) >> 7
                if self.invert_luminance:
                    is_white = luminance < threshold
                else:
                    is_white = luminance > threshold
                is_red = (r > red_threshold) and (g < red_threshold)
                if is_white:
                    bw_plane[byte_idx] |= (1 << bit_pos)
                if is_red:
                    red_plane[byte_idx] |= (1 << bit_pos)
                bit_pos -= 1
                if bit_pos < 0:
                    byte_idx += 1
                    bit_pos = 7
        raw = bytes(bw_plane) + bytes(red_plane)
        try:
            compressed = compress_data(raw, force_raw=True)  # TODO: QuickLZ 호환 확인 후 force_raw 제거
            # compress_data 반환: [4B part2_len] + compressed_part1 + compressed_part2
            # prefix 없이 그대로 반환 (7.5"의 total_len 헤더와 동일한 위치)
            _LOGGER.debug(
                "Compress (1-bit dual plane BWR): raw=%s -> %s bytes, head32=%s",
                len(raw),
                len(compressed),
                compressed[:32].hex() if len(compressed) >= 32 else compressed.hex(),
            )
            return list(compressed)
        except Exception as e:
            _LOGGER.warning("Compression failed: %s. Using uncompressed data.", e)
            return list(raw)

    def _make_cmd_packet(self, cmd: int) -> bytes:
        if cmd == 0x02:
            if self.compression2:
                # 10.2" 등 compression2 디바이스: 6바이트 [02] [4B size LE] [01]
                # Wireshark 확인: 02:4b:2a:01:00:01
                packet = bytearray(6)
                packet[0] = cmd
                struct.pack_into("<I", packet, 1, self.packet_size)
                packet[5] = 0x01  # compression2 모드 플래그
                return bytes(packet)
            else:
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


def decompress_byte_data(payload: bytes, width: int, height: int) -> tuple[list[int], list[int] | None]:
    """
    _compress_byte_data() 출력 형식의 역연산.
    compression=True 디바이스(예: 7.5" 0x2B) 패킷을 복원해 (byte_data, byte_data_red) 반환.
    byte_data_red는 없으면 None.
    """
    if len(payload) < 4:
        return ([], None)
    byte_per_line = height // 8
    chunk_header = 7  # 0x75, total_byte, uncompressed_byte, 0x00*4
    chunk_size = chunk_header + byte_per_line
    pos = 4
    byte_data: list[int] = []
    for _ in range(width):
        if pos + chunk_size > len(payload) or payload[pos] != 0x75:
            break
        pos += chunk_header
        byte_data.extend(payload[pos : pos + byte_per_line])
        pos += byte_per_line
    byte_data_red: list[int] | None = None
    if pos < len(payload) and payload[pos] == 0x75:
        byte_data_red = []
        for _ in range(width):
            if pos + chunk_size > len(payload) or payload[pos] != 0x75:
                break
            pos += chunk_header
            byte_data_red.extend(payload[pos : pos + byte_per_line])
            pos += byte_per_line
    return (byte_data, byte_data_red)
