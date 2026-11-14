#!/usr/bin/env python3
"""A tiny mock Meross lamp for testing tools/lamp_recon.py offline.

It implements enough of POST /config to validate the signature and answer:
  Appliance.System.All
  Appliance.System.Ability
  Appliance.Control.Light
  Appliance.Control.ToggleX
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

STATE = {
    "onoff": 1,
    "rgb": 0xFFFFFF,
    "luminance": 80,
    "temperature": 100,
    "capacity": 6,
    "channel": 0,
    "transform": 0,
}


def light_state():
    # The real MSL120DR's Light digest has no onoff field; ToggleX is
    # authoritative for on/off.
    return {k: v for k, v in STATE.items() if k != "onoff"}

EMPTY_WIFI_LIST = False

UUID = "mocklamp0000000000000000000000000000000000000000000000000000000000"


def sign(message_id: str, key: str, timestamp: str) -> str:
    return hashlib.md5((message_id + key + str(timestamp)).encode()).hexdigest()


def header_for(req_header, method, namespace, key="meross"):
    return {
        "messageId": req_header.get("messageId", ""),
        "namespace": namespace,
        "method": method,
        "payloadVersion": 1,
        "from": "/appliance/%s/publish" % UUID,
        "timestamp": int(__import__("time").time()),
        "timestampMs": 0,
        "sign": sign(
            req_header.get("messageId", ""),
            key,
            int(__import__("time").time()),
        ),
    }


def system_all():
    return {
        "all": {
            "system": {
                "hardware": {
                    "type": "msl420",
                    "subType": "mock",
                    "version": "1.0.0",
                    "chipType": "mock-chip",
                    "uuid": UUID,
                    "macAddress": "02:00:00:00:00:01",
                },
                "firmware": {
                    "version": "9.9.9",
                    "compileTime": "2026/01/01 00:00:00 GMT +08:00",
                    "innerIp": "10.10.10.1",
                },
                "online": {"status": 1},
            },
            "digest": {
                "light": light_state(),
                "togglex": [
                    {"channel": 0, "onoff": STATE["onoff"], "lmTime": 0}
                ],
                "triggerx": [],
                "timerx": [],
            },
        }
    }


class Handler(BaseHTTPRequestHandler):
    server_version = "MockMeross/1.0"

    def log_message(self, fmt, *args):
        pass

    def _send(self, obj, status=200):
        body = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.path != "/config":
            self._send({"error": "not found"}, 404)
            return
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length)
        try:
            packet = json.loads(raw.decode())
        except Exception:
            self._send({"error": "bad json"}, 400)
            return

        header = packet.get("header") or {}
        namespace = header.get("namespace")
        method = header.get("method")
        payload = packet.get("payload") or {}
        message_id = header.get("messageId", "")
        timestamp = str(header.get("timestamp", ""))
        provided = header.get("sign", "")
        expected = sign(message_id, "meross", timestamp)
        if provided != expected:
            self._send(
                {
                    "header": header_for(header, "ERROR", namespace or ""),
                    "payload": {
                        "error": {
                            "code": 5000,
                            "detail": "sign error",
                            "expected": expected,
                        }
                    },
                }
            )
            return

        if namespace == "Appliance.System.All" and method == "GET":
            self._send(
                {
                    "header": header_for(header, "GETACK", namespace),
                    "payload": system_all(),
                }
            )
            return

        if namespace == "Appliance.System.Ability" and method == "GET":
            self._send(
                {
                    "header": header_for(header, "GETACK", namespace),
                    "payload": {
                        "payloadVersion": 1,
                        "ability": {
                            "Appliance.System.All": {},
                            "Appliance.System.Ability": {},
                            "Appliance.Control.Light": {"capacity": 6},
                            "Appliance.Control.ToggleX": {},
                            "Appliance.Control.Effect": {"capacity": 1},
                        },
                    },
                }
            )
            return

        if namespace == "Appliance.Config.WifiList" and method == "GET":
            wifi_list = []
            if not EMPTY_WIFI_LIST:
                wifi_list = [
                    {
                        "ssid": base64.b64encode(b"YOUR_HOME_WIFI").decode(),
                        "bssid": "aa:bb:cc:dd:ee:ff",
                        "signal": 90,
                        "channel": 1,
                        "encryption": 6,
                        "cipher": 3,
                    }
                ]
            self._send(
                {
                    "header": header_for(header, "GETACK", namespace),
                    "payload": {"wifiList": wifi_list},
                }
            )
            return

        if namespace == "Appliance.Config.Wifi" and method == "SET":
            wifi = payload.get("wifi") or {}
            # Echo only the non-secret routing fields.
            self._send(
                {
                    "header": header_for(header, "SETACK", namespace),
                    "payload": {
                        "wifi": {
                            "ssid": wifi.get("ssid"),
                            "bssid": wifi.get("bssid"),
                            "channel": wifi.get("channel"),
                            "encryption": wifi.get("encryption"),
                            "cipher": wifi.get("cipher"),
                        }
                    },
                }
            )
            return

        if namespace == "Appliance.Control.Light":
            if method == "GET":
                self._send(
                    {
                        "header": header_for(header, "GETACK", namespace),
                        "payload": {"light": light_state()},
                    }
                )
                return
            if method == "SET":
                light = payload.get("light") or {}
                for key in ("rgb", "luminance", "temperature", "capacity", "channel", "transform"):
                    if key in light:
                        STATE[key] = light[key]
                self._send(
                    {
                        "header": header_for(header, "SETACK", namespace),
                        "payload": {"light": light_state()},
                    }
                )
                return

        if namespace == "Appliance.Control.ToggleX":
            if method == "GET":
                self._send(
                    {
                        "header": header_for(header, "GETACK", namespace),
                        "payload": {
                            "togglex": [
                                {
                                    "channel": 0,
                                    "onoff": STATE["onoff"],
                                    "lmTime": 0,
                                }
                            ]
                        },
                    }
                )
                return
            if method == "SET":
                togglex = payload.get("togglex") or {}
                STATE["onoff"] = int(togglex.get("onoff", STATE["onoff"]))
                self._send(
                    {
                        "header": header_for(header, "SETACK", namespace),
                        "payload": {
                            "togglex": [
                                {
                                    "channel": 0,
                                    "onoff": STATE["onoff"],
                                    "lmTime": 0,
                                }
                            ]
                        },
                    }
                )
                return

        self._send(
            {
                "header": header_for(header, "ERROR", namespace or ""),
                "payload": {"error": {"code": 4001, "detail": "unsupported"}},
            }
        )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=18080)
    parser.add_argument("--empty-wifi-list", action="store_true")
    args = parser.parse_args()
    global EMPTY_WIFI_LIST
    EMPTY_WIFI_LIST = args.empty_wifi_list
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print("mock Meross lamp on http://%s:%d/config" % (args.host, args.port), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
