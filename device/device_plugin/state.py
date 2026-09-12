import datetime as dt
import time


class BootState:
    def __init__(self):
        self.reset()

    def reset(self):
        self.monotonic = time.monotonic()
        self.time = dt.datetime.now(dt.UTC)

    def uptime_seconds(self):
        return int(time.monotonic() - self.monotonic)

    def time_iso(self):
        return self.time.isoformat(timespec="seconds")


boot_state = BootState()
