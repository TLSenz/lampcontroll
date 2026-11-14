#!/usr/bin/env python3
"""Find and control the Meross lamp on the normal home LAN.

Once the lamp has been onboarded to the home Wi-Fi it gets a 192.168.x.x
address.  This tool scans the local /24 for port 80, speaks the Meross local
protocol, matches the known UUID/MAC, and optionally runs the on/off + colour
control test over the LAN.

No cloud, no Meross account, no Wi-Fi switching.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import ipaddress
import json
import os
import socket
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lamp_recon as lr  # noqa: E402

DEFAULT_UUID = os.environ.get("LAMP_UUID", "")
DEFAULT_MAC = os.environ.get("LAMP_MAC", "")
DEFAULT_SSID = os.environ.get("HOME_SSID", "")


def local_subnet() -> str:
    ip = lr.local_ip_for("192.168.1.1") or "192.168.1.50"
    return ".".join(ip.split(".")[:3]) + ".0/24"


def probe_host(host: str, ports: List[int]) -> Optional[Tuple[str, int]]:
    for port in ports:
        if lr.tcp_probe(host, port, timeout=0.5):
            return host, port
    return None


def find_lamp(
    subnet: str,
    uuid: str,
    mac: str,
    host: Optional[str] = None,
    port: int = 80,
) -> Optional[Dict[str, Any]]:
    if host:
        candidates = [(host, port)]
    else:
        hosts = [str(ip) for ip in ipaddress.ip_network(subnet).hosts()]
        candidates = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=128) as pool:
            for result in pool.map(
                lambda h: probe_host(h, [80, 443]), hosts
            ):
                if result:
                    candidates.append(result)

    for candidate_host, candidate_port in candidates:
        use_tls = candidate_port == 443
        key, attempts, res = lr.meross_handshake(
            candidate_host, candidate_port, use_tls
        )
        if key is None:
            continue
        summary = lr.summarize_system_all(res)
        summary_uuid = (summary.get("uuid") or "").lower()
        summary_mac = (summary.get("mac") or "").lower()
        if uuid and summary_uuid and summary_uuid != uuid.lower():
            continue
        if mac and summary_mac and summary_mac != mac.lower():
            continue
        return {
            "host": candidate_host,
            "port": candidate_port,
            "tls": use_tls,
            "key": key,
            "summary": summary,
            "system_all": res.get("json"),
            "attempts": attempts,
        }
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--subnet", default=None, help="LAN subnet, e.g. 192.168.1.0/24")
    parser.add_argument("--host", help="probe one host instead of scanning")
    parser.add_argument("--port", type=int, default=80)
    parser.add_argument("--uuid", default=DEFAULT_UUID)
    parser.add_argument("--mac", default=DEFAULT_MAC)
    parser.add_argument("--control", action="store_true", help="run on/off + colour test")
    parser.add_argument("--color", default="ffffff", help="RGB colour to test")
    parser.add_argument("--keep", action="store_true", help="do not restore the lamp state")
    args = parser.parse_args()

    subnet = args.subnet or local_subnet()
    print("LampControll LAN discovery")
    print("  subnet: %s" % subnet)
    print("  target UUID: %s" % args.uuid)
    print("  target MAC:  %s" % args.mac)
    print()

    started = datetime.now().isoformat(timespec="seconds")
    found = find_lamp(subnet, args.uuid, args.mac, host=args.host, port=args.port)
    report: Dict[str, Any] = {
        "generated_at": started,
        "subnet": subnet,
        "target_uuid": args.uuid,
        "target_mac": args.mac,
        "found": found,
        "control": None,
    }

    if not found:
        print("Lamp not found on %s." % subnet)
        print("Is it powered, and did it join the home Wi-Fi?")
        report_dir = lr.REPORT_DIR
        report_dir.mkdir(parents=True, exist_ok=True)
        path = report_dir / "lan_report.json"
        path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print("Report: %s" % path)
        return 1

    summary = found["summary"]
    print("Found lamp:")
    print("  IP:       %s:%d%s" % (found["host"], found["port"], " (TLS)" if found["tls"] else ""))
    print("  model:    %s" % summary.get("model"))
    print("  uuid:     %s" % summary.get("uuid"))
    print("  mac:      %s" % summary.get("mac"))
    print("  firmware: %s" % summary.get("firmware"))
    print("  key:      %r" % found["key"])
    print("  light:    %s" % json.dumps(summary.get("light")))
    print("  togglex:  %s" % json.dumps(summary.get("togglex")))

    if args.control:
        print()
        print("Control test over LAN ...")
        control = lr.control_test(
            found["host"],
            found["port"],
            found["key"],
            found["tls"],
            summary,
            args.color,
            restore=not args.keep,
        )
        report["control"] = control
        print("  before onoff: %s" % control.get("before_onoff"))
        print("  target onoff: %s" % control.get("target_onoff"))
        print("  after onoff:  %s" % control.get("after_onoff"))
        print("  verified:     %s" % control.get("verified"))
        print("  color verified: %s" % control.get("color_verified"))
        print("  restore verified: %s" % control.get("restore_verified"))
        if control.get("error"):
            print("  error: %s" % control["error"])

    report_dir = lr.REPORT_DIR
    report_dir.mkdir(parents=True, exist_ok=True)
    json_path = report_dir / "lan_report.json"
    text_path = report_dir / "lan_report.txt"
    json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    lines = [
        "LampControll LAN report",
        "Generated: %s" % started,
        "Subnet: %s" % subnet,
        "IP: %s" % found["host"],
        "Model: %s" % summary.get("model"),
        "UUID: %s" % summary.get("uuid"),
        "MAC: %s" % summary.get("mac"),
        "Firmware: %s" % summary.get("firmware"),
        "Key: %r" % found["key"],
        "Light: %s" % json.dumps(summary.get("light")),
        "Togglex: %s" % json.dumps(summary.get("togglex")),
    ]
    control = report.get("control") or {}
    if control:
        lines.extend(
            [
                "",
                "Control test:",
                "  before onoff: %s" % control.get("before_onoff"),
                "  target onoff: %s" % control.get("target_onoff"),
                "  after onoff: %s" % control.get("after_onoff"),
                "  verified: %s" % control.get("verified"),
                "  color verified: %s" % control.get("color_verified"),
                "  restore verified: %s" % control.get("restore_verified"),
            ]
        )
    text_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print()
    print("Report: %s" % text_path)
    if control.get("verified") and control.get("color_verified"):
        print("SUCCESS: lamp controlled over the home LAN.")
        return 0
    if control.get("verified"):
        print("SUCCESS: on/off controlled over the home LAN (colour not confirmed).")
        return 0
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
