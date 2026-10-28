"""Windows display topology and explicit input injection; no driver installation."""
import ctypes as C
from ctypes import wintypes as W
from dataclasses import dataclass
import math
from protocol import placement

user32 = C.WinDLL("user32", use_last_error=True)


class POINTL(C.Structure):
    _fields_ = [("x", W.LONG), ("y", W.LONG)]


class DEVMODE(C.Structure):
    _fields_ = [("dmDeviceName", W.WCHAR * 32), ("dmSpecVersion", W.WORD),
        ("dmDriverVersion", W.WORD), ("dmSize", W.WORD), ("dmDriverExtra", W.WORD),
        ("dmFields", W.DWORD), ("dmPosition", POINTL), ("dmDisplayOrientation", W.DWORD),
        ("dmDisplayFixedOutput", W.DWORD), ("dmColor", W.SHORT), ("dmDuplex", W.SHORT),
        ("dmYResolution", W.SHORT), ("dmTTOption", W.SHORT), ("dmCollate", W.SHORT),
        ("dmFormName", W.WCHAR * 32), ("dmLogPixels", W.WORD), ("dmBitsPerPel", W.DWORD),
        ("dmPelsWidth", W.DWORD), ("dmPelsHeight", W.DWORD), ("dmDisplayFlags", W.DWORD),
        ("dmDisplayFrequency", W.DWORD), ("dmICMMethod", W.DWORD), ("dmICMIntent", W.DWORD),
        ("dmMediaType", W.DWORD), ("dmDitherType", W.DWORD), ("dmReserved1", W.DWORD),
        ("dmReserved2", W.DWORD), ("dmPanningWidth", W.DWORD), ("dmPanningHeight", W.DWORD)]


class DEVICE(C.Structure):
    _fields_ = [("cb", W.DWORD), ("DeviceName", W.WCHAR * 32), ("DeviceString", W.WCHAR * 128),
        ("StateFlags", W.DWORD), ("DeviceID", W.WCHAR * 128), ("DeviceKey", W.WCHAR * 128)]


user32.EnumDisplayDevicesW.argtypes = [W.LPCWSTR, W.DWORD, C.POINTER(DEVICE), W.DWORD]
user32.EnumDisplaySettingsW.argtypes = [W.LPCWSTR, W.DWORD, C.POINTER(DEVMODE)]
user32.ChangeDisplaySettingsExW.argtypes = [W.LPCWSTR, C.POINTER(DEVMODE), W.HWND, W.DWORD, C.c_void_p]
user32.ChangeDisplaySettingsExW.restype = W.LONG


@dataclass
class Display:
    name: str
    title: str
    primary: bool
    x: int
    y: int
    width: int
    height: int
    hz: int = 60

    @property
    def rect(self):
        return self.x, self.y, self.width, self.height

    @property
    def capture(self):
        return dict(left=self.x, top=self.y, width=self.width, height=self.height)


def mode(name):
    value = DEVMODE()
    value.dmSize = C.sizeof(DEVMODE)
    if not user32.EnumDisplaySettingsW(name, 0xFFFFFFFF, C.byref(value)):
        raise OSError("Windows не повернула параметри дисплея")
    return value


def displays():
    result = []
    for index in range(32):
        dev = DEVICE()
        dev.cb = C.sizeof(DEVICE)
        if not user32.EnumDisplayDevicesW(None, index, C.byref(dev), 0):
            break
        if dev.StateFlags & 1 and not dev.StateFlags & 8:
            m = mode(dev.DeviceName)
            if m.dmPelsWidth and m.dmPelsHeight:
                result.append(Display(dev.DeviceName, dev.DeviceString, bool(dev.StateFlags & 4),
                    m.dmPosition.x, m.dmPosition.y, m.dmPelsWidth, m.dmPelsHeight, m.dmDisplayFrequency))
    return result


def supported_modes(name):
    """Only progressive, 32-bit modes advertised by this display's driver."""
    result = set()
    for index in range(4096):
        value = DEVMODE()
        value.dmSize = C.sizeof(DEVMODE)
        if not user32.EnumDisplaySettingsW(name, index, C.byref(value)): break
        if value.dmBitsPerPel >= 32 and not value.dmDisplayFlags & 2 and value.dmDisplayFrequency > 1:
            result.add((int(value.dmPelsWidth), int(value.dmPelsHeight), int(value.dmDisplayFrequency)))
    return sorted(result)


def set_display_mode(target, primary, width, height, hz, side):
    """Apply an advertised resolution/refresh and adjacent placement, restoring on failure."""
    if target.primary: raise ValueError("Основний екран не змінюється. Виберіть додатковий дисплей.")
    modes = supported_modes(target.name)
    rates = [f for w,h,f in modes if (w,h) == (width,height)]
    if not rates: raise ValueError(f"Драйвер не пропонує {width}×{height}. Додайте цей режим у Virtual Driver Control та оновіть список.")
    hz = max(rates) if hz == 0 else hz
    if hz not in rates: raise ValueError("Обрана частота недоступна для цієї роздільності.")
    original = mode(target.name)
    changed = DEVMODE.from_buffer_copy(original)
    changed.dmPelsWidth, changed.dmPelsHeight, changed.dmDisplayFrequency = width, height, hz
    changed.dmPosition.x, changed.dmPosition.y = placement(primary.rect, (0,0,width,height), side)
    proposed = (changed.dmPosition.x, changed.dmPosition.y, width, height)
    for other in displays():
        if other.name in (target.name,primary.name): continue
        x,y,w,h = proposed
        if x < other.x+other.width and x+w > other.x and y < other.y+other.height and y+h > other.y:
            raise ValueError("Це місце зайняте іншим дисплеєм. Виберіть інший бік.")
    changed.dmFields = 0x20 | 0x80000 | 0x100000 | 0x400000
    code = user32.ChangeDisplaySettingsExW(target.name,C.byref(changed),None,2,None)
    if code != 0: raise OSError(f"Windows відхилила режим {width}×{height} / {hz} Гц (код {code})")
    try:
        code = user32.ChangeDisplaySettingsExW(target.name,C.byref(changed),None,0,None)
        if code != 0: raise OSError(f"Не вдалося застосувати режим (код {code})")
        actual = mode(target.name)
        if (actual.dmPelsWidth,actual.dmPelsHeight,actual.dmDisplayFrequency,actual.dmPosition.x,actual.dmPosition.y) != (width,height,hz,changed.dmPosition.x,changed.dmPosition.y):
            raise OSError("Windows застосувала інший режим; повертаю попередній.")
    except Exception as exc:
        try: restore_display(target.name,original)
        except OSError as restore_error: raise OSError(f"{exc}\nНе вдалося відновити режим: {restore_error}") from exc
        raise
    return original


def move_display(target, primary, side):
    if target.primary:
        raise ValueError("Основний екран не переміщується")
    original = mode(target.name)
    changed = DEVMODE.from_buffer_copy(original)
    changed.dmPosition.x, changed.dmPosition.y = placement(primary.rect, target.rect, side)
    changed.dmFields = 0x20  # DM_POSITION only; preserve resolution and refresh rate.
    code = user32.ChangeDisplaySettingsExW(target.name, C.byref(changed), None, 2, None)
    if code != 0:
        raise OSError(f"Windows відхилила розташування (код {code})")
    code = user32.ChangeDisplaySettingsExW(target.name, C.byref(changed), None, 0, None)
    if code != 0:
        raise OSError(f"Не вдалося перемістити екран (код {code})")
    return original


def restore_display(name, original):
    code = user32.ChangeDisplaySettingsExW(name, C.byref(original), None, 0, None)
    if code != 0:
        raise OSError(f"Не вдалося відновити екран (код {code})")


ULONG_PTR = C.c_size_t
class MOUSEINPUT(C.Structure):
    _fields_ = [("dx", W.LONG), ("dy", W.LONG), ("mouseData", W.DWORD), ("dwFlags", W.DWORD), ("time", W.DWORD), ("dwExtraInfo", ULONG_PTR)]
class KEYBDINPUT(C.Structure):
    _fields_ = [("wVk", W.WORD), ("wScan", W.WORD), ("dwFlags", W.DWORD), ("time", W.DWORD), ("dwExtraInfo", ULONG_PTR)]
class INPUTUNION(C.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT)]
class INPUT(C.Structure):
    _anonymous_ = ("data",)
    _fields_ = [("type", W.DWORD), ("data", INPUTUNION)]

user32.SendInput.argtypes = [W.UINT, C.POINTER(INPUT), C.c_int]
user32.SendInput.restype = W.UINT
user32.SetCursorPos.argtypes = [C.c_int, C.c_int]


def send_inputs(values):
    arr = (INPUT * len(values))(*values)
    if user32.SendInput(len(values), arr, C.sizeof(INPUT)) != len(values):
        raise OSError("Windows заблокувала введення. UAC та підвищені вікна не підтримуються.")


class RemoteInput:
    KEYS = {"enter":13, "escape":27, "tab":9, "backspace":8, "delete":46,
        "left":37, "up":38, "right":39, "down":40, "ctrl":17, "alt":18,
        "shift":16, "win":91, "home":36, "end":35, "pageup":33, "pagedown":34,
        **{chr(i): i for i in range(65, 91)}, **{str(i):48+i for i in range(10)}}

    def __init__(self, screen):
        self.screen = screen
        self.buttons = set()
        self.keys = set()

    def mouse(self, data):
        x, y = float(data.get("x", 0)), float(data.get("y", 0))
        if not math.isfinite(x) or not math.isfinite(y):
            raise ValueError("Invalid pointer")
        x, y = max(0, min(1, x)), max(0, min(1, y))
        user32.SetCursorPos(self.screen.x + round(x*(self.screen.width-1)), self.screen.y + round(y*(self.screen.height-1)))
        action = data.get("action", "move")
        button = data.get("button", "left")
        if action in ("down", "up") and button in ("left", "right"):
            flag = {("left","down"):2, ("left","up"):4, ("right","down"):8, ("right","up"):16}[button,action]
            send_inputs([INPUT(type=0, mi=MOUSEINPUT(dwFlags=flag))])
            if action == "down": self.buttons.add(button)
            else: self.buttons.discard(button)

    def key(self, data):
        key = data.get("key")
        if key not in self.KEYS: return
        down = data.get("down") is True
        extended = key in {"delete","left","up","right","down","home","end","pageup","pagedown","win"}
        send_inputs([INPUT(type=1, ki=KEYBDINPUT(wVk=self.KEYS[key], dwFlags=(0 if down else 2) | int(extended)))])
        if down: self.keys.add(key)
        else: self.keys.discard(key)

    def text(self, text):
        if not isinstance(text, str) or len(text) > 4096: raise ValueError("Text too long")
        raw = text.encode("utf-16-le")
        values = []
        for i in range(0, len(raw), 2):
            unit = int.from_bytes(raw[i:i+2], "little")
            values.extend([INPUT(type=1, ki=KEYBDINPUT(wScan=unit, dwFlags=4)), INPUT(type=1, ki=KEYBDINPUT(wScan=unit, dwFlags=6))])
        if values: send_inputs(values)

    def scroll(self, amount):
        amount = max(-1200, min(1200, int(amount)))
        send_inputs([INPUT(type=0, mi=MOUSEINPUT(mouseData=amount & 0xffffffff, dwFlags=0x800))])

    def release(self):
        for button in list(self.buttons):
            try: send_inputs([INPUT(type=0, mi=MOUSEINPUT(dwFlags=4 if button == "left" else 16))])
            except OSError: pass
        self.buttons.clear()
        for key in list(self.keys):
            try: self.key({"key":key, "down":False})
            except OSError: pass
        self.keys.clear()
