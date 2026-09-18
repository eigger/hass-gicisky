"""Experimental XTE 400x300 transport, reverse engineered from one capture.

The palette and opaque image metadata need hardware validation. This protocol
is separate from Gicisky's Fxxx services despite sharing a 2-bit pixel layout.
"""

from __future__ import annotations

import asyncio
import math

from PIL import Image

SERVICE_UUID = "00002760-08c2-11e1-9073-0e8ac72e1001"
WRITE_UUID = "00002760-08c2-11e1-9073-0e8ac72e0001"
NOTIFY_UUID = "00002760-08c2-11e1-9073-0e8ac72e0002"
MANUFACTURER_ID = 0x5258
# Two observed PSJ-420 advertisements differ only in the final byte (1e/1b).
# Its meaning is unconfirmed; exclude it from the model fingerprint, but keep
# the exact length and remaining bytes to avoid claiming other XTE models.
ADVERTISEMENT = bytes.fromhex("fd024002009964060102ffff1e")
WIDTH, HEIGHT = 400, 300
BLOCK_DATA_SIZE = 1211  # 1220-byte logical block, including its 9-byte header.
PALETTE = ((0, 0, 0), (255, 255, 255), (255, 255, 0), (255, 0, 0))


def is_psj420_advertisement(data: bytes | None) -> bool:
    """Recognize the observed PSJ-420 signature, ignoring its changing tail."""
    return data is not None and len(data) == 13 and data[:12] == ADVERTISEMENT[:12]


def pack_pixels(image: Image.Image) -> bytes:
    """Pack four pixels per byte, most significant pixel first."""
    if image.size != (WIDTH, HEIGHT):
        raise ValueError("XTE requires a 400x300 image")
    rgb = image.convert("RGB")
    # Quantize using a fixed palette without dithering, like the HA renderer.
    result = bytearray()
    packed = 0
    color_cache = {color: index for index, color in enumerate(PALETTE)}
    raw = rgb.tobytes()
    for i, pixel in enumerate(zip(raw[0::3], raw[1::3], raw[2::3])):
        value = color_cache.get(pixel)
        if value is None:
            value = min(range(4), key=lambda n: sum(
                (pixel[c] - PALETTE[n][c]) ** 2 for c in range(3)
            ))
            color_cache[pixel] = value
        packed = (packed << 2) | value
        if i % 4 == 3:
            result.append(packed)
            packed = 0
    return bytes(result)


def encode_rle(data: bytes) -> bytes:
    """Encode (count, value) runs, splitting runs at 255 bytes."""
    output = bytearray()
    pos = 0
    while pos < len(data):
        end = pos + 1
        while end < len(data) and end - pos < 255 and data[end] == data[pos]:
            end += 1
        output.extend((end - pos, data[pos]))
        pos = end
    return bytes(output)


def make_image_object(pixels: bytes) -> bytes:
    """Build XTEK metadata, RLE image and 32-bit additive checksum."""
    if len(pixels) != WIDTH * HEIGHT // 4:
        raise ValueError("Expected 30000 bytes of packed XTE pixels")
    # The captured encoder resets its run at byte 15000, halfway through the
    # frame. Preserve that boundary even when both adjacent bytes are equal.
    midpoint = len(pixels) // 2
    compressed = encode_rle(pixels[:midpoint]) + encode_rle(pixels[midpoint:])
    # Preserve observed opaque fields (offsets 12..24 and 33) for this profile.
    metadata = bytes.fromhex("01000000110000000000000000")
    body = (metadata + WIDTH.to_bytes(4, "big") + HEIGHT.to_bytes(4, "big")
            + b"\x01" + len(compressed).to_bytes(4, "big") + compressed)
    return (b"XTEK" + (sum(body) & 0xFFFFFFFF).to_bytes(4, "big")
            + (12 + len(body)).to_bytes(4, "big") + body)


def make_command(payload: bytes) -> bytes:
    """Control frames use a one-byte total length and payload checksum."""
    if len(payload) > 249:
        raise ValueError("XTE command too long")
    return b"XTE\x01" + bytes((6 + len(payload), sum(payload) & 0xFF)) + payload


def make_blocks(image_object: bytes) -> list[bytes]:
    """Frame the object into numbered, checksummed logical blocks."""
    count = math.ceil(len(image_object) / BLOCK_DATA_SIZE)
    if not 1 <= count <= 255:
        raise ValueError("Invalid XTE block count")
    blocks = []
    for number in range(count):
        payload = bytes((count, number)) + image_object[
            number * BLOCK_DATA_SIZE:(number + 1) * BLOCK_DATA_SIZE
        ]
        blocks.append(b"XTE\x02" + (7 + len(payload)).to_bytes(2, "big")
                      + bytes((sum(payload) & 0xFF,)) + payload)
    return blocks


class XteClient:
    """Send the observed transaction, requiring both application responses."""

    def __init__(self, client, attempt: int = 1, write_delay_ms: int = 0):
        self.client = client
        self.delay = max(0, write_delay_ms) / 1000 + 0.05 * max(0, attempt - 1)
        self.responses: asyncio.Queue[bytes] = asyncio.Queue()
        self.timeout = 5.0

    def _notification(self, _sender, data: bytearray) -> None:
        self.responses.put_nowait(bytes(data))

    async def _write(self, characteristic, data: bytes, chunk_size: int) -> None:
        for offset in range(0, len(data), chunk_size):
            await self.client.write_gatt_char(
                characteristic, data[offset:offset + chunk_size], response=False
            )
            if self.delay:
                await asyncio.sleep(self.delay)

    async def _command(self, characteristic, payload: bytes, chunk_size: int,
                       expected_payload: bytes) -> None:
        while not self.responses.empty():
            self.responses.get_nowait()
        await self._write(characteristic, make_command(payload), chunk_size)
        async with asyncio.timeout(self.timeout):
            while True:
                response = await self.responses.get()
                if not response.startswith(b"XTE\x04"):
                    continue
                if len(response) < 6:
                    raise ValueError("Truncated XTE response")
                length = response[4]
                if length < 7 or length > len(response):
                    raise ValueError("Invalid XTE response length")
                body = response[6:length]
                if sum(body) & 0xFF != response[5]:
                    raise ValueError("Invalid XTE response checksum")
                # Only the captured positive responses are currently known.
                # Never treat an arbitrary notification as transfer success.
                if body != expected_payload:
                    raise ValueError(f"Unexpected XTE response: {body.hex()}")
                return

    async def write_image(self, image: Image.Image) -> bool:
        service = self.client.services.get_service(SERVICE_UUID)
        if service is None:
            raise ValueError("XTE service missing")
        write_char = service.get_characteristic(WRITE_UUID)
        notify_char = service.get_characteristic(NOTIFY_UUID)
        if write_char is None or notify_char is None:
            raise ValueError("XTE characteristics missing")
        if "write-without-response" not in write_char.properties or "notify" not in notify_char.properties:
            raise ValueError("XTE characteristic properties do not match")
        chunk_size = min(244, write_char.max_write_without_response_size)
        # Only 244-byte writes were captured. Fail explicitly on an adapter
        # with an insufficient negotiated MTU instead of guessing framing.
        if chunk_size < 244:
            raise ValueError("XTE requires ATT MTU >= 247 (244-byte writes); check adapter/proxy")
        image_object = await asyncio.to_thread(lambda: make_image_object(pack_pixels(image)))
        blocks = make_blocks(image_object)
        await self.client.start_notify(notify_char, self._notification)
        try:
            await self._command(write_char, b"\x01" + len(image_object).to_bytes(4, "big"),
                                chunk_size, bytes.fromhex("01ffbd"))
            for block in blocks:
                await self._write(write_char, block, chunk_size)
            await self._command(write_char, b"\x04\x00", chunk_size, bytes.fromhex("04ff"))
            return True
        finally:
            # Disconnect in update_image is still attempted if unsubscribe fails.
            await self.client.stop_notify(notify_char)
