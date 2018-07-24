from .connection import SerialConnection, Message, Address, AddressType
from . import protocol
import asyncio
import zigpy.zcl
import logging
import zigpy.zcl.clusters
import zigpy.appdb
import zigpy.application
import zigpy.device
from .zigpy_utils import addr_to_zigpy_ieee

logger = logging.getLogger(__name__)


class ZigpyConnection(SerialConnection):
    def __init__(self):
        SerialConnection.__init__(self)
        self.app = zigpy.application.ControllerApplication('/Users/equi/PycharmProjects/raspbee/rbee/db.sqlite')
        self.app.request = self.zigpy_request_proxy
        self.app_ready = False

    async def zigpy_request_proxy(self, nwk, profile, cluster, src_ep, dst_ep, sequence, data, expect_reply=True, timeout=10):
        logger.warning('Request proxy: %s', [nwk, profile, cluster, src_ep, dst_ep, sequence, data, expect_reply, timeout])
        ret = asyncio.Future()
        if src_ep:
            src_ep = 1
        msg = Message()
        msg.dest = Address(AddressType.NWK, nwk, dst_ep)
        msg.src = Address(AddressType.IEEE, None, src_ep)
        msg.profile_id = profile
        msg.cluster_id = cluster
        msg.data = data
        msg.request_id = sequence

        self.send_msg(msg)

        self.zigpy_futures[sequence] = ret
        done, pending = await asyncio.wait([ret], timeout=timeout)
        if ret in pending:
            logger.error("Request %d timed out!", sequence)
            raise TimeoutError()

        return ret.result()

    async def get_or_create_device(self, nwk, ieee) -> zigpy.device.Device:
        assert ieee
        try:
            return self.app.get_device(ieee=ieee, nwk=nwk)
        except KeyError:
            if not isinstance(ieee, zigpy.types.EUI64):
                ieee = addr_to_zigpy_ieee(ieee)
            dev = self.app.add_device(ieee, nwk)
            self.logger.warning("New device created, scheduling initalization and waiting")
            dev.schedule_initialize()

            # FIXME ugly!
            while dev.initializing:
                logger.warning("Waiting for initialization, status: %s", dev.status)
                await asyncio.sleep(1)
        return self.app.get_device(nwk=nwk)


    async def wait_for_startup(self):
        while not self.app_ready:
            await asyncio.sleep(0.1)

    async def startup(self):
        my_nwk = await self.get_parameter(protocol.NetworkParameter.NWK_ADDR)
        my_ieee = await self.get_parameter(protocol.NetworkParameter.MAC_ADDR)
        self.app._ieee = addr_to_zigpy_ieee(my_ieee)
        self.app._nwk = my_nwk
        logging.warning("my NWK: 0x%x, my_ieee: %s", my_nwk, self.app.ieee)
        self.device = await self.get_or_create_device(self.app.nwk, self.app.ieee)
        self.app_ready = True
        logging.warning("Startup completed")


    def handle_incoming_message(self, msg: Message):
        self.logger.warning('Data: %s', msg)
        if msg.src.mode == AddressType.IEEE:
            ieee = addr_to_zigpy_ieee(msg.src)
            try:
                dev = self.app.get_device(ieee=ieee)    # type: zigpy.device.Device
            except KeyError:
                self.app.add_device(ieee=ieee, nwk=0)
                dev = self.app.get_device(ieee=ieee)    # type: zigpy.device.Device

            if msg.src.endpoint:
                dev.add_endpoint(msg.src.endpoint)
                tsn, cluster_id, is_reply, args = dev.deserialize(msg.src.endpoint, msg.cluster_id, msg.data)
            else:
                tsn, cluster_id, is_reply, args = dev.zdo.deserialize(msg.cluster_id, msg.data)
            logger.warning('tsn: %s, cluster_id: 0x%04x, is_reply: %s, args: %s', tsn, cluster_id, is_reply, args)
            if is_reply:
                try:
                    fut = self.zigpy_futures[tsn]   # type: asyncio.Future
                except KeyError:
                    logger.error("No future to match tsn %d", tsn)
                else:
                    fut.set_result(args)
        else:
            logging.error("TODO: handle messages with source NWK address")
