# Result: the lamp is controlled from this Mac

## Device

| Field | Value |
| --- | --- |
| Model | `msl120dr` (Meross lamp) |
| Hardware | 4.0.0 |
| Firmware | 4.1.12 |
| UUID | `YOUR_LAMP_UUID` |
| MAC | `aa:bb:cc:dd:ee:ff` |
| Setup AP | `Meross_XXXXXX` |
| LAN address | `192.168.1.111` |
| Local key after onboarding | empty string |

## 1. Reverse engineering (lamp AP)

The lamp was reached at `10.10.10.1` while the Mac was on `Meross_XXXXXX`.
`Appliance.System.All` returned the state above; the signed request envelope
was accepted with key `meross` during setup mode.

The first control attempt sent `onoff` through `Appliance.Control.Light` and
got `SETACK` but no state change. The corrected tool uses
`Appliance.Control.ToggleX`:

```text
before onoff: 1
target onoff: 0
after onoff:  0
verified:     True
restore verified: True
```

Colour required the ability capacity, not the digest capacity:

```text
SET light rgb=65280 capacity=6 -> SETACK, rgb stays 16777215
SET light rgb=65280 capacity=7 -> SETACK, rgb becomes 65280
```

The lamp's own Wi-Fi scan found the home network on 2.4 GHz:

```text
YOUR_HOME_WIFI  ch=9  enc=6  cipher=3  signal=73  bssid=aa:bb:cc:dd:ee:ff
```

## 2. Onboarding to the home Wi-Fi

The Mac switched to `Meross_XXXXXX`, and `Appliance.Config.Wifi` was sent
with the lamp's own scan data:

```text
Wi-Fi scan attempt 3/6: 3 network(s)
selected AP: YOUR_HOME_WIFI bssid=aa:bb:cc:dd:ee:ff ch=9 enc=6 cipher=3
Appliance.Config.Wifi -> SETACK (HTTP 200)
lamp AP endpoint gone (rebooting)
```

The lamp rebooted, joined `YOUR_HOME_WIFI`, and appeared at `192.168.1.111`.
The Mac briefly failed to rejoin the home Wi-Fi (`-3900`), power-cycled Wi-Fi,
and came back. Password handling: read from the System keychain into a `0600`
temp file, sent once, deleted on exit; it is not in any report.

## 3. LAN control (permanent)

The discovery found the lamp by UUID and MAC:

```text
Found lamp:
  IP:       192.168.1.111:80
  model:    msl120dr
  uuid:     YOUR_LAMP_UUID
  mac:      aa:bb:cc:dd:ee:ff
  firmware: 4.1.12
  key:      ''
```

Live control through `tools/lampctl.py`:

```text
$ python3 tools/lampctl.py status
Lamp 192.168.1.111:80
  model:      msl120dr (fw 4.1.12)
  power:      on
  color:      #0000ff (rgb 255)
  luminance:  100
  temperature:100

$ python3 tools/lampctl.py off
power off -> verified (0)

$ python3 tools/lampctl.py on
power on -> verified (1)

$ python3 tools/lampctl.py color 00FF00
color #00ff00 -> verified (reported #00ff00)

$ python3 tools/lampctl.py color 0000FF
color #0000ff -> verified (reported #0000ff)
```

The lamp was left on and white after the tests.

## 4. macOS app

The SwiftUI app was built, ad-hoc signed, installed at
`/Applications/LampControll.app`, and it connected to the real lamp
(`msl120dr · fw 4.1.12`, On, brightness 100).

The same `LampClient.swift` used by the app was exercised against the lamp:

```text
before: on=true rgb=#ffffff
toggle: on=false verified=true
colour: rgb=#34c759 verified=true
restored: on=true rgb=#ffffff
```

## 5. Android app

The signed APK was installed on an Android 15 emulator. The app connected to
the lamp and showed:

```text
● msl120dr · fw 4.1.12 · On
Brightness 100%
```

Tapping the green swatch changed the real lamp:

```text
$ python3 tools/lampctl.py status
color: #34c759 (rgb 3458905)
```

Tapping the white swatch restored it:

```text
color: #ffffff (rgb 16777215)
```

## Reproduce

```sh
python3 tools/lampctl.py discover   # first run / IP change
python3 tools/lampctl.py status
python3 tools/lampctl.py toggle
python3 tools/lampctl.py color FF8800

./macapp/build.sh                   # macOS app
./android/build.sh                  # signed Android APK
```
