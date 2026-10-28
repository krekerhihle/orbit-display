"""Exact-monitor GPU capture, with GDI fallback for unsupported virtual drivers."""
import logging
from PIL import Image
import mss


def matches_output(output, screen):
    rect = output.desc.DesktopCoordinates
    return (output.devicename == screen.name and output.attached_to_desktop and
        (rect.left,rect.top,rect.right-rect.left,rect.bottom-rect.top) == screen.rect)


class ScreenCapture:
    def __init__(self,screen,fast=True):
        self.screen,self.fast = screen,fast
        self.camera = self.gdi = self.com = None
        self.backend = 'GDI'
        self.cursor_embedded = False
        self.has_gpu_frame = False

    def __enter__(self):
        if self.fast:
            try:
                import comtypes
                comtypes.CoInitialize()
                self.com = comtypes
                # Enumerate afresh: a virtual monitor may have been added since app launch.
                # This adapter is intentionally pinned to DXcam 0.3.0.
                from dxcam import DXCamera
                from dxcam.core.device import Device
                from dxcam.core.output import Output
                from dxcam.util.io import enum_dxgi_adapters
                for adapter in enum_dxgi_adapters():
                    device = Device(adapter)
                    for native_output in device.enum_outputs():
                        output = Output(native_output)
                        if not matches_output(output,self.screen): continue
                        for backend in ('dxgi','winrt'):
                            try:
                                camera = DXCamera(output,device,None,output_color='RGB',max_buffer_len=2,backend=backend,processor_backend='numpy')
                                self.camera = camera
                                self.backend = 'GPU / ' + backend.upper()
                                self.cursor_embedded = backend == 'winrt'
                                self.gpu_backend,self.gpu_cursor = self.backend,self.cursor_embedded
                                return self
                            except Exception:
                                logging.info('Capture backend %s unavailable',backend,exc_info=True)
            except Exception:
                logging.info('GPU capture unavailable; using exact-rectangle GDI fallback',exc_info=True)
        self.gdi = mss.mss()
        return self

    def frame(self, changes_only=False):
        if self.camera:
            try:
                array = self.camera.grab(new_frame_only=changes_only)
                if array is not None:
                    frame = Image.fromarray(array)
                    if frame.size != (self.screen.width,self.screen.height):
                        raise OSError('GPU output dimensions changed')
                    self.backend,self.cursor_embedded=self.gpu_backend,self.gpu_cursor
                    self.has_gpu_frame=True
                    return frame
                if changes_only and self.has_gpu_frame:return None
            except Exception:
                logging.info('GPU capture failed; switching to GDI',exc_info=True)
                self.camera.release()
                self.camera = None
            # A fresh duplication session may have no frame yet. Capture this frame
            # with GDI, but retry the GPU next time instead of disabling it forever.
            self.backend,self.cursor_embedded = 'GDI',False
        if self.gdi is None:self.gdi=mss.mss()
        shot=self.gdi.grab(self.screen.capture)
        return Image.frombytes('RGB',shot.size,shot.bgra,'raw','BGRX')

    def changed_frame(self):
        return self.frame(changes_only=True)

    def __exit__(self,*args):
        try:
            if self.camera:self.camera.release()
            if self.gdi:self.gdi.close()
        finally:
            if self.com:self.com.CoUninitialize()
