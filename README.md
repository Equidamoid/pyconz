### pyconz


[pyconz](https://github.com/Equidamoid/pyconz) is a Python implementation for the [Zigpy](https://github.com/zigpy/) project to implement [deCONZ](https://www.dresden-elektronik.de/funktechnik/products/software/pc/deconz/) based [Zigbee](https://www.zigbee.org) radio devices.

This uses the deCONZ serial protocol for communicating with [ConBee](https://www.dresden-elektronik.de/conbee/) and [RaspBee](https://www.dresden-elektronik.de/raspbee/) adapters from [Dresden-Elektronik](https://github.com/dresden-elektronik/).


#### Current status

Library supports basic protocol features:
 - Getting network parameters
 - Receiving data messages (and decoding them if possible using zigpy).
 - In theory, sending data messages, but I can't really generate proper payload to test it yet.

#### Development

You will need python3 and some dependences:

     # of course, it's better to use virtualenv and/or packet manager
     pip install pyserial sliplib zigpy

There is a demo.py script that opens the connection and prints incoming data to stderr.

Note! Documentation of the deCONZ serial protocol can currently be obtained by contancting Dresden-Elektronik employees via GitHub here https://github.com/dresden-elektronik/deconz-rest-plugin/issues/158

Pull requests are welcome!
