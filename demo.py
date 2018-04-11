import serial
import serial.aio
import logging
import pyconz.app

logging.basicConfig(format='[%(asctime)s] %(message)s')
logger = logging.getLogger(__name__)

import asyncio

conn = pyconz.app.SerialConnection()


def do():
    loop = asyncio.get_event_loop()
    coro = serial.aio.create_serial_connection(loop, lambda: conn, '/dev/ttyS0', baudrate=38400)
    loop.run_until_complete(coro)
    loop.run_forever()
    loop.close()


do()

