import ctypes as C
import pytest
import display
from display import Display,DEVMODE,INPUT,RemoteInput,move_display


def test_windows_abi():
    assert C.sizeof(DEVMODE)==220
    assert C.sizeof(INPUT)==40


def test_cannot_move_primary():
    d=Display("1","primary",True,0,0,1920,1080)
    with pytest.raises(ValueError):move_display(d,d,"right")


def test_failed_validation_never_applies(monkeypatch):
    calls=[]
    monkeypatch.setattr(display,"mode",lambda name:DEVMODE())
    monkeypatch.setattr(display.user32,"ChangeDisplaySettingsExW",lambda *args:calls.append(args[3]) or -2)
    with pytest.raises(OSError):move_display(Display("2","secondary",False,0,0,1280,720),Display("1","primary",True,0,0,1920,1080),"right")
    assert calls==[2]


def test_unicode_uses_utf16_surrogate_pairs(monkeypatch):
    calls=[]
    monkeypatch.setattr(display,"send_inputs",lambda values:calls.extend(values))
    remote=RemoteInput(None);remote.text("А🙂")
    assert len(calls)==6
    assert [i.ki.wScan for i in calls[::2]]==[0x410,0xd83d,0xde42]


def test_release_held_modifiers_and_mouse(monkeypatch):
    calls=[]
    monkeypatch.setattr(display,"send_inputs",lambda values:calls.extend(values))
    remote=RemoteInput(None);remote.buttons.add("left");remote.keys.add("ctrl");remote.release()
    assert not remote.buttons and not remote.keys
    assert calls[0].mi.dwFlags==4
    assert calls[1].ki.wVk==17 and calls[1].ki.dwFlags==2
