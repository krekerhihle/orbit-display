# Build Orbit Display

## Windows

Use 64-bit Python 3.12 on Windows 10/11:

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements-build.txt
.venv\Scripts\python.exe -m pytest tests -q
.venv\Scripts\python.exe desktop\app.py
.\build-windows.ps1 -Python "$PWD\.venv\Scripts\python.exe"
```

The portable EXE and its shared libraries are in `dist/OrbitDisplay/`. Keep `_internal` beside the EXE. To reproduce the complete distribution, copy unmodified Android platform-tools into `dist/OrbitDisplay/tools/platform-tools/` and the official VDD Control package into `dist/OrbitDisplay/tools/Virtual-Driver-Control/`. Include original third-party notices and `THIRD_PARTY.md`.

Optional packaged smoke test (starts no server and changes no display settings):

```powershell
dist\OrbitDisplay\OrbitDisplay.exe --smoke-test "$PWD\build\smoke.json"
```

## Android (no Gradle required)

This client uses only Android framework APIs; it has no third-party Java dependencies. Install/extract the official build toolchain in this layout:

```text
toolchain/
  jdk/jdk-17.../bin/javac.exe
  platform/android-35/android.jar
  build-tools/android-15/aapt2.exe
  build-tools/android-15/d8.bat
  build-tools/android-15/apksigner.bat
```

The names of the first child directory under each toolchain subdirectory are discovered automatically. Use exactly one version in each. Tested toolchain:

- Eclipse Temurin JDK 17.0.20.1+1, Windows x64 (Adoptium API).
- Google `platform-35_r02.zip`, SHA-1 `0bb560a90a7a2cbd0dd8348224d518b638fe7949`.
- Google `build-tools_r35_windows.zip`, SHA-1 `af059bb67cf7786f45ee0db85e2d24985df1b4b6`.
- Runtime USB helper: `platform-tools_r37.0.1-win.zip`, SHA-1 `e03e78b1d80b396f1c3358e31251cb31740e1110`.

SDK archive URLs and checksums are published in https://dl.google.com/android/repository/repository2-1.xml . Review the applicable SDK license before using the SDK.

```powershell
.\build-android.ps1 -ToolchainRoot C:\path\to\toolchain
```

The script compiles resources with aapt2, Java with javac, bytecode with D8, then zipaligns and signs the APK. The first build creates a **development** signing key under the toolchain directory, outside the source tree. Preserve that key for upgrade compatibility. It is not included in the source ZIP. For store publication, replace the development signing step with a private release keystore managed by the owner. Default development key alias/password follow Android conventions; they are not production credentials.

The packaged stream check starts a server on an ephemeral **loopback-only** port and validates 12 real captured frames at up to Full HD, without saving pixels or sending input:

```powershell
dist\OrbitDisplay\OrbitDisplay.exe --stream-smoke "$PWD\build\stream-smoke.json"
```

GPU capture uses DXcam 0.3.0 with its NumPy processor, not OpenCV. WinRT namespaces must be collected because that backend imports bindings dynamically. The build script sanitizes PATH to prevent unrelated ICU DLLs from being bundled. It also preserves additional TLS trust-policy data if the Python distribution supplies it.

## Protocol

TLS 1.2 or newer on TCP 48620. Android 0.1 negotiates TLS 1.2. Each record: 4-byte unsigned big-endian length (includes kind byte), `J` + UTF-8 JSON or `F` + JPEG bytes. Maximum incoming command 32768 bytes including kind; maximum frame 16 MiB. Authentication: `{"type":"auth","version":1,"pin":"six digits","name":"client"}`. Server responds with `ready` and monitor dimensions/permissions or `error`. Auth is sent only after certificate fingerprint comparison. Host permits five incoming authentication attempts per minute globally; pairing PIN expires after 10 minutes. No remote HTTP endpoint exists.

The v1 authentication object now optionally includes `frame_ack_v2: true` and `refresh_hz`. When negotiated, `G` records contain an 8-byte unsigned big-endian sequence number followed by JPEG. At most two JPEG records may be unacknowledged; H.264 permits four to accommodate hardware decoder startup. Client ACK is `{"type":"ack","seq":N,"presented":true}` after its Canvas draw call; replacing a pending frame uses `presented:false`. Unknown/duplicate ACKs cannot release capacity. Old clients still receive `F` JPEG and use one frame in flight. New clients also accept `F` from old servers.

The client sends `{"type":"refresh","hz":actualDisplayHz}` every second (also serves as a heartbeat). The server targets the minimum of source display Hz, client-reported actual Hz and requested FPS (Auto defaults to a 60 FPS cap). Only finite refresh rates in (1,500] are accepted; invalid rates fall back to 60. This is a rate limit, not a throughput promise. A nonblocking TLS wrapper serializes individual OpenSSL calls and waits outside the lock, permitting safe full-duplex frame/ACK traffic.

Read timeouts and shutdown release held mouse/keyboard state. Pointer positions are normalized in the displayed image rectangle, excluding letterboxing, and mapped to the selected Windows monitor's native geometry.

## Project structure

- `desktop/app.py`: Qt desktop UI and explicit session controls.
- `desktop/display.py`: Windows display placement and input API bindings.
- `desktop/server.py`: TLS pairing, capture, encoding and permissions.
- `desktop/capture.py`: exact output matching, GPU capture, GDI fallback.
- `desktop/flow.py`, `desktop/tls_channel.py`: bounded frame acknowledgements and serialized nonblocking TLS operations.
- `desktop/integrations.py`: Beamer launcher and USB ADB helper.
- `android/src/ua/orbit/display/MainActivity.java`: native Android UI, pinned TLS client, decoder and touch input.
- `tests/`: protocol/security/lifecycle tests using synthetic images and mocked input; never type into the user's applications.

## Version 0.3: installer and video

PyAV 16.1.0 is pinned in requirements.txt and collected with its codec DLLs by PyInstaller. Source modules video.py, capture.py and flow.py implement H.264, capture recovery and bounded pacing. H packets carry a uint64 big-endian sequence followed by one Annex B H.264 access unit. The client opts in with h264=true and frame_ack_v2=true; ready reports codec and encoded dimensions. Old clients retain F/G JPEG packets. H.264 ACKs follow releaseOutputBuffer to Surface, not network receipt. MediaCodec surfaces, codec threads and temporary Windows timer resolution are released at session end.

Build the installer after assembling the distribution and notices:

```powershell
ISCC.exe /DBundleDir="C:\absolute\dist\OrbitDisplay" /DDeliverables="C:\absolute\outputs" installer.iss
```

The destination page is always shown. Install/uninstall are per-user; drivers are installed manually through the wizard. For frozen video validation use `OrbitDisplay.exe --stream-smoke output.json`; it exercises both JPEG and H.264 over local TLS using the current main display, without saving pixels or injecting input.

## Signed updates

Release assets are described by update.json: base64 UTF-8 JSON payload and a base64 RSA PKCS#1 v1.5 SHA-256 signature. Clients embed only the public key. The payload contains windows {version,url,size,sha256} and android {versionCode,version,url,size,sha256}. Keep the private signing key and Android keystore outside the repository. Never commit either. The signing tool accepts an explicit private-key path; upload its output with both matching binaries. Windows and Android download only a newer version, verify the signature and artifact hash, and request installation without interrupting a stream. Android installation requires the normal system permission/confirmation.
