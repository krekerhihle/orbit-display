from pathlib import Path
import subprocess
import sys

USB_READY = "USB готовий. На Android оберіть USB (127.0.0.1)."


def bundle_root():
    return Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parents[1]


def prepare_usb():
    adb = bundle_root()/"tools"/"platform-tools"/"adb.exe"
    if not adb.exists(): raise OSError("Не знайдено tools/platform-tools/adb.exe. Перевстановіть Orbit або розпакуйте повний Windows-архів.")
    def run(args):
        r = subprocess.run([str(adb), *args], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=20,
            creationflags=subprocess.CREATE_NO_WINDOW)
        if r.returncode: raise OSError(r.stderr.strip() or r.stdout.strip())
        return r.stdout
    rows = [line.split() for line in run(["devices"]).splitlines()[1:] if line.strip()]
    devices = [r[0] for r in rows if len(r)>1 and r[1] == "device" and ":" not in r[0] and not r[0].startswith("emulator-")]
    if not devices: raise OSError("Під'єднайте USB, увімкніть налагодження через USB і підтвердьте доступ на телефоні.")
    if len(devices) != 1: raise OSError("Залиште підключеним один Android-пристрій.")
    run(["-s", devices[0], "reverse", "tcp:48620", "tcp:48620"])
    return USB_READY
