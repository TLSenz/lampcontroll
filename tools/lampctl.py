#!/usr/bin/env python3
"""Permanent local CLI for the Meross MSL120DR lamp.

Examples:
  python3 tools/lampctl.py status
  python3 tools/lampctl.py on
  python3 tools/lampctl.py off
  python3 tools/lampctl.py toggle
  python3 tools/lampctl.py color FF8800
  python3 tools/lampctl.py white
  python3 tools/lampctl.py brightness 40
  python3 tools/lampctl.py discover

The lamp's address/key are cached in lamp_config.json after the first
discovery.  No cloud, no Meross account, no Wi-Fi switching.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lamp_recon as lr  # noqa: E402
import lamp_lan as lan  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "lamp_config.json"

DEFAULT_UUID = lan.DEFAULT_UUID
DEFAULT_MAC = lan.DEFAULT_MAC


def load_config() -> Optional[Dict[str, Any]]:
    if not CONFIG_PATH.exists():
        return None
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return None


def save_config(config: Dict[str, Any]) -> None:
    CONFIG_PATH.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")


def discover() -> Dict[str, Any]:
    print("Discovering lamp on the home LAN ...")
    found = lan.find_lamp("192.168.1.0/24", DEFAULT_UUID, DEFAULT_MAC)
    if not found:
        raise SystemExit("Lamp not found on the LAN.")
    summary = found["summary"]
    config = {
        "host": found["host"],
        "port": found["port"],
        "tls": found["tls"],
        "key": found["key"],
        "uuid": summary.get("uuid"),
        "mac": summary.get("mac"),
        "model": summary.get("model"),
        "firmware": summary.get("firmware"),
    }
    save_config(config)
    print("Saved %s" % CONFIG_PATH)
    return config


def resolve(args: argparse.Namespace) -> Dict[str, Any]:
    config = load_config() or {}
    if args.host:
        config["host"] = args.host
        config.setdefault("port", args.port or 80)
        config.setdefault("tls", False)
        config.setdefault("key", "")
    if not config.get("host"):
        config = discover()
    elif not args.host and not lr.tcp_probe(
        config["host"], int(config.get("port", 80)), timeout=0.6
    ):
        print(
            "Cached lamp address %s is not reachable; rediscovering ..."
            % config["host"]
        )
        config = discover()
    if args.key is not None:
        config["key"] = args.key
    config.setdefault("port", 80)
    config.setdefault("tls", False)
    config.setdefault("key", "")
    return config


def state(config: Dict[str, Any]) -> Dict[str, Any]:
    res = lr.meross_call(
        config["host"],
        config["port"],
        "Appliance.System.All",
        "GET",
        {"all": {}},
        config["key"],
        use_tls=config["tls"],
    )
    if lr.meross_method(res) not in ("GETACK", "SETACK", "PUSH"):
        raise SystemExit("Lamp did not answer: %s" % res.get("error") or res.get("body"))
    return lr.summarize_system_all(res)


def ability_capacity(config: Dict[str, Any], default: int = 7) -> int:
    res = lr.meross_call(
        config["host"],
        config["port"],
        "Appliance.System.Ability",
        "GET",
        {},
        config["key"],
        use_tls=config["tls"],
    )
    doc = res.get("json") or {}
    ability = ((doc.get("payload") or {}).get("ability") or {})
    light = ability.get("Appliance.Control.Light") or {}
    return int(light.get("capacity", default))


def print_state(summary: Dict[str, Any]) -> None:
    light = summary.get("light") or {}
    togglex = summary.get("togglex") or []
    onoff = (
        togglex[0].get("onoff")
        if togglex
        else light.get("onoff", "?")
    )
    rgb = light.get("rgb")
    color = "#%06x" % rgb if isinstance(rgb, int) else "?"
    print("  model:      %s (fw %s)" % (summary.get("model"), summary.get("firmware")))
    print("  power:      %s" % ("on" if onoff == 1 else "off" if onoff == 0 else onoff))
    print("  color:      %s (rgb %s)" % (color, rgb))
    print("  luminance:  %s" % light.get("luminance"))
    print("  temperature:%s" % light.get("temperature"))


def set_power(config: Dict[str, Any], target: int) -> bool:
    res = lr.set_togglex(
        config["host"], config["port"], config["key"], config["tls"], target
    )
    method = lr.meross_method(res)
    if method != "SETACK":
        print("SET failed: %s" % method)
        return False
    time.sleep(0.7)
    summary = state(config)
    togglex = summary.get("togglex") or []
    actual = togglex[0].get("onoff") if togglex else None
    ok = actual == target
    print(
        "power %s -> %s (%s)"
        % ("on" if target else "off", "verified" if ok else "MISMATCH", actual)
    )
    return ok


def apply_light(config: Dict[str, Any], values: Dict[str, Any]) -> bool:
    result = lr.set_light(
        config["host"], config["port"], config["key"], config["tls"], values
    )
    return lr.meross_method(result) == "SETACK"


def set_color(config: Dict[str, Any], rgb: int) -> bool:
    summary = state(config)
    light = summary.get("light") or {}
    togglex = summary.get("togglex") or []
    onoff = togglex[0].get("onoff") if togglex else light.get("onoff", 0)
    if onoff != 1:
        set_power(config, 1)
        time.sleep(0.4)
    capacity = ability_capacity(config)
    values = {
        "channel": 0,
        "rgb": rgb,
        "luminance": int(light.get("luminance", 100)),
        "capacity": capacity,
    }
    if not apply_light(config, values):
        print("Color SET failed.")
        return False
    time.sleep(0.8)
    after = state(config)
    actual = (after.get("light") or {}).get("rgb")
    ok = actual == rgb
    print(
        "color #%06x -> %s (reported #%06x)"
        % (rgb, "verified" if ok else "MISMATCH", actual if isinstance(actual, int) else 0)
    )
    return ok


def set_brightness(config: Dict[str, Any], luminance: int) -> bool:
    summary = state(config)
    light = summary.get("light") or {}
    capacity = ability_capacity(config)
    values = {
        "channel": 0,
        "rgb": int(light.get("rgb", 0xFFFFFF)),
        "luminance": max(0, min(100, luminance)),
        "capacity": capacity,
    }
    if not apply_light(config, values):
        print("Brightness SET failed.")
        return False
    time.sleep(0.8)
    after = state(config)
    actual = (after.get("light") or {}).get("luminance")
    ok = actual == values["luminance"]
    print(
        "brightness %s -> %s (reported %s)"
        % (values["luminance"], "verified" if ok else "MISMATCH", actual)
    )
    return ok


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", help="lamp IP (default: cached or discover)")
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--key", default=None, help="shared key (default: cached)")
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status")
    sub.add_parser("on")
    sub.add_parser("off")
    sub.add_parser("toggle")
    sub.add_parser("white")
    sub.add_parser("discover")
    color = sub.add_parser("color")
    color.add_argument("rgb", help="RRGGBB or #RRGGBB")
    brightness = sub.add_parser("brightness")
    brightness.add_argument("value", type=int, help="0-100")
    args = parser.parse_args()

    if args.command == "discover":
        config = discover()
        summary = state(config)
        print_state(summary)
        return 0

    config = resolve(args)
    if args.verbose:
        print("using %s:%s key=%r" % (config["host"], config["port"], config["key"]))

    if args.command == "status":
        summary = state(config)
        print("Lamp %s:%s" % (config["host"], config["port"]))
        print_state(summary)
        return 0

    if args.command == "on":
        return 0 if set_power(config, 1) else 1
    if args.command == "off":
        return 0 if set_power(config, 0) else 1
    if args.command == "toggle":
        summary = state(config)
        togglex = summary.get("togglex") or []
        current = togglex[0].get("onoff") if togglex else 0
        return 0 if set_power(config, 0 if current else 1) else 1
    if args.command == "color":
        try:
            rgb = int(args.rgb.lstrip("#"), 16)
        except ValueError:
            raise SystemExit("Invalid RGB value: %s" % args.rgb)
        return 0 if set_color(config, rgb) else 1
    if args.command == "white":
        return 0 if set_color(config, 0xFFFFFF) else 1
    if args.command == "brightness":
        return 0 if set_brightness(config, args.value) else 1
    return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
