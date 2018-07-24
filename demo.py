import serial.aio
import logging
import asyncio
import pyconz.connection
import pyconz.zigpy_integ
import pyconz.apps

logging.basicConfig(format='[%(asctime)s] %(message)s')
logger = logging.getLogger(__name__)

conn = pyconz.zigpy_integ.ZigpyConnection()


async def discover_neighbours(conn, dev):
    # type: (pyconz.zigby_integ.ZigpyConnection, zigpy.device.Device) -> typing.List[zigpy.device.Device]
    results = []
    results_dev = []
    while True:
        try:
            status, n_total, r_offset, r_count, data = await dev.zdo.request(0x0031, len(results))
        except TimeoutError:
            logger.error("ZDO request timed out, skipping device")
            return []
        results += data
        logger.warning("N disco: %d/%d", len(results), n_total)
        if r_offset + r_count >= n_total:
            break

    logger.warning("%d neighbours discovered for dev %s:", len(results), dev)
    for i in results:
        ieee = i.IEEEAddr
        nwk = i.NWKAddr
        n_dev = await conn.get_or_create_device(ieee=ieee, nwk=nwk)
        results_dev.append(n_dev)
        logger.warning("%s", i)
    return results_dev


async def discover_network(conn):
    # type: (pyconz.zigpy_integ.ZigpyConnection) -> (typing.List[zigpy.device.Device], typing.List[int])
    scanned_devices = {}
    devices_to_scan = {conn.device.nwk: conn.device}
    links = []

    while devices_to_scan:
        logger.warning("Discovery progress: todo: %d, scanned: %d, links: %d", len(devices_to_scan), len(scanned_devices), len(links))
        nwk, dev = list(devices_to_scan.items())[0]
        scanned_devices[nwk] = dev
        del devices_to_scan[nwk]

        for dev_n in await discover_neighbours(conn, dev):
            nwk_n = dev_n.nwk
            if not nwk_n in scanned_devices:
                devices_to_scan[nwk_n] = dev_n
            links.append([nwk, nwk_n])

    logger.warning('%r', links)
    return scanned_devices, links

def do():
    loop = asyncio.get_event_loop()
    coro = serial.aio.create_serial_connection(loop, lambda: conn, '/dev/ttyS0', baudrate=38400)
    loop.run_until_complete(coro)
    loop.run_until_complete(conn.wait_for_startup())
    loop.run_until_complete(discover_network(conn))
    loop.close()


do()

