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
        self.request_id = None  # type: int

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
        return 0, 0, 0, binascii.hexlify(self.data),

    def __str__(self):
        tsn, cmd, reply, value = self.deserialize()

        if isinstance(value, bytes):
            value = binascii.hexlify(value).decode()
        return '[%04x:%04x] %s -> %s: [%s]' % (
            self.cluster_id, self.profile_id, self.src, self.dest,
            binascii.hexlify(self.data).decode())


class SerialConnection:
    def __init__(self):
        super().__init__()
        self._transport = None  # type: serial.aio.SerialTransport
        self._seq = 0
        self._drv = sliplib.Driver()
        self.logger = logger
        self._msg_handlers = {
            CommandId.DEVICE_STATE: self._handle_dev_state,
            CommandId.DEVICE_STATE_CHANGED: self._handle_dev_state_changed,
            # 0x1c: self.ignore_message,
            CommandId.APS_DATA_INDICATION: self._handle_incoming_data,
            CommandId.READ_PARAMETER: self._handle_get_parameter_response,
            CommandId.WRITE_PARAMETER: self._handle_set_parameter_response,
            CommandId.APS_DATA_REQUEST: self._handle_data_request_response,
        }
        self._requests = {}     # type: typing.Dict[int, asyncio.Future]
        self.zigpy_futures = {}

    def _handle_data_request_response(self, buf):
        self.logger.info("APS_DATA_REQUEST result: %s", buf.status)

    def eof_received(self):
        logging.error("EOF")

    async def read_all_parameters(self):
        data = {}
        for p in NetworkParameter:
            data[p] = await self.get_parameter(p)
        self.logger.warning("Read device parameters:")
        for i in sorted(data):
            self.logger.warning('%s = %s', i, data[i])
        return data

    def get_parameter(self, p):
        # type: (protocol.NetworkParameter) -> asyncio.Future
        ret = asyncio.Future()
        seq = self._next_seq()
        req = struct.pack('<BBBHHB', 0x0a, seq, 0, 8, 1, p.value)
        self._requests[seq] = ret
        self._send_command(req)
        return ret

    def _handle_get_parameter_response(self, buf: Buffer):
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

    def set_parameter(self, p, v):
        # type: (protocol.NetworkParameter, typing.Any) -> asyncio.Future
        p_type = param_types[p]
        seq = self._next_seq()
        pl = struct.pack(p_type.format, v)
        hdr = struct.pack('<BBBHHB', protocol.CommandId.WRITE_PARAMETER.value, seq, 0, len(pl) + 8, len(pl) + 1, p.value)
        ret = asyncio.Future()
        self._requests[seq] = ret
        self._send_command(hdr + pl)
        return ret

    def _handle_set_parameter_response(self, buf: Buffer):
        seq = buf.seq
        pl_len = buf.pop_int('<H')
        param = buf.pop_enum('B', NetworkParameter)
        p_type = param_types[param]     # type: protocol.NetworkParamInfo
        data = buf.pop_int(p_type.format)
        status = buf.status
        self.logger.warning("Status for writing %s: %s", param, status)
        try:
            f = self._requests[seq]
            if status == protocol.Status.SUCCESS:
                f.set_result()
            else:
                f.set_exception(RuntimeError("Error %s" % status))
            del self._requests[seq]
        except KeyError:
            pass

    def set_network_state(self, state=protocol.NetworkState.CONNECTED):
        seq = self._next_seq()
        msg = struct.pack(
            '<BBBHB',
            protocol.CommandId.CHANGE_NETWORK_STATE.value,
            seq,
            0,
            6, state.value)
        self._send_command(msg)

    def _next_seq(self):
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
                self._handle_command(i)
            except:
                self.logger.exception("Error while handling command %s", binascii.hexlify(i).decode())

    def connection_lost(self, exc):
        self.logger.error("Connection lost")

    def do_hello(self):
        self.request_dev_state()
        asyncio.ensure_future(self.startup())

    def hard_reset(self):
        os.system('gpio write 0 0; sleep 2; gpio write 0 1')
        self._drv = sliplib.Driver()

    def _handle_command(self, buf):
        self.logger.debug("Incoming serial message %s", binascii.hexlify(buf).decode())
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
                self.logger.warning("Ignoring unknown message (cmd id %s, %s)", cmd.cmd, binascii.hexlify(buf).decode())

    def _handle_dev_state_value(self, state):
        flags = [i for i in DeviceState if (state & i.value) == i.value]
        net_state = NetworkState(state & 3)
        logger.info("Device state message: state = %d (net: %s, %s, %s)", state, net_state, bin(state), flags)
        if DeviceState.APSDE_DATA_INDICATION in flags:
            self.request_incoming_data()

    def request_dev_state(self):
        req = struct.pack('<BBBHBBB', protocol.CommandId.DEVICE_STATE.value, self._next_seq(), 0, 8, 0, 0, 0)
        self._send_command(req)

    def _handle_dev_state(self, buf: Buffer):
        state = buf.pop_int('B')
        self._handle_dev_state_value(state)

    def _handle_dev_state_changed(self, buf: Buffer):
        state = buf.pop_int('B')
        self._handle_dev_state_value(state)

    def _handle_incoming_data(self, buf: Buffer):
        if buf.status != Status.SUCCESS:
            self.logger.warning("Incoming data with status %s", buf.status)
            return
        msg, dev_st = Message.from_buffer(buf)
        try:
            self.handle_incoming_message(msg)
        except:
            self.logger.exception("Error while processing message %s", msg)
        self._handle_dev_state_value(dev_st)

    def handle_incoming_message(self, msg: Message):
        self.logger.warning("Unhandled message: %s", msg)

    def request_incoming_data(self):
        req_id = self._next_seq()
        req = struct.pack(
            '<BBBHH',
            protocol.CommandId.APS_DATA_INDICATION.value,
            req_id,
            0,
            7,
            1,
        )
        self._send_command(req)

    def _send_command(self, buf):
        self.logger.info("Sending message %s", binascii.hexlify(buf).decode())
        pack = self._drv.send(buf + crc(buf))
        self.logger.debug("Encoded message: %s", binascii.hexlify(pack).decode())
        self._transport.write(bytes([0xC0]))
        self._transport.write(pack)

    def send_msg(self, msg: Message):
        assert msg.dest.mode == AddressType.NWK
        pl = struct.pack(
            '<BBBHBHHBH',
            msg.request_id,
            0,
            0x02,  # FIXME NWK
            msg.dest.addr,
            msg.dest.endpoint,
            msg.profile_id,
            msg.cluster_id,
            msg.src.endpoint,
            len(msg.data)
        )
        pl += msg.data
        pl += struct.pack('<BB', 0, 5)
        buf = struct.pack(
            '<BBBHH',
            0x12,
            self._next_seq(),
            0,
            len(pl) + 7,
            len(pl)

        )
        self._send_command(buf + pl)

    def ignore_message(self, buf):
        pass


