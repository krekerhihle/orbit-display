"""Real TLS sockets; synthetic pixels avoid reading the user's desktop in tests."""
import hashlib
import io
import socket
import ssl
import struct
import threading
import time
from types import SimpleNamespace
import pytest
from PIL import Image
import server as module
from server import Server,certificate
from display import Display
from protocol import read_json,read_exact,json_packet


class Capture:
    backend='Synthetic'
    cursor_embedded=False
    def __init__(self,*args):pass
    def __enter__(self):return self
    def __exit__(self,*a):pass
    def frame(self):return Image.new('RGB',(320,180),'#a07030')


class Input:
    released=threading.Event()
    def __init__(self,screen):pass
    def release(self):self.released.set()


@pytest.fixture
def host(tmp_path,monkeypatch):
    # Transport tests require continuous synthetic frames; idle suppression has
    # separate tests and must not turn an 80-frame stress test into 80 seconds.
    monkeypatch.setattr(module.FrameDeduplicator,'should_send',lambda *args:True)
    monkeypatch.setattr(module,"ScreenCapture",Capture)
    monkeypatch.setattr(module,"RemoteInput",Input)
    Input.released.clear()
    screen=Display("test","Virtual",False,1920,0,320,180)
    monkeypatch.setattr(module,"displays",lambda:[screen])
    events=[]
    s=Server(tmp_path,lambda kind,text:events.append((kind,text)),port=0)
    s.start(screen,bind="127.0.0.1")
    s.events=events
    yield s
    s.stop()
    assert not s.thread.is_alive()


def connect(host):
    ctx=ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname=False
    ctx.verify_mode=ssl.CERT_NONE
    client=ctx.wrap_socket(socket.create_connection(host.listener.getsockname(),timeout=2),server_hostname="localhost")
    assert hashlib.sha256(client.getpeercert(binary_form=True)).hexdigest().upper()==host.fingerprint
    return client


def authenticate(client,host,pin=None):client.sendall(json_packet({"type":"auth","version":1,"pin":pin or host.pin,"name":"Test Android"}))


def test_certificate_stays_pinned(tmp_path):
    _,first=certificate(tmp_path)
    _,second=certificate(tmp_path)
    assert first==second and len(first)==64


def test_invalid_pin_never_gets_a_frame(host):
    with connect(host) as c:
        authenticate(c,host,"invalid")
        assert read_json(c)["type"]=="error"
        assert c.recv(1)==b""
    assert not any(kind=="connected" for kind,_ in host.events)


def test_expired_pin(host):
    host.expires=time.monotonic()-1
    with connect(host) as c:
        authenticate(c,host)
        assert read_json(c)["type"]=="error"


def test_protocol_mismatch(host):
    with connect(host) as c:
        c.sendall(json_packet({"type":"auth","version":99,"pin":host.pin}))
        assert read_json(c)["type"]=="error"


def test_attempt_budget_rejects_sixth_connection(host):
    for _ in range(5):
        with connect(host) as c:
            authenticate(c,host,"bad")
            assert read_json(c)["type"]=="error"
    with socket.create_connection(host.listener.getsockname(),timeout=2) as raw:
        assert raw.recv(1)==b""


def test_stop_interrupts_unauthenticated_client(host):
    with connect(host) as c:
        host.stop()
        assert not host.thread.is_alive()
        assert c.recv(1)==b""


def test_authenticated_frames_and_releases_on_disconnect(host):
    with connect(host) as c:
        authenticate(c,host)
        ready=read_json(c)
        assert ready["width"]==320 and ready["height"]==180
        for _ in range(3):
            size=struct.unpack("!I",read_exact(c,4))[0]
            payload=read_exact(c,size)
            assert payload[:1]==b"F"
            im=Image.open(io.BytesIO(payload[1:]));assert im.size==(320,180)
            c.sendall(json_packet({"type":"ack"}))
    assert Input.released.wait(2)


def test_no_extra_frame_until_ack(host):
    with connect(host) as c:
        authenticate(c,host);read_json(c)
        size=struct.unpack("!I",read_exact(c,4))[0];read_exact(c,size)
        c.settimeout(.2)
        with pytest.raises(socket.timeout):c.recv(1)


def test_clipboard_denied_by_default(host):
    with connect(host) as c:
        authenticate(c,host);read_json(c)
        c.sendall(json_packet({"type":"clipboard_set","text":"private"}))
        time.sleep(.05)
    assert not any(kind=="clipboard_set" for kind,_ in host.events)


def test_clipboard_requires_explicit_permission(host):
    host.allow_clipboard=True
    with connect(host) as c:
        authenticate(c,host);read_json(c)
        c.sendall(json_packet({"type":"clipboard_set","text":"test"}))
        deadline=time.monotonic()+1
        while not any(k=="clipboard_set" for k,_ in host.events) and time.monotonic()<deadline:time.sleep(.01)
    assert ("clipboard_set","test") in host.events


def test_topology_change_ends_capture(host,monkeypatch):
    monkeypatch.setattr(module,"displays",lambda:[])
    with connect(host) as c:
        authenticate(c,host);read_json(c)
        assert c.recv(1)==b""
    assert any("змінилося" in text for _,text in host.events)


def read_sequenced_frame(client):
    size=struct.unpack('!I',read_exact(client,4))[0];body=read_exact(client,size)
    assert body[:1]==b'G'
    sequence=struct.unpack('!Q',body[1:9])[0]
    image=Image.open(io.BytesIO(body[9:]));image.load()
    assert image.size==(320,180)
    return sequence


def test_new_client_pipeline_and_fps_negotiation(host):
    host.fps=0
    with connect(host) as c:
        c.sendall(json_packet({'type':'auth','version':1,'pin':host.pin,'frame_ack_v2':True,'refresh_hz':120}))
        ready=read_json(c)
        assert ready['frame_ack_v2'] is True
        assert ready['target_fps']==60  # Source display is 60 Hz, even with a 120-Hz Android.
        one,two=read_sequenced_frame(c),read_sequenced_frame(c)
        assert one<two
        c.settimeout(.1)
        with pytest.raises(socket.timeout):c.recv(1)
        c.sendall(json_packet({'type':'ack','seq':one,'presented':True}))
        c.settimeout(2)
        three=read_sequenced_frame(c)
        assert three>two
        c.sendall(json_packet({'type':'ack','seq':one}))  # Duplicate must not release a slot.
        c.sendall(json_packet({'type':'ack','seq':99999}))
        c.settimeout(.1)
        with pytest.raises(socket.timeout):c.recv(1)
        c.sendall(json_packet({'type':'ack','seq':two,'presented':False}))
        c.settimeout(2);assert read_sequenced_frame(c)>three


def test_large_tls_frames_and_simultaneous_acknowledgements(host,monkeypatch):
    import random
    pixels=random.Random(1234).randbytes(320*180*3)
    monkeypatch.setattr(Capture,'frame',lambda self:Image.frombytes('RGB',(320,180),pixels))
    host.fps=0
    with connect(host) as client:
        client.sendall(json_packet({'type':'auth','version':1,'pin':host.pin,'frame_ack_v2':True,'refresh_hz':144}))
        assert read_json(client)['type']=='ready'
        for i in range(80):
            seq=read_sequenced_frame(client)
            client.sendall(json_packet({'type':'ack','seq':seq}))
        client.sendall(json_packet({'type':'bye'}))
    assert Input.released.wait(2)
