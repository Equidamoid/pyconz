import asyncio
import serial.aio
import serial
import typing
import logging
import binascii

loop = asyncio.get_event_loop()


class SocketForwardingProtocol(asyncio.Protocol):
    def __init__(self, tty):
        self.peer = tty         # type: ProxyConnection
        self.transport = None   # type: asyncio.Transport

    def data_received(self, data):
        if not self.peer:
            logging.error("Peer is None, wtf?")
            return
        if self.peer.transport is None:
            logging.error("Peer not ready")
            return
        logging.warning('cli->dev: %s', binascii.hexlify(data).decode())
        self.peer.transport.write(data)

    def connection_made(self, transport):
        self.transport = transport


class ProxyConnection(asyncio.Protocol):

    def __init__(self):
        self.socket = None      # type: SocketForwardingProtocol
        self.transport = serial.aio.SerialTransport(loop, self, serial.Serial('/dev/ttyS0', baudrate=38400))

    def data_received(self, data):
        super().data_received(data)
        logging.warning("dev->cli: %s", binascii.hexlify(data).decode())
        if self.socket and self.socket.transport:
            self.socket.transport.write(data)
        else:
            logging.warning("No active socket connection")

    def socket_factory(self):
        logging.warning("Got new connection")
        if self.socket:
            logging.warning("Closing existing client socket")
            self.socket.transport.close()
            self.socket.peer = None
        self.socket = SocketForwardingProtocol(self)
        return self.socket


def main():
    logging.basicConfig(format='[%(asctime)s - %(message)s')
    pc = ProxyConnection()
    server = loop.create_server(pc.socket_factory, host='0.0.0.0', port=9999, reuse_address=True)
    asyncio.ensure_future(server)

    loop.run_forever()


if __name__ == '__main__':
    main()