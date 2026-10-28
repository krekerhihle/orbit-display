import ctypes as C
import pytest
import display
from display import Display,DEVMODE,supported_modes,set_display_mode


def devmode(w=1280,h=720,hz=60,x=1920,y=180):
    m=DEVMODE();m.dmSize=C.sizeof(m);m.dmBitsPerPel=32
    m.dmPelsWidth=w;m.dmPelsHeight=h;m.dmDisplayFrequency=hz;m.dmPosition.x=x;m.dmPosition.y=y
    return m


def test_only_advertised_progressive_32bit_modes(monkeypatch):
    modes=[devmode(1920,1080,60),devmode(1920,1080,144),devmode(1920,1080,144),devmode(1920,1080,120),devmode(640,480,60)]
    modes[3].dmDisplayFlags=2;modes[4].dmBitsPerPel=16
    def enum(name,index,ptr):
        if index>=len(modes):return 0
        C.memmove(ptr,C.byref(modes[index]),C.sizeof(DEVMODE));return 1
    monkeypatch.setattr(display.user32,'EnumDisplaySettingsW',enum)
    assert supported_modes('test')==[(1920,1080,60),(1920,1080,144)]


@pytest.fixture
def api(monkeypatch):
    primary=Display('main','Main',True,0,0,1920,1080)
    second=Display('second','Virtual',False,1920,180,1280,720)
    state={'current':devmode(),'calls':[],'test_error':0,'apply_error':0,'wrong':False}
    monkeypatch.setattr(display,'displays',lambda:[primary,second])
    monkeypatch.setattr(display,'supported_modes',lambda name:[(1280,720,60),(1920,1080,60),(1920,1080,120),(1920,1080,144)])
    monkeypatch.setattr(display,'mode',lambda name:DEVMODE.from_buffer_copy(state['current']))
    def change(name,ptr,handle,flags,unused):
        value=DEVMODE.from_buffer_copy(ptr._obj)
        state['calls'].append((flags,value))
        if flags==2:return state['test_error']
        if state['apply_error']:return state['apply_error']
        if not state['wrong']:state['current']=value
        return 0
    monkeypatch.setattr(display.user32,'ChangeDisplaySettingsExW',change)
    return primary,second,state


def test_fullhd_maximum_refresh_and_placement(api):
    p,s,state=api
    original=set_display_mode(s,p,1920,1080,0,'top')
    assert original.dmPelsWidth==1280
    actual=state['current']
    assert (actual.dmPelsWidth,actual.dmPelsHeight,actual.dmDisplayFrequency)==(1920,1080,144)
    assert (actual.dmPosition.x,actual.dmPosition.y)==(0,-1080)
    assert [flag for flag,_ in state['calls']]==[2,0]


def test_explicit_rate_instead_of_maximum(api):
    p,s,state=api;set_display_mode(s,p,1920,1080,120,'left')
    assert state['current'].dmDisplayFrequency==120
    assert state['current'].dmPosition.x==-1920


@pytest.mark.parametrize('w,h,hz',[(3840,2160,60),(1920,1080,240)])
def test_unsupported_mode_does_not_change_windows(api,w,h,hz):
    p,s,state=api
    with pytest.raises(ValueError):set_display_mode(s,p,w,h,hz,'right')
    assert state['calls']==[]


def test_driver_rejection_never_applies(api):
    p,s,state=api;state['test_error']=-2
    with pytest.raises(OSError):set_display_mode(s,p,1920,1080,0,'right')
    assert [f for f,_ in state['calls']]==[2]


def test_silent_wrong_mode_restores_original(api):
    p,s,state=api;state['wrong']=True
    with pytest.raises(OSError):set_display_mode(s,p,1920,1080,0,'right')
    assert [f for f,_ in state['calls']]==[2,0,0]
    assert state['calls'][-1][1].dmPelsWidth==1280


def test_primary_is_protected(api):
    p,s,state=api
    with pytest.raises(ValueError):set_display_mode(p,p,1920,1080,0,'right')
    assert state['calls']==[]


def test_does_not_overlap_another_screen(api,monkeypatch):
    p,s,state=api
    monkeypatch.setattr(display,'displays',lambda:[p,s,Display('third','Third',False,1920,0,800,600)])
    with pytest.raises(ValueError):set_display_mode(s,p,1920,1080,0,'right')
    assert state['calls']==[]
