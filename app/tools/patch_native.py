"""Re-apply the native config the FlutterFlow export does not carry (master prompt Phase 4.4). Idempotent —
run after every `flutterflow export-code`:

    python app/tools/patch_native.py [app/export]

Android: RECORD_AUDIO / CAMERA / MODIFY_AUDIO_SETTINGS permissions, cleartext HTTP+WS to the laptop
(usesCleartextTraffic), minSdk 24. iOS: mic/camera/local-network usage strings and ATS exception for the
plain-http laptop server.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

export = Path(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).resolve().parents[1] / "export").resolve()
changed: list[str] = []


def patch(path: Path, fn) -> None:
    txt = path.read_text(encoding="utf-8")
    new = fn(txt)
    if new != txt:
        path.write_text(new, encoding="utf-8")
        changed.append(str(path.relative_to(export)))


def manifest(t: str) -> str:
    perms = ["android.permission.RECORD_AUDIO", "android.permission.CAMERA", "android.permission.MODIFY_AUDIO_SETTINGS", "android.permission.INTERNET", "android.permission.ACCESS_NETWORK_STATE"]
    add = "".join(f'    <uses-permission android:name="{p}"/>\n' for p in perms if f'android:name="{p}"' not in t)
    if add:
        t = re.sub(r"(<manifest[^>]*>\n)", lambda m: m.group(1) + add, t, count=1)
    if "android:usesCleartextTraffic" not in t:
        t = t.replace("<application\n", '<application\n        android:usesCleartextTraffic="true"\n', 1)
    # the QR scanner needs a camera feature declaration that is not required (emulator has no camera)
    if 'android.hardware.camera' not in t:
        t = re.sub(r"(<uses-permission android:name=\"android.permission.CAMERA\"/>\n)", lambda m: m.group(1) + '    <uses-feature android:name="android.hardware.camera" android:required="false"/>\n', t, count=1)
    return t


def gradle(t: str) -> str:
    return re.sub(r"minSdkVersion\s+\d+", "minSdkVersion 24", t)


def plist(t: str) -> str:
    entries = {
        "NSMicrophoneUsageDescription": "<string>Interview Cracker listens to your answers during a mock interview. Audio goes only to your own laptop.</string>",
        "NSCameraUsageDescription": "<string>Scan the pairing QR code shown by the laptop.</string>",
        "NSLocalNetworkUsageDescription": "<string>Connects to the interview server running on your laptop over the local hotspot.</string>",
        "NSAppTransportSecurity": "<dict><key>NSAllowsArbitraryLoads</key><true/><key>NSAllowsLocalNetworking</key><true/></dict>",
    }
    add = "".join(f"\t<key>{k}</key>\n\t{v}\n" for k, v in entries.items() if f"<key>{k}</key>" not in t)
    if add:
        t = t.replace("</dict>\n</plist>", add + "</dict>\n</plist>", 1)
    return t


patch(export / "android" / "app" / "src" / "main" / "AndroidManifest.xml", manifest)
patch(export / "android" / "app" / "build.gradle", gradle)
patch(export / "ios" / "Runner" / "Info.plist", plist)

def pubspec(t: str) -> str:
    # FlutterFlow generates for Flutter 3.38 (intl 0.20.2); a newer local Flutter's flutter_localizations wants intl ^0.20.3
    return re.sub(r"^(\s+intl:\s*)0\.20\.2\s*$", r"\g<1>^0.20.2", t, flags=re.M)


patch(export / "pubspec.yaml", pubspec)


def gradle_wrapper(t: str) -> str:
    # FlutterFlow's template ships gradle-8.12; Flutter 3.47's Gradle plugin refuses anything below 8.14.0
    return re.sub(r"gradle-8\.(?:[0-9]|1[0-3])(?:\.\d+)?-(all|bin)\.zip", "gradle-8.14.3-bin.zip", t)


patch(export / "android" / "gradle" / "wrapper" / "gradle-wrapper.properties", gradle_wrapper)


def agp_version(t: str) -> str:
    # Flutter 3.47's Gradle plugin refuses the template's AGP 8.9.1 (minimum 8.11.1); Kotlin 2.1.0 / compileSdk 36 / NDK 28 are accepted
    return re.sub(r'(id\s+"com\.android\.application"\s+version\s+")8\.(?:[0-9]|10|11\.0)(?:\.\d+)?(")', r"\g<1>8.11.1\g<2>", t)


patch(export / "android" / "settings.gradle", agp_version)

print("patched:", ", ".join(changed) if changed else "nothing (already applied)")
