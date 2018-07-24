from .connection import Address, AddressType
import zigpy.types

def addr_to_zigpy_ieee(addr: Address):
    import zigpy.types
    if isinstance(addr, str):
        return zigpy.types.EUI64([int(i, 16) for i in addr.split(':')])
    if isinstance(addr, Address):
        assert addr.mode == AddressType.IEEE
        addr_v = addr.addr
    else:
        addr_v = addr
    l = []
    assert addr_v
    while len(l) < 8:
        l.append(zigpy.types.uint8_t(addr_v % 256))
        addr_v //= 256
    return zigpy.types.EUI64(l)