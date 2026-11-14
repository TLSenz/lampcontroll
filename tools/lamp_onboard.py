#!/usr/bin/env python3
"""Onboard the Meross lamp onto the home Wi-Fi from its own AP.

Run while the Mac is connected to the lamp AP.  The tool:
  1. speaks the Meross local protocol to 10.10.10.1,
  2. asks the lamp for its Wi-Fi scan (Appliance.Config.WifiList),
  3. selects the target SSID on a 2.4 GHz channel,
  4. sends Appliance.Config.Wifi with base64 SSID/password and the
     bssid/channel/encryption/cipher reported by the lamp.

The password is read from a file and is never printed or written to the
report.  The lamp reboots and joins the home network; after that,
tools/lamp_lan.py can find and control it over the LAN.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lamp_recon as lr  # noqa: E402

DEFAULT_SSID = os.environ.get("HOME_SSID", "")


def choose_target(
    entries: List[Dict[str, Any]], ssid: str
) -> Dict[str, Any] | None:
    matches = [
        entry
        for entry in entries
        if ssid
        in (
            entry.get("ssid"),
            entry.get("ssid_raw"),
            entry.get("ssid_decoded"),
        )
    ]
    if not matches:
        return None
    pool = [
        entry
        for entry in matches
        if isinstance(entry.get("channel"), int)
        and 1 <= entry["channel"] <= 13
    ] or matches
    return max(pool, key=lambda entry: entry.get("signal") or 0)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="10.10.10.1")
    parser.add_argument("--port", type=int, default=80)
    parser.add_argument("--tls", action="store_true")
    parser.add_argument("--ssid", default=DEFAULT_SSID)
    parser.add_argument("--password-file", required=True)
    parser.add_argument("--uuid", default="")
    parser.add_argument("--mac", default="")
    parser.add_argument(
        "--bssid",
        default="aa:bb:cc:dd:ee:ff",
        help="fallback BSSID if the lamp's Wi-Fi scan is empty",
    )
    parser.add_argument("--channel", type=int, default=9)
    parser.add_argument("--encryption", type=int, default=6)
    parser.add_argument("--cipher", type=int, default=3)
    parser.add_argument("--scan-retries", type=int, default=6)
    parser.add_argument("--scan-delay", type=float, default=3.0)
    args = parser.parse_args()

    if not args.ssid:
        print("--ssid is required (or set HOME_SSID in lamp_env.sh).")
        return 1

    password_path = Path(args.password_file)
    if not password_path.exists():
        print("Password file not found: %s" % password_path)
        return 1
    password = password_path.read_text(encoding="utf-8").rstrip("\r\n")
    if not password:
        print("Password file is empty.")
        return 1

    started = datetime.now().isoformat(timespec="seconds")
    print("LampControll onboarding")
    print("  lamp: %s:%d" % (args.host, args.port))
    print("  target SSID: %s" % args.ssid)

    key, attempts, res = lr.meross_handshake(args.host, args.port, args.tls)
    if key is None:
        print("Could not complete the Meross handshake.")
        return 1
    summary = lr.summarize_system_all(res)
    print("  model: %s" % summary.get("model"))
    print("  uuid:  %s" % summary.get("uuid"))
    print("  mac:   %s" % summary.get("mac"))
    if args.uuid and (summary.get("uuid") or "").lower() != args.uuid.lower():
        print("UUID mismatch; refusing to configure.")
        return 2
    if args.mac and (summary.get("mac") or "").lower() != args.mac.lower():
        print("MAC mismatch; refusing to configure.")
        return 2

    entries: List[Dict[str, Any]] = []
    scan_attempts = 0
    for scan_attempts in range(1, args.scan_retries + 1):
        wifi_res = lr.meross_call(
            args.host,
            args.port,
            "Appliance.Config.WifiList",
            "GET",
            {},
            key,
            use_tls=args.tls,
        )
        entries = lr.summarize_wifi_list(wifi_res)
        print(
            "  Wi-Fi scan attempt %d/%d: %d network(s)"
            % (scan_attempts, args.scan_retries, len(entries))
        )
        if entries:
            break
        if scan_attempts < args.scan_retries:
            time.sleep(args.scan_delay)

    target = choose_target(entries, args.ssid)
    used_fallback = False
    if not target:
        if args.bssid and args.channel:
            print(
                "  scan empty or target missing; using known AP fallback "
                "%s ch=%d" % (args.bssid, args.channel)
            )
            target = {
                "ssid": args.ssid,
                "ssid_raw": args.ssid,
                "bssid": args.bssid,
                "channel": args.channel,
                "encryption": args.encryption,
                "cipher": args.cipher,
                "signal": None,
            }
            used_fallback = True
        else:
            print("Target SSID %r not visible to the lamp." % args.ssid)
            print("Visible networks:")
            for entry in entries:
                print(
                    "  %-28s ch=%s enc=%s cipher=%s signal=%s"
                    % (
                        entry.get("ssid"),
                        entry.get("channel"),
                        entry.get("encryption"),
                        entry.get("cipher"),
                        entry.get("signal"),
                    )
                )
            return 1

    print("  selected AP:")
    for field in ("ssid", "bssid", "channel", "encryption", "cipher", "signal"):
        print("    %-10s %s" % (field + ":", target.get(field)))

    wifi_payload: Dict[str, Any] = {
        "ssid": base64.b64encode(args.ssid.encode("utf-8")).decode("ascii"),
        "password": base64.b64encode(password.encode("utf-8")).decode("ascii"),
    }
    for field in ("bssid", "channel", "encryption", "cipher"):
        if target.get(field) is not None:
            wifi_payload[field] = target[field]

    set_res = lr.meross_call(
        args.host,
        args.port,
        "Appliance.Config.Wifi",
        "SET",
        {"wifi": wifi_payload},
        key,
        use_tls=args.tls,
    )
    method = lr.meross_method(set_res)
    print("  Appliance.Config.Wifi -> %s (HTTP %s)" % (method, set_res.get("status")))

    # Give the device a moment to acknowledge/reboot, then see if the AP
    # endpoint disappears (expected when it switches to the home network).
    time.sleep(4)
    still_up = lr.tcp_probe(args.host, args.port, timeout=1.0)
    print("  lamp AP endpoint %s" % ("still up" if still_up else "gone (rebooting)"))

    report: Dict[str, Any] = {
        "generated_at": started,
        "lamp": {
            "host": args.host,
            "port": args.port,
            "model": summary.get("model"),
            "uuid": summary.get("uuid"),
            "mac": summary.get("mac"),
            "firmware": summary.get("firmware"),
        },
        "target_ssid": args.ssid,
        "target_ap": {
            field: target.get(field)
            for field in ("ssid", "bssid", "channel", "encryption", "cipher", "signal")
        },
        "scan_attempts": scan_attempts,
        "used_fallback_ap": used_fallback,
        "set_method": method,
        "set_http_status": set_res.get("status"),
        "set_response": set_res.get("json"),
        "password_sent": True,
        "lamp_ap_still_up": still_up,
        "notes": [
            "The Wi-Fi password is intentionally not stored in this report.",
            "The lamp should now reboot and join the target SSID.",
        ],
    }

    report_dir = lr.REPORT_DIR
    report_dir.mkdir(parents=True, exist_ok=True)
    json_path = report_dir / "onboard_report.json"
    text_path = report_dir / "onboard_report.txt"
    json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    lines = [
        "LampControll onboarding report",
        "Generated: %s" % started,
        "Model: %s" % summary.get("model"),
        "UUID: %s" % summary.get("uuid"),
        "MAC: %s" % summary.get("mac"),
        "Target SSID: %s" % args.ssid,
        "Target AP: %s" % json.dumps(report["target_ap"]),
        "Scan attempts: %d (fallback: %s)" % (scan_attempts, used_fallback),
        "Appliance.Config.Wifi: %s (HTTP %s)" % (method, set_res.get("status")),
        "Lamp AP endpoint still up: %s" % still_up,
    ]
    text_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("  report: %s" % text_path)

    if method == "SETACK":
        print("Onboarding command accepted. The lamp should join %s." % args.ssid)
        return 0
    print("Onboarding command was not acknowledged.")
    return 2


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
