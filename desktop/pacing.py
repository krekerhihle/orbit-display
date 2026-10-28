"""Avoid repeatedly encoding identical pixels; keep a one-second refresh."""
import zlib

class FrameDeduplicator:
    def __init__(self):self.last=None;self.sent_at=-10
    def should_send(self,image,now):
        signature=(image.size,zlib.crc32(image.tobytes()))
        changed=signature!=self.last or now-self.sent_at>=1
        if changed:self.last=signature;self.sent_at=now
        return changed
