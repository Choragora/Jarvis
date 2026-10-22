import asyncio
import time
from collections import deque


class Events:
    def __init__(self):
        self.clients: set[asyncio.Queue] = set()
        self.history = deque(maxlen=200)
        self.sequence = 0

    def emit(self, kind: str, **data):
        self.sequence += 1
        event = {"seq": self.sequence, "type": kind, "at": time.monotonic(), **data}
        self.history.append(event)
        for queue in tuple(self.clients):
            if queue.full():
                queue.get_nowait()
            queue.put_nowait(event)
