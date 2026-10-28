"""Orbit v1: TLS, uint32 network-order length, one-byte kind, payload."""
import json
import struct

VERSION = 1
PORT = 48620
MAX_COMMAND = 32768
MAX_FRAME = 16 * 1024 * 1024


def read_exact(sock, size):
    data = bytearray()
    while len(data) < size:
        part = sock.recv(size - len(data))
        if not part:
            raise EOFError("Connection closed")
        data.extend(part)
    return bytes(data)


def packet(kind, payload):
    return struct.pack("!I", len(payload) + 1) + kind + payload


def json_packet(value):
    return packet(b"J", json.dumps(value, ensure_ascii=False).encode("utf-8"))


def read_json(sock):
    length = struct.unpack("!I", read_exact(sock, 4))[0]
    if not 2 <= length <= MAX_COMMAND:
        raise ValueError("Invalid command length")
    body = read_exact(sock, length)
    if body[:1] != b"J":
        raise ValueError("Expected JSON command")
    value = json.loads(body[1:].decode("utf-8"))
    if not isinstance(value, dict):
        raise ValueError("Expected object")
    return value


def placement(primary, secondary, side):
    """Centre the shared edge; coordinates may legitimately be negative."""
    px, py, pw, ph = primary
    _, _, sw, sh = secondary
    if side == "left":
        return px - sw, py + (ph - sh) // 2
    if side == "right":
        return px + pw, py + (ph - sh) // 2
    if side == "top":
        return px + (pw - sw) // 2, py - sh
    if side == "bottom":
        return px + (pw - sw) // 2, py + ph
    raise ValueError("Unknown screen position")
