import queue
import threading


class EventHub:
    def __init__(self):
        self._lock = threading.Lock()
        self._listeners: set[queue.Queue] = set()

    def subscribe(self) -> queue.Queue:
        listener: queue.Queue = queue.Queue(maxsize=100)
        with self._lock:
            self._listeners.add(listener)
        return listener

    def unsubscribe(self, listener: queue.Queue) -> None:
        with self._lock:
            self._listeners.discard(listener)

    def publish(self, kind: str, **data) -> None:
        event = {"event": kind, **data}
        with self._lock:
            listeners = list(self._listeners)
        for listener in listeners:
            try:
                listener.put_nowait(event)
            except queue.Full:
                pass
