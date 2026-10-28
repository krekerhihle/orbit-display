"""Explicit CLI-only stream check. Local TLS, no input, no pixels written to disk."""
import io
import socket
import ssl
import struct
from PIL import Image
from server import Server
from protocol import json_packet,read_json,read_exact


def stream_check(directory,screen,video=False):
    events=[]
    server=Server(directory,lambda kind,text:events.append((kind,text)),port=0)
    server.start(screen,fps=0,quality=65,max_width=1920,bind='127.0.0.1')
    try:
        context=ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.check_hostname=False;context.verify_mode=ssl.CERT_NONE
        context.maximum_version=ssl.TLSVersion.TLSv1_2
        with context.wrap_socket(socket.create_connection(server.listener.getsockname(),timeout=12),server_hostname='localhost') as client:
            client.setsockopt(socket.IPPROTO_TCP,socket.TCP_NODELAY,1)
            client.sendall(json_packet({'type':'auth','version':1,'pin':server.pin,'frame_ack_v2':True,'refresh_hz':144,'h264':video}))
            ready=read_json(client)
            if video:
                import av
                assert ready['codec']=='h264'
                decoder=av.CodecContext.create('h264','r')
            for _ in range(12):
                length=struct.unpack('!I',read_exact(client,4))[0];body=read_exact(client,length)
                assert body[:1]==(b'H' if video else b'G')
                sequence=struct.unpack('!Q',body[1:9])[0]
                if video:
                    frames=decoder.decode(av.Packet(body[9:]));assert len(frames)==1
                    size=[frames[0].width,frames[0].height]
                else:
                    image=Image.open(io.BytesIO(body[9:]));image.load();size=list(image.size)
                client.sendall(json_packet({'type':'ack','seq':sequence}))
        return {'ok':True,'codec':ready['codec'],'frames':12,'frame_size':size,'target_fps':ready['target_fps'],
            'capture_backends':[text for kind,text in events if kind=='capture'],'saved_pixels':False}
    finally:server.stop()
