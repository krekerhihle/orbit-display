"""Low-delay H.264 access units. No B frames, lookahead or encoder queue."""
from fractions import Fraction
import av
import logging


def video_size(width, height, maximum):
    scale = min(1, maximum / width)
    return max(2, int(width * scale) // 2 * 2), max(2, int(height * scale) // 2 * 2)


class VideoEncoder:
    def __init__(self, width, height, fps, quality=65, hardware=True):
        self.settings=(width,height,fps,quality)
        self.started=False
        if hardware:
            try:
                self.codec=av.CodecContext.create('h264_nvenc','w')
                self.codec.width,self.codec.height=width,height
                # NVENC converts packed RGB to YUV on the GPU. Avoid swscale's
                # full-frame CPU conversion on every captured frame.
                self.codec.pix_fmt='rgb0'
                self.codec.time_base=Fraction(1,1000000)
                self.codec.framerate=Fraction(round(fps),1)
                self.codec.bit_rate=18000000 if quality>=80 else 10000000
                self.codec.max_b_frames=0
                self.codec.gop_size=120
                self.codec.options={'preset':'p1','tune':'ull','zerolatency':'1',
                    'rc-lookahead':'0','delay':'0','surfaces':'4','profile':'baseline'}
                self.codec.open()
                self.name='NVIDIA NVENC'
                return
            except Exception:
                logging.info('NVENC unavailable; trying Intel Quick Sync')
            try:
                self.codec=av.CodecContext.create('h264_qsv','w')
                self.codec.width,self.codec.height=width,height
                self.codec.pix_fmt='nv12'
                self.codec.time_base=Fraction(1,1000000)
                self.codec.framerate=Fraction(round(fps),1)
                self.codec.bit_rate=18000000 if quality>=80 else 12000000
                self.codec.max_b_frames=0
                self.codec.gop_size=120
                self.codec.options={'async_depth':'1','preset':'veryfast','look_ahead':'0','bf':'0','profile':'baseline','refs':'1'}
                self.codec.open()
                self.name='Intel Quick Sync'
                return
            except Exception:
                logging.info('Quick Sync unavailable; using software H.264')
        self.software()

    def software(self):
        width,height,fps,quality=self.settings
        self.codec = av.CodecContext.create('libx264', 'w')
        self.codec.width, self.codec.height = width, height
        self.codec.pix_fmt = 'yuv420p'
        self.codec.time_base = Fraction(1, 1000000)
        self.codec.framerate = Fraction(round(fps), 1)
        self.codec.thread_count = 4
        self.codec.options = {'preset':'ultrafast', 'tune':'zerolatency', 'profile':'baseline',
            'crf':'20' if quality >= 80 else '25',
            'x264-params':'bframes=0:rc-lookahead=0:sync-lookahead=0:repeat-headers=1:annexb=1:keyint=120:scenecut=0'}
        self.codec.open()
        self.name='CPU / x264'

    def encode(self, image, sequence):
        if self.name=='NVIDIA NVENC':
            frame=av.VideoFrame(image.width,image.height,'rgb0')
            if frame.planes[0].line_size==image.width*4:
                frame.planes[0].update(image.tobytes('raw','RGBX'))
            else:
                frame=av.VideoFrame.from_image(image).reformat(format='rgb0')
        else:
            frame = av.VideoFrame.from_image(image)
        frame.pts = sequence
        frame.time_base = self.codec.time_base
        try:
            chunks = self.codec.encode(frame)
            if len(chunks)!=1:raise OSError('Encoder buffered the frame')
        except Exception:
            if self.started or self.name=='CPU / x264':raise
            self.software()
            frame.time_base=self.codec.time_base
            chunks=self.codec.encode(frame)
        if len(chunks) != 1:
            raise OSError('H.264 encoder did not return one immediate frame. Select JPEG compatibility mode.')
        self.started=True
        return bytes(chunks[0])
