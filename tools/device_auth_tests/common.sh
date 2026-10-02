#!/usr/bin/env bash
# Shared environment for the LittleNet Parent device-auth emulator harness.
# Source this file; do not execute it directly.
#
# Required environment (or defaults below):
#   ANDROID_SDK_ROOT  - path to the Android SDK (default: ~/workspace/android-sdk)
#   AVD_API           - API level for the test AVDs (default: 34)
#
# No secrets are read or written by any script in this directory.

if [ -n "${DEVICE_AUTH_ENV_LOADED:-}" ]; then
  return 0 2>/dev/null || exit 0
fi
DEVICE_AUTH_ENV_LOADED=1

export ANDROID_SDK_ROOT="${ANDROID_SDK_ROOT:-$HOME/workspace/android-sdk}"
export ANDROID_AVD_HOME="${ANDROID_AVD_HOME:-$HOME/.android/avd}"
export AVD_API="${AVD_API:-34}"
export PATH="$ANDROID_SDK_ROOT/cmdline-tools/latest/bin:$ANDROID_SDK_ROOT/platform-tools:$ANDROID_SDK_ROOT/emulator:$PATH"

# System image used by all three profiles. google_apis carries the
# biometric HAL bits the fingerprint simulator needs.
export SYSIMG_PKG="system-images;android-${AVD_API};google_apis;x86_64"

ADB="${ADB:-adb}"
EMULATOR_BIN="${EMULATOR_BIN:-emulator}"
AVDMANAGER="${AVDMANAGER:-avdmanager}"

die() { echo "ERROR: $*" >&2; exit 1; }

require_bins() {
  command -v "$ADB" >/dev/null || die "adb not found (tried: $ADB). Install platform-tools."
}

# Wait until the device at $1 (default: emulator-5554) reports boot completed.
wait_for_boot() {
  local serial="${1:-emulator-5554}"
  local tries=0
  echo "Waiting for $serial to boot..."
  while [ "$tries" -lt 60 ]; do
    if [ "$("$ADB" -s "$serial" shell getprop sys.boot_completed 2>/dev/null | tr -d '\r')" = "1" ]; then
      echo "Boot completed."
      "$ADB" -s "$serial" wait-for-device >/dev/null 2>&1
      sleep 5
      return 0
    fi
    sleep 10
    tries=$((tries + 1))
  done
  die "Timed out waiting for $serial to boot."
}

# Create an AVD if it does not already exist.
ensure_avd() {
  local name="$1"   # e.g. ln_biometric
  local device="${2:-pixel_7}"
  if [ -d "$ANDROID_AVD_HOME/${name}.avd" ]; then
    echo "AVD '$name' already exists, reusing."
    return 0
  fi
  echo "Creating AVD '$name' (API $AVD_API, $SYSIMG_PKG)..."
  echo "no" | "$AVDMANAGER" create avd \
    --name "$name" \
    --package "$SYSIMG_PKG" \
    --device "$device" \
    --force >/dev/null || die "avdmanager failed to create '$name'"
  # Fingerprint sensor on for every profile (harmless when nothing is enrolled).
  {
    echo "hw.fingerprint=yes"
  } >> "$ANDROID_AVD_HOME/${name}.avd/config.ini"
  echo "AVD '$name' created."
}

# Boot an AVD headlessly in the background; prints nothing on stdout except status.
boot_avd_bg() {
  local name="$1"
  local port="${2:-5554}"
  echo "Booting AVD '$name' on emulator-$port ..."
  nohup "$EMULATOR_BIN" -avd "$name" \
    -port "$port" \
    -no-window -no-audio -no-boot-anim \
    -gpu swiftshader_indirect \
    > "/tmp/emulator-${name}.log" 2>&1 &
  echo $! > "/tmp/emulator-${name}.pid"
  wait_for_boot "emulator-$port"
}

serial_for() { echo "emulator-${1:-5554}"; }
