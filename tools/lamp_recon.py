#!/usr/bin/env python3
"""LampControll offline recon + control tool.

Run this while this Mac is connected to the lamp's own Wi-Fi access point
(e.g. a Meross "Meross_XXXXXX" open network).  It does not need internet.

What it does:
  1. Finds the default gateway (normally the lamp itself, e.g. 10.10.10.1).
  2. Fingerprints open TCP ports and HTTP services.
  3. Speaks the Meross local protocol (POST /config, signed JSON):
       Appliance.System.All, Appliance.System.Ability,
       Appliance.Control.Light, Appliance.Control.ToggleX
  4. Optionally toggles the lamp (and sets a colour) to prove control,
     then restores the original state.
  5. Writes reports/lamp_report.json and reports/lamp_report.txt.

Everything is stdlib-only so it works on a fresh macOS Python.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
import secrets
import socket
import ssl
import subprocess
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib import error, request

ROOT = Path(__file__).resolve().parent.parent
REPORT_DIR = ROOT / "reports"
DEFAULT_HTTP_PORTS = [80, 443, 8081, 8080, 5000]
DEFAULT_OTHER_PORTS = [6668, 8883, 1883]
COMMON_LAMP_HOSTS = ["10.10.10.1", "192.168.4.1", "10.0.0.1"]
MEROSS_KEYS = ["meross", "", "0"]


# --------------------------------------------------------------------------
# small helpers
# --------------------------------------------------------------------------

def log(message: str = "") -> None:
    print(message, flush=True)


def run_command(cmd: List[str], timeout: float = 4.0) -> str:
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout
        )
        return result.stdout
    except Exception:
        return ""


def default_gateway() -> Optional[str]:
    out = run_command(["route", "-n", "get", "default"])
    match = re.search(r"gateway:\s*([0-9.]+)", out)
    return match.group(1) if match else None


def local_ip_for(host: str) -> Optional[str]:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect((host, 80))
        return sock.getsockname()[0]
    except Exception:
        return None
    finally:
        sock.close()


def tcp_probe(host: str, port: int, timeout: float = 1.2) -> bool:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        return sock.connect_ex((host, port)) == 0
    except Exception:
        return False
    finally:
        sock.close()


def http_request(
    host: str,
    port: int,
    path: str = "/",
    method: str = "GET",
    body: Optional[bytes] = None,
    headers: Optional[Dict[str, str]] = None,
    timeout: float = 5.0,
    use_tls: bool = False,
) -> Dict[str, Any]:
    scheme = "https" if use_tls else "http"
    url = "%s://%s:%d%s" % (scheme, host, port, path)
    req = request.Request(url, data=body, method=method, headers=headers or {})
    context = ssl._create_unverified_context() if use_tls else None
    try:
        with request.urlopen(req, timeout=timeout, context=context) as resp:
            raw = resp.read(1024 * 1024)
            return {
                "url": url,
                "status": resp.status,
                "reason": resp.reason,
                "headers": dict(resp.headers),
                "body": raw.decode("utf-8", "replace"),
            }
    except error.HTTPError as exc:
        raw = exc.read(1024 * 1024)
        return {
            "url": url,
            "status": exc.code,
            "reason": exc.reason,
            "headers": dict(exc.headers),
            "body": raw.decode("utf-8", "replace"),
        }
    except Exception as exc:
        return {"url": url, "error": repr(exc)}


def decode_json(res: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    body = res.get("body")
    if not body:
        return None
    try:
        value = json.loads(body)
        return value if isinstance(value, dict) else None
    except Exception:
        return None


# --------------------------------------------------------------------------
# Meross local protocol
# --------------------------------------------------------------------------

def meross_packet(
    namespace: str,
    method: str,
    payload: Dict[str, Any],
    key: str,
    from_address: str = "Meross",
) -> Dict[str, Any]:
    message_id = secrets.token_hex(16)
    timestamp = int(time.time())
    sign = hashlib.md5(
        (message_id + key + str(timestamp)).encode("utf-8")
    ).hexdigest()
    return {
        "header": {
            "messageId": message_id,
            "namespace": namespace,
            "method": method,
            "payloadVersion": 1,
            "from": from_address,
            "timestamp": timestamp,
            "timestampMs": 0,
            "sign": sign,
        },
        "payload": payload,
    }


def meross_call(
    host: str,
    port: int,
    namespace: str,
    method: str,
    payload: Dict[str, Any],
    key: str,
    timeout: float = 5.0,
    use_tls: bool = False,
) -> Dict[str, Any]:
    packet = meross_packet(
        namespace, method, payload, key, from_address="%s/config" % host
    )
    res = http_request(
        host,
        port,
        "/config",
        method="POST",
        body=json.dumps(packet).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=UTF-8"},
        timeout=timeout,
        use_tls=use_tls,
    )
    res["request"] = packet
    res["json"] = decode_json(res)
    return res


def meross_method(res: Dict[str, Any]) -> Optional[str]:
    payload = res.get("json") or {}
    header = payload.get("header") or {}
    return header.get("method")


def meross_handshake(
    host: str, port: int, use_tls: bool
) -> Tuple[Optional[str], List[Dict[str, Any]], Dict[str, Any]]:
    """Try the known default keys and return the first accepted one."""
    attempts: List[Dict[str, Any]] = []
    last: Dict[str, Any] = {}
    for key in MEROSS_KEYS:
        res = meross_call(
            host,
            port,
            "Appliance.System.All",
            "GET",
            {"all": {}},
            key,
            use_tls=use_tls,
        )
        last = res
        method = meross_method(res)
        attempts.append(
            {
                "key": key,
                "http_status": res.get("status"),
                "error": res.get("error"),
                "method": method,
                "json": res.get("json"),
            }
        )
        payload = ((res.get("json") or {}).get("payload") or {})
        if method in ("GETACK", "SETACK", "PUSH") and payload.get("all"):
            return key, attempts, res
        # If we got a Meross ERROR it was a sign problem; try the next key.
        if method == "ERROR" or res.get("json"):
            continue
    return None, attempts, last


def summarize_system_all(res: Dict[str, Any]) -> Dict[str, Any]:
    doc = res.get("json") or {}
    payload = doc.get("payload") or {}
    all_data = payload.get("all") or {}
    system = all_data.get("system") or {}
    digest = all_data.get("digest") or {}
    hardware = system.get("hardware") or {}
    firmware = system.get("firmware") or {}
    online = system.get("online") or {}
    light = digest.get("light") or {}
    togglex = digest.get("togglex") or []
    return {
        "model": hardware.get("type"),
        "sub_type": hardware.get("subType"),
        "hardware_version": hardware.get("version"),
        "chip": hardware.get("chipType"),
        "uuid": hardware.get("uuid"),
        "mac": hardware.get("macAddress"),
        "firmware": firmware.get("version"),
        "firmware_compile_time": firmware.get("compileTime"),
        "inner_ip": firmware.get("innerIp"),
        "online": online.get("status"),
        "light": light,
        "togglex": togglex,
    }


def summarize_ability(res: Dict[str, Any]) -> Dict[str, Any]:
    doc = res.get("json") or {}
    payload = doc.get("payload") or {}
    ability = payload.get("ability") or {}
    return {
        "namespaces": sorted(ability.keys()),
        "light": ability.get("Appliance.Control.Light"),
        "effect": ability.get("Appliance.Control.Effect"),
        "togglex": ability.get("Appliance.Control.ToggleX"),
    }


def summarize_wifi_list(res: Dict[str, Any]) -> List[Dict[str, Any]]:
    doc = res.get("json") or {}
    payload = doc.get("payload") or {}
    items = payload.get("wifiList") or []
    result: List[Dict[str, Any]] = []
    for item in items:
        raw_ssid = item.get("ssid", "")
        decoded_ssid: Optional[str] = None
        try:
            candidate = base64.b64decode(raw_ssid, validate=True).decode("utf-8")
            if candidate and all(32 <= ord(ch) < 127 for ch in candidate):
                decoded_ssid = candidate
        except Exception:
            decoded_ssid = None
        ssid = decoded_ssid if decoded_ssid is not None else raw_ssid
        result.append(
            {
                "ssid": ssid,
                "ssid_raw": raw_ssid,
                "ssid_decoded": decoded_ssid,
                "bssid": item.get("bssid"),
                "signal": item.get("signal"),
                "channel": item.get("channel"),
                "encryption": item.get("encryption"),
                "cipher": item.get("cipher"),
            }
        )
    return result


def get_state(host: str, port: int, key: str, use_tls: bool) -> Dict[str, Any]:
    res = meross_call(
        host,
        port,
        "Appliance.System.All",
        "GET",
        {"all": {}},
        key,
        use_tls=use_tls,
    )
    return {"response": res, "summary": summarize_system_all(res)}


def set_light(
    host: str,
    port: int,
    key: str,
    use_tls: bool,
    values: Dict[str, Any],
) -> Dict[str, Any]:
    res = meross_call(
        host,
        port,
        "Appliance.Control.Light",
        "SET",
        {"light": values},
        key,
        use_tls=use_tls,
    )
    return res


def set_togglex(
    host: str,
    port: int,
    key: str,
    use_tls: bool,
    onoff: int,
) -> Dict[str, Any]:
    res = meross_call(
        host,
        port,
        "Appliance.Control.ToggleX",
        "SET",
        {"togglex": {"channel": 0, "onoff": onoff}},
        key,
        use_tls=use_tls,
    )
    return res


def control_test(
    host: str,
    port: int,
    key: str,
    use_tls: bool,
    summary: Dict[str, Any],
    color: Optional[str],
    restore: bool,
) -> Dict[str, Any]:
    """Toggle the lamp and verify the reported state actually changed."""
    result: Dict[str, Any] = {"steps": [], "verified": False}
    light = summary.get("light") or {}
    togglex = summary.get("togglex") or []

    # On Meross lamps the authoritative on/off state is ToggleX.  The
    # Appliance.Control.Light digest often has no onoff field at all.
    if togglex:
        before_on = int(togglex[0].get("onoff", 0))
    elif light:
        before_on = int(light.get("onoff", 0))
    else:
        result["error"] = "device reports neither light nor togglex digest"
        return result

    target_on = 1 - before_on
    result["before_onoff"] = before_on
    result["target_onoff"] = target_on

    if togglex:
        res = set_togglex(host, port, key, use_tls, target_on)
        result["steps"].append(
            {
                "action": "Appliance.Control.ToggleX SET onoff=%d" % target_on,
                "method": meross_method(res),
                "http_status": res.get("status"),
                "json": res.get("json"),
            }
        )
    else:
        values = dict(light)
        values["channel"] = int(values.get("channel", 0))
        values["onoff"] = target_on
        if "capacity" not in values:
            values["capacity"] = 6
        res = set_light(host, port, key, use_tls, values)
        result["steps"].append(
            {
                "action": "Appliance.Control.Light SET onoff=%d" % target_on,
                "method": meross_method(res),
                "http_status": res.get("status"),
                "json": res.get("json"),
            }
        )

    time.sleep(0.8)
    after = get_state(host, port, key, use_tls)
    after_summary = after["summary"]
    result["after"] = after_summary
    after_light = after_summary.get("light") or {}
    after_togglex = after_summary.get("togglex") or []
    if after_togglex:
        after_on = int(after_togglex[0].get("onoff", -1))
    elif after_light:
        after_on = int(after_light.get("onoff", -1))
    else:
        after_on = -1
    result["after_onoff"] = after_on
    result["verified"] = after_on == target_on

    if color and light:
        try:
            rgb = int(color.lstrip("#"), 16)
        except Exception:
            rgb = 0xFF0000
        capacity = int(light.get("capacity", 6))
        base = {
            "channel": int(light.get("channel", 0)),
            "rgb": rgb,
            "luminance": 100,
            "capacity": capacity,
        }
        # Different firmware revisions accept slightly different Light SET
        # payloads.  Try the common shapes and keep the first one the device
        # actually reports back.
        variants = [
            base,
            dict(base, temperature=0),
            dict(base, temperature=-1),
            dict(base, transform=0),
            dict(base, capacity=7),
        ]
        attempts: List[Dict[str, Any]] = []
        color_verified = False
        after_color: Optional[Dict[str, Any]] = None
        for variant in variants:
            color_res = set_light(host, port, key, use_tls, variant)
            time.sleep(0.8)
            color_after = get_state(host, port, key, use_tls)
            after_color = color_after["summary"].get("light")
            rgb_after = (after_color or {}).get("rgb")
            attempts.append(
                {
                    "payload": variant,
                    "method": meross_method(color_res),
                    "http_status": color_res.get("status"),
                    "rgb_after": rgb_after,
                    "json": color_res.get("json"),
                }
            )
            if rgb_after == rgb:
                color_verified = True
                break
        result["color_attempts"] = attempts
        result["after_color"] = after_color
        result["color_verified"] = color_verified

    if restore:
        time.sleep(0.4)
        if togglex:
            res = set_togglex(host, port, key, use_tls, before_on)
        else:
            restore_values = dict(light)
            restore_values["channel"] = 0
            restore_values["onoff"] = before_on
            res = set_light(host, port, key, use_tls, restore_values)
        result["steps"].append(
            {
                "action": "restore onoff=%d" % before_on,
                "method": meross_method(res),
                "http_status": res.get("status"),
                "json": res.get("json"),
            }
        )
        if color and light:
            original_light = {
                k: light[k]
                for k in (
                    "channel",
                    "rgb",
                    "luminance",
                    "temperature",
                    "capacity",
                    "transform",
                )
                if k in light
            }
            if original_light:
                # The MSL120DR only accepts RGB changes with the ability
                # capacity (7), not the digest capacity (6).  Reuse the
                # capacity from the variant that actually worked.
                if color_verified and attempts:
                    original_light["capacity"] = attempts[-1]["payload"].get(
                        "capacity", original_light.get("capacity")
                    )
                set_light(host, port, key, use_tls, original_light)
        time.sleep(0.8)
        restored = get_state(host, port, key, use_tls)
        restored_summary = restored["summary"]
        restored_light = restored_summary.get("light") or {}
        restored_togglex = restored_summary.get("togglex") or []
        if restored_togglex:
            restored_on = int(restored_togglex[0].get("onoff", -1))
        elif restored_light:
            restored_on = int(restored_light.get("onoff", -1))
        else:
            restored_on = -1
        result["restored_onoff"] = restored_on
        result["restore_verified"] = restored_on == before_on
        result["restored_state"] = restored_summary

    return result


# --------------------------------------------------------------------------
# discovery
# --------------------------------------------------------------------------

def fingerprint_host(
    host: str, extra_ports: Optional[List[int]] = None, extra_http: bool = False
) -> Dict[str, Any]:
    finding: Dict[str, Any] = {"host": host, "ports": [], "http": []}
    scan_ports = list(DEFAULT_HTTP_PORTS) + list(DEFAULT_OTHER_PORTS)
    for port in extra_ports or []:
        if port not in scan_ports:
            scan_ports.append(port)
    for port in scan_ports:
        if tcp_probe(host, port):
            finding["ports"].append(port)

    http_ports = [
        p
        for p in finding["ports"]
        if p in DEFAULT_HTTP_PORTS or (extra_http and p in (extra_ports or []))
    ]
    for port in http_ports:
        use_tls = port == 443
        for path in ("/", "/index.html", "/status", "/api/status", "/config"):
            res = http_request(host, port, path, timeout=3.0, use_tls=use_tls)
            entry = {
                "path": path,
                "tls": use_tls,
                "status": res.get("status"),
                "error": res.get("error"),
                "server": (res.get("headers") or {}).get("Server"),
                "content_type": (res.get("headers") or {}).get("Content-Type"),
                "body_preview": (res.get("body") or "")[:400],
            }
            finding["http"].append(entry)
            if res.get("status") and res.get("status") < 400:
                # One useful page per port is enough for the initial report.
                break

    if 6668 in finding["ports"]:
        finding["tuya_hint"] = (
            "TCP 6668 is the Tuya local-protocol port. This may be a "
            "Tuya/Smart Life device rather than Meross."
        )
    return finding


def save_report(report: Dict[str, Any]) -> Tuple[Path, Path]:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = REPORT_DIR / "lamp_report.json"
    text_path = REPORT_DIR / "lamp_report.txt"
    json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    lines: List[str] = []
    lines.append("LampControll recon report")
    lines.append("Generated: %s" % report.get("generated_at"))
    lines.append("Host: %s" % report.get("hostname"))
    lines.append("Default gateway: %s" % report.get("default_gateway"))
    lines.append("")
    for finding in report.get("findings", []):
        lines.append("Host %s" % finding.get("host"))
        lines.append("  open TCP ports: %s" % finding.get("ports"))
        for entry in finding.get("http", []):
            lines.append(
                "  HTTP%s %s -> %s %s"
                % (
                    "S" if entry.get("tls") else "",
                    entry.get("path"),
                    entry.get("status"),
                    entry.get("error") or "",
                )
            )
            if entry.get("server"):
                lines.append("    server: %s" % entry.get("server"))
            if entry.get("body_preview"):
                preview = entry["body_preview"].replace("\n", " ")
                lines.append("    body: %s" % preview[:240])
        if finding.get("tuya_hint"):
            lines.append("  note: %s" % finding["tuya_hint"])
        lines.append("")

    meross = report.get("meross") or {}
    if meross:
        lines.append("Meross handshake")
        lines.append("  host: %s:%s" % (meross.get("host"), meross.get("port")))
        lines.append("  accepted key: %r" % meross.get("key"))
        summary = meross.get("summary") or {}
        lines.append("  model: %s" % summary.get("model"))
        lines.append("  uuid: %s" % summary.get("uuid"))
        lines.append("  mac: %s" % summary.get("mac"))
        lines.append("  firmware: %s" % summary.get("firmware"))
        lines.append("  light: %s" % json.dumps(summary.get("light")))
        lines.append("  togglex: %s" % json.dumps(summary.get("togglex")))
        ability = meross.get("ability") or {}
        lines.append("  namespaces: %s" % ", ".join(ability.get("namespaces") or []))
        wifi_list = meross.get("wifi_list") or []
        if wifi_list:
            lines.append("  nearby Wi-Fi networks visible to the lamp:")
            for entry in wifi_list:
                lines.append(
                    "    %-28s ch=%-3s enc=%-2s cipher=%-2s signal=%s"
                    % (
                        entry.get("ssid"),
                        entry.get("channel"),
                        entry.get("encryption"),
                        entry.get("cipher"),
                        entry.get("signal"),
                    )
                )
        lines.append("")

    control = report.get("control") or {}
    if control:
        lines.append("Control test")
        lines.append("  before onoff: %s" % control.get("before_onoff"))
        lines.append("  target onoff: %s" % control.get("target_onoff"))
        lines.append("  after onoff: %s" % control.get("after_onoff"))
        lines.append("  verified: %s" % control.get("verified"))
        if control.get("color_verified") is not None:
            lines.append("  color verified: %s" % control.get("color_verified"))
        if control.get("restore_verified") is not None:
            lines.append("  restore verified: %s" % control.get("restore_verified"))
        for step in control.get("steps", []):
            lines.append(
                "  %s -> %s (HTTP %s)"
                % (step.get("action"), step.get("method"), step.get("http_status"))
            )
        lines.append("")

    notes = report.get("notes") or []
    if notes:
        lines.append("Notes")
        for note in notes:
            lines.append("  - %s" % note)

    text_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return json_path, text_path


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", help="lamp IP (default: auto-detect gateway)")
    parser.add_argument("--port", type=int, default=80, help="Meross HTTP port")
    parser.add_argument(
        "--tls", action="store_true", help="use HTTPS for the Meross API"
    )
    parser.add_argument(
        "--control",
        action="store_true",
        help="toggle the lamp on/off to prove control, then restore",
    )
    parser.add_argument(
        "--color",
        help="also set an RGB colour during --control, e.g. ff0000",
    )
    parser.add_argument(
        "--keep",
        action="store_true",
        help="do not restore the original on/off state after --control",
    )
    parser.add_argument(
        "--timeout", type=float, default=5.0, help="HTTP timeout in seconds"
    )
    args = parser.parse_args()

    started = datetime.now().isoformat(timespec="seconds")
    gateway = default_gateway()
    report: Dict[str, Any] = {
        "generated_at": started,
        "hostname": socket.gethostname(),
        "default_gateway": gateway,
        "findings": [],
        "notes": [],
    }

    candidates: List[str] = []
    if args.host:
        candidates.append(args.host)
    else:
        if gateway:
            candidates.append(gateway)
        for host in COMMON_LAMP_HOSTS:
            if host not in candidates:
                candidates.append(host)

    local_ip = local_ip_for(gateway or "10.10.10.1")
    report["local_ip"] = local_ip
    log("LampControll recon")
    log("  default gateway: %s" % gateway)
    log("  local IP:        %s" % local_ip)
    log("  candidates:      %s" % ", ".join(candidates))
    log("")

    live_hosts: List[str] = []
    for host in candidates:
        log("Fingerprinting %s ..." % host)
        finding = fingerprint_host(
            host,
            extra_ports=[args.port] if args.host else None,
            extra_http=bool(args.host),
        )
        report["findings"].append(finding)
        if finding["ports"]:
            live_hosts.append(host)
            log("  open ports: %s" % finding["ports"])
        else:
            log("  no open ports")

    if not live_hosts:
        report["notes"].append(
            "No candidate host answered. Are you connected to the lamp's Wi-Fi?"
        )
        json_path, text_path = save_report(report)
        log("")
        log("No device found. Report written to:")
        log("  %s" % json_path)
        log("  %s" % text_path)
        return 1

    # Try the Meross protocol on each live host.
    meross_result: Optional[Dict[str, Any]] = None
    for host in live_hosts:
        ports = []
        for finding in report["findings"]:
            if finding["host"] == host:
                ports = finding["ports"]
        meross_ports = [p for p in ports if p in (80, 443)] or [args.port]
        if args.host and args.port not in meross_ports:
            meross_ports = [args.port]
        for port in meross_ports:
            use_tls = args.tls or port == 443
            log("")
            log("Trying Meross protocol on %s:%d%s ..." % (host, port, " (TLS)" if use_tls else ""))
            key, attempts, res = meross_handshake(host, port, use_tls)
            if key is None:
                log("  no accepted key (tried %s)" % ", ".join(repr(k) for k in MEROSS_KEYS))
                report.setdefault("meross_attempts", []).append(
                    {"host": host, "port": port, "attempts": attempts}
                )
                continue
            log("  accepted key: %r" % key)
            summary = summarize_system_all(res)
            log("  model: %s" % summary.get("model"))
            log("  uuid:  %s" % summary.get("uuid"))
            log("  mac:   %s" % summary.get("mac"))
            log("  fw:    %s" % summary.get("firmware"))
            log("  light: %s" % json.dumps(summary.get("light")))
            log("  togglex: %s" % json.dumps(summary.get("togglex")))

            ability_res = meross_call(
                host,
                port,
                "Appliance.System.Ability",
                "GET",
                {},
                key,
                use_tls=use_tls,
            )
            ability = summarize_ability(ability_res)
            log("  namespaces: %s" % ", ".join(ability.get("namespaces") or []))

            wifi_res = meross_call(
                host,
                port,
                "Appliance.Config.WifiList",
                "GET",
                {},
                key,
                use_tls=use_tls,
            )
            wifi_list = summarize_wifi_list(wifi_res)
            if wifi_list:
                log("  nearby Wi-Fi networks visible to the lamp:")
                for entry in wifi_list:
                    log(
                        "    %-28s ch=%-3s enc=%-2s cipher=%-2s signal=%s"
                        % (
                            entry.get("ssid"),
                            entry.get("channel"),
                            entry.get("encryption"),
                            entry.get("cipher"),
                            entry.get("signal"),
                        )
                    )

            meross_result = {
                "host": host,
                "port": port,
                "tls": use_tls,
                "key": key,
                "summary": summary,
                "ability": ability,
                "system_all": res.get("json"),
                "ability_raw": ability_res.get("json"),
                "wifi_list": wifi_list,
                "wifi_list_raw": wifi_res.get("json"),
            }
            break
        if meross_result:
            break

    report["meross"] = meross_result

    if not meross_result:
        report["notes"].append(
            "A device answered but did not accept the Meross local protocol. "
            "Check the HTTP fingerprints and the Tuya hint."
        )
        json_path, text_path = save_report(report)
        log("")
        log("No Meross device identified. Report written to:")
        log("  %s" % json_path)
        log("  %s" % text_path)
        return 2

    host = meross_result["host"]
    port = meross_result["port"]
    key = meross_result["key"]
    use_tls = meross_result["tls"]

    if args.control:
        log("")
        log("Control test: toggling lamp ...")
        control = control_test(
            host,
            port,
            key,
            use_tls,
            meross_result["summary"],
            args.color,
            restore=not args.keep,
        )
        report["control"] = control
        log("  before onoff: %s" % control.get("before_onoff"))
        log("  target onoff: %s" % control.get("target_onoff"))
        log("  after onoff:  %s" % control.get("after_onoff"))
        log("  verified:     %s" % control.get("verified"))
        if control.get("color_verified") is not None:
            log("  color verified: %s" % control.get("color_verified"))
        if control.get("restore_verified") is not None:
            log("  restore verified: %s" % control.get("restore_verified"))
        if control.get("error"):
            log("  error: %s" % control["error"])

    json_path, text_path = save_report(report)
    log("")
    log("Report written to:")
    log("  %s" % json_path)
    log("  %s" % text_path)
    if args.control and (report.get("control") or {}).get("verified"):
        log("")
        log("SUCCESS: the lamp changed state and reported the new state back.")
        return 0
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        log("")
        log("Interrupted.")
        sys.exit(130)
    except Exception:
        traceback.print_exc()
        sys.exit(1)
