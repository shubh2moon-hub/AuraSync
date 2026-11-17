#!/usr/bin/env bash
# Builds and signs the APK with the plain Android SDK tools (no Gradle needed).
set -euo pipefail
cd "$(dirname "$0")"
SDK=/c/Android/Sdk
BT=$SDK/build-tools/36.0.0
JAR=$SDK/platforms/android-36/android.jar
rm -rf build && mkdir -p build/gen build/classes build/dex build/assets
# ship only what the phone renders (not the 4K masters / PC images that live in library/packs)
for d in assets/packs/*/; do
  id=$(basename "$d"); mkdir -p "build/assets/packs/$id"
  for f in meta.json phone_base.jpg phone_light.jpg phone_preview.jpg phone_land_base.jpg phone_land_light.jpg; do
    [ -f "$d$f" ] && cp "$d$f" "build/assets/packs/$id/$f"
  done
done
[ -f assets/packs/library.json ] && cp assets/packs/library.json build/assets/packs/
"$BT/aapt2.exe" compile --dir res -o build/res.zip
"$BT/aapt2.exe" link -I "$JAR" --manifest AndroidManifest.xml --java build/gen \
  -A build/assets --min-sdk-version 26 --target-sdk-version 34 -o build/unsigned.apk build/res.zip
javac -encoding UTF-8 --release 11 -classpath "$JAR" -d build/classes \
  $(find src build/gen -name '*.java') 2>&1 | grep -v 'bootstrap\|^1 warning\|-source 11' || true
"$BT/d8.bat" --release --min-api 26 --lib "$JAR" --output build/dex $(find build/classes -name '*.class')
python -c "import zipfile; z=zipfile.ZipFile('build/unsigned.apk','a'); z.write('build/dex/classes.dex','classes.dex'); z.close()"
"$BT/zipalign.exe" -f -p 4 build/unsigned.apk build/aligned.apk
if [ ! -f aura-debug.keystore ]; then
  keytool -genkeypair -keystore aura-debug.keystore -storepass android -keypass android -alias aura \
    -keyalg RSA -keysize 2048 -validity 10000 -dname "CN=Aura Phone Sync" >/dev/null 2>&1
fi
"$BT/apksigner.bat" sign --ks aura-debug.keystore --ks-pass pass:android --key-pass pass:android \
  --out AuraPhoneSync.apk build/aligned.apk
"$BT/apksigner.bat" verify AuraPhoneSync.apk && ls -la AuraPhoneSync.apk
