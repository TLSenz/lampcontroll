# LampControll for Android

A single-activity Android app for the Meross MSL120DR lamp. It speaks the
Meross local protocol directly over the LAN — no cloud, no account.

## Features

- Live on/off state and model/firmware display
- Power toggle
- Brightness slider
- Seven colour presets
- Editable lamp IP, persisted in `SharedPreferences`
- No external libraries; plain Android Java

## Build

Requires the Android SDK (build-tools 34+ and a platform) plus JDK 17+.
No Gradle needed.

```sh
./build.sh
```

Output: `LampControll.apk` (signed with the local release key).

## Install

```sh
adb install -r LampControll.apk
```

Or copy the APK to the phone and sideload it (enable “Install unknown apps”
for the file manager/browser you use).

Minimum Android version: 7.0 (API 24). Target: API 36.

The default address is `192.168.1.111`; change it in the app if your lamp has
a different DHCP address.
