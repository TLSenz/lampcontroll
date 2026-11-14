# Meross lamp local protocol (reverse-engineered notes)

## Device discovery

- The lamp exposes an open 2.4 GHz access point named `Meross_XXXXXX`
  (observed signal -49 dBm, no encryption).
- In setup/AP mode a Meross device normally serves DHCP and puts itself at
  `10.10.10.1`; the default gateway is the lamp.
- The device speaks plain HTTP on port 80. The config endpoint is
  `POST http://<lamp-ip>/config`.

## Request envelope

```json
{
  "header": {
    "messageId": "32 hex characters",
    "namespace": "Appliance.System.All",
    "method": "GET",
    "payloadVersion": 1,
    "from": "<lamp-ip>/config",
    "timestamp": 1760000000,
    "timestampMs": 0,
    "sign": "md5(messageId + key + timestamp)"
  },
  "payload": {}
}
```

- `sign = md5(messageId + key + timestamp)` as a lowercase hex string.
- In AP/setup mode the shared key is normally the literal string `meross`
  (an unpaired device has no account key yet). The tool also tries an empty
  key for older firmware.
- `messageId` is arbitrary; responses echo it.

## Useful namespaces

| Namespace | Method | Payload | Meaning |
| --- | --- | --- | --- |
| `Appliance.System.All` | `GET` | `{"all": {}}` | full state: hardware, firmware, light, togglex |
| `Appliance.System.Ability` | `GET` | `{}` | supported namespaces and light capacity |
| `Appliance.Control.Light` | `GET` | `{"light": {}}` | current light state |
| `Appliance.Control.Light` | `SET` | `{"light": {...}}` | set on/off, RGB, luminance, temperature |
| `Appliance.Control.ToggleX` | `SET` | `{"togglex":{"channel":0,"onoff":1}}` | on/off for plug-like devices |

### Light state observed on Meross lamps

```json
{
  "light": {
    "onoff": 1,
    "capacity": 6,
    "channel": 0,
    "rgb": 16753920,
    "temperature": 100,
    "luminance": 100,
    "transform": 0
  }
}
```

- `onoff`: 0/1.
- `rgb`: 24-bit integer, e.g. `0x00FF00` = 65280.
- `luminance`: 0-100.
- `temperature`: warm/cool white value; `capacity` describes which features
  the model supports.
- A SET usually echoes the accepted state in a `SETACK`; a follow-up
  `Appliance.System.All` confirms the change.

## Response header

Responses have `method` values `GETACK`, `SETACK`, `PUSH` or `ERROR`, echo the
request `messageId`, and include their own `sign`. An invalid request signature
produces an `ERROR` payload such as `{"error":{"code":5000,"detail":"sign error"}}`.

## Tooling in this repo

- `tools/lamp_recon.py` — stdlib-only discovery + Meross handshake + optional
  toggle/colour test. Writes `reports/lamp_report.json` and
  `reports/lamp_report.txt`.
- `Run-Lamp-Recon.command` — double-clickable macOS helper: switches Wi-Fi to
  `Meross_XXXXXX`, runs the tool, switches back to `YOUR_HOME_WIFI`.
- `tests/mock_meross_lamp.py` — local mock implementing the same protocol, used
  to verify the tool end-to-end without the physical lamp.

## Verification without the lamp

```sh
python3 tests/mock_meross_lamp.py --port 18080
python3 tools/lamp_recon.py --host 127.0.0.1 --port 18080 --control --color 00ff00
```

The mock validates the MD5 signature, answers the three namespaces, and changes
its state on SET. The tool reports:

```
before onoff: 1
target onoff: 0
after onoff:  0
verified:     True
color verified: True
restore verified: True
```

## Real device findings

First run against the physical lamp (connected to `Meross_XXXXXX`):

| Field | Value |
| --- | --- |
| Model | `msl120dr` |
| Hardware | `4.0.0` |
| Firmware | `4.1.12` (HomeKit version 4.1) |
| Chip | `rtl8710cm` |
| UUID | `YOUR_LAMP_UUID` |
| MAC | `aa:bb:cc:dd:ee:ff` |
| Lamp IP | `10.10.10.1` |
| Mac IP on lamp AP | `10.10.10.100` |
| Accepted key | `meross` |
| Online status | `2` (unbound / setup mode) |

Observed state:

```json
{
  "light": {
    "capacity": 6,
    "channel": 0,
    "rgb": 16777215,
    "temperature": 100,
    "luminance": 100,
    "transform": 0
  },
  "togglex": [{"channel": 0, "onoff": 1, "lmTime": 0}]
}
```

Important: **the `light` digest has no `onoff` field** on this firmware.
`Appliance.Control.ToggleX` is the authoritative on/off state. Sending
`Appliance.Control.Light` with `onoff` returns `SETACK` but does not change
the `togglex` state. The first version of the tool used the light field and
therefore reported a false negative; the corrected tool uses ToggleX and
verifies against the returned `togglex` value.

Colour control has a similar trap: the digest reports `capacity: 6`, but the
lamp only accepts an RGB change when the SET payload uses the **ability
capacity 7**. Payloads with capacity 6 return `SETACK` and leave `rgb` at
`16777215` (white). Verified sequence:

```text
SET {"light":{"channel":0,"rgb":65280,"luminance":100,"capacity":6}} -> SETACK, rgb stays 16777215
SET {"light":{"channel":0,"rgb":65280,"luminance":100,"capacity":7}} -> SETACK, rgb becomes 65280
```

The Wi-Fi scan reported by the lamp:

```json
[
  {"ssid": "YOUR_HOME_WIFI", "bssid": "aa:bb:cc:dd:ee:ff",
   "signal": 68, "channel": 9, "encryption": 6, "cipher": 3},
  {"ssid": "austrasse-gast", "bssid": "b2:4b:fe:f4:dd:a1",
   "signal": 68, "channel": 9, "encryption": 8, "cipher": 4},
  {"ssid": "YOUR_HOME_WIFI", "bssid": "aa:bb:cc:dd:ee:02",
   "signal": 23, "channel": 9, "encryption": 6, "cipher": 3}
]
```

The SSID is base64-encoded in the raw response. Onboarding uses
`Appliance.Config.Wifi` with the selected entry:

```json
{
  "wifi": {
    "ssid": "<base64>",
    "password": "<base64>",
    "bssid": "aa:bb:cc:dd:ee:ff",
    "channel": 9,
    "encryption": 6,
    "cipher": 3
  }
}
```

`Appliance.System.Ability` on this device lists:

```text
Appliance.Config.Info, Appliance.Config.Key, Appliance.Config.Trace,
Appliance.Config.Wifi, Appliance.Config.WifiList, Appliance.Control.Bind,
Appliance.Control.Light, Appliance.Control.Multiple,
Appliance.Control.TimerX, Appliance.Control.ToggleX,
Appliance.Control.TriggerX, Appliance.Control.Unbind,
Appliance.Control.Upgrade, Appliance.Digest.TimerX,
Appliance.Digest.TriggerX, Appliance.System.Ability, Appliance.System.All,
Appliance.System.Clock, Appliance.System.Debug, Appliance.System.Firmware,
Appliance.System.Hardware, Appliance.System.Online,
Appliance.System.Position, Appliance.System.Report, Appliance.System.Runtime,
Appliance.System.Time
```

The lamp also serves a setup page at `http://10.10.10.1/` with SSID/password
form fields (`ELEM_SSID`, `ELEM_PASSWORD`, `ELEM_FW`, `ELEM_UUID`). This is
an alternative onboarding path to the JSON API.

## Open questions

- Which exact `Appliance.Control.Light` payload switches the MSL120DR into
  RGB mode (the first attempt returned `SETACK` but the reported `rgb` stayed
  white).
- Whether `Appliance.Config.Wifi` on firmware 4.1.12 needs only
  base64(ssid)/base64(password), or also bssid/channel/encryption/cipher from
  `Appliance.Config.WifiList`.
- Whether the device keeps key `meross` after joining the home Wi-Fi.
