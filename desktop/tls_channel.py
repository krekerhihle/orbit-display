"""Serialize OpenSSL calls without blocking the opposite direction on a read."""
import select
import socket
import ssl
import threading
import time


class TLSChannel:
    def __init__(self,sock,timeout=12):
        self.socket = sock
        self.timeout = timeout
        self.lock = threading.Lock()
        sock.setblocking(False)

    def _wait(self,read,deadline):
        remaining = deadline-time.monotonic()
        if remaining<=0:raise socket.timeout('TLS connection timed out')
        readable,writable,_=select.select([self.socket] if read else [],[] if read else [self.socket],[],remaining)
        if not readable and not writable:raise socket.timeout('TLS connection timed out')

    def recv(self,size):
        deadline=time.monotonic()+self.timeout
        while True:
            try:
                with self.lock:return self.socket.recv(size)
            except ssl.SSLWantReadError:self._wait(True,deadline)
            except ssl.SSLWantWriteError:self._wait(False,deadline)

    def sendall(self,data):
        view=memoryview(data);offset=0
        deadline=time.monotonic()+self.timeout
        while offset<len(view):
            try:
                with self.lock:sent=self.socket.send(view[offset:offset+65536])
                if not sent:raise EOFError('TLS connection closed')
                offset+=sent
            except ssl.SSLWantReadError:self._wait(True,deadline)
            except ssl.SSLWantWriteError:self._wait(False,deadline)

    def shutdown(self,how):self.socket.shutdown(how)

    def close(self):
        with self.lock:self.socket.close()
