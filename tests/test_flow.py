import threading
import time
import pytest
from flow import FrameWindow,target_rate,valid_rate


@pytest.mark.parametrize("requested,source,client,expected",[(0,144,120,120),(0,60,144,60),(240,165,120,120),(30,120,120,30),(0,60,59.94,59.94)])
def test_negotiated_fps(requested,source,client,expected):
    assert target_rate(requested,source,client)==expected


@pytest.mark.parametrize("value",[None,True,False,0,-1,10000,float('nan'),float('inf'),'invalid'])
def test_invalid_refresh(value):assert valid_rate(value)==60


def test_exactly_two_unacknowledged_frames():
    window=FrameWindow(2)
    first,second=window.reserve(),window.reserve()
    with pytest.raises(OSError):window.reserve(.01)
    assert not window.acknowledge(999)
    assert not window.acknowledge(True)
    assert window.acknowledge(first)
    assert not window.acknowledge(first)
    assert window.reserve()>second
    assert len(window.pending)==2


def test_close_unblocks_waiting_writer():
    window=FrameWindow(1);window.reserve()
    result=[]
    thread=threading.Thread(target=lambda:result.append(window.reserve(2)))
    thread.start();window.close();thread.join(1)
    assert result==[None] and not thread.is_alive()


def test_dropped_frame_frees_slot_but_is_not_latency_sample():
    window=FrameWindow(1);seq=window.reserve()
    assert window.acknowledge(seq,presented=False)
    assert window.roundtrip_ms==0
    assert window.reserve()>seq
