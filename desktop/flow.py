"""Bounded frame acknowledgements and explicit source/client rate negotiation."""
import math
import threading
import time


def valid_rate(value, default=60.0):
    if isinstance(value,bool): return default
    try: rate = float(value)
    except (TypeError,ValueError): return default
    return rate if math.isfinite(rate) and 1 < rate <= 500 else default


def target_rate(requested, source, client):
    limit = min(valid_rate(source),valid_rate(client))
    return min(limit,valid_rate(requested)) if requested else limit


class FrameWindow:
    def __init__(self, capacity):
        self.capacity = capacity
        self.condition = threading.Condition()
        self.pending = {}
        self.next_id = 1
        self.closed = False
        self.roundtrip_ms = 0.0

    def reserve(self, timeout=10):
        with self.condition:
            if not self.condition.wait_for(lambda:self.closed or len(self.pending)<self.capacity,timeout):
                raise OSError("Телефон не підтверджує кадри")
            if self.closed: return None
            sequence = self.next_id
            self.next_id += 1
            self.pending[sequence] = time.perf_counter()
            return sequence

    def acknowledge(self, sequence=None, legacy=False, presented=True):
        with self.condition:
            if legacy: sequence = next(iter(self.pending),None)
            if isinstance(sequence,bool) or not isinstance(sequence,int) or sequence not in self.pending: return False
            start = self.pending.pop(sequence)
            if presented: self.roundtrip_ms = (time.perf_counter()-start)*1000
            self.condition.notify_all()
            return True

    def close(self):
        with self.condition:
            self.closed = True
            self.condition.notify_all()
