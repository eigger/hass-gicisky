"""Codec and transport checks without a BLE adapter or Home Assistant."""

import asyncio
import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock

from PIL import Image
import pytest

from custom_components.gicisky.gicisky_ble.xte import (
    XteClient, SERVICE_UUID, WRITE_UUID, NOTIFY_UUID,
    encode_rle, make_image_object, make_blocks, make_command, pack_pixels,
    is_psj420_advertisement,
)


@pytest.mark.parametrize("tail", [0x1E, 0x1B, 0x00, 0xFF])
def test_advertisement_variable_tail(tail):
    assert is_psj420_advertisement(bytes.fromhex("fd024002009964060102ffff") + bytes([tail]))


@pytest.mark.parametrize("data", [
    None, b"", bytes.fromhex("fd024002009964060102ffff"),
    bytes.fromhex("fd024002009964060102ffff1b00"),
    bytes.fromhex("fd024003009964060102ffff1b"),
])
def test_advertisement_rejects_other_signatures(data):
    assert not is_psj420_advertisement(data)


def test_rle_boundaries():
    assert encode_rle(b"") == b""
    assert encode_rle(b"\x55" * 256 + b"\xaa" * 2) == bytes.fromhex("ff55015502aa")
    raw = bytes(range(256)) * 120
    encoded = encode_rle(raw)
    assert b"".join(bytes([v]) * n for n, v in zip(encoded[::2], encoded[1::2])) == raw


def test_palette_and_bit_order():
    image = Image.new("RGB", (400, 300), "white")
    for x, color in enumerate(("black", "white", "yellow", "red")):
        image.putpixel((x, 0), Image.new("RGB", (1, 1), color).getpixel((0, 0)))
    assert pack_pixels(image) == b"\x1b" + b"\x55" * 29999
    with pytest.raises(ValueError, match="400x300"):
        pack_pixels(Image.new("RGB", (300, 400)))


def test_image_header_and_half_frame_run_boundary():
    obj = make_image_object(b"\xaa" * 30000)
    # Each independently encoded 15000-byte half is 58*255 + 210 bytes.
    encoded_half = bytes.fromhex("ffaa") * 58 + bytes.fromhex("d2aa")
    assert obj[38:] == encoded_half * 2
    assert obj[:4] == b"XTEK"
    assert int.from_bytes(obj[4:8], "big") == sum(obj[12:])
    assert int.from_bytes(obj[8:12], "big") == len(obj)
    assert obj[12:25] == bytes.fromhex("01000000110000000000000000")
    assert obj[25:34] == bytes.fromhex("000001900000012c01")
    assert int.from_bytes(obj[34:38], "big") == 236
    with pytest.raises(ValueError):
        make_image_object(b"\x00")


def test_control_commands_from_capture():
    assert make_command(b"\x01" + (10244).to_bytes(4, "big")) == bytes.fromhex("585445010b2d0100002804")
    assert make_command(b"\x04\x00") == bytes.fromhex("5854450108040400")


def test_blocks_and_worst_case_size():
    obj = bytes(range(256)) * 40 + b"test"
    blocks = make_blocks(obj)
    assert len(blocks) == 9
    assert [len(b) for b in blocks] == [1220] * 8 + [565]
    assert b"".join(b[9:] for b in blocks) == obj
    for i, block in enumerate(blocks):
        assert block[:4] == b"XTE\x02"
        assert int.from_bytes(block[4:6], "big") == len(block)
        assert block[6] == sum(block[7:]) & 255
        assert block[7:9] == bytes((9, i))
    raw = (bytes(range(256)) * 118)[:30000]
    assert len(make_image_object(raw)) == 60038
    assert len(make_blocks(make_image_object(raw))) == 50


class FakeClient:
    def __init__(self, reply="ok", mtu_payload=244, fail_write=False):
        self.write_char = SimpleNamespace(properties=["write-without-response"], max_write_without_response_size=mtu_payload)
        self.notify_char = SimpleNamespace(properties=["notify"])
        self.service = SimpleNamespace(get_characteristic=lambda uuid: {
            WRITE_UUID: self.write_char, NOTIFY_UUID: self.notify_char
        }.get(uuid))
        self.services = SimpleNamespace(get_service=lambda uuid: self.service if uuid == SERVICE_UUID else None)
        self.reply = reply
        self.fail_write = fail_write
        self.writes = []
        self.stopped = False

    async def start_notify(self, characteristic, callback):
        assert characteristic is self.notify_char
        self.callback = callback

    async def stop_notify(self, characteristic):
        assert characteristic is self.notify_char
        self.stopped = True

    async def write_gatt_char(self, characteristic, data, response):
        assert characteristic is self.write_char and response is False
        assert len(data) <= 244
        self.writes.append(data)
        if self.fail_write:
            raise OSError("adapter write failed")
        if not data.startswith(b"XTE\x01") or self.reply == "timeout":
            return
        if data[6] == 1:
            reply = bytearray.fromhex("5854450409bd01ffbd00000000000000")
        else:
            reply = bytearray.fromhex("58544504080304ff0000000000000000")
        if self.reply == "checksum":
            reply[5] ^= 1
        elif self.reply == "status":
            reply[7] = 0
            reply[5] = sum(reply[6:reply[4]]) & 255
        elif self.reply == "length":
            reply[4] = 17
        self.callback(None, reply)


def test_transport_sequence():
    client = FakeClient()
    image = Image.new("RGB", (400, 300), "white")
    assert asyncio.run(XteClient(client).write_image(image))
    obj = make_image_object(b"\x55" * 30000)
    expected = [make_command(b"\x01" + len(obj).to_bytes(4, "big"))]
    for block in make_blocks(obj):
        expected.extend(block[i:i + 244] for i in range(0, len(block), 244))
    expected.append(make_command(b"\x04\x00"))
    assert client.writes == expected
    assert client.stopped


@pytest.mark.parametrize("reply,error", [
    ("checksum", ValueError), ("status", ValueError),
    ("length", ValueError), ("timeout", TimeoutError),
])
def test_bad_responses_fail_and_unsubscribe(reply, error):
    client = FakeClient(reply=reply)
    transport = XteClient(client)
    transport.timeout = 0.01
    with pytest.raises(error):
        asyncio.run(transport.write_image(Image.new("RGB", (400, 300))))
    assert client.stopped
    assert len(client.writes) == 1  # No data sent after a failed preparation.


def test_small_mtu_and_missing_service():
    client = FakeClient(mtu_payload=20)
    with pytest.raises(ValueError, match="MTU"):
        asyncio.run(XteClient(client).write_image(Image.new("RGB", (400, 300))))
    assert client.writes == []
    client.services.get_service = lambda uuid: None
    with pytest.raises(ValueError, match="service missing"):
        asyncio.run(XteClient(client).write_image(Image.new("RGB", (400, 300))))


def test_write_failure_unsubscribes():
    client = FakeClient(fail_write=True)
    with pytest.raises(OSError):
        asyncio.run(XteClient(client).write_image(Image.new("RGB", (400, 300))))
    assert client.stopped


def test_discovery_and_legacy_profile(monkeypatch):
    """Load the actual parser with a minimal sensor-state base, not MagicMock."""
    class BluetoothData:
        def __init__(self):
            self.metadata = {}
            self.sensors = []

        def __getattr__(self, name):
            if name.startswith("set_"):
                return lambda value: self.metadata.update({name: value})
            if name.startswith("update_predefined"):
                return lambda *args: self.sensors.append(args)
            raise AttributeError(name)

        def supported(self, info):
            self._start_update(info)
            return "set_device_type" in self.metadata

    monkeypatch.setitem(sys.modules, "bluetooth_sensor_state_data", SimpleNamespace(BluetoothData=BluetoothData))
    path = Path(__file__).parents[1] / "custom_components/gicisky/gicisky_ble/parser.py"
    spec = importlib.util.spec_from_file_location("custom_components.gicisky.gicisky_ble._test_parser", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    info = SimpleNamespace(address="AA:BB:CC:DD:EE:FF", service_uuids=[],
                           manufacturer_data={0x5258: bytes.fromhex("fd024002009964060102ffff1e")})
    device = module.GiciskyBluetoothDeviceData()
    assert device.supported(info)
    assert device.device.protocol == "xte"
    assert device.metadata["set_device_manufacturer"] == "Poshiji"
    assert device.sensors == []
    assert device.last_service_info is info
    # A new parser after restart/reload must recognize the changed tail too.
    info.manufacturer_data = {0x5258: bytes.fromhex("fd024002009964060102ffff1b")}
    restarted = module.GiciskyBluetoothDeviceData()
    assert restarted.supported(info)
    assert restarted.device.protocol == "xte"
    assert restarted.device.width == 400 and restarted.device.height == 300
    assert device.supported(info)  # Also works on the existing instance.
    info.manufacturer_data = {0x5053: bytes.fromhex("fd024002009964060102ffff1b")}
    assert not module.GiciskyBluetoothDeviceData().supported(info)
    info.manufacturer_data = {0x5258: b"\x00" * 13}
    assert not module.GiciskyBluetoothDeviceData().supported(info)
    info.manufacturer_data = {0x5053: bytes.fromhex("4b1e810140")}
    info.service_uuids = ["0000fff0-0000-1000-8000-00805f9b34fb"]
    legacy = module.GiciskyBluetoothDeviceData()
    assert legacy.supported(info)
    assert legacy.device.protocol == "gicisky"
    assert legacy.metadata["set_device_manufacturer"] == "Gicisky"
    assert len(legacy.sensors) == 3


def test_writer_routes_xte_and_disconnects(monkeypatch):
    from custom_components.gicisky.gicisky_ble import writer
    from custom_components.gicisky.gicisky_ble.devices import PSJ_420

    client = SimpleNamespace(is_connected=True, disconnect=AsyncMock())
    monkeypatch.setattr(writer, "establish_connection", AsyncMock(return_value=client))
    transport = SimpleNamespace(write_image=AsyncMock(return_value=True))
    calls = []

    def create_transport(*args):
        calls.append(args)
        return transport

    monkeypatch.setattr(writer, "XteClient", create_transport)
    device = SimpleNamespace(address="AA:BB:CC:DD:EE:FF")
    image = Image.new("RGB", (400, 300))
    assert asyncio.run(writer.update_image(device, PSJ_420, image, attempt=2, write_delay_ms=30))
    assert calls == [(client, 2, 30)]
    transport.write_image.assert_awaited_once_with(image)
    client.disconnect.assert_awaited_once()
    client.disconnect.reset_mock()
    transport.write_image.side_effect = ValueError("invalid response")
    assert not asyncio.run(writer.update_image(device, PSJ_420, image))
    client.disconnect.assert_awaited_once()
