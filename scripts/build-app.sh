#!/bin/bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MODULE="${1:?Usage: scripts/build-app.sh sky-shortcut|share-indicator}"
case "$MODULE" in sky-shortcut|share-indicator) ;; *) echo 'Unknown app module' >&2; exit 2;; esac
SDK="${ANDROID_SDK_ROOT:-${ANDROID_HOME:-}}"
: "${SDK:?Set ANDROID_SDK_ROOT to an Android SDK directory}"
TOOLS="$SDK/build-tools/${BUILD_TOOLS_VERSION:-34.0.0}"
PLATFORM="$SDK/platforms/android-${ANDROID_API:-32}/android.jar"
APP="$ROOT/$MODULE"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
mkdir -p "$WORK/classes" "$WORK/dex" "$APP/build" "$APP/.local"
"$TOOLS/aapt" package -f -M "$APP/AndroidManifest.xml" -S "$APP/res" -I "$PLATFORM" -F "$WORK/unsigned.apk"
javac --release 8 -classpath "$PLATFORM" -d "$WORK/classes" "$APP"/src/lab/tv/*/*.java
"$TOOLS/d8" --min-api 26 --lib "$PLATFORM" --output "$WORK/dex" "$WORK"/classes/lab/tv/*/*.class
(cd "$WORK/dex" && zip -q "$WORK/unsigned.apk" classes.dex)
"$TOOLS/zipalign" -f 4 "$WORK/unsigned.apk" "$WORK/aligned.apk"
KEY="$APP/.local/debug.keystore"
if [ ! -f "$KEY" ]; then
 keytool -genkeypair -keystore "$KEY" -storepass android -keypass android -alias local \
  -dname 'CN=Local TV Development' -keyalg RSA -validity 10000 >/dev/null 2>&1
 chmod 600 "$KEY"
fi
"$TOOLS/apksigner" sign --ks "$KEY" --ks-key-alias local --ks-pass pass:android --out "$APP/build/$MODULE.apk" "$WORK/aligned.apk"
"$TOOLS/apksigner" verify "$APP/build/$MODULE.apk"
printf 'Built %s\n' "$APP/build/$MODULE.apk"
