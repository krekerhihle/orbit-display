import av
import pytest
from PIL import Image
from video import VideoEncoder, video_size
from protocol import json_packet, read_json, read_exact
import struct
from test_server import host, connect, Input


@pytest.fixture(autouse=True)
def deterministic_encoder(monkeypatch):
    import video
    monkeypatch.setattr(video,'VideoEncoder',lambda *args:VideoEncoder(*args,hardware=False))


def test_low_delay_annexb_decodes_every_frame():
    encoder=VideoEncoder(320,180,120,hardware=False)
    decoder=av.CodecContext.create('h264','r')
    for seq in range(1,15):
        data=encoder.encode(Image.new('RGB',(320,180),(seq*10,20,30)),seq)
        assert data.startswith(b'\x00\x00\x00\x01')
        frames=decoder.decode(av.Packet(data))
        assert len(frames)==1 and (frames[0].width,frames[0].height)==(320,180)


def test_even_video_dimensions():
    assert video_size(1920,1080,1920)==(1920,1080)
    assert video_size(1920,1080,1280)==(1280,720)
    assert video_size(1365,767,1600)==(1364,766)


def test_authenticated_video_and_ack_backpressure(host):
    decoder=av.CodecContext.create('h264','r')
    with connect(host) as client:
        client.sendall(json_packet({'type':'auth','version':1,'pin':host.pin,'frame_ack_v2':True,'h264':True,'refresh_hz':120}))
        ready=read_json(client)
        assert ready['codec']=='h264' and ready['video_width']==320
        for _ in range(30):
            length=struct.unpack('!I',read_exact(client,4))[0];body=read_exact(client,length)
            assert body[:1]==b'H'
            seq=struct.unpack('!Q',body[1:9])[0]
            frames=decoder.decode(av.Packet(body[9:]))
            assert len(frames)==1
            client.sendall(json_packet({'type':'ack','seq':seq}))
        client.sendall(json_packet({'type':'bye'}))
    assert Input.released.wait(2)


def test_jpeg_setting_overrides_client_video(host):
    host.video=False
    with connect(host) as client:
        client.sendall(json_packet({'type':'auth','version':1,'pin':host.pin,'frame_ack_v2':True,'h264':True}))
        assert read_json(client)['codec']=='jpeg'


def test_encoder_failure_negotiates_jpeg(host,monkeypatch):
    import video
    def fail(*a):raise RuntimeError('Unavailable')
    monkeypatch.setattr(video,'VideoEncoder',fail)
    with connect(host) as client:
        client.sendall(json_packet({'type':'auth','version':1,'pin':host.pin,'frame_ack_v2':True,'h264':True}))
        assert read_json(client)['codec']=='jpeg'
