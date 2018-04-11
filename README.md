### pyconz

A python implementation of [deCONZ](https://www.dresden-elektronik.de/funktechnik/products/software/pc/deconz/)
serial protocol for communicating with [Raspbee](https://www.dresden-elektronik.de/raspbee/) devices.

#### Current status

Library supports basic protocol features:
 - Getting network parameters
 - Receiving data messages (and decoding them if possible using zigpy)
 - In theory, sending data messages, but I can't really generate proper payload to test it yet.

#### Development

You will need python3 and some dependences:

     # of course, it's better to use virtualenv and/or packet manager
     pip install serial sliblib zigpy

There is a demo.py script that opens the connection and prints incoming data to stderr.

Pull requests are welcome!