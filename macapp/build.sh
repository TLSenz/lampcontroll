#!/bin/zsh
# Build a small, ad-hoc-signed LampControll.app for this Mac.
set -euo pipefail
cd "$(dirname "$0")"

ROOT="$(cd .. && pwd)"
APP="build/LampControll.app"
SDK="$(xcrun --show-sdk-path)"

rm -rf build
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"

cp Info.plist "$APP/Contents/Info.plist"

echo "Compiling Swift sources ..."
swiftc \
  -O \
  -parse-as-library \
  -module-name LampControll \
  -target arm64-apple-macosx13.0 \
  -sdk "$SDK" \
  -framework SwiftUI \
  -framework AppKit \
  -framework CryptoKit \
  -o "$APP/Contents/MacOS/LampControll" \
  LampControllApp.swift LampClient.swift ContentView.swift

# App icon: render the existing SVG with Quick Look, then build an iconset.
ICON_SRC="$ROOT/assets/icon.svg"
if [[ -f "$ICON_SRC" ]]; then
  echo "Rendering icon ..."
  qlmanage -t -s 1024 -o build "$ICON_SRC" >/dev/null 2>&1 || true
  PNG="build/icon.svg.png"
  if [[ -f "$PNG" ]]; then
    ICONSET="build/AppIcon.iconset"
    mkdir -p "$ICONSET"
    for size in 16 32 64 128 256 512 1024; do
      sips -z "$size" "$size" "$PNG" --out "build/icon-$size.png" >/dev/null
    done
    cp "build/icon-16.png" "$ICONSET/icon_16x16.png"
    cp "build/icon-32.png" "$ICONSET/icon_16x16@2x.png"
    cp "build/icon-32.png" "$ICONSET/icon_32x32.png"
    cp "build/icon-64.png" "$ICONSET/icon_32x32@2x.png"
    cp "build/icon-128.png" "$ICONSET/icon_128x128.png"
    cp "build/icon-256.png" "$ICONSET/icon_128x128@2x.png"
    cp "build/icon-256.png" "$ICONSET/icon_256x256.png"
    cp "build/icon-512.png" "$ICONSET/icon_256x256@2x.png"
    cp "build/icon-512.png" "$ICONSET/icon_512x512.png"
    cp "build/icon-1024.png" "$ICONSET/icon_512x512@2x.png"
    iconutil -c icns "$ICONSET" -o "$APP/Contents/Resources/AppIcon.icns" || true
  fi
fi

echo "Signing (ad-hoc) ..."
codesign --force --deep --sign - "$APP"
codesign --verify --deep --strict "$APP"

echo "Built: $(pwd)/$APP"
