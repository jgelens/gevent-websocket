# This class implements the Websocket protocol draft version as of May 23, 2010
# The version as of August 6, 2010 will be implementend once Firefox or
# Webkit-trunk support this version.

import binascii
import struct

class WebSocket(object):
    def __init__(self, sock, rfile, environ):
        self.rfile = rfile
        self.socket = sock
        self.origin = environ.get('HTTP_ORIGIN')
        self.protocol = environ.get('HTTP_SEC_WEBSOCKET_PROTOCOL', 'unknown')
        self.path = environ.get('PATH_INFO')
        self.websocket_closed = False

    def send(self, message):
        if self.websocket_closed:
            raise Exception("Connection was terminated")

        if isinstance(message, unicode):
            message = message.encode('utf-8')
        elif isinstance(message, str):
            message = unicode(message).encode('utf-8')
        else:
            raise Exception("Invalid message encoding")

        self.socket.sendall("\x00" + message + "\xFF")

    def close_connection(self):
        if not self.websocket_closed:
            self.websocket_closed = True
            self.socket.shutdown(True)
            self.socket.close()
        else:
            return

    def _message_length(self):
        # TODO: buildin security agains lengths greater than 2**31 or 2**32
        length = 0

        while True:
            byte_str = self.rfile.read(1)

            if not byte_str:
                return 0
            else:
                byte = ord(byte_str)

            if byte != 0x00:
                length = length * 128 + (byte & 0x7f)
                if (byte & 0x80) != 0x80:
                    break

        return length

    def _read_until(self):
        bytes = []

        while True:
            byte = self.rfile.read(1)
            if ord(byte) != 0xff:
                bytes.append(byte)
            else:
                break

        return ''.join(bytes)

    def wait(self):
        while True:
            if self.websocket_closed:
                return None

            frame_str = self.rfile.read(1)
            if not frame_str:
                # Connection lost?
                self.websocket_closed = True
                continue
            else:
                frame_type = ord(frame_str)


            if (frame_type & 0x80) == 0x00: # most significant byte is not set

                if frame_type == 0x00:
                    bytes = self._read_until()
                    return bytes.decode("utf-8", "replace")
                else:
                    self.websocket_closed = True

            elif (frame_type & 0x80) == 0x80: # most significant byte is set
                # Read binary data (forward-compatibility)
                if frame_type != 0xff:
                    self.websocket_closed = True
                else:
                    length = self._message_length()
                    if length == 0:
                        self.websocket_closed = True
                    else:
                        self.rfile.read(length) # discard the bytes
            else:
                raise IOError("Reveiced an invalid message")

class WebSocketVersion7(WebSocket):
    FIN = int("10000000", 2)
    RSV = int("01110000", 2)
    OPCODE = int("00001111", 2)
    MASK = int("10000000", 2)
    PAYLOAD = int("01111111", 2)

    OPCODE_TEXT = 0x1
    OPCODE_BINARY = 0x2
    OPCODE_CLOSE = 0x8
    OPCODE_PING = 0x9
    OPCODE_PONG = 0xA

    REASON_NORMAL = 1000
    REASON_GOING_AWAY = 1001

    LEN_16 = 126
    LEN_64 = 127

    def __init__(self, sock, rfile, environ):
        self.rfile = rfile
        self.socket = sock
        self.origin = environ.get('HTTP_SEC_WEBSOCKET_ORIGIN')
        self.protocol = environ.get('HTTP_SEC_WEBSOCKET_PROTOCOL', 'unknown')
        self.path = environ.get('PATH_INFO')
        self.websocket_closed = False

    def wait(self):
        msg = ""
        while True:
            if self.websocket_closed:
                return None

            opcode, length = struct.unpack('!BB', self.rfile.read(2))

            if self.RSV & opcode:
                self.close(1002, 'Reserved bits cannot be set')
                return None

            is_final_frag = (self.FIN & opcode) != 0

    def _encodeText(self, s):
        if isinstance(s, unicode):
            return s.encode('utf-8')
        elif isinstance(s, str):
            return unicode(s).encode('utf-8')
        else:
            raise Exception('Invalid encoding')

    def send(self, opcode, message):
        if self.websocket_closed:
            raise Exception('Connection was terminated')

        if opcode < self.OPCODE_TEXT or (opcode > self.OPCODE_BINARY and 
                opcode < self.OPCODE_CLOSE) or opcode > self.OPCODE_PONG:
            raise Exception('Invalid opcode %d' % opcode)

        if opcode == self.OPCODE_TEXT:
            message = self._encodeText(message)

        length = len(message)

        if opcode == self.OPCODE_TEXT:
            message = struct.pack('!%ds' % length, message)

        if length < 126:
            preamble = struct.pack('!BB', self.FIN | opcode, length)
        elif length < 2 ** 16:
            preamble = struct.pack('!BBH', self.FIN | opcode, self.LEN_16, length)
        else:
            preamble = struct.pack('!BBQ', self.FIN | opcode, self.LEN_64, length)

        self.socket.sendall(preamble + message)

    def close(self, reason, message):
        message = self._encodeText(message)
        self.send(self.OPCODE_CLOSE, struct.pack('!H%ds' % len(message), reason, message))
        self.websocket_closed = True

        # based on gevent/pywsgi.py
        # see http://pypi.python.org/pypi/gevent#downloads
        if self.socket is not None:
            try:
                self.socket._sock.close()
                self.socket.close()
            except socket.error:
                pass
