from types import SimpleNamespace
from PIL import Image
import capture
from display import Display


def test_gpu_output_must_match_name_and_geometry():
    screen=Display('display2','Virtual',False,-1920,0,1920,1080)
    output=SimpleNamespace(devicename='display1',attached_to_desktop=True,desc=SimpleNamespace(DesktopCoordinates=SimpleNamespace(left=-1920,top=0,right=0,bottom=1080)))
    assert not capture.matches_output(output,screen)
    output.devicename='display2';assert capture.matches_output(output,screen)
    output.desc.DesktopCoordinates.right=1;assert not capture.matches_output(output,screen)


def test_gdi_fallback_captures_only_selected_rectangle(monkeypatch):
    seen=[]
    class GDI:
        def grab(self,rect):seen.append(rect);return SimpleNamespace(size=(2,2),bgra=b'\x01\x02\x03\xff'*4)
        def close(self):seen.append('closed')
    monkeypatch.setattr(capture.mss,'mss',GDI)
    screen=Display('display2','Virtual',False,-2,0,2,2)
    with capture.ScreenCapture(screen,fast=False) as stream:
        assert stream.frame().getpixel((0,0))==(3,2,1)
    assert seen==[screen.capture,'closed']


def test_failed_gpu_does_not_reuse_old_frame(monkeypatch):
    released=[]
    class GPU:
        def grab(self,**kw):raise OSError('device lost')
        def release(self):released.append(True)
    class GDI:
        def grab(self,rect):return SimpleNamespace(size=(2,2),bgra=b'\x04\x05\x06\xff'*4)
        def close(self):pass
    monkeypatch.setattr(capture.mss,'mss',GDI)
    stream=capture.ScreenCapture(Display('2','Virtual',False,0,0,2,2),False)
    stream.camera=GPU()
    assert stream.frame().getpixel((0,0))==(6,5,4)
    assert released==[True] and stream.backend=='GDI' and stream.camera is None
    stream.__exit__()


def test_initial_gpu_timeout_does_not_disable_acceleration(monkeypatch):
    import numpy as np
    class GPU:
        count=0
        def grab(self,**kw):
            self.count+=1
            return None if self.count==1 else np.zeros((2,2,3),dtype=np.uint8)
        def release(self):pass
    class GDI:
        def grab(self,rect):return SimpleNamespace(size=(2,2),bgra=b'\x04\x05\x06\xff'*4)
        def close(self):pass
    monkeypatch.setattr(capture.mss,'mss',GDI)
    stream=capture.ScreenCapture(Display('2','Virtual',False,0,0,2,2),False)
    stream.camera=GPU();stream.gpu_backend='GPU / DXGI';stream.gpu_cursor=False
    assert stream.frame().getpixel((0,0))==(6,5,4)
    assert stream.camera is not None
    assert stream.frame().getpixel((0,0))==(0,0,0) and stream.backend=='GPU / DXGI'
    stream.__exit__()
