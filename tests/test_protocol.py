import io
import json
import socket
import struct
import pytest
from protocol import placement, json_packet, read_json, read_exact, MAX_COMMAND


class Fragmented:
    def __init__(self,data): self.data=io.BytesIO(data)
    def recv(self,n): return self.data.read(min(n,2))


@pytest.mark.parametrize("side,expected",[("left",(-1280,180)),("right",(1920,180)),("top",(320,-720)),("bottom",(320,1080))])
def test_adjacent_screen_positions(side,expected):
    assert placement((0,0,1920,1080),(0,0,1280,720),side)==expected


def test_offset_and_portrait():
    assert placement((-1920,40,1920,1080),(0,0,1080,1920),"right")== (0,-380)


def test_fragmented_utf8_roundtrip():
    value={"type":"text","text":"Привіт 🛰️"}
    assert read_json(Fragmented(json_packet(value)))==value


@pytest.mark.parametrize("length",[0,1,MAX_COMMAND+1,0xffffffff])
def test_reject_invalid_lengths_before_reading_body(length):
    with pytest.raises(ValueError):read_json(Fragmented(struct.pack("!I",length)))


def test_reject_non_object():
    with pytest.raises(ValueError):read_json(Fragmented(json_packet([1,2])))


def test_truncated_packet():
    with pytest.raises(EOFError):read_json(Fragmented(json_packet({"a":1})[:-2]))
