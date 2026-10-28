import datetime
import hashlib
import hmac
import io
import logging
import secrets
import socket
import ssl
import threading
import time
import struct
import ctypes
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID
from PIL import Image, ImageDraw

from protocol import VERSION, PORT, packet, json_packet, read_json
from display import RemoteInput, displays, user32, W, C
from flow import FrameWindow, target_rate, valid_rate
from capture import ScreenCapture
from tls_channel import TLSChannel
from pacing import FrameDeduplicator


def certificate(directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    certfile, keyfile = directory / "host.crt", directory / "host.key"
    if not certfile.exists() or not keyfile.exists():
        key = ec.generate_private_key(ec.SECP256R1())
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Orbit Display")])
        now = datetime.datetime.now(datetime.timezone.utc)
        cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now-datetime.timedelta(days=1))
            .not_valid_after(now+datetime.timedelta(days=3650)).sign(key, hashes.SHA256()))
        keyfile.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
        certfile.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    cert = x509.load_pem_x509_certificate(certfile.read_bytes())
    fingerprint = cert.fingerprint(hashes.SHA256()).hex().upper()
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ctx.load_cert_chain(certfile, keyfile)
    return ctx, fingerprint


class Server:
    """One explicitly selected monitor, one authenticated client, one frame in flight."""
    def __init__(self, directory, event, port=PORT):
        self.context, self.fingerprint = certificate(directory)
        self.event, self.port = event, port
        self.pin = ""
        self.listener = None
        self.client = None
        self.thread = None
        self.stop_event = threading.Event()
        self.send_lock = threading.Lock()
        self.input_lock = threading.Lock()
        self.control = None
        self.allow_touch = True
        self.allow_clipboard = False
        self.failures = []
        self.authenticated = False

    def start(self, screen, fps=15, quality=65, max_width=1600, bind="0.0.0.0", fast_capture=True, video=True):
        if self.thread and self.thread.is_alive(): raise RuntimeError("Session is still stopping")
        self.screen, self.fps, self.quality, self.max_width = screen, fps, quality, max_width
        self.fast_capture = fast_capture
        self.video = video
        self.pin = f"{secrets.randbelow(1000000):06}"
        self.expires = time.monotonic()+600
        self.stop_event.clear()
        listener = socket.socket()
        # Windows SO_EXCLUSIVEADDRUSE prevents a second process from hijacking the port.
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        try:
            listener.bind((bind, self.port))
            listener.listen(2)
            listener.settimeout(.5)
        except Exception:
            listener.close()
            raise
        self.listener = listener
        self.thread = threading.Thread(target=self._serve, daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        for obj in (self.client, self.listener):
            if obj:
                try: obj.shutdown(socket.SHUT_RDWR)
                except OSError: pass
                try: obj.close()
                except OSError: pass
        if self.thread and self.thread is not threading.current_thread(): self.thread.join(2)

    def send_json(self, value):
        if self.client and self.authenticated:
            try:
                with self.send_lock: self.client.sendall(json_packet(value))
            except OSError: pass

    def _serve(self):
        try:
            while not self.stop_event.is_set():
                try: raw, address = self.listener.accept()
                except socket.timeout: continue
                except OSError: break
                try:
                    raw.settimeout(12)
                    raw.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                    # Global attempt budget survives session restarts; no IP-spoof bypass.
                    self.failures = [t for t in self.failures if time.monotonic()-t < 60]
                    if len(self.failures) >= 5:
                        raw.close()
                        self.event("status", "Забагато спроб. Зачекайте хвилину.")
                        continue
                    self.client = raw
                    # Publish the SSL socket before blocking in the handshake, so Stop can
                    # interrupt it. wrap_socket's default handshake detaches raw first.
                    conn = self.context.wrap_socket(raw, server_side=True, do_handshake_on_connect=False)
                    self.client = conn
                    if self.stop_event.is_set(): break
                    conn.do_handshake()
                    conn.settimeout(60)  # Time to compare the certificate on the phone.
                    self.failures.append(time.monotonic())
                    auth = read_json(conn)
                    if (auth.get("type") != "auth" or auth.get("version") != VERSION or
                        time.monotonic() > self.expires or not isinstance(auth.get("pin"), str) or
                        not hmac.compare_digest(auth["pin"], self.pin)):
                        conn.sendall(json_packet({"type":"error", "message":"Неправильний або прострочений код. Перезапустіть сеанс на ПК."}))
                        continue
                    self.authenticated = True
                    conn.settimeout(12)
                    conn = TLSChannel(conn)
                    self.client = conn
                    self.event("connected", str(auth.get("name", "Android"))[:80])
                    self._stream(conn, auth)
                except (OSError, ValueError, EOFError) as exc:
                    if not self.stop_event.is_set(): self.event("status", f"З'єднання завершено: {exc}")
                except Exception:
                    logging.exception("Session failed")
                    self.event("status", "Помилка сеансу. Подробиці в orbit.log.")
                finally:
                    self.authenticated = False
                    if self.client:
                        try: self.client.close()
                        except OSError: pass
                    raw.close()
                    self.client = None
                    self.event("disconnected", "Телефон від'єднано")
        finally:
            self.event("stopped", "Сеанс завершено")

    def _stream(self, conn, auth):
        done = threading.Event()
        sequenced = auth.get("frame_ack_v2") is True
        window = FrameWindow(2 if sequenced else 1)
        client_hz = valid_rate(auth.get("refresh_hz"))
        rate = [target_rate(self.fps or 60,self.screen.hz,client_hz)]
        encoder = None
        encoded_width, encoded_height = self.screen.width, self.screen.height
        if self.video and sequenced and auth.get('h264') is True:
            try:
                from video import VideoEncoder, video_size
                encoded_width, encoded_height = video_size(self.screen.width,self.screen.height,self.max_width)
                encoder = VideoEncoder(encoded_width,encoded_height,rate[0],self.quality)
            except Exception:
                logging.exception('H.264 unavailable; negotiating JPEG')
        # Some hardware decoders require several input buffers before producing
        # output. Keep this bounded while allowing their startup pipeline to fill.
        if encoder:window.capacity=4
        control = RemoteInput(self.screen)
        self.control = control
        self.send_json({"type":"ready", "version":VERSION, "width":self.screen.width,
            "height":self.screen.height, "touch":self.allow_touch, "clipboard":self.allow_clipboard,
            "frame_ack_v2":sequenced, "target_fps":rate[0], "source_hz":self.screen.hz,
            "codec":"h264" if encoder else "jpeg", "video_width":encoded_width,"video_height":encoded_height})

        def receive():
            try:
                while not done.is_set() and not self.stop_event.is_set():
                    data = read_json(conn)
                    kind = data.get("type")
                    if kind == "ack": window.acknowledge(data.get("seq"),legacy=not sequenced,presented=data.get("presented",True) is True)
                    elif kind == "refresh": rate[0] = target_rate(self.fps or 60,self.screen.hz,valid_rate(data.get("hz")))
                    elif kind == "ping": self.send_json({"type":"pong"})
                    elif kind == "bye": break
                    elif kind in ("clipboard_get", "clipboard_set"):
                        if self.allow_clipboard:
                            text = data.get("text", "")
                            if isinstance(text, str) and len(text) <= 4096: self.event(kind, text)
                    elif self.allow_touch:
                        with self.input_lock:
                            if kind == "pointer": control.mouse(data)
                            elif kind == "key": control.key(data)
                            elif kind == "text": control.text(data.get("text", ""))
                            elif kind == "scroll": control.scroll(data.get("amount", 0))
            except (OSError, ValueError, EOFError, TypeError) as exc:
                if not done.is_set() and not self.stop_event.is_set():
                    logging.info('Receiver ended: %s',exc)
                    self.event('status',f'З’єднання з Android завершено: {exc}')
            finally:
                done.set()
                window.close()
                with self.input_lock: control.release()

        reader = threading.Thread(target=receive, daemon=True)
        reader.start()
        # Windows otherwise rounds short Event.wait intervals toward a 15.6-ms tick.
        # Scope the 1-ms request to the active stream and balance it on every exit.
        precise_timer = ctypes.windll.winmm.timeBeginPeriod(1) == 0
        try:
            with ScreenCapture(self.screen,self.fast_capture) as capture:
                frames, sent, start, topology_check = 0, 0, time.perf_counter(), 0
                last_backend = None
                dedup=FrameDeduplicator()
                last_frame=None
                last_pointer=None
                last_sent=0
                while not done.is_set() and not self.stop_event.is_set():
                    tick = time.perf_counter()
                    if tick-topology_check > 1:
                        topology_check = tick
                        current = next((d for d in displays() if d.name == self.screen.name), None)
                        if current is None or current.rect != self.screen.rect or current.hz != self.screen.hz:
                            self.event("status", "Розташування дисплеїв змінилося. Зупиніть і почніть сеанс знову.")
                            break
                    sequence = window.reserve()
                    if sequence is None or done.is_set() or self.stop_event.is_set(): break
                    # Auto mode caps polling at 60 to avoid saturating the CPU while
                    # stationary; higher requested rates remain explicit choices.
                    interval=1/rate[0]
                    pos = W.POINT()
                    pointer=(pos.x,pos.y) if user32.GetCursorPos(C.byref(pos)) else None
                    frame = capture.changed_frame() if hasattr(capture,'changed_frame') else capture.frame()
                    if frame is None:
                        if last_frame is None or (pointer==last_pointer and tick-last_sent<1):
                            window.acknowledge(sequence,presented=False)
                            done.wait(max(.001,interval-(time.perf_counter()-tick)))
                            continue
                        frame=last_frame
                    last_frame=frame
                    last_pointer=pointer
                    frame=frame.copy()
                    if capture.backend != last_backend:
                        last_backend = capture.backend
                        self.event('capture',capture.backend)
                    if not capture.cursor_embedded and pointer:
                        x, y = pos.x-self.screen.x, pos.y-self.screen.y
                        if 0 <= x < frame.width and 0 <= y < frame.height:
                            ImageDraw.Draw(frame).polygon([(x,y),(x,y+20),(x+5,y+15),(x+11,y+23),(x+15,y+20),(x+9,y+13),(x+18,y+12)],fill="white",outline="black",width=2)
                    if encoder and frame.size != (encoded_width,encoded_height):
                        frame = frame.resize((encoded_width,encoded_height), Image.Resampling.BILINEAR)
                    elif not encoder and frame.width > self.max_width:
                        frame = frame.resize((self.max_width, round(frame.height*self.max_width/frame.width)), Image.Resampling.BILINEAR)
                    if not dedup.should_send(frame,tick):
                        window.acknowledge(sequence,presented=False)
                        done.wait(max(.001,interval-(time.perf_counter()-tick)))
                        continue
                    if encoder:
                        data = encoder.encode(frame,sequence)
                    else:
                        output = io.BytesIO()
                        frame.save(output, format="JPEG", quality=self.quality)
                        data = output.getvalue()
                    # Bounded frames across encode/network/render: four H.264, two JPEG.
                    payload = packet(b"H" if encoder else b"G", struct.pack("!Q",sequence)+data) if sequenced else packet(b"F",data)
                    with self.send_lock: conn.sendall(payload)
                    last_sent=tick
                    frames += 1
                    sent += len(data)
                    elapsed = time.perf_counter()-start
                    if elapsed >= 1:
                        self.event("metrics", f"{frames/elapsed:.0f} FPS / ціль {rate[0]:.0f} · {frame.width}×{frame.height} · {'H.264 / '+encoder.name if encoder else 'JPEG'}\n{sent*8/elapsed/1e6:.1f} Мбіт/с · кадр ↔ ПК {window.roundtrip_ms:.0f} мс")
                        frames, sent, start = 0, 0, time.perf_counter()
                    done.wait(max(0, interval-(time.perf_counter()-tick)))
        finally:
            if precise_timer: ctypes.windll.winmm.timeEndPeriod(1)
            done.set()
            window.close()
            try: conn.shutdown(socket.SHUT_RDWR)
            except OSError: pass
            reader.join(2)
            with self.input_lock: control.release()
            self.control = None
