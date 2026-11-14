# How the lamp's Wi-Fi was identified

macOS hides Wi-Fi names from command-line tools unless the process has
Location Services permission:

```text
$ system_profiler SPAirPortDataType
...
Other Local Wi-Fi Networks:
  <redacted>:
    Security: None
    Signal / Noise: -49 dBm / -77 dBm
```

`CoreWLAN`'s `scanForNetworks` returns `nil` for the same reason, and UI
scripting through System Events is blocked by Accessibility permissions:

```text
execution error: osascript hat keine Berechtigung für den Hilfszugriff. (-1719)
```

Screen capture *is* allowed, and the Wi-Fi settings window renders the names,
so the window was captured and OCR'd with the macOS Vision framework:

```sh
open "x-apple.systempreferences:com.apple.wifi-settings-extension"
screencapture -x -l <window-id> /tmp/wifi_window.png
swift tools/ocr.swift /tmp/wifi_window.png
```

Relevant OCR output:

```text
YOUR_HOME_WIFI
• Verbunden
Bekanntes Netzwerk
Andere Netzwerke
austrasse-gast
bianconero94
Casa Maldonado Silva
Meross_XXXXXX
NSA_observation truck_2.1
xvb-29652
```

That identified:

- **Lamp access point:** `Meross_XXXXXX` (the only Meross network, open,
  2.4 GHz, -49 dBm)
- **Current home network:** `YOUR_HOME_WIFI` (WPA2, saved)

The lamp AP hands out DHCP and normally puts itself at `10.10.10.1`, which is
what `tools/lamp_recon.py` probes first.
