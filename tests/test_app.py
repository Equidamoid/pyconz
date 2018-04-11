import pytest
import binascii
from pyconz.app import SerialConnection, crc, Message, Address
from pyconz.utils import Buffer
from pyconz import protocol

# device status
test_msg07 = binascii.unhexlify(b'0701000800aa000244ff')

# incoming data
test_msg17 = binascii.unhexlify(b'1702002b0024002a0200000103336a0e00002618840304010600070018880a0000100000af1faa000104ab04fb')

# network info -> mac address
test_msg0a_mac = binascii.unhexlify(b'0a05001000090001e77f01ffff2e210023fc')


def test_checksum():
    for msg in test_msg07, test_msg17, test_msg0a_mac:
        assert crc(msg[:-2]) == msg[-2:]
    pass


def test_header():
    b = Buffer(test_msg07)
    assert b.status == protocol.Status.SUCCESS
    assert b.seq == 1
    assert b.cmd == protocol.CommandId.DEVICE_STATE
    assert len(b.data) == 5

    b = Buffer(test_msg17)
    assert b.status == protocol.Status.SUCCESS
    assert b.seq == 2
    assert b.cmd == protocol.CommandId.APS_DATA_INDICATION

    b = Buffer(test_msg0a_mac)
    assert b.status == protocol.Status.SUCCESS
    assert b.seq == 5
    assert b.cmd == protocol.CommandId.READ_PARAMETER


def test_incoming():
    b = Buffer(test_msg17)
    msg, st = Message.from_buffer(b)
    assert msg
    assert msg.src == Address(protocol.AddressType.IEEE, 0x84182600000e6a33, 3)
    assert msg.dest == Address(protocol.AddressType.NWK, 0, 1)
    assert msg.cluster_id == 0x6
    assert msg.profile_id == 0x0104
    decoded = msg.deserialize()
    assert decoded[0] == 136
    assert decoded[1] == 10