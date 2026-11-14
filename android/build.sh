#!/bin/zsh
# Build a signed LampControll Android APK without Gradle.
set -euo pipefail
cd "$(dirname "$0")"

SDK="${ANDROID_HOME:-$HOME/Library/Android/sdk}"
BT="$SDK/build-tools/36.1.0"
PLATFORM="$SDK/platforms/android-36/android.jar"
if [[ ! -x "$BT/aapt2" ]]; then
  BT="$(ls -d "$SDK"/build-tools/* | sort -V | tail -1)"
fi
if [[ ! -f "$PLATFORM" ]]; then
  PLATFORM="$(ls "$SDK"/platforms/*/android.jar | sort -V | tail -1)"
fi

echo "Android build-tools: $BT"
echo "Android platform:    $PLATFORM"

rm -rf build
mkdir -p build/compiled build/classes build/dex build/gen build/dist

echo "Compiling resources ..."
"$BT/aapt2" compile --dir res -o build/compiled.zip

echo "Linking resources ..."
"$BT/aapt2" link \
  -o build/base.apk \
  -I "$PLATFORM" \
  --manifest AndroidManifest.xml \
  -R build/compiled.zip \
  --auto-add-overlay \
  --java build/gen \
  --min-sdk-version 24 \
  --target-sdk-version 36 \
  --version-code 1 \
  --version-name 1.0

echo "Compiling Java ..."
find src build/gen -name '*.java' > build/sources.txt
javac --release 8 -Xlint:-options -classpath "$PLATFORM" -d build/classes @build/sources.txt

echo "Dexing ..."
jar --create --file build/classes.jar -C build/classes .
"$BT/d8" --min-api 24 --lib "$PLATFORM" --output build/dex build/classes.jar

echo "Packaging ..."
cp build/base.apk build/unsigned.apk
(cd build/dex && zip -q -j ../unsigned.apk classes.dex)
"$BT/zipalign" -f 4 build/unsigned.apk build/aligned.apk

KEYSTORE="$HOME/.lampcontroll/android-release.keystore"
if [[ ! -f "$KEYSTORE" ]]; then
  echo "Creating signing key at $KEYSTORE ..."
  mkdir -p "$(dirname "$KEYSTORE")"
  keytool -genkeypair \
    -keystore "$KEYSTORE" \
    -alias lampcontroll \
    -keyalg RSA \
    -keysize 2048 \
    -validity 10000 \
    -storepass lampcontroll \
    -keypass lampcontroll \
    -dname "CN=LampControll, OU=Local, O=LampControll, C=CH" >/dev/null
fi

echo "Signing ..."
"$BT/apksigner" sign \
  --ks "$KEYSTORE" \
  --ks-pass pass:lampcontroll \
  --key-pass pass:lampcontroll \
  --out LampControll.apk \
  build/aligned.apk

"$BT/apksigner" verify --print-certs LampControll.apk

echo
"$BT/aapt2" dump badging LampControll.apk | head -5
echo
echo "Built: $(pwd)/LampControll.apk"
