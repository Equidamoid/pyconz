import zigpy.zdo
import zigpy.zcl
import logging
import serial
import serial.aio
import asyncio
import sliplib
from .protocol import *
from . import protocol
from .utils import Buffer
import binascii
import os
import typing

logger = logging.getLogger(__name__)


Address = collections.namedtuple('Address', ['mode', 'addr', 'endpoint'])
Address.__str__ = lambda a: '%x.%02x (%s)' % (a.addr, a.endpoint, a.mode)


class Message:
    def __init__(self):
        self.src = None     # type: Address
        self.dest = None    # type: Address
        self.data = None    # type: bytes
        self.profile_id = None  # type: int
        self.cluster_id = None  # type: int

    @staticmethod
    def from_buffer(buf: Buffer):
        pl_len = buf.pop_int('<H')
        dev_st = buf.pop_int('B')

        dest_addr_mode = buf.pop_enum('B', AddressType)
        dest_addr = buf.pop('<H' if dest_addr_mode in [AddressType.Group, AddressType.NWK] else '<Q')[0]
        dest_endpoint = buf.pop_int('B')
        src_addr_mode = buf.pop_enum('B', AddressType)
        assert src_addr_mode != AddressType.Group   # not in the spec
        src_addr = buf.pop('<H' if src_addr_mode == AddressType.NWK else '<Q')[0]

        src_endpoint, profile_id, cluster_id = buf.pop('<BHH')
        asdu_len = buf.pop_int('<H')
        asdu = buf.pop_raw(asdu_len)
        logger.warning('Data %x.%02d (%s) -> %x.%02d (%s), len %d, %s', src_addr, src_endpoint, src_addr_mode, dest_addr, dest_endpoint, dest_addr_mode, asdu_len, binascii.hexlify(asdu).decode())
        buf.pop('<BB')
        lqi = buf.pop('<B')[0]
        buf.pop('<BBBB')
        rssi = buf.pop('<b')[0]

        msg = Message()
        msg.src = Address(src_addr_mode, src_addr, src_endpoint)
        msg.dest = Address(dest_addr_mode, dest_addr, dest_endpoint)
        msg.data = asdu
        msg.cluster_id = cluster_id
        msg.profile_id = profile_id

        return msg, dev_st

    def deserialize(self):
        if self.dest.endpoint == 0:
            deserialize = zigpy.zdo.deserialize
        else:
            deserialize = zigpy.zcl.deserialize
        return deserialize(self.cluster_id, self.data)

    def __str__(self):
        tsn, cmd, reply, value = self.deserialize()

        if isinstance(value, bytes):
            value = binascii.hexlify(value).decode()
        return '[%04x:%04x] %s -> %s: [%d, %d, %d, %s]' % (
            self.cluster_id, self.profile_id, self.src, self.dest,
            tsn, cmd, reply, value)


class SerialConnection:
    def __init__(self):
        super().__init__()
        self._transport = None  # type: serial.aio.SerialTransport
        self._seq = 0
        self._drv = sliplib.Driver()
        self.logger = logger
        self._msg_handlers = {
            CommandId.DEVICE_STATE: self.handle_dev_state,
            CommandId.DEVICE_STATE_CHANGED: self.handle_dev_state_changed,
            # 0x1c: self.ignore_message,
            CommandId.APS_DATA_INDICATION: self.handle_incoming_data,
            CommandId.READ_PARAMETER: self.handle_get_parameter_response
        }
        self._requests = {}     # type: typing.Dict[int, asyncio.Future]

    async def read_all_parameters(self):
        data = {}
        for p in NetworkParameter:
            data[p] = await self.get_parameter(p)
        self.logger.warning("Parameters: %s", data)

    def get_parameter(self, p):
        # type: (protocol.NetworkParameter) -> asyncio.Future
        ret = asyncio.Future()
        seq = self.next_seq()
        req = struct.pack('<BBBHHB', 0x0a, seq, 0, 8, 1, p.value)
        self._requests[seq] = ret
        self.send_message(req)
        return ret

    def handle_get_parameter_response(self, buf: Buffer):
        seq = buf.seq
        pl_len = buf.pop_int('<H')
        param = buf.pop_enum('B', NetworkParameter)
        p_type = param_types[param]     # type: protocol.NetworkParamInfo
        data = buf.pop_int(p_type.format)
        self.logger.warning("Got parameter value %s = %x", param, data)
        try:
            f = self._requests[seq]
            f.set_result(data)
            del self._requests[seq]
        except KeyError:
            pass

    def next_seq(self):
        self._seq += 1
        self._seq = self._seq % 256
        if self._seq in self._requests:
            self.logger.error("Have to reuse request id %d", self._seq)
            self._requests[self._seq].set_exception(TimeoutError("No response received, have to reuse request id"))
            del self._requests[self._seq]
        return self._seq

    def connection_made(self, transport: serial.aio.SerialTransport):
        self.logger.warning("Connection made: %s", transport)
        self._transport = transport
        self.do_hello()

    def data_received(self, data):
        msgs = self._drv.receive(data)
        for i in msgs:
            try:
                self.handle_message(i)
            except:
                self.logger.exception("Error while handling message %s", binascii.hexlify(i).decode())

    def connection_lost(self, exc):
        self.logger.error("Connection lost")

    async def startup(self):
        self.logger.warning("Beginning of startup sequence")
        await asyncio.sleep(5)
        await self.read_all_parameters()
        self.logger.warning("End of startup sequence")

    def do_hello(self):
        self.request_dev_state()
        asyncio.ensure_future(self.startup())

    def hard_reset(self):
        os.system('gpio write 0 0; sleep 2; gpio write 0 1')
        self._drv = sliplib.Driver()

    def handle_message(self, buf):
        self.logger.info("Got message %s", binascii.hexlify(buf).decode())
        if b'STARTING APP' in buf:
            self.logger.warning("Device [re]started")
            self.do_hello()
        else:
            cksum = buf[-2:]
            buf = buf[:-2]
            if crc(buf) != cksum:
                self.logger.error("CRC mismatch: %s, %s", binascii.hexlify(buf).decode(), binascii.hexlify(cksum).decode())
                return
            cmd = Buffer(buf)
            if not isinstance(cmd.cmd, CommandId):
                if cmd.cmd != 0x11111c:
                    self.logger.warning("Unknown command id: %x", cmd.cmd)
            elif cmd.cmd in self._msg_handlers:
                self._msg_handlers[cmd.cmd](cmd)
            else:
                self.logger.warning("Ignoring unknown message (cmd id %02x, %s)", cmd.cmd, binascii.hexlify(buf).decode())

    def handle_dev_state_value(self, state):
        flags = [i for i in DeviceState if (state & i.value) == i.value]
        net_state = NetworkState(state & 3)
        logger.info("Device state message: state = %d (net: %s, %s, %s)", state, net_state, bin(state), flags)
        if DeviceState.APSDE_DATA_INDICATION in flags:
            self.request_incoming_data()

    def request_dev_state(self):
        req = struct.pack('<BBBHBBB', 0x07, self.next_seq(), 0, 8, 0, 0, 0)
        self.send_message(req)

    def handle_dev_state(self, buf: Buffer):
        state = buf.pop_int('B')
        self.handle_dev_state_value(state)

    def handle_dev_state_changed(self, buf: Buffer):
        state = buf.pop_int('B')
        self.handle_dev_state_value(state)

    def handle_incoming_data(self, buf: Buffer):
        if buf.status != Status.SUCCESS:
            self.logger.warning("Incoming data with status %s", buf.status)
            return
        msg, dev_st = Message.from_buffer(buf)

        # No integration with zigpy yet, so let's just log the data
        self.logger.warning('Data: %s', msg)
        self.handle_dev_state_value(dev_st)

    def request_incoming_data(self):
        req_id = self.next_seq()
        req = struct.pack(
            '<BBBHH',
            0x17,
            req_id,
            0,
            7,
            1,
        )
        self.send_message(req)

    def send_message(self, buf):
        self.logger.info("Sending message %s", binascii.hexlify(buf).decode())
        pack = self._drv.send(buf + crc(buf))
        self.logger.debug("Encoded message: %s", binascii.hexlify(pack).decode())
        self._transport.write(bytes([0xC0]))
        self._transport.write(pack)

    def request(self, nwk, profile, cluster, src_ep, dst_ep, sequence, data, expect_reply=True, timeout=10):
        pass

    def ignore_message(self, buf):
        pass

