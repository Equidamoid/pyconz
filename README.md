### pyconz

A python implementation of [deCONZ](https://www.dresden-elektronik.de/funktechnik/products/software/pc/deconz/) serial UART protocol for communicating with [ConBee](https://www.dresden-elektronik.de/conbee/) and [RaspBee](https://www.dresden-elektronik.de/raspbee/) devices from [Dresden-Elektronik](https://github.com/dresden-elektronik/) for primarly use with [ZigPy](https://github.com/zigpy/zigpy/) to implement native ZigBee adapter/dongle support.

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

Pull requests are welcome!
