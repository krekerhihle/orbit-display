# Third-party components and provenance

Orbit Display's original source is provided under GPL-3.0 (see LICENSE).

## Runtime components

| Component | Version | License / source |
|---|---|---|
| CPython | 3.12.14 | PSF; https://www.python.org/downloads/source/ |
| PySide6-Essentials / Shiboken6 / Qt | 6.10.2 | LGPL-3.0 / GPL alternatives; https://download.qt.io/official_releases/QtForPython/pyside6/PySide6-6.10.2-src/ and https://download.qt.io/archive/qt/6.10/6.10.2/ |
| Pillow | 12.1.0 | HPND; https://github.com/python-pillow/Pillow/tree/12.1.0 |
| mss | 10.1.0 | MIT; https://github.com/BoboTiG/python-mss/tree/v10.1.0 |
| DXcam | 0.3.0 | MIT; https://github.com/ra1nty/DXcam |
| NumPy | 2.3.5 | BSD-3-Clause and bundled library notices; https://github.com/numpy/numpy/tree/v2.3.5 |
| comtypes | 1.4.17 | MIT; https://github.com/enthought/comtypes |
| PyWinRT | runtime 4.0.3, SDK bindings 4!10.0.28000.2705, interop 4.0.0/4.1.0 | MIT; https://github.com/pywinrt/pywinrt |
| cryptography | 46.0.5 | Apache-2.0 / BSD; https://github.com/pyca/cryptography/tree/46.0.5 |
| cffi | 2.1.1 | MIT; https://foss.heptapod.net/pypy/cffi |
| PyInstaller bootloader | 6.19.0 | GPL-2.0 with bootloader exception; https://github.com/pyinstaller/pyinstaller/tree/v6.19.0 |

Windows distribution uses shared Qt libraries in `_internal`; they are not statically linked. Those libraries can be replaced by compatible modified builds. Relevant installed license/notice files are copied into `licenses/`. Python source and build instructions for Orbit are included separately. See the respective upstream source distributions for third-party source and complete notices.

## Optional USB and virtual display components

**Android SDK platform-tools 37.0.1**: official unmodified Google archive, obtained from https://dl.google.com/android/repository/platform-tools_r37.0.1-win.zip . Its full `NOTICE.txt` is kept with the files. ADB source: https://android.googlesource.com/platform/packages/modules/adb/ . This package also contains other SDK utilities; Orbit invokes only `adb.exe` with device listing and `reverse` arguments.

**Virtual Driver Control 25.7.23**: official unmodified distribution from https://github.com/VirtualDrivers/Virtual-Display-Driver/releases/tag/25.7.23 . Original archive: https://github.com/VirtualDrivers/Virtual-Display-Driver/releases/download/25.7.23/VDD.Control.25.7.23.zip . Project source at the release tag: https://github.com/VirtualDrivers/Virtual-Display-Driver/tree/25.7.23 . The upstream license and source archive accompany the third-party package. Its application and driver catalogs are signed by SignPath Foundation; Windows Authenticode validation returned `Valid` in this environment. This does not constitute a hardware compatibility test. Orbit does not install the driver or modify the certificate store automatically.


## Video runtime added in 0.3

PyAV 16.1.0 (BSD-3-Clause), official Windows wheel from PyPI; source: https://github.com/PyAV-Org/PyAV/tree/v16.1.0 . Its bundled shared FFmpeg 8.0.1 libraries and codec DLLs remain replaceable in `_internal/av.libs`. The vendor build manifest, dependency versions, source URLs, checksums and patches are in the included `pyav-ffmpeg-build-8.0.1-3.zip`: https://github.com/PyAV-Org/pyav-ffmpeg/tree/8.0.1-3 . Full dependency notices and sources accompany the vendor source material. FFmpeg is LGPL/GPL depending on enabled components; x264/x265 are GPL components. Orbit source is GPL-3.0.

H.264 encoder selection tries NVIDIA NVENC (packed RGB, low-delay preset), then Intel Quick Sync with zero B frames and one asynchronous slot, then falls back to x264 ultrafast/zerolatency. Android uses framework MediaCodec; no third-party decoder binary is bundled in the APK. Inno Setup 6.7.3 builds the installer; its compiler is a build dependency, not installed with Orbit.
