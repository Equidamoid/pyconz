import struct
from . import protocol


class Buffer:
    def __init__(self, data):
        self.data = data
        self.cmd, self.seq, self.status, self.frame_len= self.pop('<BBBH')
        try:
            self.cmd = protocol.CommandId(self.cmd)
        except ValueError:
            pass
        self.status = protocol.Status(self.status)

    def pop(self, fmt):
        # type: (str) -> tuple
        l = struct.calcsize(fmt)
        return struct.unpack(fmt, self.pop_raw(l))

    def pop_int(self, fmt):
        # type: (str) -> int
        return self.pop(fmt)[0]

    def pop_enum(self, fmt, cls):
        # type: (str, type) -> object
        return cls(self.pop(fmt)[0])

    def pop_raw(self, l):
        buf = self.data[:l]
        self.data = self.data[l:]
        return buf