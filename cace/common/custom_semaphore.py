from threading import Thread
from threading import Condition

from copy import copy


class CustomSemaphore:
    def __init__(self, value: int = 1):
        if value < 0:
            raise ValueError('Initial value must be >= 0')

        # initialize counter
        self._counter = value

        # initialize lock
        self._condition = Condition()

    def __enter__(self):
        self.acquire()

    def __exit__(self, type, value, traceback):
        self.release()

    def acquire(self, count: int = 1) -> None:
        """Acquire count permits atomically, or wait until they are available."""

        with self._condition:
            self._condition.wait_for(lambda: self._counter >= count)
            self._counter -= count

    def locked(self, count: int = 1) -> bool:
        """Return True if acquire(count) would not return immediately."""

        return self._counter < count

    def release(self, count: int = 1) -> None:
        """Release count permits."""

        with self._condition:
            self._counter += count
            self._condition.notify_all()
