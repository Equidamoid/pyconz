import enum
import struct
import collections
import typing


class CommandId(enum.Enum):
    DEVICE_STATE = 0x07
    CHANGE_NETWORK_STATE = 0x08
    READ_PARAMETER = 0x0a
    WRITE_PARAMETER = 0x0b
    DEVICE_STATE_CHANGED = 0x0e
    APS_DATA_REQUEST = 0x12
    APS_DATA_CONFIRM = 0x04
    APS_DATA_INDICATION = 0x17


class DeviceState(enum.Enum):
    # NET_STATE_MASK = 3
    APSDE_DATA_CONFIRM = 0x04
    APSDE_DATA_INDICATION = 0x08
    CONF_CHANGED = 0x10
    APSDE_DATA_REQUEST = 0x20


class NetworkState(enum.Enum):
    OFFLINE = 0
    JOINING = 1
    CONNECTED = 2
    LEAVING = 3


class Status(enum.Enum):
    SUCCESS = 0
    FAILURE = 1
    BUSY = 2
    TIMEOUT = 3
    UNSUPPORTED = 4
    ERROR = 5
    NO_NETWORK = 6
    INVALID_VALUE = 7


class AddressType(enum.Enum):
    Group = 1
    NWK = 2
    IEEE = 3


class ApsDesignedCoordinator(enum.Enum):
    Coordinator = 1
    Router = 0


class NetworkParameter(enum.Enum):
    MAC_ADDR = 0x01
    NWK_PANID = 0x05
    NWK_ADDR = 0x07
    NWK_EXTENDED_PANID = 0x08
    APS_DESIGNED_COORDINATOR = 0x09
    SECURITY_MODE = 0x10


NetworkParamInfo = collections.namedtuple('NetworkParamInfo', ['format', 'str_format'])

param_types = {     # type: typing.Dict[NetworkParameter, NetworkParamInfo]
    NetworkParameter.MAC_ADDR: NetworkParamInfo('Q', '%x'),
    NetworkParameter.NWK_PANID: NetworkParamInfo('H', '%x'),
    NetworkParameter.NWK_ADDR: NetworkParamInfo('H', '%x'),
    NetworkParameter.NWK_EXTENDED_PANID: NetworkParamInfo('Q', '%x'),
    NetworkParameter.APS_DESIGNED_COORDINATOR: NetworkParamInfo('B', '%x'),
    NetworkParameter.SECURITY_MODE: NetworkParamInfo('B', '%x'),
}


def crc(s):
    # type: (bytes)->bytes
    ret = 0
    for i in s:
        ret += i
    c0 = (~(ret) + 1) & 0xff
    c1 = ((~(ret) + 1) >> 8) & 0xff
    ret = (c0 + (c1 << 8))
    return struct.pack('H', ret)