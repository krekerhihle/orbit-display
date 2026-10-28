from PIL import Image
from pacing import FrameDeduplicator

def test_idle_is_suppressed_but_small_change_is_sent():
    tracker=FrameDeduplicator();frame=Image.new('RGB',(1920,1080),'black')
    assert tracker.should_send(frame,0)
    assert not tracker.should_send(frame,.01)
    frame.putpixel((1919,1079),(1,0,0))
    assert tracker.should_send(frame,.02)
    assert not tracker.should_send(frame,.03)
    assert tracker.should_send(frame,1.03)
