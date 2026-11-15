# How to talk to the lamp

This is the “explain it like I’m new to this” version. The full packet
reference is in [protocol.md](protocol.md); this page explains the mental
model and shows a runnable client.

## 1. The lamp is a tiny web server

When the lamp is on your network it has an IP address, for example
`192.168.1.111`. It listens on **port 80** (plain HTTP) and has one useful
endpoint:

```text
POST http://192.168.1.111/config
```

You do not open this in a browser. You send it a JSON document and it sends
JSON back. That is the whole idea.

## 2. Every message has an envelope and a payload

Think of the JSON as an envelope with a letter inside:

```json
{
  "header": {
    "messageId": "0123456789abcdef0123456789abcdef",
    "namespace": "Appliance.System.All",
    "method": "GET",
    "payloadVersion": 1,
    "from": "MyLampClient",
    "timestamp": 1760000000,
    "timestampMs": 0,
    "sign": "d41d8cd98f00b204e9800998ecf8427e"
  },
  "payload": {
    "all": {}
  }
}
```

- **messageId** — a random 32-character hex ID. The lamp copies it into its
  reply so you can match request and response.
- **namespace** — which command you are calling, for example
  `Appliance.System.All` (“tell me everything”).
- **method** — `GET` to read, `SET` to change something.
- **payloadVersion** — always `1` on this device.
- **from** — a free-form label; the lamp does not care much.
- **timestamp** — Unix time in seconds.
- **sign** — a fingerprint, explained below.
- **payload** — the actual command data.

## 3. The signature

The lamp checks this value:

```text
sign = md5(messageId + key + timestamp)
```

`md5` is a hash function: it turns a string into a fixed 32-character
fingerprint. Both sides compute the same fingerprint from the same inputs.
If your key is wrong, your fingerprint is different and the lamp replies:

```json
{"header": {"method": "ERROR"}, "payload": {"error": {"detail": "sign error"}}}
```

Important: this is **not encryption**. It proves you know the shared key, but
anyone sniffing the local network can read the JSON. It is a checksum, not
security.

- In the lamp's setup/AP mode the key is the literal string `meross`.
- After the lamp has joined the home Wi-Fi, its key is the **empty string** on
  this device.

We found that by trying the documented setup key and then reading the
`Appliance.System.All` response. If the key is wrong, you get an `ERROR`
instead of `GETACK`.

## 4. Namespaces are just commands

The lamp tells you what it supports with `Appliance.System.Ability`. The ones
we use are:

| Namespace | Method | Payload | Meaning |
| --- | --- | --- | --- |
| `Appliance.System.All` | `GET` | `{"all": {}}` | read the full state |
| `Appliance.System.Ability` | `GET` | `{}` | list supported commands |
| `Appliance.Control.ToggleX` | `SET` | `{"togglex":{"channel":0,"onoff":1}}` | turn on/off |
| `Appliance.Control.Light` | `SET` | `{"light":{"channel":0,"rgb":65280,"luminance":100,"capacity":7}}` | colour/brightness |
| `Appliance.Config.WifiList` | `GET` | `{}` | ask the lamp for nearby Wi-Fi |
| `Appliance.Config.Wifi` | `SET` | `{"wifi":{"ssid":"...","password":"..."}}` | join a Wi-Fi network |

The response header uses `GETACK` or `SETACK` when it worked, and `ERROR`
when it did not.

## 5. A complete minimal client

[`examples/minimal_client.py`](../examples/minimal_client.py) is a single
stdlib-only file. The core is this:

```python
message_id = uuid.uuid4().hex
timestamp = int(time.time())
sign = hashlib.md5((message_id + key + str(timestamp)).encode()).hexdigest()

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
    "http://%s/config" % host,
    data=json.dumps(packet).encode(),
    headers={"Content-Type": "application/json"},
    method="POST",
)
with urlopen(request, timeout=5) as response:
    document = json.loads(response.read())
```

Run it against the real lamp:

```sh
python3 examples/minimal_client.py --host 192.168.1.111 status
python3 examples/minimal_client.py --host 192.168.1.111 off
python3 examples/minimal_client.py --host 192.168.1.111 on
python3 examples/minimal_client.py --host 192.168.1.111 color 00FF00
python3 examples/minimal_client.py --host 192.168.1.111 brightness 40
```

Example output (from the bundled mock, so you can reproduce it offline):

```text
$ python3 examples/minimal_client.py --host 127.0.0.1 --port 18080 --key meross status
Lamp 127.0.0.1
  model:     msl420 (fw 9.9.9)
  power:     on
  colour:    #ffffff
  luminance: 80

$ python3 examples/minimal_client.py --host 127.0.0.1 --port 18080 --key meross color 00FF00
Lamp 127.0.0.1
  model:     msl420 (fw 9.9.9)
  power:     on
  colour:    #00ff00
  luminance: 80
```

The real lamp returned the same shape with `msl120dr`, firmware `4.1.12`, and
`luminance: 100`.

## 6. How the protocol was actually figured out

The short version is: **look at the state the lamp reports, change one thing,
read the state again**.

1. **Find the address.** In setup mode the lamp is the DHCP gateway, normally
   `10.10.10.1`. A port scan showed port 80.
2. **Identify the protocol.** The HTTP setup page and the signed JSON envelope
   match Meross's local protocol. Community documentation gave the envelope
   and the setup key `meross`.
3. **Ask the lamp what it can do.** `Appliance.System.Ability` listed
   `Appliance.Control.ToggleX`, `Appliance.Control.Light`,
   `Appliance.Config.WifiList`, etc.
4. **Read the state.** `Appliance.System.All` returned `togglex` and `light`.
5. **Hypothesis: on/off is in `light.onoff`.** We sent
   `Appliance.Control.Light` with `onoff`. The lamp answered `SETACK`, but
   re-reading `System.All` showed `togglex` unchanged. So the hypothesis was
   wrong: the real switch is `Appliance.Control.ToggleX`.
6. **Hypothesis: RGB uses `capacity: 6`.** The digest said 6, but the lamp
   ignored it. Trying `capacity: 7` (from `System.Ability`) changed the
   reported `rgb`. That is why the verified payload uses 7.
7. **Onboarding.** `WifiList` returned base64 SSIDs plus BSSID/channel/
   encryption/cipher. `Config.Wifi` accepted base64 SSID/password and the
   lamp rebooted onto the home network.

The important lesson: **`SETACK` means “I received it”, not “the physical
state changed”**. Every command in this project is followed by another
`System.All` read to verify the result.

## 7. Security notes

- HTTP is plaintext on the LAN. The signature is a shared-key check, not
  encryption.
- After onboarding, the key is empty, so the signature adds no real
  authentication. Keep the lamp on a trusted network and do not expose port
  80 to the internet.
- The lamp is intentionally **not bound to the Meross cloud**: `server` is
  empty and `userId` is 0. It works entirely locally.
- The Wi-Fi password is only used once during onboarding. It is never stored
  in the apps or the repository.

## 8. Where to look in the code

| File | What it shows |
| --- | --- |
| [`examples/minimal_client.py`](../examples/minimal_client.py) | smallest readable client |
| [`tools/lamp_recon.py`](../tools/lamp_recon.py) | discovery and state reading |
| [`tools/lampctl.py`](../tools/lampctl.py) | full command-line client |
| [`macapp/LampClient.swift`](../macapp/LampClient.swift) | Swift version used by the Mac app |
| [`android/src/com/thalium/lampcontroll/LampClient.java`](../android/src/com/thalium/lampcontroll/LampClient.java) | Java version used by Android |
