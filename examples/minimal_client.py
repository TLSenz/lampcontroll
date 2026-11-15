#!/usr/bin/env python3
"""A minimal, readable Meross lamp client.

This is deliberately small: one HTTP POST helper, three commands, no
dependencies.  It is the same protocol the GUI apps use.

Examples:
  python3 examples/minimal_client.py status
  python3 examples/minimal_client.py on
  python3 examples/minimal_client.py off
  python3 examples/minimal_client.py toggle
  python3 examples/minimal_client.py color 00FF00
  python3 examples/minimal_client.py brightness 40

In the lamp's setup AP mode the key is "meross":
  python3 examples/minimal_client.py --host 10.10.10.1 --key meross status
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
import uuid
from typing import Any, Dict
from urllib.request import Request, urlopen

DEFAULT_HOST = "192.168.1.111"
DEFAULT_KEY = ""  # after onboarding; use "meross" in setup AP mode


def call(
    host: str,
    port: int,
    key: str,
    namespace: str,
    method: str,
    payload: Dict[str, Any],
    timeout: float = 5.0,
) -> Dict[str, Any]:
    """Send one signed Meross packet to POST /config and return the JSON reply."""
    message_id = uuid.uuid4().hex
    timestamp = int(time.time())
    sign = hashlib.md5(
        (message_id + key + str(timestamp)).encode("utf-8")
    ).hexdigest()

    packet = {
        "header": {
            "messageId": message_id,
            "namespace": namespace,
            "method": method,
            "payloadVersion": 1,
            "from": "MinimalLampClient",
            "timestamp": timestamp,
            "timestampMs": 0,
            "sign": sign,
        },
        "payload": payload,
    }

    request = Request(
        "http://%s:%d/config" % (host, port),
        data=json.dumps(packet).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=UTF-8"},
        method="POST",
    )
    with urlopen(request, timeout=timeout) as response:
        document = json.loads(response.read())

    header = document.get("header") or {}
    if header.get("method") == "ERROR":
        error = ((document.get("payload") or {}).get("error") or {})
        raise RuntimeError(error.get("detail", "lamp returned an error"))
    return document


def read_state(host: str, port: int, key: str) -> Dict[str, Any]:
    document = call(host, port, key, "Appliance.System.All", "GET", {"all": {}})
    all_data = document["payload"]["all"]
    system = all_data["system"]
    digest = all_data["digest"]
    light = digest.get("light") or {}
    toggles = digest.get("togglex") or []
    onoff = toggles[0].get("onoff", 0) if toggles else light.get("onoff", 0)
    return {
        "model": system["hardware"]["type"],
        "firmware": system["firmware"]["version"],
        "on": onoff == 1,
        "rgb": light.get("rgb", 0),
        "luminance": light.get("luminance", 100),
    }


def print_state(host: str, port: int, key: str) -> None:
    state = read_state(host, port, key)
    print("Lamp %s" % host)
    print("  model:     %s (fw %s)" % (state["model"], state["firmware"]))
    print("  power:     %s" % ("on" if state["on"] else "off"))
    print("  colour:    #%06x" % state["rgb"])
    print("  luminance: %s" % state["luminance"])


def set_power(host: str, port: int, key: str, on: bool) -> None:
    call(
        host,
        port,
        key,
        "Appliance.Control.ToggleX",
        "SET",
        {"togglex": {"channel": 0, "onoff": 1 if on else 0}},
    )
    time.sleep(0.5)
    print_state(host, port, key)


def set_colour(host: str, port: int, key: str, rgb: int) -> None:
    state = read_state(host, port, key)
    if not state["on"]:
        call(
            host,
            port,
            key,
            "Appliance.Control.ToggleX",
            "SET",
            {"togglex": {"channel": 0, "onoff": 1}},
        )
        time.sleep(0.4)
    call(
        host,
        port,
        key,
        "Appliance.Control.Light",
        "SET",
        {
            "light": {
                "channel": 0,
                "rgb": rgb & 0xFFFFFF,
                "luminance": state["luminance"],
                "capacity": 7,
            }
        },
    )
    time.sleep(0.5)
    print_state(host, port, key)


def set_brightness(host: str, port: int, key: str, luminance: int) -> None:
    state = read_state(host, port, key)
    call(
        host,
        port,
        key,
        "Appliance.Control.Light",
        "SET",
        {
            "light": {
                "channel": 0,
                "rgb": state["rgb"] & 0xFFFFFF,
                "luminance": max(0, min(100, luminance)),
                "capacity": 7,
            }
        },
    )
    time.sleep(0.5)
    print_state(host, port, key)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=80)
    parser.add_argument("--key", default=DEFAULT_KEY)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status")
    sub.add_parser("on")
    sub.add_parser("off")
    sub.add_parser("toggle")
    colour = sub.add_parser("color")
    colour.add_argument("rgb", help="RRGGBB")
    brightness = sub.add_parser("brightness")
    brightness.add_argument("value", type=int)
    args = parser.parse_args()

    if args.command == "status":
        print_state(args.host, args.port, args.key)
    elif args.command == "on":
        set_power(args.host, args.port, args.key, True)
    elif args.command == "off":
        set_power(args.host, args.port, args.key, False)
    elif args.command == "toggle":
        set_power(args.host, args.port, args.key, not read_state(args.host, args.port, args.key)["on"])
    elif args.command == "color":
        set_colour(args.host, args.port, args.key, int(args.rgb, 16))
    elif args.command == "brightness":
        set_brightness(args.host, args.port, args.key, args.value)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
