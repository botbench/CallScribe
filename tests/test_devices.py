"""Mic name classification heuristics."""

from callscribe.devices import classify_mic, mic_class_tip


def test_classify_airpods() -> None:
    assert classify_mic("XS AirPods Pro 3") == "airpods"
    assert classify_mic("AirPods") == "airpods"


def test_classify_bluetooth() -> None:
    assert classify_mic("Some Bluetooth Headset") == "bluetooth"
    assert classify_mic("WH-1000XM Hands-Free") == "bluetooth"


def test_classify_builtin() -> None:
    assert classify_mic("MacBook Pro Microphone") == "builtin"
    assert classify_mic("Built-in Microphone") == "builtin"


def test_classify_usb() -> None:
    assert classify_mic("Blue Yeti USB Microphone") == "usb"


def test_classify_unknown() -> None:
    assert classify_mic("Mystery Mic 3000") == "unknown"


def test_mic_class_tip_airpods() -> None:
    tip = mic_class_tip("airpods")
    assert tip is not None
    assert "HFP" in tip or "Bluetooth" in tip
