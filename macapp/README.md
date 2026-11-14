# LampControll for macOS

A small SwiftUI app for the Meross MSL120DR lamp. It talks directly to the
lamp over the local network — no Meross cloud, no account.

## Features

- Live on/off state and model/firmware display
- Power toggle
- Brightness slider
- Seven colour presets
- Editable lamp IP, persisted in `UserDefaults`
- Automatic refresh on launch

## Build

Requires macOS 13+ and the Swift toolchain (Xcode Command Line Tools).

```sh
./build.sh
```

The app is built at `build/LampControll.app` and ad-hoc signed.

## Install

```sh
ditto build/LampControll.app /Applications/LampControll.app
open /Applications/LampControll.app
```

On first launch macOS may ask for **Local Network** permission. Allow it so
the app can reach the lamp.

The default address is `192.168.1.111`; change it in the footer if your lamp
has a different DHCP address.
